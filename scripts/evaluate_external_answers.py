"""Run model-agnostic external answer/evidence evaluation via the local API."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DATASET = Path("datasets/sample_external_answer_eval_cases.json")
DEFAULT_OUTPUT_DIR = Path("data/experiments")


def load_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"dataset is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("dataset must be a JSON object")
    if not isinstance(data.get("cases"), list):
        raise SystemExit("dataset must contain a cases list")
    return data


def run_external_evaluation(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/evaluate/external-answers"
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"external evaluation failed: {response.status_code} {response.text}"
        ) from exc
    result = response.json()
    if not isinstance(result, dict):
        raise SystemExit("external evaluation response must be a JSON object")
    return result


def write_result(
    result: dict[str, Any],
    *,
    dataset_path: Path,
    output_dir: Path,
    timestamp: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"external_eval_{ts}.json"
    record = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        **result,
    }
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate externally generated answers against supplied evidence."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    payload = load_payload(args.dataset)
    result = run_external_evaluation(args.base_url, payload)
    output_path = write_result(result, dataset_path=args.dataset, output_dir=args.output_dir)
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
