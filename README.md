<!--
Copyright (c) 2026 xhdlphzr
SPDX-License-Identifier: MIT
-->

# StanzaWeaver

神经符号智能诗歌生成桌面软件

## 概述

StanzaWeaver 是一个基于 **神经符号方法**（Neuro-Symbolic）的多语言诗歌生成工具。核心理念是将诗歌创作为两层协作：

- **符号层**（硬规则）：音节计数、平仄/轻重/长短约束、押韵检测、三平尾、孤平等格律校验，由 Python 代码零 AI 开销完成。
- **神经层**（AI 语义）：现代文描述生成、句意构思、炼句优化、句意终审，通过 LLM（大语言模型）+ 工具调用（Tool Calling）实现。

两层通过结构化工具调用解耦，AI 只能通过 `search_words`、`refine_line`、`rewrite`、`submit` 四个工具输出结构化数据，杜绝冗余自由文本。

## 核心特性

- **四步流水线**：描述生成 → 初稿（仅验音节数）→ ReAct 炼句循环（搜词 + 整行替换 + 整体重写，每次改完自动跑全部格律约束）→ 检查 AI 句意终审
- **三要素反馈闭环**：编写 AI → 检查 AI → 用户，任意一环不通过即可打回 Step 3 继续炼句
- **多语言支持**：中文（绝句、律诗、词牌）、英文（商籁体、维拉内拉、英雄双行体）、意大利语、法语、古典拉丁语，模板以 Python 类定义，可无限扩展
- **多层格律校验**：逐位平仄/轻重约束 + 三平尾 + 孤平 + 二四六分明 + 押韵检测
- **实时流式输出**：LLM 生成过程逐 token 推送到前端，Step 详情区默认展开持续更新
- **双重 AI 代理**：编写 AI（4 工具）+ 检查 AI（1 工具），可独立配置不同 LLM 端点/模型
- **桌面软件打包**：pywebview + Flask + SocketIO，pyinstaller 打包单 exe 分发

## 快速开始

```bash
# 1. 安装依赖
pip install flask flask-socketio pywebview openai pypinyin nltk

# 2. 导入词库（首次运行前）
python -c "from src.knowledge.importer import import_all; import_all()"

# 3. 配置 LLM
# 启动后在 UI 右上角齿轮按钮中配置编写 AI 和检查 AI 的 Base URL / API Key / Model
# 或手动编辑 ~/.stanza_weaver/config.json

# 4. 启动
python app.py
```

## 项目结构

```
StanzaWeaver/
├── requirements.txt        # 项目依赖
├── app.py                   # pywebview + Flask + SocketIO 入口
├── templates/index.html     # 前端 UI
├── static/style.css         # 样式
└── src/
    ├── config.py            # LLM 多端点配置
    ├── models/              # 数据模型（音节 Syllable、词条 Word）
    ├── prosody/             # 符号层：格律工具
    │   ├── base.py          # SyllableAnalyzer 抽象基类
    │   ├── chinese.py       # 中文分析器（pypinyin）
    │   ├── english.py       # 英文分析器（CMUdict）
    │   ├── italian.py       # 意大利语分析器
    │   ├── french.py        # 法语分析器
    │   ├── latin.py         # 拉丁语分析器
    │   ├── syllable_counter.py  # 多语言统一音节计数
    │   └── meter_validator.py   # 格律总校验
    ├── knowledge/           # 本地词库
    │   ├── schema.sql       # SQLite 建表
    │   ├── vocabulary.py    # 查询接口
    │   ├── embeddings.py    # sentence-transformers 向量重排
    │   └── importer.py      # 数据集导入（CC-CEDICT / CMUdict / Lexique / GLAW-IT / Lewis & Short）
    ├── agents/              # 神经层：AI Agent
    │   ├── base.py          # LLM 调用封装
    │   ├── writer_ai.py     # 编写 AI（4 工具）
    │   └── checker_ai.py    # 检查 AI（1 工具）
    ├── tools/               # Agent 工具定义
    │   ├── __init__.py      # OpenAI Tool JSON Schema（search_words / refine_line / rewrite / submit）
    │   ├── search_words.py  # 搜词执行
    │   └── refine_line.py   # 整行替换执行
    ├── templates/           # 格律模板（Python 类）
    │   ├── __init__.py      # PoetryTemplate 基类 + 注册表
    │   ├── zh.py            # 中文模板（五绝/七绝/五律/七律/相见欢）
    │   ├── en.py            # 英文模板（商籁体/维拉内拉/英雄双行体）
    │   ├── it.py            # 意大利语模板（三行体/八行体/歌谣）
    │   ├── fr.py            # 法语模板（回旋诗/三韵叠句诗/叙事歌）
    │   └── la.py            # 拉丁语模板（六步格/哀歌双行体/十一音节诗）
    └── pipeline/
        └── pipeline.py      # 4 步流水线 + 打回循环
```

## 格律模板

模板以 Python 类形式定义，继承 `PoetryTemplate`，需实现：

| 方法 | 说明 |
|------|------|
| `get_syllable_constraints()` | 逐位音节约束（供 refine_line 单行校验） |
| `validate_full()` | 完整规则检查（三平尾、孤平、押韵等） |
| `describe()` | 人类可读的格律描述（供 AI prompt 使用） |

内置模板：五言绝句、七言绝句、五言律诗、七言律诗、相见欢、莎士比亚商籁体、维拉内拉诗、英雄双行体、意大利语三行体/八行体/歌谣、法语回旋诗/三韵叠句诗/叙事歌、拉丁语六步格/哀歌双行体/十一音节诗。

扩展方式：在 `src/templates/` 下新增 Python 文件，实现模板类后在 `app.py` 中注册；或在 UI 中通过「+ 自定义」生成模板（自动落盘到 `src/templates/custom_*.py`，重启后自动恢复注册）。

## LLM 配置

支持任何兼容 OpenAI API 格式的端点（OpenAI / Ollama / vLLM / DeepSeek / Groq 等）：

```json
{
  "writer": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4o"
  },
  "checker": {
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5:7b"
  }
}
```

UI 齿轮按钮中直接编辑保存，或手动编辑 `~/.stanza_weaver/config.json`。
