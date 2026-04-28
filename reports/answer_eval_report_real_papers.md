# 答案评测对比实验报告

## 实验信息

- **实验记录时间**: 2026-04-28T14:03:50+08:00
- **数据集路径**: `datasets\real_paper_answer_eval_cases.json`

## Baseline / Guarded 配置摘要

| 项目 | Baseline | Guarded |
|---|---|---|
| method | bm25 | bm25 |
| generator | extractive | extractive |
| top_k | 3 | 3 |
| min_support_rate | - | 0.5 |
| min_relevance_overlap | - | 0.35 |

## 汇总指标

| 指标 | 说明 | Baseline | Guarded |
|---|---|---|---|
| `total` | 用例总数 | 20 | 20 |
| `answerable_total` | 可回答用例数 | 12 | 12 |
| `citation_hit_rate` | 引用命中率 | 1.0000 | 1.0000 |
| `unanswerable_total` | 不可回答用例数 | 8 | 8 |
| `refusal_accuracy` | 拒答准确率 | 0.0000 | 0.6250 |
| `mean_support_rate` | 平均证据支持率 | 0.9345 | 0.7008 |
| `mean_hallucination_rate` | 平均幻觉率 | 0.0655 | 0.2992 |

## 关键变化

- **citation_hit_rate**: +0.0000 (baseline 1.0000 -> guarded 1.0000)
- **refusal_accuracy**: +0.6250 (baseline 0.0000 -> guarded 0.6250)
- **mean_hallucination_rate**: +0.2336 (baseline 0.0655 -> guarded 0.2992)

## 简短结论

引用命中率与 Baseline 持平。 拒答准确率提升，说明幻觉抑制对不可回答问题有效。 平均幻觉率上升，可能是拒答样本的空证据计分方式造成，需要结合 refusal_accuracy 解读。
