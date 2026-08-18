# 推荐卡片用户可见精简终稿：详细 A/B 实验

- 运行时间（UTC）：2026-08-18T06:55:32.327070+00:00
- 生成模型：`deepseek-v4-flash`；盲评模型：`deepseek-v4-pro`。
- 评分对象是完整生产链路最终落盘、用户实际会看到的文本；包含整卡重试、首行处理、结构检查及分段兜底。
- 原始 MinerU 全文和完整候选输出只保存在仓库外；本报告仅包含哈希、分数和盲评结论。
- 原2篇隐藏集已经在前一实验打开，本轮降级为 post-hoc；本轮结果不能直接替换线上默认。

## 冻结规则

单候选仍按八字段0–100分评审，并叠加程序硬校验。类型2挑战者必须同时满足：均分至少提高2分、最终硬校验100%、事实性下降不超过1分、客观事实护栏全净、成对盲评至少半数论文判B胜、成对事实性不劣、零新增不支持内容、零实质信息损失、任一字段均分下降不超过3分。规则在本轮新候选输出生成前冻结。

## 类型1：不做精简 vs 当前线上精简

| 数据 | 原稿分 | 当前精简分 | 变化 | 硬校验 | B胜/平/负 |
| --- | --- | --- | --- | --- | --- |
| dev | 69.0 | 69.0 | +0.00 | 0%→0% | 0/2/1 |
| post-hoc | 69.0 | 69.0 | +0.00 | 0%→0% | 0/0/2 |

## 类型2：当前基线 vs 多轮提示词

| 版本 | 开发分 | 开发硬校验 | 开发事实性 | 平均模型调用 | 整卡兜底率 | post-hoc分 | post-hoc硬校验 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| raw_no_refinement | 69.0 | 0% | 96.55 | 0.0 | 0% | 69.0 | 0% |
| r1_field_limits | 69.0 | 0% | 96.67 | 5.67 | 100% | 69.0 | 0% |
| r4_safe_budget_template | 77.73 | 33% | 96.67 | 3.0 | 33% | 79.65 | 50% |
| r5_atomic_safe_budget | 77.03 | 33% | 96.07 | 3.0 | 33% | 82.75 | 50% |
| r6_evidence_safe_budget | 77.56 | 33% | 96.43 | 3.0 | 33% | 69.0 | 0% |
| r8_atomic_evidence_budget | 78.56 | 33% | 96.67 | 3.0 | 33% | 80.19 | 50% |
| r9_anchor_first_microcopy | 77.7 | 33% | 96.55 | 3.0 | 33% | 92.0 | 100% |
| r10_r1_aligned_fallback | 77.31 | 33% | 96.9 | 6.33 | 100% | 78.83 | 50% |
| r11_r4_aligned_fallback | 85.01 | 67% | 96.9 | 3.33 | 33% | 81.91 | 50% |
| r12_r8_aligned_fallback | 84.71 | 67% | 96.9 | 3.33 | 33% | 69.0 | 0% |
| r13_r4_contract_flow | 92.77 | 100% | 95.95 | 4.67 | 33% | 92.03 | 100% |
| r14_r4_evidence_budget | 86.13 | 67% | 96.9 | 3.0 | 33% | 80.69 | 50% |
| r15_r4_robust_evidence | 86.13 | 67% | 96.9 | 3.0 | 33% | 80.69 | 50% |
| r16_r4_selective_contract | 86.13 | 67% | 96.9 | 3.0 | 33% | 80.69 | 50% |
| r17_r4_reliable_selective | 86.13 | 67% | 96.9 | 3.0 | 33% | 93.41 | 100% |

### 开发集逐轮结果

| 轮 | A基线 | B挑战 | A分 | B分 | 差值 | 硬校验 | 盲评B胜/平/负 | 事实差 | 最差字段 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | r1_field_limits | r4_safe_budget_template | 69.0 | 77.73 | +8.73 | 0%→33% | 0/1/2 | +0.00 | 重点思路 -1.60 | 保留基线 |
| 2 | r1_field_limits | r5_atomic_safe_budget | 69.0 | 77.03 | +8.03 | 0%→33% | 0/1/2 | -0.60 | 重点思路 -2.66 | 保留基线 |
| 3 | r1_field_limits | r6_evidence_safe_budget | 69.0 | 77.56 | +8.56 | 0%→33% | 0/1/2 | -0.24 | 重点思路 -1.60 | 保留基线 |
| 4 | r1_field_limits | r8_atomic_evidence_budget | 69.0 | 78.56 | +9.56 | 0%→33% | 0/1/2 | +0.00 | 重点思路 -1.06 | 保留基线 |
| 5 | r1_field_limits | r9_anchor_first_microcopy | 69.0 | 77.7 | +8.70 | 0%→33% | 0/1/2 | -0.12 | 重点思路 +0.00 | 保留基线 |
| 6 | r1_field_limits | r10_r1_aligned_fallback | 69.0 | 77.31 | +8.31 | 0%→33% | 1/0/2 | +0.23 | 分析总结 -1.34 | 保留基线 |
| 7 | r1_field_limits | r11_r4_aligned_fallback | 69.0 | 85.01 | +16.01 | 0%→67% | 0/0/3 | +0.23 | 研究问题 -0.53 | 保留基线 |
| 8 | r1_field_limits | r12_r8_aligned_fallback | 69.0 | 84.71 | +15.71 | 0%→67% | 0/0/3 | +0.23 | 研究问题 -1.07 | 保留基线 |
| 9 | r1_field_limits | r13_r4_contract_flow | 69.0 | 92.77 | +23.77 | 0%→100% | 0/0/3 | -0.72 | 重点思路 -2.93 | 保留基线 |
| 10 | r1_field_limits | r14_r4_evidence_budget | 69.0 | 86.13 | +17.13 | 0%→67% | 1/0/2 | +0.23 | 研究问题 +1.07 | 保留基线 |
| 11 | r1_field_limits | r15_r4_robust_evidence | 69.0 | 86.13 | +17.13 | 0%→67% | 1/0/2 | +0.23 | 研究问题 +1.07 | 保留基线 |
| 12 | r1_field_limits | r16_r4_selective_contract | 69.0 | 86.13 | +17.13 | 0%→67% | 1/0/2 | +0.23 | 研究问题 +1.07 | 保留基线 |
| 13 | r1_field_limits | r17_r4_reliable_selective | 69.0 | 86.13 | +17.13 | 0%→67% | 1/0/2 | +0.23 | 研究问题 +1.07 | 保留基线 |

### 已打开样本的 post-hoc 复核

| 轮 | A基线 | B挑战 | A分 | B分 | 差值 | 硬校验 | 盲评B胜/平/负 | 事实差 | 最差字段 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | r1_field_limits | r4_safe_budget_template | 69.0 | 79.65 | +10.65 | 0%→50% | 0/1/1 | -0.53 | 中文短标题 -5.60 | 保留基线 |
| 2 | r1_field_limits | r5_atomic_safe_budget | 69.0 | 82.75 | +13.75 | 0%→50% | 0/1/1 | -0.17 | 重点思路 +0.00 | 保留基线 |
| 3 | r1_field_limits | r6_evidence_safe_budget | 69.0 | 69.0 | +0.00 | 0%→0% | 0/2/0 | -1.07 | 重点思路 -1.59 | 保留基线 |
| 4 | r1_field_limits | r8_atomic_evidence_budget | 69.0 | 80.19 | +11.19 | 0%→50% | 0/1/1 | -1.78 | 重点思路 -3.59 | 保留基线 |
| 5 | r1_field_limits | r9_anchor_first_microcopy | 69.0 | 92.0 | +23.00 | 0%→100% | 0/0/2 | -1.42 | 中文短标题 -4.80 | 保留基线 |
| 6 | r1_field_limits | r10_r1_aligned_fallback | 69.0 | 78.83 | +9.83 | 0%→50% | 0/0/2 | -8.92 | 个人观点 -48.66 | 保留基线 |
| 7 | r1_field_limits | r11_r4_aligned_fallback | 69.0 | 81.91 | +12.91 | 0%→50% | 0/0/2 | -0.17 | 重点思路 -0.79 | 保留基线 |
| 8 | r1_field_limits | r12_r8_aligned_fallback | 69.0 | 69.0 | +0.00 | 0%→0% | 0/0/2 | -2.32 | 分析总结 -5.28 | 保留基线 |
| 9 | r1_field_limits | r13_r4_contract_flow | 69.0 | 92.03 | +23.03 | 0%→100% | 0/0/2 | -1.78 | 中文短标题 -4.40 | 保留基线 |
| 10 | r1_field_limits | r14_r4_evidence_budget | 69.0 | 80.69 | +11.69 | 0%→50% | 0/0/2 | -1.60 | 研究问题 -2.40 | 保留基线 |
| 11 | r1_field_limits | r15_r4_robust_evidence | 69.0 | 80.69 | +11.69 | 0%→50% | 0/0/2 | -1.60 | 研究问题 -2.40 | 保留基线 |
| 12 | r1_field_limits | r16_r4_selective_contract | 69.0 | 80.69 | +11.69 | 0%→50% | 0/0/2 | -1.60 | 研究问题 -2.40 | 保留基线 |
| 13 | r1_field_limits | r17_r4_reliable_selective | 69.0 | 93.41 | +24.41 | 0%→100% | 0/0/2 | -1.60 | 研究问题 -2.40 | 保留基线 |

## 第二阶段：相同整卡结果下的精简后处理 A/B

为排除模型重复生成造成的随机波动，每篇论文、每个整卡提示词只生成一次中间卡片；旧后处理与新后处理逐字共享该冻结输入。以下输入同一性检查是实验有效性的前置条件。

| 数据 | A旧后处理 | B新后处理 | 相同输入 | 检查 |
| --- | --- | --- | --- | --- |
| dev | r1_field_limits | r10_r1_aligned_fallback | 3/3 | 通过 |
| dev | r4_safe_budget_template | r11_r4_aligned_fallback | 3/3 | 通过 |
| dev | r8_atomic_evidence_budget | r12_r8_aligned_fallback | 3/3 | 通过 |
| dev | r11_r4_aligned_fallback | r13_r4_contract_flow | 3/3 | 通过 |
| dev | r13_r4_contract_flow | r14_r4_evidence_budget | 3/3 | 通过 |
| dev | r14_r4_evidence_budget | r15_r4_robust_evidence | 3/3 | 通过 |
| dev | r13_r4_contract_flow | r15_r4_robust_evidence | 3/3 | 通过 |
| dev | r13_r4_contract_flow | r16_r4_selective_contract | 3/3 | 通过 |
| dev | r15_r4_robust_evidence | r16_r4_selective_contract | 3/3 | 通过 |
| dev | r13_r4_contract_flow | r17_r4_reliable_selective | 3/3 | 通过 |
| dev | r16_r4_selective_contract | r17_r4_reliable_selective | 3/3 | 通过 |
| post-hoc | r1_field_limits | r10_r1_aligned_fallback | 2/2 | 通过 |
| post-hoc | r4_safe_budget_template | r11_r4_aligned_fallback | 2/2 | 通过 |
| post-hoc | r8_atomic_evidence_budget | r12_r8_aligned_fallback | 2/2 | 通过 |
| post-hoc | r11_r4_aligned_fallback | r13_r4_contract_flow | 2/2 | 通过 |
| post-hoc | r13_r4_contract_flow | r14_r4_evidence_budget | 2/2 | 通过 |
| post-hoc | r14_r4_evidence_budget | r15_r4_robust_evidence | 2/2 | 通过 |
| post-hoc | r13_r4_contract_flow | r15_r4_robust_evidence | 2/2 | 通过 |
| post-hoc | r13_r4_contract_flow | r16_r4_selective_contract | 2/2 | 通过 |
| post-hoc | r15_r4_robust_evidence | r16_r4_selective_contract | 2/2 | 通过 |
| post-hoc | r13_r4_contract_flow | r17_r4_reliable_selective | 2/2 | 通过 |
| post-hoc | r16_r4_selective_contract | r17_r4_reliable_selective | 2/2 | 通过 |

### 开发集配对结果

| 轮 | A基线 | B挑战 | A分 | B分 | 差值 | 硬校验 | 盲评B胜/平/负 | 事实差 | 最差字段 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | r1_field_limits | r10_r1_aligned_fallback | 69.0 | 77.31 | +8.31 | 0%→33% | 1/0/2 | +0.23 | 分析总结 -1.34 | 保留基线 |
| 2 | r4_safe_budget_template | r11_r4_aligned_fallback | 77.73 | 85.01 | +7.28 | 33%→67% | 2/0/1 | +0.23 | 推荐理由 +0.00 | 保留基线 |
| 3 | r8_atomic_evidence_budget | r12_r8_aligned_fallback | 78.56 | 84.71 | +6.15 | 33%→67% | 0/0/3 | +0.23 | 研究问题 -0.54 | 保留基线 |
| 4 | r11_r4_aligned_fallback | r13_r4_contract_flow | 85.01 | 92.77 | +7.76 | 67%→100% | 0/2/1 | -0.95 | 重点思路 -2.40 | 保留基线 |
| 5 | r13_r4_contract_flow | r14_r4_evidence_budget | 92.77 | 86.13 | -6.64 | 100%→67% | 3/0/0 | +0.95 | 一句话记忆 +0.88 | 保留基线 |
| 6 | r14_r4_evidence_budget | r15_r4_robust_evidence | 86.13 | 86.13 | +0.00 | 67%→67% | 0/3/0 | +0.00 | 中文短标题 +0.00 | 保留基线 |
| 7 | r13_r4_contract_flow | r15_r4_robust_evidence | 92.77 | 86.13 | -6.64 | 100%→67% | 3/0/0 | +0.95 | 一句话记忆 +0.88 | 保留基线 |
| 8 | r13_r4_contract_flow | r16_r4_selective_contract | 92.77 | 86.13 | -6.64 | 100%→67% | 3/0/0 | +0.95 | 一句话记忆 +0.88 | 保留基线 |
| 9 | r15_r4_robust_evidence | r16_r4_selective_contract | 86.13 | 86.13 | +0.00 | 67%→67% | 0/3/0 | +0.00 | 中文短标题 +0.00 | 保留基线 |
| 10 | r13_r4_contract_flow | r17_r4_reliable_selective | 92.77 | 86.13 | -6.64 | 100%→67% | 3/0/0 | +0.95 | 一句话记忆 +0.88 | 保留基线 |
| 11 | r16_r4_selective_contract | r17_r4_reliable_selective | 86.13 | 86.13 | +0.00 | 67%→67% | 0/3/0 | +0.00 | 中文短标题 +0.00 | 保留基线 |

### 已打开样本的 post-hoc 配对复核

| 轮 | A基线 | B挑战 | A分 | B分 | 差值 | 硬校验 | 盲评B胜/平/负 | 事实差 | 最差字段 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | r1_field_limits | r10_r1_aligned_fallback | 69.0 | 78.83 | +9.83 | 0%→50% | 0/0/2 | -8.92 | 个人观点 -48.66 | 保留基线 |
| 2 | r4_safe_budget_template | r11_r4_aligned_fallback | 79.65 | 81.91 | +2.26 | 50%→50% | 1/0/1 | +0.36 | 分析总结 +1.20 | 保留基线 |
| 3 | r8_atomic_evidence_budget | r12_r8_aligned_fallback | 80.19 | 69.0 | -11.19 | 50%→0% | 0/0/2 | -0.54 | 分析总结 -5.10 | 保留基线 |
| 4 | r11_r4_aligned_fallback | r13_r4_contract_flow | 81.91 | 92.03 | +10.12 | 50%→100% | 0/1/1 | -1.61 | 中文短标题 -6.00 | 保留基线 |
| 5 | r13_r4_contract_flow | r14_r4_evidence_budget | 92.03 | 80.69 | -11.34 | 100%→50% | 2/0/0 | +0.18 | 一句话记忆 -0.98 | 保留基线 |
| 6 | r14_r4_evidence_budget | r15_r4_robust_evidence | 80.69 | 80.69 | +0.00 | 50%→50% | 0/2/0 | +0.00 | 中文短标题 +0.00 | 保留基线 |
| 7 | r13_r4_contract_flow | r15_r4_robust_evidence | 92.03 | 80.69 | -11.34 | 100%→50% | 2/0/0 | +0.18 | 一句话记忆 -0.98 | 保留基线 |
| 8 | r13_r4_contract_flow | r16_r4_selective_contract | 92.03 | 80.69 | -11.34 | 100%→50% | 2/0/0 | +0.18 | 一句话记忆 -0.98 | 保留基线 |
| 9 | r15_r4_robust_evidence | r16_r4_selective_contract | 80.69 | 80.69 | +0.00 | 50%→50% | 0/2/0 | +0.00 | 中文短标题 +0.00 | 保留基线 |
| 10 | r13_r4_contract_flow | r17_r4_reliable_selective | 92.03 | 93.41 | +1.38 | 100%→100% | 2/0/0 | +0.18 | 研究问题 +0.80 | 保留基线 |
| 11 | r16_r4_selective_contract | r17_r4_reliable_selective | 80.69 | 93.41 | +12.72 | 50%→100% | 0/1/1 | +0.00 | 中文短标题 +0.00 | 保留基线 |

## 链路审计发现

当前整卡合同要求“笔记标题”和八个用户字段，但旧后处理仍按“机构：摘要首行”的历史结构判断与压缩；其分段预算也宽于整卡字段预算，一句话记忆原先还不会进入分段压缩。因此，单独优化整卡提示词不能保证最终展示合格，首行、结构、各字段和记忆句必须作为同一个展示合同共同评测。

## 逐论文最终输出得分

| 数据 | 论文 | 版本 | 0–100分 | 硬校验 | 模型调用 | 整卡失败兜底 | 终段本地兜底 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev | 2608.06218 | raw_no_refinement | 69.0 | 未通过 | 0 | 否 | 否 |
| dev | 2608.06301 | raw_no_refinement | 69.0 | 未通过 | 0 | 否 | 否 |
| dev | 2608.09772 | raw_no_refinement | 69.0 | 未通过 | 0 | 否 | 否 |
| dev | 2608.06218 | r1_field_limits | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.06301 | r1_field_limits | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r1_field_limits | 69.0 | 未通过 | 5 | 是 | 否 |
| dev | 2608.06218 | r4_safe_budget_template | 69.0 | 未通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r4_safe_budget_template | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r4_safe_budget_template | 95.2 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r5_atomic_safe_budget | 69.0 | 未通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r5_atomic_safe_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r5_atomic_safe_budget | 93.09 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r6_evidence_safe_budget | 69.0 | 未通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r6_evidence_safe_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r6_evidence_safe_budget | 94.69 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r8_atomic_evidence_budget | 69.0 | 未通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r8_atomic_evidence_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r8_atomic_evidence_budget | 97.68 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r9_anchor_first_microcopy | 69.0 | 未通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r9_anchor_first_microcopy | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r9_anchor_first_microcopy | 95.1 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r10_r1_aligned_fallback | 93.92 | 通过 | 7 | 是 | 否 |
| dev | 2608.06301 | r10_r1_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r10_r1_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.06218 | r11_r4_aligned_fallback | 91.66 | 通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r11_r4_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r11_r4_aligned_fallback | 94.38 | 通过 | 2 | 否 | 否 |
| dev | 2608.06218 | r12_r8_aligned_fallback | 91.92 | 通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r12_r8_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| dev | 2608.09772 | r12_r8_aligned_fallback | 93.2 | 通过 | 2 | 否 | 否 |
| dev | 2608.06218 | r13_r4_contract_flow | 91.66 | 通过 | 2 | 否 | 否 |
| dev | 2608.06301 | r13_r4_contract_flow | 92.27 | 通过 | 10 | 是 | 否 |
| dev | 2608.09772 | r13_r4_contract_flow | 94.38 | 通过 | 2 | 否 | 否 |
| dev | 2608.06218 | r14_r4_evidence_budget | 94.19 | 通过 | 1 | 否 | 否 |
| dev | 2608.06301 | r14_r4_evidence_budget | 69.0 | 未通过 | 7 | 是 | 是 |
| dev | 2608.09772 | r14_r4_evidence_budget | 95.2 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r15_r4_robust_evidence | 94.19 | 通过 | 1 | 否 | 否 |
| dev | 2608.06301 | r15_r4_robust_evidence | 69.0 | 未通过 | 7 | 是 | 是 |
| dev | 2608.09772 | r15_r4_robust_evidence | 95.2 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r16_r4_selective_contract | 94.19 | 通过 | 1 | 否 | 否 |
| dev | 2608.06301 | r16_r4_selective_contract | 69.0 | 未通过 | 7 | 是 | 是 |
| dev | 2608.09772 | r16_r4_selective_contract | 95.2 | 通过 | 1 | 否 | 否 |
| dev | 2608.06218 | r17_r4_reliable_selective | 94.19 | 通过 | 1 | 否 | 否 |
| dev | 2608.06301 | r17_r4_reliable_selective | 69.0 | 未通过 | 7 | 是 | 是 |
| dev | 2608.09772 | r17_r4_reliable_selective | 95.2 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.05069 | raw_no_refinement | 69.0 | 未通过 | 0 | 否 | 否 |
| posthoc | 2608.09880 | raw_no_refinement | 69.0 | 未通过 | 0 | 否 | 否 |
| posthoc | 2608.05069 | r1_field_limits | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.09880 | r1_field_limits | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r4_safe_budget_template | 90.3 | 通过 | 2 | 否 | 否 |
| posthoc | 2608.09880 | r4_safe_budget_template | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r5_atomic_safe_budget | 96.5 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.09880 | r5_atomic_safe_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r6_evidence_safe_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.09880 | r6_evidence_safe_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r8_atomic_evidence_budget | 91.38 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.09880 | r8_atomic_evidence_budget | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r9_anchor_first_microcopy | 89.17 | 通过 | 2 | 否 | 否 |
| posthoc | 2608.09880 | r9_anchor_first_microcopy | 94.82 | 通过 | 4 | 否 | 否 |
| posthoc | 2608.05069 | r10_r1_aligned_fallback | 88.66 | 通过 | 10 | 是 | 否 |
| posthoc | 2608.09880 | r10_r1_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r11_r4_aligned_fallback | 94.82 | 通过 | 3 | 否 | 否 |
| posthoc | 2608.09880 | r11_r4_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r12_r8_aligned_fallback | 69.0 | 未通过 | 4 | 否 | 否 |
| posthoc | 2608.09880 | r12_r8_aligned_fallback | 69.0 | 未通过 | 6 | 是 | 否 |
| posthoc | 2608.05069 | r13_r4_contract_flow | 91.04 | 通过 | 3 | 否 | 否 |
| posthoc | 2608.09880 | r13_r4_contract_flow | 93.01 | 通过 | 9 | 是 | 否 |
| posthoc | 2608.05069 | r14_r4_evidence_budget | 92.37 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.09880 | r14_r4_evidence_budget | 69.0 | 未通过 | 6 | 是 | 是 |
| posthoc | 2608.05069 | r15_r4_robust_evidence | 92.37 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.09880 | r15_r4_robust_evidence | 69.0 | 未通过 | 6 | 是 | 是 |
| posthoc | 2608.05069 | r16_r4_selective_contract | 92.37 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.09880 | r16_r4_selective_contract | 69.0 | 未通过 | 6 | 是 | 是 |
| posthoc | 2608.05069 | r17_r4_reliable_selective | 92.37 | 通过 | 1 | 否 | 否 |
| posthoc | 2608.09880 | r17_r4_reliable_selective | 94.45 | 通过 | 7 | 是 | 否 |

## 结论

严格晋级冠军（未过门槛即保留基线）：`r1_field_limits`；最佳合同合规候选：`r13_r4_contract_flow`；线上默认仍为 `r1_field_limits`。

最佳合同合规候选为r13_r4_contract_flow：开发集92.77分、硬校验100%，post-hoc为92.03分、硬校验100%；但相对r11的盲评为0胜/2平/1负，并有1篇被判实质信息损失。它未通过冻结的成对质量门槛，且旧留出集已经打开，不能提供新的泛化证据。因此不得替换管理员后台或服务器默认；下一步应先实现单字段失败隔离，再用新增且冻结的隐藏集复核。

## 下一步

1. 把分段模型失败从“整卡回退”改为“仅该字段回退”，保留其他已经成功且通过校验的字段；对每个字段输出分别做结构、长度和数字追溯校验。
2. 以 `r13_r4_contract_flow` 为开发基线，验证单字段失败隔离是否能在不增加信息损失的前提下维持100%最终硬校验。
3. 冻结新的未见论文集后再做盲评；在新隐藏集通过全部门槛前，不改服务器管理员默认提示词。

## 解释限制

只有5篇已授权公开论文，且其中2篇已被查看，样本量不足以估计跨学科稳定性。自动生成与盲评来自同一模型家族，可能存在共同风格偏好；成对盲评、硬校验和事实护栏只能降低、不能消除该风险。
