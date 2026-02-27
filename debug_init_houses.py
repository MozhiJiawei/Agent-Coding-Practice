"""
独立调试脚本：直接测试 init_houses 接口，输出详细诊断信息。

用法：
    $env:USER_ID = "l00933108"
    python debug_init_houses.py
"""
# 确保 USER_ID 在导入 tools 之前设置（tools 模块加载时会读取）
import os
os.environ.setdefault("USER_ID", "l00933108")

# 兼容性检查：httpcore 依赖 anyio.CancelScope，需 anyio>=4.0
try:
    import anyio
    if not hasattr(anyio, "CancelScope"):
        raise RuntimeError(
            "anyio 版本过旧，缺少 CancelScope。请执行: pip install -U 'anyio>=4.0'"
        )
except ImportError:
    pass  # anyio 为 httpx 的传递依赖，通常已安装

import asyncio
import time
import httpx

# 支持通过环境变量覆盖，便于本地 Mock 或不同网络环境
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.197.86.219:8080")
USER_ID = os.environ["USER_ID"]  # 已由 setdefault 保证存在
TARGET_URL = f"{RENTAL_API_BASE}/api/houses/init"

# 快速模式：QUICK_DEBUG=1 时缩短超时以便快速验证（不等待慢 API）
QUICK = os.environ.get("QUICK_DEBUG", "").lower() in ("1", "true", "yes")
DEFAULT_TIMEOUT = 15.0 if QUICK else 30.0
LONG_TIMEOUT = 20.0 if QUICK else 120.0

_connect_error_help_shown = False


def _headers() -> dict:
    return {"X-User-ID": USER_ID}


def _print_sep(title: str = "") -> None:
    print(f"\n{'─' * 60}")
    if title:
        print(f"  {title}")
        print(f"{'─' * 60}")


# ── Case 1: 使用与 main.py 完全相同的客户端配置 ──────────────────
async def test_with_main_config() -> None:
    _print_sep(f"Case 1: 与 main.py 相同配置 (timeout={DEFAULT_TIMEOUT}s, base_url)")
    print(f"  base_url : {RENTAL_API_BASE}")
    print(f"  endpoint : /api/houses/init")
    print(f"  headers  : {_headers()}")

    async with httpx.AsyncClient(
        base_url=RENTAL_API_BASE,
        timeout=DEFAULT_TIMEOUT,
        trust_env=False,  # 不走代理
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
        except httpx.ConnectError as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
            _print_connect_error_help()
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")


# ── Case 2: 使用更长超时 (120s) ────────────────────────────────────
async def test_with_longer_timeout() -> None:
    _print_sep(f"Case 2: 更长超时 (connect=10s, read={LONG_TIMEOUT}s)")
    timeout = httpx.Timeout(connect=10.0, read=LONG_TIMEOUT, write=10.0, pool=10.0)

    async with httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=timeout, trust_env=False) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.post("/api/houses/init", headers=_headers())
            elapsed = time.perf_counter() - t0
            print(f"  status   : {resp.status_code}  ({elapsed:.2f}s)")
            print(f"  body     : {resp.text[:500]}")
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - t0
            print(f"  TIMEOUT  : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
        except httpx.ConnectError as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
            _print_connect_error_help()
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")


# ── Case 3: 使用完整 URL（不拆 base_url）────────────────────────────
async def test_with_full_url() -> None:
    _print_sep("Case 3: 完整 URL（不使用 base_url）")

    async with httpx.AsyncClient(timeout=LONG_TIMEOUT, trust_env=False) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.post(TARGET_URL, headers=_headers())
            elapsed = time.perf_counter() - t0
            print(f"  status   : {resp.status_code}  ({elapsed:.2f}s)")
            print(f"  body     : {resp.text[:500]}")
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - t0
            print(f"  TIMEOUT  : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
        except httpx.ConnectError as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")
            _print_connect_error_help()
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  ERROR    : {type(e).__name__}: {e}  ({elapsed:.2f}s)")


# ── Case 4: 调用 tools.init_houses（真实导入路径）──────────────────
async def test_via_tools_module() -> None:
    _print_sep("Case 4: 通过 tools.init_houses() 调用")
    from tools import init_houses  # noqa: PLC0415

    async with httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=LONG_TIMEOUT, trust_env=False) as client:
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
    print(f"  RENTAL_API_BASE : {repr(RENTAL_API_BASE)}")
    if not raw:
        print("  ⚠  USER_ID 未设置，将使用默认值 l00933108")
    if RENTAL_API_BASE != "http://7.197.86.219:8080":
        print("  ℹ  RENTAL_API_BASE 已通过环境变量覆盖")


def _print_connect_error_help() -> None:
    """连接失败时打印诊断建议（仅首次）"""
    global _connect_error_help_shown
    if _connect_error_help_shown:
        return
    _connect_error_help_shown = True
    print("\n  ═══ 连接失败诊断建议 ═══")
    print("  1. 检查网络：服务器可能仅在内网/比赛 VPN 下可访问")
    print("  2. 尝试 curl 测试：curl -v -X POST -H 'X-User-ID: l00933108' "
          f"'{RENTAL_API_BASE}/api/houses/init'")
    print("  3. 使用本地 Mock：若有 Mock 服务，设置 $env:RENTAL_API_BASE='http://localhost:端口'")
    print("  4. 检查防火墙/代理：脚本已设置 trust_env=False 不走系统代理")


async def main() -> None:
    check_env()
    await test_with_main_config()
    await test_with_longer_timeout()
    await test_with_full_url()
    await test_via_tools_module()
    _print_sep("完成")


if __name__ == "__main__":
    asyncio.run(main())
