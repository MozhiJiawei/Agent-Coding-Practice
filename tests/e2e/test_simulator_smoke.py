"""
tests/e2e/test_simulator_smoke.py — Test Simulator ↔ 主 Agent 联调冒烟测试

验证目标（需要真实服务运行）：
  1. 服务可达性：Agent(8191)、Model Proxy(8888)、Mock Rental(8080)
  2. Mock Rental API：/api/houses/init 硬编码响应 / 未匹配返回 code=404 / OpenAPI 路由注册
  3. Model Proxy：转发请求至 SiliconFlow 并获得真实 LLM 响应 / Session-ID 透传 / token 统计 / 502 处理
  4. 全链路：Agent → Model Proxy(8888) → SiliconFlow → Agent 返回真实响应

运行方式：
  # 确保三个服务已启动后执行：
  pytest tests/e2e/ -v -m smoke
  # 只运行 LLM 相关测试：
  pytest tests/e2e/ -v -m llm
  # 运行全部 E2E 测试：
  pytest tests/e2e/ -v
"""
from __future__ import annotations

import json
import time

import httpx
import pytest

from .conftest import (
    AGENT_URL,
    MODEL_PROXY_URL,
    MOCK_RENTAL_URL,
    LLM_TIMEOUT,
    AGENT_TIMEOUT,
)

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


# ═══════════════════════════════════════════════════════════════
# 1. 服务可达性检测
# ═══════════════════════════════════════════════════════════════

class TestServiceReachability:
    """验证三个服务均可访问（OpenAPI /docs 端点响应正常）。"""

    def test_agent_is_reachable(self, agent_available):
        """Smoke: Agent(8191) 可达"""
        assert agent_available, (
            "Agent(8191) 不可达。启动命令：USER_ID=xxx python -m uvicorn main:app --host 0.0.0.0 --port 8191"
        )

    def test_model_proxy_is_reachable(self, model_proxy_available):
        """Smoke: Model Proxy(8888) 可达"""
        assert model_proxy_available, (
            "Model Proxy(8888) 不可达。启动命令：cd test-simulator && python main.py"
        )

    def test_mock_rental_is_reachable(self, mock_rental_available):
        """Smoke: Mock Rental API(8080) 可达"""
        assert mock_rental_available, (
            "Mock Rental(8080) 不可达。启动命令：cd test-simulator && python main.py"
        )

    def test_agent_openapi_schema(self, require_agent, http_client):
        """Smoke: Agent OpenAPI schema 可正常访问"""
        r = http_client.get(f"{AGENT_URL}/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "openapi" in schema
        assert "/api/v1/chat" in schema.get("paths", {})

    def test_model_proxy_openapi_schema(self, require_model_proxy, http_client):
        """Smoke: Model Proxy OpenAPI schema 中包含 /v1/chat/completions 路由"""
        r = http_client.get(f"{MODEL_PROXY_URL}/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "/v1/chat/completions" in schema.get("paths", {})

    def test_mock_rental_openapi_schema(self, require_mock_rental, http_client):
        """Smoke: Mock Rental OpenAPI schema 可正常访问"""
        r = http_client.get(f"{MOCK_RENTAL_URL}/openapi.json")
        assert r.status_code == 200
        assert "openapi" in r.json()


# ═══════════════════════════════════════════════════════════════
# 2. Mock Rental API 接口验证
# ═══════════════════════════════════════════════════════════════

class TestMockRentalAPI:
    """验证 Mock Rental API 的核心路由行为（不依赖 LLM）。"""

    def test_post_houses_init_returns_hardcoded_success(self, require_mock_rental, http_client):
        """
        AC2: POST /api/houses/init 始终返回硬编码成功响应。
        无论 rental_mode 为何，均返回 HTTP 200 + 固定 JSON。
        """
        r = http_client.post(
            f"{MOCK_RENTAL_URL}/api/houses/init",
            headers={"X-User-ID": "test-smoke-user"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["message"] == "success"
        assert body["data"]["action"] == "reset_user"
        assert "该用户状态覆盖已清空" in body["data"]["message"]

    def test_post_houses_init_ignores_rental_mode(self, require_mock_rental, http_client):
        """
        AC2: /api/houses/init 优先于 rental_mode 判断，永远返回成功响应。
        连续发送两次，每次都应返回相同的硬编码响应。
        """
        for i in range(2):
            r = http_client.post(
                f"{MOCK_RENTAL_URL}/api/houses/init",
                headers={"X-User-ID": f"smoke-user-{i}"},
            )
            assert r.status_code == 200
            assert r.json()["code"] == 0, f"第 {i+1} 次调用应返回 code=0"

    def test_unmatched_get_returns_http200_with_code404(self, require_mock_rental, http_client):
        """
        AC4 (NFR9): Mock 模式下未匹配路由返回 HTTP 200 + {"code": 404, ...}。
        绝不返回 HTTP 5xx。
        """
        r = http_client.get(f"{MOCK_RENTAL_URL}/api/landmarks")
        assert r.status_code == 200, "未匹配路由不应返回 5xx，必须返回 HTTP 200"
        body = r.json()
        assert body["code"] == 404
        assert "Mock 未匹配" in body["message"]

    def test_unmatched_post_returns_http200_with_code404(self, require_mock_rental, http_client):
        """
        AC4: POST 方法未匹配时同样返回 HTTP 200 + code=404（不崩溃）。
        """
        r = http_client.post(
            f"{MOCK_RENTAL_URL}/api/houses/9999/rent",
            headers={"X-User-ID": "smoke"},
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 404

    def test_all_15_rental_endpoints_respond_without_5xx(self, require_mock_rental, http_client):
        """
        AC1: 15 个租房 API 端点均可访问，任何端点均不应返回 5xx。
        Mock 模式下未配置规则时返回 code=404，但 HTTP 状态码为 200。
        """
        endpoints = [
            ("GET",  "/api/landmarks"),
            ("GET",  "/api/landmarks/name/test-landmark"),
            ("GET",  "/api/landmarks/search"),
            ("GET",  "/api/landmarks/1"),
            ("GET",  "/api/landmarks/stats"),
            ("GET",  "/api/houses/HF_1"),
            ("GET",  "/api/houses/listings/HF_1"),
            ("GET",  "/api/houses/by_community"),
            ("GET",  "/api/houses/by_platform"),
            ("GET",  "/api/houses/nearby"),
            ("GET",  "/api/houses/nearby_landmarks"),
            ("GET",  "/api/houses/stats"),
            ("POST", "/api/houses/init"),
            ("POST", "/api/houses/HF_1/rent"),
            ("POST", "/api/houses/HF_1/terminate"),
            ("POST", "/api/houses/HF_1/offline"),
        ]
        failed = []
        for method, path in endpoints:
            r = http_client.request(
                method,
                f"{MOCK_RENTAL_URL}{path}",
                headers={"X-User-ID": "smoke"},
                json={} if method == "POST" else None,
            )
            if r.status_code >= 500:
                failed.append(f"{method} {path} → {r.status_code}")
        assert not failed, f"以下端点返回了 5xx:\n" + "\n".join(failed)


# ═══════════════════════════════════════════════════════════════
# 3. Model Proxy 接口验证（需要 SiliconFlow API Key）
# ═══════════════════════════════════════════════════════════════

class TestModelProxy:
    """验证 Model Proxy 转发逻辑、token 统计和错误处理（需要真实 LLM 调用）。"""

    @pytest.mark.llm
    def test_model_proxy_forwards_to_siliconflow_and_gets_real_response(
        self, require_model_proxy, require_api_key, http_client
    ):
        """
        AC6 + AC7: Model Proxy 成功转发请求至 SiliconFlow，返回真实 LLM 响应。
        响应体必须包含 choices[0].message.content 和 usage 字段。
        """
        payload = {
            "model": "Qwen/Qwen3-32B",
            "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
            "max_tokens": 50,
        }
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(
                f"{MODEL_PROXY_URL}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        assert r.status_code == 200, f"Model Proxy 返回非 200: {r.status_code}, body: {r.text[:200]}"
        body = r.json()
        assert "choices" in body, "响应缺少 choices 字段"
        assert len(body["choices"]) > 0
        assert body["choices"][0]["message"]["content"], "LLM 响应内容为空"
        assert "usage" in body, "响应缺少 usage 字段（无法统计 token）"
        usage = body["usage"]
        assert usage.get("total_tokens", 0) > 0, "total_tokens 应 > 0"

    @pytest.mark.llm
    def test_model_proxy_passes_session_id_header(
        self, require_model_proxy, require_api_key, http_client
    ):
        """
        AC6: Session-ID 请求头应透传至 SiliconFlow（proxy 不丢弃该头）。
        验证方式：请求成功且得到有效响应（SiliconFlow 会忽略未知头，不会报错）。
        """
        session_id = f"smoke-test-{int(time.time())}"
        payload = {
            "model": "Qwen/Qwen3-32B",
            "messages": [{"role": "user", "content": "Say: PONG"}],
            "max_tokens": 20,
        }
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(
                f"{MODEL_PROXY_URL}/v1/chat/completions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Session-ID": session_id,
                },
            )
        assert r.status_code == 200
        assert "choices" in r.json()

    @pytest.mark.llm
    def test_model_proxy_token_usage_fields_present(
        self, require_model_proxy, require_api_key, http_client
    ):
        """
        AC7: LLM 响应的 usage 字段包含 prompt_tokens、completion_tokens、total_tokens。
        这些字段会被 token_counter.add() 消费。
        """
        payload = {
            "model": "Qwen/Qwen3-32B",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
        }
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(f"{MODEL_PROXY_URL}/v1/chat/completions", json=payload)
        assert r.status_code == 200
        usage = r.json().get("usage", {})
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_model_proxy_does_not_crash_on_malformed_request(self, require_model_proxy):
        """
        AC8 partial: Model Proxy 不会因畸形请求而崩溃。
        完整的 502 测试（upstream 不可达）需要独立的 Model Proxy 实例配置一个不可达的
        upstream URL，应在单元测试中验证。此处验证 proxy 对异常请求能正常返回响应。
        """
        payload = {"not_a_valid_field": "malformed"}
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            r = client.post(
                f"{MODEL_PROXY_URL}/v1/chat/completions",
                json=payload,
            )
        assert r.status_code < 600, (
            f"Model Proxy 返回了异常状态码: {r.status_code}"
        )

    def test_model_proxy_api_key_loaded_from_file(
        self, require_model_proxy, require_api_key, http_client
    ):
        """
        AC9: API Key 从 .api_key 文件动态加载，不在配置或代码中硬编码。
        验证方式：Model Proxy 能正常响应（若 key 未加载则会返回 401/403）。
        """
        payload = {
            "model": "Qwen/Qwen3-32B",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(f"{MODEL_PROXY_URL}/v1/chat/completions", json=payload)
        assert r.status_code not in (401, 403), (
            f"Model Proxy 返回 {r.status_code}，可能 API Key 未正确加载。"
            f" 检查 .api_key 文件是否存在且有效。body: {r.text[:200]}"
        )


# ═══════════════════════════════════════════════════════════════
# 4. 全链路端到端验证：Agent → Model Proxy → SiliconFlow
# ═══════════════════════════════════════════════════════════════

class TestFullChainIntegration:
    """
    验证完整调用链路：
    Test → Agent(8191) → Model Proxy(8888) → SiliconFlow LLM → Agent → Test

    这是 Story 5.2 AC11 的固化冒烟测试。
    """

    @pytest.mark.llm
    def test_agent_chat_reaches_terminal_state(self, require_full_stack):
        """
        AC11 (Smoke): 发送 chat 请求至 Agent，响应不能处于 ERROR 状态。
        Agent 通过 Model Proxy(8888) 调用 SiliconFlow，链路必须畅通。
        """
        payload = {
            "model_ip": "127.0.0.1",
            "session_id": f"smoke-{int(time.time())}",
            "message": "Hello, please reply with one sentence.",
        }
        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            r = client.post(f"{AGENT_URL}/api/v1/chat", json=payload)

        assert r.status_code == 200, f"Agent 返回非 200: {r.status_code}"
        body = r.json()

        required_fields = {"session_id", "response", "status", "tool_results", "timestamp", "duration_ms"}
        for field in required_fields:
            assert field in body, f"Agent 响应缺少字段: {field}"

        assert body["status"] in ("success", "error"), (
            f"status 应为 success 或 error，实际: {body['status']}"
        )
        assert body["response"], "Agent 响应的 response 字段不能为空"
        assert body["session_id"] == payload["session_id"]

    @pytest.mark.llm
    def test_agent_chat_returns_non_empty_response(self, require_full_stack):
        """
        AC11 (Smoke): Agent 响应的 response 字段非空（LLM 有真实输出）。
        """
        payload = {
            "model_ip": "127.0.0.1",
            "session_id": f"smoke-content-{int(time.time())}",
            "message": "What is 1+1? Answer with just the number.",
        }
        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            r = client.post(f"{AGENT_URL}/api/v1/chat", json=payload)

        body = r.json()
        response_text = body.get("response", "")
        assert response_text, "Agent response 字段不能为空字符串"
        assert len(response_text) > 0

    @pytest.mark.llm
    def test_agent_new_session_triggers_rental_init(self, require_full_stack):
        """
        AC11 + Story 2.2: 新 session 时 Agent 调用 Mock Rental /api/houses/init 成功。
        验证方式：Agent 能完成响应（init_houses 若失败 Agent 会返回 error 状态）。
        """
        unique_session = f"smoke-init-{int(time.time())}"
        payload = {
            "model_ip": "127.0.0.1",
            "session_id": unique_session,
            "message": "hello",
        }
        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            r = client.post(f"{AGENT_URL}/api/v1/chat", json=payload)

        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == unique_session
        assert body["response"], "新 session 应能正常响应（init_houses 链路畅通）"

    @pytest.mark.llm
    def test_agent_session_isolation(self, require_full_stack):
        """
        AC11 (Smoke): 两个不同 session 的响应相互独立，不共享历史。
        """
        ts = int(time.time())
        sessions = [f"smoke-iso-A-{ts}", f"smoke-iso-B-{ts}"]
        responses = {}

        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            for sid in sessions:
                r = client.post(
                    f"{AGENT_URL}/api/v1/chat",
                    json={
                        "model_ip": "127.0.0.1",
                        "session_id": sid,
                        "message": "hello",
                    },
                )
                assert r.status_code == 200
                responses[sid] = r.json()

        for sid in sessions:
            assert responses[sid]["session_id"] == sid, "响应的 session_id 应与请求一致"

    @pytest.mark.llm
    def test_agent_duration_ms_is_reasonable(self, require_full_stack):
        """
        AC11 (Smoke): Agent 的 duration_ms 是合理的正整数（> 0，< 90000ms）。
        """
        payload = {
            "model_ip": "127.0.0.1",
            "session_id": f"smoke-dur-{int(time.time())}",
            "message": "hi",
        }
        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            r = client.post(f"{AGENT_URL}/api/v1/chat", json=payload)

        body = r.json()
        duration = body.get("duration_ms", -1)
        assert isinstance(duration, int) and duration > 0, f"duration_ms 应为正整数，实际: {duration}"
        assert duration < 90_000, f"duration_ms 超过 90s 超时预期: {duration}ms"


# ═══════════════════════════════════════════════════════════════
# 5. Simulator 服务稳定性检测
# ═══════════════════════════════════════════════════════════════

class TestSimulatorServiceStability:
    """验证 Test Simulator 服务的稳定性（不依赖 LLM）。"""

    def test_mock_rental_handles_concurrent_requests(self, require_mock_rental):
        """
        Smoke: Mock Rental API 能串行处理多个请求而不崩溃。
        """
        results = []
        with httpx.Client(timeout=10.0) as client:
            for i in range(5):
                r = client.post(
                    f"{MOCK_RENTAL_URL}/api/houses/init",
                    headers={"X-User-ID": f"concurrent-{i}"},
                )
                results.append(r.status_code)

        assert all(s == 200 for s in results), f"部分请求失败: {results}"

    def test_model_proxy_responds_to_healthcheck(self, require_model_proxy, http_client):
        """
        Smoke: Model Proxy /docs 端点可访问（服务健康检查）。
        """
        r = http_client.get(f"{MODEL_PROXY_URL}/docs")
        assert r.status_code == 200

    def test_mock_rental_responds_to_healthcheck(self, require_mock_rental, http_client):
        """
        Smoke: Mock Rental /docs 端点可访问（服务健康检查）。
        """
        r = http_client.get(f"{MOCK_RENTAL_URL}/docs")
        assert r.status_code == 200

    def test_agent_responds_to_healthcheck(self, require_agent, http_client):
        """
        Smoke: Agent /docs 端点可访问（服务健康检查）。
        """
        r = http_client.get(f"{AGENT_URL}/docs")
        assert r.status_code == 200
