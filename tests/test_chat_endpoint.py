"""
Story 1.4: POST /api/v1/chat 路由与全局异常捕获 - 单元测试
AC 1-4 全覆盖，TDD RED → GREEN 循环

Tasks covered:
  Task 1: duration_ms 真实壁钟计时 (AC1 NFR4)
  Task 2: 全局 try/except 包装 (AC2 NFR8)
  Task 3: run_agent 调用与 ChatResponse 构建 (AC1)
  Task 4: HTTP 200 始终返回 (AC1, AC2)
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from main import app

VALID_REQUEST = {
    "model_ip": "10.0.0.1",
    "session_id": "test-session-001",
    "message": "hello",
}


# ─────────────────────────────────────────────────────────────
# Task 1: duration_ms 壁钟计时 (AC1 NFR4)
# ─────────────────────────────────────────────────────────────
class TestDurationMs:
    def test_duration_ms_is_non_negative_integer(self):
        """AC1 NFR4: duration_ms 是非负整数"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data["duration_ms"], int)
                assert data["duration_ms"] >= 0

    def test_duration_ms_reflects_real_processing_time(self):
        """AC1 NFR4: duration_ms 反映真实处理时间，误差 ≤ 10ms"""
        async def slow_agent(*args, **kwargs):
            await asyncio.sleep(0.05)  # 50ms 延迟
            return {"response": "done", "status": "success", "tool_results": []}

        with patch("main.run_agent", new=slow_agent):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200
                data = resp.json()
                assert data["duration_ms"] >= 40, "duration_ms 低于预期下界（50ms sleep - 10ms 容差）"
                assert data["duration_ms"] <= 200, "duration_ms 远超预期上界，计时可能异常"

    def test_duration_ms_on_error_path_is_non_negative(self):
        """AC1 NFR4: 异常路径的 duration_ms 也是非负整数"""
        with patch("main.run_agent", new=AsyncMock(side_effect=Exception("err"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert isinstance(data["duration_ms"], int)
                assert data["duration_ms"] >= 0


# ─────────────────────────────────────────────────────────────
# Task 2: 全局 try/except (AC2 NFR8)
# ─────────────────────────────────────────────────────────────
class TestGlobalExceptionHandler:
    def test_exception_returns_http_200(self):
        """AC2 NFR8: run_agent 抛出异常时仍返回 HTTP 200，不返回 5xx"""
        with patch("main.run_agent", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200

    def test_exception_response_status_is_error(self):
        """AC2: 异常响应的 status 字段为 'error'，且 response 包含异常信息"""
        with patch("main.run_agent", new=AsyncMock(side_effect=ValueError("bad value"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["status"] == "error"
                assert "bad value" in data["response"]

    def test_exception_message_in_response_field(self):
        """AC2: 精确异常信息出现在 response 字段中"""
        with patch("main.run_agent", new=AsyncMock(side_effect=RuntimeError("specific error msg"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert "specific error msg" in data["response"]

    def test_exception_tool_results_is_empty_list(self):
        """AC2: 异常响应的 tool_results 为空列表"""
        with patch("main.run_agent", new=AsyncMock(side_effect=Exception("err"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["tool_results"] == []

    def test_log_event_called_on_exception(self):
        """AC2: 异常时以 ('ERROR', session_id, {'error': str(e)}) 调用 log_event"""
        with patch("main.run_agent", new=AsyncMock(side_effect=RuntimeError("test error"))):
            with patch("main.log_event") as mock_log:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                    mock_log.assert_called_once()
                    call_args = mock_log.call_args[0]
                    assert call_args[0] == "ERROR"
                    assert call_args[1] == VALID_REQUEST["session_id"]
                    assert call_args[2] == {"error": "test error"}

    def test_no_5xx_even_on_unexpected_exception(self):
        """AC2 NFR8: 任意类型异常（含 TypeError）均不返回 5xx"""
        with patch("main.run_agent", new=AsyncMock(side_effect=TypeError("type err"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200
                assert resp.json()["status"] == "error"


# ─────────────────────────────────────────────────────────────
# Task 3: run_agent 调用与 ChatResponse 构建 (AC1)
# ─────────────────────────────────────────────────────────────
class TestRunAgentWiring:
    def test_run_agent_called_once_per_request(self):
        """Task 3: 每个请求恰好调用 run_agent 一次"""
        mock_agent = AsyncMock(return_value={"response": "ok", "status": "success", "tool_results": []})
        with patch("main.run_agent", new=mock_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                mock_agent.assert_called_once()

    def test_run_agent_called_with_model_ip(self):
        """Task 3: run_agent 的第二个参数为 request.model_ip"""
        mock_agent = AsyncMock(return_value={"response": "ok", "status": "success", "tool_results": []})
        with patch("main.run_agent", new=mock_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                call_args = mock_agent.call_args[0]
                assert call_args[1] == VALID_REQUEST["model_ip"]

    def test_run_agent_called_with_history_list(self):
        """Task 3: run_agent 的第一个参数为 list（history）"""
        mock_agent = AsyncMock(return_value={"response": "ok", "status": "success", "tool_results": []})
        with patch("main.run_agent", new=mock_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                call_args = mock_agent.call_args[0]
                assert isinstance(call_args[0], list)

    def test_run_agent_called_with_httpx_client(self):
        """Task 3: run_agent 的第三个参数为 httpx.AsyncClient（来自 app.state）"""
        mock_agent = AsyncMock(return_value={"response": "ok", "status": "success", "tool_results": []})
        with patch("main.run_agent", new=mock_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                call_args = mock_agent.call_args[0]
                assert isinstance(call_args[2], httpx.AsyncClient)

    def test_none_result_returns_agent_not_implemented(self):
        """Task 3: run_agent 返回 None → response='Agent not implemented', status='error'"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["response"] == "Agent not implemented"
                assert data["status"] == "error"

    def test_none_result_tool_results_is_empty(self):
        """Task 3: run_agent 返回 None → tool_results=[]"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["tool_results"] == []

    def test_success_result_response_mapped(self):
        """Task 3: run_agent 成功返回 → ChatResponse.response 正确"""
        agent_result = {"response": "找到 3 套房源", "status": "success", "tool_results": []}
        with patch("main.run_agent", new=AsyncMock(return_value=agent_result)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["response"] == "找到 3 套房源"

    def test_success_result_status_mapped(self):
        """Task 3: run_agent 成功返回 → ChatResponse.status 正确"""
        agent_result = {"response": "ok", "status": "success", "tool_results": []}
        with patch("main.run_agent", new=AsyncMock(return_value=agent_result)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["status"] == "success"

    def test_success_result_tool_results_mapped(self):
        """Task 3: run_agent 成功返回 → tool_results 正确映射"""
        agent_result = {
            "response": "ok",
            "status": "success",
            "tool_results": [{"tool_name": "search_houses", "result": "3 results"}],
        }
        with patch("main.run_agent", new=AsyncMock(return_value=agent_result)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert len(data["tool_results"]) == 1
                assert data["tool_results"][0]["tool_name"] == "search_houses"

    def test_malformed_tool_results_caught_by_except(self):
        """run_agent 返回非法 tool_results → Pydantic ValidationError 被 try/except 捕获，仍返回 HTTP 200"""
        agent_result = {
            "response": "ok",
            "status": "success",
            "tool_results": [{"bad_key": "invalid"}],
        }
        with patch("main.run_agent", new=AsyncMock(return_value=agent_result)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "error"

    def test_invalid_status_normalized_to_error(self):
        """AC1: run_agent 返回非法 status（如 'pending'）→ 归一化为 'error'"""
        agent_result = {"response": "ok", "status": "pending", "tool_results": []}
        with patch("main.run_agent", new=AsyncMock(return_value=agent_result)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["status"] == "error"

    def test_empty_dict_result_returns_defaults(self):
        """run_agent 返回空 dict {} → .get() 默认值生效，仍返回有效 ChatResponse"""
        with patch("main.run_agent", new=AsyncMock(return_value={})):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200
                data = resp.json()
                assert data["response"] == ""
                assert data["status"] == "error"
                assert data["tool_results"] == []


# ─────────────────────────────────────────────────────────────
# Task 4: HTTP 200 始终返回 (AC1, AC2)
# ─────────────────────────────────────────────────────────────
class TestHttp200AlwaysReturned:
    def test_valid_request_returns_http_200(self):
        """AC1: 有效请求返回 HTTP 200"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200

    def test_exception_in_run_agent_still_http_200(self):
        """AC2 NFR8: run_agent 抛异常时仍返回 HTTP 200"""
        with patch("main.run_agent", new=AsyncMock(side_effect=Exception("unexpected"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                assert resp.status_code == 200

    def test_timestamp_is_unix_integer(self):
        """AC1: timestamp 是当前 Unix 时间整数"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                before = int(time.time())
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                after = int(time.time()) + 1
                data = resp.json()
                assert isinstance(data["timestamp"], int)
                assert before <= data["timestamp"] <= after

    def test_session_id_echoed_in_response(self):
        """AC1: 响应中的 session_id 与请求一致"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                data = resp.json()
                assert data["session_id"] == VALID_REQUEST["session_id"]
