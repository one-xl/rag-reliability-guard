import json
import logging
from pathlib import Path

from fastapi import HTTPException


def load_demo_external_eval(path: Path, *, logger: logging.Logger) -> dict:
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
