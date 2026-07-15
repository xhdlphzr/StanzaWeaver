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
import json
from ..knowledge.vocabulary import search_words as db_search


def execute_search_words(template: dict, arguments: dict) -> dict:
    language = template.get("language", "zh")
    meaning = arguments.get("meaning", "")
    syllable_count = arguments.get("syllable_count")
    onset = arguments.get("onset", "")
    nucleus = arguments.get("nucleus", "")
    coda = arguments.get("coda", "")
    tone = arguments.get("tone", "")
    stress = arguments.get("stress", "")
    length = arguments.get("length", "")
    pos = arguments.get("pos", "")
    limit = arguments.get("limit", 20)

    results = db_search(
        language=language,
        meaning=meaning,
        syllable_count=syllable_count,
        onset=onset,
        nucleus=nucleus,
        coda=coda,
        tone=tone,
        stress=stress,
        length=length,
        pos=pos,
        limit=limit,
    )
    return {"words": results}
