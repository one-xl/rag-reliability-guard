# 提交产物清单

本文档用于当前阶段提交前检查，目标是只提交可复现的代码、测试、数据集样例和论文材料，不提交本地密钥、缓存或大体积可再下载文件。

## 建议提交

- 后端与评测逻辑：
  - `app/answerer.py`
  - `app/evaluator.py`
  - `app/main.py` 中与评测参数透传相关的改动
- 自动化脚本：
  - `scripts/build_real_paper_eval_dataset.py`
  - `scripts/run_answer_eval_experiment.py`
  - `scripts/summarize_answer_eval_comparison.py`
- 测试：
  - `tests/test_answerer.py`
  - `tests/test_evaluator.py`
  - `tests/test_build_real_paper_eval_dataset.py`
  - `tests/test_run_answer_eval_experiment.py`
  - `tests/test_summarize_answer_eval_comparison.py`
- 可复现实验输入与文档：
  - `datasets/real_paper_answer_eval_cases.json`
  - `docs/codex_cursor_reproducible_workflow.md`
  - `docs/thesis_experiment_section.md`
  - `docs/commit_artifacts_checklist.md`
  - `reports/answer_eval_report_real_papers.md`

## 不建议提交

- 本地密钥与环境配置：
  - `.env`
  - 原因：包含外部模型 API Key 或本地私有配置。
- Python 与测试缓存：
  - `__pycache__/`
  - `*.pyc`
  - `.pytest_cache/`
  - `.pytest_tmp/`
  - 原因：机器生成物，可重复生成，容易污染 diff。
- 虚拟环境：
  - `.venv/`
  - `venv/`
  - 原因：体积大，和本机路径强相关。
- 本地运行数据：
  - `data/`
  - 原因：包含上传、索引和实验运行输出，适合本地复现，不适合直接入库。
- 真实论文原始 PDF 和中间检索结果：
  - `papers/*.pdf`
  - `papers/search_result_*.json`
  - `papers/upload_results.json`
  - `papers/real_papers_answer_eval*.json`
  - `papers/real_papers_answer_eval*.csv`
  - 原因：PDF 体积较大且可从公开来源重新下载；中间搜索和上传结果可由脚本重新生成。

## 提交前检查命令

```powershell
git status --short --ignored
git check-ignore -v .env
git check-ignore -v papers\self_rag_iclr2024.pdf
git check-ignore -v papers\search_result_1.json
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
```

如果需要确认上传逻辑未被误改：

```powershell
git diff -- app\main.py | Select-String -Pattern "upload|read|MAX_UPLOAD|UPLOAD_CHUNK" -Context 2,2
```

## 当前阶段建议提交信息

```text
Add RAG guardrail evaluation workflow
```

## Cursor / Codex 协作记录

本次整理原计划由 Cursor Agent 实现、Codex 审查。实际执行时 Cursor Agent 返回 `[unavailable]`，因此由 Codex 按同一任务做最小兜底修改；后续仍应优先保持“Cursor 实现，Codex 审查”的流程。
