"""Run baseline-vs-guarded answer evaluation against the local FastAPI app."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DATASET = Path("datasets/sample_answer_eval_cases.json")
DEFAULT_OUTPUT_DIR = Path("data/experiments")
AGGREGATE_FIELDS = [
    "name",
    "method",
    "generator",
    "top_k",
    "min_support_rate",
    "min_relevance_overlap",
    "total",
    "answerable_total",
    "answerable_hits",
    "citation_hit_rate",
    "unanswerable_total",
    "refusal_correct_count",
    "refusal_accuracy",
    "mean_support_rate",
    "mean_hallucination_rate",
]


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"dataset is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("dataset must be a JSON object accepted by /api/evaluate/answers")
    if not isinstance(data.get("cases"), list):
        raise SystemExit("dataset must contain a cases list")
    return data


def _baseline_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("min_support_rate", None)
    out.pop("min_relevance_overlap", None)
    out.pop("save", None)
    return out


def _guarded_payload(
    payload: dict[str, Any],
    *,
    min_support_rate: float,
    min_relevance_overlap: float,
) -> dict[str, Any]:
    out = dict(payload)
    out["min_support_rate"] = min_support_rate
    out["min_relevance_overlap"] = min_relevance_overlap
    out.pop("save", None)
    return out


def _post_evaluation(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/evaluate/answers"
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"evaluation request failed: {response.status_code} {response.text}"
        ) from exc
    data = response.json()
    if not isinstance(data, dict):
        raise SystemExit("evaluation response must be a JSON object")
    return data


def _aggregate_row(name: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    aggregate = evaluation.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = {}
    row = {
        "name": name,
        "method": evaluation.get("method"),
        "generator": evaluation.get("generator"),
        "top_k": evaluation.get("top_k"),
        "min_support_rate": evaluation.get("min_support_rate"),
        "min_relevance_overlap": evaluation.get("min_relevance_overlap"),
    }
    row.update(aggregate)
    return row


def _write_outputs(
    output_dir: Path,
    timestamp: str,
    dataset_path: Path,
    results: dict[str, dict[str, Any]],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"comparison_{timestamp}.json"
    csv_path = output_dir / f"comparison_{timestamp}.csv"
    record = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "results": results,
    }
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = [_aggregate_row(name, evaluation) for name, evaluation in results.items()]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AGGREGATE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare baseline and guarded answer evaluation metrics."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-support-rate", type=float, default=0.5)
    parser.add_argument("--min-relevance-overlap", type=float, default=0.35)
    args = parser.parse_args()

    payload = _load_payload(args.dataset)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {
        "baseline": _post_evaluation(args.base_url, _baseline_payload(payload)),
        "guarded": _post_evaluation(
            args.base_url,
            _guarded_payload(
                payload,
                min_support_rate=args.min_support_rate,
                min_relevance_overlap=args.min_relevance_overlap,
            ),
        ),
    }
    json_path, csv_path = _write_outputs(args.output_dir, timestamp, args.dataset, results)
    print(f"wrote {json_path}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
