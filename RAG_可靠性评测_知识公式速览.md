# RAG 可靠性评测与幻觉抑制：知识与公式速览

本文面向毕设方向“基于检索增强生成的中文专业知识问答系统及其可靠性评测研究”，用于快速了解相关概念、常用公式和可落地实验设计。

## 1. 方向概述

大语言模型可以生成流畅答案，但容易出现幻觉，即答案看似合理却没有事实依据。检索增强生成（Retrieval-Augmented Generation, RAG）的基本思想是：先从本地知识库中检索相关文档片段，再让大模型基于这些片段回答问题。

一个典型 RAG 系统包含：

1. 文档解析：读取 PDF、Word、Markdown、网页等资料。
2. 文本切分：将长文档切成多个 chunk。
3. 向量化：用 embedding 模型把 query 和 chunk 转成向量。
4. 检索召回：找出与问题最相关的 top-k 片段。
5. 重排序：用更精细的模型重新排序候选片段。
6. 生成回答：让 LLM 基于检索证据生成答案。
7. 可靠性评测：检查答案是否正确、是否有证据支持、是否应该拒答。

## 2. 核心概念

### 2.1 文档切分

设原始文档为：

```text
D = [t1, t2, ..., tn]
```

其中 `ti` 表示 token。切分后的片段集合为：

```text
C = {c1, c2, ..., cm}
```

常见切分方式：

```text
ci = [t_start, ..., t_end]
```

chunk size 通常设置为 300 到 1000 tokens，overlap 通常设置为 50 到 150 tokens。overlap 的作用是减少语义在切分边界处断裂。

### 2.2 向量表示

Embedding 模型将文本映射到向量空间：

```text
e_q = f(q)
e_i = f(ci)
```

其中：

- `q` 是用户问题。
- `ci` 是第 i 个文档片段。
- `f` 是 embedding 模型。
- `e_q` 和 `e_i` 是向量表示。

### 2.3 相似度检索

最常用的是余弦相似度：

```text
cos(e_q, e_i) = (e_q · e_i) / (||e_q|| ||e_i||)
```

检索目标：

```text
TopK(q) = arg top-k_i cos(e_q, e_i)
```

含义：从所有文档片段中选出和问题最相似的 k 个片段。

### 2.4 BM25 关键词检索

BM25 是传统信息检索方法，适合关键词匹配：

```text
score(D, q) = sum IDF(t) * ((f(t, D) * (k1 + 1)) / (f(t, D) + k1 * (1 - b + b * |D| / avgdl)))
```

其中：

- `f(t, D)`：词 t 在文档 D 中出现的次数。
- `|D|`：文档长度。
- `avgdl`：平均文档长度。
- `k1`、`b`：超参数，常见取值为 `k1 = 1.2`，`b = 0.75`。
- `IDF(t)`：逆文档频率，衡量词的重要性。

BM25 和向量检索可以组合成混合检索：

```text
score_final = alpha * score_dense + (1 - alpha) * score_bm25
```

其中 `alpha` 控制语义检索和关键词检索的权重。

## 3. RAG 生成公式

普通大语言模型直接根据问题生成答案：

```text
P(y | q)
```

RAG 模型引入检索到的证据集合 `Z`：

```text
P(y | q, Z)
```

其中：

```text
Z = {z1, z2, ..., zk}
```

`zi` 是检索得到的证据片段。

理想目标是：

```text
y* = argmax_y P(y | q, Z)
```

也就是说，生成答案时不仅依赖模型参数记忆，还依赖本地知识库证据。

## 4. 幻觉与可靠性

### 4.1 幻觉定义

在 RAG 场景中，幻觉可以定义为：

```text
Hallucination = Answer claims not supported by retrieved evidence
```

中文解释：答案中的某个事实性陈述无法被检索到的证据支持。

### 4.2 支持性判断

设答案被拆成多个事实陈述：

```text
A = {a1, a2, ..., an}
```

证据集合为：

```text
Z = {z1, z2, ..., zk}
```

如果存在某个证据 `zj` 支持陈述 `ai`，则：

```text
support(ai, Z) = 1
```

否则：

```text
support(ai, Z) = 0
```

答案支持率：

```text
SupportRate = (sum support(ai, Z)) / n
```

幻觉率：

```text
HallucinationRate = 1 - SupportRate
```

## 5. 常用评测指标

### 5.1 检索召回率 Recall@K

如果标准答案所需证据在 top-k 检索结果中出现，则记为命中。

```text
Recall@K = (# questions with relevant evidence in top-k) / (# all questions)
```

适合衡量检索模块能否找到正确材料。

### 5.2 检索准确率 Precision@K

```text
Precision@K = (# relevant chunks in top-k) / K
```

适合衡量 top-k 结果中有多少是真正有用的片段。

### 5.3 MRR

MRR（Mean Reciprocal Rank）关注第一个正确证据出现的位置：

```text
MRR = (1 / N) * sum_i (1 / rank_i)
```

其中 `rank_i` 是第 i 个问题中第一个相关证据的排名。

如果正确证据排得越靠前，MRR 越高。

### 5.4 答案准确率

```text
AnswerAccuracy = (# correct answers) / (# all questions)
```

可以人工标注，也可以用 LLM-as-a-judge 辅助评测，但最终论文里最好抽样人工复核。

### 5.5 引用准确率 Citation Precision

如果答案引用了证据编号，如 `[1]`、`[2]`，需要判断引用是否真的支持对应句子：

```text
CitationPrecision = (# supported citations) / (# all citations)
```

### 5.6 拒答准确率 Refusal Accuracy

对于知识库中没有答案的问题，系统应该拒答，而不是编造。

```text
RefusalAccuracy = (# correctly refused unanswerable questions) / (# unanswerable questions)
```

可以设计一批“知识库外问题”来测试。

### 5.7 综合可靠性分数

毕设中可以自定义一个综合指标：

```text
ReliabilityScore = w1 * AnswerAccuracy
                 + w2 * CitationPrecision
                 + w3 * Recall@K
                 + w4 * RefusalAccuracy
                 - w5 * HallucinationRate
```

其中：

```text
w1 + w2 + w3 + w4 + w5 = 1
```

权重可以根据论文重点设置，例如：

```text
w1 = 0.30
w2 = 0.25
w3 = 0.20
w4 = 0.15
w5 = 0.10
```

## 6. 可做的改进方法

### 6.1 混合检索

组合 BM25 和向量检索：

```text
score_final = alpha * score_dense + (1 - alpha) * score_bm25
```

实验可比较：

- 只用 BM25。
- 只用向量检索。
- BM25 + 向量检索。

### 6.2 重排序

先召回 top-20，再用 reranker 选 top-5：

```text
Candidates = RetrieveTop20(q)
Z = RerankTop5(q, Candidates)
```

重排序通常能提高证据质量。

### 6.3 置信度阈值拒答

如果最高相似度低于阈值，则拒答：

```text
if max_i cos(e_q, e_i) < theta:
    refuse
else:
    answer
```

其中 `theta` 是阈值。可以通过实验找到较合适的值。

### 6.4 引用约束生成

提示词要求模型：

```text
只能根据给定证据回答。
每个关键结论必须引用证据编号。
如果证据不足，回答“资料中没有足够信息”。
```

这能显著降低无依据扩写。

### 6.5 答案自检

生成答案后，再让模型逐句检查：

```text
For each claim ai in answer:
    judge whether ai is supported by evidence Z
```

可以输出：

```text
supported / unsupported / partially supported
```

最终只保留被支持的内容，或提示用户证据不足。

## 7. 毕设实验设计

### 7.1 数据集构建

可以从自己的课程资料、毕业论文相关文献、教材 PDF 中构建知识库。

建议数据规模：

- 文档：20 到 100 篇。
- 问答测试集：100 到 300 个问题。
- 不可回答问题：30 到 80 个。

问题类型：

1. 事实型：某概念是什么。
2. 比较型：A 和 B 有什么区别。
3. 推理型：根据材料判断某结论是否成立。
4. 引用型：要求答案给出证据来源。
5. 不可回答型：资料中没有答案。

### 7.2 对比实验

建议至少做 4 组：

```text
Baseline 1: 直接 LLM 回答，不使用知识库
Baseline 2: 普通 RAG
Method 1: RAG + 混合检索
Method 2: RAG + 混合检索 + 重排序 + 拒答阈值 + 自检
```

### 7.3 结果表格模板

| 方法 | Recall@5 | Answer Accuracy | Citation Precision | Refusal Accuracy | Hallucination Rate |
|---|---:|---:|---:|---:|---:|
| Direct LLM | - |  | - |  |  |
| Basic RAG |  |  |  |  |  |
| Hybrid RAG |  |  |  |  |  |
| Reliable RAG |  |  |  |  |  |

论文中重点分析：

- 检索质量是否影响答案质量。
- 引用约束是否降低幻觉。
- 拒答阈值是否能减少知识库外问题的编造。
- 自检是否能提高可靠性。

## 8. 系统模块设计

### 8.1 后端模块

```text
DocumentLoader
Chunker
EmbeddingService
VectorStore
Retriever
Reranker
AnswerGenerator
FaithfulnessChecker
Evaluator
```

### 8.2 前端页面

可以设计 4 个页面：

1. 知识库管理：上传、解析、切分文档。
2. 智能问答：输入问题，显示答案和引用。
3. 证据追踪：点击引用查看原文片段。
4. 评测面板：展示准确率、幻觉率、拒答准确率等指标。

## 9. 论文创新点写法

可以这样表述：

1. 构建了一个面向中文专业知识库的检索增强生成问答系统。
2. 设计了包含可回答与不可回答问题的中文 RAG 可靠性评测集。
3. 从检索召回、答案准确性、引用支持度、拒答能力和幻觉率多个角度评估系统可靠性。
4. 提出结合混合检索、重排序、引用约束和答案自检的幻觉抑制流程。

## 10. 开题报告可用题目

偏学术：

```text
面向中文垂直知识库的检索增强生成可靠性评测与幻觉抑制方法研究
```

偏工程：

```text
基于检索增强生成的中文专业知识问答系统设计与实现
```

折中推荐：

```text
基于检索增强生成的中文专业知识问答系统及其可靠性评测研究
```

## 11. 最小实现技术栈

推荐使用：

- Python：后端与实验脚本。
- FastAPI：提供问答接口。
- SQLite 或 PostgreSQL：保存文档和问答记录。
- FAISS、Chroma 或 Milvus：向量数据库。
- sentence-transformers 或 bge 系列模型：中文向量化。
- reranker 模型：重排序。
- Vue、React 或简单 HTML：前端展示。

如果时间有限，优先做：

```text
PDF 上传 -> 文本切分 -> 向量检索 -> RAG 问答 -> 引用展示 -> 指标评测
```

先保证闭环跑通，再做优化。

## 12. 一句话理解

这个毕设不是简单做一个“AI 问答网站”，而是研究：

```text
模型的答案是否来自知识库证据，以及如何减少没有证据的编造。
```

