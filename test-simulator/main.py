"""CLI 入口 + asyncio 服务编排 + 生命周期管理（最小可用版本）"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time

import httpx
import uvicorn

from config import load_config, load_test_cases, load_mock_data, TokenCounter
from model_proxy import create_model_proxy_app
from mock_rental import create_mock_rental_app


async def start_server(app, host: str, port: int) -> uvicorn.Server:
    cfg = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    await server.serve()
    return server


async def run_single_case_stub(
    case_id: str,
    messages: list[str],
    agent_base_url: str,
) -> tuple[str, str]:
    """最小化单用例执行：发送消息至 Agent，返回 (status, detail)。
    不含断言引擎（留 Story 6.1），仅验证链路连通性。"""
    session_id = f"test-{case_id}-{int(time.time())}"
    last_response = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        for msg in messages:
            try:
                r = await client.post(
                    f"{agent_base_url}/api/v1/chat",
                    json={
                        "model_ip": "127.0.0.1",
                        "session_id": session_id,
                        "message": msg,
                    },
                )
                body = r.json()
                if body.get("status") == "error":
                    return "FAIL", f"Agent returned error: {body.get('response', '')[:200]}"
                last_response = body.get("response", "")
            except httpx.ConnectError:
                return "ERROR", f"Agent unreachable at {agent_base_url}"
            except Exception as e:
                return "ERROR", str(e)

    if not last_response:
        return "FAIL", "Agent returned empty response"
    return "PASS", ""


async def main_async(args: argparse.Namespace) -> None:
    config = load_config("config.yaml")
    mock_registry = load_mock_data(config.mock_data_file)
    token_counter = TokenCounter()

    model_proxy_app = create_model_proxy_app(config, token_counter)
    mock_rental_app = create_mock_rental_app(config, mock_registry)

    proxy_task = asyncio.create_task(
        start_server(model_proxy_app, "0.0.0.0", config.model_proxy_port)
    )
    rental_task = asyncio.create_task(
        start_server(mock_rental_app, "0.0.0.0", config.mock_rental_port)
    )

    await asyncio.sleep(1.0)
    print(f"[sim] Model Proxy :{config.model_proxy_port} + Mock Rental :{config.mock_rental_port} started")

    if args.case:
        cases = load_test_cases(config.test_cases_file)
        target = next((c for c in cases if c.id == args.case), None)
        if target is None:
            print(f"[sim] ERROR: case '{args.case}' not found in {config.test_cases_file}")
            proxy_task.cancel()
            rental_task.cancel()
            return

        print(f"[sim] Running case: {target.id} ({target.type})")
        t0 = time.perf_counter()
        status, detail = await run_single_case_stub(
            target.id, target.messages, config.agent_base_url,
        )
        elapsed = time.perf_counter() - t0
        if status == "PASS":
            print(f"[1/1] {target.id} ............ {status}  ({elapsed:.1f}s)")
        else:
            print(f"[1/1] {target.id} ............ {status}  ({elapsed:.1f}s)")
            print(f"       ✗ {detail}")
        print(f"\nResults: {'1 passed' if status == 'PASS' else '0 passed, 1 failed'}")

        proxy_task.cancel()
        rental_task.cancel()
    else:
        print("[sim] No --case specified. Services running for manual testing.")
        print(f"  curl -X POST http://localhost:8191/api/v1/chat -H \"Content-Type: application/json\" \\")
        print(f"    -d '{{\"model_ip\":\"127.0.0.1\",\"session_id\":\"test-001\",\"message\":\"你好\"}}'")
        print("[sim] Ctrl+C to stop")
        try:
            await asyncio.gather(proxy_task, rental_task)
        except asyncio.CancelledError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Simulator — AI Agent 仿真测试工具")
    parser.add_argument("--case", type=str, help="Run a single test case by ID (e.g. chat_hello)")
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
