# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

def execute_submit(poem: list[str]) -> dict:
    return {
        "status": "submitted",
        "poem": list(poem),
        "message": "诗稿已提交给检查AI进行终审。",
    }
