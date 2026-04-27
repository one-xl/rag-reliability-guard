"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Load simple KEY=VALUE pairs without overriding existing environment values."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class DoubaoSettings:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float

    @property
    def is_configured(self) -> bool:
        placeholders = {
            "",
            "your_ark_api_key_here",
            "your_doubao_endpoint_or_model_id_here",
        }
        return self.api_key not in placeholders and self.model not in placeholders


def get_doubao_settings() -> DoubaoSettings:
    load_dotenv()
    timeout_raw = os.getenv("DOUBAO_TIMEOUT_SECONDS", "60")
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 60.0
    return DoubaoSettings(
        api_key=os.getenv("DOUBAO_API_KEY", ""),
        base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        model=os.getenv("DOUBAO_MODEL", ""),
        timeout_seconds=timeout_seconds,
    )
