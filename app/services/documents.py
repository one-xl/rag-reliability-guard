import hashlib
import json
import logging
import re
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

from fastapi import HTTPException, UploadFile

from app.document_index import refresh_document_index
from app.text_chunker import chunk_text


def safe_stem(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w\u4e00-\u9fff.\-]", "_", base, flags=re.UNICODE)
    return base[:180] if len(base) > 180 else base


def find_document_by_sha256(documents_dir: Path, file_sha256: str) -> dict | None:
    if not documents_dir.is_dir():
        return None
    for path in sorted(documents_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("sha256") == file_sha256:
            return data
    return None


def upload_summary(metadata: dict, *, duplicate: bool = False) -> dict:
    return {
        "id": metadata["id"],
        "saved_as": metadata.get("saved_as"),
        "original_filename": metadata.get("original_filename"),
        "page_count": metadata.get("page_count"),
        "char_count": metadata.get("char_count"),
        "text_preview": metadata.get("text_preview", ""),
        "duplicate": duplicate,
    }


async def process_pdf_upload(
    file: UploadFile,
    *,
    data_dir: Path,
    documents_dir: Path,
    max_upload_bytes: int,
    upload_chunk_bytes: int,
    preview_chars: int,
    chunk_size: int,
    chunk_overlap: int,
    extract_text: Callable[[BinaryIO], tuple[str, int]],
    logger: logging.Logger,
) -> dict:
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    total_bytes = 0
    hasher = hashlib.sha256()
    with tempfile.SpooledTemporaryFile(max_size=max_upload_bytes, mode="w+b") as upload_buffer:
        while chunk := await file.read(upload_chunk_bytes):
            total_bytes += len(chunk)
            if total_bytes > max_upload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大，上限 {max_upload_bytes // (1024 * 1024)} MB",
                )
            hasher.update(chunk)
            upload_buffer.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="空文件")

        upload_buffer.seek(0)
        if upload_buffer.read(5) != b"%PDF-":
            raise HTTPException(
                status_code=422,
                detail="无法解析该 PDF，请确认文件未损坏且为有效 PDF",
            )
        file_sha256 = hasher.hexdigest()
        existing = find_document_by_sha256(documents_dir, file_sha256)
        if existing is not None:
            return upload_summary(existing, duplicate=True)

        upload_buffer.seek(0)
        try:
            text, page_count = extract_text(cast(BinaryIO, upload_buffer))
        except Exception:
            logger.exception("PDF 解析失败")
            raise HTTPException(
                status_code=422,
                detail="无法解析该 PDF，请确认文件未损坏且为有效 PDF",
            ) from None

        data_dir.mkdir(parents=True, exist_ok=True)
        doc_id = str(uuid.uuid4())
        stem = safe_stem(filename)
        saved_name = f"{doc_id}_{stem}"
        if not saved_name.lower().endswith(".pdf"):
            saved_name += ".pdf"
        out_path = data_dir / saved_name
        upload_buffer.seek(0)
        with out_path.open("wb") as out_file:
            shutil.copyfileobj(upload_buffer, out_file)

    preview = text[:preview_chars] if text else ""
    piece_texts = chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
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
        "sha256": file_sha256,
        "chunks": chunk_entries,
    }
    documents_dir.mkdir(parents=True, exist_ok=True)
    meta_path = documents_dir / f"{doc_id}.json"
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    refresh_document_index(documents_dir)

    return upload_summary(metadata, duplicate=False)


def load_doc_metadata_path(documents_dir: Path, doc_id: str) -> Path:
    try:
        uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到该文档") from exc
    return documents_dir / f"{doc_id}.json"


def list_document_summaries(documents_dir: Path) -> list[dict]:
    if not documents_dir.is_dir():
        return []
    summaries: list[dict] = []
    for path in sorted(documents_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data.pop("chunks", None)
        summaries.append(data)
    return summaries


def get_document_metadata(documents_dir: Path, doc_id: str, *, logger: logging.Logger) -> dict:
    path = load_doc_metadata_path(documents_dir, doc_id)
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


def delete_document_files(
    documents_dir: Path,
    data_dir: Path,
    doc_id: str,
    *,
    logger: logging.Logger,
) -> dict:
    path = load_doc_metadata_path(documents_dir, doc_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="未找到该文档")
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("读取文档元数据失败")
        raise HTTPException(
            status_code=500,
            detail="文档元数据已损坏，无法读取",
        ) from exc

    saved_as = metadata.get("saved_as")
    upload_path = data_dir / saved_as if isinstance(saved_as, str) else None
    try:
        path.unlink()
        if upload_path is not None and upload_path.parent == data_dir and upload_path.is_file():
            upload_path.unlink()
    except OSError as exc:
        logger.exception("删除文档失败")
        raise HTTPException(status_code=500, detail="删除文档失败") from exc

    refresh_document_index(documents_dir)
    return {"deleted": True, "id": doc_id}
