# RAG Reliability Guard

[中文](README.md)

Model-agnostic RAG/Agent reliability evaluation and hallucination mitigation toolkit.

This project evaluates whether answers from RAG systems, agents, or external LLM pipelines are grounded in supplied evidence. It can run as a local PDF RAG application, but its guardrail layer is designed to also evaluate externally generated `answer + evidence` records from any model or retrieval stack. It reports support rate, hallucination risk, refusal accuracy, over-refusal, and reliability decisions.

## Features

- PDF upload and local document indexing
- Keyword and BM25 retrieval over text chunks
- Extractive answer generation with citations
- Optional Doubao/Volcengine Ark OpenAI-compatible answer generation
- Faithfulness and hallucination proxy metrics
- Model-agnostic external answer/evidence evaluation
- Over-refusal tracking for answerable questions
- Batch answer evaluation with JSON and CSV export
- Experiment history and Markdown report generation
- Real-paper evaluation dataset and thesis experiment section examples

## Project Structure

```text
app/                         FastAPI app, retrieval, answer generation, evaluation logic
app/static/index.html         Browser dashboard
datasets/                     Reproducible evaluation datasets
docs/                         Workflow notes and thesis-ready experiment writing
reports/                      Final Markdown experiment reports
scripts/                      Experiment and report automation scripts
tests/                        Pytest test suite
```

Local runtime data is written under `data/` and is intentionally ignored by Git.

## Requirements

- Python 3.12 recommended
- Windows PowerShell examples are shown below, but the app also works on macOS/Linux with equivalent shell commands

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional Doubao configuration:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```text
DOUBAO_API_KEY=your_ark_api_key_here
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=your_doubao_endpoint_or_model_id_here
DOUBAO_TIMEOUT_SECONDS=60
```

## Run the App

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

## Basic Usage

Upload a PDF:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/documents/upload" `
  -F "file=@C:\path\to\paper.pdf"
```

Search evidence:

```powershell
curl.exe "http://127.0.0.1:8000/api/search?q=Self-RAG%20retrieve%20critique&method=bm25&top_k=3"
```

Generate a guarded answer:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Does this paper explain a quantum chip recipe?\",\"method\":\"bm25\",\"generator\":\"extractive\",\"top_k\":3,\"min_support_rate\":0.5,\"min_relevance_overlap\":0.35}"
```

## External Answer/Evidence Evaluation

Use this path when the answer was produced outside this app, for example by another RAG service, an agent workflow, a search pipeline, or a different model provider.

**Multi-model comparison:** each case may include optional metadata `provider`, `model`, and `run_id` (strings). If `provider` or `model` is omitted, the evaluator fills them with `"unknown"` in per-row output; missing `run_id` becomes JSON `null`. Batch responses add `aggregate.by_model`, an object keyed by `"provider/model"` with per-model totals, answerable/unanswerable counts, `refusal_accuracy`, `over_refusal_rate`, `mean_support_rate`, and `mean_hallucination_rate`. These fields are labels only—no remote LLM is invoked.

Example case fields:

```json
{
  "case_id": "supported-rag-answer",
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "run_id": "exp-2026-001",
  "question": "What does RAG use before generating an answer?",
  "answerable": true,
  "answer": "RAG uses retrieved evidence before generating an answer.",
  "evidence": [{ "evidence_id": "doc-1#chunk-1", "source": "example.md", "text": "..." }]
}
```

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset datasets\sample_external_answer_eval_cases.json
```

The saved file under `data/experiments/external_eval_<timestamp>.json` mirrors the API payload, including `aggregate.by_model`.

Metrics include:

- `support_rate`
- `hallucination_rate`
- `refusal_accuracy`
- `over_refusal_rate`
- `reliable`
- per-model rollups in `aggregate.by_model` for batch evaluation

## Experiment Workflow

```powershell
.\.venv\Scripts\python.exe scripts\build_real_paper_eval_dataset.py --output datasets\real_paper_answer_eval_cases.json
.\.venv\Scripts\python.exe scripts\run_answer_eval_experiment.py --dataset datasets\real_paper_answer_eval_cases.json
.\.venv\Scripts\python.exe scripts\summarize_answer_eval_comparison.py --input data\experiments\comparison_<timestamp>.json --output reports\answer_eval_report_real_papers.md
```

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
```

Expected current result:

```text
98 passed
```

## Important API Endpoints

| Endpoint | Method | Purpose |
|---|---:|---|
| `/` | GET | Dashboard |
| `/health` | GET | Health check |
| `/api/documents/upload` | POST | Upload and index a PDF |
| `/api/documents` | GET | List indexed documents |
| `/api/search` | GET | Search indexed chunks |
| `/api/answer` | POST | Generate citation-bearing answer |
| `/api/evaluate/faithfulness` | POST | Evaluate answer faithfulness |
| `/api/evaluate/retrieval` | POST | Evaluate retrieval cases |
| `/api/evaluate/answers` | POST | Batch answer reliability evaluation |
| `/api/evaluate/answers/export` | POST | Export answer evaluation CSV |
| `/api/evaluate/external-answer` | POST | Evaluate one external answer/evidence case |
| `/api/evaluate/external-answers` | POST | Batch-evaluate external model or agent outputs |
| `/api/experiments` | GET | List saved experiments |
| `/api/experiments/{run_id}` | GET | View experiment detail |

## Notes

This is a local research/prototype project. The current hallucination metric is a lightweight proxy based on evidence support, not a replacement for full human evaluation. For a thesis or production evaluation, expand the dataset, manually audit samples, and report limitations clearly.
