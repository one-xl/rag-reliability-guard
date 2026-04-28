# RAG Reliability Guard

Evidence-based RAG evaluation and hallucination mitigation for local PDF knowledge bases.

This project is a FastAPI application for uploading PDF papers, chunking them into a local knowledge base, retrieving evidence with keyword/BM25 search, generating citation-bearing answers, and evaluating whether answers are grounded in retrieved evidence. It includes a guarded answer mode based on evidence support and relevance thresholds, plus scripts for reproducible baseline-vs-guarded experiments.

## Features

- PDF upload and local document indexing
- Keyword and BM25 retrieval over text chunks
- Extractive answer generation with citations
- Optional Doubao/Volcengine Ark OpenAI-compatible answer generation
- Faithfulness and hallucination proxy metrics
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

Python dependencies:

```text
fastapi
uvicorn[standard]
python-multipart
pypdf
httpx
pytest
```

## Setup

Clone the repository:

```powershell
git clone https://github.com/one-xl/rag-reliability-guard.git
cd rag-reliability-guard
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
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

The `.env` file is ignored by Git. Do not commit API keys.

## Run the App

Start the local API and dashboard:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Basic Usage

### 1. Upload PDFs

Use the dashboard at `http://127.0.0.1:8000/`, or call the API:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/documents/upload" `
  -F "file=@C:\path\to\paper.pdf"
```

Uploaded PDFs are parsed, chunked, and indexed under local `data/` directories.

### 2. Search Evidence

```powershell
curl.exe "http://127.0.0.1:8000/api/search?q=Self-RAG%20retrieve%20critique&method=bm25&top_k=3"
```

Supported retrieval methods:

- `keyword`
- `bm25`

### 3. Generate an Answer

Extractive answer with citations:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Self-RAG retrieve generate critique\",\"method\":\"bm25\",\"generator\":\"extractive\",\"top_k\":3}"
```

Guarded answer with hallucination suppression:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/answer" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Does this paper explain a quantum chip recipe?\",\"method\":\"bm25\",\"generator\":\"extractive\",\"top_k\":3,\"min_support_rate\":0.5,\"min_relevance_overlap\":0.35}"
```

Key guardrail parameters:

- `min_support_rate`: minimum evidence support rate required for a reliable answer
- `min_relevance_overlap`: minimum overlap between question content terms and retrieved evidence

If evidence is insufficient, the system refuses to answer instead of fabricating unsupported content.

### 4. Use Doubao Generation

After filling `.env`, set `generator` to `doubao`:

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

The app uses an OpenAI-compatible Doubao/Volcengine Ark endpoint configured by `.env`.

## Evaluation Workflow

### Build a Real-Paper Evaluation Dataset

After uploading/indexing the papers locally:

```powershell
.\.venv\Scripts\python.exe scripts\build_real_paper_eval_dataset.py --output datasets\real_paper_answer_eval_cases.json
```

This creates answerable and unanswerable evaluation cases. Answerable cases include expected document/chunk IDs from the current local index, so rebuild this dataset after re-uploading PDFs.

### Run Baseline vs Guarded Experiment

```powershell
.\.venv\Scripts\python.exe scripts\run_answer_eval_experiment.py --dataset datasets\real_paper_answer_eval_cases.json
```

The script runs:

- `baseline`: no support/relevance guard thresholds
- `guarded`: `min_support_rate=0.5`, `min_relevance_overlap=0.35`

It writes comparison files under `data/experiments/`:

```text
comparison_<timestamp>.json
comparison_<timestamp>.csv
```

### Generate a Markdown Report

```powershell
.\.venv\Scripts\python.exe scripts\summarize_answer_eval_comparison.py `
  --input data\experiments\comparison_<timestamp>.json `
  --output reports\answer_eval_report_real_papers.md
```

The report summarizes:

- dataset path
- baseline and guarded configuration
- citation hit rate
- refusal accuracy
- mean support rate
- mean hallucination rate
- conclusion and limitations

## Testing

Run the full test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
```

Expected current result:

```text
86 passed
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_answerer.py tests/test_evaluator.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_run_answer_eval_experiment.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_summarize_answer_eval_comparison.py -q
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
| `/api/experiments` | GET | List saved experiments |
| `/api/experiments/{run_id}` | GET | View experiment detail |

## What Is Committed vs Ignored

Committed:

- app code
- tests
- reusable scripts
- example/evaluation datasets
- thesis and workflow documentation
- final Markdown report examples

Ignored:

- `.env`
- `.venv/`
- `data/`
- Python/pytest caches
- large paper PDFs under `papers/*.pdf`
- reproducible intermediate files under `papers/`

See `docs/commit_artifacts_checklist.md` for the current commit checklist.

## Notes

This is a local research/prototype project. The current hallucination metric is a lightweight proxy based on evidence support, not a replacement for full human evaluation. For a thesis or production evaluation, expand the dataset, manually audit samples, and report limitations clearly.
