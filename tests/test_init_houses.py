"""
Story 2.2: 新 Session 数据初始化钩子 — init_houses 测试

Task 1: init_houses(client) in tools.py (AC: 1)
Task 2: Import and call init_houses in main.py (AC: 1)
Task 3: Subsequent requests skip init (AC: 1)
"""
import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import tools as _tools_module
from tools import init_houses


# ─────────────────────────────────────────────────────────────
# Task 1: init_houses(client) 单元测试
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def mock_http_success():
    """成功路径的 mock client + response，消除重复设置"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp
    return mock_client, mock_resp


class TestInitHousesSuccess:
    """init_houses 成功路径"""

    @pytest.mark.anyio
    async def test_calls_post_api_houses_init(self, mock_http_success):
        """Task 1: 调用 client.post('/api/houses/init', headers=_get_headers())"""
        mock_client, _ = mock_http_success
        await init_houses(mock_client)
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args[0][0] == "/api/houses/init"

    @pytest.mark.anyio
    async def test_uses_get_headers(self, mock_http_success):
        """Task 1: 使用 _get_headers() 传递 X-User-ID"""
        mock_client, _ = mock_http_success
        await init_houses(mock_client)
        headers = mock_client.post.call_args.kwargs["headers"]
        assert "X-User-ID" in headers
        assert headers["X-User-ID"] == _tools_module.USER_ID

    @pytest.mark.anyio
    async def test_calls_raise_for_status(self, mock_http_success):
        """Task 1: 调用 resp.raise_for_status()"""
        mock_client, mock_resp = mock_http_success
        await init_houses(mock_client)
        mock_resp.raise_for_status.assert_called_once()

    @pytest.mark.anyio
    async def test_returns_response_json(self, mock_http_success):
        """Task 1: 成功时返回 resp.json()"""
        mock_client, mock_resp = mock_http_success
        expected = {"status": "ok", "houses_count": 42}
        mock_resp.json.return_value = expected
        result = await init_houses(mock_client)
        assert result == expected


class TestInitHousesFailure:
    """init_houses 异常路径 — 永不 raise，返回 error dict"""

    @pytest.mark.anyio
    async def test_network_error_returns_error_dict(self):
        """Task 1: 网络错误 → 返回 {'error': 'init_houses failed: ...'}, 不 raise"""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        result = await init_houses(mock_client)
        assert isinstance(result, dict)
        assert "error" in result
        assert "init_houses failed" in result["error"]

    @pytest.mark.anyio
    async def test_http_error_returns_error_dict(self):
        """Task 1: HTTP 500 → raise_for_status 抛异常 → 返回 error dict"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        result = await init_houses(mock_client)
        assert isinstance(result, dict)
        assert "error" in result
        assert "init_houses failed" in result["error"]

    @pytest.mark.anyio
    async def test_generic_exception_returns_error_dict(self):
        """Task 1: 任意异常 → 返回 error dict, 不 raise"""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = RuntimeError("unexpected")

        result = await init_houses(mock_client)
        assert isinstance(result, dict)
        assert "error" in result
        assert "unexpected" in result["error"]

    @pytest.mark.anyio
    async def test_never_raises_exception(self):
        """Task 1: 任何场景下 init_houses 都不 raise"""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = Exception("boom")

        result = await init_houses(mock_client)
        assert isinstance(result, dict)


class TestInitHousesNotATool:
    """Task 1: init_houses 不在 TOOLS / TOOL_DISPATCH 中"""

    def test_not_in_tools_list(self):
        """init_houses 不出现在 TOOLS 常量中"""
        for tool in _tools_module.TOOLS:
            func_name = tool.get("function", {}).get("name", "")
            assert func_name != "init_houses"

    def test_tool_dispatch_not_exists_or_excludes_init_houses(self):
        """TOOL_DISPATCH 若存在，不包含 init_houses"""
        dispatch = getattr(_tools_module, "TOOL_DISPATCH", None)
        if dispatch is not None:
            assert "init_houses" not in dispatch


# ─────────────────────────────────────────────────────────────
# Task 2: main.py 集成 — init_houses 被正确调用
# ─────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient
import main as _main_module
from main import app

VALID_REQUEST = {
    "model_ip": "10.0.0.1",
    "session_id": "init-test-session",
    "message": "hello",
}


class TestInitHousesCalledOnNewSession:
    """Task 2: 新 session 触发 init_houses"""

    def test_new_session_calls_init_houses(self):
        """Task 2: 新 session_id 首次请求时调用 init_houses"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"status": "ok"})) as mock_init:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                    mock_init.assert_called_once()

    def test_init_houses_called_with_httpx_client(self):
        """Task 2: init_houses 接收 app.state.client (httpx.AsyncClient)"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"status": "ok"})) as mock_init:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                    call_args = mock_init.call_args[0]
                    assert isinstance(call_args[0], httpx.AsyncClient)

    def test_init_houses_called_before_session_created(self):
        """Task 2: init_houses 在 sessions[id]=[] 之前调用"""
        call_order = []

        async def tracking_init(client):
            call_order.append("init_houses")
            return {"status": "ok"}

        original_setitem = dict.__setitem__

        class TrackingDict(dict):
            def __setitem__(self, key, value):
                if key == VALID_REQUEST["session_id"] and isinstance(value, list) and len(value) == 0:
                    call_order.append("session_created")
                original_setitem(self, key, value)

        tracking_sessions = TrackingDict()

        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=tracking_init):
                with patch.object(_main_module, "sessions", tracking_sessions):
                    with TestClient(app) as client:
                        client.post("/api/v1/chat", json=VALID_REQUEST)

        assert "init_houses" in call_order
        assert "session_created" in call_order
        assert call_order.index("init_houses") < call_order.index("session_created")


# ─────────────────────────────────────────────────────────────
# Task 3: 后续请求跳过 init
# ─────────────────────────────────────────────────────────────
class TestInitHousesFailureResilience:
    """init_houses 失败时 session 仍正常创建（优雅降级）"""

    def test_session_created_even_when_init_houses_fails(self):
        """M2: init_houses 返回 error dict → session 仍创建，请求正常返回"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"error": "init_houses failed: timeout"})):
                with TestClient(app) as client:
                    resp = client.post("/api/v1/chat", json=VALID_REQUEST)
                    assert resp.status_code == 200
                    assert VALID_REQUEST["session_id"] in _main_module.sessions

    def test_user_message_appended_after_failed_init(self):
        """M2: init_houses 失败后 user 消息仍追加到 history"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"error": "init_houses failed: 500"})):
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                    history = _main_module.sessions[VALID_REQUEST["session_id"]]
                    user_msgs = [m for m in history if m.get("role") == "user"]
                    assert len(user_msgs) == 1
                    assert user_msgs[0]["content"] == VALID_REQUEST["message"]


class TestSubsequentRequestsSkipInit:
    """Task 3: 同一 session 第二次请求不再触发 init_houses"""

    def test_second_message_does_not_call_init_houses(self):
        """Task 3: 同一 session_id 第二条消息 → init_houses 不被再次调用"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"status": "ok"})) as mock_init:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                    client.post("/api/v1/chat", json=VALID_REQUEST)
                    assert mock_init.call_count == 1

    def test_different_sessions_each_trigger_init_once(self):
        """Task 3: 两个不同 session_id → 各触发一次 init_houses"""
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"status": "ok"})) as mock_init:
                with TestClient(app) as client:
                    client.post("/api/v1/chat", json={
                        "model_ip": "10.0.0.1", "session_id": "sess-A", "message": "hi"
                    })
                    client.post("/api/v1/chat", json={
                        "model_ip": "10.0.0.1", "session_id": "sess-B", "message": "hi"
                    })
                    assert mock_init.call_count == 2

    def test_three_messages_same_session_init_called_once(self):
        """Task 3: 同一 session 发 3 条消息 → init_houses 仅调用 1 次"""
        sid = "multi-msg-session"
        with patch("main.run_agent", new=AsyncMock(return_value=None)):
            with patch("main.init_houses", new=AsyncMock(return_value={"status": "ok"})) as mock_init:
                with TestClient(app) as client:
                    for i in range(3):
                        client.post("/api/v1/chat", json={
                            "model_ip": "10.0.0.1", "session_id": sid, "message": f"msg{i}"
                        })
                    assert mock_init.call_count == 1
