#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 merged_all.jsonl 解析用例，以 c1~c20 同样风格更新 test_cases.yaml 中的 final-test 用例。
用法: 在 test-simulator 目录下运行 python update_test_cases_from_merged.py
"""

import json
import re
from pathlib import Path

import yaml

# 简单问候语视为 Chat 类型（单轮、无工具）
CHAT_GREETINGS = ("你好", "你好呀", "您好", "你好，你可以做什么")


def parse_merged_jsonl(path: Path) -> list[dict]:
    """解析 merged_all.jsonl，返回用例列表，每项为 {messages: [str, ...]}"""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n# ====== 开始：", text)
    cases = []
    for block in blocks:
        block = block.strip()
        if not block or "USER_REQUEST" not in block:
            continue
        messages = []
        for line in block.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
                if row.get("event") == "USER_REQUEST":
                    details = row.get("details") or {}
                    msg = details.get("message")
                    if msg:
                        messages.append(msg)
            except json.JSONDecodeError:
                continue
        if messages:
            cases.append({"messages": messages})
    return cases


def case_type(messages: list[str]) -> str:
    """与 c1~c20 一致：单条且为问候 -> Chat；单条 -> Single；多条 -> Multi"""
    if len(messages) == 1:
        first = (messages[0] or "").strip()
        if first in CHAT_GREETINGS or first.startswith("你好") and len(first) <= 12:
            return "Chat"
        return "Single"
    return "Multi"


def build_final_test_cases(cases: list[dict]) -> list[dict]:
    """构建与 c1~c20 同风格的 final-test 用例列表"""
    out = []
    for i, c in enumerate(cases, start=1):
        msgs = c["messages"]
        out.append({
            "id": f"c{i}",
            "type": case_type(msgs),
            "fixture_file": "mock_data/final-test.yaml",
            "messages": msgs,
            "expect": {
                "has_response": True,
                "response_not_empty": True,
                "status_success": True,
            },
            "tags": ["final-test"],
        })
    return out


def main():
    base = Path(__file__).resolve().parent
    merged_path = base / "merged_all.jsonl"
    yaml_path = base / "test_cases.yaml"

    if not merged_path.exists():
        raise SystemExit(f"未找到: {merged_path}")
    if not yaml_path.exists():
        raise SystemExit(f"未找到: {yaml_path}")

    cases = parse_merged_jsonl(merged_path)
    print(f"从 merged_all.jsonl 解析到 {len(cases)} 个用例")

    final_cases = build_final_test_cases(cases)

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 去掉原有带 final-test 的用例，再追加新用例
    test_cases = data.get("test_cases") or []
    rest = [tc for tc in test_cases if not (tc.get("tags") and "final-test" in tc.get("tags", []))]
    data["test_cases"] = rest + final_cases

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )

    print(f"已更新 {yaml_path}：保留非 final-test 用例，并写入 {len(final_cases)} 条 final-test 用例 (c1~c{len(final_cases)})")


if __name__ == "__main__":
    main()
