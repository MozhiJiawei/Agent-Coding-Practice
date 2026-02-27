"""
独立调试脚本：直接测试 init_houses 接口，输出详细诊断信息。

用法：
    $env:USER_ID = "l00933108"
    python debug_init_houses.py
"""
import asyncio
import os
import time
import httpx

RENTAL_API_BASE = "http://7.197.86.219:8080"
USER_ID = os.environ.get("USER_ID", "l00933108")
TARGET_URL = f"{RENTAL_API_BASE}/api/houses/init"


def _headers() -> dict:
    return {"X-User-ID": USER_ID}


def _print_sep(title: str = "") -> None:
    print(f"\n{'─' * 60}")
    if title:
        print(f"  {title}")
        print(f"{'─' * 60}")


# ── Case 1: 使用与 main.py 完全相同的客户端配置 ──────────────────
async def test_with_main_config() -> None:
    _print_sep("Case 1: 与 main.py 相同配置 (timeout=30s, base_url)")
    print(f"  base_url : {RENTAL_API_BASE}")
    print(f"  endpoint : /api/houses/init")
    print(f"  headers  : {_headers()}")

    async with httpx.AsyncClient(
        base_url=RENTAL_API_BASE,
        timeout=30.0,
    ) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.post("/api/houses/init", headers=_headers())
            elapsed = time.perf_counter() - t0
            print(f"  status   : {resp.status_code}  ({elapsed:.2f}s)")
            print(f"  body     : {resp.text[:500]}")
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - t0
            print(f"  TIMEOUT  : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")


# ── Case 2: 使用更长超时 (120s) ────────────────────────────────────
async def test_with_longer_timeout() -> None:
    _print_sep("Case 2: 更长超时 (connect=10s, read=120s)")
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

    async with httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=timeout) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.post("/api/houses/init", headers=_headers())
            elapsed = time.perf_counter() - t0
            print(f"  status   : {resp.status_code}  ({elapsed:.2f}s)")
            print(f"  body     : {resp.text[:500]}")
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - t0
            print(f"  TIMEOUT  : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")


# ── Case 3: 使用完整 URL（不拆 base_url）────────────────────────────
async def test_with_full_url() -> None:
    _print_sep("Case 3: 完整 URL（不使用 base_url）")

    async with httpx.AsyncClient(timeout=120.0) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.post(TARGET_URL, headers=_headers())
            elapsed = time.perf_counter() - t0
            print(f"  status   : {resp.status_code}  ({elapsed:.2f}s)")
            print(f"  body     : {resp.text[:500]}")
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - t0
            print(f"  TIMEOUT  : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")


# ── Case 4: 调用 tools.init_houses（真实导入路径）──────────────────
async def test_via_tools_module() -> None:
    _print_sep("Case 4: 通过 tools.init_houses() 调用")
    from tools import init_houses  # noqa: PLC0415

    async with httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=120.0) as client:
        t0 = time.perf_counter()
        result = await init_houses(client)
        elapsed = time.perf_counter() - t0
        print(f"  elapsed  : {elapsed:.2f}s")
        print(f"  result   : {result}")


# ── Case 5: 检查 USER_ID 环境变量是否正确 ─────────────────────────
def check_env() -> None:
    _print_sep("Env Check")
    raw = os.environ.get("USER_ID")
    print(f"  USER_ID (env)    : {repr(raw)}")
    print(f"  USER_ID (loaded) : {repr(USER_ID)}")
    if not raw:
        print("  ⚠  USER_ID 未设置，将使用默认值 l00933108")


async def main() -> None:
    check_env()
    await test_with_main_config()
    await test_with_longer_timeout()
    await test_with_full_url()
    await test_via_tools_module()
    _print_sep("完成")


if __name__ == "__main__":
    asyncio.run(main())
