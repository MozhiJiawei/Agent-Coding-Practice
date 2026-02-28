"""
POST /api/v1/chat 路由单元测试

Story 1.4: 路由骨架与全局异常捕获 (AC1-AC4)
Story 2.1: Session 内存存储与跨请求历史持久化 (AC1-AC2)
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

import main as _main_module
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
        """AC2 / Story4.2 Task3.4: 异常时调用 log_event('ERROR', ..., exc=e)"""
        err = RuntimeError("test error")
        with patch("main.run_agent", new=AsyncMock(side_effect=err)):
            with patch("main.log_event") as mock_log:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                # 找到 ERROR 事件调用（新 session 还会触发 SESSION_START / SESSION_INIT）
                error_calls = [c for c in mock_log.call_args_list if c[0][0] == "ERROR"]
                assert len(error_calls) == 1
                call_args = error_calls[0][0]
                call_kwargs = error_calls[0][1] if error_calls[0][1] else {}
                assert call_args[0] == "ERROR"
                assert call_args[1] == VALID_REQUEST["session_id"]
                assert call_args[2] == {"error": "test error"}
                # Story 4.2 Task 3.4: exc 参数必须传入实际异常对象
                assert "exc" in call_kwargs
                assert isinstance(call_kwargs["exc"], RuntimeError)

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


# ─────────────────────────────────────────────────────────────
# Story 2.1 — Session Storage & History Persistence
# ─────────────────────────────────────────────────────────────

# Task 1: sessions reference pattern (AC: 1)
class TestSessionStorageReference:
    def test_new_session_creates_entry_in_sessions_dict(self):
        """Task 1: 新 session_id → sessions dict 中创建对应 key"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                assert VALID_REQUEST["session_id"] in _main_module.sessions

    def test_sessions_value_is_list(self):
        """Task 1: sessions[session_id] 是 list 对象"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                assert isinstance(_main_module.sessions.get(VALID_REQUEST["session_id"]), list)

    def test_sessions_entry_persists_after_request(self):
        """Task 1: 请求结束后 sessions dict 仍保留该 session 的 list（非临时对象）"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                # sessions dict 里必须有该 key，且为 list
                stored = _main_module.sessions.get(VALID_REQUEST["session_id"])
                assert stored is not None
                assert isinstance(stored, list)

    def test_existing_session_reuses_same_list_object(self):
        """Task 1: 同一 session_id 两次请求使用同一 list 对象（直接引用，非 get() copy）"""
        sid = VALID_REQUEST["session_id"]
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                list_ref_first = _main_module.sessions[sid]
                client.post("/api/v1/chat", json=VALID_REQUEST)
                list_ref_second = _main_module.sessions[sid]
                assert list_ref_first is list_ref_second


# Task 2: Append user message to history before run_agent (AC: 1)
class TestUserMessageAppend:
    def test_run_agent_receives_history_with_user_message(self):
        """Task 2: run_agent 接收的 history 含用户消息 dict"""
        captured = {}

        async def capture_agent(history, model_ip, client, **kwargs):
            captured["history"] = list(history)
            return None

        with patch("main.run_agent", new=capture_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                assert any(
                    m.get("role") == "user" and m.get("content") == VALID_REQUEST["message"]
                    for m in captured.get("history", [])
                )

    def test_user_message_exact_openai_format(self):
        """Task 2: history 中的 user 消息严格符合 OpenAI dict 格式"""
        captured = {}

        async def capture_agent(history, model_ip, client, **kwargs):
            captured["history"] = list(history)
            return None

        req = {"model_ip": "10.0.0.1", "session_id": "fmt-test", "message": "测试消息"}
        with patch("main.run_agent", new=capture_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=req)
                user_msgs = [m for m in captured.get("history", []) if m.get("role") == "user"]
                assert len(user_msgs) == 1
                assert user_msgs[0] == {"role": "user", "content": "测试消息"}

    def test_user_message_appended_before_run_agent_call(self):
        """Task 2: run_agent 被调用时 history 中已有 user 消息（先 append 后调用）"""
        history_at_call_time = {}

        async def capture_agent(history, model_ip, client, **kwargs):
            history_at_call_time["snapshot"] = list(history)
            return None

        with patch("main.run_agent", new=capture_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json=VALID_REQUEST)
                snapshot = history_at_call_time.get("snapshot", [])
                roles = [m.get("role") for m in snapshot]
                assert "user" in roles, "run_agent 调用时 history 中应已包含 user 消息"


# Task 3: Session isolation (AC: 2 — NFR10)
class TestSessionIsolation:
    def test_two_sessions_are_different_list_objects(self):
        """Task 3: sessions['id_A'] is not sessions['id_B']"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "id_A", "message": "hello"})
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "id_B", "message": "world"})
                assert "id_A" in _main_module.sessions
                assert "id_B" in _main_module.sessions
                assert _main_module.sessions["id_A"] is not _main_module.sessions["id_B"]

    def test_writing_to_session_a_does_not_affect_session_b(self):
        """Task 3 NFR10: session A 的消息不会出现在 session B 中"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "id_A", "message": "msg_A"})
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "id_B", "message": "msg_B"})
                a_contents = [m.get("content") for m in _main_module.sessions["id_A"]]
                b_contents = [m.get("content") for m in _main_module.sessions["id_B"]]
                assert "msg_B" not in a_contents
                assert "msg_A" not in b_contents

    def test_each_session_has_only_its_own_user_message(self):
        """Task 3: 每个 session 仅包含自己的 user 消息，无数据串漏"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "sess_X", "message": "unique_X"})
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "sess_Y", "message": "unique_Y"})
                x_contents = [m.get("content") for m in _main_module.sessions.get("sess_X", [])]
                y_contents = [m.get("content") for m in _main_module.sessions.get("sess_Y", [])]
                assert "unique_X" in x_contents
                assert "unique_Y" in y_contents
                assert "unique_Y" not in x_contents
                assert "unique_X" not in y_contents


# Task 4: Multi-turn accumulation (AC: 1)
class TestMultiTurnAccumulation:
    def test_same_session_history_grows_across_three_requests(self):
        """Task 4: 同一 session_id 发 3 条消息 → history 依次累积 3 条 user 消息"""
        sid = "multi-turn-session"
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                for i in range(1, 4):
                    client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": f"msg{i}"})
                user_msgs = [m["content"] for m in _main_module.sessions[sid] if m.get("role") == "user"]
                assert user_msgs == ["msg1", "msg2", "msg3"]

    def test_second_request_history_contains_first_user_message(self):
        """Task 4: 第 2 次请求时 run_agent 的 history 包含第 1 次的 user 消息"""
        sid = "turn-test"
        histories = []

        async def capture_agent(history, model_ip, client, **kwargs):
            histories.append(list(history))
            return None

        with patch("main.run_agent", new=capture_agent):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": "turn1"})
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": "turn2"})

        assert len(histories) == 2
        turn2_contents = [m.get("content") for m in histories[1] if m.get("role") == "user"]
        assert "turn1" in turn2_contents
        assert "turn2" in turn2_contents

    def test_independent_sessions_accumulate_independently(self):
        """Task 4: 不同 session 各自独立累积，互不干扰"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "sessA", "message": "A1"})
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "sessA", "message": "A2"})
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": "sessB", "message": "B1"})
                a_msgs = [m["content"] for m in _main_module.sessions["sessA"] if m.get("role") == "user"]
                b_msgs = [m["content"] for m in _main_module.sessions["sessB"] if m.get("role") == "user"]
                assert a_msgs == ["A1", "A2"]
                assert b_msgs == ["B1"]


# ─────────────────────────────────────────────────────────────
# Story 2.1 — Edge case: exception path session persistence
# ─────────────────────────────────────────────────────────────
class TestExceptionPathSessionPersistence:
    def test_user_message_persists_in_session_after_run_agent_exception(self):
        """run_agent 抛异常后，user 消息仍保留在 sessions 中"""
        sid = "exception-session"
        req = {"model_ip": "10.0.0.1", "session_id": sid, "message": "before-crash"}
        with patch("main.run_agent", new=AsyncMock(side_effect=RuntimeError("crash"))):
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json=req)
                assert resp.status_code == 200
                assert sid in _main_module.sessions
                user_msgs = [m for m in _main_module.sessions[sid] if m.get("role") == "user"]
                assert len(user_msgs) == 1
                assert user_msgs[0] == {"role": "user", "content": "before-crash"}

    def test_session_continues_accumulating_after_error_recovery(self):
        """异常后同一 session 继续发消息，history 持续累积"""
        sid = "recovery-session"
        with TestClient(app) as client:
            with patch("main.run_agent", new=AsyncMock(side_effect=RuntimeError("fail"))):
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": "msg1"})
            with patch("main.run_agent", new=AsyncMock(return_value=None)):
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": "msg2"})
            user_msgs = [m["content"] for m in _main_module.sessions[sid] if m.get("role") == "user"]
            assert user_msgs == ["msg1", "msg2"]


# ─────────────────────────────────────────────────────────────
# Story 4.2 — SESSION_START / SESSION_INIT 日志事件
# ─────────────────────────────────────────────────────────────
class TestSessionLogging:
    def test_session_start_logged_for_new_session(self):
        """Story 4.2 Task3.2: 新 session 触发 SESSION_START log_event"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.log_event") as mock_log:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                logged_events = [c[0][0] for c in mock_log.call_args_list]
                assert "SESSION_START" in logged_events

    def test_session_start_not_logged_for_existing_session(self):
        """Story 4.2 Task3.2: 已存在的 session 不再触发 SESSION_START"""
        sid = "existing-session"
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with TestClient(app) as client:
                # 第一次请求建立 session
                client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": "first"})
                with patch("main.log_event") as mock_log:
                    # 第二次请求，session 已存在
                    client.post("/api/v1/chat", json={"model_ip": "10.0.0.1", "session_id": sid, "message": "second"})
                    logged_events = [c[0][0] for c in mock_log.call_args_list]
                    assert "SESSION_START" not in logged_events

    def test_session_init_logged_for_new_session(self):
        """Story 4.2 Task3.3: 新 session 触发 SESSION_INIT log_event"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.log_event") as mock_log:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                logged_events = [c[0][0] for c in mock_log.call_args_list]
                assert "SESSION_INIT" in logged_events

    def test_session_start_before_session_init(self):
        """Story 4.2 Task3.2/3.3: SESSION_START 先于 SESSION_INIT 记录"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.log_event") as mock_log:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                events_in_order = [c[0][0] for c in mock_log.call_args_list]
                start_idx = events_in_order.index("SESSION_START")
                init_idx = events_in_order.index("SESSION_INIT")
                assert start_idx < init_idx
