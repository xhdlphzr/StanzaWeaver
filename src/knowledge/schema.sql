-- Copyright (C) 2026 xhdlphzr
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- This program is free software: you can redistribute it and/or modify
-- it under the terms of the GNU Affero General Public License as published by
-- the Free Software Foundation, either version 3 of the License, or
-- (at your option) any later version.
--
-- This program is distributed in the hope that it will be useful,
-- but WITHOUT ANY WARRANTY; without even the implied warranty of
-- MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
-- GNU Affero General Public License for more details.
--
-- You should have received a copy of the GNU Affero General Public License
-- along with this program.  If not, see <https://www.gnu.org/licenses/>.
--
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
    pos TEXT DEFAULT '',
    meaning TEXT DEFAULT '',
    onset TEXT DEFAULT '',
    nucleus TEXT DEFAULT '',
    coda TEXT DEFAULT '',
    tone TEXT DEFAULT '',
    stress TEXT DEFAULT '',
    length TEXT DEFAULT '',
    syllable_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_words_language ON words(language);
CREATE INDEX IF NOT EXISTS idx_words_text ON words(text);
CREATE INDEX IF NOT EXISTS idx_words_pos ON words(pos);
CREATE INDEX IF NOT EXISTS idx_words_onset ON words(onset);
CREATE INDEX IF NOT EXISTS idx_words_nucleus ON words(nucleus);
CREATE INDEX IF NOT EXISTS idx_words_coda ON words(coda);
CREATE INDEX IF NOT EXISTS idx_words_tone ON words(tone);
CREATE INDEX IF NOT EXISTS idx_words_stress ON words(stress);
CREATE INDEX IF NOT EXISTS idx_words_length ON words(length);
CREATE INDEX IF NOT EXISTS idx_words_syllable_count ON words(syllable_count);
