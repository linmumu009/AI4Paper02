import type { AutoClassifyFolder, AutoClassifyFolderSuggestion } from '../api'
import type { KbFolder } from '../types/paper'

export type FolderOrigin = 'user' | 'ai' | 'system'

export interface AutoClassifyFolderNode {
  _key: string
  name: string
  description: string
  folder_id: number | null
  origin: FolderOrigin
  suggestion_reason?: string
  paper_count?: number
  children: AutoClassifyFolderNode[]
}

function normalizeOrigin(origin: unknown, name = ''): FolderOrigin {
  if (name.trim() === '未分类') return 'system'
  return origin === 'ai' ? 'ai' : 'user'
}

export function buildAutoClassifyTree(
  flat: AutoClassifyFolder[],
  makeKey: () => string,
): AutoClassifyFolderNode[] {
  if (!flat.length) return []
  const usedKeys = new Set<string>()
  const byId = new Map<number, AutoClassifyFolderNode>()
  const byKey = new Map<string, AutoClassifyFolderNode>()
  const indexByNode = new Map<AutoClassifyFolderNode, number>()
  const nodes = flat.map((folder, index) => {
    let key = folder._key || (folder.folder_id ? `kb-${folder.folder_id}` : makeKey())
    if (usedKeys.has(key)) key = makeKey()
    usedKeys.add(key)
    const node: AutoClassifyFolderNode = {
      _key: key,
      name: folder.name || '',
      description: folder.description || '',
      folder_id: folder.folder_id ?? null,
      origin: normalizeOrigin(folder.origin, folder.name),
      suggestion_reason: folder.suggestion_reason,
      paper_count: folder.paper_count,
      children: [],
    }
    if (node.folder_id != null && !byId.has(node.folder_id)) {
      byId.set(node.folder_id, node)
    }
    byKey.set(key, node)
    indexByNode.set(node, index)
    return node
  })

  const roots: AutoClassifyFolderNode[] = []
  flat.forEach((folder, index) => {
    const node = nodes[index]
    if (!node) return
    const parent = folder.parent_id != null
      ? byId.get(folder.parent_id)
      : folder._parent_key
        ? byKey.get(folder._parent_key)
        : undefined
    if (parent && parent !== node && (indexByNode.get(parent) ?? index) < index) {
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  })
  return roots
}

export function flattenAutoClassifyTree(
  nodes: AutoClassifyFolderNode[],
  parentFolderId: number | null = null,
  parentKey: string | null = null,
): AutoClassifyFolder[] {
  const result: AutoClassifyFolder[] = []
  for (const node of nodes) {
    result.push({
      name: node.name,
      description: node.description,
      folder_id: node.folder_id,
      parent_id: parentFolderId,
      origin: node.origin,
      suggestion_reason: node.suggestion_reason,
      paper_count: node.paper_count,
      _key: node._key,
      _parent_key: parentKey,
    })
    result.push(...flattenAutoClassifyTree(node.children, node.folder_id, node._key))
  }
  return result
}

function flattenKnowledgeBaseFolders(
  folders: KbFolder[],
  savedById: Map<number, AutoClassifyFolder>,
  parentId: number | null = null,
): AutoClassifyFolder[] {
  const result: AutoClassifyFolder[] = []
  for (const folder of folders) {
    const saved = savedById.get(folder.id)
    result.push({
      name: folder.name,
      description: saved?.description || '',
      folder_id: folder.id,
      parent_id: parentId,
      origin: normalizeOrigin(saved?.origin ?? folder.origin, folder.name),
      suggestion_reason: saved?.suggestion_reason,
      paper_count: saved?.paper_count,
      _key: saved?._key || `kb-${folder.id}`,
      _parent_key: saved?._parent_key,
    })
    result.push(...flattenKnowledgeBaseFolders(folder.children || [], savedById, folder.id))
  }
  return result
}

/** Merge the real KB hierarchy with saved metadata and pending suggestions. */
export function mergeKnowledgeBaseFolderTree(
  kbFolders: KbFolder[],
  savedFolders: AutoClassifyFolder[],
  makeKey: () => string,
): AutoClassifyFolderNode[] {
  const savedById = new Map<number, AutoClassifyFolder>()
  for (const folder of savedFolders) {
    if (folder.folder_id != null) savedById.set(folder.folder_id, folder)
  }
  const actualFlat = flattenKnowledgeBaseFolders(kbFolders, savedById)
  // A saved ID missing from the real tree means the user deleted that folder.
  // Respect the real KB as source of truth; only genuinely unsynced previews
  // (folder_id === null) should remain eligible for creation.
  const pending = savedFolders.filter(folder => folder.folder_id == null)
  return buildAutoClassifyTree([...actualFlat, ...pending], makeKey)
}

export function appendFolderSuggestions(
  tree: AutoClassifyFolderNode[],
  suggestions: AutoClassifyFolderSuggestion[],
  makeKey: () => string,
): number {
  const byId = new Map<number, AutoClassifyFolderNode>()
  const visit = (nodes: AutoClassifyFolderNode[]) => {
    for (const node of nodes) {
      if (node.folder_id != null) byId.set(node.folder_id, node)
      visit(node.children)
    }
  }
  visit(tree)

  let added = 0
  for (const suggestion of suggestions) {
    const parent = suggestion.parent_id == null ? undefined : byId.get(suggestion.parent_id)
    const siblings = parent?.children || tree
    const duplicate = siblings.some(node => (
      node.name.trim().toLocaleLowerCase() === suggestion.name.trim().toLocaleLowerCase()
    ))
    if (duplicate) continue
    siblings.push({
      _key: makeKey(),
      name: suggestion.name,
      description: suggestion.description,
      folder_id: null,
      origin: 'ai',
      suggestion_reason: suggestion.suggestion_reason,
      paper_count: suggestion.paper_count,
      children: [],
    })
    added += 1
  }
  return added
}
