const pretty = (value) => JSON.stringify(value, null, 2);
const API_BASE = "/api/v1";
const EXPERIMENT_PAGE_SIZE = 10;

function apiPath(path) {
  return `${API_BASE}${path}`;
}

    let lastAnswerPayload = null;
    let experimentOffset = 0;

    function normalizeErrorBody(body) {
      if (body && typeof body === "object") {
        const detail = body.detail;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
          return detail.map((item) => item.msg || pretty(item)).join("; ");
        }
        return pretty(body);
      }
      return String(body || "请求失败");
    }

    function setOutputText(output, text, isError = false) {
      output.textContent = text;
      output.classList.toggle("output-error", isError);
    }

    function setOutputHtml(output, html, isError = false) {
      output.innerHTML = html;
      output.classList.toggle("output-error", isError);
    }

    function showOutputError(output, error, action) {
      const message = error && error.message ? error.message : String(error || "未知错误");
      setOutputText(output, `${action}失败：${message}`, true);
    }

    async function requestJson(url, options) {
      const response = await fetch(url, options);
      const text = await response.text();
      let body;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = text;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${normalizeErrorBody(body)}`);
      }
      return body;
    }

    function escapeRegExp(value) {
      return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function searchTerms(query) {
      const terms = String(query || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean);
      return [...new Set(terms)].sort((a, b) => b.length - a.length);
    }

    function highlightText(text, terms) {
      if (!terms.length) return escHtml(text);
      const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
      const lowerTerms = new Set(terms.map((term) => term.toLowerCase()));
      return String(text || "")
        .split(pattern)
        .map((part) =>
          lowerTerms.has(part.toLowerCase()) ? `<mark class="search-hit">${escHtml(part)}</mark>` : escHtml(part)
        )
        .join("");
    }

    function renderSearchResults(body, query) {
      const output = document.getElementById("search-output");
      const results = Array.isArray(body && body.results) ? body.results : [];
      if (!results.length) {
        setOutputHtml(output, `<div class="muted">No results for ${escHtml(query || "")}</div>`);
        return;
      }
      const terms = searchTerms(query);
      setOutputHtml(output, `
        <div class="search-summary">query=${escHtml(body.query)} 路 method=${escHtml(body.method)} 路 top_k=${escHtml(body.top_k)}</div>
        <div class="search-result-list">
          ${results.map((row) => `
            <article class="search-result-card">
              <div><strong>${escHtml(row.original_filename || row.document_id)}</strong></div>
              <div class="muted">doc=${escHtml(row.document_id)} 路 chunk=${escHtml(row.chunk_index)} 路 score=${escHtml(row.score)}</div>
              <p>${highlightText(row.text_preview || "", terms)}</p>
            </article>
          `).join("")}
        </div>
      `);
    }

    function updateExperimentPager(rowCount, totalCount) {
      const status = document.getElementById("experiments-page-status");
      const prev = document.getElementById("experiments-prev");
      const next = document.getElementById("experiments-next");
      if (!status || !prev || !next) return;
      const page = Math.floor(experimentOffset / EXPERIMENT_PAGE_SIZE) + 1;
      const start = totalCount > 0 ? experimentOffset + 1 : 0;
      const end = totalCount > 0 ? experimentOffset + rowCount : 0;
      status.textContent = `Page ${page} · showing ${start}-${end} of ${totalCount}`;
      prev.disabled = experimentOffset === 0;
      next.disabled = experimentOffset + rowCount >= totalCount;
    }

    async function loadDocuments() {
      const list = document.getElementById("documents-list");
      const docs = await requestJson(apiPath("/documents"));
      if (!docs.length) {
        setOutputHtml(list, "<div class='muted'>暂无文档</div>");
        return;
      }
      setOutputHtml(list, docs.map((doc) => `
        <div class="item">
          <strong>${doc.original_filename || doc.id}</strong>
          <div class="muted">${doc.chunk_count || 0} chunks · ${doc.char_count || 0} chars</div>
          <div class="muted">${doc.id}</div>
          <div class="item-actions">
            <button type="button" class="danger delete-document" data-doc-id="${doc.id}">删除文档</button>
          </div>
        </div>
      `).join(""));
    }

    document.getElementById("upload-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const output = document.getElementById("upload-output");
      const submit = event.currentTarget.querySelector('button[type="submit"]');
      const file = document.getElementById("pdf-file").files[0];
      const data = new FormData();
      data.append("file", file);
      setOutputText(output, "Uploading...");
      submit.disabled = true;
      try {
        const body = await requestJson(apiPath("/documents/upload"), { method: "POST", body: data });
        setOutputText(output, pretty(body));
        await loadDocuments();
      } catch (error) {
        showOutputError(output, error, "上传");
      } finally {
        submit.disabled = false;
      }
    });

    document.getElementById("refresh-documents").addEventListener("click", loadDocuments);

    document.getElementById("documents-list").addEventListener("click", async (event) => {
      const button = event.target.closest(".delete-document");
      if (!button) return;
      const docId = button.getAttribute("data-doc-id");
      if (!window.confirm(`Delete document ${docId}?`)) return;
      const output = document.getElementById("upload-output");
      button.disabled = true;
      setOutputText(output, "Deleting...");
      try {
        setOutputText(output, pretty(await requestJson(apiPath(`/documents/${encodeURIComponent(docId)}`), { method: "DELETE" })));
        await loadDocuments();
      } catch (error) {
        showOutputError(output, error, "删除文档");
        button.disabled = false;
      }
    });

    document.getElementById("run-search").addEventListener("click", async () => {
      const q = document.getElementById("search-query").value;
      const topK = document.getElementById("top-k").value || "5";
      const output = document.getElementById("search-output");
      setOutputText(output, "Searching...");
      try {
        const body = await requestJson(apiPath(`/search?q=${encodeURIComponent(q)}&top_k=${encodeURIComponent(topK)}`));
        renderSearchResults(body, q);
      } catch (error) {
        showOutputError(output, error, "检索");
      }
    });

    document.getElementById("run-answer").addEventListener("click", async () => {
      const output = document.getElementById("answer-output");
      setOutputText(output, "Answering...");
      try {
        const body = await requestJson(apiPath("/answer"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: document.getElementById("answer-question").value,
            method: document.getElementById("answer-method").value,
            generator: document.getElementById("answer-generator").value,
            top_k: Number(document.getElementById("answer-top-k").value || 5),
            min_support_rate: Number(document.getElementById("answer-min-support").value || 0.5)
          })
        });
        lastAnswerPayload = body;
        setOutputText(output, pretty(body));
      } catch (error) {
        showOutputError(output, error, "生成答案");
      }
    });

    document.getElementById("run-faithfulness").addEventListener("click", async () => {
      const output = document.getElementById("answer-output");
      if (!lastAnswerPayload) {
        setOutputText(output, "请先生成一次证据回答。", true);
        return;
      }
      setOutputText(output, "Evaluating faithfulness...");
      try {
        const result = await requestJson(apiPath("/evaluate/faithfulness"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            answer: lastAnswerPayload.answer,
            citations: lastAnswerPayload.citations
          })
        });
        setOutputText(output, pretty({ answer: lastAnswerPayload, faithfulness: result }));
      } catch (error) {
        showOutputError(output, error, "评估答案可靠性");
      }
    });

    document.getElementById("run-eval").addEventListener("click", async () => {
      const output = document.getElementById("eval-output");
      setOutputText(output, "Evaluating...");
      try {
        const payload = JSON.parse(document.getElementById("eval-cases").value);
        setOutputText(output, pretty(await requestJson(apiPath("/evaluate/retrieval"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        })));
      } catch (error) {
        showOutputError(output, error, "运行检索评测");
      }
    });

    document.getElementById("run-answer-eval").addEventListener("click", async () => {
      const output = document.getElementById("answer-eval-output");
      setOutputText(output, "Evaluating answers...");
      try {
        const payload = JSON.parse(document.getElementById("answer-eval-cases").value);
        payload.save = document.getElementById("answer-eval-save").checked;
        setOutputText(output, pretty(await requestJson(apiPath("/evaluate/answers"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        })));
      } catch (error) {
        showOutputError(output, error, "运行答案评测");
      }
    });

    document.getElementById("download-answer-eval-csv").addEventListener("click", async () => {
      const output = document.getElementById("answer-eval-output");
      setOutputText(output, "Generating CSV...");
      try {
        const payload = JSON.parse(document.getElementById("answer-eval-cases").value);
        const response = await fetch(apiPath("/evaluate/answers/export"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const text = await response.text();
        if (!response.ok) {
          let errBody;
          try {
            errBody = text ? JSON.parse(text) : null;
          } catch {
            errBody = text;
          }
          throw new Error(`HTTP ${response.status}: ${normalizeErrorBody(errBody)}`);
        }
        const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "answer_evaluation.csv";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
        setOutputText(output, "已开始下载 CSV（answer_evaluation.csv）。");
      } catch (error) {
        showOutputError(output, error, "下载评测 CSV");
      }
    });

    async function loadExperiments() {
      const list = document.getElementById("experiments-list");
      const page = await requestJson(apiPath(`/experiments?limit=${EXPERIMENT_PAGE_SIZE}&offset=${experimentOffset}&include_total=true`));
      const rows = Array.isArray(page) ? page : page.items;
      const safeRows = Array.isArray(rows) ? rows : [];
      const total = Array.isArray(page) ? safeRows.length : Number(page.total || 0);
      updateExperimentPager(safeRows.length, total);
      if (!safeRows.length) {
        setOutputHtml(list, "<div class='muted'>暂无已保存实验</div>");
        return;
      }
      setOutputHtml(list, safeRows.map((row) => {
        const rid = row.run_id;
        const escape = (s) =>
          String(s ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/"/g, "&quot;");
        return `
        <div class="item experiment-row" data-run-id="${escape(rid)}"
             role="button" tabindex="0" aria-label="查看实验 ${escape(rid)}">
          <div><strong>${escape(rid)}</strong></div>
          <div class="muted">${escape(row.created_at)} · ${escape(row.method)} · ${escape(row.generator)} · top_k=${escape(row.top_k)}</div>
          <div class="muted">total=${escape(row.total)} · mean_support=${escape(row.mean_support_rate)} · mean_hallucination=${escape(row.mean_hallucination_rate)}</div>
        </div>`;
      }).join(""));
    }

    /** Saved answer-eval experiment viz (dashboard smoke: renderSavedExperimentViz) */
    function fmtExperimentDash(v) {
      if (v === null || v === undefined) return "-";
      if (v === "") return "-";
      if (typeof v === "number" && Number.isNaN(v)) return "-";
      return null;
    }

    function fmtExperimentScalarForHtml(v) {
      const d = fmtExperimentDash(v);
      if (d !== null) return d;
      if (typeof v === "boolean") return v ? "是" : "否";
      if (typeof v === "number" && Number.isInteger(v)) return escHtml(String(v));
      if (typeof v === "number") return v.toFixed(4);
      return escHtml(String(v));
    }

    function rateBarParts(value) {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return { pct: 0, text: "-" };
      }
      return {
        pct: Math.min(100, Math.max(0, value * 100)),
        text: value.toFixed(4),
      };
    }

    function appendExperimentRateBars(container, title, rowsSpec) {
      if (title) {
        const h = document.createElement("h3");
        h.textContent = title;
        container.appendChild(h);
      }
      for (const spec of rowsSpec) {
        const { pct, text } = rateBarParts(spec.value);
        const rowEl = document.createElement("div");
        rowEl.className = "metric-bar-row";
        const fill = spec.fillClass || "";
        rowEl.innerHTML = `
          <label>${escHtml(spec.label)}</label>
          <div class="metric-bar-track" aria-hidden="true"><div class="metric-bar-fill ${fill}" style="width:${pct}%"></div></div>
          <span class="metric-bar-val">${escHtml(text)}</span>
        `;
        container.appendChild(rowEl);
      }
    }

    function cellCitationHit(row) {
      if (!row || typeof row !== "object") return "-";
      if (row.answerable !== true) return "-";
      if (row.hit === true) return "是";
      if (row.hit === false) return "否";
      return "-";
    }

    function cellRefused(row) {
      if (!row || typeof row !== "object") return "-";
      if (row.answerable !== false) return "-";
      if (row.refusal_correct === true) return "是";
      if (row.refusal_correct === false) return "否";
      return "-";
    }

    function renderExperimentRiskTips(agg, rows) {
      const lines = [];
      const mh = Number(agg.mean_hallucination_rate);
      if (!Number.isNaN(mh) && mh >= 0.25) {
        lines.push("平均幻觉率偏高：建议核对证据覆盖与生成是否越界。");
      }
      const ut = Number(agg.unanswerable_total);
      const ra = Number(agg.refusal_accuracy);
      if (ut > 0 && !Number.isNaN(ra) && ra < 0.6) {
        lines.push("拒答准确率偏低：不可答用例上可能误答或拒答表述不稳定。");
      }
      const at = Number(agg.answerable_total);
      const chr = Number(agg.citation_hit_rate);
      if (at > 0 && !Number.isNaN(chr) && chr < 0.7) {
        lines.push("可答引用命中率偏低：检索、引用对齐或回答策略可能偏保守（过度拒答风险）。");
      }
      if (Array.isArray(rows) && at > 0) {
        let suspicious = 0;
        for (const r of rows) {
          if (r && r.answerable === true && r.hit === false) {
            const sr = Number(r.support_rate);
            if (!Number.isNaN(sr) && sr < 0.35) suspicious += 1;
          }
        }
        const ratio = suspicious / at;
        if (suspicious >= 2 || ratio >= 0.3) {
          lines.push("多条可答案例支持率偏低且未命中预期引用：可能存在过度拒答或证据不足。");
        }
      }
      if (!lines.length) {
        lines.push("未触发常见风险阈值；仍请结合 JSON 与场景人工复核。");
      }
      return lines.map((t) => `<div>${escHtml(t)}</div>`).join("");
    }

    function renderSavedExperimentViz(detail) {
      const wrap = document.getElementById("experiment-detail-viz-wrap");
      const aggOut = document.getElementById("experiment-detail-aggregate");
      const barsOut = document.getElementById("experiment-detail-bars");
      const tbody = document.querySelector("#experiment-detail-cases tbody");
      const risksOut = document.getElementById("experiment-detail-risks");

      if (!detail || typeof detail !== "object" || !aggOut || !barsOut || !tbody || !risksOut) {
        if (wrap) wrap.hidden = true;
        return;
      }

      const agg = detail.aggregate;
      if (!agg || typeof agg !== "object") {
        wrap.hidden = true;
        return;
      }

      wrap.hidden = false;

      const fmtAgg = (key) => fmtExperimentScalarForHtml(agg[key]);

      aggOut.innerHTML = `
        <dl>
          <dt>total</dt><dd>${fmtAgg("total")}</dd>
          <dt>answerable_total</dt><dd>${fmtAgg("answerable_total")}</dd>
          <dt>unanswerable_total</dt><dd>${fmtAgg("unanswerable_total")}</dd>
          <dt>answerable_hits</dt><dd>${fmtAgg("answerable_hits")}</dd>
          <dt>citation_hit_rate</dt><dd>${fmtAgg("citation_hit_rate")}</dd>
          <dt>refusal_correct_count</dt><dd>${fmtAgg("refusal_correct_count")}</dd>
          <dt>refusal_accuracy</dt><dd>${fmtAgg("refusal_accuracy")}</dd>
          <dt>mean_support_rate</dt><dd>${fmtAgg("mean_support_rate")}</dd>
          <dt>mean_hallucination_rate</dt><dd>${fmtAgg("mean_hallucination_rate")}</dd>
        </dl>
      `;

      barsOut.innerHTML = "";
      appendExperimentRateBars(barsOut, "mean_support_rate / mean_hallucination_rate", [
        { label: "mean_support_rate", value: agg.mean_support_rate, fillClass: "" },
        { label: "mean_hallucination_rate", value: agg.mean_hallucination_rate, fillClass: "alt-a" },
      ]);
      const unans = agg.unanswerable_total;
      const refAcc = agg.refusal_accuracy;
      const refAccNum = typeof refAcc === "number" && !Number.isNaN(refAcc) ? refAcc : null;
      const showRef = typeof unans === "number" && unans > 0 && refAccNum !== null;
      appendExperimentRateBars(barsOut, "citation_hit_rate / refusal_accuracy", [
        { label: "citation_hit_rate", value: agg.citation_hit_rate, fillClass: "alt-b" },
        {
          label: "refusal_accuracy",
          value: showRef ? refAccNum : null,
          fillClass: "alt-c",
        },
      ]);

      const rows = detail.rows;
      if (!Array.isArray(rows) || !rows.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="muted">无用例数据</td></tr>`;
      } else {
        tbody.innerHTML = rows.map((row) => {
          const qRaw = row && typeof row.question === "string" ? row.question : "";
          const qShort = qRaw.length > 72 ? `${qRaw.slice(0, 72)}…` : qRaw;
          return `
            <tr>
              <td class="q-cell" title="${escHtml(qRaw)}">${escHtml(qShort || "-")}</td>
              <td>${fmtExperimentScalarForHtml(row && row.answerable)}</td>
              <td>${escHtml(cellCitationHit(row))}</td>
              <td>${escHtml(cellRefused(row))}</td>
              <td>${fmtExperimentScalarForHtml(row && row.support_rate)}</td>
              <td>${fmtExperimentScalarForHtml(row && row.hallucination_rate)}</td>
              <td>${fmtExperimentScalarForHtml(row && row.reliable)}</td>
            </tr>
          `;
        }).join("");
      }

      risksOut.innerHTML = renderExperimentRiskTips(agg, Array.isArray(rows) ? rows : []);
    }

    function bindExperimentRows() {
      const list = document.getElementById("experiments-list");
      list.addEventListener("click", async (event) => {
        const row = event.target.closest(".experiment-row");
        if (!row) return;
        const runId = row.getAttribute("data-run-id");
        const out = document.getElementById("experiment-detail-output");
        const vizWrap = document.getElementById("experiment-detail-viz-wrap");
        setOutputText(out, "Loading...");
        if (vizWrap) vizWrap.hidden = true;
        try {
          const detail = await requestJson(apiPath(`/experiments/${encodeURIComponent(runId)}`));
          setOutputText(out, pretty(detail));
          renderSavedExperimentViz(detail);
        } catch (error) {
          showOutputError(out, error, "加载实验详情");
          if (vizWrap) vizWrap.hidden = true;
        }
      });
      list.addEventListener("keydown", (event) => {
        const row = event.target.closest(".experiment-row");
        if (!row || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        row.click();
      });
    }

    bindExperimentRows();

    const externalEvalApiPath = apiPath("/evaluate/external-answers");
    const externalEvalDemoPath = apiPath("/demo/external-eval");

    function escHtml(s) {
      return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/"/g, "&quot;");
    }

    function approxEq(a, b) {
      return Math.abs(Number(a) - Number(b)) < 1e-9;
    }

    function computeModelHighlights(byModel) {
      const entries = Object.entries(byModel || {});
      if (!entries.length) {
        return { lowHall: [], highRefusalAcc: [], highOverRefusal: [] };
      }
      let minH = Infinity;
      let maxR = -Infinity;
      let maxO = -Infinity;
      for (const [, v] of entries) {
        minH = Math.min(minH, Number(v.mean_hallucination_rate ?? 0));
        maxR = Math.max(maxR, Number(v.refusal_accuracy ?? 0));
        maxO = Math.max(maxO, Number(v.over_refusal_rate ?? 0));
      }
      return {
        lowHall: entries.filter(([, v]) => approxEq(v.mean_hallucination_rate ?? 0, minH)).map(([k]) => k),
        highRefusalAcc: entries.filter(([, v]) => approxEq(v.refusal_accuracy ?? 0, maxR)).map(([k]) => k),
        highOverRefusal: entries.filter(([, v]) => approxEq(v.over_refusal_rate ?? 0, maxO)).map(([k]) => k),
      };
    }

    function renderMetricBarBlock(byModel, metricKey, title, fillClass) {
      const keys = Object.keys(byModel || {}).sort();
      const vals = keys.map((k) => Number(byModel[k][metricKey] ?? 0));
      const denom = Math.max(1e-9, ...vals, 1e-9);
      const wrap = document.createElement("div");
      const h = document.createElement("h3");
      h.textContent = title;
      wrap.appendChild(h);
      keys.forEach((key) => {
        const v = Number(byModel[key][metricKey] ?? 0);
        const pct = Math.min(100, Math.max(0, (v / denom) * 100));
        const row = document.createElement("div");
        row.className = "metric-bar-row";
        row.innerHTML = `
          <label title="${escHtml(key)}">${escHtml(key)}</label>
          <div class="metric-bar-track" aria-hidden="true"><div class="metric-bar-fill ${fillClass}" style="width:${pct}%"></div></div>
          <span class="metric-bar-val">${v.toFixed(4)}</span>
        `;
        wrap.appendChild(row);
      });
      return wrap;
    }

    function renderExternalEvalViz(body) {
      const wrap = document.getElementById("external-eval-aggregate-wrap");
      const aggOut = document.getElementById("external-eval-aggregate");
      const hiOut = document.getElementById("external-eval-highlights");
      const barsOut = document.getElementById("external-eval-bars");
      const tbody = document.querySelector("#external-eval-by-model tbody");

      const agg = body && body.aggregate;
      const byModel = agg && agg.by_model ? agg.by_model : {};

      if (!agg) {
        wrap.hidden = true;
        tbody.innerHTML = "";
        return;
      }

      wrap.hidden = false;

      const hl = computeModelHighlights(byModel);
      const fmt = (x) => (typeof x === "number" && !Number.isNaN(x) ? x.toFixed(4) : String(x));

      aggOut.innerHTML = `
        <dl>
          <dt>total</dt><dd>${escHtml(fmt(agg.total))}</dd>
          <dt>answerable_total</dt><dd>${escHtml(fmt(agg.answerable_total))}</dd>
          <dt>unanswerable_total</dt><dd>${escHtml(fmt(agg.unanswerable_total))}</dd>
          <dt>mean_support_rate</dt><dd>${escHtml(fmt(agg.mean_support_rate))}</dd>
          <dt>mean_hallucination_rate</dt><dd>${escHtml(fmt(agg.mean_hallucination_rate))}</dd>
          <dt>refusal_accuracy</dt><dd>${escHtml(fmt(agg.refusal_accuracy))}</dd>
          <dt>over_refusal_rate</dt><dd>${escHtml(fmt(agg.over_refusal_rate))}</dd>
          <dt>refusal_correct_count</dt><dd>${escHtml(fmt(agg.refusal_correct_count))}</dd>
          <dt>over_refusal_count</dt><dd>${escHtml(fmt(agg.over_refusal_count))}</dd>
          <dt>min_support_rate</dt><dd>${body.min_support_rate == null ? "null" : escHtml(fmt(body.min_support_rate))}</dd>
        </dl>
      `;

      const joinKeys = (arr) => (arr.length ? arr.map((k) => `<strong>${escHtml(k)}</strong>`).join("、") : "（无）");
      hiOut.innerHTML = `
        <div><strong>幻觉率 mean_hallucination_rate 最低：</strong>${joinKeys(hl.lowHall)}</div>
        <div><strong>拒答准确率 refusal_accuracy 最高：</strong>${joinKeys(hl.highRefusalAcc)}</div>
        <div><strong>过度拒答率 over_refusal_rate 最高：</strong>${joinKeys(hl.highOverRefusal)}</div>
      `;

      barsOut.innerHTML = "";
      barsOut.appendChild(renderMetricBarBlock(byModel, "mean_support_rate", "mean_support_rate（分模型，条长相对本组最大值）", ""));
      barsOut.appendChild(renderMetricBarBlock(byModel, "mean_hallucination_rate", "mean_hallucination_rate", "alt-a"));
      barsOut.appendChild(renderMetricBarBlock(byModel, "refusal_accuracy", "refusal_accuracy", "alt-b"));
      barsOut.appendChild(renderMetricBarBlock(byModel, "over_refusal_rate", "over_refusal_rate", "alt-c"));

      const hlH = new Set(hl.lowHall);
      const hlR = new Set(hl.highRefusalAcc);
      const hlO = new Set(hl.highOverRefusal);
      const keysSorted = Object.keys(byModel).sort();
      tbody.innerHTML = keysSorted.map((key) => {
        const m = byModel[key];
        const flags = [
          hlH.has(key) ? '<span class="muted">[低幻觉]</span>' : "",
          hlR.has(key) ? '<span class="muted">[高拒答准]</span>' : "",
          hlO.has(key) ? '<span class="muted">[高过度拒答]</span>' : "",
        ].filter(Boolean).join(" ");
        return `
          <tr>
            <td>${escHtml(key)} ${flags}</td>
            <td>${escHtml(fmt(m.total))}</td>
            <td>${escHtml(fmt(m.answerable_total))}</td>
            <td>${escHtml(fmt(m.unanswerable_total))}</td>
            <td>${escHtml(fmt(m.mean_support_rate))}</td>
            <td>${escHtml(fmt(m.mean_hallucination_rate))}</td>
            <td>${escHtml(fmt(m.refusal_accuracy))}</td>
            <td>${escHtml(fmt(m.over_refusal_rate))}</td>
          </tr>
        `;
      }).join("");
    }

    document.getElementById("load-external-eval-demo").addEventListener("click", async () => {
      const rawOut = document.getElementById("external-eval-raw-output");
      const casesTa = document.getElementById("external-eval-cases");
      setOutputText(rawOut, "载入中…");
      document.getElementById("external-eval-aggregate-wrap").hidden = true;
      try {
        const data = await requestJson(externalEvalDemoPath, { method: "GET" });
        casesTa.value = pretty(data);
        setOutputText(rawOut, "已载入内置 Demo，可直接运行批量评测。");
      } catch (error) {
        showOutputError(rawOut, error, "载入 Demo");
      }
    });

    document.getElementById("run-external-eval").addEventListener("click", async () => {
      const rawOut = document.getElementById("external-eval-raw-output");
      setOutputText(rawOut, "评测中…");
      document.getElementById("external-eval-aggregate-wrap").hidden = true;
      try {
        const payload = JSON.parse(document.getElementById("external-eval-cases").value);
        const body = await requestJson(externalEvalApiPath, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setOutputText(rawOut, pretty(body));
        renderExternalEvalViz(body);
      } catch (error) {
        showOutputError(rawOut, error, "运行外部答案批量评测");
        document.getElementById("external-eval-aggregate-wrap").hidden = true;
      }
    });

    document.getElementById("refresh-experiments").addEventListener("click", () => {
      experimentOffset = 0;
      const list = document.getElementById("experiments-list");
      setOutputHtml(list, "<div class='muted'>Loading...</div>");
      loadExperiments().catch((error) => {
        setOutputHtml(list, `<div class="muted">${escHtml(error.message)}</div>`, true);
      });
    });

    document.getElementById("experiments-prev").addEventListener("click", () => {
      experimentOffset = Math.max(0, experimentOffset - EXPERIMENT_PAGE_SIZE);
      const list = document.getElementById("experiments-list");
      setOutputHtml(list, "<div class='muted'>Loading...</div>");
      loadExperiments().catch((error) => {
        setOutputHtml(list, `<div class="muted">${escHtml(error.message)}</div>`, true);
      });
    });

    document.getElementById("experiments-next").addEventListener("click", () => {
      experimentOffset += EXPERIMENT_PAGE_SIZE;
      const list = document.getElementById("experiments-list");
      setOutputHtml(list, "<div class='muted'>Loading...</div>");
      loadExperiments().catch((error) => {
        setOutputHtml(list, `<div class="muted">${escHtml(error.message)}</div>`, true);
      });
    });

    loadDocuments().catch((error) => {
      setOutputHtml(document.getElementById("documents-list"), `<div class="muted">${escHtml(error.message)}</div>`, true);
    });

    loadExperiments().catch((error) => {
      setOutputHtml(document.getElementById("experiments-list"), `<div class='muted'>${escHtml(error.message)}</div>`, true);
    });
