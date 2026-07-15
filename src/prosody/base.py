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

from abc import ABC, abstractmethod
from ..models.syllable import Syllable


class SyllableAnalyzer(ABC):
    language: str = ""

    @abstractmethod
    def analyze_word(self, word: str) -> list[Syllable]:
        ...

    @abstractmethod
    def count_syllables(self, text: str) -> int:
        ...

    def tokenize_line(self, line: str) -> list[str]:
        return line.split()
