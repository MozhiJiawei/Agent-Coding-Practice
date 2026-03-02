"""
test-simulator 用例运行脚本（无服务启动）

复用已运行的 Mock Rental(:8080) + Model Proxy(:8888) + Agent(:8191)，
直接调用 runner 运行 test_cases.yaml 中的用例，支持 --case / --tag / --all。

用法：
    python -u run_ev_tests.py --all
    python -u run_ev_tests.py --case ev06_wangjing_to_daxing_rental_flow
    python -u run_ev_tests.py --tag ev03
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

# Windows GBK 终端兼容：强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

from config import load_config, load_test_cases, TokenCounter
from runner import generate_reports, print_case_result, run_single_case


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 test_cases.yaml 用例（复用已启动服务）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="运行全部用例")
    group.add_argument("--case", type=str, metavar="CASE_ID", help="运行指定 ID 的单个用例")
    group.add_argument("--tag", type=str, metavar="TAG", help="运行匹配 tag 的所有用例")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    config = load_config("config.yaml")
    all_cases = load_test_cases("test_cases.yaml")

    if args.all:
        cases = all_cases
    elif args.case:
        cases = [c for c in all_cases if c.id == args.case]
        if not cases:
            print(f"[sim] ERROR: 用例 '{args.case}' 不存在", flush=True)
            return 1
    else:
        cases = [c for c in all_cases if args.tag in c.tags]
        if not cases:
            print(f"[sim] ERROR: 未找到 tag='{args.tag}' 的用例", flush=True)
            return 1

    print(f"[sim] 共 {len(cases)} 个用例待运行", flush=True)

    token_counter = TokenCounter()
    results = []
    t0 = time.perf_counter()

    async with httpx.AsyncClient(timeout=config.timeout_per_case + 10.0) as client:
        for i, case in enumerate(cases, 1):
            token_counter.reset()
            result = await run_single_case(case, config, client, token_counter)
            results.append(result)
            print_case_result(i, len(cases), result)
            sys.stdout.flush()

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    passed = sum(1 for r in results if r.status == "PASS")
    failed = len(results) - passed

    print(f"\n{'='*50}", flush=True)
    print(f"Results: {passed}/{len(results)} passed, {failed} failed ({elapsed_ms/1000:.1f}s)", flush=True)

    if failed > 0:
        print("\nFailed cases:", flush=True)
        for r in results:
            if r.status != "PASS":
                print(f"  [{r.status}] {r.case_id}: {r.failure_reason}", flush=True)

    if results:
        report_path = generate_reports(results, config, elapsed_ms)
        print(f"\nReport: {report_path}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    args = parse_args()
    exit_code = asyncio.run(run(args))
    sys.exit(exit_code)
