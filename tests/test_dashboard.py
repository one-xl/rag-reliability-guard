"""Dashboard smoke tests."""

from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_serves_html():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    js = client.get("/static/dashboard.js").text
    css = client.get("/static/dashboard.css").text
    assert 'href="/static/dashboard.css"' in body
    assert 'src="/static/dashboard.js"' in body
    assert ".external-metrics" in css
    assert ".search-hit" in css
    assert ".pager" in css
    assert ".output-error" in css
    assert 'const API_BASE = "/api/v1"' in js
    assert "showOutputError" in js
    assert "include_total=true" in js
    assert "上传 PDF" in body
    assert "刷新文档列表" in body
    assert "检索 Chunks" in body
    assert "证据回答" in body
    assert "评估答案可靠性" in body
    assert "检索评测" in body
    assert "全模型 RAG / Agent 输出评估" in body
    assert "运行外部答案批量评测" in body
    assert 'id="load-external-eval-demo"' in body
    assert "载入内置 Demo" in body
    assert "/api/v1/demo/external-eval" in body
    assert "externalEvalDemoPath" in js
    assert "load-external-eval-demo" in js
    assert 'apiPath("/evaluate/external-answers")' in js
    assert "external-eval-cases" in body
    assert "aggregate.by_model" in body
    assert 'id="experiment-detail-viz-wrap"' in body
    assert 'data-dashboard="saved-experiment-viz"' in body
    assert 'id="experiment-detail-aggregate"' in body
    assert 'id="experiment-detail-bars"' in body
    assert 'id="experiment-detail-cases"' in body
    assert 'id="experiment-detail-risks"' in body
    assert "renderSavedExperimentViz" in js
    assert "renderSearchResults" in js
    assert "highlightText" in js
    assert "experiments-prev" in body
    assert "experiments-next" in body
    assert "mean_support_rate / mean_hallucination_rate" in js
    assert "citation_hit_rate / refusal_accuracy" in js
