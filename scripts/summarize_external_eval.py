"""Summarize multi-model external answer evaluation JSON into a Markdown report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_EXPERIMENTS_DIR = Path("data/experiments")
DEFAULT_REPORTS_DIR = Path("reports")
EXTERNAL_EVAL_GLOB = "external_eval_*.json"

AGGREGATE_METRICS: tuple[tuple[str, str], ...] = (
    ("total", "用例总数"),
    ("answerable_total", "可回答用例数"),
    ("unanswerable_total", "不可回答用例数"),
    ("refusal_correct_count", "正确拒答次数"),
    ("refusal_accuracy", "拒答准确率"),
    ("over_refusal_count", "过度拒答次数"),
    ("over_refusal_rate", "过度拒答率"),
    ("mean_support_rate", "平均证据支持率"),
    ("mean_hallucination_rate", "平均幻觉率"),
)

BY_MODEL_METRICS: tuple[tuple[str, str], ...] = (
    ("total", "用例总数"),
    ("answerable_total", "可回答用例数"),
    ("unanswerable_total", "不可回答用例数"),
    ("refusal_accuracy", "拒答准确率"),
    ("over_refusal_rate", "过度拒答率"),
    ("mean_support_rate", "平均证据支持率"),
    ("mean_hallucination_rate", "平均幻觉率"),
)

RATE_FIELDS = {
    "refusal_accuracy",
    "over_refusal_rate",
    "mean_support_rate",
    "mean_hallucination_rate",
    "min_support_rate",
}


def _latest_external_eval_json(experiments_dir: Path) -> Path | None:
    candidates = sorted(
        experiments_dir.glob(EXTERNAL_EVAL_GLOB),
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_external_eval(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"external eval file not found: {path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("external eval JSON must be an object")
    aggregate = data.get("aggregate")
    if not isinstance(aggregate, dict):
        raise SystemExit("external eval JSON must contain an aggregate object")
    by_model = aggregate.get("by_model")
    if by_model is not None and not isinstance(by_model, dict):
        raise SystemExit("aggregate.by_model must be an object when present")
    return data


def _fmt_metric(key: str, value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if key in RATE_FIELDS:
            return f"{float(value):.4f}"
        return str(value)
    return str(value)


def _models_extreme(by_model: dict[str, Any], metric: str, *, mode: str) -> list[str]:
    """Return model keys tied for the requested max/min metric."""
    pairs: list[tuple[str, float]] = []
    for key, block in by_model.items():
        if not isinstance(block, dict):
            continue
        raw = block.get(metric)
        if isinstance(raw, (int, float)):
            pairs.append((str(key), float(raw)))
    if not pairs:
        return []
    if mode == "max":
        best = max(value for _, value in pairs)
        return sorted(key for key, value in pairs if value == best)
    if mode == "min":
        best = min(value for _, value in pairs)
        return sorted(key for key, value in pairs if value == best)
    raise ValueError(f"unknown mode: {mode}")


def _metric_extreme_value(by_model: dict[str, Any], metric: str, *, mode: str) -> float | None:
    values: list[float] = []
    for block in by_model.values():
        if not isinstance(block, dict):
            continue
        raw = block.get(metric)
        if isinstance(raw, (int, float)):
            values.append(float(raw))
    if not values:
        return None
    if mode == "max":
        return max(values)
    if mode == "min":
        return min(values)
    raise ValueError(f"unknown mode: {mode}")


def _join_models(keys: list[str]) -> str:
    if not keys:
        return "（无分模型数据）"
    return "、".join(f"`{key}`" for key in keys)


def _short_conclusion(
    aggregate: dict[str, Any],
    by_model: dict[str, Any],
    top_refusal: list[str],
    top_over_refusal: list[str],
    lowest_hallucination: list[str],
) -> str:
    parts: list[str] = []
    total = aggregate.get("total")
    if isinstance(total, int) and total > 0:
        parts.append(f"本批共评测 {total} 条外部模型答案。")

    if by_model:
        max_over_refusal = _metric_extreme_value(
            by_model,
            "over_refusal_rate",
            mode="max",
        )
        if max_over_refusal is not None and max_over_refusal <= 0:
            over_refusal_text = "本批分模型 `over_refusal_rate` 均为 0，未观察到过度拒答"
        else:
            over_refusal_text = (
                f"`over_refusal_rate` 最高的是 {_join_models(top_over_refusal)}，"
                "说明这些模型在可回答样本上更容易保守拒答"
            )
        parts.append(
            f"分模型对比显示：`refusal_accuracy` 最高的是 {_join_models(top_refusal)}；"
            f"{over_refusal_text}；"
            f"`mean_hallucination_rate` 最低的是 {_join_models(lowest_hallucination)}。"
        )
    else:
        parts.append("未提供 `aggregate.by_model`，本报告仅展示整体指标。")

    refusal_accuracy = aggregate.get("refusal_accuracy")
    over_refusal_rate = aggregate.get("over_refusal_rate")
    if isinstance(refusal_accuracy, (int, float)) and isinstance(over_refusal_rate, (int, float)):
        if refusal_accuracy >= 0.9 and over_refusal_rate <= 0.1:
            parts.append("整体拒答行为较稳健。")
        elif over_refusal_rate > 0.2:
            parts.append("整体过度拒答偏高，建议检查可回答样本上的拒答策略或证据质量。")

    if not parts:
        return "数据不足以自动生成结论，请人工核对 aggregate 和 rows。"
    return " ".join(parts)


def render_report_markdown(record: dict[str, Any]) -> str:
    created_at = record.get("created_at")
    dataset = record.get("dataset")
    aggregate = record.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ValueError("record must contain aggregate")

    by_model_raw = aggregate.get("by_model")
    by_model: dict[str, Any] = by_model_raw if isinstance(by_model_raw, dict) else {}

    top_refusal = _models_extreme(by_model, "refusal_accuracy", mode="max")
    top_over_refusal = _models_extreme(by_model, "over_refusal_rate", mode="max")
    lowest_hallucination = _models_extreme(
        by_model,
        "mean_hallucination_rate",
        mode="min",
    )

    lines: list[str] = [
        "# 多模型外部评测报告",
        "",
        "## 实验信息",
        "",
        f"- **实验记录时间**: {created_at if created_at is not None else '-'}",
        f"- **数据集路径**: `{dataset}`" if dataset else "- **数据集路径**: -",
        f"- **min_support_rate**: {_fmt_metric('min_support_rate', record.get('min_support_rate'))}",
        "",
        "## 整体 aggregate 指标",
        "",
        "| 指标 | 说明 | 值 |",
        "|---|---|---|",
    ]

    for key, label in AGGREGATE_METRICS:
        lines.append(f"| `{key}` | {label} | {_fmt_metric(key, aggregate.get(key))} |")

    lines.extend(["", "## 分模型指标（by_model）", ""])

    if not by_model:
        lines.append("（aggregate 中无 `by_model` 或为空）")
    else:
        header = "| 模型（provider/model） | " + " | ".join(
            label for _, label in BY_MODEL_METRICS
        ) + " |"
        sep = "|---|" + "|".join("---" for _ in BY_MODEL_METRICS) + "|"
        lines.append(header)
        lines.append(sep)
        for model_key in sorted(by_model.keys()):
            block = by_model[model_key]
            if not isinstance(block, dict):
                continue
            cells = [f"`{model_key}`"]
            for metric_key, _label in BY_MODEL_METRICS:
                cells.append(_fmt_metric(metric_key, block.get(metric_key)))
            lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## 模型对比摘要",
            "",
            f"- **refusal_accuracy 最高的模型**: {_join_models(top_refusal)}",
            f"- **over_refusal_rate 最高的模型**: {_join_models(top_over_refusal)}",
            f"- **mean_hallucination_rate 最低的模型**: {_join_models(lowest_hallucination)}",
            "",
            "## 简短结论",
            "",
            _short_conclusion(
                aggregate,
                by_model,
                top_refusal,
                top_over_refusal,
                lowest_hallucination,
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_report(markdown: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a Markdown report from external_eval_*.json."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to external_eval_*.json (default: latest under experiments dir)",
    )
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=DEFAULT_EXPERIMENTS_DIR,
        help=f"Directory to scan for {EXTERNAL_EVAL_GLOB} when --input is omitted",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Markdown path (default: reports/external_eval_report_<timestamp>.md)",
    )
    args = parser.parse_args()

    if args.input is not None:
        input_path = args.input
    else:
        latest = _latest_external_eval_json(args.experiments_dir)
        if latest is None:
            raise SystemExit(
                f"no {EXTERNAL_EVAL_GLOB} found under {args.experiments_dir}; pass --input PATH"
            )
        input_path = latest

    record = load_external_eval(input_path)
    markdown = render_report_markdown(record)

    if args.output is not None:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = DEFAULT_REPORTS_DIR / f"external_eval_report_{timestamp}.md"

    written = write_report(markdown, output_path)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
