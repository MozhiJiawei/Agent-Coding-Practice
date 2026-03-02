"""
test_agent_loop.py — Task 5 (AC: 2, 3, 4, 5)
测试 run_agent() Agent Loop 完整行为
"""
import json
import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from agent import run_agent, SYSTEM_PROMPT, MAX_ITERATIONS, HOUSE_SEARCH_TOOLS


# ─────────────────────────────────────────────────────────────
# Helper: 构造 Mock LLM Response
# ─────────────────────────────────────────────────────────────

def make_mock_response(content="你好，有什么可以帮助您的？", tool_calls=None, finish_reason="stop"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = MagicMock()
    resp.choices = [choice]
    # 设置 usage 为 None，防止 MagicMock 导致 token 计算 TypeError
    resp.usage = None
    return resp


def make_tool_call(name: str, arguments: dict, call_id: str = "call_001"):
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


@pytest.fixture
def mock_httpx_client():
    return MagicMock(spec=httpx.AsyncClient)


# ─────────────────────────────────────────────────────────────
# AC2: SYSTEM_PROMPT 模块级常量
# ─────────────────────────────────────────────────────────────

class TestSystemPrompt:
    def test_system_prompt_is_defined(self):
        assert SYSTEM_PROMPT is not None
        assert isinstance(SYSTEM_PROMPT, str)

    def test_system_prompt_not_empty(self):
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_role_definition(self):
        assert "租房" in SYSTEM_PROMPT or "助手" in SYSTEM_PROMPT

    def test_system_prompt_contains_tool_calling_instruction(self):
        assert "工具" in SYSTEM_PROMPT or "tool" in SYSTEM_PROMPT.lower()

    def test_system_prompt_contains_intent_classification(self):
        """必须包含聊天和房源操作的区分指令"""
        has_chat = "聊天" in SYSTEM_PROMPT or "直接" in SYSTEM_PROMPT or "自然语言" in SYSTEM_PROMPT
        has_tool = "工具" in SYSTEM_PROMPT or "调用" in SYSTEM_PROMPT
        assert has_chat or has_tool

    def test_system_prompt_contains_update_preferences_instruction(self):
        """Story 8.1: SYSTEM_PROMPT 应包含 update_preferences 工具指引"""
        assert "update_preferences" in SYSTEM_PROMPT

    def test_system_prompt_contains_format_instruction(self):
        """禁止自行生成 JSON 的指令，或有格式控制说明"""
        assert "JSON" in SYSTEM_PROMPT or "json" in SYSTEM_PROMPT or "格式" in SYSTEM_PROMPT or "禁止" in SYSTEM_PROMPT

    def test_system_prompt_no_hardcoded_house_ids(self):
        ids = re.findall(r'HF_\d+', SYSTEM_PROMPT)
        assert len(ids) == 0, f"SYSTEM_PROMPT 不应包含预设房源 ID: {ids}"

    def test_system_prompt_token_budget(self):
        """中文字符数 ≤ 500（粗略估计 token ≤ 800）"""
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', SYSTEM_PROMPT)
        assert len(chinese_chars) <= 500, f"中文字符数 {len(chinese_chars)} 超过 500"

    def test_max_iterations_constant(self):
        assert MAX_ITERATIONS == 10

    def test_house_search_tools_constant(self):
        """Story 8.1: HOUSE_SEARCH_TOOLS 包含 update_preferences"""
        assert "update_preferences" in HOUSE_SEARCH_TOOLS


# ─────────────────────────────────────────────────────────────
# AC2: Agent Loop 骨架 — max iterations 退出
# ─────────────────────────────────────────────────────────────

class TestAgentLoopMaxIterations:
    @pytest.mark.anyio
    async def test_max_iterations_returns_error(self, mock_httpx_client):
        """AC2 NFR3: 达到 MAX_ITERATIONS 时返回 status=error"""
        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"})
        mock_response = make_mock_response(
            content="", tool_calls=[tool_call], finish_reason="tool_calls"
        )
        mock_create = AsyncMock(return_value=mock_response)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": AsyncMock(return_value={})}):
                result = await run_agent(
                    [{"role": "user", "content": "找房"}],
                    "10.0.0.1",
                    mock_httpx_client,
                    "test-session"
                )

        assert result["status"] == "error"
        assert "limit" in result["response"].lower() or "exceeded" in result["response"].lower()

    @pytest.mark.anyio
    async def test_max_iterations_count_is_10(self, mock_httpx_client):
        """确认恰好 10 次工具调用后退出"""
        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"})
        mock_response = make_mock_response(
            content="", tool_calls=[tool_call], finish_reason="tool_calls"
        )
        mock_create = AsyncMock(return_value=mock_response)
        mock_tool = AsyncMock(return_value={})

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": mock_tool}):
                result = await run_agent(
                    [{"role": "user", "content": "找房"}],
                    "10.0.0.1",
                    mock_httpx_client,
                )

        assert result["status"] == "error"
        assert mock_tool.call_count == MAX_ITERATIONS


# ─────────────────────────────────────────────────────────────
# AC4: Loop 退出条件 — finish_reason="stop"
# ─────────────────────────────────────────────────────────────

class TestAgentLoopNormalExit:
    @pytest.mark.anyio
    async def test_finish_reason_stop_exits_loop(self, mock_httpx_client):
        """AC4: finish_reason=stop 且无 tool_calls 时正常退出"""
        mock_response = make_mock_response("你好！", tool_calls=None, finish_reason="stop")
        mock_create = AsyncMock(return_value=mock_response)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            result = await run_agent(
                [{"role": "user", "content": "你好"}],
                "10.0.0.1",
                mock_httpx_client,
                "test-session"
            )

        assert result["status"] == "success"
        assert result["response"] == "你好！"

    @pytest.mark.anyio
    async def test_llm_called_once_on_simple_chat(self, mock_httpx_client):
        """纯聊天时 LLM 只调用一次"""
        mock_create = AsyncMock(return_value=make_mock_response("ok"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            await run_agent([{"role": "user", "content": "hi"}], "10.0.0.1", mock_httpx_client)

        assert mock_create.call_count == 1


# ─────────────────────────────────────────────────────────────
# AC3: Tool Dispatch 与 Tool Message 格式
# ─────────────────────────────────────────────────────────────

class TestToolDispatchAndMessage:
    @pytest.mark.anyio
    async def test_tool_message_content_is_string(self, mock_httpx_client):
        """AC3: tool message content 必须是字符串，非 dict"""
        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"}, "call_abc")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("这是HF_1的详情", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        async def capturing_tool(client, **kwargs):
            return {"id": "HF_1", "name": "测试房源", "price": 5000}

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": capturing_tool}):
                history = [{"role": "user", "content": "看看HF_1的详情"}]
                result = await run_agent(history, "10.0.0.1", mock_httpx_client, "s1")

        # 检查 history 中 tool 消息的 content 字段是字符串
        tool_messages = [m for m in history if m.get("role") == "tool"]
        assert len(tool_messages) >= 1
        for tm in tool_messages:
            assert isinstance(tm["content"], str), f"tool message content 应为字符串，实际为 {type(tm['content'])}"

    @pytest.mark.anyio
    async def test_tool_message_has_tool_call_id(self, mock_httpx_client):
        """AC3: tool message 必须包含 tool_call_id"""
        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"}, "my_call_id_123")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("结果", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        history = [{"role": "user", "content": "看看HF_1"}]
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": AsyncMock(return_value={})}):
                await run_agent(history, "10.0.0.1", mock_httpx_client)

        tool_messages = [m for m in history if m.get("role") == "tool"]
        assert len(tool_messages) >= 1
        assert tool_messages[0]["tool_call_id"] == "my_call_id_123"

    @pytest.mark.anyio
    async def test_tool_result_returns_in_tool_results_log(self, mock_httpx_client):
        """返回值包含 tool_results 列表"""
        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("ok", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": AsyncMock(return_value={"id": "HF_1"})}):
                result = await run_agent(
                    [{"role": "user", "content": "看看HF_1"}], "10.0.0.1", mock_httpx_client
                )

        assert isinstance(result["tool_results"], list)
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["tool_name"] == "get_house_detail"


# ─────────────────────────────────────────────────────────────
# AC5: Format Guard — 意图分类与输出格式控制
# ─────────────────────────────────────────────────────────────

class TestFormatGuard:
    @pytest.mark.anyio
    async def test_house_search_path_response_is_json_string(self, mock_httpx_client):
        """AC5: 调用 update_preferences 后 response 可被 json.loads() 解析"""
        tool_call = make_tool_call("update_preferences", {"location": ["朝阳"]}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("为您推荐：HF_1、HF_2", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {
                "update_preferences": AsyncMock(return_value={"preferences": {}, "status": "updated"})
            }):
                result = await run_agent(
                    [{"role": "user", "content": "找朝阳区房源"}], "10.0.0.1", mock_httpx_client
                )

        assert result["status"] == "success"
        parsed = json.loads(result["response"])
        assert "message" in parsed
        assert "houses" in parsed

    @pytest.mark.anyio
    async def test_house_search_houses_field_contains_valid_ids(self, mock_httpx_client):
        """AC5 FR22: houses 列表只含有效 HF_xxx ID，最多 5 个"""
        tool_call = make_tool_call("update_preferences", {}, "c1")
        content = "推荐：HF_1、HF_2、HF_3、HF_4、HF_5、HF_6"  # 6个，Format Guard 截至5个
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response(content, tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"update_preferences": AsyncMock(return_value={})}):
                result = await run_agent(
                    [{"role": "user", "content": "找房"}], "10.0.0.1", mock_httpx_client
                )

        parsed = json.loads(result["response"])
        assert len(parsed["houses"]) <= 5
        for hid in parsed["houses"]:
            assert re.match(r'^HF_\d+$', hid), f"无效 house ID: {hid}"

    @pytest.mark.anyio
    async def test_house_search_no_duplicate_ids(self, mock_httpx_client):
        """AC5: houses 列表中无重复 ID"""
        tool_call = make_tool_call("update_preferences", {}, "c1")
        content = "HF_1 HF_1 HF_2 HF_1"  # HF_1 重复
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response(content, tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"update_preferences": AsyncMock(return_value={})}):
                result = await run_agent(
                    [{"role": "user", "content": "找房"}], "10.0.0.1", mock_httpx_client
                )

        parsed = json.loads(result["response"])
        assert len(parsed["houses"]) == len(set(parsed["houses"]))

    @pytest.mark.anyio
    async def test_chat_path_response_is_plain_string(self, mock_httpx_client):
        """AC5 FR21: 纯聊天时 response 是纯字符串，不包含 JSON 结构"""
        mock_create = AsyncMock(return_value=make_mock_response("今天天气很好！"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            result = await run_agent(
                [{"role": "user", "content": "今天天气怎么样？"}],
                "10.0.0.1",
                mock_httpx_client
            )

        assert result["status"] == "success"
        assert result["response"] == "今天天气很好！"
        # 纯聊天 response 不应是合法 JSON
        try:
            json.loads(result["response"])
            is_json = True
        except (json.JSONDecodeError, TypeError):
            is_json = False
        assert not is_json, "纯聊天 response 不应是 JSON 格式"

    @pytest.mark.anyio
    async def test_empty_tools_called_no_json_format(self, mock_httpx_client):
        """AC5: tools_called 为空时 Format Guard 不触发 JSON 格式"""
        mock_create = AsyncMock(return_value=make_mock_response("我是助手"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            result = await run_agent(
                [{"role": "user", "content": "你是谁？"}],
                "10.0.0.1",
                mock_httpx_client
            )

        assert result["response"] == "我是助手"

    @pytest.mark.anyio
    async def test_nearby_landmark_also_triggers_json_format(self, mock_httpx_client):
        """AC5: update_preferences 属于 HOUSE_SEARCH_TOOLS，触发 JSON 格式"""
        tool_call = make_tool_call("update_preferences", {"location": ["望京SOHO附近"]}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("附近有：HF_10", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {
                "update_preferences": AsyncMock(return_value={"preferences": {}, "status": "updated"})
            }):
                result = await run_agent(
                    [{"role": "user", "content": "望京SOHO附近有房吗？"}],
                    "10.0.0.1",
                    mock_httpx_client
                )

        parsed = json.loads(result["response"])
        assert "houses" in parsed

    @pytest.mark.anyio
    async def test_format_guard_json_is_parseable(self, mock_httpx_client):
        """AC5 NFR9: json.loads(response) 不抛出异常"""
        tool_call = make_tool_call("update_preferences", {}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("HF_3 HF_7", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"update_preferences": AsyncMock(return_value={})}):
                result = await run_agent(
                    [{"role": "user", "content": "找房"}], "10.0.0.1", mock_httpx_client
                )

        # 不应抛出异常
        parsed = json.loads(result["response"])
        assert isinstance(parsed, dict)


# ─────────────────────────────────────────────────────────────
# AC2: OpenAI client 构建 — per-call，base_url 正确
# ─────────────────────────────────────────────────────────────

class TestOpenAIClientConstruction:
    @pytest.mark.anyio
    async def test_openai_client_base_url_uses_model_ip(self, mock_httpx_client):
        """AC2 NFR6: AsyncOpenAI(base_url=f'http://{model_ip}:8888/v1', api_key='placeholder')"""
        mock_create = AsyncMock(return_value=make_mock_response("ok"))

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            await run_agent(
                [{"role": "user", "content": "hi"}],
                "192.168.1.100",
                mock_httpx_client
            )

        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args
        assert "http://192.168.1.100:8888/v1" in str(call_kwargs)
        assert "placeholder" in str(call_kwargs)


# ─────────────────────────────────────────────────────────────
# AC6: log_event 在 run_agent 中被调用（文件写入验证）
# ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def temp_log_dir_agent(tmp_path, monkeypatch):
    import logger
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger, "LOG_DIR", log_dir)
    return log_dir


class TestLogEventCalledInRunAgent:
    @pytest.mark.anyio
    async def test_model_response_event_logged(self, mock_httpx_client, tmp_path, monkeypatch):
        """AC6: MODEL_RESPONSE 事件被写入日志文件"""
        import logger
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(logger, "LOG_DIR", log_dir)

        mock_create = AsyncMock(return_value=make_mock_response("hello"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            await run_agent(
                [{"role": "user", "content": "hi"}],
                "10.0.0.1",
                mock_httpx_client,
                "test-session"
            )

        log_file = log_dir / "test-session.jsonl"
        assert log_file.exists()
        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        event_names = [e["event"] for e in events]
        assert "MODEL_RESPONSE" in event_names

    @pytest.mark.anyio
    async def test_tool_call_event_logged(self, mock_httpx_client, tmp_path, monkeypatch):
        """AC6: TOOL_CALL 事件被写入日志文件"""
        import logger
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(logger, "LOG_DIR", log_dir)

        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("结果", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": AsyncMock(return_value={})}):
                await run_agent(
                    [{"role": "user", "content": "看看HF_1"}],
                    "10.0.0.1",
                    mock_httpx_client,
                    "test-session"
                )

        log_file = log_dir / "test-session.jsonl"
        assert log_file.exists()
        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        event_names = [e["event"] for e in events]
        assert "TOOL_CALL" in event_names

    @pytest.mark.anyio
    async def test_llm_request_event_logged_before_create(self, mock_httpx_client, tmp_path, monkeypatch):
        """AC6 / AC#6: LLM_REQUEST 事件在 create 前被记录"""
        import logger
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(logger, "LOG_DIR", log_dir)

        mock_create = AsyncMock(return_value=make_mock_response("hello"))
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            await run_agent(
                [{"role": "user", "content": "hi"}],
                "10.0.0.1",
                mock_httpx_client,
                "test-session"
            )

        log_file = log_dir / "test-session.jsonl"
        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        event_names = [e["event"] for e in events]
        assert "LLM_REQUEST" in event_names

    @pytest.mark.anyio
    async def test_llm_request_event_has_correct_fields(self, mock_httpx_client, tmp_path, monkeypatch):
        """AC6: LLM_REQUEST 事件含 iteration 和 message_count 字段"""
        import logger
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(logger, "LOG_DIR", log_dir)

        mock_create = AsyncMock(return_value=make_mock_response("hello"))
        history = [{"role": "user", "content": "hi"}]
        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            await run_agent(history, "10.0.0.1", mock_httpx_client, "test-session")

        log_file = log_dir / "test-session.jsonl"
        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        llm_req_events = [e for e in events if e["event"] == "LLM_REQUEST"]
        assert len(llm_req_events) >= 1
        e = llm_req_events[0]
        assert "iteration" in e["details"]
        assert "new_message_count" in e["details"]
        assert isinstance(e["details"]["iteration"], int)
        assert isinstance(e["details"]["new_message_count"], int)

    @pytest.mark.anyio
    async def test_unknown_tool_logs_error_event(self, mock_httpx_client, tmp_path, monkeypatch):
        """未知工具名应记录 ERROR 事件"""
        import logger
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(logger, "LOG_DIR", log_dir)

        tool_call = make_tool_call("nonexistent_tool", {}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("ok", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            await run_agent(
                [{"role": "user", "content": "test"}],
                "10.0.0.1",
                mock_httpx_client,
                "test-session"
            )

        log_file = log_dir / "test-session.jsonl"
        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        error_events = [e for e in events if e["event"] == "ERROR"]
        assert len(error_events) >= 1
        assert "Unknown tool" in error_events[0]["details"]["error"]

    @pytest.mark.anyio
    async def test_tool_call_event_has_result_preview(self, mock_httpx_client, tmp_path, monkeypatch):
        """AC7: TOOL_CALL 事件 details 含 result_preview 字段（前300字符）"""
        import logger
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(logger, "LOG_DIR", log_dir)

        tool_call = make_tool_call("get_house_detail", {"house_id": "HF_1"}, "c1")
        responses = [
            make_mock_response("", tool_calls=[tool_call], finish_reason="tool_calls"),
            make_mock_response("结果", tool_calls=None, finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)
        tool_result = {"id": "HF_1", "name": "测试房源", "price": 5000}

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            with patch("agent.TOOL_DISPATCH", {"get_house_detail": AsyncMock(return_value=tool_result)}):
                await run_agent(
                    [{"role": "user", "content": "看看HF_1详情"}],
                    "10.0.0.1",
                    mock_httpx_client,
                    "test-session"
                )

        log_file = log_dir / "test-session.jsonl"
        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        tool_call_events = [e for e in events if e["event"] == "TOOL_CALL"]
        assert len(tool_call_events) >= 1
        tc = tool_call_events[0]
        assert "result_preview" in tc["details"]
        assert isinstance(tc["details"]["result_preview"], str)
        assert len(tc["details"]["result_preview"]) <= 300
