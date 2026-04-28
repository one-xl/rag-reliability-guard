"""Summarize baseline-vs-guarded answer evaluation comparison JSON into Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_EXPERIMENTS_DIR = Path("data/experiments")
DEFAULT_REPORTS_DIR = Path("reports")
COMPARISON_GLOB = "comparison_*.json"

KEY_METRICS = (
    ("total", "用例总数"),
    ("answerable_total", "可回答用例数"),
    ("citation_hit_rate", "引用命中率"),
    ("unanswerable_total", "不可回答用例数"),
    ("refusal_accuracy", "拒答准确率"),
    ("mean_support_rate", "平均证据支持率"),
    ("mean_hallucination_rate", "平均幻觉率"),
)

RATE_FIELDS = {
    "citation_hit_rate",
    "refusal_accuracy",
    "mean_support_rate",
    "mean_hallucination_rate",
}


def _latest_comparison_json(experiments_dir: Path) -> Path | None:
    candidates = sorted(
        experiments_dir.glob(COMPARISON_GLOB),
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_comparison(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"comparison file not found: {path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("comparison JSON must be an object")
    if not isinstance(data.get("results"), dict):
        raise SystemExit("comparison JSON must contain a results object")
    return data


def _aggregate(results: dict[str, Any], name: str) -> dict[str, Any]:
    block = results.get(name)
    if not isinstance(block, dict):
        return {}
    aggregate = block.get("aggregate")
    return aggregate if isinstance(aggregate, dict) else {}


def _fmt_value(key: str, value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if key in RATE_FIELDS:
            return f"{float(value):.4f}"
        return str(value)
    return str(value)


def _delta_line(metric_key: str, baseline_value: Any, guarded_value: Any) -> str:
    if not isinstance(baseline_value, (int, float)) or not isinstance(guarded_value, (int, float)):
        return f"- **{metric_key}**: 无法计算，缺少数值"
    delta = float(guarded_value) - float(baseline_value)
    return (
        f"- **{metric_key}**: {delta:+.4f} "
        f"(baseline {_fmt_value(metric_key, baseline_value)} -> "
        f"guarded {_fmt_value(metric_key, guarded_value)})"
    )


def _conclusion(baseline_aggregate: dict[str, Any], guarded_aggregate: dict[str, Any]) -> str:
    parts: list[str] = []

    citation_baseline = baseline_aggregate.get("citation_hit_rate")
    citation_guarded = guarded_aggregate.get("citation_hit_rate")
    if isinstance(citation_baseline, (int, float)) and isinstance(citation_guarded, (int, float)):
        if citation_guarded > citation_baseline:
            parts.append("Guarded 相比 Baseline 提升了引用命中率。")
        elif citation_guarded < citation_baseline:
            parts.append("Guarded 相比 Baseline 降低了引用命中率，需要检查阈值是否过严。")
        else:
            parts.append("引用命中率与 Baseline 持平。")

    refusal_baseline = baseline_aggregate.get("refusal_accuracy")
    refusal_guarded = guarded_aggregate.get("refusal_accuracy")
    if isinstance(refusal_baseline, (int, float)) and isinstance(refusal_guarded, (int, float)):
        if refusal_guarded > refusal_baseline:
            parts.append("拒答准确率提升，说明幻觉抑制对不可回答问题有效。")
        elif refusal_guarded < refusal_baseline:
            parts.append("拒答准确率下降，需要检查拒答策略。")
        else:
            parts.append("拒答准确率与 Baseline 持平。")

    hallucination_baseline = baseline_aggregate.get("mean_hallucination_rate")
    hallucination_guarded = guarded_aggregate.get("mean_hallucination_rate")
    if isinstance(hallucination_baseline, (int, float)) and isinstance(hallucination_guarded, (int, float)):
        if hallucination_guarded < hallucination_baseline:
            parts.append("平均幻觉率下降，答案更保守。")
        elif hallucination_guarded > hallucination_baseline:
            parts.append("平均幻觉率上升，可能是拒答样本的空证据计分方式造成，需要结合 refusal_accuracy 解读。")
        else:
            parts.append("平均幻觉率与 Baseline 持平。")

    if not parts:
        return "数据不足以自动生成结论，请人工核对 aggregate 字段。"
    return " ".join(parts)


def render_report_markdown(record: dict[str, Any]) -> str:
    created_at = record.get("created_at")
    dataset = record.get("dataset")
    results = record.get("results")
    if not isinstance(results, dict):
        raise ValueError("record must contain a results object")

    baseline = results.get("baseline")
    guarded = results.get("guarded")
    baseline_meta = baseline if isinstance(baseline, dict) else {}
    guarded_meta = guarded if isinstance(guarded, dict) else {}
    baseline_aggregate = _aggregate(results, "baseline")
    guarded_aggregate = _aggregate(results, "guarded")

    lines: list[str] = [
        "# 答案评测对比实验报告",
        "",
        "## 实验信息",
        "",
        f"- **实验记录时间**: {created_at if created_at is not None else '-'}",
        f"- **数据集路径**: `{dataset}`" if dataset else "- **数据集路径**: -",
        "",
        "## Baseline / Guarded 配置摘要",
        "",
        "| 项目 | Baseline | Guarded |",
        "|---|---|---|",
        f"| method | {_fmt_value('method', baseline_meta.get('method'))} | {_fmt_value('method', guarded_meta.get('method'))} |",
        f"| generator | {_fmt_value('generator', baseline_meta.get('generator'))} | {_fmt_value('generator', guarded_meta.get('generator'))} |",
        f"| top_k | {_fmt_value('top_k', baseline_meta.get('top_k'))} | {_fmt_value('top_k', guarded_meta.get('top_k'))} |",
        f"| min_support_rate | - | {_fmt_value('min_support_rate', guarded_meta.get('min_support_rate'))} |",
        f"| min_relevance_overlap | - | {_fmt_value('min_relevance_overlap', guarded_meta.get('min_relevance_overlap'))} |",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 说明 | Baseline | Guarded |",
        "|---|---|---|---|",
    ]

    for key, description in KEY_METRICS:
        lines.append(
            f"| `{key}` | {description} | "
            f"{_fmt_value(key, baseline_aggregate.get(key))} | "
            f"{_fmt_value(key, guarded_aggregate.get(key))} |"
        )

    lines.extend(
        [
            "",
            "## 关键变化",
            "",
            _delta_line(
                "citation_hit_rate",
                baseline_aggregate.get("citation_hit_rate"),
                guarded_aggregate.get("citation_hit_rate"),
            ),
            _delta_line(
                "refusal_accuracy",
                baseline_aggregate.get("refusal_accuracy"),
                guarded_aggregate.get("refusal_accuracy"),
            ),
            _delta_line(
                "mean_hallucination_rate",
                baseline_aggregate.get("mean_hallucination_rate"),
                guarded_aggregate.get("mean_hallucination_rate"),
            ),
            "",
            "## 简短结论",
            "",
            _conclusion(baseline_aggregate, guarded_aggregate),
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
        description="Build a Markdown report from answer-eval comparison JSON."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to comparison_*.json (default: latest under experiments dir)",
    )
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=DEFAULT_EXPERIMENTS_DIR,
        help=f"Directory to scan for {COMPARISON_GLOB} when --input is omitted",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Markdown path (default: reports/answer_eval_report_<timestamp>.md)",
    )
    args = parser.parse_args()

    if args.input is not None:
        input_path = args.input
    else:
        latest = _latest_comparison_json(args.experiments_dir)
        if latest is None:
            raise SystemExit(
                f"no {COMPARISON_GLOB} found under {args.experiments_dir}; pass --input PATH"
            )
        input_path = latest

    record = load_comparison(input_path)
    markdown = render_report_markdown(record)

    if args.output is not None:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = DEFAULT_REPORTS_DIR / f"answer_eval_report_{timestamp}.md"

    written = write_report(markdown, output_path)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
