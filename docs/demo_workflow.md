# RAG Reliability Guard 可演示流程

本文档用于把项目成果串成一条可以复现、可以答辩展示的闭环：输入 RAG 或 Agent 输出，评估证据支持情况，识别幻觉与错误拒答，并通过 guarded 配置或评测报告体现抑制效果。

## 项目定位

RAG Reliability Guard 是一个模型无关的 RAG/Agent 输出可靠性评估与幻觉抑制层。它不要求回答一定由本项目生成，也不绑定某个模型供应商。只要外部系统能提供 `answer + evidence`，本项目就可以评估该回答是否被证据支持。

项目有两种使用方式：

- 内置知识库模式：上传 PDF，系统完成解析、切分、检索、回答和评测。
- 外部评测模式：直接传入外部模型或 Agent 的回答与证据，系统只负责可靠性评估。

## 演示目标

演示时要回答三个问题：

1. 如何检测 RAG 可靠性：展示证据支持率、幻觉率、拒答准确率、过度拒答率等指标。
2. 如何识别幻觉：展示答案陈述与证据不匹配时，`hallucination_rate` 上升，`reliable` 变为 false。
3. 如何体现抑制效果：对比 baseline 与 guarded 配置，说明阈值策略如何提升不可回答问题上的拒答能力，或通过多模型对比找出更低幻觉率的输出。

## 准备环境

```powershell
git clone https://github.com/one-xl/rag-reliability-guard.git
cd rag-reliability-guard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 dashboard：

```text
http://127.0.0.1:8000/
```

## 路线 A：内置 PDF 知识库 RAG 对比

这条路线用于展示“同一个知识库、同一批问题下，guarded 配置比 baseline 更保守，能减少证据不足时的错误回答”。

### 1. 上传并索引 PDF

在 dashboard 的“上传 PDF”区域上传论文 PDF。上传后，系统会把文档元数据写入 `data/documents/`，并把原始文件保存到 `data/uploads/`。

注意：`data/` 是本地运行产物，默认不提交到 Git。

### 2. 构造真实论文评测集

```powershell
.\.venv\Scripts\python.exe scripts\build_real_paper_eval_dataset.py `
  --output datasets\real_paper_answer_eval_cases.json
```

如果重新上传同一批 PDF，`document_id` 可能变化，需要重新生成评测集。

### 3. 运行 baseline / guarded 对比

```powershell
.\.venv\Scripts\python.exe scripts\run_answer_eval_experiment.py `
  --dataset datasets\real_paper_answer_eval_cases.json
```

脚本会生成：

```text
data/experiments/comparison_<timestamp>.json
data/experiments/comparison_<timestamp>.csv
```

其中 baseline 不启用守护阈值，guarded 默认启用 `min_support_rate=0.5` 与 `min_relevance_overlap=0.35`。

### 4. 生成论文式 Markdown 报告

```powershell
.\.venv\Scripts\python.exe scripts\summarize_answer_eval_comparison.py `
  --input data\experiments\comparison_<timestamp>.json `
  --output reports\answer_eval_report_real_papers.md
```

答辩展示重点：

- `refusal_accuracy` 是否提升：体现对不可回答问题的幻觉抑制。
- `citation_hit_rate` 是否保持稳定：说明守护策略没有破坏引用链。
- `mean_support_rate` 与 `mean_hallucination_rate` 的变化：说明需要和拒答行为联合解释。

## 路线 B：外部模型 / Agent 全模型评测

这条路线用于展示“本项目不局限于毕业论文知识库，也可以评估任意模型或 Agent 输出”。

### 1. 准备外部评测数据

**推荐演示输入（答辩 / 端到端固定演示）：**

```text
datasets/demo_external_eval_cases.json
```

该文件与 `datasets/sample_external_answer_eval_cases.json` 同形，但体量更大、场景更全，便于一次跑完指标与 `aggregate.by_model` 对比。覆盖的典型情况包括：

| 场景 | 说明 |
|---|---|
| 有证据且回答正确 | 检索证据与陈述一致，支持率高、`reliable` 易为 true |
| 无证据且正确拒答 | 不可回答问题、空证据、模型明确拒绝，有利于 `refusal_accuracy` |
| 有证据但幻觉 | 证据写明某指标，回答改写为矛盾或未支持的细节，拉高幻觉代理 |
| 有证据但过度拒答 | 本应可答且证据充分，模型仍拒答，体现 `over_refusal_rate` |
| 不可回答却编造 | 无证据仍给出具体数值或结论，与正确拒答形成对照 |
| 多 provider / model / run_id | 多条记录分布在 volcengine、openai、anthropic、alibaba、google、deepseek 等标签及若干 `run_id`，便于表格与条形图分模型对比 |

体积较小的冒烟示例仍可使用：

```text
datasets/sample_external_answer_eval_cases.json
```

每条 case 至少包含：

- `question`：问题
- `answerable`：该问题是否应被证据回答
- `answer`：外部模型或 Agent 的回答
- `evidence`：外部系统提供的证据片段列表

可选字段：

- `provider`：模型供应商，例如 `volcengine`
- `model`：模型名，例如 `doubao-pro`
- `run_id`：外部实验批次

这些字段只作为元数据使用，外部评测不会真实调用模型。

### 2. 在 dashboard 中演示

打开首页后，找到“全模型 RAG / Agent 输出评估”区域。

操作步骤：

1. 将 `datasets/demo_external_eval_cases.json`（推荐）或 `datasets/sample_external_answer_eval_cases.json` 的内容粘贴到文本框，或直接使用页面内置默认示例后再替换为上述文件。
2. 点击“运行外部答案批量评测”。
3. 查看总体 `aggregate` 指标。
4. 查看 `aggregate.by_model` 分模型表。
5. 查看四组条形图：`mean_support_rate`、`mean_hallucination_rate`、`refusal_accuracy`、`over_refusal_rate`。
6. 观察系统标出的模型：幻觉率最低、拒答准确率最高、过度拒答率最高。
7. 展开下方原始 JSON，用于复制到实验报告或进一步分析。

这个区域适合展示“评估层”定位：模型输出可以来自任何外部系统，本项目只判断回答是否有证据支撑。

### 3. 使用命令行批量评测

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py `
  --dataset datasets\demo_external_eval_cases.json
```

输出：

```text
data/experiments/external_eval_<timestamp>.json
```

### 4. 生成多模型 Markdown 报告

默认读取 `data/experiments/` 下最新的 `external_eval_*.json`，写入固定文件名便于演示归档：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py --output reports\external_eval_report_demo.md
```

不加 `--output` 时文件名带时间戳。也可以指定输入输出：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py `
  --input data\experiments\external_eval_<timestamp>.json `
  --output reports\external_eval_report_demo.md
```

报告会列出整体指标、分模型指标、拒答准确率最高模型、过度拒答率最高模型、幻觉率最低模型和中文结论。

## 指标解释

| 指标 | 含义 | 展示价值 |
|---|---|---|
| `support_rate` | 答案陈述被证据支持的比例 | 越高说明答案越贴合证据 |
| `hallucination_rate` | `1 - support_rate` | 越高说明无证据陈述越多 |
| `refusal_accuracy` | 不可回答问题上正确拒答的比例 | 体现系统能否识别证据不足 |
| `over_refusal_rate` | 可回答问题上错误拒答的比例 | 体现系统是否过度保守 |
| `reliable` | 基于阈值的可靠性判断 | 可作为上线前拦截或人工复核信号 |

解释结果时不要只看单一指标。比如 guarded 配置可能提高拒答准确率，但也可能让部分回答更保守，因此应同时报告过度拒答率。

## 答辩展示证据链

建议按下面顺序展示：

1. 问题背景：RAG 和 Agent 可能给出看似流畅但缺乏证据的回答。
2. 系统定位：本项目在模型输出和用户之间增加一个可靠性评估层。
3. 检测能力：展示外部评测 case，说明同样的答案可以被拆解为证据支持率与幻觉率。
4. 幻觉识别：展示证据不支持的 case，指出 `hallucination_rate` 上升、`reliable=false`。
5. 幻觉抑制：展示 baseline / guarded 对比，强调 `refusal_accuracy` 提升。
6. 泛化能力：展示 dashboard 的多模型表格，说明项目不绑定某个模型，也不局限于论文 PDF。
7. 局限性：说明当前是轻量代理指标，需要更大评测集与人工抽检配合。

可以把最终结论概括为：

```text
本项目不是试图让某个模型永远不幻觉，而是在模型输出进入用户视野前，建立一层可复现的证据一致性检测与风险拦截机制。
```

## 常见问题

### data/ 目录为什么没有提交？

`data/` 是本地运行产物，包含上传 PDF 后生成的索引、实验 JSON 和 CSV。为了避免提交大文件或环境相关数据，该目录默认被 Git 忽略。

### 重新上传 PDF 后为什么测试集可能失效？

评测集里的 `expected_document_id` 与 `expected_chunk_index` 绑定当前索引状态。重新上传后文档 ID 可能变化，因此需要重新运行 `build_real_paper_eval_dataset.py`。

### 外部评测会调用真实大模型吗？

不会。外部评测只评估你传入的 `answer + evidence`。`provider` 和 `model` 是元数据，用于分模型统计。

### 如何体现项目不局限于毕业论文知识库？

使用路线 B。只要外部系统能提供答案和证据，本项目就可以评估它的输出，因此适用于 RAG 服务、Agent 工作流、搜索增强问答、企业知识库问答等场景。

### 如何体现“抑制”而不只是“检测”？

在内置 RAG 路线中，guarded 配置通过 `min_support_rate` 和 `min_relevance_overlap` 影响输出策略。证据不足时系统更倾向拒答，这可以通过 baseline / guarded 的 `refusal_accuracy` 差异体现。
