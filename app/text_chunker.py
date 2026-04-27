"""按固定字符长度切分文本，支持重叠。"""


def chunk_text(text: str, *, chunk_size: int, overlap: int = 0) -> list[str]:
    """
    将 `text` 切为连续片段；相邻片段在末尾与开头可重叠 `overlap` 个字符。

    空字符串返回 []. 每个片段长度至多为 `chunk_size`；最后一段可更短。

    参数
    ----
    chunk_size
        每段最大字符数，必须为正整数。
    overlap
        相邻窗口重叠的字符数，须满足 ``0 <= overlap < chunk_size``。
    """
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    step = chunk_size - overlap
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= n:
            break
        start += step
    return chunks
