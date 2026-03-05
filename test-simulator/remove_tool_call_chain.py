#!/usr/bin/env python3
"""从 test_cases.yaml 中移除所有 tool_call_chain 键及其列表值。"""
import re
from pathlib import Path

YAML_PATH = Path(__file__).resolve().parent / "test_cases.yaml"

# 匹配 "tool_call_chain:" 行（仅键，任意缩进）
KEY_PATTERN = re.compile(r"^\s*tool_call_chain:\s*$")
# 匹配 YAML 列表项：缩进 + "- " + 内容
LIST_ITEM_PATTERN = re.compile(r"^\s+-\s+.+$")


def main() -> None:
    content = YAML_PATH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    skip_until_next_key = False

    for line in lines:
        if KEY_PATTERN.match(line):
            skip_until_next_key = True
            continue
        if skip_until_next_key:
            # 只跳过紧跟在 tool_call_chain 后的列表项行
            if LIST_ITEM_PATTERN.match(line):
                continue
            skip_until_next_key = False
        out.append(line)

    YAML_PATH.write_text("".join(out), encoding="utf-8")
    print(f"已从 {YAML_PATH} 中移除所有 tool_call_chain 块。")


if __name__ == "__main__":
    main()
