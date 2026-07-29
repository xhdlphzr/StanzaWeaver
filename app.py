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


@app.route("/api/templates/custom", methods=["POST"])
def api_create_custom_template():
    import importlib
    import re
    from pathlib import Path

    data = request.get_json()
    name = data.get("name", "").strip()
    language = data.get("language", "zh")
    lines = data.get("lines", 4)
    syllables_per_line = data.get("syllables_per_line", [5] * lines)
    constraints = data.get("constraints", [])
    custom_code = data.get("code", "").strip()

    if not name:
        return jsonify({"status": "error", "message": "模板名称不能为空"}), 400

    safe_name = re.sub(r"\W+", "_", name)
    class_name = f"Custom{safe_name.title().replace('_', '')}Template"
    file_key = f"custom_{safe_name}"
    file_path = Path(__file__).parent / "src" / "templates" / f"{file_key}.py"

    constraints_code = []
    for line_c in constraints:
        cells = []
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
        f"from .zh import _make_syl, _FREE, _tone as _t\n\n\n"
        f"class {class_name}(PoetryTemplate):\n"
        f'    name = "{name}"\n'
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
            code_body += f"        {line}\n"
    else:
        code_body += "        return errors\n"
    code_body += "        return errors\n\n\n"
    code_body += f"def register_custom_{safe_name}():\n"
    code_body += f'    register("{file_key}", {class_name}())\n'

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(code_body, encoding="utf-8")

    try:
        module = importlib.import_module(f"src.templates.{file_key}")
        reg_func = getattr(module, f"register_custom_{safe_name}", None)
        if reg_func:
            reg_func()
    except Exception as e:
        return jsonify({"status": "error", "message": f"注册失败: {e}"}), 500

    socketio.emit("templates_updated", {"count": len(load_templates())})
    return jsonify(
        {
            "status": "ok",
            "message": f"模板'{name}'已创建并注册",
            "count": len(load_templates()),
        }
    )


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
