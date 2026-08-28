# 贡献指南（CONTRIBUTING）

感谢你为 **StanzaWeaver**（以智识，巧织诗）贡献力量！本文件说明如何搭建开发环境、提交前必须通过的检查，以及如何在符号层新增**诗体**与**语言**。

> 所有新增功能都必须通过测试；无法离线验证的逻辑（如需要联网下载词库）至少要提供走桩（stub）的单测，保证 `pytest` 全绿。

---

## 1. 开发环境搭建（Docker）

推荐用 Docker 启动一个与 CI 一致的开发/运行环境（基础镜像 `python:3.14-slim`，与 `.github/workflows/ci.yml` 锁定的 Python 版本一致）。

### 1.1 构建镜像

仓库 `scripts/` 下提供了跨平台脚本（`.sh` / `.ps1` / `.bat`），直接用它们构建即可：

```bash
# Linux / macOS
./scripts/build.sh

# Windows (PowerShell)
.\scripts\build.ps1
```

- 国内无法直连 Docker Hub 时，可指定加速器前缀基础镜像：
  `./scripts/build.sh -b docker.m.daocloud.io/library/python:3.14-slim`
- 其他可选参数见脚本 `--help`（如 `-t <tag>` 指定镜像标签、`-n` 无缓存重建）。

### 1.2 运行（带数据持久化）

```bash
# Linux / macOS
./scripts/run.sh              # 前台运行；-d 后台，-l 跟随日志，-p <port> 改端口

# Windows (PowerShell)
.\scripts\run.ps1
```

- 访问：<http://localhost:5000>（安全设计仅接受 `localhost`/`127.0.0.1` 的 Host 头）
- 数据卷 `stanzaweaver-data` 自动创建，持久化配置 / 词库 / 历史 / 日志（`~/.stanza_weaver`）

### 1.3 使用 docker-compose

```bash
docker compose up -d --build     # 启动
docker compose logs -f stanzaweaver   # 查看日志
docker compose down              # 停止
```

### 1.4 在容器内开发

镜像已构建后，进入容器即可使用与本地相同的命令（`mypy` / `ruff` / `pytest`）：

```bash
docker exec -it stanzaweaver bash
cd /app
python -m pytest
```

### 1.5 不使用 Docker（可选）

本地用虚拟环境也可，但需 Python **3.14**：

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
#   source .venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
pip install pytest ruff mypy        # 测试/检查工具
```

---

## 2. 提交前必须通过的检查

每次提交（PR）前，请在仓库根目录依次运行以下命令，**全部 0 退出码 / 无输出错误** 才允许提交：

```bash
# 1) 类型检查（零容忍，--strict）
mypy --strict ./

# 2) 静态检查并自动修复（含 unsafe 修复）
ruff check --fix --unsafe-fixes ./

# 3) 代码格式化
ruff format ./

# 4) 测试
pytest
```

说明：

- CI 中 `ruff` 以 `ruff check ./`（不自动修改）执行，因此**你本地必须先用上面的 `--fix --unsafe-fixes` 与 `format` 把代码整理干净**，否则 CI 会失败。
- `mypy` 必须使用本项目配套的虚拟环境版本（`python3.14` + 项目依赖），系统全局 `mypy` 可能出现 import-not-found 的误报。
- `pytest` 通过 `tests/pytest.ini` 配置（`pythonpath = .`，`testpaths = tests`）。测试使用 `tests/helpers.py` 中的 `StubLLMClient` 走桩，**不调用任何真实 LLM / 不联网**，可离线全量运行。

---

## 3. 如何新增诗体（模板）

诗体（如十四行诗、绝句、俳句）由 `src/templates/` 下的 `PoetryTemplate` 子类定义，并注册到全局模板表。

### 3.1 接口

基类位于 `src/templates/__init__.py`：

```python
class PoetryTemplate(ABC):
    name: str                      # 诗体名称
    language: str                 # 语言代码（zh/en/it/fr/la）
    lines: int                    # 行数
    syllables_per_line: Sequence[int | tuple[int, int]]  # 每行音节数（区间用元组）
    rule_description: str         # 格律规则文本（用于提示 LLM）

    def get_syllable_constraints(self) -> ConstraintTable | None: ...
    def validate_full(self, poem: list[str], syllables: list[list[Syllable]]) -> list[str]: ...
```

- `get_syllable_constraints()` 返回每位置约束表（`list[list[dict]]`），单条约束形如：
  `{"onset": "", "nucleus": "", "coda": "", "attributes": {"tone": "", "stress": "", "length": ""}}`，空字符串表示不限制（详见 `src/models/syllable.py` 的 `match_constraint`）。返回 `None` 表示不施加逐位置约束。
- `validate_full(poem, syllables) -> list[str]`：返回错误字符串列表，**空列表即校验通过**。

### 3.2 新增步骤

1. 在对应语言模块（如 `src/templates/en.py`）新增子类，设置类属性并实现两个方法：

   ```python
   class MyNewFormTemplate(PoetryTemplate):
       name = "my_new_form"
       language = "en"
       lines = 4
       syllables_per_line = [8, 8, 8, 8]
       rule_description = "四行，每行八音节，ABAB 押韵。"

       def get_syllable_constraints(self):
           # 返回每位置约束；不需要可返回 None
           return None

       def validate_full(self, poem, syllables):
           errors: list[str] = []
           # 自行实现押韵 / 字数 / 平仄等校验
           return errors
   ```

2. 在该模块的 `register_<lang>_templates()` 函数中注册：

   ```python
   register("en_my_new_form", MyNewFormTemplate())
   ```

3. 在 `app.py` 中调用注册函数（与其他 `register_*_templates()` 并列，约 34–38 行），使服务端与 UI 可见。

4. 在 `tests/conftest.py` 的 `_register_all_templates` fixture 中同样加入该注册调用，确保测试能自动加载新诗体。

### 3.3 必须新增的测试

- 在 `tests/unit/` 增加 `test_<lang>_analyzer.py`（若涉及语言）或针对该诗体的校验测试；至少应覆盖：
  - 合法诗作 `validate_full` 返回 `[]`；
  - 明显违规（行数错 / 音节错 / 不押韵）能被 `validate_full` 捕获。
- 如有 UI / 端到端诉求，可在 `tests/integration/` 用 `helpers.make_stub` 驱动 `Pipeline` / SocketIO 验证全流程。

---

## 4. 如何新增语言

语言需要三处配合：① 音节分析器；② 模板表的语言标签；③ 词库导入器（可选但推荐，否则 `search_words` 工具无数据）。

### 4.1 实现分析器

在 `src/prosody/` 新增 `<lang>.py`，继承 `src/prosody/base.py` 的 `SyllableAnalyzer`：

```python
class SyllableAnalyzer(ABC):
    language: str

    def analyze_word(self, word: str) -> list[Syllable]: ...   # 抽象
    def count_syllables(self, text: str) -> int: ...           # 抽象
    def tokenize_line(self, line: str) -> list[str]: ...       # 可重写（中文按字切分）
```

 实现后注册到多语言分发器 `src/prosody/syllable_counter.py`。

#### `_ANALYZERS` 字典 / 分发机制（详细）

模块级 `_ANALYZERS` 是一个**语言代码 → 分析器实例**的映射表，是所有音节分析的路由核心：

```python
_ANALYZERS: dict[str, SyllableAnalyzer] = {
    "zh": ChineseAnalyzer(),   # 中文：整行经 pypinyin 处理多音字
    "en": EnglishAnalyzer(),   # 英文：逐词 + 重音/变体
    "it": ItalianAnalyzer(),   # 意大利语：整行 sinalefe 跨词合并
    "fr": FrenchAnalyzer(),    # 法语：逐词
    "la": LatinAnalyzer(),     # 拉丁语：整行跨词判定音长
}
```

- **注册 / 获取**：
  - `register_analyzer(language, analyzer)` —— 新增或覆盖某语言的分析器（写入 `_ANALYZERS[language] = analyzer`）。
  - `get_analyzer(language)` —— 按语言取实例；未注册时抛 `ValueError("No syllable analyzer registered for language: <lang>")`。
- **对外入口**（均内部调用 `get_analyzer`）：
  - `count_syllables(text, language) -> int`：返回音节总数。
  - `analyze_line(line, language) -> list[Syllable]`：返回整行音节列表，其路由逻辑按语言分三种：
    1. `zh`：整行送 `ChineseAnalyzer.analyze_word("".join(tokenize_line(line)))`，靠 pypinyin 上下文消歧多音字。
    2. `it`：调用 `ItalianAnalyzer.syllabify_line(line)` 做 sinalefe（跨词音节合并）。
    3. `la`：调用 `LatinAnalyzer.analyze_line(line)` 做跨词音长判定（muta cum liquida 等）。
    4. 其它语言：`tokenize_line` 先按词切分，再对每个词 `analyze_word` 后拼接。

新增语言时的两种注册方式（二选一即可）：

- **方式 A（静态，推荐）**：直接在 `_ANALYZERS` 中加一行 `"xx": XxAnalyzer()`。
- **方式 B（动态）**：在模块加载处调用：
  ```python
  register_analyzer("xx", XxAnalyzer())
  ```

> ⚠️ 重要：若你的新语言需要**整行级**特殊处理（像 `zh` / `it` / `la` 那样不能简单逐词拼接），除了把分析器加入 `_ANALYZERS`，还必须**在 `analyze_line()` 的 `if/elif` 分支中新增对应的 `language == "xx"` 分支**，否则会退化为默认的逐词拼接逻辑。若新语言只需逐词分析，则无需改 `analyze_line`。


### 4.2 模板语言标签

在 `src/templates/__init__.py` 的 `_LANGUAGE_LABELS` 中为新语言增加显示名（供前端下拉框使用），例如 `"xx": "新语言"`。

### 4.3 词库导入（可选但推荐）

在 `src/knowledge/importer.py` 增加 `_import_<lang>()`，从公开词表解析为 `Word(text, language, syllables, meaning)`（`syllables` 由你的分析器产出），并接入 `import_all()`。查询层 `src/knowledge/vocabulary.py` 的 `search_words` 会据此为 `search_words` 工具提供离线候选。

### 4.4 必须新增的测试

- `tests/unit/test_<lang>_analyzer.py`：覆盖 `analyze_word` / `count_syllables` / `tokenize_line` 的典型用例（含多音节词、特殊拼写）。
- 若新增约束/校验逻辑，补充 `test_meter_validator.py` 相关用例。
- 词库导入若为离线内置样例，提供不联网的断言；若必须联网下载，请在测试中以本地样例或走桩替代，保证 `pytest` 离线可过。

---

## 5. 测试总则

- 运行：`pytest`（根目录执行，依赖 `tests/pytest.ini`）。
- 全部测试**不依赖真实 LLM / 不联网**：LLM 由 `tests/helpers.py` 的 `StubLLMClient` 替换。
- 任何新功能（诗体 / 语言 / 分析器 / 校验器）都必须有对应单测；集成改动需有 `integration/` 下的端到端用例。
- 提交前确保 `mypy --strict ./`、`ruff check --fix --unsafe-fixes ./`、`ruff format ./`、`pytest` 四项全绿。

---

## 6. 提交清单（PR Checklist）

- [ ] 代码通过 `mypy --strict ./`
- [ ] 代码通过 `ruff check --fix --unsafe-fixes ./`
- [ ] 代码通过 `ruff format ./`
- [ ] `pytest` 全绿（含新增测试）
- [ ] 新增诗体已在 `app.py` 与 `tests/conftest.py` 注册
- [ ] 新增语言已注册分析器、语言标签，并有对应单测
- [ ] 相关改动已在 PR 描述中说明用途与验证方式

合并以 `main` 分支为目标的 PR；CI（`ci` + `build`）通过后由维护者合入。
