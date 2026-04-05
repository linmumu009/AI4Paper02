# Grounded Token Initialization for New Vocabulary in LMs for Generative Recommendation

Daiwei Chen1,2∗ Zhoutong $\mathbf { F } \mathbf { u } ^ { 2 }$ , Chengming Jiang2, Haichao Zhang3, Ran Zhou2 Tan Wang2, Chunnan $\mathbf { Y a o } ^ { 2 }$ , Guoyao $\mathbf { L i } ^ { 2 }$ , Rui Cai4, Yihan $\mathbf { C a o } ^ { 2 }$ , Ruijie Jiang2, Fedor Borisyuk2, Jianqiang Shen2, Jingwei $\mathbf { { W } _ { u } } ^ { 2 }$ , Ramya Korlakai Vinayak1

1University of Wisconsin-Madison 2LinkedIn Corporation 3Northeastern University 4University of California, Davis

# Abstract

Language models (LMs) are increasingly extended with new learnable vocabulary tokens for domain-specific tasks, such as Semantic-ID tokens in generative recommendation. The standard practice initializes these new tokens as the mean of existing vocabulary embeddings, then relies on supervised fine-tuning to learn their representations. We present a systematic analysis of this strategy: through spectral and geometric diagnostics, we show that mean initialization collapses all new tokens into a degenerate subspace, erasing inter-token distinctions that subsequent fine-tuning struggles to fully recover. These findings suggest that token initialization is a key bottleneck when extending LMs with new vocabularies. Motivated by this diagnosis, we propose the Grounded Token Initialization Hypothesis: linguistically grounding novel tokens in the pretrained embedding space before fine-tuning better enables the model to leverage its general-purpose knowledge for novel-token domains. We operationalize this hypothesis as GTI (Grounded Token Initialization), a lightweight grounding stage that, prior to fine-tuning, maps new tokens to distinct, semantically meaningful locations in the pretrained embedding space using only paired linguistic supervision. Despite its simplicity, GTI outperforms both mean initialization and existing auxiliary-task adaptation methods in the majority of evaluation settings across multiple generative recommendation benchmarks, including industry-scale and public datasets. Further analyses show that grounded embeddings produce richer inter-token structure that persists through fine-tuning, corroborating the hypothesis that initialization quality is a key bottleneck in vocabulary extension.

# 1 Introduction

Pretrained language models (LMs) are increasingly adapted to specialized domains by extending their vocabulary with new learnable tokens. A prominent example is generative retrieval, where items (Rajput et al., 2023; Deldjoo et al., 2024) or documents (Tay et al., 2022) are assigned discrete semantic codes and generated autoregressively by the LM; similar challenges arise whenever domain-specific symbols must be integrated into a pretrained vocabulary. These systems introduce thousands of new tokens into the model’s vocabulary, and a fundamental challenge is how to incorporate them into the pretrained embedding space so that the LM can transfer its general-purpose knowledge to the novel-token domain.

The prevailing practice initializes new token embeddings as the mean of the existing vocabulary embeddings (Hewitt, 2021). This heuristic is widely adopted because it is simple, places new tokens on the pretrained embedding manifold, and provides a tighter KL-divergence upper bound on output probabilities. However, it collapses all new tokens into a single point in embedding space, erasing inter-token distinctions and stripping domain-level semantics. An existing alternative (Zheng et al., 2024) employs auxiliary-task

![](images/5c4b60d75c1e59d2e16613bb9ce05bd9d9beb9fec7312a09b8ec790d1a004460.jpg)  
Figure 1: Overview of the GTI grounding stage. The LM backbone and original vocabulary embeddings are frozen (snowflake); only the newly introduced Semantic-ID (SID) token embeddings $( | \mathcal { V } _ { \mathrm { S I D } } | \times D$ parameters, fire) are trained. Paired prompts map between natural language descriptions and SID tokens in both directions, grounding the new tokens in the pretrained embedding space. This stage is inserted before standard end-to-end fine-tuning (see Section 3).

adaptation of the full LM to induce linguistic signals for new tokens, but the multi-task training introduces an objective mismatch: the auxiliary losses are not aligned with the target downstream task, resulting in limited and inconsistent gains.

In this paper, we identify token-embedding misalignment as a fundamental limitation when extending pretrained LMs with new vocabulary, and propose the Grounded Token Initialization Hypothesis: linguistically grounding novel tokens in an LM’s pretrained embedding space, before fine-tuning, better enables the model to leverage its general-purpose knowledge for novel-token domains. The intuition is that pretrained LM embeddings encode rich linguistic structure, semantically related tokens occupy nearby regions (Levy & Goldberg, 2014), and the model’s attention and feed-forward layers have learned to exploit this geometry (Gao et al., 2019). If new tokens are placed meaningfully within this structure, the LM can immediately leverage its existing representations to process them in context, rather than relying on fine-tuning alone to recover from a degenerate starting point. This motivates framing vocabulary extension as a token-grounding problem: new token embeddings should be grounded in linguistically meaningful representations while remaining coherent with the pretrained LM’s embedding geometry.

Building on this hypothesis, we introduce GTI, a simple and effective grounded token initialization method. Before downstream fine-tuning, GTI freezes the LM backbone and grounds newly introduced token embeddings using paired supervision between natural language descriptions and the corresponding new tokens (Figure 1). This grounding stage resolves the mismatch between well-trained vocabulary embeddings and newly initialized tokens, providing the LM with a semantically structured starting point for subsequent end-to-end fine-tuning of the full model for target downstream tasks.

We validate GTI on Generative Recommendation (GR) (Rajput et al., 2023; Zhai et al., 2024), a challenging and practically important application of vocabulary extension. GRs have attracted growing attention in both academia and industry (Ding et al., 2026; Han et al., 2025; Chen et al., 2025a; Deng et al., 2025), as they dramatically simplify retrieval by autoregressively generating item identifiers token-by-token from user interaction histories, replacing the expensive user–item inner products required by traditional dense-embedding methods (Koren et al., 2009; He et al., 2017; 2020; Wang et al., 2019). GRs can further exploit scaling-law behavior as model size and data increase (Han et al., 2025), offering a clear path to continued improvement. The GR setting is a particularly demanding testbed for grounded token initialization: large sets of new learnable Semantic-ID (SID) tokens must be incorporated into pretrained LMs, each encoding fine-grained item-level semantics and hierarchical codebook structure that should be properly grounded in the LM’s embedding space to support effective retrieval.

# Contributions.

1. Diagnosis. Through spectral and geometric analysis, we characterize the tokenembedding misalignment caused by mean initialization: all new learnable tokens collapse into a degenerate, low-rank subspace that does not fully recover under subsequent fine-tuning. This motivates the Grounded Token Initialization Hypothesis: linguistically grounding new tokens before fine-tuning better enables the LM to leverage its pretrained knowledge for the new domain.   
2. Methodology. We introduce GTI, a simple and effective grounding stage that freezes the LM backbone and learns new token embeddings via paired linguistic supervision before standard fine-tuning, providing a semantically structured starting point for downstream adaptation.   
3. Finding. On generative recommendation benchmarks, spanning industry-scale and public datasets, GTI consistently outperforms both direct supervised fine-tuning and LC-Rec (Zheng et al., 2024), an existing approach that jointly adapts the full model via auxiliary tasks. These results suggest that token initialization is a key bottleneck in vocabulary extension.

# 2 Token-Embedding Misalignment

We formalize the vocabulary extension problem in the context of generative retrieval, our primary application domain, and then use spectral and geometric diagnostics to characterize a systematic token-embedding misalignment that arises from standard initialization practices when new tokens are added to a pretrained language model.

Generative Retrieval. We adopt the framework of Rajput et al. (2023). Each item $I _ { i } \in \mathcal { I }$ has content features (title, description, etc.) that a pretrained text encoder maps to a semantic embedding $\mathbf { z } _ { i } \in \mathbb { R } ^ { d }$ . An RQ-VAE (Lee et al., 2022) with $L$ codebook levels of K entries each discretizes $\mathbf { z } _ { i }$ into a Semantic ID $\left( c _ { 1 } , \dots , c _ { L } \right)$ , $\dot { c } _ { l } \in \{ 1 , \dots , K \} ,$ , via recursive residual quantization:

$$
\mathbf {r} _ {1} := \mathbf {z} _ {i}; \qquad c _ {l} = \arg \min  _ {k} \left\| \mathbf {r} _ {l} - \mathbf {q} _ {k} ^ {(l)} \right\| _ {2}, \quad \mathbf {r} _ {l + 1} := \mathbf {r} _ {l} - \mathbf {q} _ {c _ {l}} ^ {(l)}, \quad l = 1, \ldots , L,
$$

where $\{ \mathbf { q } _ { k } ^ { ( l ) } \} _ { k = 1 } ^ { K } \subset \mathbb { R } ^ { d }$ is the l-l codebook. $K \times L$ SID codes1 re appended to $\mathcal { V } _ { \mathrm { t e x t } }$ $\gamma _ { \mathrm { S I D } }$ $\mathbf { x }$ interaction history (retrieval) or a natural language query (search), the LM generates the target Semantic ID autoregressively:

$$
P _ {\theta} \left(c _ {1}, \dots , c _ {L} \mid \mathbf {x}\right) = \prod_ {t = 1} ^ {L} P _ {\theta} \left(c _ {t} \mid c _ {<   t}, \mathbf {x}\right).
$$

Mean-of-Vocabulary Initialization. Standard practice initializes all novel token embeddings to the mean of the existing vocabulary embeddings (Hewitt, 2021):

$$
\mathbf {e} _ {c} := \frac {1}{| \mathcal {V} _ {\text {t e x t}} |} \sum_ {v \in \mathcal {V} _ {\text {t e x t}}} \mathbf {e} _ {v}, \quad \forall c \in \mathcal {V} _ {\text {S I D}}, \tag {1}
$$

where $\mathbf { e } _ { v }$ denotes the input embedding of token v.

Diagnosing the misalignment. Under mean-of-vocabulary initialization (Eq. 1), every new token receives an identical embedding, 1) collapsing all inter-token distinctions and 2) discarding the semantic structure each token should encode (Fig. 2, left). This heuristic is nonetheless widely adopted (Wolf et al., 2020) because it places new tokens on the pretrained manifold and yields a tighter KL-divergence upper bound on output probabilities compared with random initialization (Hewitt, 2021). Random initialization, conversely,

![](images/0d66c45383fe3307f7295516c16607f90ae99a84eed42d64c59329193b1e2266.jpg)  
Figure 2: Token-embedding collapse under mean initialization and the effect of grounding. (a) Left: Mean initialization maps all SID tokens (white triangles) to a single point, collapsing inter-token distinctions. Top-right: GTI grounds SID tokens (colored triangles) into distinct regions by training only the $| \mathcal { V } _ { \mathrm { S I D } } | \times d$ embedding parameters while freezing the backbone. Bottom-right: Fine-tuning without grounding does not fully resolve the collapse (see Figure 7). (b)&(c) GTI initialization yields higher effective rank and preserves blockwise hierarchical structure among SID tokens after downstream task supervised finetuning.

assigns distinct vectors to each token but places them without coherent relation to the pretrained manifold, providing no linguistic prior for the model to build on. Pairwise cosine similarities among token embeddings (Fig. 5) confirm that mean initialization produces a near-uniform similarity block across all SID tokens, while random initialization yields unstructured noise.

We examine whether supervised fine-tuning recovers the structure lost under mean initialization. The pairwise similarity among SID embeddings (Fig.2 (c) and Fig.6 Left&Mid) and the singular-value decomposition of the SID embedding matrix $E _ { \mathrm { S I D } } \in \bar { \mathbb { R } } ^ { | \mathcal { V } _ { \mathrm { S I D } } | \times d }$ after supervised fine-tuning from the mean-initialized state (Fig.2 (b) and Fig.7) reveals rapid spectral decay and low effective rank, confirming that supervised fine-tuning alone does not recover the inter-token structure lost at mean or random initialization. Taken together, these analyses show that neither strategy provides a suitable starting point: mean initialization places tokens on the pretrained manifold but erases discrimination, while random initialization preserves discrimination but lacks linguistic grounding.

Grounded Token Initialization (GTI) Hypothesis. These observations motivate our central hypothesis: linguistically grounding novel tokens in an LM’s pretrained embedding space, before downstream fine-tuning, better enables the model to leverage its general-purpose knowledge for novel-token domains. Rather than relying on fine-tuning alone to recover from a degenerate initialization, we propose inserting a simple and efficient grounding stage that learns new token embeddings via linguistic supervision with the backbone frozen, before proceeding to standard end-to-end fine-tuning. We operationalize this hypothesis in Section 3 and verify its effectiveness empirically in Section 4.

# 3 GTI: Grounded Token Initialization Stage

The diagnosis in Section 2 motivates a straightforward modification to the standard training pipeline: before downstream fine-tuning, insert a grounding stage that freezes the LM backbone and only learns new token embeddings via paired linguistic supervision. This design builds on the established principle of training new token embeddings within a frozen LM (Hao et al., 2024; Nguyen et al., 2024). We term the resulting procedure GTI. Despite its simplicity, we show that this additional stage yields consistent improvements

across multiple benchmarks, including both public and industry-scale datasets (Section 4), suggesting that token initialization is a key bottleneck in vocabulary extension.

Algorithm. Let $\nu = \nu _ { \mathrm { t e x t } } \cup \nu _ { \mathrm { n e w } }$ denote the extended vocabulary, where $\mathcal { V } _ { \mathrm { n e w } }$ are the newly added domain tokens. Given a pretrained autoregressive LM with input-embedding matrix $\boldsymbol { E } \in \mathbb { R } ^ { | \nu | \times d } .$ , we partition $E$ into the pretrained rows $E _ { \mathrm { t e x t } }$ and the new rows $E _ { \mathrm { n e w } } \in$ $\mathbb { R } ^ { | \mathcal { V } _ { \mathrm { n e w } } | \times d }$ . Each domain entity is associated with a natural-language description $x _ { i }$ (e.g., title or definition) and a canonical new-token sequence $y _ { i } = ( c _ { i , 1 } , \cdot \cdot \cdot , \overline { { c } } _ { i , L } )$ . We instantiate GTI in the generative recommendation setting, where $\mathcal { V } _ { \mathrm { n e w } } = \mathcal { V } _ { \mathrm { S I D } } , x _ { i }$ is an item title/description, and $y _ { i }$ is the corresponding SID sequence.

We construct a grounding corpus $\mathcal { D } _ { \mathrm { g r o u n d } } = \{ ( x _ { i } , y _ { i } ) \} _ { i = 1 } ^ { n }$ pairing each description with its new token sequence, along with reversed pairs $\left\{ \left( y _ { i } , x _ { i } \right) \right\}$ that require the model to generate descriptions from new tokens2. Using an instruction-style prompt template prompt $( x )$ (Listing as follows), we minimize the negative log-likelihood over $\tilde { E _ { \mathrm { n e w } } }$ :

$$
\min  _ {E _ {\text {n e w}}} \sum_ {(x, y) \in \mathcal {D} _ {\text {g r o u n d}}} \sum_ {t = 1} ^ {| y |} - \log P _ {\theta} \left(y _ {t} \mid y _ {<   t}, \text {p r o m p t} (x)\right) \tag {2}
$$

where $\theta$ denotes all LM parameters. During this stage, all parameters except $E _ { \mathrm { n e w } }$ are held fixed, including $E _ { \mathrm { t e x t } }$ and the LM head, which shares weights with $E$ via the standard tiedembedding parameterization. This weight tying means the grounding stage simultaneously shapes how the model reads and generates new tokens. After grounding, we retain the learned $E _ { \mathrm { n e w } }$ as initialization and proceed with standard supervised fine-tuning of all model parameters $\theta$ . Implementation details are provided in Algorithm 1.

Item Title/Description Semantic IDs (Text→New Vocabulary Tokens)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
What item is called {{title}} and described as {{description}}?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

# 4 Experiments

We evaluate GTI within the highly demanding domain of generative recommendation. This domain serves as an ideal testbed for the initialization bottleneck, as it requires incorporating thousands of new Semantic-ID (SID) tokens into a pretrained language model. To empirically validate whether aligning these tokens with the model’s pre-existing linguistic geometry can prevent semantic collapse, we evaluate across two diverse environments: an industrial-scale candidate retrieval system and the public Vibrent Clothes Rental benchmark.

# 4.1 Setup

Datasets. We evaluate across two distinct scales and domains.

(1) Industrial candidate retrieval.3 This dataset consists of job requirement–candidate pairs from a world-leading recruitment platform. Each pair is categorized into three relevance levels (good, good&maybe, and not match) by an internal LLM evaluator according to how

many job requirements a candidate satisfies. Due to data-sharing constraints, we report only relative performance gains over the SFT baseline for this dataset.

(2) Vibrent Clothes Rental. To validate generalizability, we adapt the public Vibrent Clothes Rental Dataset (Borgersen, 2024) into a generative retrieval task, treating users as queries and clothing items as candidates based on historical rental transactions.

Baselines. To strictly isolate the initialization bottleneck, all methods share an identical Qwen3-0.6B backbone and RQ-VAE tokenization structure, differing only in how they introduce novel tokens.

(1) Vanilla SFT: New SID tokens are mean-initialized (Eq. 1), inducing a semantic collapse. The model relies entirely on downstream fine-tuning to disambiguate tokens from this degenerate starting point.   
(2) LC-Rec (Zheng et al., 2024): A recent multi-task approach that begins from the same collapsed state but attempts to recover semantic structure by applying auxiliary natural language alignment objectives during fine-tuning.   
(3) GTI (Ours): Using the grounding stage described in Section 3, we ground the new SID tokens into distinct, semantically meaningful regions of the frozen LM’s embedding space, providing a structurally rich starting point for the subsequent SFT procedure.

Evaluation Metrics. We measure retrieval accuracy using Top-K Precision, Recall, and NDCG. For the industrial dataset, we sample 200 jobs as evaluation queries (retrieving 200 candidates each). To comply with data-sharing constraints, we isolate the direct performance uplift of our grounding stage by reporting results strictly as a relative percentage gain over the standard SFT baseline, formulated as $\left( M _ { \mathrm { m e t h o d } } - \dot { M } _ { \mathrm { B a s e l i n e } } \right) /  { M _ { \mathrm { B a s e l i n e } } }$ . For the public Vibrent dataset, we adopt the standard leave-one-out sequence splitting strategy (Kang & McAuley, 2018; Geng et al., 2023).

Implementation Details. Across both datasets, we employ Qwen3-0.6B as the backbone language model. Semantic IDs are constructed via RQ-VAE, following the formulation in Rajput et al. (2023). For GTI, the grounding stage freezes all parameters except $E _ { \mathrm { n e w } }$ and trains for 8,000 steps with batch size 128; all parameters are then unfrozen for an additional 8,000 steps at the same batch size, followed by the standard SFT procedure used for the baseline. All experiments use four NVIDIA H100 GPUs.

Table 1: Relative Precision@K gain $( \% )$ over SFT baseline on a real-world candidate retrieval dataset. Bold and underline denote the best result.   

<table><tr><td rowspan="2">Methodology</td><td colspan="5">Precision@K (Good Match)</td><td colspan="5">Precision@K (Good &amp; Maybe Match)</td></tr><tr><td>P@5</td><td>P@10</td><td>P@20</td><td>P@50</td><td>P@100</td><td>P@5</td><td>P@10</td><td>P@20</td><td>P@50</td><td>P@100</td></tr><tr><td>MI+Vanilla SFT (Baseline)</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td></tr><tr><td>MI+Multi-task SFT (LC-Rec)</td><td>+6.38%</td><td>+5.20%</td><td>+3.87%</td><td>+3.00%</td><td>+3.47%</td><td>+5.63%</td><td>+5.35%</td><td>+2.98%</td><td>+3.32%</td><td>+3.05%</td></tr><tr><td>GTI+Multi-task SFT (Ours)</td><td>+21.63%</td><td>+13.59%</td><td>+8.16%</td><td>+6.35%</td><td>+4.25%</td><td>+15.83%</td><td>+10.89%</td><td>+5.74%</td><td>+5.87%</td><td>+4.10%</td></tr><tr><td>GTI: extra gain over LC-Rec (Δ)</td><td>+15.25%</td><td>+8.39%</td><td>+4.29%</td><td>+3.35%</td><td>+0.78%</td><td>+10.20%</td><td>+5.54%</td><td>+2.76%</td><td>+2.55%</td><td>+1.05%</td></tr></table>

![](images/9bdd5537dd67ad90b1cd10aab0325c67c519a9bb264ba6eabf47cbe9e7263b04.jpg)

![](images/f43ca15abf89ff01b8281e483e11dbade44f0d81c298102af03efbb2e3ce2240.jpg)

![](images/34230d2ebe269a60b2dc0df0bab4871de596199b613a26c82ed9deea2c1714f7.jpg)  
Figure 3: Relative gain versus candidate pool size. Left/Middle: Relative Precision@K gain under Good Match and Good & Maybe Match; Right: Relative NDCG@K gain (Composite). GTI consistently outperforms both baselines across all pool sizes, with the largest gains at small K. Shaded areas denote variability across runs.

Table 2: Relative NDCG@K (Composite) gain $( \% )$ over SFT baseline on a real-world candidate retrieval dataset. Bold and underline denote the best result.   

<table><tr><td rowspan="2">Methodology</td><td colspan="5">NDCG@K (Composite)</td></tr><tr><td>@5</td><td>@10</td><td>@20</td><td>@50</td><td>@100</td></tr><tr><td>MI+Vanilla SFT (Baseline)</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td></tr><tr><td>MI+Multi-task SFT (LC-Rec)</td><td>+6.94%</td><td>+4.38%</td><td>+1.94%</td><td>+1.95%</td><td>+1.01%</td></tr><tr><td>GTI+Multi-task SFT (Ours)</td><td>+17.88%</td><td>+12.03%</td><td>+6.90%</td><td>+4.99%</td><td>+2.89%</td></tr><tr><td>GTI: extra gain over LC-Rec (Δ)</td><td>+10.94%</td><td>+7.65%</td><td>+4.96%</td><td>+3.04%</td><td>+1.88%</td></tr></table>

Industrial dataset. Candidate-level semantic representations are obtained by fine-tuning Mistral-E5 in a two-tower architecture with recruiter engagement signals, producing 1024- dimensional embeddings. The RQ-VAE uses $L = 3$ codebook levels with $\dot { K } = 8 { , } 1 9 2 \dot { }$ codes per level. The subsequent SFT baseline trains with a batch size of 512 for 1,600 steps.

Public dataset. Item-level semantic representations are derived using the off-the-shelf Qwen3-Embedding-0.6B encoder, yielding 1024-dimensional vectors. The RQ-VAE uses a 3-layer MLP encoder–decoder with ReLU activations, $L = 4$ codebook levels with $K = 2 5 6$ codes per level (32-dimensional codes), and the diversity regularizer of Wang et al. (2024) to encourage balanced codebook utilization. The RQ-VAE is trained for 20K epochs. The SFT baseline trains with batch size 512 for 1,600 steps.

# 4.2 Overall Performance Analysis

Tables 1 & 2 and Figure 3 detail the overall performance on the industrial-scale dataset.

The effectiveness of GTI Initialization. Across all cutoffs, evaluation metrics, and relevance thresholds (Good Match and Good & Maybe Match), GTI outperforms both baselines. Under the strict Good Match criterion, GTI achieves $\mathbf { + 2 1 . 6 3 \% }$ relative gain at $\mathrm { P @ 5 }$ over vanilla SFT, compared to $+ 6 . 3 8 \%$ for LC-Rec, yielding an extra gain $\Delta$ of $1 5 . 2 5 \%$ attributable to the grounding stage. This pattern is consistent across evaluation settings: under Good & Maybe Match, GTI maintains a clear advantage $( + 1 5 . 8 3 \%$ vs. $+ 5 . 6 3 \%$ at $\mathrm { P } \bar { \ @ } 5$ ), and NDCG@5 exhibits the same trend $\mathbf { + 1 7 . 8 8 \% }$ vs. $+ 6 . 9 4 \%$ ). Sweeping the candidate pool size from 5 to 200 (Figure 3) further confirms that the improvement is robust across retrieval scales.

Evidence for the GTI hypothesis. The comparison between LC-Rec and GTI provides a controlled test of our hypothesis, as both methods introduce linguistic supervision for new tokens but differ in when it is applied: LC-Rec incorporates auxiliary language modeling objectives during fine-tuning while retaining mean initialization, whereas GTI addresses the initialization directly through a grounding stage that precedes fine-tuning. The consistent performance gap (extra gain $\Delta$ ) between the two methods, despite sharing the same downstream SFT procedure, suggests that grounding new tokens before fine-tuning provides a more effective starting point than relying on auxiliary objectives alone, consistent with the Grounded Token Initialization hypothesis.

Table 3: Relative Recall@K and NDCG@K $( \% )$ ) over SFT baseline on Vibrent Dataset.   

<table><tr><td rowspan="2">Methodology</td><td colspan="5">Recall@K</td><td colspan="5">NDCG@K</td></tr><tr><td>@5</td><td>@10</td><td>@20</td><td>@50</td><td>@100</td><td>@5</td><td>@10</td><td>@20</td><td>@50</td><td>@100</td></tr><tr><td>MI+Vanilla SFT (Baseline)</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td><td>0.00%</td></tr><tr><td>MI+Multi-task SFT (LC-Rec)</td><td>+7.69%</td><td>+11.86%</td><td>+13.41%</td><td>+12.03%</td><td>+15.73%</td><td>+8.47%</td><td>+10.74%</td><td>+11.30%</td><td>+11.18%</td><td>+13.26%</td></tr><tr><td>GTI+Vanilla SFT (Ours)</td><td>+1.71%</td><td>+22.03%</td><td>+26.02%</td><td>+21.55%</td><td>+18.54%</td><td>-5.19%</td><td>+8.02%</td><td>+12.23%</td><td>+12.83%</td><td>+12.46%</td></tr></table>

![](images/90e84e6303cad3aa132dc2b79f5bd3058f472c1c3ebf75f72669f1cead493d4f.jpg)

![](images/b175d7705c7f1e933a1fd7eaa20f84ae8d7af737889d61778ef7c5ff20ca85b5.jpg)  
Figure 4: Relative gain versus candidate pool size. Left: Relative Recall@K gain; Right: Relative NDCG@K gain. Shaded areas denote variability across runs.

![](images/788b72e37607d4abad6e6681bb2649dbb495167dc549262576a96e7ecc4cb82d.jpg)

![](images/5f72dcd9c8d3fef77a1f74d542385219904ebdc3d3bf7106c360953893a5312d.jpg)

![](images/2868ef299d41328fcfc2d3daaaff301e59e53776ab6170e988e8059cf8afe8bb.jpg)  
Figure 5: Pairwise cosine-similarity matrices under three initialization strategies. Each matrix shows similarities between 50 pretrained tokens (upper-left block) and 50 SID tokens (bottom-right block)5. Random initialization (left) yields noninformative SID embeddings. Mean initialization (middle) collapses SID tokens into a near-uniform block. GTI (right) produces differentiated intra-SID structure with meaningful affinities to pretrained tokens.

![](images/6779e02b6f034d815215688f9e1222263d3faf6dbe34cb71b484c33aa0182407.jpg)

![](images/b329b2bd5c6cf6930ce457c083686e03e114b0b62d9a1c9532982659733b168b.jpg)

![](images/f834eac1a7c2fc63916eb0966504726a4249220ccc88d7a3f5307d212a829626.jpg)  
Figure 6: Pairwise SID similarity after fine-tuning (public dataset). We visualize the pairwise cosine similarity matrix of SID embeddings at the fine-tuned checkpoint. GTI is the only initialization strategy that preserves a clear blockwise hierarchical semantics among SID tokens, suggesting improved preservation of semantic geometry. By contrast, mean and random initialization produce flat or noisy similarity patterns even after SFT stage.

Controlled comparison on public dataset. To disentangle the effect of grounded initialization from that of multi-task adaptation and assess the generalization of our method beyond the proprietary dataset, we compare GTI+Vanilla SFT against LC-Rec (Multi-task SFT) on the public Vibrent dataset (Table 4 and Figure 4). Even without auxiliary objectives during fine-tuning, GTI achieves substantially higher Recall at $K \geq 1 0$ (e.g., $+ 2 6 . { \dot { 0 } } 2 { \% }$ vs. $+ 1 3 . 4 1 \%$ at Recall $@ 2 0$ ) and comparable NDCG, indicating that the grounding stage alone accounts for a large portion of the downstream improvement.

# 4.3 Further Analysis

The preceding results establish that grounded initialization improves downstream performance; we now investigate why. We use spectral and geometric diagnostics on the SID embedding subspace, both at initialization and after fine-tuning. These analyses provide direct evidence to the Grounded Token Initialization Hypothesis (Section 2).

Grounded initialization produces differentiated embedding geometry. Figure 5 visualizes pairwise cosine similarities among pretrained vocabulary tokens and SID tokens under three initialization strategies. Random initialization avoids uniformity but yields unstructured noise with no coherent affinity to the pretrained manifold. Mean initialization produces a uniform SID block, confirming the collapse diagnosed in Section 2. In contrast, GTI produces rich, differentiated structure within the SID block together with coherent cross-block affinities to relevant lexical tokens.

![](images/63e4b69ae2a028bbb5e79b3e2949d6472313501525d8d319efe4c6f75900f233.jpg)  
Figure 7: (a) Singular-Value Spectra of SID embedding matrix after SFT: GTI initialization yields slower spectral decay and higher effective rank than mean initialization. (b) Representational Similarity Analysis (RSA) of SID embeddings after SFT: We compare the pairwise geometry of the ground-truth RQ-VAE codebook vectors and the learned SID embeddings using Pearson r and Spearman ρ. GTI initialization achieves the highest correlation under both metrics, indicating better preservation of the semantic structure among SID embeddings than mean or random initialization.

Grounded structure persists through fine-tuning. We next examine whether the structure induced by grounding persists through fine-tuning. (1) Pairwise cosine similarities among SID embeddings after fine-tuning on the public dataset (Figure 6) show that only the GTIinitialized model preserves the blockwise hierarchical structure encoded by the RQ-VAE; mean and random initialization produce flat or noisy similarity patterns. (2) The singularvalue spectrum of $E _ { \mathrm { S I D } } \in \mathbb { R } ^ { | \mathcal { V } _ { \mathrm { S I D } } | \times d }$ after fine-tuning on the industrial dataset (Figure 7a) shows that mean initialization leads to rapid spectral decay and low effective rank, while grounded initialization yields slower decay and higher effective rank, indicating a nondegenerate subspace with multiple active directions along which items differ (see Appendix for extended SVD analysis of the industrial dataset).(3) Representational similarity analysis (RSA) between the learned SID embeddings and the ground-truth RQ-VAE codebook vectors (Figure 7b) shows that GTI-initialized embeddings better preserve the original semantic structure through training. Taken together, these results suggest that the grounding stage seeds embedding structure that persists through fine-tuning, corroborating the downstream performance gains.

# 5 Related Work

Vocabulary Extension in Language Models. Extending a pretrained LM’s vocabulary with new tokens is a recurring challenge. Standard approaches initialize new embeddings at the vocabulary mean (Hewitt, 2021) or randomly, then rely on fine-tuning. ToolkenGPT (Hao et al., 2024) and Yo’LLaVA (Nguyen et al., 2024) show that training only new token embeddings against a frozen LM can be effective for tool invocation and visual concept grounding, respectively. GTI reframes this mechanism as an initialization strategy: by grounding new tokens before fine-tuning, the learned structure serves as a starting point that benefits arbitrary downstream tasks, rather than being tied to a specific end use.

Generative Recommendation. We adopt generative recommendation as our primary evaluation domain, as it requires injecting thousands of novel tokens into a pretrained LM, making it a demanding testbed for vocabulary extension. This paradigm frames retrieval as autoregressive decoding of Semantic IDs (SIDs) discretized via RQ-VAE (van den Oord et al., 2018; Lee et al., 2022; Rajput et al., 2023; Zheng et al., 2024). We provide an extended discussion in Appendix 7.5.

# 6 Conclusion

Through spectral and geometric diagnostics, we show that mean-of-vocabulary initialization collapses new tokens into a degenerate subspace that fine-tuning does not fully recover. Motivated by this diagnosis, we propose GTI, a lightweight grounding stage that learns only

the new token embeddings via paired linguistic supervision before standard fine-tuning. On generative recommendation benchmarks spanning industrial-scale and public datasets, GTI consistently outperforms both mean initialization and auxiliary-task adaptation, with further analyses confirming that grounded structure persists through fine-tuning. These findings support the Grounded Token Initialization Hypothesis. As the grounding mechanism makes no assumptions about the downstream task, an important direction for future work is to test its generality in broader vocabulary-extension settings beyond recommendation.

# References

Karl Audun Kagnes Borgersen. Vibrent clothes rental dataset. https://www.kaggle.com/ datasets/kaborg15/vibrent-clothes-rental-dataset, 2024. Kaggle dataset, accessed March 22, 2026.   
Rui Cai, Chao Wang, Qianyi Cai, Dazhong Shen, and Hui Xiong. Boosting knowledge graphbased recommendations through confidence-aware augmentation with large language models. arXiv preprint arXiv:2502.03715, 2025.   
Ben Chen, Xian Guo, Siyuan Wang, Zihan Liang, Yue Lv, Yufei Ma, Xinlong Xiao, Bowen Xue, Xuxin Zhang, Ying Yang, Huangyu Dai, Xing Xu, Tong Zhao, Mingcan Peng, Xiaoyang Zheng, Chao Wang, Qihang Zhao, Zhixin Zhai, Yang Zhao, Bochao Liu, Jingshan Lv, Jing Chen, Xiao Liang, Yuqing Ding, Chenyi Lei, Wenwu Ou, Han Li, and Kun Gai. Onesearch: A preliminary exploration of the unified end-to-end generative framework for e-commerce search, 2025a. URL https://arxiv.org/abs/2509.03236.   
Daiwei Chen, Yi Chen, Aniket Rege, Zhi Wang, and Ramya Korlakai Vinayak. Pal: Sampleefficient personalized reward modeling for pluralistic alignment. In The Thirteenth International Conference on Learning Representations, 2025b. URL https://openreview.net/forum? id=1kFDrYCuSu.   
Yashar Deldjoo, Zhankui He, Julian McAuley, Anton Korikov, Scott Sanner, Arnau Ramisa, Rene Vidal, Maheswaran Sathiamoorthy, Atoosa Kasirzadeh, and Silvia Milano. A review ´ of modern recommender systems using generative models (gen-recsys), 2024. URL https://arxiv.org/abs/2404.00579.   
Jiaxin Deng, Shiyao Wang, Kuo Cai, Lejian Ren, Qigen Hu, Weifeng Ding, Qiang Luo, and Guorui Zhou. Onerec: Unifying retrieve and rank with generative recommender and iterative preference alignment. arXiv preprint arXiv:2502.18965, 2025. URL https: //arxiv.org/abs/2502.18965.   
Yijie Ding, Zitian Guo, Jiacheng Li, Letian Peng, Shuai Shao, Wei Shao, Xiaoqiang Luo, Luke Simon, Jingbo Shang, Julian McAuley, and Yupeng Hou. How well does generative recommendation generalize?, 2026. URL https://arxiv.org/abs/2603.19809.   
Jun Gao, Di He, Xu Tan, Tao Qin, Liwei Wang, and Tie-Yan Liu. Representation degeneration problem in training natural language generation models. In International Conference on Learning Representations, 2019.   
Shijie Geng, Shuchang Liu, Zuohui Fu, Yingqiang Ge, and Yongfeng Zhang. Recommendation as language processing (rlp): A unified pretrain, personalized prompt & predict paradigm (p5), 2023. URL https://arxiv.org/abs/2203.13366.   
Ruidong Han, Bin Yin, Shangyu Chen, He Jiang, Fei Jiang, Xiang Li, Chi Ma, Mincong Huang, Xiaoguang Li, Chunzhen Jing, et al. Mtgr: Industrial-scale generative recommendation framework in meituan. arXiv preprint arXiv:2505.18654, 2025.   
Shibo Hao, Tianyang Liu, Zhen Wang, and Zhiting Hu. Toolkengpt: Augmenting frozen language models with massive tools via tool embeddings, 2024. URL https://arxiv. org/abs/2305.11554.   
Xiangnan He, Lizi Liao, Hanwang Zhang, Liqiang Nie, Xia Hu, and Tat-Seng Chua. Neural collaborative filtering. In Proceedings of the 26th International Conference on World Wide Web (WWW ’17), pp. 173–182, 2017. doi: 10.1145/3038912.3052569.

Xiangnan He, Kuan Deng, Xiang Wang, Yan Li, Yongdong Zhang, and Meng Wang. Lightgcn: Simplifying and powering graph convolution network for recommendation, 2020. URL https://arxiv.org/abs/2002.02126.   
John Hewitt. Initializing new word embeddings for pretrained language models. https: //nlp.stanford.edu/∼johnhew/vocab-expansion.html, 2021.   
HuggingFace. Trl documentation: Quickstart. https://huggingface.co/docs/trl/en/ quickstart, 2025. Accessed: 2025-09-23.   
Ruijie Jiang, Thuan Nguyen, Shuchin Aeron, and Prakash Ishwar. Hard-negative sampling for contrastive learning: Optimal representation geometry and neural-vs dimensionalcollapse. Transactions on Machine Learning Research, 2024.   
Li Jing, Pascal Vincent, Yann LeCun, and Yuandong Tian. Understanding dimensional collapse in contrastive self-supervised learning. arXiv preprint arXiv:2110.09348, 2021.   
Wang-Cheng Kang and Julian McAuley. Self-attentive sequential recommendation. In 2018 IEEE International Conference on Data Mining (ICDM), pp. 197–206, 2018. doi: 10.1109/ ICDM.2018.00035.   
Yehuda Koren, Robert Bell, and Chris Volinsky. Matrix factorization techniques for recommender systems. Computer, 42(8):30–37, 2009. doi: 10.1109/MC.2009.263.   
Doyup Lee, Chiheon Kim, Saehoon Kim, Minsu Cho, and Wook-Shin Han. Autoregressive image generation using residual quantization, 2022. URL https://arxiv.org/abs/2203. 01941.   
Omer Levy and Yoav Goldberg. Neural word embedding as implicit matrix factorization. In Advances in Neural Information Processing Systems, volume 27, 2014.   
Thao Nguyen, Haotian Liu, Yuheng Li, Mu Cai, Utkarsh Ojha, and Yong Jae Lee. Yo’llava: Your personalized language and vision assistant, 2024. URL https://arxiv.org/abs/ 2406.09400.   
Shashank Rajput, Nikhil Mehta, Anima Singh, Raghunandan H. Keshavan, Trung Vu, Lukasz Heldt, Lichan Hong, Yi Tay, Vinh Q. Tran, Jonah Samost, Maciej Kula, Ed H. Chi, and Maheswaran Sathiamoorthy. Recommender systems with generative retrieval, 2023. URL https://arxiv.org/abs/2305.05065.   
Aniket Rege, Aditya Kusupati, Sharan Ranjit S, Alan Fan, Qingqing Cao, Sham Kakade, Prateek Jain, and Ali Farhadi. Adanns: A framework for adaptive semantic search. In A. Oh, T. Naumann, A. Globerson, K. Saenko, M. Hardt, and S. Levine (eds.), Advances in Neural Information Processing Systems, volume 36, pp. 76311–76335. Curran Associates, Inc., 2023. URL https://proceedings.neurips.cc/paper files/paper/2023/ file/f062da1973ac9ac61fc6d44dd7fa309f-Paper-Conference.pdf.   
Yi Tay, Vinh Tran, Mostafa Dehghani, Jianmo Ni, Dara Bahri, Harsh Mehta, Zhen Qin, Kai Hui, Zhe Zhao, Jai Gupta, et al. Transformer memory as a differentiable search index. In Advances in Neural Information Processing Systems, 2022.   
Aaron van den Oord, Oriol Vinyals, and Koray Kavukcuoglu. Neural discrete representation learning, 2018. URL https://arxiv.org/abs/1711.00937.   
Wenjie Wang, Honghui Bao, Xinyu Lin, Jizhi Zhang, Yongqi Li, Fuli Feng, See-Kiong Ng, and Tat-Seng Chua. Learnable item tokenization for generative recommendation, 2024. URL https://arxiv.org/abs/2405.07314.   
Xiang Wang, Xiangnan He, Meng Wang, Fuli Feng, and Tat-Seng Chua. Neural graph collaborative filtering. In Proceedings of the 42nd International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR ’19), pp. 165–174, 2019. doi: 10.1145/3331184.3331267.

Thomas Wolf, Lysandre Debut, Victor Sanh, Julien Chaumond, Clement Delangue, Anthony Moi, Pierric Cistac, Tim Rault, Remi Louf, Morgan Funtowicz, Joe Davison, Sam Shleifer, Patrick von Platen, Clara Ma, Yacine Jernite, Julien Plu, Canwen Xu, Teven Le Scao, Sylvain Gugger, Mariama Drame, Quentin Lhoest, and Alexander Rush. Transformers: State-of-the-art natural language processing. In Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing: System Demonstrations, pp. 38–45, 2020.   
Jiaqi Zhai, Lucy Liao, Xing Liu, Yueming Wang, Rui Li, Xuan Cao, Leon Gao, Zhaojie Gong, Fangda Gu, Jiayuan He, Yinghai Lu, and Yu Shi. Actions speak louder than words: Trillion-parameter sequential transducers for generative recommendations. In Ruslan Salakhutdinov, Zico Kolter, Katherine Heller, Adrian Weller, Nuria Oliver, Jonathan Scarlett, and Felix Berkenkamp (eds.), Proceedings of the 41st International Conference on Machine Learning, volume 235 of Proceedings of Machine Learning Research, pp. 58484–58509. PMLR, 21–27 Jul 2024. URL https://proceedings.mlr.press/v235/zhai24a.html.   
Haichao Zhang and Yun Fu. VQToken: Neural discrete token representation learning for extreme token reduction in video large language models. In The Thirty-ninth Annual Conference on Neural Information Processing Systems, 2025. URL https://openreview.net/ forum?id=X8oEu4Gs3W.   
Haichao Zhang, Yao Lu, Lichen Wang, Yunzhe Li, Daiwei Chen, Yunpeng Xu, and Yun Fu. Linkedout: Linking world knowledge representation out of video llm for next-generation video recommendation. arXiv preprint arXiv:2512.16891, 2025.   
Bowen Zheng, Yupeng Hou, Hongyu Lu, Yu Chen, Wayne Xin Zhao, Ming Chen, and Ji-Rong Wen. Adapting large language models by integrating collaborative semantics for recommendation, 2024. URL https://arxiv.org/abs/2311.09049.   
Guorui Zhou, Jiaxin Deng, Jinghao Zhang, Kuo Cai, Lejian Ren, Qiang Luo, Qigen Wang, Qianqian Hu, Rui Huang, Shiyao Wang, et al. Onerec technical report. arXiv preprint arXiv:2506.13695, 2025. URL https://arxiv.org/abs/2506.13695.

# 7 Appendix

# 7.1 Datasets

# 7.1.1 Retrieval Dataset

Industrial Candidate Retrieval Dataset. The industrial-scale candidate retrieval dataset6 consists of job requirement–candidate pairs collected in 2025 from a world-leading professional networking platform with global user coverage and evaluated by our internal LLM judge. According to product policy, which measures how many job requirements a candidate satisfies, each pair is assigned to one of three relevance levels: good match, good&maybe match, and not match. We use the good match pairs for supervised fine-tuning (SFT).

The member profile dataset contains profiles of users who provide at least one of the following attributes: geographic location, job positions, education history, or skill information.

Vibrent Dataset. The Vibrent Clothes Rental Dataset is a publicly available dataset from Kaggle. To complement our industrial dataset with a publicly available benchmark, we also evaluate our method on it. The dataset contains anonymized user–item rental transactions from a clothing rental platform. We construct a candidate retrieval task by treating users as queries and clothing items as candidates, where observed rental interactions are considered positive relevance signals, and non-interacted items are treated as negatives during training.

# 7.2 Prompt Templates

7.2.1 Prompt Template: Auxiliary Task (Item Title/Description New Vocabulary Tokens)

Item Title/Description Semantic IDs7(Title→New Vocabulary Tokens)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
Which item has the title: {{title}}?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

Item Title/Description Semantic IDs (Description New Vocabulary Tokens)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
Can you tell me what item is described as {{description}}?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

Item Title/Description Semantic IDs (Title+Description New Vocabulary Tokens)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
What item is called {{title}} and described as {{description}}?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

Semantic IDs Item Title/Description (New Vocabulary Tokens→Title)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
Could you please tell me what item {{ITEM SEMANTIC_ID}} is called?   
<assistant>   
{{title}} 
```

Semantic IDs Item Title/Description (New Vocabulary Tokens Description)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
Briefly describe item {{ITEM SEMANTIC_ID}}.   
<assistant>   
{{description}} 
```

Semantic IDs Item Title/Description (New Vocabulary Tokens Title+Description)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
What is the title and description of item {{ITEM SEMANTIC_ID}}?   
<assistant>   
{{title}}\n\n{description} 
```

# 7.2.2 Prompt Template: Search Query Task

Candidate Description Semantic Id Alignment Prompt 8   
```handlebars
<user>   
Instruction: Predict the candidate SID. Input:   
{{candidate headline}}   
{{candidate profile description}}   
{{candidate job title}}   
{{candidate education}}   
{{candidate employment history}}   
{{candidate location}}   
{{candidate skills}}   
{{candidate company}}   
<assistant>   
{{CANDIDATE SEMANTIC_ID}} 
```

Semantic Id → Candidate Description Alignment Prompt   
```handlebars
<user>   
Instruction: Recover the candidate text. Input: {{CANDIDATE SEMANTIC_ID}}   
<assistant>   
{{candidate headline}}   
{{candidate profile description}}   
{{candidate job title}}   
{{candidate education}}   
{{candidate employment history}}   
{{candidate location}}   
{{candidate skills}} 
```

7Most of Item Title/Description Semantic IDs prompts and retrieval prompts are adapted from (Zheng et al., 2024).

```handlebars
{{candidate company}} 
```

Search Query Candidate Semantic Id Alignment Prompt   
```handlebars
<user>   
Instruction: Predict the relevant candidate SID that matches job requirements as much as possible. If there are no candidates that meet the criteria, return the candidate SID that prioritizes the matching required requirements then matching the preferred requirements. Input:   
{{required requirements}}   
{{preferred requirements}}   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

# 7.2.3 Prompt Template: Retrieval Task

Retrieval Prompt (Template 1)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
The user has interacted with items {{inters}} in chronological order. Can you predict the next possible item that the user may expect?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

Retrieval Prompt (Template 2)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
Based on the items that the user has interacted with: {{inters}}, can you determine what item would be recommended to the user next?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

Retrieval Prompt (Template 3)   
```handlebars
<system>   
You are a helpful assistant.   
<user>   
Here is the item interaction history of the user: {{inters}}, what to recommend to the user next?   
<assistant>   
{{ITEM SEMANTIC_ID}} 
```

# 7.3 Implementation Details

We utilize the pre-trained Qwen3-Embedding-0.6B encoder to extract semantic representations for items. The encoder processes item metadata including titles and descriptions to generate 1024-dimensional dense vectors that capture semantic similarities between items. We process text features of products by concatenating them as: [TITLE] [DESCRIPTION]. We set the maximum input sequence length as 2048. The final outputs are dense semantic embeddings: $z _ { i } \in \mathbb { R } ^ { 1 0 2 4 }$ for item i.

Our Residual Quantized Variational Autoencoder (RQ-VAE) follows the TIGER (Rajput et al., 2023) framework with carefully designed architectural specifications to ensure effective quantization of semantic representations. The encoder architecture consists of a 3-layer Multi-Layer Perceptron (MLP) with hidden dimensions of [1024, 512, 256], utilizing ReLU activation functions and applying a dropout rate of 0.1 between layers. The residual quantization mechanism employs four codebook layers, each containing 256 entries with 32-dimensional codes. This hierarchical quantization approach enables fine-grained representation of semantic information while maintaining discrete tokenization properties essential for language model integration. We trained the model for 20,000 epochs to achieve a high codebook utilization rate and minimize collision rates. To further prevent collisions where multiple items map to identical sequences of semantic IDs, we employed the Sinkhorn-Knopp trick used by LC-Rec (Zheng et al., 2024), which ensures uniform distribution of item semantics across codebook embeddings in the final layer.

The base language model employs Qwen3-0.6B with hidden dimension of 1024. The model architecture comprises 28 transformer layers supporting a maximum context length of 32,768 tokens. This configuration provides sufficient capacity for processing sequential recommendation tasks while maintaining computational efficiency. Parameter-efficient fine-tuning is implemented through Quantized Low-Rank Adaptation (QLoRA) with a rank of 8 and alpha value of 32. The LoRA adaptation applies a dropout rate of 0.05 and targets key projection matrices including q proj, k proj, v proj, o proj, gate proj, up proj, and down proj. We also set LoRA modules to be saved as embed tokens and lm head, so that only the embedding layer and the language modeling head are preserved during training while other modules can remain frozen. This configuration enables efficient adaptation while preserving pre-trained knowledge.

We implement the token-embedding grounding stage of GTI by extending the Hugging Face TRL (HuggingFace, 2025) SFTTrainer to update only the Semantic-ID embedding matrix while freezing the LM backbone; the trainer consumes paired (title/description, SemID) examples and optimizes the embeddings as outlined in the pseudo code below. Unless otherwise stated, we train for 10 epochs with a learning rate of 1e-3 and a batch size 16.

Algorithm 1: GTI Grounding Stage   
Input: Pretrained model $\mathcal{M}$ with embedding matrix $E\in \mathbb{R}^{V\times d}$ ; new token indices $\mathcal{T}\subseteq \{0,\dots ,V - 1\}$ ; paired corpus $\mathcal{D} = \{(text_j,\text{token}_j)\}$ Output: Model $\mathcal{M}$ with grounded embeddings for tokens in $\mathcal{T}$ // Setup: freeze all parameters except new token embeddings  
Freeze all parameters of $\mathcal{M}$ Construct binary mask $\mathbf{m}\in \{0,1\} ^V$ where $m_{i} = 1$ iff $i\in \mathcal{T}$ $\mathbf{M}\gets \mathbf{m}\otimes \mathbf{1}_d$ // Broadcast to $\mathbb{R}^{V\times d}$ // Training: update only new token embeddings via masked gradients  
for each batch $\mathcal{B}\subset \mathcal{D}$ do $\begin{array}{l}\mathcal{L}\leftarrow \mathrm{LM\_Loss}(\mathcal{M},\mathcal{B})\\ \nabla E\leftarrow \nabla_{E}\mathcal{L}\\ E\leftarrow E - \eta \cdot (\nabla E\odot \mathbf{M}) \end{array}$ // Forward pass // Compute gradients // Update only new token embeddings

# 7.4 Analysis Details

Representation Similarity Analysis (RSA). To quantitatively measure whether the learned representations preserves the semantic structure of SID new vocabulary tokens, we perform representational similarity analysis. Given the well-trained RQ-VAE codebooks, which encode the compressed representation of SID new vocabulary tokens, we define the oracle semantic embeddings as $\mathbf { \bar { \phi } } _ { X } = \{ x _ { 1 } , . . . , x _ { n } \} , x _ { i } \in \mathbf { R } ^ { 3 2 }$ . And let the corresponding learned

token embeddings from language model as $\hat { X } = \{ \hat { x } _ { 1 } , . . . , \hat { x } _ { n } \} , x _ { i } \in \mathbb { R } ^ { d } .$ , where $d$ depends on the language model dimensionality. We construct pairwise token similarity matrices $S _ { X } , S _ { \hat { X } } \in \tilde { \mathbf { R } ^ { n \times n } } $ , where:

$$
(S _ {X}) _ {i, j} = \cos (x _ {i}, x _ {j}), \qquad (S _ {\hat {X}}) _ {i, j} = \cos (\hat {x} _ {i}, \hat {x} _ {j}).
$$

We then vectorize the upper-triangular entries of $S _ { X }$ and $S _ { \hat { X } }$ and compute their correlation (We implement both Spearman correlation and Pearson correlation to capture complementary aspects of representational alignment). This yields an RSA score that quantifies the extent to which the learned representation space preserves the pairwise semantic relations of the oracle space. Since RSA compares representational geometry rather than coordinates directly, it is well suited to our setting where the oracle and learned embeddings live in different ambient dimensions (32 vs. d).

Extended SVD analysis of the industrial dataset. The slower spectral decay and higher effective rank observed with GTI initialization suggest that this method preserves a more expressive and diverse feature space throughout the SFT process, preventing the dimensional collapse often associated with mean initialization.

![](images/fe4c38f2dd8161b838a792957d0c30cfe855d49433718a7b146c1faed1ff4097.jpg)  
Figure 8: Singular-Value Spectra of SID embedding matrix after SFT for Industrial dataset.

# 7.5 Full Related Work

RQ-VAE and Semantic IDs. Vector-quantized autoencoders (van den Oord et al., 2018; Zhang & Fu, 2025) learn discrete item representations by mapping continuous embeddings to codebook entries. Residual Quantized VAEs (RQ-VAE) (Lee et al., 2022) extend this

Table 4: Additional retrieval results on the Vibrent dataset. We report Recall@K and NDCG@K for Baseline (MI+Vanilla SFT), LC-Rec (MI+Multi-task SFT), and our method GTI+Vanilla SFT. GTI+Vanilla SFT achieves the best performance on most Recall@K metrics and remains competitive on NDCG@K, further supporting the effectiveness of grounded token initialization for generative retrieval.   

<table><tr><td rowspan="2">Methodology</td><td colspan="5">Recall@K</td><td colspan="5">NDCG@K</td></tr><tr><td>@5</td><td>@10</td><td>@20</td><td>@50</td><td>@100</td><td>@5</td><td>@10</td><td>@20</td><td>@50</td><td>@100</td></tr><tr><td>MI+Vanilla SFT (Baseline)</td><td>0.0226</td><td>0.0342</td><td>0.0475</td><td>0.0771</td><td>0.1031</td><td>0.0150</td><td>0.0188</td><td>0.0222</td><td>0.0280</td><td>0.0322</td></tr><tr><td>MI+Multi-task SFT (LC-Rec)</td><td>0.0243</td><td>0.0382</td><td>0.0539</td><td>0.0863</td><td>0.1194</td><td>0.0163</td><td>0.0208</td><td>0.0247</td><td>0.0311</td><td>0.0365</td></tr><tr><td>GTI+Vanilla SFT (Ours)</td><td>0.0230</td><td>0.0417</td><td>0.0599</td><td>0.0937</td><td>0.1222</td><td>0.0143</td><td>0.0203</td><td>0.0249</td><td>0.0316</td><td>0.0362</td></tr></table>

with a hierarchy of residual codebooks, producing multi-level Semantic IDs (SIDs) that capture progressively finer semantic distinctions. Unlike conventional item IDs, SIDs carry compositional structure amenable to autoregressive generation, making them a standard component in generative recommendation (Rajput et al., 2023; Zheng et al., 2024; Han et al., 2025). Crucially, each codebook entry becomes a new token in the LM vocabulary, and how these tokens are initialized is precisely the bottleneck our work addresses.

Generative Recommendation. Generative retrieval reframes recommendation as autoregressive decoding of item identifiers rather than nearest-neighbor search in embedding space (Rege et al., 2023; Chen et al., 2025b). TIGER (Rajput et al., 2023) introduced RQ-VAE-learned SIDs as generation targets, and LC-Rec (Zheng et al., 2024) added auxiliary linguistic objectives during fine-tuning to improve SID representations. Several systems have demonstrated industrial-scale deployment: MTGR (Han et al., 2025) integrates generative retrieval with DLRM cross-feature signals; OneSearch (Chen et al., 2025a) combines keyword-enhanced quantization with preference-aware rewards; and OneRec (Deng et al., 2025; Zhou et al., 2025) unifies retrieval and ranking via session-wise generation. Complementary directions include LLM-driven knowledge-graph recommenders (Cai et al., 2025) and MLLM-based world-knowledge integration (Zhang et al., 2025). All of these systems must inject novel tokens into a pretrained LM; our work addresses a step that is upstream of and complementary to their contributions, namely how those tokens should be initialized.

Connection to Dimensional Collapse. The initialization collapse we diagnose is related to dimensional collapse in contrastive and self-supervised learning (Jing et al., 2021; Jiang et al., 2024), where learned representations are restricted to a low-dimensional subspace, eliminating fine-grained distinctions (Figure 2). Mean-of-vocabulary initialization induces a similar effect: all new tokens start at the same point, forming a rank-deficient configuration. Jiang et al. (2024) show that appropriate initialization can mitigate dimensional collapse in contrastive learning, which parallels our finding that grounding new tokens before fine-tuning preserves a higher-rank, more differentiated embedding subspace.