"""
test-simulator 用例运行脚本（无服务启动）

复用已运行的 Mock Rental(:8080) + Model Proxy(:8888) + Agent(:8191)，
直接调用 runner 运行 test_cases.yaml 中的用例，支持 --case / --tag / --all。

用法：
    python -u run_ev_tests.py --all
    python -u run_ev_tests.py --all --concurrency 10
    python -u run_ev_tests.py --case ev06_wangjing_to_daxing_rental_flow
    python -u run_ev_tests.py --case ev01 ev02 ev03
    python -u run_ev_tests.py --tag ev03
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

# Windows GBK 终端兼容：强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

from config import load_config, load_test_cases
from runner import generate_reports, print_case_result, run_cases_parallel


def post_result_to_dashboard(result: dict, config) -> None:
    """POST case result to Dashboard for visualization."""
    url = f"http://localhost:{config.dashboard_port}/api/case-result"
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(url, json=result)
    except Exception:
        pass  # Dashboard may not be running


def save_html_report(config) -> str | None:
    """Fetch export-html from Dashboard and save to report_dir. Returns path or None."""
    url = f"http://localhost:{config.dashboard_port}/api/export-html"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
            if r.status_code != 200:
                return None
            html = r.text
    except Exception:
        return None
    os.makedirs(config.report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(config.report_dir, f"report-{timestamp}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 test_cases.yaml 用例（复用已启动服务）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="运行全部用例")
    group.add_argument("--case", type=str, action="append", metavar="CASE_ID", help="运行指定 ID 的用例（可多次传入多个）")
    group.add_argument("--tag", type=str, metavar="TAG", help="运行匹配 tag 的所有用例")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        metavar="N",
        help="最大并发数（默认取 config.yaml 中的 max_concurrency，上限 15）",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    config = load_config("config.yaml")
    all_cases = load_test_cases("test_cases.yaml")

    if args.all:
        cases = all_cases
    elif args.case:
        requested = set(args.case)  # args.case 为 list（每次 --case xxx 追加一个）
        cases = [c for c in all_cases if c.id in requested]
        missing = requested - {c.id for c in cases}
        if missing:
            print(f"[sim] ERROR: 用例不存在: {', '.join(sorted(missing))}", flush=True)
            return 1
    else:
        cases = [c for c in all_cases if args.tag in c.tags]
        if not cases:
            print(f"[sim] ERROR: 未找到 tag='{args.tag}' 的用例", flush=True)
            return 1

    concurrency = args.concurrency if args.concurrency is not None else config.max_concurrency
    concurrency = min(concurrency, 15)

    print(f"[sim] 共 {len(cases)} 个用例待运行，并发度={concurrency}", flush=True)

    t0 = time.perf_counter()

    def on_result(done: int, total: int, result) -> None:
        print_case_result(done, total, result)
        post_result_to_dashboard(result.model_dump(), config)
        sys.stdout.flush()

    results = await run_cases_parallel(
        cases,
        config,
        max_concurrency=concurrency,
        on_result=on_result,
    )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    passed = sum(1 for r in results if r.status == "PASS")
    failed = len(results) - passed

    print(f"\n{'='*50}", flush=True)
    print(f"Results: {passed}/{len(results)} passed, {failed} failed ({elapsed_ms/1000:.1f}s)", flush=True)

    if failed > 0:
        print("\nFailed cases:", flush=True)
        for r in results:
            if r.status != "PASS":
                print(f"  [{r.status}] {r.case_id}:", flush=True)
                if r.failure_reason:
                    for line in r.failure_reason.split("\n"):
                        print(f"    \u2717 {line}", flush=True)

    if results:
        report_path = generate_reports(results, config, elapsed_ms)
        print(f"\nReport: {report_path}", flush=True)
        html_path = save_html_report(config)
        if html_path:
            print(f"HTML report: {html_path}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    # Windows: 使用 Selector 事件循环，避免 ProactorEventLoop 导致进程无法退出（run_e2e.ps1 等调用时能正常退出）
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = parse_args()
    exit_code = asyncio.run(run(args))
    # Windows: 直接退出进程，避免 asyncio/线程池等导致子进程不退出、run_e2e.ps1 无法结束
    if sys.platform == "win32":
        os._exit(exit_code)
    sys.exit(exit_code)
