-- Copyright (c) 2026 xhdlphzr
-- SPDX-License-Identifier: MIT

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_words_onset ON words(onset);
CREATE INDEX IF NOT EXISTS idx_words_nucleus ON words(nucleus);
CREATE INDEX IF NOT EXISTS idx_words_coda ON words(coda);
CREATE INDEX IF NOT EXISTS idx_words_tone ON words(tone);
CREATE INDEX IF NOT EXISTS idx_words_stress ON words(stress);
CREATE INDEX IF NOT EXISTS idx_words_length ON words(length);
CREATE INDEX IF NOT EXISTS idx_words_syllable_count ON words(syllable_count);
