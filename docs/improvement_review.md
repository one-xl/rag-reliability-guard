# 项目改进与优化清单

本文件记录对当前仓库（feature/rag-system 分支）的代码审查结论与后续实施进度。
下方“实施进度记录”和“状态索引”代表当前状态；后面的原始审查条目保留为历史材料，部分“现状”描述已经被后续优化修复。

> 角色声明：审查者视角。涉及"是否实施、是否合并"由实现者与用户决定。
>
> 原始审查时机：`git status` 仅有 `app/__init__.py` 一处空行改动；原始清单基于该历史快照。

---

## 实施进度记录

### 2026-05-01 第一轮优化（已完成）

- 完成 #1：`check_answer_faithfulness` 对无关键词 claim 改为跳过统计，避免客套语推高支持率。
- 完成 #2 + #3：内部 / 外部评测统一使用收紧后的 `is_refusal`，避免子串误命中，并支持 citations 非空时仍正确识别拒答。
- 完成 #4：新增 `unsupported_claim_rate` 与 `hallucination_proxy_rate`，保留 `hallucination_rate` 兼容旧 JSON / CSV / dashboard。
- 完成 #5 + #6：中文匹配从逐字调整为 CJK bigram；停用词表合并到 `app/faithfulness.py`，`answerer` 复用同一套关键词提取。
- 完成 #10：PDF 上传增加 magic bytes 校验。
- 完成 #14：`/api/answer` 的 `min_support_rate` / `min_relevance_overlap` 增加 0-1 范围校验。
- 完成 #15：Doubao 生成失败默认 fallback 到 extractive，并提供 `fallback_to_extractive=false` 严格模式。
- 完成 #18 + #19：`app/__init__.py` 改为有意义的包版本常量；`app/main.py` 复用 `PROJECT_ROOT`。
- 验证：`116 passed`。

### 2026-05-01 第二轮优化（已完成）

- 完成 #7：新增 `app/document_index.py` 轻量内存索引，缓存文档 rows、`(doc_id, chunk_idx) -> text` 映射和 BM25 统计；`search.py`、`bm25.py`、`answerer.py` 已接入。
- 完成 #8：PDF 上传改用 `tempfile.SpooledTemporaryFile` 分块写入，避免 `list[bytes] + join` 带来的额外内存放大。
- 完成 #9：`/api/experiments` 增加 `limit` / `offset` 分页参数，默认保留向后兼容的最新 50 条。
- 验证：`118 passed`。

### 2026-05-01 第三轮优化（已完成）

- 完成 #11：Doubao OpenAI-compatible 调用对网络错误和 5xx 响应增加最多 2 次指数退避重试；4xx、JSON 解析失败和响应结构异常保持快速失败。
- 完成 #11：批量答案评测增加 `continue_on_error`，显式开启时单条 LLM 失败会记录为 `error` 行，并计入 `aggregate.error_count`，避免整批实验中断。
- 验证：`122 passed`。

### 2026-05-01 第四轮优化（已完成）

- 完成 #17：新增 `app/schemas.py`，把 `/api/answer`、`/api/evaluate/answers`、`/api/evaluate/answers/export`、`/api/evaluate/external-answer`、`/api/evaluate/external-answers` 的请求边界校验集中到 Pydantic 模型。
- 完成 #14/#17 延续：`top_k`、`method`、`generator`、`min_support_rate`、`min_relevance_overlap`、`continue_on_error`、`fallback_to_extractive` 等参数统一由 schema 约束，减少 `main.py` 重复 `if`。
- 兼容性说明：为了不破坏现有前端和测试，Pydantic 校验错误仍在路由层转换为 400 字符串错误；后续若要完全使用 FastAPI 自动 OpenAPI body schema，可再切换为直接类型注解并接受 422 语义。
- 验证：`122 passed`。

### 2026-05-01 第五轮优化（已完成）

- 完成 #12：新增 `app/logging_config.py`，应用导入时配置标准日志格式，避免模块 logger 默认无 handler。
- 完成 #13：增强手写 dotenv 解析，支持 `export KEY=...`、带空格引号值和行内注释；仍不新增运行时依赖。
- 完成 #24：`chunk_text` 在存在空行段落时优先按段落聚合，长段再回退固定窗口切分；无空行文本保持旧的固定窗口行为。
- 完成 #25：PDF 上传写入 `sha256`，重复文件直接返回已存在文档；新增 `DELETE /api/documents/{id}` 删除元数据和上传文件，并刷新内存索引。
- 完成 #27/#28：dashboard 文档列表增加删除按钮；外部评测 by_model 区域增加 provider/model 元数据提醒；上传和删除按钮增加 loading/disabled 状态。
- 完成 #21：新增 `requirements-dev.txt`、基础 `pyproject.toml` ruff 配置和 GitHub Actions pytest workflow。
- 完成 #26：新增 `scripts/sweep_answer_thresholds.py`，可在本地文档索引和评测集上扫描 `min_support_rate` / `min_relevance_overlap` 阈值组合并输出 JSON/CSV。
- 验证：`131 passed`。

### 2026-05-02 第六轮优化（已完成）

- 完成 #16：`app/main.py` 从约 431 行压缩到约 204 行，保留薄 FastAPI 路由层；文档上传/删除、实验持久化、请求解析、答案评测包装、Demo 数据读取拆入 `app/services/`。
- 完成 #20：`app/static/index.html` 从约 1008 行拆为页面结构、`dashboard.css` 和 `dashboard.js`；根路由改用 `FileResponse`，并挂载 `/static` 静态资源。
- 完成 #20 延续：dashboard 测试改为分别校验 HTML 结构、CSS 样式资源和 JS 交互逻辑，避免前端拆分后继续在 HTML 中硬找脚本内容。
- 验证：`python -m py_compile app/main.py app/services/*.py` 通过；全量 pytest 在沙箱外验证 `131 passed`。

### 2026-05-02 第七轮优化（已完成）

- 完成 #22：新增 `/api/v1/...` 版本化 API 路径，并保留 `/api/...` 作为兼容别名；OpenAPI schema 仅暴露 `/api/v1/...`，降低后续破坏性变更风险。
- 完成 #28 延续：dashboard 默认改用 `/api/v1`；检索结果从纯 JSON 改为卡片化展示，并对查询词命中部分做高亮。
- 完成 #28 延续：实验记录列表接入 `limit/offset` 前端分页控件；文档删除增加浏览器确认，降低误删风险。
- 验证：`python -m py_compile app/main.py`、`node --check app/static/dashboard.js` 通过；全量 pytest 在沙箱外验证 `134 passed`。

### 2026-05-02 第八轮优化（已完成）

- 完成 #29：同步 `README.md` 与 `README.en.md` 的目录结构、API 示例、API 表和测试预期结果；推荐路径统一为 `/api/v1/...`，并说明 `/api/...` 是兼容别名。
- 完成 #21/#29 延续：README 增加可选 `requirements-dev.txt` 开发工具安装说明，避免 lint/type-check 配置和文档脱节。
- 完成清单维护：本文件顶部增加当前状态说明，明确后续原始审查条目是历史材料，避免已修复问题被误读为仍未处理。
- 验证：文档一致性检查通过，README 中已无过期的 `112 passed` 或未说明的旧 `/api/...` 示例。

### 2026-05-02 第九轮优化（已完成）

- 完成 #28 延续：dashboard 统一错误输出，HTTP detail、JSON 解析失败和操作失败都会显示带动作上下文的提示，并用 `.output-error` 高亮。
- 完成 #9/#28 延续：`/api/v1/experiments?include_total=true` 可返回 `{items,total,limit,offset}`，旧接口默认仍返回数组；dashboard 分页状态改为显示 `showing x-y of total`。
- 完成 #29 延续：同步 README / README.en.md 的测试基线为 `135 passed`，并补充 `include_total` 参数说明。
- #21 进展：尝试运行 ruff/mypy 时发现当前虚拟环境未安装 dev 依赖；安装依赖需要用户单独确认，本轮未修改本地环境。
- 验证：`node --check app/static/dashboard.js`、`python -m py_compile app/main.py app/services/experiments.py` 通过；相关测试 `4 passed`；全量 pytest 在沙箱外验证 `135 passed`。

### 2026-05-02 第十轮优化（已完成）

- 完成 #21：安装并运行 `requirements-dev.txt` 中的 ruff、mypy、pre-commit；新增 `.pre-commit-config.yaml`，本地 hook 覆盖 ruff、mypy 和 dashboard JS 语法检查。
- 完成 #21 延续：GitHub Actions 改为安装 `requirements-dev.txt`，并在 pytest 前运行 `python -m ruff check app scripts tests` 与 `python -m mypy app scripts`。
- 完成类型收敛：`parse_request` 改为泛型返回具体 Pydantic schema；修正若干类型边界（检索评测 cases 校验、citation key 类型、PDF 临时流类型）。
- 完成 lint 收敛：整理 import、移除未使用导入、采用 `datetime.UTC` 等 ruff 自动修复项；保留 FastAPI `Body/File` 默认值相关 B008 忽略。
- 验证：`ruff check app scripts tests`、`mypy app scripts`、`node --check app/static/dashboard.js`、`pre_commit run --all-files`、全量 pytest `135 passed`。

## 状态索引

- 已完成：#1-#22、#24-#29。
- 部分完成：#17 已集中 Pydantic 校验，但未切换到 FastAPI 原生 body schema + 422 语义。
- 未完成：#23 Dense / Hybrid 检索。
- 当前验证基线：全量 pytest `135 passed`。

### 当前仍未完成 / 后续优化

- #23：Dense / Hybrid 检索尚未实现；会引入 `sentence-transformers`、FAISS 或模型下载，建议单独确认依赖体积和离线策略后再做。
- #28：dashboard 核心体验优化已完成；后续只剩更多可视化筛选等增强项。
- #17 延续：Pydantic 已集中校验，但还未切到 FastAPI 原生 body schema + 422 语义；若要完整 OpenAPI schema，可另做兼容迁移。
- #21：开发质量工具链已落地；Windows 本地运行 pre-commit 时需先把 `.venv\Scripts` 放到 PATH 前面，避免误用 Anaconda Python。

---

## 一、影响指标真实性的逻辑层问题（建议优先）

### 1. `check_answer_faithfulness` 在无关键词的 claim 上判 supported=True

- 位置：`app/faithfulness.py:81-94`
- 现状：当 claim 提取不到关键词（例如 "好的。"、"以下是结论："）时，只要 `citations` 非空就判为 supported。
- 影响：豆包等生成器加客套语会显著推高 `mean_support_rate`，扭曲 baseline / guarded 对比实验的数字。
- 建议：关键词为空的 claim 直接跳过统计，或单独计 `null` 状态，不计入 `supported_count` / `total`。

### 2. 内部 / 外部"拒答判定"语义不一致

- 位置：
  - `app/external_eval.py:7-27`（`is_refusal`，子串短语匹配）
  - `app/evaluator.py:53-57`（`_refusal_correct_unanswerable`，仅在 `citations` 为空时检查拒答短语）
- 影响：citations 非空但答案是拒答的样本，在内部评测里会被漏算为 refusal_correct；和外部评测口径不一致，跨实验比较不可信。
- 建议：统一一套 `is_refusal`，evaluator 也调用它。

### 3. `is_refusal` 关键词容易误命中

- 位置：`app/external_eval.py:7-21`
- 现状：`"do not know"`、`"not enough information"`、`"无法回答"` 等短语在子串中匹配。
- 影响：诸如 `"the paper does not have enough information about X"`、`"I don't know if it improves"` 这种合法叙述会被整段判成 refusal，可答样本被误算成 over_refusal。
- 建议：限定整句开头匹配 / 分句级匹配，或暴露开关让用户自定义短语集合。

### 4. `hallucination_rate` 命名误导

- 位置：`app/faithfulness.py:103`、`app/evaluator.py`、`app/external_eval.py`、CSV 字段、报告模板
- 现状：`hallucination_rate = 1 - support_rate`，本质是"未被关键词证据覆盖的 claim 比例"，不是真正的幻觉率。
- 影响：论文 / 答辩时容易被审稿人挑战；README 已经声明这是 proxy，但代码字段名仍是 `hallucination_rate`，对外接口、CSV、报告里到处都是这个词。
- 建议：改名 `unsupported_claim_rate`，或新增 `hallucination_proxy_rate` 别名，旧字段保留兼容用于回放历史 JSON。

### 5. CJK 相似度退化为"逐字"

- 位置：`app/faithfulness.py:49-58`、`app/bm25.py:18`
- 现状：中文整段被拆成单个汉字做交集，"模型/参数/检索/向量"会大量假命中。
- 影响：中文论文场景的 `mean_support_rate` 系统性偏高。
- 建议：可选启用 jieba/pkuseg 分词；至少在 `evidence_relevance_overlap` 里限制为长度 ≥ 2 的中文 n-gram。

### 6. evidence overlap 的停用词表偏少且分叉

- 位置：`app/answerer.py:18-47`、`app/faithfulness.py:11-41`
- 现状：两个模块各维护一份停用词表，缺 `paper / model / system / question / dataset / method / based / using / according` 等高频词。
- 影响：`min_relevance_overlap` 阈值容易被无意义命中而通过，或被无关名词稀释。
- 建议：合并到 `app/faithfulness.py` 暴露常量，提供注入接口；并把英文常见学术功能词补齐。

---

## 二、性能 / 扩展性

### 7. 检索每次请求都全量重读 + 重算

- 位置：
  - `app/search.py:27-67`（`iter_indexable_chunks`）
  - `app/bm25.py:60-78`（每次请求重算 DF/IDF）
  - `app/answerer.py:94-113`（`_load_evidence_texts` 是 O(citations × all_chunks) 扫描）
- 影响：知识库到几十篇 PDF 后延迟肉眼可见。
- 建议：引入轻量索引层（`Indexer` 单例），lifespan 启动时 build 一次，上传后增量更新；保存 `(doc_id, chunk_idx) -> text` 字典 + 倒排 + DF。无需引入大依赖。

### 8. PDF 上传整文件入内存

- 位置：`app/main.py:367-378`
- 现状：分块读到 `chunks: list[bytes]` 后再 `b"".join(chunks)`，又交给 `BytesIO`。
- 影响：并发时内存占用 ≈ 并发数 × 文件大小 × 2。
- 建议：改用 `tempfile.SpooledTemporaryFile`，让 `pypdf` 直接读文件路径或流。

### 9. `/api/experiments` 没有分页

- 位置：`app/main.py:245-280`
- 现状：一次把所有 `*.json` 全部读出再排序。
- 影响：实验记录多了之后页面会卡。
- 建议：加 `?limit&offset` 或时间窗参数。

---

## 三、健壮性 / 一致性

### 10. PDF 校验只看后缀

- 位置：`app/main.py:363-365`
- 现状：仅 `endswith(".pdf")`，未校验 magic bytes。
- 建议：加一行 `if not raw.startswith(b"%PDF-"): raise HTTPException(...)`，几乎零成本。

### 11. Doubao 调用没有重试 / 没有 best-effort 模式

- 位置：`app/llm_client.py:62-83`、`app/evaluator.py:91-105`
- 现状：一次失败直接 `LLMRequestError`；批量评测里任意一条失败会整批 502。
- 建议：
  - 对 5xx / 网络错误加 1-2 次指数退避重试；
  - 批量评测增加 `continue_on_error=True` 选项，把失败样本标 `error: ...`，避免几十分钟的运行被一条网络抖动整掉。

### 12. logging 未在启动时配置

- 位置：`app/main.py`、各模块的 `logging.getLogger(__name__)`
- 现状：未在 `lifespan` / `basicConfig` 配置 handler 与格式，应用日志默认不会出现在标准输出。
- 建议：写 `app/logging_config.py`，由 `lifespan` 调用一次。

### 13. dotenv 是手写最小实现

- 位置：`app/config.py:14-26`
- 现状：不支持转义、引号内空格、`export KEY=...`。
- 建议：直接依赖 `python-dotenv`，或保留手写但加注释说明边界。

### 14. `min_support_rate` 在 `/api/answer` 里没做范围校验

- 位置：`app/main.py:320-323`（仅校验类型，未限制 0-1）
- 对比：`app/main.py:213` 在 `/api/evaluate/answers` 里校验了。
- 影响：两套接口校验不一致。
- 建议：迁移到 Pydantic 模型，统一约束（同时解决很多重复 if）。

### 15. answerer 在 doubao 失败路径没有 fallback

- 位置：`app/answerer.py:171-182`
- 现状：Doubao 抛错就整体 raise，dashboard 不会展示 fallback 的 extractive 结果。
- 建议：增加可选参数 `fallback_to_extractive=True`。

---

## 四、工程结构 / 可维护性

### 16. `app/main.py` 单文件 468 行

- 现状：路由 + 业务逻辑 + 持久化都堆在一起（`_persist_answer_experiment`、`_evaluate_answers_payload`、`_load_doc_metadata_path` 与路由混在一起）。
- 建议：
  - `app/routes/`：各模块路由
  - `app/services/experiments.py`：持久化与列表
  - `app/schemas.py`：全部 Pydantic 模型
  - 预计能少 ~60 行重复 if 校验，每个接口可压到 < 25 行。

### 17. 全部接口手写 dict 校验，未用 Pydantic

- 位置：`/api/answer`、`/api/evaluate/answers`、`/api/evaluate/external-answers`
- 现状：各自写了一遍 `if not isinstance(...)`，规则还互相不一致（见 #14）。
- 建议：改成 BaseModel + Field 校验后能减少重复，且自动生成 OpenAPI schema、自动 422 错误带 location，单元测试更短。

### 18. `app/__init__.py` 当前 git diff 只是加了一行空行

- 位置：`app/__init__.py`
- 建议：按 AGENTS.md 的"无关改动"原则，要么 `git checkout app/__init__.py` 回滚，要么改成有意义的 `__version__ = "0.1.0"`。

### 19. 项目根路径多次重复

- 位置：`app/main.py:25-31`、`app/config.py:10`
- 现状：`Path(__file__).resolve().parent.parent` 在多处重复出现，已经有 `PROJECT_ROOT` 常量。
- 建议：main.py 直接复用 `app.config.PROJECT_ROOT`。

### 20. 前端 929 行单文件

- 位置：`app/static/index.html`
- 现状：同时含 ~210 行 CSS、~700 行 JS，大量字符串拼 HTML。
- 建议：
  - 拆出 `dashboard.js`、`dashboard.css`，由 `app/main.py` 通过 `StaticFiles` 挂载；
  - `dashboard()` 改用 `FileResponse(path)`，可启用 ETag / Last-Modified 浏览器缓存。

### 21. 缺少 lint / type-check / pre-commit / CI

- `requirements.txt` 没区分 dev/prod。
- 建议：
  - 加 `requirements-dev.txt`：ruff、mypy（或 pyright）、pre-commit；
  - 配 `[tool.ruff]`，扫一遍能发现重复校验、未用导入；
  - 加 `.github/workflows/test.yml` 跑 `pytest -q`，避免 README 里 "112 passed" 靠人手维护。

### 22. 没有 API 版本前缀

- 现状：所有接口都是 `/api/...`。
- 建议：早期就拆出 `/api/v1/`，未来破坏性变更可分流。

---

## 五、检索 / 算法层面（论文价值更高）

### 23. 没有向量检索

- 现状：仅 `keyword` + `bm25`。
- 影响：改写句、近义、跨语言查询时 BM25 召回明显劣化。
- 建议：可选 `method=embedding`，用 `sentence-transformers` 的 `paraphrase-multilingual-MiniLM-L12-v2`（轻量、CPU 即可）+ FAISS 内存索引。
- 给毕设论文直接增加一组「BM25 vs Dense vs Hybrid」对比图。

### 24. 文本切分按字符固定窗口

- 位置：`app/text_chunker.py`
- 现状：1200 字符 / 150 重叠的硬切。
- 影响：论文跨段、跨章节会被切碎。
- 建议：先按 `\n\n` / 段落分，长段再二次切；保留 `start_char`、`page_no`（`pypdf` 拿得到），引用更精准。

### 25. 没有文档去重 / 没有删除接口

- 现状：同一个 PDF 上传两次会产生两份 doc。
- 建议：上传时基于 `sha256(raw)` 做秒传；增加 `DELETE /api/documents/{id}`，dashboard 即可管理库。

### 26. 阈值 sweep 工具缺失

- 现状：README 推荐 `min_support_rate=0.5`、`min_relevance_overlap=0.35`，但没给"为什么是这两个数"的脚本。
- 建议：写 sweep 脚本，在已有评测集上扫 [0.1, 0.9]，画 PR / refusal_accuracy vs over_refusal_rate 曲线，自动选最优阈值——直接放进毕设实验小节。

### 27. demo 数据集多 provider 标签的展示风险

- 位置：`datasets/demo_external_eval_cases.json`、dashboard `aggregate.by_model` 表格
- 现状：README 已强调标签是元数据，但 dashboard 上仍按"模型对比"渲染，对外演示时易让人误解为真实排名。
- 建议：在前端表头加一行小字提醒「provider/model 标签可能仅为元数据，详见 README」。

---

## 六、可以快速做的体验提升

### 28. dashboard

- 位置：`app/static/index.html:477-491` 等
- 上传按钮无 disabled / loading state，网慢时容易重复点。
- 检索结果 `text_preview` 没有查询词高亮。
- 没有"删除文档"按钮（呼应 #25）。
- 实验列表无分页（呼应 #9）。
- 状态：核心体验项已完成；剩余可继续补统一错误提示、实验记录总数显示和更多筛选。

### 29. README 双语维护漂移风险

- 位置：`README.md` 与 `README.en.md`
- 现状：没有自动同步机制，中文版已 426 行，未来漂移概率高。
- 建议：英文版改成更短的"快速 5 行 + 链接到中文版/docs"，或加一个 `scripts/check_readme_sync.py`。
- 另：README 第 99 行的依赖列表是手抄 `requirements.txt`，已经少了 `python-multipart` 之外字段，建议改成 CI 校验或直接引用文件。
- 状态：中英文 README 已同步本轮实际 API、目录结构和验证基线；尚未新增自动同步脚本。

---

## 优先级建议

当前高优先级已经从“修正核心指标/拆分结构”转为“补齐可选增强和工程收尾”：

1. **#23 Dense / Hybrid 检索**：先确认依赖体积、模型下载和离线策略，再实现 `method=dense|hybrid` 对比基线。
2. **#21 开发质量工具落地**：安装 dev 依赖并运行 ruff / mypy / pre-commit，根据结果做最小修复。
3. **#17 FastAPI 原生 schema 迁移**：如果可以接受部分错误码从 400 迁到 422，再把请求体切到原生 Pydantic body schema。
4. **#28 dashboard 小体验**：核心项已完成，后续可按展示需要追加更多筛选条件和图表。
5. **收尾清理**：为可选 dense 模式补 README 说明，并清理本地 pytest 权限临时目录等环境噪声。

---

## 未发现的"阻塞性"问题

- 当前没有观察到新的逻辑阻塞点；核心路径已有测试覆盖，最新全量 pytest 基线为 `135 passed`。
- 本地 `git status` 仍可能提示 `pytest-cache-files-*` 权限目录，这是 Windows pytest 临时目录 ACL 噪声，不属于业务代码；未在本文件中建议自动删除，避免误删用户环境文件。

---

## 残余风险

- 上述 #1 ~ #6 修复后，关键词代理指标仍是代理；要真正声明"幻觉抑制"效果，最终需要 LLM-as-judge 或人工抽样复核（README 已经提及，应在论文局限性中保留）。
- #7 内存索引若不加 mtime 失效或上传钩子，多进程部署时会出现数据不同步；该问题在单进程 uvicorn 下不存在。
- #23 引入 sentence-transformers 会显著增大依赖体积（~500MB 模型权重首跑下载），需在 README 标注离线/在线两种模式。
