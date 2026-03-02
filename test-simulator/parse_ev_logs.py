#!/usr/bin/env python3
"""从 logs 目录解析 EV-XX 评估日志，提取 user messages 和 metadata，用于生成 test_cases。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from collections import defaultdict

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def parse_ev_log(jsonl_path: Path) -> dict:
    """解析单个 EV 日志，返回 messages、has_tool_call、ev_id。"""
    messages: list[str] = []
    has_tool_call = False
    ev_id = ""

    m = re.search(r"EV-(\d+)", jsonl_path.name)
    if m:
        ev_id = f"EV-{int(m.group(1)):02d}"

    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = event.get("event", "")
            details = event.get("details") or {}
            if etype == "USER_REQUEST":
                msg = details.get("message", "")
                if msg:
                    messages.append(msg)
            elif etype == "TOOL_CALL":
                has_tool_call = True

    return {"ev_id": ev_id, "messages": messages, "has_tool_call": has_tool_call}


def main():
    log_files = sorted(LOGS_DIR.glob("eval_*_EV-*.jsonl"))
    # 按 EV-XX 去重，保留每个 EV 最新的一份（文件名中 timestamp 较大）
    by_ev: dict[str, Path] = {}
    for p in log_files:
        m = re.search(r"EV-(\d+)", p.name)
        if m:
            key = int(m.group(1))
            ev_key = f"EV-{key:02d}"
            if ev_key not in by_ev or p.name > by_ev[ev_key].name:
                by_ev[ev_key] = p

    cases = []
    for ev_key in sorted(by_ev.keys(), key=lambda x: int(x.split("-")[1])):
        path = by_ev[ev_key]
        data = parse_ev_log(path)
        if not data["messages"]:
            continue
        cases.append(
            {
                "ev_id": data["ev_id"],
                "messages": data["messages"],
                "has_tool_call": data["has_tool_call"],
                "log_file": path.name,
            }
        )
    return cases


if __name__ == "__main__":
    import yaml
    out_path = Path(__file__).parent / "_parsed_ev_cases.yaml"
    cases = main()
    with out_path.open("w", encoding="utf-8") as f:
        yaml.dump(cases, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"Written {len(cases)} cases to {out_path}")
