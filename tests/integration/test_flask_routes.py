# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Flask 路由集成测试（不依赖 OpenAI，仅验证 HTTP 层与本地访问守卫）。

借助 Flask 测试客户端发起请求；CSRF 守卫按设计需携带 X-CSRF-Token。
"""

from collections.abc import Iterator
from typing import Any

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
    assert "language" in data
    assert data["language"] in ("zh", "en")


def test_i18n_zh(client: FlaskClient) -> None:
    """验证中文翻译接口。"""
    resp = client.get("/api/i18n/zh")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "html" in data
    assert data["html"]["lang"] == "zh-CN"
    assert "generate" in data


def test_i18n_en(client: FlaskClient) -> None:
    """验证英文翻译接口。"""
    resp = client.get("/api/i18n/en")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "html" in data
    assert data["html"]["lang"] == "en"
    assert "generate" in data


def test_i18n_unknown_fallback(client: FlaskClient) -> None:
    """验证未知语言回退到中文。"""
    resp = client.get("/api/i18n/fr")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["html"]["lang"] == "zh-CN"


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


def test_templates_meta_endpoint(client: FlaskClient) -> None:
    """自定义模板 meta 应覆盖五语言并返回约束维度/可选项/辅助函数。"""
    resp = client.get("/api/templates/meta")
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data) == {"zh", "en", "fr", "it", "la"}
    assert data["zh"]["attribute"] == "tone"
    assert data["zh"]["values"] == ["平", "仄"]
    assert data["en"]["attribute"] == "stress"
    assert data["la"]["attribute"] == "length"
    assert data["fr"]["attribute"] == ""
    assert "_check_sanpingwei" in data["zh"]["helpers"]
    assert isinstance(data["zh"]["helpers"], list)


def test_custom_template_rejects_unknown_language(client: FlaskClient) -> None:
    """创建自定义模板时未知语言应返回 400。"""
    resp = client.post(
        "/api/templates/custom",
        json={
            "name": "测试",
            "language": "xx",
            "lines": 4,
            "syllables_per_line": [5, 5, 5, 5],
            "constraints": [],
            "code": "",
        },
        headers=_csrf(),
    )
    assert resp.status_code == 400


def test_build_custom_template_code_all_languages() -> None:
    """五种语言的模板源码均可编译且使用对应语言模块别名 rules。"""
    cases: list[tuple[str, str, str]] = [
        ("zh", "tone", "平"),
        ("en", "stress", "light"),
        ("it", "stress", "heavy"),
        ("la", "length", "long"),
        ("fr", "", ""),
    ]
    for lang, dimension, value in cases:
        attributes = {"tone": "", "stress": "", "length": ""}
        constraints: list[list[dict[str, Any]]] = []
        if dimension:
            attributes[dimension] = value
        constraints.append(
            [{"onset": "", "nucleus": "", "coda": "", "attributes": attributes}]
        )
        code = app_module._build_custom_template_code(
            name=f"P{lang}",
            language=lang,
            lines=1,
            syllables_per_line=[1],
            dimension=dimension,
            constraints=constraints,
            custom_code="",
            class_name=f"CustomP{lang}Template",
            file_key=f"custom_p{lang}",
        )
        compile(code, f"<custom_{lang}>", "exec")
        assert f"from . import {lang} as rules" in code
        if dimension:
            assert f'"{dimension}": "{value}"' in code
