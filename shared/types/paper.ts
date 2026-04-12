/** 单篇论文摘要（来自 file_collect _limit.md + pdf_info.json） */
export interface PaperSummary {
  institution: string
  short_title: string
  '📖标题': string
  '🌐来源': string
  paper_id: string
  '推荐理由'?: string
  '🛎️文章简介': {
    '🔸研究问题': string
    '🔸主要贡献': string
  }
  '📝重点思路': string[]
  '🔎分析总结': string[]
  '💡个人观点': string
  '一句话记忆版'?: string
  relevance_score?: number | null
  is_large_institution?: boolean
  /** Institution tier: 1=T1 顶尖, 2=T2 一流, 3=T3 知名, 4=T4 一般 */
  institution_tier?: number
  abstract?: string
  images?: string[]
  image_count?: number
}

/** 所有 paper_assets block 共有的基础字段 */
export interface AssetBlock {
  text: string
  bullets: string[]
  [key: string]: string | string[] | null | undefined
}

export interface PaperProfileBlock {
  text: string
  bullets: string[]
  title?: string
  authors?: string[]
  affiliations?: string[]
  year?: number | null
  publication_status?: string
  paper_type?: string
  research_domain?: string
  problem_gap?: string
  position_in_literature?: string
}

export interface ObjectiveBlock extends AssetBlock {
  research_questions?: string[]
  claimed_contributions?: string[]
}

export interface MethodBlock extends AssetBlock {
  input?: string | null
  task_or_object?: string | null
  architecture_or_paradigm?: string | null
  key_mechanisms?: string[]
  training_required?: string | null
  training_or_optimization?: string | null
  inference_strategy?: string | null
  novelty?: string[]
}

export interface DataBlock extends AssetBlock {
  datasets_or_materials?: string[]
  data_source?: string | null
  data_scale?: string | null
  domain_scope?: string | null
}

export interface ExperimentBlock extends AssetBlock {
  design?: string | null
  baselines_or_comparators?: string[]
  variables_or_modules?: string[]
  ablation_or_counterfactual?: string | null
  argumentation_structure?: string | null
}

export interface MetricsBlock extends AssetBlock {
  metric_names?: string[]
  evaluation_protocol?: string | null
  judge_or_annotation_method?: string | null
}

export interface ResultsBlock extends AssetBlock {
  main_findings?: string[]
  numerical_results?: string[]
  phenomena?: string[]
  mechanism_explanations?: string[]
}

export interface EvidenceChainBlock extends AssetBlock {
  claim_to_evidence?: string[]
  strongly_supported_claims?: string[]
  weakly_supported_claims?: string[]
  unsupported_or_overextended_claims?: string[]
  key_evidence_from_figures_tables_appendix?: string[]
}

export interface LimitationsBlock extends AssetBlock {
  scope_boundaries?: string[]
  threats_to_validity?: string[]
  generalization_limits?: string[]
}

export interface CriticalAnalysisBlock extends AssetBlock {
  strongest_argument?: string
  weakest_argument?: string
  substantive_contributions?: string[]
  packaging_or_framing_elements?: string[]
  strong_conclusions?: string[]
  weak_conclusions?: string[]
  needs_more_evidence?: string[]
  reproduction_or_extension_priorities?: string[]
}

export interface SummaryBlock extends AssetBlock {
  one_sentence_summary?: string
  three_takeaways?: string[]
  literature_review_comment?: string
}

/** 完整 paper_assets 条目（新 13-key schema，兼容旧 8-key） */
export interface PaperAssets {
  paper_id: string
  title: string
  url: string
  year: number | null
  blocks: {
    paper_profile?: PaperProfileBlock
    background?: AssetBlock
    objective?: ObjectiveBlock
    method?: MethodBlock
    data?: DataBlock
    experiment_or_argumentation?: ExperimentBlock
    experiment?: AssetBlock
    metrics?: MetricsBlock
    results?: ResultsBlock
    evidence_chain?: EvidenceChainBlock
    figures_tables_appendix?: AssetBlock
    limitations?: LimitationsBlock
    critical_analysis?: CriticalAnalysisBlock
    summary?: SummaryBlock
  }
}

export interface DatesResponse {
  dates: string[]
}

export interface PapersResponse {
  date: string
  count: number
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: import('./auth').UserTier | 'anonymous'
}

export interface PaperDetailResponse {
  summary: PaperSummary
  paper_assets: PaperAssets | null
  date: string
  images: string[]
  arxiv_url: string
  pdf_url: string
}

export interface DigestResponse {
  date: string
  total_papers: number
  large_institution_count: number
  avg_relevance_score: number | null
  institution_distribution: { name: string; count: number }[]
  tier_distribution?: { tier: number; count: number }[]
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: import('./auth').UserTier | 'anonymous'
}

export interface PipelineStep {
  step: string
  completed: boolean
}

export interface PipelineStatusResponse {
  date: string
  steps: PipelineStep[]
}
