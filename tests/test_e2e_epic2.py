"""
test_e2e_epic2.py — Epic 2 完成后原型系统可运行能力 E2E 测试

验证目标：
1. HTTP 端点可访问，返回 200
2. 响应体满足规范字段结构
3. Session 管理正确（新 session 注入 system message，多轮历史持久化）
4. Agent Loop 完整运行（含 LLM 调用 → 格式守卫 → 响应输出）
5. init_houses 仅在新 session 首次调用时触发一次
6. 错误路径返回合法响应（非 5xx）

注意：LLM 调用以 AsyncMock 替代，避免依赖真实模型服务。
所有其余代码路径（FastAPI 路由、session 管理、Agent Loop、Format Guard）均为真实运行。
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi.testclient import TestClient

import agent as _agent_module
import main as _main_module
from main import app


# 覆盖 conftest 中的 _mock_run_agent autouse fixture
# E2E 测试需要运行真实的 run_agent，仅 mock LLM 层（agent.AsyncOpenAI）
@pytest.fixture(autouse=True)
def _use_real_run_agent():
    """E2E 测试使用真实 run_agent，覆盖 conftest 的默认 mock。"""
    with patch("main.run_agent", side_effect=_agent_module.run_agent):
        yield


# ─────────────────────────────────────────────────────────────
# Helper: Mock LLM Response 工厂
# ─────────────────────────────────────────────────────────────

def make_llm_response(content: str, tool_calls=None, finish_reason: str = "stop"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


def make_tool_call_mock(name: str, args: dict, call_id: str = "call_e2e_001"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


# ─────────────────────────────────────────────────────────────
# E2E: 基本可运行能力
# ─────────────────────────────────────────────────────────────

class TestE2EBasicReachability:
    def test_chat_endpoint_returns_200(self):
        """E2E: POST /api/v1/chat 返回 HTTP 200"""
        mock_create = AsyncMock(return_value=make_llm_response("你好！我是智能租房助手。"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "e2e-001",
                    "message": "你好"
                })
        assert resp.status_code == 200

    def test_response_body_has_required_fields(self):
        """E2E: 响应体包含所有规范字段"""
        mock_create = AsyncMock(return_value=make_llm_response("你好！"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "e2e-002",
                    "message": "你好"
                })
        data = resp.json()
        required_fields = {"session_id", "response", "status", "tool_results", "timestamp", "duration_ms"}
        for field in required_fields:
            assert field in data, f"响应体缺少字段: {field}"

    def test_response_status_is_success_on_normal_chat(self):
        """E2E: 正常聊天时 status = 'success'"""
        mock_create = AsyncMock(return_value=make_llm_response("很高兴为您服务！"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "e2e-003",
                    "message": "介绍一下你自己"
                })
        assert resp.json()["status"] == "success"

    def test_response_session_id_echoed(self):
        """E2E: 响应中的 session_id 与请求一致"""
        mock_create = AsyncMock(return_value=make_llm_response("ok"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "my-unique-session-xyz",
                    "message": "hi"
                })
        assert resp.json()["session_id"] == "my-unique-session-xyz"

    def test_duration_ms_is_non_negative_integer(self):
        """E2E NFR4: duration_ms 是非负整数"""
        mock_create = AsyncMock(return_value=make_llm_response("ok"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "e2e-dur",
                    "message": "test"
                })
        data = resp.json()
        assert isinstance(data["duration_ms"], int)
        assert data["duration_ms"] >= 0

    def test_timestamp_is_positive_integer(self):
        """E2E: timestamp 是正整数（Unix 时间戳）"""
        mock_create = AsyncMock(return_value=make_llm_response("ok"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "e2e-ts",
                    "message": "test"
                })
        data = resp.json()
        assert isinstance(data["timestamp"], int)
        assert data["timestamp"] > 0


# ─────────────────────────────────────────────────────────────
# E2E: Session 管理
# ─────────────────────────────────────────────────────────────

class TestE2ESessionManagement:
    def test_new_session_triggers_init_houses(self):
        """E2E Story 2.2: 新 session 触发 init_houses 一次"""
        mock_create = AsyncMock(return_value=make_llm_response("你好！"))
        init_mock = AsyncMock(return_value={"status": "ok"})
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("main.init_houses", init_mock):
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json={
                        "model_ip": "10.0.0.1",
                        "session_id": "new-sess-001",
                        "message": "hello"
                    })
        init_mock.assert_called_once()

    def test_existing_session_does_not_trigger_init_houses(self):
        """E2E Story 2.2: 已存在的 session 不再触发 init_houses"""
        mock_create = AsyncMock(return_value=make_llm_response("ok"))
        init_mock = AsyncMock(return_value={"status": "ok"})
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("main.init_houses", init_mock):
                with TestClient(app) as client:
                    # 第一次请求（新 session）
                    client.post("/api/v1/chat", json={
                        "model_ip": "10.0.0.1",
                        "session_id": "sess-persist",
                        "message": "first"
                    })
                    # 第二次请求（已有 session）
                    client.post("/api/v1/chat", json={
                        "model_ip": "10.0.0.1",
                        "session_id": "sess-persist",
                        "message": "second"
                    })
        # init_houses 只应在第一次请求时调用一次
        assert init_mock.call_count == 1

    def test_new_session_has_system_message_in_history(self):
        """E2E Story 2.3 AC7: 新 session 的第一次请求历史包含 system message"""
        from agent import SYSTEM_PROMPT

        mock_create = AsyncMock(return_value=make_llm_response("ok"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "sys-msg-test",
                    "message": "hi"
                })

        # 验证 LLM 调用时 messages 包含 system message
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0] if call_kwargs.args else None
        if messages is None and call_kwargs.kwargs:
            messages = call_kwargs.kwargs.get("messages", [])

        system_messages = [m for m in messages if m.get("role") == "system"]
        assert len(system_messages) >= 1, "新 session 的 LLM 调用应包含 system message"
        assert system_messages[0]["content"] == SYSTEM_PROMPT

    def test_multi_turn_history_persists(self):
        """E2E Story 2.1: 多轮对话历史在同一 session 中持久化"""
        mock_create = AsyncMock(side_effect=[
            make_llm_response("我是租房助手"),
            make_llm_response("海淀区有很多房源"),
        ])
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "multi-turn",
                    "message": "你是谁？"
                })
                client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "multi-turn",
                    "message": "找海淀区房源"
                })

        # 第二次 LLM 调用时，messages 应包含第一轮的历史
        second_call_kwargs = mock_cls.return_value.chat.completions.create.call_args_list[1]
        messages = second_call_kwargs.kwargs.get("messages", [])
        # 应包含：system + user1 + assistant1 + user2
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) >= 2, "第二次请求应包含第一轮用户消息"

    def test_different_sessions_are_isolated(self):
        """E2E: 不同 session_id 的历史相互隔离"""
        calls_per_session = []

        async def capturing_create(**kwargs):
            calls_per_session.append(len(kwargs.get("messages", [])))
            return make_llm_response("ok")

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(side_effect=capturing_create)
            with TestClient(app) as client:
                # Session A: 第1次请求
                client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "session-A",
                    "message": "消息A1"
                })
                # Session B: 全新 session，history 不应包含 Session A 的消息
                client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "session-B",
                    "message": "消息B1"
                })

        # 两次调用的 messages 长度应相同（都是全新 session）
        assert calls_per_session[0] == calls_per_session[1], \
            "不同 session 应有相同的初始 history 长度（各自独立）"


# ─────────────────────────────────────────────────────────────
# E2E: Agent Loop 完整运行
# ─────────────────────────────────────────────────────────────

class TestE2EAgentLoopExecution:
    def test_pure_chat_response_is_plain_string(self):
        """E2E: 纯聊天响应是自然语言字符串（不是 JSON）"""
        mock_create = AsyncMock(return_value=make_llm_response("北京天气很好！"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "chat-test",
                    "message": "北京今天天气怎样？"
                })
        data = resp.json()
        assert data["status"] == "success"
        assert data["response"] == "北京天气很好！"

    def test_tool_call_loop_executes_and_returns_json(self):
        """E2E: 序列调用 update_preferences + search_by_preferences 后 Format Guard 返回合法 JSON"""
        call1 = make_tool_call_mock("update_preferences", {"location": ["海淀"]})
        call2 = make_tool_call_mock("search_by_preferences", {})
        responses = [
            make_llm_response("", tool_calls=[call1], finish_reason="tool_calls"),
            make_llm_response("", tool_calls=[call2], finish_reason="tool_calls"),
            make_llm_response("为您推荐：HF_1、HF_2、HF_3", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)
        mock_search = {"total_matched": 2, "total_raw": 2, "items": [{"house_id": "HF_1"}, {"house_id": "HF_2"}], "preferences_summary": {}}

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.update_preferences", AsyncMock(return_value={"preferences_summary": {}})):
                with patch("agent.search_by_preferences", AsyncMock(return_value=mock_search)):
                    with TestClient(app) as client:
                        resp = client.post("/api/v1/chat", json={
                            "model_ip": "10.0.0.1",
                            "session_id": "tool-test",
                            "message": "找海淀区两居室"
                        })

        data = resp.json()
        assert data["status"] == "success"
        parsed = json.loads(data["response"])
        assert "message" in parsed
        assert "houses" in parsed

    def test_tool_results_field_populated_after_tool_call(self):
        """E2E: 序列调用后 tool_results 包含 update_preferences 与 search_by_preferences 记录"""
        call1 = make_tool_call_mock("update_preferences", {"location": ["朝阳"]})
        call2 = make_tool_call_mock("search_by_preferences", {})
        responses = [
            make_llm_response("", tool_calls=[call1], finish_reason="tool_calls"),
            make_llm_response("", tool_calls=[call2], finish_reason="tool_calls"),
            make_llm_response("推荐 HF_5", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)
        mock_search = {"total_matched": 1, "items": [{"house_id": "HF_5"}], "preferences_summary": {}}

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.update_preferences", AsyncMock(return_value={"preferences_summary": {}})):
                with patch("agent.search_by_preferences", AsyncMock(return_value=mock_search)):
                    with TestClient(app) as client:
                        resp = client.post("/api/v1/chat", json={
                            "model_ip": "10.0.0.1",
                            "session_id": "tr-test",
                            "message": "朝阳区有房吗？"
                        })

        data = resp.json()
        assert len(data["tool_results"]) >= 2
        tool_names = [r["tool_name"] for r in data["tool_results"]]
        assert "update_preferences" in tool_names
        assert "search_by_preferences" in tool_names

    def test_max_iterations_returns_error_status(self):
        """E2E: 达到最大迭代次数时 status = 'error'"""
        tool_call = make_tool_call_mock("get_house_detail", {"house_id": "HF_1"})
        mock_create = AsyncMock(return_value=make_llm_response(
            "", tool_calls=[tool_call], finish_reason="tool_calls"
        ))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": AsyncMock(return_value={})}):
                with TestClient(app) as client:
                    resp = client.post("/api/v1/chat", json={
                        "model_ip": "10.0.0.1",
                        "session_id": "max-iter",
                        "message": "一直找房"
                    })

        data = resp.json()
        assert data["status"] == "error"
        assert resp.status_code == 200  # 即使是业务错误，HTTP 也返回 200


# ─────────────────────────────────────────────────────────────
# E2E: 错误处理
# ─────────────────────────────────────────────────────────────

class TestE2EErrorHandling:
    def test_llm_exception_returns_error_response_not_500(self):
        """E2E: LLM 调用抛出异常时，返回 error 响应而非 HTTP 500"""
        mock_create = AsyncMock(side_effect=Exception("LLM connection failed"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "err-test",
                    "message": "hello"
                })
        # 不应返回 500，应被全局异常捕获
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

    def test_missing_model_ip_returns_422(self):
        """E2E: 缺少必要字段时返回 422 Unprocessable Entity"""
        with TestClient(app) as client:
            resp = client.post("/api/v1/chat", json={
                "session_id": "missing-field",
                "message": "hello"
                # 缺少 model_ip
            })
        assert resp.status_code == 422

    def test_empty_message_is_accepted(self):
        """E2E: 空消息也能正常处理（不崩溃）"""
        mock_create = AsyncMock(return_value=make_llm_response("请问有什么可以帮您？"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat", json={
                    "model_ip": "10.0.0.1",
                    "session_id": "empty-msg",
                    "message": ""
                })
        assert resp.status_code == 200
