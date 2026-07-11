/**
 * 统一的灵感生成策略元数据。
 * IdeaLabView / IdeaProvenanceFlow / IdeaDerivationBridge 共同引用此文件，
 * 避免三处独立维护造成同一 strategy 在页内显示不一致。
 */
export interface StrategyMeta {
  label: string
  action: string
  colorClass: string
}

/** 覆盖后端所有已知 strategy 枚举值（含历史别名） */
export const STRATEGY_META: Record<string, StrategyMeta> = {
  // 跨域迁移
  transfer:             { label: '跨域迁移',      action: '将原论文方法迁移到新场景，解决类似但未被覆盖的问题',             colorClass: 'strategy-transfer' },
  migration:            { label: '跨域迁移',      action: '将原论文方法迁移到新场景，解决类似但未被覆盖的问题',             colorClass: 'strategy-transfer' },
  // 方法融合
  stitch:               { label: '方法融合',      action: '组合多篇论文的不同方法，形成协同效果',                           colorClass: 'strategy-stitch' },
  stitching:            { label: '方法融合',      action: '组合多篇论文的不同方法，形成协同效果',                           colorClass: 'strategy-stitch' },
  combine:              { label: '方法融合',      action: '组合多篇论文的不同方法，形成协同效果',                           colorClass: 'strategy-stitch' },
  synthesis:            { label: '方法融合',      action: '综合多篇论文的核心贡献，提出整合性研究思路',                     colorClass: 'strategy-stitch' },
  // 修补改进
  patch:                { label: '修补改进',      action: '针对已知局限提出直接修补，在保留原方法优势的同时改善其弱点',     colorClass: 'strategy-patch' },
  patching:             { label: '修补改进',      action: '针对已知局限提出直接修补，在保留原方法优势的同时改善其弱点',     colorClass: 'strategy-patch' },
  fix:                  { label: '修补改进',      action: '针对已知局限提出直接修补，在保留原方法优势的同时改善其弱点',     colorClass: 'strategy-patch' },
  fix_limitation:       { label: '修补改进',      action: '针对已知局限提出直接修补，在保留原方法优势的同时改善其弱点',     colorClass: 'strategy-patch' },
  // 场景扩展
  extend:               { label: '场景扩展',      action: '将原方法推广到更多应用场景或数据分布',                           colorClass: 'strategy-extend' },
  augmentation:         { label: '场景扩展',      action: '通过扩充数据、条件或模态，延伸原方法的适用边界',                 colorClass: 'strategy-extend' },
  // 空白探索
  explore:              { label: '空白探索',      action: '填补领域中尚未被研究者关注的问题空白',                           colorClass: 'strategy-explore' },
  gap:                  { label: '空白探索',      action: '识别并填补领域中的研究空缺',                                     colorClass: 'strategy-explore' },
  // 反事实 / 假设挑战
  counterfactual:       { label: '反事实推断',    action: '反转原论文的假设或前提，探索不同解决路径',                       colorClass: 'strategy-counter' },
  negate:               { label: '假设挑战',      action: '质疑原论文的核心假设，探索替代解释',                             colorClass: 'strategy-counter' },
  contrast:             { label: '对比验证',      action: '设计对照实验以验证或反驳原论文的核心结论',                       colorClass: 'strategy-counter' },
  // 资源约束重设计
  resource_constrained: { label: '资源约束重设计', action: '在更严格的资源约束下重新设计原论文方法',                        colorClass: 'strategy-resource' },
  resource_constraint:  { label: '资源约束重设计', action: '在更严格的资源约束下重新设计原论文方法',                        colorClass: 'strategy-resource' },
}

/** 回退项：strategy 为空或未收录时使用 */
const FALLBACK_META: StrategyMeta = {
  label: '原创构想',
  action: '综合论文证据，提出新的研究思路',
  colorClass: 'strategy-default',
}

/** 返回完整策略元数据；未匹配时提供带原始值的回退标签 */
export function getStrategyMeta(strategy: string | undefined | null): StrategyMeta & { raw: string } {
  const raw = (strategy ?? '').trim()
  const key = raw.toLowerCase()
  const found = STRATEGY_META[key] ?? Object.entries(STRATEGY_META).find(([k]) => key.includes(k))?.[1]
  if (found) return { ...found, raw }
  return {
    ...FALLBACK_META,
    label: raw ? `未归类策略（${raw}）` : FALLBACK_META.label,
    raw,
  }
}

/** 仅需中文标签时使用（简化版） */
export function getStrategyLabel(strategy: string | undefined | null): string {
  return getStrategyMeta(strategy).label
}
