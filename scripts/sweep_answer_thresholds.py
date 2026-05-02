"""Sweep answer guard thresholds over a local answer-eval dataset."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from app.evaluator import evaluate_answer_cases

DEFAULT_DATASET = Path("datasets/sample_answer_eval_cases.json")
DEFAULT_DOCUMENTS_DIR = Path("data/documents")
DEFAULT_OUTPUT_DIR = Path("data/experiments")
CSV_FIELDS = [
    "min_support_rate",
    "min_relevance_overlap",
    "score",
    "total",
    "answerable_total",
    "citation_hit_rate",
    "unanswerable_total",
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
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise SystemExit("dataset must be a JSON object with a cases list")
    return data


def _values(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise SystemExit("threshold list must not be empty")
    for value in values:
        if not 0.0 <= value <= 1.0:
            raise SystemExit("thresholds must be between 0 and 1")
    return values


def _score(aggregate: dict[str, Any]) -> float:
    citation = float(aggregate.get("citation_hit_rate") or 0.0)
    refusal = float(aggregate.get("refusal_accuracy") or 0.0)
    hallucination = float(aggregate.get("mean_hallucination_rate") or 0.0)
    return citation + refusal - hallucination


def sweep_thresholds(
    payload: dict[str, Any],
    documents_dir: Path,
    *,
    support_values: list[float],
    overlap_values: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for support in support_values:
        for overlap in overlap_values:
            evaluation = evaluate_answer_cases(
                payload["cases"],
                documents_dir,
                method=str(payload.get("method", "keyword")),
                generator=str(payload.get("generator", "extractive")),
                top_k=int(payload.get("top_k", 5)),
                min_support_rate=support,
                min_relevance_overlap=overlap,
            )
            aggregate = evaluation.get("aggregate", {})
            row = {
                "min_support_rate": support,
                "min_relevance_overlap": overlap,
                "score": _score(aggregate if isinstance(aggregate, dict) else {}),
            }
            if isinstance(aggregate, dict):
                row.update(aggregate)
            rows.append(row)
    rows.sort(
        key=lambda row: (
            -float(row.get("score", 0.0)),
            float(row["min_support_rate"]),
            float(row["min_relevance_overlap"]),
        )
    )
    return rows


def write_outputs(
    rows: list[dict[str, Any]],
    output_dir: Path,
    *,
    dataset_path: Path,
    timestamp: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"threshold_sweep_{timestamp}.json"
    csv_path = output_dir / f"threshold_sweep_{timestamp}.csv"
    record = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "best": rows[0] if rows else None,
        "rows": rows,
    }
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep answer guard thresholds locally.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--documents-dir", type=Path, default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--support-values",
        default="0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9",
    )
    parser.add_argument(
        "--overlap-values",
        default="0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9",
    )
    args = parser.parse_args()

    payload = _load_payload(args.dataset)
    rows = sweep_thresholds(
        payload,
        args.documents_dir,
        support_values=_values(args.support_values),
        overlap_values=_values(args.overlap_values),
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path, csv_path = write_outputs(
        rows,
        args.output_dir,
        dataset_path=args.dataset,
        timestamp=timestamp,
    )
    print(f"best: {rows[0] if rows else None}")
    print(f"wrote {json_path}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
