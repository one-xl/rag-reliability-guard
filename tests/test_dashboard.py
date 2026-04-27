"""Dashboard smoke tests."""

from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_serves_html():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "上传 PDF" in body
    assert "刷新文档列表" in body
    assert "检索 Chunks" in body
    assert "证据回答" in body
    assert "检索评测" in body
