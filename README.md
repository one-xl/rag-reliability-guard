# RAG Reliability Guard

[English](README.en.md)

一个模型无关的 RAG/Agent 输出可靠性评估与幻觉抑制工具。

本项目用于判断 RAG 系统、智能体工作流或外部大模型管线生成的回答是否有证据支撑。它既可以作为本地 PDF 知识库问答系统运行，也可以作为独立的评估层，直接评估任意外部系统传入的 `answer + evidence` 数据。系统会输出证据支持率、幻觉风险、拒答准确率、过度拒答率和可靠性判断。

## 功能

- PDF 上传、本地解析、文本切分与索引
- 关键词检索与 BM25 检索
- 带引用的抽取式答案生成
- 可选接入豆包 / 火山方舟 OpenAI-compatible API
- 答案证据支持率与幻觉率评估
- 模型无关的外部 `answer + evidence` 评测
- 对可回答问题的过度拒答统计
- 批量答案评测、JSON/CSV 导出
- 实验历史记录与 Markdown 报告生成
- 真实论文评测集和毕设实验小节示例

## 目录结构

```text
app/                         FastAPI 应用、检索、答案生成、评测逻辑
app/services/                文档、实验记录、请求解析等服务层
app/static/index.html        浏览器 dashboard 页面结构
app/static/dashboard.css     dashboard 样式
app/static/dashboard.js      dashboard 交互逻辑
datasets/                     可复现实验数据集
docs/                         协作流程、提交清单、论文实验小节
reports/                      Markdown 实验报告
scripts/                      实验与报告自动化脚本
tests/                        pytest 测试
```

本地运行数据会写入 `data/`，该目录默认被 Git 忽略。

完整演示路线见 [docs/demo_workflow.md](docs/demo_workflow.md)：从内置 PDF 知识库 baseline/guarded 对比，到外部模型/Agent 全模型评测、dashboard 可视化和报告生成。

## 最短演示流程

开箱即用、无需上传 PDF：用固定数据集演示「外部模型 / Agent 输出的 RAG 可靠性评测与幻觉抑制」指标链（支持率、幻觉代理、拒答准确率、过度拒答、`aggregate.by_model`）。

**说明：** `datasets/demo_external_eval_cases.json` 等 demo 中的多 `provider` / `model` / `run_id` 标签为**演示数据**，用于展示分模型统计与报告形态，**不代表真实多模型对比或排名**。若需对豆包做真实生成再评测，见下方「真实豆包外部评测数据」。

1. **启动服务**（已在项目根目录创建虚拟环境并 `pip install -r requirements.txt`）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

2. **Dashboard**：浏览器打开 `http://127.0.0.1:8000/` ，在「全模型 RAG / Agent 输出评估」区域粘贴 [datasets/demo_external_eval_cases.json](datasets/demo_external_eval_cases.json) 全文并运行批量评测。

3. **命令行批量评测（demo 数据集）**：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset datasets\demo_external_eval_cases.json
```

4. **生成 demo 报告**（默认选取 `data/experiments/` 下文件名排序最新的 `external_eval_*.json`；若刚执行过上一步，即为本次输出）：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py --output reports\external_eval_report_demo.md
```

需要指定某次实验 JSON 时：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py `
  --input data\experiments\external_eval_<timestamp>.json `
  --output reports\external_eval_report_demo.md
```

更详细的答辩级步骤与指标说明仍以 [docs/demo_workflow.md](docs/demo_workflow.md) 为准。

### 真实豆包外部评测数据（需要 `.env`，会产生 API 费用）

在已配置 `DOUBAO_API_KEY` / `DOUBAO_MODEL` 的前提下，可先用 demo 骨架（`question` / `evidence` / `answerable`）调用豆包生成真实 `answer`，再跑外部评测与报告生成：

```powershell
.\.venv\Scripts\python.exe scripts\generate_doubao_external_eval_cases.py
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset data\experiments\doubao_external_eval_cases_<timestamp>.json
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py --input data\experiments\external_eval_<timestamp>.json --output reports\external_eval_report_doubao_live.md
```

`generate_doubao_external_eval_cases.py` 默认读 `datasets\demo_external_eval_cases.json`，写出 `data\experiments\doubao_external_eval_cases_<timestamp>.json`；可用 `--source` / `--output` / `--run-id` 覆盖。第二步的 `--dataset` 请指定上一步实际生成的文件路径；第三步的 `--input` 为 `evaluate_external_answers.py` 产出的 `external_eval_*.json`（若不加 `--input` 则默认取 `data\experiments` 下最新的 `external_eval_*.json`）。

## 环境要求

- 推荐 Python 3.12
- 以下命令以 Windows PowerShell 为例；macOS/Linux 可使用等价命令

依赖包括：

```text
fastapi
uvicorn[standard]
python-multipart
pypdf
httpx
pytest
```

## 安装部署

克隆仓库：

```powershell
git clone https://github.com/one-xl/rag-reliability-guard.git
cd rag-reliability-guard
```

创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -r requirements.txt
```

如果需要使用豆包生成器，复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`：

```text
DOUBAO_API_KEY=your_ark_api_key_here
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=your_doubao_endpoint_or_model_id_here
DOUBAO_TIMEOUT_SECONDS=60
```

`.env` 已被 `.gitignore` 忽略，不要提交 API Key。

## 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 dashboard：

```text
http://127.0.0.1:8000/
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 基础使用

推荐使用 `/api/v1/...` 版本化接口；旧的 `/api/...` 路径仍保留为兼容别名。

### 1. 上传 PDF

可以在 dashboard 上传，也可以调用接口：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/documents/upload" `
  -F "file=@C:\path\to\paper.pdf"
```

上传后，系统会解析 PDF、切分文本，并把索引元数据写入本地 `data/` 目录。

### 2. 检索证据

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/search?q=Self-RAG%20retrieve%20critique&method=bm25&top_k=3"
```

支持两种检索方式：

- `keyword`
- `bm25`

### 3. 生成带引用答案

抽取式答案：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Self-RAG retrieve generate critique\",\"method\":\"bm25\",\"generator\":\"extractive\",\"top_k\":3}"
```

开启幻觉抑制阈值：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Does this paper explain a quantum chip recipe?\",\"method\":\"bm25\",\"generator\":\"extractive\",\"top_k\":3,\"min_support_rate\":0.5,\"min_relevance_overlap\":0.35}"
```

关键参数：

- `min_support_rate`：答案被证据支持的最低比例
- `min_relevance_overlap`：问题有效词与检索证据的最低覆盖率

当证据不足时，系统会拒答或标记答案不可靠，避免无依据编造。

### 4. 使用豆包生成器

配置 `.env` 后，将 `generator` 设置为 `doubao`：

```json
{
  "question": "What is Self-RAG?",
  "method": "bm25",
  "generator": "doubao",
  "top_k": 3,
  "min_support_rate": 0.5,
  "min_relevance_overlap": 0.35
}
```

## 外部模型 / Agent 答案评测

如果答案来自项目外部，例如另一个 RAG 服务、Agent 工作流、搜索增强管线或其他模型供应商，可以直接使用外部评测接口。评测器只需要问题、回答、是否可回答标签和证据列表。

批量评测时，每条 `case` 可附带 **`provider`、`model`、`run_id`（均为可选）**，用于多模型对比：缺省时 `model` 与 `provider` 在结果里记为 `unknown`，`run_id` 为 `null`。聚合结果 `aggregate.by_model` 以 `provider/model` 为键分别统计 `total`、可答/不可答数量、`refusal_accuracy`、`over_refusal_rate`、平均支持率与平均幻觉率。

**重要：** 若 `answer` 来自诸如 `datasets/demo_external_eval_cases.json` 的固定示例，其中的 `provider` / `model` 往往是**占位标签**：外部评测管线**不会据此调用真实第三方模型**，只把你一并传入的 `answer` + `evidence` 纳入指标；这些标签既不表示真实推理过程，也不宜解读为可信的跨模型强弱排名。**只有**当你的 `answer` 确实由对应后端产生（例如你用 `scripts/generate_doubao_external_eval_cases.py` 调用的豆包）时，`provider=model` 才可视为与该次生成一致的元数据。

示例输入：

```json
{
  "min_support_rate": 0.5,
  "cases": [
    {
      "case_id": "supported-rag-answer",
      "provider": "volcengine",
      "model": "doubao-pro",
      "run_id": "exp-2026-001",
      "question": "What does RAG use before generating an answer?",
      "answerable": true,
      "answer": "RAG uses retrieved evidence before generating an answer.",
      "evidence": [
        {
          "evidence_id": "doc-1#chunk-1",
          "source": "example.md",
          "text": "Retrieval-Augmented Generation retrieves evidence from a knowledge base before generating an answer."
        }
      ]
    }
  ]
}
```

单条评测：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/evaluate/external-answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"What does RAG use?\",\"answerable\":true,\"answer\":\"RAG uses retrieved evidence.\",\"evidence\":[{\"text\":\"RAG uses retrieved evidence.\"}],\"min_support_rate\":0.5}"
```

批量评测：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/evaluate/external-answers" `
  -H "Content-Type: application/json" `
  -d "@datasets/sample_external_answer_eval_cases.json"
```

也可以运行脚本：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset datasets\sample_external_answer_eval_cases.json
```

输出文件：

```text
data/experiments/external_eval_<timestamp>.json
```

脚本写入的 JSON 与接口响应一致，包含每条 `rows` 的 `model` / `provider` / `run_id` 以及 `aggregate.by_model`。

外部评测指标：

- `support_rate`：答案陈述被证据支持的比例
- `hallucination_rate`：`1 - support_rate`
- `refusal_accuracy`：不可回答问题上的正确拒答率
- `over_refusal_rate`：可回答问题上的错误拒答率
- `reliable`：基于阈值的可靠性判断

### 生成多模型外部评测 Markdown 报告

在得到 `data/experiments/external_eval_<timestamp>.json` 后，可用汇总脚本生成中文 Markdown 报告：实验时间、数据集路径、整体 `aggregate` 指标表、`by_model` 分模型表，以及 `refusal_accuracy` 最高、`over_refusal_rate` 最高、`mean_hallucination_rate` 最低的模型与简短结论。

默认选取 `data/experiments/` 下文件名排序最新的一条 `external_eval_*.json`，输出到 `reports/external_eval_report_<timestamp>.md`：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py
```

指定输入或输出路径：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py `
  --input data\experiments\external_eval_<timestamp>.json `
  --output reports\external_eval_report_custom.md
```

未指定 `--input` 时，可用 `--experiments-dir` 修改扫描目录（默认 `data/experiments`）。

这使项目可以作为大部分 RAG/Agent 系统的通用评估与防护层，而不局限于内置 PDF 知识库。

## 实验流程

### 构造真实论文评测集

先上传并索引论文，再运行：

```powershell
.\.venv\Scripts\python.exe scripts\build_real_paper_eval_dataset.py --output datasets\real_paper_answer_eval_cases.json
```

注意：可回答样例会绑定当前本地索引中的 `document_id` 和 `chunk_index`。如果重新上传论文，需要重新生成评测集。

### 运行 Baseline / Guarded 对比实验

```powershell
.\.venv\Scripts\python.exe scripts\run_answer_eval_experiment.py --dataset datasets\real_paper_answer_eval_cases.json
```

脚本会运行两组配置：

- `baseline`：不开启证据支持率和相关性阈值
- `guarded`：开启 `min_support_rate=0.5`、`min_relevance_overlap=0.35`

输出目录：

```text
data/experiments/comparison_<timestamp>.json
data/experiments/comparison_<timestamp>.csv
```

### 生成 Markdown 实验报告

```powershell
.\.venv\Scripts\python.exe scripts\summarize_answer_eval_comparison.py `
  --input data\experiments\comparison_<timestamp>.json `
  --output reports\answer_eval_report_real_papers.md
```

报告会汇总数据集、配置、引用命中率、拒答准确率、平均支持率、平均幻觉率、结论和局限性。

## 测试

运行全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
```

当前预期结果：

```text
135 passed
```

开发质量工具可选安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m mypy app scripts
```

若要运行 pre-commit，本项目使用本地 hook；Windows 下建议先把项目虚拟环境放到 PATH 前面，避免误用 Anaconda 或系统 Python：

```powershell
$env:PATH = (Resolve-Path .\.venv\Scripts).Path + ';' + $env:PATH
.\.venv\Scripts\python.exe -m pre_commit run --all-files
```

常用子集测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_answerer.py tests/test_evaluator.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_external_eval.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_run_answer_eval_experiment.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_summarize_answer_eval_comparison.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_summarize_external_eval.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_generate_doubao_external_eval_cases.py -q
```

## API 列表

OpenAPI schema 仅暴露 `/api/v1/...`；旧 `/api/...` 路径保留为兼容别名。

| 接口 | 方法 | 用途 |
|---|---:|---|
| `/` | GET | Dashboard |
| `/health` | GET | 健康检查 |
| `/api/v1/documents/upload` | POST | 上传并索引 PDF |
| `/api/v1/documents` | GET | 列出已索引文档 |
| `/api/v1/documents/{doc_id}` | GET / DELETE | 查看或删除文档 |
| `/api/v1/search` | GET | 检索文档片段 |
| `/api/v1/answer` | POST | 生成带引用答案 |
| `/api/v1/evaluate/faithfulness` | POST | 评估答案证据支持情况 |
| `/api/v1/evaluate/retrieval` | POST | 评估检索用例 |
| `/api/v1/evaluate/answers` | POST | 批量评估内置 RAG 答案 |
| `/api/v1/evaluate/answers/export` | POST | 导出答案评测 CSV |
| `/api/v1/evaluate/external-answer` | POST | 评估单条外部 answer/evidence |
| `/api/v1/evaluate/external-answers` | POST | 批量评估外部模型或 Agent 输出 |
| `/api/v1/demo/external-eval` | GET | 返回内置外部评测 Demo 数据 |
| `/api/v1/experiments` | GET | 列出实验记录，支持 `limit` / `offset` / `include_total` |
| `/api/v1/experiments/{run_id}` | GET | 查看实验详情 |

## 提交与忽略规则

会提交：

- 应用代码
- 测试
- 可复用脚本
- 示例/评测数据集
- 文档与论文实验材料
- 最终 Markdown 报告示例

不会提交：

- `.env`
- `.venv/`
- `data/`
- Python/pytest 缓存
- `papers/*.pdf`
- `papers/` 下可重复生成的中间文件

具体清单见 `docs/commit_artifacts_checklist.md`。

## 注意事项

当前幻觉率是基于证据关键词支持的轻量代理指标，不等同于完整人工事实核查。用于论文或生产评估时，应扩大评测集、抽样人工复核，并明确报告指标局限性。
