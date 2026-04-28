import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response

from app.answerer import draft_answer
from app.bm25 import search_documents_bm25
from app.evaluator import answer_evaluation_to_csv, evaluate_answer_cases, evaluate_retrieval
from app.external_eval import evaluate_external_answer_case, evaluate_external_answer_cases
from app.faithfulness import check_answer_faithfulness
from app.llm_client import LLMConfigurationError, LLMRequestError
from app.pdf_loader import extract_text_from_pdf
from app.search import search_documents
from app.text_chunker import chunk_text

logger = logging.getLogger(__name__)

app = FastAPI(title="RAG 毕设 API", version="0.1.0")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"
EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "experiments"
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEMO_EXTERNAL_EVAL_PATH = (
    Path(__file__).resolve().parent.parent / "datasets" / "demo_external_eval_cases.json"
)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
PREVIEW_CHARS = 800
# 入库元数据用：偏大 chunk、适中 overlap，减少片段过碎
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def _safe_stem(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w\u4e00-\u9fff.\-]", "_", base, flags=re.UNICODE)
    return base[:180] if len(base) > 180 else base


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/demo/external-eval")
def api_demo_external_eval():
    """Return built-in external-eval demo JSON (read-only)."""
    path = DEMO_EXTERNAL_EVAL_PATH
    if not path.is_file():
        raise HTTPException(status_code=404, detail="内置评测 Demo 数据不可用")
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        logger.exception("读取内置外部评测 Demo 失败")
        raise HTTPException(
            status_code=503,
            detail="内置评测 Demo 数据不可用",
        ) from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=503, detail="内置评测 Demo 数据不可用")
    return data


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/search")
def api_search(
    q: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    method: str = Query("keyword", description="keyword=子串计分, bm25=Okapi BM25（分块为文档）"),
):
    """
    在已入库文档分块上检索。method=keyword 为与原先一致的子串计分；method=bm25 为经典 BM25。
    """
    if q is None or not q.strip():
        raise HTTPException(status_code=400, detail="查询 q 不能为空")
    if method not in ("keyword", "bm25"):
        raise HTTPException(status_code=400, detail="method 必须是 keyword 或 bm25")
    stripped = q.strip()
    if method == "bm25":
        results = search_documents_bm25(DOCUMENTS_DIR, stripped, top_k)
    else:
        results = search_documents(DOCUMENTS_DIR, stripped, top_k)
    return {
        "query": stripped,
        "top_k": top_k,
        "method": method,
        "results": results,
    }


@app.post("/api/evaluate/retrieval")
def api_evaluate_retrieval(
    payload: dict = Body(...),
    top_k: int | None = Query(None, ge=1, le=20),
):
    """Evaluate current retrieval results against small benchmark cases."""
    cases = payload.get("cases")
    body_top_k = payload.get("top_k", 5)
    effective_top_k = top_k if top_k is not None else body_top_k
    if not isinstance(effective_top_k, int) or not 1 <= effective_top_k <= 20:
        raise HTTPException(status_code=400, detail="top_k 必须在 1 到 20 之间")
    try:
        metrics = evaluate_retrieval(cases, DOCUMENTS_DIR, effective_top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"top_k": effective_top_k, **metrics}


def _persist_answer_experiment(evaluation: dict) -> tuple[str, dict[str, str]]:
    """Write evaluation JSON and CSV under EXPERIMENTS_DIR; return run_id and relative paths."""
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {"run_id": run_id, "created_at": created_at, **evaluation}
    json_path = EXPERIMENTS_DIR / f"{run_id}.json"
    csv_path = EXPERIMENTS_DIR / f"{run_id}.csv"
    json_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_text = answer_evaluation_to_csv(evaluation)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
    rel_json = f"data/experiments/{run_id}.json"
    rel_csv = f"data/experiments/{run_id}.csv"
    return run_id, {"json": rel_json, "csv": rel_csv}


@app.post("/api/evaluate/answers")
def api_evaluate_answers(payload: dict = Body(...)):
    """Batch-run draft_answer over benchmark cases for thesis experiments."""
    save = payload.get("save") is True
    evaluation = _evaluate_answers_payload(payload)
    if not save:
        return evaluation
    run_id, saved_paths = _persist_answer_experiment(evaluation)
    return {**evaluation, "run_id": run_id, "saved_paths": saved_paths}


@app.post("/api/evaluate/answers/export")
def api_evaluate_answers_export(payload: dict = Body(...)):
    """Export per-case answer evaluation rows as CSV for thesis tables."""
    evaluation = _evaluate_answers_payload(payload)
    csv_text = answer_evaluation_to_csv(evaluation)
    headers = {"Content-Disposition": 'attachment; filename="answer_evaluation.csv"'}
    return Response(content=csv_text, media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/api/evaluate/external-answer")
def api_evaluate_external_answer(payload: dict = Body(...)):
    """Evaluate one externally generated answer with externally supplied evidence."""
    min_support_rate = payload.get("min_support_rate")
    if min_support_rate is not None and not isinstance(min_support_rate, (int, float)):
        raise HTTPException(status_code=400, detail="min_support_rate must be a number")
    try:
        return evaluate_external_answer_case(
            payload,
            min_support_rate=float(min_support_rate) if min_support_rate is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/evaluate/external-answers")
def api_evaluate_external_answers(payload: dict = Body(...)):
    """Batch-evaluate external answer/evidence cases for model-agnostic RAG guardrails."""
    cases = payload.get("cases")
    min_support_rate = payload.get("min_support_rate")
    if not isinstance(cases, list):
        raise HTTPException(status_code=400, detail="cases must be a list")
    if min_support_rate is not None and not isinstance(min_support_rate, (int, float)):
        raise HTTPException(status_code=400, detail="min_support_rate must be a number")
    try:
        return evaluate_external_answer_cases(
            cases,
            min_support_rate=float(min_support_rate) if min_support_rate is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _evaluate_answers_payload(payload: dict) -> dict:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise HTTPException(status_code=400, detail="cases 必须是列表")

    top_k = payload.get("top_k", 5)
    if not isinstance(top_k, int) or not 1 <= top_k <= 20:
        raise HTTPException(status_code=400, detail="top_k 必须在 1 到 20 之间")

    method = payload.get("method", "keyword")
    if method not in ("keyword", "bm25"):
        raise HTTPException(status_code=400, detail="method 必须是 keyword 或 bm25")

    generator = payload.get("generator", "extractive")
    if generator not in ("extractive", "doubao"):
        raise HTTPException(status_code=400, detail="generator 必须是 extractive 或 doubao")

    min_support_rate = payload.get("min_support_rate")
    if min_support_rate is not None and not isinstance(min_support_rate, (int, float)):
        raise HTTPException(status_code=400, detail="min_support_rate 必须是数字")
    if isinstance(min_support_rate, (int, float)) and not 0.0 <= float(min_support_rate) <= 1.0:
        raise HTTPException(status_code=400, detail="min_support_rate 必须在 0 到 1 之间")

    min_relevance_overlap = payload.get("min_relevance_overlap")
    if min_relevance_overlap is not None and not isinstance(min_relevance_overlap, (int, float)):
        raise HTTPException(status_code=400, detail="min_relevance_overlap 必须是数字")
    if (
        isinstance(min_relevance_overlap, (int, float))
        and not 0.0 <= float(min_relevance_overlap) <= 1.0
    ):
        raise HTTPException(status_code=400, detail="min_relevance_overlap 必须在 0 到 1 之间")

    try:
        return evaluate_answer_cases(
            cases,
            DOCUMENTS_DIR,
            method=method,
            generator=generator,
            top_k=top_k,
            min_support_rate=float(min_support_rate) if min_support_rate is not None else None,
            min_relevance_overlap=(
                float(min_relevance_overlap) if min_relevance_overlap is not None else None
            ),
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/experiments")
def list_experiments():
    """List persisted answer-evaluation runs (newest first by created_at)."""
    if not EXPERIMENTS_DIR.is_dir():
        return []
    summaries: list[dict] = []
    for path in EXPERIMENTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_id = data.get("run_id")
        if not isinstance(run_id, str):
            continue
        agg = data.get("aggregate")
        if not isinstance(agg, dict):
            continue
        summaries.append(
            {
                "run_id": run_id,
                "created_at": data.get("created_at"),
                "method": data.get("method"),
                "generator": data.get("generator"),
                "top_k": data.get("top_k"),
                "total": agg.get("total"),
                "mean_support_rate": agg.get("mean_support_rate"),
                "mean_hallucination_rate": agg.get("mean_hallucination_rate"),
            }
        )

    def _sort_key(item: dict):
        ts = item.get("created_at")
        return ts if isinstance(ts, str) else ""

    summaries.sort(key=_sort_key, reverse=True)
    return summaries


@app.get("/api/experiments/{run_id}")
def get_experiment(run_id: str):
    try:
        uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到该实验") from exc
    path = EXPERIMENTS_DIR / f"{run_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="未找到该实验")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("读取实验 JSON 失败")
        raise HTTPException(
            status_code=500,
            detail="实验数据已损坏，无法读取",
        ) from exc


@app.post("/api/answer")
def api_answer(payload: dict = Body(...)):
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=400, detail="question 不能为空")

    top_k = payload.get("top_k", 5)
    if not isinstance(top_k, int) or not 1 <= top_k <= 20:
        raise HTTPException(status_code=400, detail="top_k 必须在 1 到 20 之间")

    method = payload.get("method", "keyword")
    if method not in ("keyword", "bm25"):
        raise HTTPException(status_code=400, detail="method 必须是 keyword 或 bm25")

    generator = payload.get("generator", "extractive")
    if generator not in ("extractive", "doubao"):
        raise HTTPException(status_code=400, detail="generator 必须是 extractive 或 doubao")

    min_support_rate = payload.get("min_support_rate")
    if min_support_rate is not None and not isinstance(min_support_rate, (int, float)):
        raise HTTPException(status_code=400, detail="min_support_rate 必须是数字")

    min_relevance_overlap = payload.get("min_relevance_overlap")
    if min_relevance_overlap is not None and not isinstance(min_relevance_overlap, (int, float)):
        raise HTTPException(status_code=400, detail="min_relevance_overlap 必须是数字")

    try:
        return draft_answer(
            question,
            DOCUMENTS_DIR,
            top_k=top_k,
            method=method,
            generator=generator,
            min_support_rate=min_support_rate,
            min_relevance_overlap=min_relevance_overlap,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/evaluate/faithfulness")
def api_evaluate_faithfulness(payload: dict = Body(...)):
    answer = payload.get("answer")
    citations = payload.get("citations")
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(status_code=400, detail="answer 不能为空")
    if not isinstance(citations, list):
        raise HTTPException(status_code=400, detail="citations 必须是列表")
    return check_answer_faithfulness(answer, citations)


@app.post("/api/documents/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    接收单个 PDF 文件，保存到 data/uploads，并返回页数、字数与正文预览。
    以原始文件名为准：须以 .pdf 结尾（不校验 Content-Type）。
    """
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    chunks: list[bytes] = []
    total_bytes = 0
    while chunk := await file.read(UPLOAD_CHUNK_BYTES):
        total_bytes += len(chunk)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"文件过大，上限 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
            )
        chunks.append(chunk)

    raw = b"".join(chunks)
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="空文件")

    try:
        text, page_count = extract_text_from_pdf(raw)
    except Exception:
        logger.exception("PDF 解析失败")
        raise HTTPException(
            status_code=422,
            detail="无法解析该 PDF，请确认文件未损坏且为有效 PDF",
        ) from None

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    stem = _safe_stem(filename)
    saved_name = f"{doc_id}_{stem}"
    if not saved_name.lower().endswith(".pdf"):
        saved_name += ".pdf"
    out_path = DATA_DIR / saved_name
    out_path.write_bytes(raw)

    preview = text[:PREVIEW_CHARS] if text else ""
    piece_texts = chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    chunk_entries = [
        {"index": i, "text": piece, "char_count": len(piece)}
        for i, piece in enumerate(piece_texts)
    ]
    metadata = {
        "id": doc_id,
        "original_filename": filename,
        "saved_as": saved_name,
        "page_count": page_count,
        "char_count": len(text),
        "chunk_count": len(chunk_entries),
        "text_preview": preview,
        "chunks": chunk_entries,
    }
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DOCUMENTS_DIR / f"{doc_id}.json"
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "id": doc_id,
        "saved_as": saved_name,
        "original_filename": filename,
        "page_count": page_count,
        "char_count": len(text),
        "text_preview": preview,
    }


def _load_doc_metadata_path(doc_id: str) -> Path:
    try:
        uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到该文档") from exc
    return DOCUMENTS_DIR / f"{doc_id}.json"


@app.get("/api/documents")
def list_documents():
    if not DOCUMENTS_DIR.is_dir():
        return []
    summaries: list[dict] = []
    for path in sorted(DOCUMENTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data.pop("chunks", None)
        summaries.append(data)
    return summaries


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    path = _load_doc_metadata_path(doc_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="未找到该文档")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("读取文档元数据失败")
        raise HTTPException(
            status_code=500,
            detail="文档元数据已损坏，无法读取",
        ) from exc
