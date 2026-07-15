# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from ..prosody.meter_validator import MeterValidator


def execute_refine_line(
    poem: list[str],
    template: dict,
    arguments: dict,
) -> dict:
    line_idx = arguments.get("line", -1)
    new_text = arguments.get("new_text", "")

    if line_idx < 0 or line_idx >= len(poem):
        return {"error": f"行号 {line_idx} 越界，共 {len(poem)} 行"}

    validator = MeterValidator()
    result = validator.validate_line(new_text, line_idx, template)
    if not result.passed:
        return {"error": result.errors}

    old_text = poem[line_idx]
    poem[line_idx] = new_text
    return {
        "poem": list(poem),
        "changed_line": line_idx,
        "old_text": old_text,
        "new_text": new_text,
    }
