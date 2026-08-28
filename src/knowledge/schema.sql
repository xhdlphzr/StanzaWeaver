-- Copyright (c) 2026 xhdlphzr
-- SPDX-License-Identifier: MIT

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
    meaning TEXT DEFAULT '',
    syllables_json TEXT DEFAULT '[]',
    syllable_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_words_language ON words(language);
CREATE INDEX IF NOT EXISTS idx_words_text ON words(text);
CREATE INDEX IF NOT EXISTS idx_words_syllable_count ON words(syllable_count);
