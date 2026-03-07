#!/usr/bin/env python3
"""
从 test_cases.yaml 中提取每条用例的用户请求（messages），
写入同级目录的 user_requests.yaml。
"""

import yaml
from pathlib import Path


def main():
    script_dir = Path(__file__).resolve().parent
    input_file = script_dir / "test_cases.yaml"
    output_file = script_dir / "user_requests.yaml"

    with open(input_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cases = data.get("test_cases", [])
    if not cases:
        print("未找到 test_cases")
        return

    extracted = []
    for case in cases:
        case_id = case.get("id", "")
        msg_list = case.get("messages", [])
        # 保证 messages 是字符串列表
        messages = [m if isinstance(m, str) else str(m) for m in msg_list]
        extracted.append({
            "id": case_id,
            "type": case.get("type", ""),
            "messages": messages,
        })

    out_data = {"user_requests": extracted}

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(
            out_data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"已从 {len(cases)} 条用例中提取用户请求，写入: {output_file}")


if __name__ == "__main__":
    main()
