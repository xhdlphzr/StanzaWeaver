# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

import json
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Import and register all templates
from src.templates.zh import register_chinese_templates
from src.templates.en import register_english_templates
from src.templates import list_dicts

register_chinese_templates()
register_english_templates()

app = Flask(__name__, template_folder="templates", static_folder="static")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_active_states: dict[str, dict] = {}


def load_templates() -> list[dict]:
    return list_dicts()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/templates")
def api_templates():
    return jsonify(load_templates())


@app.route("/api/config", methods=["GET"])
def api_get_config():
    from src.config import get_config

    config = get_config()
    return jsonify(
        {
            "writer": config.writer,
            "checker": config.checker,
        }
    )


@app.route("/api/config", methods=["POST"])
def api_save_config():
    from src.config import get_config

    config = get_config()
    data = request.get_json()
    if "writer" in data:
        config.writer = data["writer"]
    if "checker" in data:
        config.checker = data["checker"]
    config.save()
    return jsonify({"status": "ok"})


@socketio.on("connect")
def handle_connect():
    pass


@socketio.on("generate")
def handle_generate(data):
    from src.pipeline.pipeline import PoetryPipeline

    topic = data.get("topic", "")
    template_key = data.get("template_key", "")
    session_id = request.sid

    if not topic or not template_key:
        emit("error", {"message": "主题和模板不能为空"})
        return

    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict):
        socketio.emit("progress", state_dict, to=session_id)

    def run():
        result = pipeline.run(
            topic=topic,
            template_key=template_key,
            on_progress=on_progress,
        )
        _active_states[session_id] = {
            "pipeline_state": result,
        }
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

    threading.Thread(target=run, daemon=True).start()


@socketio.on("feedback")
def handle_feedback(data):
    from src.pipeline.pipeline import PoetryPipeline

    feedback = data.get("feedback", "")
    session_id = request.sid

    session_data = _active_states.get(session_id, {})
    pipeline_state = session_data.get("pipeline_state")
    if pipeline_state is None:
        emit("error", {"message": "没有活跃的生成会话，请先生成诗歌"})
        return

    pipeline = PoetryPipeline()

    def on_progress(state_dict: dict):
        socketio.emit("progress", state_dict, to=session_id)

    def run():
        result = pipeline.continue_with_feedback(
            state=pipeline_state,
            user_feedback=feedback,
            on_progress=on_progress,
        )
        _active_states[session_id] = {
            "pipeline_state": result,
        }
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

    threading.Thread(target=run, daemon=True).start()


@socketio.on("import_vocabulary")
def handle_import_vocabulary(data):
    from src.knowledge.importer import import_all
    from src.knowledge.vocabulary import word_count

    limit = data.get("limit", 0)

    def run():
        socketio.emit("import_progress", {"message": "开始导入词库..."})
        try:
            import_all(limit_chinese=limit)
            zh_count = word_count("zh")
            en_count = word_count("en")
            socketio.emit(
                "import_progress",
                {"message": f"词库导入完成。中文: {zh_count}条, 英文: {en_count}条"},
            )
        except Exception as e:
            socketio.emit("import_progress", {"message": f"导入失败: {str(e)}"})

    threading.Thread(target=run, daemon=True).start()


def start_server():
    socketio.run(app, host="127.0.0.1", port=5000, allow_unsafe_werkzeug=True)


def main():
    try:
        import webview
    except ImportError:
        start_server()
        return

    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    webview.create_window(
        "StanzaWeaver",
        "http://127.0.0.1:5000",
        width=900,
        height=700,
        min_size=(700, 500),
    )
    webview.start()


if __name__ == "__main__":
    main()
