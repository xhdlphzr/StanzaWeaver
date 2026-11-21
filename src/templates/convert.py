# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""统一的模板转化接口（跨语言转化）.

一个模板对外暴露的完整规格包括：行数、每行音节数、逐位约束（可多份）、
押韵韵式、自定义校验代码。跨语言转化时，除“逐位约束的属性值需要按映射
换成目标语言的属性值”之外，其余部分（行数、音节数、韵式、自定义代码）
原样复制。

本模块是唯一的转化实现：前端“应用转换”、模板编辑 AI 的 set_from_template
工具以及后续任何调用方都通过 :func:`convert_template` 得到同一份结果，避免
多处重复实现转化逻辑。
"""

from typing import Any

from . import custom_template_schemes
from . import get as get_template
from .rhyme import normalize_rhyme_scheme
from .structural import normalize_structural_rules

#: 约束属性值的中文别名（AI/用户可能用中文描述轻重/长短）。
_VALUE_ALIASES: dict[str, str] = {
    "重": "heavy",
    "轻": "light",
    "长": "long",
    "短": "short",
    "平": "平",
    "仄": "仄",
}

#: 自定义模板行数上限。
_MAX_LINES = 30

#: 自定义模板每个音节的取值范围。
_MIN_SYLLABLES = 1
_MAX_SYLLABLES = 100


def constraint_scheme(language: str) -> tuple[str, tuple[str, ...]]:
    """返回某语言的逐位约束方案.

    Args:
        language: 语言代码。

    Returns:
        (属性维度键, 可选值元组)；未知语言按无属性处理。

    """
    return custom_template_schemes().get(language, ("", ()))


def normalize_constraint_value(language: str, value: Any) -> str | None:
    """把约束值归一化为该语言的规范值.

    Args:
        language: 语言代码。
        value: 原始值（可为中文别名）。

    Returns:
        规范值或空串；非法值返回 None。

    """
    attribute, values = constraint_scheme(language)
    if not attribute:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    canonical = _VALUE_ALIASES.get(text, text)
    return canonical if canonical in values else None


def convert_syllable_count(value: Any) -> int:
    """把模板的音节数（定值或区间）转为固定整数（区间取中点）.

    自定义模板的每行音节数只支持固定整数，故区间（如 8-10）取四舍五入中点。

    Args:
        value: int 或 (min, max) 区间。

    Returns:
        正整数；无法解析时返回 7。

    """
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            return max(1, round((int(value[0]) + int(value[1])) / 2))
        except TypeError, ValueError:
            return 7
    try:
        return max(1, int(value))
    except TypeError, ValueError:
        return 7


def _normalize_syllables(source_dict: dict[str, Any], lines: int) -> list[int]:
    """读取并规整源模板的每行音节数.

    Args:
        source_dict: 源模板 to_dict() 结果。
        lines: 行数。

    Returns:
        长度为 lines 的每行音节数列表。

    """
    raw = list(source_dict.get("syllables_per_line", []) or [])
    syllables: list[int] = []
    for item in raw[:lines]:
        count = convert_syllable_count(item)
        syllables.append(max(_MIN_SYLLABLES, min(count, _MAX_SYLLABLES)))
    while len(syllables) < lines:
        syllables.append(syllables[-1] if syllables else 7)
    return syllables


def _source_tables(
    source_dict: dict[str, Any], lines: int, syllables: list[int]
) -> list[list[list[dict[str, Any]]]]:
    """读取源模板的逐位约束并规整为“多份约束表”结构.

    Args:
        source_dict: 源模板 to_dict() 结果。
        lines: 行数。
        syllables: 每行音节数。

    Returns:
        每份约束一个“行 -> 单元格”表；无约束时返回一份空表。

    """
    raw_alternatives = source_dict.get("syllable_constraint_alternatives")
    tables: list[list[Any]]
    if raw_alternatives:
        tables = [list(table or []) for table in raw_alternatives]
    elif source_dict.get("syllable_constraints"):
        tables = [list(source_dict["syllable_constraints"])]
    else:
        tables = [[]]
    normalized: list[list[list[dict[str, Any]]]] = []
    for table in tables:
        rows: list[list[dict[str, Any]]] = []
        for i in range(lines):
            raw_row = table[i] if i < len(table) and isinstance(table[i], list) else []
            cells: list[dict[str, Any]] = []
            for j in range(syllables[i]):
                cell = raw_row[j] if j < len(raw_row) else {}
                cells.append(cell if isinstance(cell, dict) else {})
            rows.append(cells)
        normalized.append(rows)
    return normalized


def _normalize_mapping(
    mapping: Any, source_language: str, target_language: str
) -> tuple[dict[str, str], str | None]:
    """校验并归一化“源属性值 → 目标属性值”映射.

    Args:
        mapping: 原始映射（可为 None/非法类型）。
        source_language: 源语言代码。
        target_language: 目标语言代码。

    Returns:
        (归一化映射, 错误信息)；合法时错误信息为 None。
        多对一是允许的（不同源值可映射到同一目标值），但一个源值只能有
        一个目标值（映射本身是函数）。

    """
    result: dict[str, str] = {}
    if mapping is None:
        return result, None
    if not isinstance(mapping, dict):
        return {}, "mapping 必须是对象"
    for source, target in mapping.items():
        source_value = normalize_constraint_value(source_language, source)
        target_value = normalize_constraint_value(target_language, target)
        if source_value is None:
            return {}, f"源属性值 {source!r} 不合法"
        if target_value is None:
            return {}, f"目标属性值 {target!r} 不合法"
        if source_value:
            result[source_value] = target_value
    return result, None


def _convert_cell(
    cell: dict[str, Any],
    source_attribute: str,
    target_attribute: str,
    target_values: tuple[str, ...],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """把源语言的一个约束单元格转为目标语言约束单元格.

    Args:
        cell: 源单元格（{onset, nucleus, coda, attributes}）。
        source_attribute: 源语言属性维度键（"" 表示无属性）。
        target_attribute: 目标语言属性维度键（"" 表示无属性）。
        target_values: 目标语言允许的属性值。
        mapping: 归一化后的属性值映射。

    Returns:
        目标语言的约束单元格；声母/韵母/韵尾不跨语言携带，一律清空。

    """
    attributes = cell.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}
    source_value = (
        str(attributes.get(source_attribute, "") or "") if source_attribute else ""
    )
    mapped = mapping.get(source_value, "") if target_attribute else ""
    if mapped not in target_values:
        mapped = ""
    target_attributes = {"tone": "", "stress": "", "length": ""}
    if target_attribute and mapped:
        target_attributes[target_attribute] = mapped
    return {
        "onset": "",
        "nucleus": "",
        "coda": "",
        "attributes": target_attributes,
    }


def _convert_structural_rules(
    source_dict: dict[str, Any],
    target_language: str,
    mapping: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    """把源模板的数据化结构规则转换为目标语言版本.

    只替换 attribute/level_value/oblique_value（映射后的目标语言属性与值），
    其余字段（固定位、押韵行、三平尾/孤平开关）原样复制。

    Args:
        source_dict: 源模板 to_dict() 结果。
        target_language: 目标语言代码。
        mapping: 归一化后的属性值映射。

    Returns:
        (规整后的结构规则或 None, 未能携带时的原因)；两者可同时为 None。

    """
    rules, error = normalize_structural_rules(source_dict.get("structural_rules"))
    if error:
        return None, f"源模板结构规则无效（{error}）"
    if rules is None:
        return None, None
    target_attribute, target_values = constraint_scheme(target_language)
    if not target_attribute:
        return None, "近体诗结构规则未携带（目标语言没有可对应的音节属性）"
    level = mapping.get(str(rules["level_value"]), "")
    oblique = mapping.get(str(rules["oblique_value"]), "")
    if (
        not level
        or not oblique
        or level not in target_values
        or oblique not in target_values
    ):
        return None, "近体诗结构规则未携带（映射未覆盖平/仄对应的目标属性值）"
    if level == oblique:
        return None, "近体诗结构规则未携带（映射把平/仄映到同一目标值，无法判定）"
    converted = dict(rules)
    converted["attribute"] = target_attribute
    converted["level_value"] = level
    converted["oblique_value"] = oblique
    converted["positions"] = list(rules["positions"])
    converted["rhyme_lines"] = list(rules["rhyme_lines"])
    return converted, None


def _carried_rule_codes(
    alternatives: list[list[list[dict[str, Any]]]],
    rhyme_scheme: str,
    code: str,
    structural_rules: dict[str, Any] | None,
    rule_note: str,
) -> list[str]:
    """生成“已随转化携带的规则”代码列表（供前端/AI 展示）.

    Args:
        alternatives: 转化后的约束表。
        rhyme_scheme: 转化后的韵式。
        code: 复制的自定义代码。
        structural_rules: 转化后的结构规则。
        rule_note: 复制的模板规则描述。

    Returns:
        规则代码列表（constraints/rhyme/custom_code/jinti）。

    """
    carried = ["constraints"]
    if len(alternatives) > 1:
        carried.append("multiple_kinds")
    if rhyme_scheme:
        carried.append("rhyme")
    if code.strip():
        carried.append("custom_code")
    if structural_rules:
        carried.append("jinti")
    if rule_note.strip():
        carried.append("rule_note")
    return carried


def convert_template(
    base_key: str,
    target_language: str,
    mapping: Any = None,
) -> tuple[dict[str, Any], str | None]:
    """把一个模板的完整规格转化为目标语言的新模板规格.

    行数、每行音节数、约束种类数、押韵韵式与自定义代码原样复制；逐位约束
    的属性值按 mapping 从源语言属性值转换为目标语言属性值（这是转化中
    唯一需要改写的内容）。

    Args:
        base_key: 源模板 key。
        target_language: 目标语言代码（zh/en/fr/it/la）。
        mapping: 源属性值 → 目标属性值的映射。

    Returns:
        (转化后的模板规格, 错误信息)；成功时规格含 status="ok"、lines、
        syllables_per_line、constraints、alternatives、rhyme_scheme、
        rhyme_distinct、code、source_name、source_language、mapped 等字段。

    """
    if target_language not in custom_template_schemes():
        return {}, "不支持的目标语言"
    try:
        source = get_template(base_key)
    except KeyError:
        return {}, f"未知模板 key: {base_key!r}"
    source_dict = source.to_dict()
    source_language = str(source_dict.get("language", ""))
    source_attribute, _source_values = constraint_scheme(source_language)
    target_attribute, target_values = constraint_scheme(target_language)

    normalized_mapping, mapping_error = _normalize_mapping(
        mapping, source_language, target_language
    )
    if mapping_error:
        return {}, mapping_error

    try:
        raw_lines = int(source_dict.get("lines", 4))
    except TypeError, ValueError:
        raw_lines = 4
    lines = max(1, min(raw_lines, _MAX_LINES))
    syllables = _normalize_syllables(source_dict, lines)
    source_tables = _source_tables(source_dict, lines, syllables)
    alternatives: list[list[list[dict[str, Any]]]] = []
    for table in source_tables:
        alternatives.append(
            [
                [
                    _convert_cell(
                        cell,
                        source_attribute,
                        target_attribute,
                        target_values,
                        normalized_mapping,
                    )
                    for cell in row
                ]
                for row in table
            ]
        )

    raw_scheme = str(source_dict.get("rhyme_scheme", "") or "")
    rhyme_scheme, scheme_error = normalize_rhyme_scheme(raw_scheme, lines)
    if scheme_error:
        # 源模板声明的韵式与行数不匹配时无法携带，按“无韵式”处理。
        rhyme_scheme = ""
    rhyme_distinct = bool(source_dict.get("rhyme_distinct", False))
    if not rhyme_scheme:
        rhyme_distinct = False

    structural_rules, structural_drop_reason = _convert_structural_rules(
        source_dict, target_language, normalized_mapping
    )
    custom_code = str(source_dict.get("custom_code", "") or "")
    # 转化后直接复用源模板的规则描述：优先用户自填的 rule_note，
    # 否则复用内置模板/自动生成的 rule_description；用户可在界面上继续修改。
    rule_note = str(source_dict.get("rule_note", "") or "").strip()
    if not rule_note:
        rule_note = str(source_dict.get("rule_description", "") or "").strip()
    carried_rules = _carried_rule_codes(
        alternatives, rhyme_scheme, custom_code, structural_rules, rule_note
    )
    dropped_rules = [str(rule) for rule in (source_dict.get("special_rules") or [])]
    if structural_drop_reason:
        dropped_rules.insert(0, structural_drop_reason)

    spec: dict[str, Any] = {
        "status": "ok",
        "source_template_key": base_key,
        "source_name": str(source_dict.get("name", "")),
        "source_language": source_language,
        "language": target_language,
        "lines": lines,
        "syllables_per_line": syllables,
        "constraints": alternatives[0],
        "alternatives": alternatives,
        "rhyme_scheme": rhyme_scheme,
        "rhyme_distinct": rhyme_distinct,
        "code": custom_code,
        "rule_note": rule_note,
        "structural_rules": structural_rules,
        "carried_rules": carried_rules,
        "dropped_rules": dropped_rules,
        "mapped": normalized_mapping,
    }
    return spec, None


def constraint_tables_to_values(
    tables: list[list[list[dict[str, Any]]]], language: str
) -> list[list[list[str]]]:
    """把约束字典表转换为“规范值字符串表”（供前端/AI 草稿使用）.

    Args:
        tables: 多份约束表（行 -> 单元格 -> {attributes}）。
        language: 语言代码。

    Returns:
        多份值表：约束种类 -> 行 -> 每音节规范值（"" 表示自由）。

    """
    attribute, _values = constraint_scheme(language)
    result: list[list[list[str]]] = []
    for table in tables:
        rows: list[list[str]] = []
        for row in table:
            values: list[str] = []
            for cell in row:
                attributes = (
                    cell.get("attributes", {}) if isinstance(cell, dict) else {}
                )
                if not isinstance(attributes, dict):
                    attributes = {}
                value = str(attributes.get(attribute, "") or "") if attribute else ""
                values.append(value)
            rows.append(values)
        result.append(rows)
    return result
