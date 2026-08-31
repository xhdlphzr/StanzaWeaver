# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Flask 路由集成测试（不依赖 OpenAI，仅验证 HTTP 层与本地访问守卫）。

借助 Flask 测试客户端发起请求；CSRF 守卫按设计需携带 X-CSRF-Token。
"""

from collections.abc import Iterator

import pytest
from flask.testing import FlaskClient

import app as app_module


@pytest.fixture()
def client() -> Iterator[FlaskClient]:
    """提供 Flask 测试客户端。

    Yields:
        配置好 testing 模式的 FlaskClient。
    """
    app_module.app.testing = True
    with app_module.app.test_client() as c:
        yield c


def _csrf() -> dict[str, str]:
    """构造 CSRF 请求头。

    Returns:
        {"X-CSRF-Token": ...} 字典。
    """
    return {"X-CSRF-Token": app_module._CSRF_TOKEN}


def test_index_page(client: FlaskClient) -> None:
    """验证 index page。"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "StanzaWeaver" in resp.get_data(as_text=True)


def test_templates_endpoint(client: FlaskClient) -> None:
    """验证 templates endpoint。"""
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    keys = {t["key"] for t in data}
    assert "zh_wujue" in keys


def test_import_status_endpoint(client: FlaskClient) -> None:
    """验证 import status endpoint。"""
    resp = client.get("/api/import-status")
    assert resp.status_code == 200
    assert "importing" in resp.get_json()


def test_llm_status_endpoint(client: FlaskClient) -> None:
    """验证 LLM 连通状态 endpoint。"""
    resp = client.get("/api/llm-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "writer" in data and "checker" in data
    assert data["writer"] in ("unknown", "checking", "ok", "error")
    assert data["checker"] in ("unknown", "checking", "ok", "error")


def test_llm_ping_requires_csrf(client: FlaskClient) -> None:
    """验证手动 ping 需要 CSRF 令牌。"""
    assert client.post("/api/llm-ping").status_code == 403
    resp = client.post("/api/llm-ping", headers=_csrf())
    assert resp.status_code == 200
    data = resp.get_json()
    assert "writer" in data and "checker" in data


def test_config_requires_csrf(client: FlaskClient) -> None:
    """验证 config requires csrf。"""
    assert client.get("/api/config").status_code == 403
    resp = client.get("/api/config", headers=_csrf())
    assert resp.status_code == 200
    data = resp.get_json()
    assert "writer" in data and "checker" in data


def test_history_get(client: FlaskClient) -> None:
    """验证 history get。"""
    resp = client.get("/api/history")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_history_post_requires_csrf(client: FlaskClient) -> None:
    """验证 history post requires csrf。"""
    assert (
        client.post("/api/history", json={"topic": "t", "poem": "p"}).status_code == 403
    )
    resp = client.post(
        "/api/history",
        json={"topic": "t", "template_name": "x", "poem": "p"},
        headers=_csrf(),
    )
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "ok"
