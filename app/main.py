import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse

from app.evaluator import evaluate_retrieval
from app.pdf_loader import extract_text_from_pdf
from app.search import search_documents
from app.text_chunker import chunk_text

logger = logging.getLogger(__name__)

app = FastAPI(title="RAG 毕设 API", version="0.1.0")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"
STATIC_DIR = Path(__file__).resolve().parent / "static"
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


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/search")
def api_search(
    q: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
):
    """按关键词在已入库文档分块正文中检索（大小写不敏感，确定性排序）。"""
    if q is None or not q.strip():
        raise HTTPException(status_code=400, detail="查询 q 不能为空")
    stripped = q.strip()
    results = search_documents(DOCUMENTS_DIR, stripped, top_k)
    return {"query": stripped, "top_k": top_k, "results": results}


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
