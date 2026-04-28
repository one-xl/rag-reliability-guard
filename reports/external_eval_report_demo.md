# 多模型外部评测报告

## 实验信息

- **实验记录时间**: 2026-04-28T19:09:08+08:00
- **数据集路径**: `datasets\demo_external_eval_cases.json`
- **min_support_rate**: 0.5000

## 整体 aggregate 指标

| 指标 | 说明 | 值 |
|---|---|---|
| `total` | 用例总数 | 6 |
| `answerable_total` | 可回答用例数 | 4 |
| `unanswerable_total` | 不可回答用例数 | 2 |
| `refusal_correct_count` | 正确拒答次数 | 1 |
| `refusal_accuracy` | 拒答准确率 | 0.5000 |
| `over_refusal_count` | 过度拒答次数 | 1 |
| `over_refusal_rate` | 过度拒答率 | 0.2500 |
| `mean_support_rate` | 平均证据支持率 | 0.3333 |
| `mean_hallucination_rate` | 平均幻觉率 | 0.6667 |

## 分模型指标（by_model）

| 模型（provider/model） | 用例总数 | 可回答用例数 | 不可回答用例数 | 拒答准确率 | 过度拒答率 | 平均证据支持率 | 平均幻觉率 |
|---|---|---|---|---|---|---|---|
| `alibaba/qwen-plus` | 1 | 1 | 0 | 0.0000 | 1.0000 | 0.0000 | 1.0000 |
| `anthropic/claude-3-5-sonnet-20241022` | 1 | 1 | 0 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| `deepseek/deepseek-chat` | 1 | 1 | 0 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| `google/gemini-2.0-flash` | 1 | 0 | 1 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| `openai/gpt-4.1-mini` | 1 | 0 | 1 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| `volcengine/doubao-pro-256k` | 1 | 1 | 0 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |

## 模型对比摘要

- **refusal_accuracy 最高的模型**: `openai/gpt-4.1-mini`
- **over_refusal_rate 最高的模型**: `alibaba/qwen-plus`
- **mean_hallucination_rate 最低的模型**: `deepseek/deepseek-chat`、`volcengine/doubao-pro-256k`

## 简短结论

本批共评测 6 条外部模型答案。 分模型对比显示：`refusal_accuracy` 最高的是 `openai/gpt-4.1-mini`；`over_refusal_rate` 最高的是 `alibaba/qwen-plus`，说明这些模型在可回答样本上更容易保守拒答；`mean_hallucination_rate` 最低的是 `deepseek/deepseek-chat`、`volcengine/doubao-pro-256k`。 整体过度拒答偏高，建议检查可回答样本上的拒答策略或证据质量。
