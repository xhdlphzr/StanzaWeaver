# Copyright (C) 2026 xhdlphzr
# SPDX-License-Identifier: AGPL-3.0-or-later

from ..prosody.meter_validator import MeterValidator


def execute_submit(poem: list[str]) -> dict:
    return {
        "status": "submitted",
        "poem": list(poem),
        "message": "诗稿已提交给检查AI进行终审。",
    }
