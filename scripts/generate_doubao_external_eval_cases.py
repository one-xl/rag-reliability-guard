"""Generate external-eval dataset answers by calling live Doubao (Volcengine Ark)."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_doubao_settings
from app.llm_client import generate_doubao_answer

DATASET_COMMENT = (
    "Live Doubao-generated answers via generate_doubao_external_eval_cases.py. "
    "provider/model/run_id reflect actual generation settings."
)


def evidence_to_doubao_citations(evidence: object) -> list[dict]:
    """Map external-eval evidence items to citations for generate_doubao_answer."""
    if evidence is None:
        return []
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list")
    citations: list[dict] = []
    for i, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise ValueError(f"evidence[{i}] must be an object")
        text_raw = item.get("text")
        if not isinstance(text_raw, str):
            raise ValueError(f"evidence[{i}] text must be a string")
        source_raw = item.get("source", "")
        citations.append(
            {
                "index": i + 1,
                "original_filename": str(source_raw) if source_raw is not None else "",
                "chunk_index": i,
                "text_preview": text_raw,
            }
        )
    return citations


def load_source(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"source not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"source is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("source must be a JSON object")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise SystemExit("source must contain a cases list")
    return data


def _min_support_rate_from_payload(raw: dict[str, Any]) -> float | None:
    msr = raw.get("min_support_rate")
    if isinstance(msr, (int, float)):
        return float(msr)
    return None


def _case_id(case: dict[str, Any], index: int) -> str:
    cid = case.get("case_id")
    if cid is None:
        return f"case-{index + 1}"
    return str(cid)


def build_live_dataset_payload(
    source: dict[str, Any],
    *,
    run_id: str,
    model: str,
    provider: str = "volcengine",
    answer_generator: Callable[[str, list[dict]], str] | None = None,
) -> dict[str, Any]:
    """Build evaluate_external_answers-compatible JSON with live-generated answers."""
    gen = answer_generator if answer_generator is not None else generate_doubao_answer
    cases_in = source.get("cases")
    if not isinstance(cases_in, list):
        raise ValueError("source must contain cases list")

    out_cases: list[dict[str, Any]] = []
    for idx, raw_case in enumerate(cases_in):
        if not isinstance(raw_case, dict):
            raise ValueError(f"case {idx}: must be an object")
        question = raw_case.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"case {idx}: question must be a non-empty string")
        ans_flag = raw_case.get("answerable")
        if not isinstance(ans_flag, bool):
            raise ValueError(f"case {idx}: answerable must be a boolean")

        evidence_copy = copy.deepcopy(raw_case.get("evidence", []))
        citations = evidence_to_doubao_citations(evidence_copy)
        answer = gen(question.strip(), citations)

        out_cases.append(
            {
                "case_id": _case_id(raw_case, idx),
                "provider": provider,
                "model": model,
                "run_id": run_id,
                "question": question.strip(),
                "answerable": ans_flag,
                "answer": answer,
                "evidence": evidence_copy,
            }
        )

    payload: dict[str, Any] = {
        "_comment": DATASET_COMMENT,
        "cases": out_cases,
    }
    min_sr = _min_support_rate_from_payload(source)
    if min_sr is not None:
        payload["min_support_rate"] = min_sr
    return payload


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_run_id = f"doubao-live-{ts}"
    default_output = Path(f"data/experiments/doubao_external_eval_cases_{ts}.json")

    parser = argparse.ArgumentParser(
        description=(
            "Read external-eval scaffold cases (question, evidence, answerable), "
            "call Doubao for each answer, and write JSON for scripts/evaluate_external_answers.py."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("datasets/demo_external_eval_cases.json"),
    )
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--run-id", default=default_run_id)
    args = parser.parse_args()

    source = load_source(args.source.resolve())
    settings = get_doubao_settings()
    model = settings.model

    payload = build_live_dataset_payload(
        source,
        run_id=args.run_id,
        model=model,
        provider="volcengine",
    )

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
