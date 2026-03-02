"""
tests/e2e/conftest.py — E2E 冒烟测试专用配置

依赖真实运行的服务（不使用 mock）：
  - Agent:        http://localhost:8191
  - Model Proxy:  http://localhost:8888  (test-simulator)
  - Mock Rental:  http://localhost:8080  (test-simulator)
  - SiliconFlow:  https://api.siliconflow.cn  (外部 LLM)

运行前置条件：
  1. 主 Agent 已启动：cd <repo_root> && USER_ID=xxx python -m uvicorn main:app --port 8191
  2. Test Simulator 已启动：cd test-simulator && python main.py

跳过策略：
  若目标服务不可达，对应测试组自动 skip（不报 FAIL）。
  若 .api_key 文件不存在，LLM 相关测试 skip。
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

# ─── 服务地址常量（支持环境变量覆盖，便于多实例并行）───────────────
AGENT_URL = os.environ.get("PYTEST_AGENT_URL", "http://localhost:8191")
MODEL_PROXY_URL = os.environ.get("PYTEST_MODEL_PROXY_URL", "http://localhost:8888")
MOCK_RENTAL_URL = os.environ.get("PYTEST_MOCK_RENTAL_URL", "http://localhost:8080")
SILICONFLOW_URL = "https://api.siliconflow.cn"
API_KEY_FILE = Path(__file__).parents[2] / ".api_key"

CONNECT_TIMEOUT = 3.0   # 服务可达性探测超时（秒）
LLM_TIMEOUT = 90.0      # LLM 调用超时（秒，Qwen3-32B 首次响应可能较慢）
AGENT_TIMEOUT = 120.0   # Agent 全链路超时（秒，含 init_houses + LLM 调用）


# ─── 服务可达性探测 ──────────────────────────────────────────────

def _is_reachable(url: str, path: str = "/docs") -> bool:
    """探测服务是否可达，用于 skipif 条件。"""
    try:
        with httpx.Client(timeout=CONNECT_TIMEOUT) as client:
            r = client.get(f"{url}{path}")
            return r.status_code < 500
    except Exception:
        return False


def _api_key_available() -> bool:
    """检查 .api_key 文件是否存在且非空。"""
    return API_KEY_FILE.exists() and bool(API_KEY_FILE.read_text(encoding="utf-8").strip())


# ─── pytest markers ──────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: 端到端集成测试（需要真实服务运行）")
    config.addinivalue_line("markers", "smoke: 冒烟测试（快速验证核心链路）")
    config.addinivalue_line("markers", "llm: 需要调用外部 LLM 服务")


# ─── 共享 fixtures ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def agent_available() -> bool:
    return _is_reachable(AGENT_URL)


@pytest.fixture(scope="session")
def model_proxy_available() -> bool:
    return _is_reachable(MODEL_PROXY_URL)


@pytest.fixture(scope="session")
def mock_rental_available() -> bool:
    return _is_reachable(MOCK_RENTAL_URL)


@pytest.fixture(scope="session")
def api_key_available() -> bool:
    return _api_key_available()


@pytest.fixture(scope="session")
def api_key() -> str | None:
    if not _api_key_available():
        return None
    return API_KEY_FILE.read_text(encoding="utf-8").splitlines()[0].strip()


@pytest.fixture(scope="session")
def http_client():
    """复用 httpx.Client，整个测试 session 共享。超时设为 AGENT_TIMEOUT（最慢的路径）。"""
    with httpx.Client(timeout=AGENT_TIMEOUT) as client:
        yield client


@pytest.fixture
def require_agent(agent_available):
    if not agent_available:
        pytest.skip(f"Agent({AGENT_URL}) 未运行，跳过测试。启动命令: USER_ID=xxx python -m uvicorn main:app --port <port>")


@pytest.fixture
def require_model_proxy(model_proxy_available):
    if not model_proxy_available:
        pytest.skip(f"Model Proxy({MODEL_PROXY_URL}) 未运行，跳过测试。启动命令: cd test-simulator && python main.py")


@pytest.fixture
def require_mock_rental(mock_rental_available):
    if not mock_rental_available:
        pytest.skip(f"Mock Rental({MOCK_RENTAL_URL}) 未运行，跳过测试。启动命令: cd test-simulator && python main.py")


@pytest.fixture
def require_api_key(api_key_available):
    if not api_key_available:
        pytest.skip(f"API Key 文件不存在或为空: {API_KEY_FILE}")


@pytest.fixture
def require_full_stack(agent_available, model_proxy_available, mock_rental_available, api_key_available):
    """要求全部服务 + API Key 就绪，否则 skip。"""
    missing = []
    if not agent_available:
        missing.append(f"Agent({AGENT_URL})")
    if not model_proxy_available:
        missing.append(f"Model Proxy({MODEL_PROXY_URL})")
    if not mock_rental_available:
        missing.append(f"Mock Rental({MOCK_RENTAL_URL})")
    if not api_key_available:
        missing.append(".api_key 文件")
    if missing:
        pytest.skip(f"以下依赖未就绪，跳过全链路测试: {', '.join(missing)}")
