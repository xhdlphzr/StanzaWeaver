<!-- Copyright (c) 2026 xhdlphzr -->
<!-- SPDX-License-Identifier: MIT -->

# Contributing Guide

[![English](https://img.shields.io/badge/English-CONTRIBUTING-007EC6)](https://github.com/xhdlphzr/StanzaWeaver/blob/master/CONTRIBUTING.md)
[![汉语](https://img.shields.io/badge/汉语-CONTRIBUTING-007EC6)](https://github.com/xhdlphzr/StanzaWeaver/blob/master/docs/CONTRIBUTING.zh.md)

Thank you for contributing to **StanzaWeaver** (Weaving Stanzas with Wisdom)! This document explains how to set up the development environment, the mandatory checks before submitting, and how to add new **meter templates** and **languages** to the symbolic layer.

> All new features must pass tests with **100% code coverage on the changed `src` modules**; for logic that cannot be verified offline (e.g., requiring network download of lexicons), at least provide stub‑based unit tests to keep `pytest` green.

---

## 1. Development Environment Setup (Docker)

It is recommended to use Docker to start a development/runtime environment consistent with CI (base image `python:3.14-slim`, matching the Python version locked in `.github/workflows/ci.yml`).

### 1.1 Build the Image

Cross‑platform scripts (`.sh` / `.ps1` / `.bat`) are provided under the `scripts/` directory – use them directly to build:

```bash
# Linux / macOS
./scripts/build.sh

# Windows (PowerShell)
.\scripts\build.ps1
```

- If you cannot directly reach Docker Hub from China, specify an accelerator‑prefixed base image:
  `./scripts/build.sh -b docker.m.daocloud.io/library/python:3.14-slim`
- For other optional parameters, see the script `--help` (e.g., `-t <tag>` to specify image tag, `-n` for no‑cache rebuild).

### 1.2 Run (with Data Persistence)

```bash
# Linux / macOS
./scripts/run.sh              # foreground; -d for background, -l to follow logs, -p <port> to change port

# Windows (PowerShell)
.\scripts\run.ps1
```

- Access: <http://localhost:5000> (security design only accepts `localhost`/`127.0.0.1` Host headers)
- The data volume `stanzaweaver-data` is created automatically, persisting configuration / lexicon / history / logs (`~/.stanza_weaver`)

### 1.3 Using docker‑compose

```bash
docker compose up -d --build     # start
docker compose logs -f stanzaweaver   # view logs
docker compose down              # stop
```

### 1.4 Developing Inside the Container

After the image is built, enter the container to use the same commands as locally (`mypy` / `ruff` / `pytest`):

```bash
docker exec -it stanzaweaver bash
cd /app
python -m pytest
```

### 1.5 Without Docker (Optional)

You can also develop locally without Docker. The repo is dependency-managed with [uv](https://docs.astral.sh/uv/) and targets **Python 3.14** (see `.python-version`):

```bash
uv sync                    # creates .venv; installs runtime + dev deps from uv.lock
```

---

## 2. Pre‑Commit Checks

Before each commit (or PR), run the following commands in the repository root – **all must exit with 0 / no errors** before you commit:

```bash
# 1) Type checking (zero tolerance, --strict)
uv run mypy --strict ./

# 2) Lint and auto‑fix (including unsafe fixes)
uv run ruff check --fix --unsafe-fixes ./

# 3) Code formatting
uv run ruff format ./

# 4) Tests (enforces 100% coverage via --cov-fail-under=100 in pyproject.toml)
uv run pytest
```

Notes:

- In CI, `ruff` is run as `uv run ruff check ./` (without auto‑fix), so **you must locally clean up with `--fix --unsafe-fixes` and `format`** first, otherwise CI will fail.
- `mypy` must be used with the virtual environment that matches this project (`python3.14` + project dependencies); a system‑wide `mypy` may produce false‑positive import‑not‑found errors.
- `pytest` uses the `[tool.pytest.ini_options]` table in `pyproject.toml` (`pythonpath = .`, `testpaths = tests`, `--cov=src --cov-fail-under=100`). It enforces **100% coverage on `src`**, so every `src` change must be fully covered by tests — `pytest` fails otherwise. Tests use the `StubLLMClient` from `tests/helpers.py` – **no real LLM calls / no network**; they can run fully offline.

---

## 3. Coding Standards

### 3.1 Algorithm & Architecture

1. **Verify logic correctness** — review the algorithm/architecture layer for correctness before submitting.
2. **100% test coverage** — `pytest` must pass with 100% coverage on changed `src` modules. Every new bug must have a corresponding test case; review test code for blind spots.
3. **Interface consolidation** — when multiple interfaces exist for the same functionality, evaluate whether they can be unified.

### 3.2 Code Quality

4. **Linting** — `ruff check` must pass cleanly. Always run `ruff check --fix --unsafe-fixes` first, then fix manually if needed.
5. **Type checking** — `mypy --strict` must pass on all `src` files. Run `mypy --install-types` first if needed, then fix manually.
6. **Docstrings** — every function, class, and module must have Google-style docstrings.
7. **Formatting** — run `ruff format` after every code change.
8. **Dead code** — remove unreachable/redundant code; keep logic concise.

### 3.3 User Experience

9. **Feature completeness** — within the scope of this software, accommodate the majority of user needs.
10. **UI design** — aim for polished visuals: rounded corners, Alex Brush for English headings, Noto Serif SC for body text, and smooth animations (slide, expand, fade).

---

## 4. How to Add a New Meter Template

Meter templates (e.g., sonnet, quatrain, haiku) are defined as subclasses of `PoetryTemplate` under `src/templates/` and registered in the global template table.

### 3.1 Interface

The base class is located in `src/templates/__init__.py`:

```python
class PoetryTemplate(ABC):
    name: str  # template name
    language: str  # language code (zh/en/it/fr/la)
    lines: int  # number of lines
    syllables_per_line: Sequence[
        int | tuple[int, int]
    ]  # syllables per line (range expressed as tuple)
    rule_description: str  # meter rule description (used in LLM prompts)

    def get_syllable_constraints(self) -> ConstraintTable | None: ...
    def validate_full(
        self, poem: list[str], syllables: list[list[Syllable]]
    ) -> list[str]: ...
```

- `get_syllable_constraints()` returns a position‑wise constraint table (`list[list[dict]]`). A single constraint looks like:
  `{"onset": "", "nucleus": "", "coda": "", "attributes": {"tone": "", "stress": "", "length": ""}}` – empty strings mean no restriction (see `match_constraint` in `src/models/syllable.py`). Returning `None` means no positional constraints are applied.
- `validate_full(poem, syllables) -> list[str]` returns a list of error strings; **an empty list means validation passes**.

### 3.2 Steps to Add

1. Add a new subclass in the appropriate language module (e.g., `src/templates/en.py`), set class attributes and implement the two methods:

   ```python
   class MyNewFormTemplate(PoetryTemplate):
       name = "my_new_form"
       language = "en"
       lines = 4
       syllables_per_line = [8, 8, 8, 8]
       rule_description = "Four lines, eight syllables each, ABAB rhyme."

       def get_syllable_constraints(self):
           # return position‑wise constraints; return None if not needed
           return None

       def validate_full(self, poem, syllables):
           errors: list[str] = []
           # implement rhyme / syllable / tone validation yourself
           return errors
   ```

2. Register it in the module’s `register_<lang>_templates()` function:

   ```python
   register("en_my_new_form", MyNewFormTemplate())
   ```

3. Call the registration function in `app.py` (alongside other `register_*_templates()` calls, around lines 34–38) to make it visible to the server and UI.

4. Also add the same registration call in the `_register_all_templates` fixture in `tests/conftest.py` to ensure tests can automatically load the new template.

### 3.3 Required Tests

- Add a test file (e.g., `test_<lang>_analyzer.py` in `tests/unit/` if a new language is involved, or a test specific to the new template) that at least covers:
  - A valid poem where `validate_full` returns `[]`.
  - Obvious violations (wrong line count / wrong syllable count / no rhyme) are caught by `validate_full`.
- **Coverage requirement:** the new tests must bring the changed `src` module (e.g., the new template class) to **100% line coverage**. Run `pytest` and confirm it stays green (the `--cov-fail-under=100` gate rejects any uncovered line).
- For UI / end‑to‑end scenarios, you can use `helpers.make_stub` in `tests/integration/` to drive the `Pipeline` / SocketIO and verify the full flow.

---

## 5. How to Add a New Language

Adding a language requires three parts: ① a syllable analyser; ② a language label in the template registry; ③ a lexicon importer (optional but recommended, otherwise the `search_words` tool will have no data).

### 4.1 Implement the Analyser

Add a new `<lang>.py` under `src/prosody/` that inherits from `SyllableAnalyzer` in `src/prosody/base.py`:

```python
class SyllableAnalyzer(ABC):
    language: str

    def analyze_word(self, word: str) -> list[Syllable]: ...  # abstract
    def count_syllables(self, text: str) -> int: ...  # abstract
    def tokenize_line(
        self, line: str
    ) -> list[str]: ...  # override if needed (Chinese splits by character)
```

After implementing, register it in the multi‑language dispatcher `src/prosody/syllable_counter.py`.

#### The `_ANALYZERS` Dictionary / Dispatch Mechanism (Detailed)

The module‑level `_ANALYZERS` is a **language‑code → analyser instance** mapping that routes all syllable analysis:

```python
_ANALYZERS: dict[str, SyllableAnalyzer] = {
    "zh": ChineseAnalyzer(),  # Chinese: whole line processed with pypinyin for polyphonic characters
    "en": EnglishAnalyzer(),  # English: word‑by‑word with stress / variants
    "it": ItalianAnalyzer(),  # Italian: whole line with sinalefe (cross‑word syllable merging)
    "fr": FrenchAnalyzer(),  # French: word‑by‑word
    "la": LatinAnalyzer(),  # Latin: whole line cross‑word length determination
}
```

- **Registration / Retrieval**:
  - `register_analyzer(language, analyzer)` – add or override an analyser for a language (writes to `_ANALYZERS[language] = analyzer`).
  - `get_analyzer(language)` – returns the instance for the given language; raises `ValueError("No syllable analyzer registered for language: <lang>")` if not found.
- **Public Entry Points** (both internally call `get_analyzer`):
  - `count_syllables(text, language) -> int`: returns total syllable count.
  - `analyze_line(line, language) -> list[Syllable]`: returns the syllable list for the whole line. The routing logic varies by language:
    1. `zh`: the whole line is passed to `ChineseAnalyzer.analyze_word("".join(tokenize_line(line)))`, using pypinyin’s context to disambiguate polyphonic characters.
    2. `it`: calls `ItalianAnalyzer.syllabify_line(line)` to perform sinalefe (cross‑word syllable merging).
    3. `la`: calls `LatinAnalyzer.analyze_line(line)` for cross‑word length determination (muta cum liquida, etc.).
    4. Other languages: `tokenize_line` splits into words, then `analyze_word` is called on each word and the results are concatenated.

When adding a new language, you can register it in one of two ways (choose either):

- **Method A (static, recommended)**: add a line `"xx": XxAnalyzer()` directly in `_ANALYZERS`.
- **Method B (dynamic)**: call at module load:
  ```python
  register_analyzer("xx", XxAnalyzer())
  ```

> ⚠️ Important: If your new language requires **whole‑line** special handling (like `zh` / `it` / `la`, where simple word‑by‑word concatenation is not enough), besides adding the analyser to `_ANALYZERS`, you must also **add a new `elif language == "xx"` branch inside `analyze_line()`** – otherwise it will fall back to the default word‑by‑word concatenation logic. If your new language only needs word‑by‑word analysis, no changes to `analyze_line()` are required.

### 4.2 Template Language Label

Add a display name for the new language in `_LANGUAGE_LABELS` in `src/templates/__init__.py` (used in the frontend dropdown), e.g., `"xx": "New Language"`.

### 4.3 Lexicon Importer (Optional but Recommended)

Add a `_import_<lang>()` function in `src/knowledge/importer.py` that parses a public word list into `Word(text, language, syllables, meaning)` (where `syllables` are produced by your analyser), and wire it into `import_all()`. The query layer `src/knowledge/vocabulary.py` will then provide offline candidates to the `search_words` tool.

### 4.4 Required Tests

- `tests/unit/test_<lang>_analyzer.py`: cover typical use cases for `analyze_word` / `count_syllables` / `tokenize_line` (including multisyllabic words, special spellings).
- If new validation logic is added, add corresponding test cases in `test_meter_validator.py`.
- If the lexicon importer uses offline built‑in examples, provide assertions that do not require network; if it must download data, replace with a local sample or stub in tests to keep `pytest` offline‑capable.
- **Coverage requirement:** the new tests must bring the changed `src` modules (analyser, validator, importer, etc.) to **100% line coverage**. Run `pytest` and confirm it stays green.

---

## 6. Testing Guidelines

- Run: `pytest` (from the repository root, using `pytest.ini`). The command already enforces **100% coverage on `src`** via `--cov=src --cov-fail-under=100`, so it fails if any changed line is uncovered.
- All tests **do not depend on real LLMs / network**: LLMs are replaced by `StubLLMClient` from `tests/helpers.py`.
- Any new feature (meter template / language / analyser / validator) must have corresponding unit tests that achieve **100% coverage of the touched `src` module**; integration changes require end‑to‑end tests under `integration/`.
- Before submitting, ensure `mypy --strict ./`, `ruff check --fix --unsafe-fixes ./`, `ruff format ./`, and `pytest` are all green.

---

## 7. PR Checklist

- [ ] Code passes `mypy --strict ./`
- [ ] Code passes `ruff check --fix --unsafe-fixes ./`
- [ ] Code passes `ruff format ./`
- [ ] `pytest` is fully green, including **100% coverage of the changed `src` modules**
- [ ] New meter templates are registered in both `app.py` and `tests/conftest.py`
- [ ] New language has its analyser registered, language label added, and corresponding unit tests written
- [ ] The PR description explains the purpose and verification method of the changes

PRs should target the `main` branch; after CI (`ci` + `build`) passes, a maintainer will merge.
