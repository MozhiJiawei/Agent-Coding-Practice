"""CLI 入口 + asyncio 服务编排 + 生命周期管理"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time

# Windows GBK 终端兼容：强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import uvicorn

from config import TokenCounter, load_config, load_fixtures, load_test_cases
from mock_rental import create_mock_rental_app
from model_proxy import create_model_proxy_app
from runner import generate_reports, print_case_result, run_cases_parallel


async def start_server(app, host: str, port: int) -> None:
    cfg = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    await server.serve()


async def main_async(args: argparse.Namespace) -> None:
    config = load_config("config.yaml")
    fixtures = load_fixtures(config.fixture_file)
    token_counter = TokenCounter()

    model_proxy_app = create_model_proxy_app(config, token_counter)
    mock_rental_app = create_mock_rental_app(config, fixtures)

    proxy_task = asyncio.create_task(
        start_server(model_proxy_app, "0.0.0.0", config.model_proxy_port)
    )
    rental_task = asyncio.create_task(
        start_server(mock_rental_app, "0.0.0.0", config.mock_rental_port)
    )

    await asyncio.sleep(1.0)
    print(f"[sim] Model Proxy :{config.model_proxy_port} + Mock Rental :{config.mock_rental_port} started")

    try:
        cases = load_test_cases(config.test_cases_file)

        if args.case:
            filtered = [c for c in cases if c.id == args.case]
            if not filtered:
                print(f"[sim] ERROR: case '{args.case}' not found in {config.test_cases_file}")
                return
        elif args.tag:
            filtered = [c for c in cases if args.tag in c.tags]
            if not filtered:
                print(f"[sim] ERROR: no cases found with tag '{args.tag}' in {config.test_cases_file}")
                return
        elif args.all:
            filtered = cases
        else:
            filtered = None

        if filtered is None:
            print("[sim] No --case/--tag/--all specified. Services running for manual testing.")
            print("  curl -X POST http://localhost:8191/api/v1/chat -H \"Content-Type: application/json\" \\")
            print("    -d '{\"model_ip\":\"127.0.0.1\",\"session_id\":\"test-001\",\"message\":\"你好\"}'")
            print("[sim] Ctrl+C to stop")
            try:
                await asyncio.gather(proxy_task, rental_task)
            except asyncio.CancelledError:
                pass
            return

        total_cases = len(filtered)
        concurrency = min(config.max_concurrency, 15)
        print(f"[sim] 共 {total_cases} 个用例待运行，并发度={concurrency}", flush=True)

        t0 = time.perf_counter()
        results = []
        try:
            results = await run_cases_parallel(
                filtered,
                config,
                max_concurrency=concurrency,
                on_result=lambda done, total, result: print_case_result(done, total, result),
            )
        finally:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            if results:
                report_path = generate_reports(results, config, elapsed_ms)
                passed = sum(1 for r in results if r.status == "PASS")
                failed = len(results) - passed
                print(f"\nResults: {passed} passed, {failed} failed ({elapsed_ms / 1000:.1f}s total)")
                print(f"Report: {report_path}")
    finally:
        proxy_task.cancel()
        rental_task.cancel()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Simulator — AI Agent 仿真测试工具")
    parser.add_argument("--all", action="store_true", help="Run all test cases")
    parser.add_argument("--case", type=str, help="Run a single test case by ID (e.g. chat_hello)")
    parser.add_argument("--tag", type=str, help="Run test cases matching a tag (e.g. smoke)")
    return parser.parse_args()


def _handle_signal(loop: asyncio.AbstractEventLoop) -> None:
    for task in asyncio.all_tasks(loop):
        task.cancel()


if __name__ == "__main__":
    parsed = parse_args()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal, loop)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: _handle_signal(loop))
    try:
        loop.run_until_complete(main_async(parsed))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[sim] Shutting down...")
    finally:
        remaining = asyncio.all_tasks(loop)
        for t in remaining:
            t.cancel()
        if remaining:
            loop.run_until_complete(asyncio.gather(*remaining, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
