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
app/services/                Service layer for documents, experiments, request parsing
app/static/index.html        Browser dashboard shell
app/static/dashboard.css     Dashboard styles
app/static/dashboard.js      Dashboard interactions
datasets/                     Reproducible evaluation datasets
docs/                         Workflow notes and thesis-ready experiment writing
reports/                      Final Markdown experiment reports
scripts/                      Experiment and report automation scripts
tests/                        Pytest test suite
```

Local runtime data is written under `data/` and is intentionally ignored by Git.

For a reproducible Chinese demo flow, see [docs/demo_workflow.md](docs/demo_workflow.md). It covers the built-in PDF RAG baseline/guarded comparison, external model/Agent evaluation, dashboard visualization, and report generation.

## Quick demo (external evaluation)

No PDF upload required. Use the bundled demo dataset [datasets/demo_external_eval_cases.json](datasets/demo_external_eval_cases.json) for a fixed multi-provider `answer + evidence` batch and Markdown reporting.

**Note:** In this demo file, `provider` / `model` / `run_id` are **illustrative labels** to exercise `aggregate.by_model` and reporting—they do **not** imply a real multi-model sweep or any meaningful model ranking. For a live Doubao-generated dataset, see **Live Doubao external eval data** below.

1. Start the app (after `pip install -r requirements.txt`):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

2. Dashboard: open `http://127.0.0.1:8000/` and paste the demo JSON into the external batch evaluation panel.

3. CLI evaluation:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset datasets\demo_external_eval_cases.json
```

4. Generate a Markdown report (defaults to the newest `data/experiments/external_eval_*.json` when `--input` is omitted):

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py --output reports\external_eval_report_demo.md
```

### Live Doubao external eval data (needs `.env`, billed API usage)

After setting `DOUBAO_API_KEY` and `DOUBAO_MODEL`, you can take a demo scaffold (question / evidence / answerable-only), generate real Doubao answers, evaluate, then summarize:

```powershell
.\.venv\Scripts\python.exe scripts\generate_doubao_external_eval_cases.py
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset data\experiments\doubao_external_eval_cases_<timestamp>.json
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py --input data\experiments\external_eval_<timestamp>.json --output reports\external_eval_report_doubao_live.md
```

`generate_doubao_external_eval_cases.py` defaults to reading `datasets\demo_external_eval_cases.json` and writing `data\experiments\doubao_external_eval_cases_<timestamp>.json`. Use `--source`, `--output`, and `--run-id` as needed. Point `--dataset` at the JSON written in step 1; set `--input` on the summarizer to the `external_eval_*.json` from step 2 (or omit `--input` to pick the newest `external_eval_*.json` under `data\experiments`).

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

Use `/api/v1/...` for new integrations. The older `/api/...` paths are still available as compatibility aliases.

Upload a PDF:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/documents/upload" `
  -F "file=@C:\path\to\paper.pdf"
```

Search evidence:

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/search?q=Self-RAG%20retrieve%20critique&method=bm25&top_k=3"
```

Generate a guarded answer:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Does this paper explain a quantum chip recipe?\",\"method\":\"bm25\",\"generator\":\"extractive\",\"top_k\":3,\"min_support_rate\":0.5,\"min_relevance_overlap\":0.35}"
```

## External Answer/Evidence Evaluation

Use this path when the answer was produced outside this app, for example by another RAG service, an agent workflow, a search pipeline, or a different model provider.

**Multi-model comparison:** each case may include optional metadata `provider`, `model`, and `run_id` (strings). If `provider` or `model` is omitted, the evaluator fills them with `"unknown"` in per-row output; missing `run_id` becomes JSON `null`. Batch responses add `aggregate.by_model`, an object keyed by `"provider/model"` with per-model totals, answerable/unanswerable counts, `refusal_accuracy`, `over_refusal_rate`, `mean_support_rate`, and `mean_hallucination_rate`.

**Important:** With fixed samples such as `datasets/demo_external_eval_cases.json`, those fields are usually **placeholder labels** for the evaluator UI and `by_model` tables. The batch endpoint **does not** call remote LLMs from those labels—it only scores the `answer` and `evidence` you submit. Labels are not trustworthy for cross-model ranking unless each `answer` was actually produced under that provider/model (for example after `scripts/generate_doubao_external_eval_cases.py`).

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

### Multi-model external evaluation Markdown report

After `scripts/evaluate_external_answers.py` writes `data/experiments/external_eval_<timestamp>.json`, summarize it into a Chinese Markdown report (experiment time, dataset path, overall aggregate table, per-model `by_model` table, models with highest `refusal_accuracy`, highest `over_refusal_rate`, lowest `mean_hallucination_rate`, and a short conclusion):

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py
```

By default, the newest `external_eval_*.json` under `data/experiments/` (lexicographic name order) is used, and the report goes to `reports/external_eval_report_<timestamp>.md`. Pass explicit paths with `--input` / `--output`, or `--experiments-dir` to change the scan folder when `--input` is omitted.

```powershell
.\.venv\Scripts\python.exe scripts\summarize_external_eval.py `
  --input data\experiments\external_eval_<timestamp>.json `
  --output reports\external_eval_report_custom.md
```

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
135 passed
```

Optional development tooling:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m mypy app scripts
```

To run pre-commit, this repo uses local hooks. On Windows, put the project virtualenv first on PATH so hooks do not pick Anaconda or a system Python:

```powershell
$env:PATH = (Resolve-Path .\.venv\Scripts).Path + ';' + $env:PATH
.\.venv\Scripts\python.exe -m pre_commit run --all-files
```

## Important API Endpoints

The OpenAPI schema exposes `/api/v1/...`; legacy `/api/...` paths remain as compatibility aliases.

| Endpoint | Method | Purpose |
|---|---:|---|
| `/` | GET | Dashboard |
| `/health` | GET | Health check |
| `/api/v1/documents/upload` | POST | Upload and index a PDF |
| `/api/v1/documents` | GET | List indexed documents |
| `/api/v1/documents/{doc_id}` | GET / DELETE | View or delete a document |
| `/api/v1/search` | GET | Search indexed chunks |
| `/api/v1/answer` | POST | Generate citation-bearing answer |
| `/api/v1/evaluate/faithfulness` | POST | Evaluate answer faithfulness |
| `/api/v1/evaluate/retrieval` | POST | Evaluate retrieval cases |
| `/api/v1/evaluate/answers` | POST | Batch answer reliability evaluation |
| `/api/v1/evaluate/answers/export` | POST | Export answer evaluation CSV |
| `/api/v1/evaluate/external-answer` | POST | Evaluate one external answer/evidence case |
| `/api/v1/evaluate/external-answers` | POST | Batch-evaluate external model or agent outputs |
| `/api/v1/demo/external-eval` | GET | Return the built-in external-eval demo dataset |
| `/api/v1/experiments` | GET | List saved experiments with `limit` / `offset` / `include_total` |
| `/api/v1/experiments/{run_id}` | GET | View experiment detail |

## Notes

This is a local research/prototype project. The current hallucination metric is a lightweight proxy based on evidence support, not a replacement for full human evaluation. For a thesis or production evaluation, expand the dataset, manually audit samples, and report limitations clearly.
