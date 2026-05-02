import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from app.evaluator import answer_evaluation_to_csv


def persist_answer_experiment(evaluation: dict, experiments_dir: Path) -> tuple[str, dict[str, str]]:
    """Write evaluation JSON and CSV; return run_id and relative artifact paths."""
    experiments_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    record = {"run_id": run_id, "created_at": created_at, **evaluation}
    json_path = experiments_dir / f"{run_id}.json"
    csv_path = experiments_dir / f"{run_id}.csv"
    json_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_text = answer_evaluation_to_csv(evaluation)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
    rel_json = f"data/experiments/{run_id}.json"
    rel_csv = f"data/experiments/{run_id}.csv"
    return run_id, {"json": rel_json, "csv": rel_csv}


def _load_answer_experiment_summaries(experiments_dir: Path) -> list[dict]:
    """List persisted answer-evaluation runs, newest first."""
    if not experiments_dir.is_dir():
        return []
    summaries: list[dict] = []
    for path in experiments_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_id = data.get("run_id")
        if not isinstance(run_id, str):
            continue
        agg = data.get("aggregate")
        if not isinstance(agg, dict):
            continue
        summaries.append(
            {
                "run_id": run_id,
                "created_at": data.get("created_at"),
                "method": data.get("method"),
                "generator": data.get("generator"),
                "top_k": data.get("top_k"),
                "total": agg.get("total"),
                "mean_support_rate": agg.get("mean_support_rate"),
                "mean_hallucination_rate": agg.get("mean_hallucination_rate"),
            }
        )

    def _sort_key(item: dict):
        ts = item.get("created_at")
        return ts if isinstance(ts, str) else ""

    summaries.sort(key=_sort_key, reverse=True)
    return summaries


def list_answer_experiments(experiments_dir: Path, *, limit: int, offset: int) -> list[dict]:
    """List a page of persisted answer-evaluation runs."""
    summaries = _load_answer_experiment_summaries(experiments_dir)
    return summaries[offset : offset + limit]


def list_answer_experiment_page(experiments_dir: Path, *, limit: int, offset: int) -> dict:
    """Return experiment page data plus total count for dashboard pagination."""
    summaries = _load_answer_experiment_summaries(experiments_dir)
    return {
        "items": summaries[offset : offset + limit],
        "total": len(summaries),
        "limit": limit,
        "offset": offset,
    }


def get_answer_experiment(
    run_id: str,
    experiments_dir: Path,
    *,
    logger: logging.Logger,
) -> dict:
    try:
        uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到该实验") from exc
    path = experiments_dir / f"{run_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="未找到该实验")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("读取实验 JSON 失败")
        raise HTTPException(
            status_code=500,
            detail="实验数据已损坏，无法读取",
        ) from exc
