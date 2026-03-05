#!/usr/bin/env python3
"""
去除 test_cases.yaml 中所有 houses_match 的 ID 检查，仅保留有房/无房检查：
- 原有 houses_match 非空或 houses_match_subset 且非空 → 删除 ID 列表，保留 house_count_min: 1（有房）
- 原有 houses_match: [] → 删除后改为 house_count_max: 0（无房）

用法（在 test-simulator 目录下）：
  python strip_houses_match_ids.py
  python strip_houses_match_ids.py --dry-run
  python strip_houses_match_ids.py --test-cases path/to/test_cases.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TEST_CASES = SCRIPT_DIR / "test_cases.yaml"


def process_expect(expect: dict) -> bool:
    """处理单个 expect 字典，移除 houses_match/houses_match_subset，改为 house_count_min/ house_count_max。返回是否有修改。"""
    if not expect:
        return False
    has_match = "houses_match" in expect
    has_subset = "houses_match_subset" in expect
    if not has_match and not has_subset:
        return False

    houses = expect.get("houses_match")
    is_empty = houses is not None and (houses == [] or (isinstance(houses, list) and len(houses) == 0))

    if "houses_match" in expect:
        del expect["houses_match"]
    if "houses_match_subset" in expect:
        del expect["houses_match_subset"]

    if is_empty:
        expect["house_count_max"] = 0
    else:
        # 有房：至少 1 条（若已有 house_count_min 则保留，否则设为 1）
        if expect.get("house_count_min") is None:
            expect["house_count_min"] = 1
    return True


def process_case(case: dict) -> int:
    """处理一个用例的 expect 与 round_expects，返回修改的 expect 块数量。"""
    n = 0
    top = case.get("expect")
    if top and process_expect(top):
        n += 1
    for re in case.get("round_expects") or []:
        ex = re.get("expect") if isinstance(re, dict) else getattr(re, "expect", None)
        if ex and process_expect(ex):
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="去除 houses_match ID 检查，仅保留有房/无房")
    parser.add_argument("--test-cases", "-t", type=str, default=str(DEFAULT_TEST_CASES), help="test_cases.yaml 路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印将修改的条目，不写回文件")
    args = parser.parse_args()

    path = Path(args.test_cases)
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 1

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cases = data.get("test_cases") or []
    total_changes = 0
    for case in cases:
        cid = case.get("id", "?")
        n = process_case(case)
        if n:
            total_changes += n
            print(f"  {cid}: 修改 {n} 处 expect", file=sys.stderr)

    if total_changes == 0:
        print("未发现需要修改的 houses_match/houses_match_subset 条目。", file=sys.stderr)
        return 0

    if args.dry_run:
        print(f"[dry-run] 共将修改 {total_changes} 处，不写回。", file=sys.stderr)
        return 0

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=200,
        )
    print(f"已写回 {path}，共修改 {total_changes} 处。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
