import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.answerer import draft_answer
from app.bm25 import search_documents_bm25
from app.config import PROJECT_ROOT
from app.dense_retrieval import search_documents_dense, search_documents_hybrid
from app.evaluator import answer_evaluation_to_csv, evaluate_answer_cases, evaluate_retrieval
from app.external_eval import evaluate_external_answer_case, evaluate_external_answer_cases
from app.faithfulness import check_answer_faithfulness
from app.llm_client import LLMConfigurationError, LLMRequestError
from app.logging_config import configure_logging
from app.pdf_loader import extract_text_from_pdf_stream
from app.schemas import (
    AnswerEvaluationRequest,
    AnswerRequest,
    ExternalAnswerBatchRequest,
    ExternalAnswerRequest,
    FaithfulnessRequest,
    RetrievalEvaluationRequest,
)
from app.search import search_documents
from app.services.demo_data import load_demo_external_eval
from app.services.documents import (
    delete_document_files,
    get_document_metadata,
    list_document_summaries,
    process_pdf_upload,
)
from app.services.evaluation import evaluate_answers_payload
from app.services.experiments import (
    get_answer_experiment,
    list_answer_experiment_page,
    list_answer_experiments,
    persist_answer_experiment,
)

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="RAG 毕设 API", version="0.1.0")

DATA_DIR = PROJECT_ROOT / "data" / "uploads"
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEMO_EXTERNAL_EVAL_PATH = PROJECT_ROOT / "datasets" / "demo_external_eval_cases.json"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
PREVIEW_CHARS = 800
# 入库元数据用：偏大 chunk、适中 overlap，减少片段过碎
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def versioned_api_route(path: str, *, methods: list[str], **kwargs):
    """Register /api/v1 routes while keeping /api as a compatibility alias."""

    def decorator(func):
        app.api_route(f"/api{path}", methods=methods, include_in_schema=False, **kwargs)(func)
        app.api_route(f"/api/v1{path}", methods=methods, **kwargs)(func)
        return func

    return decorator


def api_get(path: str, **kwargs):
    return versioned_api_route(path, methods=["GET"], **kwargs)


def api_post(path: str, **kwargs):
    return versioned_api_route(path, methods=["POST"], **kwargs)


def api_delete(path: str, **kwargs):
    return versioned_api_route(path, methods=["DELETE"], **kwargs)



@app.get("/health")
def health():
    return {"status": "ok"}


@api_get("/demo/external-eval")
def api_demo_external_eval():
    """Return built-in external-eval demo JSON (read-only)."""
    return load_demo_external_eval(DEMO_EXTERNAL_EVAL_PATH, logger=logger)


@app.get("/")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


@api_get("/search")
def api_search(
    q: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    method: str = Query("keyword", description="keyword=子串计分, bm25=Okapi BM25, dense=向量检索, hybrid=BM25+向量混合"),
):
    """
    在已入库文档分块上检索。method=keyword 为与原先一致的子串计分；method=bm25 为经典 BM25；
    method=dense 为基于 sentence-transformers 的向量检索；method=hybrid 为 BM25 + 向量混合检索。
    """
    if q is None or not q.strip():
        raise HTTPException(status_code=400, detail="查询 q 不能为空")
    if method not in ("keyword", "bm25", "dense", "hybrid"):
        raise HTTPException(status_code=400, detail="method 必须是 keyword、bm25、dense 或 hybrid")
    stripped = q.strip()
    if method == "bm25":
        results = search_documents_bm25(DOCUMENTS_DIR, stripped, top_k)
    elif method == "dense":
        results = search_documents_dense(DOCUMENTS_DIR, stripped, top_k)
    elif method == "hybrid":
        results = search_documents_hybrid(DOCUMENTS_DIR, stripped, top_k)
    else:
        results = search_documents(DOCUMENTS_DIR, stripped, top_k)
    return {
        "query": stripped,
        "top_k": top_k,
        "method": method,
        "results": results,
    }


@api_post("/evaluate/retrieval")
def api_evaluate_retrieval(
    request: RetrievalEvaluationRequest,
    top_k: int | None = Query(None, ge=1, le=20),
):
    """Evaluate current retrieval results against small benchmark cases."""
    effective_top_k = top_k if top_k is not None else request.top_k
    try:
        metrics = evaluate_retrieval(request.cases, DOCUMENTS_DIR, effective_top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"top_k": effective_top_k, **metrics}


@api_post("/evaluate/answers")
def api_evaluate_answers(request: AnswerEvaluationRequest):
    """Batch-run draft_answer over benchmark cases for thesis experiments."""
    evaluation = evaluate_answers_payload(request, DOCUMENTS_DIR, evaluate_answer_cases)
    if not request.save:
        return evaluation
    run_id, saved_paths = persist_answer_experiment(evaluation, EXPERIMENTS_DIR)
    return {**evaluation, "run_id": run_id, "saved_paths": saved_paths}


@api_post("/evaluate/answers/export")
def api_evaluate_answers_export(request: AnswerEvaluationRequest):
    """Export per-case answer evaluation rows as CSV for thesis tables."""
    evaluation = evaluate_answers_payload(request, DOCUMENTS_DIR, evaluate_answer_cases)
    csv_text = answer_evaluation_to_csv(evaluation)
    headers = {"Content-Disposition": 'attachment; filename="answer_evaluation.csv"'}
    return Response(content=csv_text, media_type="text/csv; charset=utf-8", headers=headers)


@api_post("/evaluate/external-answer")
def api_evaluate_external_answer(request: ExternalAnswerRequest):
    """Evaluate one externally generated answer with externally supplied evidence."""
    case = request.model_dump(exclude={"min_support_rate"}, exclude_none=True)
    try:
        return evaluate_external_answer_case(
            case,
            min_support_rate=request.min_support_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_post("/evaluate/external-answers")
def api_evaluate_external_answers(request: ExternalAnswerBatchRequest):
    """Batch-evaluate external answer/evidence cases for model-agnostic RAG guardrails."""
    try:
        return evaluate_external_answer_cases(
            request.cases,
            min_support_rate=request.min_support_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_get("/experiments")
def list_experiments(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
):
    """List persisted answer-evaluation runs (newest first by created_at)."""
    if include_total:
        return list_answer_experiment_page(EXPERIMENTS_DIR, limit=limit, offset=offset)
    return list_answer_experiments(EXPERIMENTS_DIR, limit=limit, offset=offset)


@api_get("/experiments/{run_id}")
def get_experiment(run_id: str):
    return get_answer_experiment(run_id, EXPERIMENTS_DIR, logger=logger)


@api_post("/answer")
def api_answer(request: AnswerRequest):
    try:
        return draft_answer(
            request.question,
            DOCUMENTS_DIR,
            top_k=request.top_k,
            method=request.method,
            generator=request.generator,
            min_support_rate=request.min_support_rate,
            min_relevance_overlap=request.min_relevance_overlap,
            fallback_to_extractive=request.fallback_to_extractive,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_post("/evaluate/faithfulness")
def api_evaluate_faithfulness(request: FaithfulnessRequest):
    return check_answer_faithfulness(request.answer, request.citations)


@api_post("/documents/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    接收单个 PDF 文件，保存到 data/uploads，并返回页数、字数与正文预览。
    以原始文件名为准：须以 .pdf 结尾（不校验 Content-Type）。
    """
    return await process_pdf_upload(
        file,
        data_dir=DATA_DIR,
        documents_dir=DOCUMENTS_DIR,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        upload_chunk_bytes=UPLOAD_CHUNK_BYTES,
        preview_chars=PREVIEW_CHARS,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        extract_text=extract_text_from_pdf_stream,
        logger=logger,
    )


@api_get("/documents")
def list_documents():
    return list_document_summaries(DOCUMENTS_DIR)


@api_get("/documents/{doc_id}")
def get_document(doc_id: str):
    return get_document_metadata(DOCUMENTS_DIR, doc_id, logger=logger)


@api_delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    return delete_document_files(DOCUMENTS_DIR, DATA_DIR, doc_id, logger=logger)
