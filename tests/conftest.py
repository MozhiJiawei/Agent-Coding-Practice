"""
pytest conftest：全局测试环境配置。
- 预设 USER_ID 环境变量，避免 tools.py 模块级 KeyError
- autouse fixture 在每个测试前清空 sessions / session_preferences，保证测试隔离
- autouse mock init_houses / get_all_houses_for_debug / get_all_landmarks_for_debug 防止发起真实 HTTP 请求
- anyio 后端限定为 asyncio（trio 未安装）
- rental_client / require_mock_rental：对接 test-simulator Mock Rental (localhost:8080)
"""
import os

os.environ.setdefault("USER_ID", "test-user-placeholder")

import httpx
import pytest
from unittest.mock import AsyncMock, patch
import main as _main_module

# ── Mock Rental 连接配置 ─────────────────────────────────────────────────────
MOCK_RENTAL_URL = "http://localhost:8080"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def _mock_rental_reachable():
    """session 级探测：Mock Rental 是否可达（只探测一次）"""
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as c:
            r = c.get(f"{MOCK_RENTAL_URL}/api/landmarks")
            return r.status_code < 500
    except Exception:
        return False


@pytest.fixture
def require_mock_rental(_mock_rental_reachable):
    """不可达时自动 skip，附启动命令提示"""
    if not _mock_rental_reachable:
        pytest.skip(
            "Mock Rental(8080) 未运行，跳过对接测试。"
            "启动命令: cd test-simulator && python main.py"
        )


@pytest.fixture
async def rental_client(require_mock_rental):
    """真实 httpx.AsyncClient，base_url 指向 Mock Rental，供对接测试使用"""
    async with httpx.AsyncClient(
        base_url=MOCK_RENTAL_URL,
        headers={"X-User-ID": os.environ.get("USER_ID", "test-user-placeholder")},
        timeout=10.0,
        trust_env=False,
    ) as client:
        yield client


@pytest.fixture(autouse=True)
def _clear_sessions():
    _main_module.sessions.clear()
    _main_module.session_preferences.clear()
    yield
    _main_module.sessions.clear()
    _main_module.session_preferences.clear()


@pytest.fixture(autouse=True)
def _mock_init_houses():
    """防止 init_houses、get_all_houses_for_debug、get_all_landmarks_for_debug 发起真实 HTTP 请求。
    需要显式测试这些行为的测试类可用自己的 patch 覆盖此 fixture。
    """
    with patch("main.init_houses", new=AsyncMock(return_value={"status": "ok"})):
        with patch(
            "main.get_all_houses_for_debug",
            new=AsyncMock(
                return_value={
                    "链家": {"total": 0, "items": []},
                    "安居客": {"total": 0, "items": []},
                    "58同城": {"total": 0, "items": []},
                }
            ),
        ):
            with patch(
                "main.get_all_landmarks_for_debug",
                new=AsyncMock(return_value={"total": 0, "items": []}),
            ):
                yield


@pytest.fixture(autouse=True)
def _mock_run_agent():
    """防止 run_agent 发起真实 LLM 调用。
    默认返回空成功响应；需要测试真实 run_agent 行为的测试可用自己的 patch 覆盖此 fixture。
    """
    default_result = {"response": "Agent not implemented", "status": "error", "tool_results": []}
    with patch("main.run_agent", new=AsyncMock(return_value=default_result)):
        yield
