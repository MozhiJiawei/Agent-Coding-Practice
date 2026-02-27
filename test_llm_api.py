#!/usr/bin/env python3
"""
大模型接口测试脚本
用于验证 LLM API 的连通性和 chat completions 接口正确性。
参考 agent.py 中的调用方式，独立运行无需依赖 FastAPI 或 tools 模块。
"""

import argparse
import asyncio
import json
import sys
import time
from typing import Optional

import httpx
from openai import AsyncOpenAI


# 默认配置（与 agent.py 一致）
DEFAULT_MODEL_IP = "7.197.86.219"
DEFAULT_PORT = 8888
DEFAULT_BASE_URL = f"http://{DEFAULT_MODEL_IP}:{DEFAULT_PORT}/v1"
DEFAULT_TIMEOUT = 60.0  # 可调大以排查 504


async def test_connectivity(base_url: str, timeout: float) -> bool:
    """测试 1：基础连通性（GET /v1/models）"""
    print("\n[1/3] 测试基础连通性 (GET /v1/models)...")
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            print(f"  ✓ 成功 | 状态码: {resp.status_code} | 可用模型数: {len(models)}")
            if models:
                for m in models[:3]:
                    print(f"    - {m.get('id', 'N/A')}")
            return True
    except httpx.TimeoutException as e:
        print(f"  ✗ 超时: {e}")
        return False
    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {e}")
        return False


async def test_chat_simple(
    base_url: str,
    timeout: float,
    model: str = "",
) -> bool:
    """测试 2：最小化 chat completion（无 tools）"""
    print("\n[2/3] 测试最小化 Chat Completion（无 tools）...")
    # trust_env=False 禁用代理，避免使用 HTTP_PROXY/HTTPS_PROXY 环境变量
    async with httpx.AsyncClient(trust_env=False, timeout=timeout) as http_client:
        client = AsyncOpenAI(
            base_url=base_url,
            api_key="placeholder",
            timeout=timeout,
            http_client=http_client,
        )
        messages = [{"role": "user", "content": "你好，请用一句话回复。"}]
        try:
            start = time.perf_counter()
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
            )
            elapsed = (time.perf_counter() - start) * 1000
            if resp.choices:
                content = (resp.choices[0].message.content or "").strip()
                print(f"  ✓ 成功 | 耗时: {elapsed:.0f}ms")
                print(f"    回复: {content[:200]}{'...' if len(content) > 200 else ''}")
            else:
                print(f"  ✗ 返回无 choices: {resp}")
            return bool(resp.choices)
        except Exception as e:
            print(f"  ✗ 失败: {type(e).__name__}: {e}")
            return False


async def test_chat_with_tools(
    base_url: str,
    timeout: float,
    model: str = "",
) -> bool:
    """测试 3：带 tools 的 chat completion（与 agent.py 调用一致）"""
    print("\n[3/3] 测试带 Tools 的 Chat Completion（与 agent 调用一致）...")
    # 最小化 tools，避免依赖 tools.py 的 USER_ID
    minimal_tools = [
        {
            "type": "function",
            "function": {
                "name": "search_houses",
                "description": "搜索房源",
                "parameters": {
                    "type": "object",
                    "properties": {"district": {"type": "string"}},
                    "required": [],
                },
            },
        }
    ]
    # trust_env=False 禁用代理，避免使用 HTTP_PROXY/HTTPS_PROXY 环境变量
    async with httpx.AsyncClient(trust_env=False, timeout=timeout) as http_client:
        client = AsyncOpenAI(
            base_url=base_url,
            api_key="placeholder",
            timeout=timeout,
            http_client=http_client,
        )
        messages = [
            {"role": "system", "content": "你是租房助手。收到用户消息后，如需搜索房源请调用 search_houses。"},
            {"role": "user", "content": "海淀区有什么房源？"},
        ]
        try:
            start = time.perf_counter()
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=minimal_tools,
                tool_choice="auto",
            )
            elapsed = (time.perf_counter() - start) * 1000
            if resp.choices:
                msg = resp.choices[0].message
                finish = resp.choices[0].finish_reason
                content = (msg.content or "").strip()
                tool_calls = getattr(msg, "tool_calls", []) or []
                print(f"  ✓ 成功 | 耗时: {elapsed:.0f}ms | finish_reason: {finish}")
                if content:
                    print(f"    内容: {content[:150]}{'...' if len(content) > 150 else ''}")
                if tool_calls:
                    print(f"    tool_calls: {[tc.function.name for tc in tool_calls]}")
            else:
                print(f"  ✗ 返回无 choices: {resp}")
            return bool(resp.choices)
        except Exception as e:
            print(f"  ✗ 失败: {type(e).__name__}: {e}")
            return False


def parse_args():
    parser = argparse.ArgumentParser(description="大模型接口测试脚本")
    parser.add_argument(
        "--ip",
        default=DEFAULT_MODEL_IP,
        help=f"大模型服务 IP（默认: {DEFAULT_MODEL_IP}）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"服务端口（默认: {DEFAULT_PORT}）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"请求超时秒数（默认: {DEFAULT_TIMEOUT}，504 时可尝试调大）",
    )
    parser.add_argument(
        "--model",
        default="",
        help="模型名称（空字符串表示服务默认）",
    )
    parser.add_argument(
        "--skip-tools",
        action="store_true",
        help="跳过带 tools 的测试（仅做连通性和简单 chat 测试）",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    base_url = f"http://{args.ip}:{args.port}/v1"
    print("=" * 60)
    print("大模型接口测试")
    print("=" * 60)
    print(f"  base_url: {base_url}")
    print(f"  timeout:  {args.timeout}s")
    print(f"  model:    {repr(args.model) or '(服务默认)'}")

    ok1 = await test_connectivity(base_url, args.timeout)
    ok2 = await test_chat_simple(base_url, args.timeout, args.model)
    ok3 = True
    if not args.skip_tools:
        ok3 = await test_chat_with_tools(base_url, args.timeout, args.model)
    else:
        print("\n[3/3] 跳过（--skip-tools）")

    print("\n" + "=" * 60)
    all_ok = ok1 and ok2 and ok3
    if all_ok:
        print("全部测试通过 ✓")
    else:
        print("存在失败项，请检查网络/服务/超时配置")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
