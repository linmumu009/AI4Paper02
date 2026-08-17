import { describe, expect, it } from 'vitest'

import type { AutoClassifyFolder, AutoClassifyFolderSuggestion } from '../api'
import type { KbFolder } from '../types/paper'
import {
  appendFolderSuggestions,
  buildAutoClassifyTree,
  flattenAutoClassifyTree,
  mergeKnowledgeBaseFolderTree,
} from './autoClassifyFolders'

function keyFactory() {
  let value = 0
  return () => `new-${++value}`
}

describe('auto-classify folder hierarchy', () => {
  it('uses the real knowledge-base hierarchy as the backbone', () => {
    const kbFolders = [
      {
        id: 1,
        name: '我的研究',
        parent_id: null,
        origin: 'user',
        children: [
          {
            id: 2,
            name: '推理',
            parent_id: 1,
            origin: 'user',
            children: [],
            papers: [],
          },
        ],
        papers: [],
        created_at: '',
        updated_at: '',
      },
    ] as unknown as KbFolder[]
    const saved: AutoClassifyFolder[] = [
      { name: '旧名字', description: '模型推理研究', folder_id: 2, origin: 'ai' },
      { name: '已删除目录', description: '', folder_id: 999, origin: 'ai' },
    ]

    const tree = mergeKnowledgeBaseFolderTree(kbFolders, saved, keyFactory())

    expect(tree[0]?.name).toBe('我的研究')
    expect(tree[0]?.children[0]).toMatchObject({
      name: '推理',
      description: '模型推理研究',
      origin: 'ai',
    })
    expect(flattenAutoClassifyTree(tree).some(folder => folder.folder_id === 999)).toBe(false)
  })

  it('preserves unsynced nested relationships across save and reload', () => {
    const makeKey = keyFactory()
    const original = buildAutoClassifyTree([
      { name: '父目录', description: '', folder_id: null, _key: 'parent', origin: 'user' },
      { name: '子目录', description: '', folder_id: null, _key: 'child', _parent_key: 'parent', origin: 'user' },
    ], makeKey)

    const saved = flattenAutoClassifyTree(original)
    const reloaded = buildAutoClassifyTree(saved, makeKey)

    expect(reloaded).toHaveLength(1)
    expect(reloaded[0]?.children[0]?.name).toBe('子目录')
    expect(saved[1]?._parent_key).toBe('parent')
  })

  it('adds AI suggestions under the specified existing parent without duplicates', () => {
    const tree = buildAutoClassifyTree([
      { name: '人工智能', description: '', folder_id: 1, origin: 'user' },
    ], keyFactory())
    const suggestion = {
      name: '推理优化',
      description: '推理效率研究',
      folder_id: null,
      parent_id: 1,
      parent_path: '人工智能',
      origin: 'ai',
      suggestion_reason: '现有目录过宽',
      paper_ids: ['p1'],
      paper_count: 1,
    } satisfies AutoClassifyFolderSuggestion

    expect(appendFolderSuggestions(tree, [suggestion, suggestion], keyFactory())).toBe(1)
    expect(tree[0]?.children[0]).toMatchObject({
      name: '推理优化',
      origin: 'ai',
      folder_id: null,
    })
  })
})
