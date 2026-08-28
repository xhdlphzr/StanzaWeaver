"""StanzaWeaver 应用入口（Flask + SocketIO + pywebview）。

- HTTP API：模板列表、LLM 配置、历史记录、自定义模板、导入状态；
- SocketIO：generate / feedback 事件驱动四步流水线，progress/done/error 推送；
- 安全：仅限本机访问（Host 校验）+ CSRF 令牌保护写接口；
- 首次运行自动导入词库（后台线程）。
"""

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit  # type: ignore[import-untyped]

from src.logging_setup import get_logger, setup_logging
from src.templates import list_dicts
from src.templates.en import register_english_templates
from src.templates.fr import register_french_templates
from src.templates.it import register_italian_templates
from src.templates.la import register_latin_templates
from src.templates.zh import register_chinese_templates

logger = get_logger(__name__)

setup_logging()

register_chinese_templates()
register_english_templates()
register_italian_templates()
register_french_templates()
register_latin_templates()

_vocab_importing = True


def _auto_import() -> None:
    """后台线程：首次运行自动导入词库。"""
    global _vocab_importing
    from src.knowledge.vocabulary import init_db

    try:
        init_db()
        logger.info("[StanzaWeaver] 检查词库...")
        from src.knowledge.importer import import_all

        import_all()
    except Exception as e:  # noqa: BLE001 - 词库导入兜底：失败仅记录，不影响启动
        logger.error("[StanzaWeaver] 词库导入失败: %s", e)
    finally:
        _vocab_importing = False


threading.Thread(target=_auto_import, daemon=True).start()

app = Flask(__name__, template_folder="templates", static_folder="static")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_active_states: dict[str, dict[str, Any]] = {}
_CSRF_TOKEN = secrets.token_hex(16)


def _register_custom_templates() -> None:
    """注册 src/templates/custom_*.py 中的自定义模板（重启自动恢复）。"""
    import importlib

    tpl_dir = Path(__file__).parent / "src" / "templates"
    if not tpl_dir.exists():
        return
    for f in sorted(tpl_dir.glob("custom_*.py")):
        try:
            module = importlib.import_module(f"src.templates.{f.stem}")
            for attr in dir(module):
                if attr.startswith("register_custom_"):
                    getattr(module, attr)()
        except Exception as e:  # noqa: BLE001 - 自定义模板可含任意用户代码，注册失败仅记录
            logger.error("[StanzaWeaver] 自定义模板注册失败 %s: %s", f.name, e)


_register_custom_templates()


@app.before_request
def _guard_local_access() -> Any:
    """仅允许本机访问（Host 校验）。"""
    host = request.host or ""
    if not host.startswith(("127.0.0.1", "localhost")):
        return jsonify({"status": "error", "message": "拒绝非本机访问"}), 403
    return None


def _require_csrf() -> bool:
    """校验 CSRF 令牌。

    Returns:
        令牌匹配返回 True。
    """
    return request.headers.get("X-CSRF-Token", "") == _CSRF_TOKEN


def load_templates() -> list[dict[str, Any]]:
    """加载全部模板字典。

    Returns:
        模板字典列表。
    """
    return list_dicts()


@app.route("/api/import-status")
def api_import_status() -> Any:
    """查询词库导入状态。"""
    return jsonify({"importing": _vocab_importing})


@app.route("/")
def index() -> str:
    """主页面（注入 CSRF 令牌）。"""
    return render_template("index.html", csrf_token=_CSRF_TOKEN)


@app.route("/api/templates")
def api_templates() -> Any:
    """模板列表接口。"""
    return jsonify(load_templates())


@app.route("/api/config", methods=["GET"])
def api_get_config() -> Any:
    """读取 LLM 配置。"""
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
    from src.config import get_config

    config = get_config()
    return jsonify(
        {
            "writer": config.writer,
            "checker": config.checker,
        }
    )


@app.route("/api/config", methods=["POST"])
def api_save_config() -> Any:
    """保存 LLM 配置。"""
    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403
    from src.config import get_config

    config = get_config()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
    for key in ("writer", "checker"):
        if key in data:
            value = data[key]
            if not isinstance(value, dict):
                return jsonify(
                    {"status": "error", "message": f"{key} 配置格式错误"}
                ), 400
            config.__setattr__(key, value)
    config.save()
    logger.info(
        "LLM 配置已保存 (writer.base_url=%s, checker.base_url=%s)",
        config.writer["base_url"],
        config.checker["base_url"],
    )
    return jsonify({"status": "ok"})


@socketio.on("connect")  # type: ignore[untyped-decorator]
def handle_connect() -> None:
    """Socket 连接建立。"""


def _emit_done(session_id: str, result: Any) -> None:
    """向会话推送 done 事件。

    Args:
        session_id: SocketIO 会话 ID。
        result: 流水线结果状态。
    """
    socketio.emit(
        "done",
        {
            "draft": result.draft,
            "final_poem": result.final_poem,
            "checker_pass": result.checker_pass,
            "checker_suggestions": result.checker_suggestions,
            "step_details": result.step_details,
        },
        to=session_id,
    )


@socketio.on("generate")  # type: ignore[untyped-decorator]
def handle_generate(data: dict[str, Any]) -> None:
    """开始生成：后台线程跑四步流水线。"""
    from src.pipeline.pipeline import PoetryPipeline

    topic = str(data.get("topic", ""))
    template_key = str(data.get("template_key", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # flask_socketio 注入

    if not topic or not template_key:
        emit("error", {"message": "主题和模板不能为空"})
        return

    logger.info(
        "generate 开始 session=%s template=%s topic=%r", session_id, template_key, topic
    )
    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        socketio.emit("progress", state_dict, to=session_id)

    def run() -> None:
        try:
            result = pipeline.run(
                topic=topic,
                template_key=template_key,
                on_progress=on_progress,
            )
        except Exception as e:  # noqa: BLE001 - 生成线程兜底：任何失败转为前端错误事件
            logger.error("generate 失败 session=%s: %s", session_id, e)
            socketio.emit("error", {"message": f"生成失败: {e}"}, to=session_id)
            return
        _active_states[session_id] = {
            "pipeline_state": result,
        }
        logger.info(
            "generate 完成 session=%s checker_pass=%s rounds=%s",
            session_id,
            result.checker_pass,
            result.refine_rounds,
        )
        _emit_done(session_id, result)

    threading.Thread(target=run, daemon=True).start()


@socketio.on("feedback")  # type: ignore[untyped-decorator]
def handle_feedback(data: dict[str, Any]) -> None:
    """用户反馈续跑：打回 Step 3 按反馈重新炼句。"""
    from src.pipeline.pipeline import PoetryPipeline

    feedback = str(data.get("feedback", ""))
    session_id = request.sid  # type: ignore[attr-defined]  # flask_socketio 注入

    session_data = _active_states.get(session_id, {})
    pipeline_state = session_data.get("pipeline_state")
    if pipeline_state is None:
        emit("error", {"message": "没有活跃的生成会话，请先生成诗歌"})
        return

    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict[str, Any]) -> None:
        socketio.emit("progress", state_dict, to=session_id)

    def run() -> None:
        try:
            result = pipeline.continue_with_feedback(
                state=pipeline_state,
                user_feedback=feedback,
                on_progress=on_progress,
            )
        except Exception as e:  # noqa: BLE001 - 反馈线程兜底：任何失败转为前端错误事件
            logger.error("feedback 失败 session=%s: %s", session_id, e)
            socketio.emit("error", {"message": f"反馈处理失败: {e}"}, to=session_id)
            return
        _active_states[session_id] = {
            "pipeline_state": result,
        }
        logger.info(
            "feedback 完成 session=%s checker_pass=%s rounds=%s",
            session_id,
            result.checker_pass,
            result.refine_rounds,
        )
        _emit_done(session_id, result)

    threading.Thread(target=run, daemon=True).start()


@socketio.on("disconnect")  # type: ignore[untyped-decorator]
def handle_disconnect() -> None:
    """连接断开：清理会话状态。"""
    _active_states.pop(request.sid, None)  # type: ignore[attr-defined]  # flask_socketio 注入


@app.route("/api/templates/custom", methods=["POST"])
def api_create_custom_template() -> Any:
    """创建自定义格律模板（落盘为 src/templates/custom_*.py 并热注册）。"""
    import importlib
    import re
    from pathlib import Path

    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400
    name = str(data.get("name", "")).strip()
    language = str(data.get("language", "zh"))
    try:
        lines = int(data.get("lines", 4))
    except (TypeError, ValueError):
        lines = 4
    lines = max(1, min(lines, 30))
    syllables_per_line = data.get("syllables_per_line", [5] * lines)
    constraints = data.get("constraints", [])
    custom_code = str(data.get("code", "")).strip()

    if not name:
        return jsonify({"status": "error", "message": "模板名称不能为空"}), 400
    if language not in ("zh", "en"):
        return jsonify({"status": "error", "message": "不支持的语言"}), 400
    try:
        syllables_per_line = [max(1, int(s)) for s in syllables_per_line][:lines]
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "每行音节数格式错误"}), 400
    if len(syllables_per_line) != lines:
        return jsonify(
            {"status": "error", "message": "音节数列表长度必须等于行数"}
        ), 400

    safe_name = re.sub(r"\W+", "_", name).strip("_")
    if not safe_name:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "模板名需包含字母或数字（当前名称无法生成合法标识符）",
                }
            ),
            400,
        )
    class_name = f"Custom{safe_name.title().replace('_', '')}Template"
    file_key = f"custom_{safe_name}"
    file_path = Path(__file__).parent / "src" / "templates" / f"{file_key}.py"

    constraints_code: list[str] = []
    for line_c in constraints:
        cells: list[str] = []
        for c in line_c:
            tone = c.get("attributes", {}).get("tone", "")
            stress = c.get("attributes", {}).get("stress", "")
            if tone:
                cells.append(f'_t("{tone}")')
            elif stress:
                cells.append(f'_make_syl(attributes={{"stress": "{stress}"}})')
            else:
                cells.append("_FREE")
        constraints_code.append("[" + ", ".join(cells) + "]")

    constraints_str = (
        "[\n            " + ",\n            ".join(constraints_code) + "\n        ]"
    )

    code_body = (
        f"# Copyright (c) 2026 xhdlphzr\n"
        f"# SPDX-License-Identifier: MIT\n"
        f"# Auto-generated custom template: {name}\n\n"
        f"from . import PoetryTemplate, register\n"
        f"from .zh import (\n"
        f"    _make_syl, _FREE, _tone as _t,\n"
        f"    _check_sanpingwei, _check_sanzewei, _check_guping,\n"
        f"    _check_rhyme, _check_alternation, _check_lv_alternation,\n"
        f")\n\n\n"
        f"class {class_name}(PoetryTemplate):\n"
        f"    name = {json.dumps(name, ensure_ascii=False)}\n"
        f'    language = "{language}"\n'
        f"    lines = {lines}\n"
        f"    syllables_per_line = {syllables_per_line}\n\n"
        f"    def get_syllable_constraints(self):\n"
        f"        return {constraints_str}\n\n"
        f"    def validate_full(self, poem, syllables):\n"
        f"        errors = []\n"
    )
    if custom_code:
        for line in custom_code.split("\n"):
            if line.strip():
                code_body += f"        {line}\n"
    code_body += "        return errors\n\n\n"
    code_body += f"def register_custom_{safe_name}():\n"
    code_body += f'    register("{file_key}", {class_name}())\n'

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code_body, encoding="utf-8")
    except OSError as e:
        return jsonify({"status": "error", "message": f"模板文件写入失败: {e}"}), 500

    try:
        module = importlib.import_module(f"src.templates.{file_key}")
        reg_func = getattr(module, f"register_custom_{safe_name}", None)
        if reg_func:
            reg_func()
    except Exception as e:  # noqa: BLE001 - 用户代码模板注册兜底：任何导入/执行错误回报 500
        return jsonify({"status": "error", "message": f"注册失败: {e}"}), 500

    socketio.emit("templates_updated", {"count": len(load_templates())})
    logger.info("自定义模板已创建: %s (%s, %d 行)", name, language, lines)
    return jsonify(
        {
            "status": "ok",
            "message": f"模板'{name}'已创建并注册",
            "count": len(load_templates()),
        }
    )


def _init_history_db() -> None:
    """初始化历史记录表（幂等）。"""
    import sqlite3

    hdb = Path.home() / ".stanza_weaver" / "history.db"
    hdb.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(hdb))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        template_name TEXT,
        poem TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )"""
    )
    conn.commit()
    conn.close()


@app.route("/api/history", methods=["GET"])
def api_get_history() -> Any:
    """读取历史记录（最近 50 条）。"""
    import sqlite3

    _init_history_db()
    hdb = Path.home() / ".stanza_weaver" / "history.db"
    conn = sqlite3.connect(str(hdb))
    rows = conn.execute(
        "SELECT id, topic, template_name, poem, created_at FROM history ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify(
        [
            {
                "id": r[0],
                "topic": r[1],
                "template_name": r[2],
                "poem": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]
    )


@app.route("/api/history", methods=["POST"])
def api_save_history() -> Any:
    """保存历史记录（定稿后由前端调用）。"""
    import sqlite3

    if not _require_csrf():
        return jsonify({"status": "error", "message": "缺少安全令牌"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求格式错误"}), 400

    _init_history_db()
    hdb = Path.home() / ".stanza_weaver" / "history.db"
    conn = sqlite3.connect(str(hdb))
    conn.execute(
        "INSERT INTO history (topic, template_name, poem) VALUES (?, ?, ?)",
        (
            str(data.get("topic", "")),
            str(data.get("template_name", "")),
            str(data.get("poem", "")),
        ),
    )
    conn.commit()
    conn.close()
    logger.info(
        "历史记录已保存: %s (%s)", data.get("template_name", ""), data.get("topic", "")
    )
    return jsonify({"status": "ok"})


def start_server() -> None:
    """启动 SocketIO 服务。

    监听地址/端口可用环境变量 STANZAWEAVER_HOST / STANZAWEAVER_PORT 覆盖
    （Docker 部署时设 STANZAWEAVER_HOST=0.0.0.0 配合端口映射）。

    Returns:
        None（阻塞运行直到退出）。
    """
    host = os.environ.get("STANZAWEAVER_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("STANZAWEAVER_PORT", "5000"))
    except ValueError:
        port = 5000
    logger.info("[StanzaWeaver] 服务启动 http://%s:%s", host, port)
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)


def main() -> None:
    """入口：优先 pywebview 桌面窗口，否则纯 HTTP 服务。

    桌面窗口初始化失败（如无显示环境/缺 GUI 库）时自动回退到 HTTP 服务，
    保证 Docker 等无头环境可用。

    Returns:
        None。
    """
    try:
        import webview
    except ImportError:
        start_server()
        return

    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    try:
        webview.create_window(
            "StanzaWeaver",
            "http://127.0.0.1:5000",
            width=900,
            height=700,
            min_size=(700, 500),
        )
        webview.start()
    except Exception as e:  # noqa: BLE001 - GUI 初始化失败兜底：回退 HTTP 服务
        logger.warning("GUI 初始化失败，回退到 HTTP 服务模式: %s", e)
        t.join()


if __name__ == "__main__":
    main()
