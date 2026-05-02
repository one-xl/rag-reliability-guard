"""从 PDF 字节流提取纯文本，供知识库入库前使用。"""

from io import BytesIO
from typing import BinaryIO

from pypdf import PdfReader


def extract_text_from_pdf(data: bytes) -> tuple[str, int]:
    """
    返回 (全文拼接文本, 页数)。提取失败或空页时仍返回页数，文本可能为空字符串。
    """
    return extract_text_from_pdf_stream(BytesIO(data))


def extract_text_from_pdf_stream(stream: BinaryIO) -> tuple[str, int]:
    """Extract text from a readable binary PDF stream."""
    reader = PdfReader(stream)
    page_count = len(reader.pages)
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n\n".join(parts), page_count
