"""
Story 1.2: Pydantic 请求与响应数据模型 - 单元测试
AC 1-5 全覆盖，TDD RED → GREEN 循环
"""
import pytest
from pydantic import ValidationError

from main import ChatRequest, ChatResponse, ToolResult


# ─────────────────────────────────────────────────────────────
# AC 3: ToolResult
# ─────────────────────────────────────────────────────────────
class TestToolResult:
    def test_fields_exist_and_assignable(self):
        """AC 3: ToolResult 至少含 tool_name: str 和 result: str"""
        tr = ToolResult(tool_name="search_houses", result="found 5 listings")
        assert tr.tool_name == "search_houses"
        assert tr.result == "found 5 listings"

    def test_tool_name_type_is_str(self):
        tr = ToolResult(tool_name="test_tool", result="ok")
        assert isinstance(tr.tool_name, str)

    def test_result_type_is_str(self):
        tr = ToolResult(tool_name="test_tool", result="ok")
        assert isinstance(tr.result, str)

    def test_tool_name_is_required(self):
        with pytest.raises(ValidationError):
            ToolResult(result="ok")

    def test_result_is_required(self):
        with pytest.raises(ValidationError):
            ToolResult(tool_name="test_tool")

    def test_class_name_is_pascal_case(self):
        """AC 4: 类名使用 PascalCase"""
        assert ToolResult.__name__ == "ToolResult"

    def test_field_names_are_snake_case(self):
        """AC 4: 字段名使用 snake_case"""
        fields = list(ToolResult.model_fields.keys())
        assert "tool_name" in fields
        assert "result" in fields


# ─────────────────────────────────────────────────────────────
# AC 1: ChatRequest
# ─────────────────────────────────────────────────────────────
class TestChatRequest:
    def test_fields_exist_and_assignable(self):
        """AC 1: ChatRequest 精确包含 model_ip, session_id, message"""
        req = ChatRequest(
            model_ip="192.168.1.100",
            session_id="sess-001",
            message="请搜索北京的房源",
        )
        assert req.model_ip == "192.168.1.100"
        assert req.session_id == "sess-001"
        assert req.message == "请搜索北京的房源"

    def test_model_ip_type_is_str(self):
        req = ChatRequest(model_ip="10.0.0.1", session_id="s1", message="hi")
        assert isinstance(req.model_ip, str)

    def test_session_id_type_is_str(self):
        req = ChatRequest(model_ip="10.0.0.1", session_id="s1", message="hi")
        assert isinstance(req.session_id, str)

    def test_message_type_is_str(self):
        req = ChatRequest(model_ip="10.0.0.1", session_id="s1", message="hi")
        assert isinstance(req.message, str)

    def test_model_ip_is_required(self):
        with pytest.raises(ValidationError):
            ChatRequest(session_id="s1", message="hi")

    def test_session_id_is_required(self):
        with pytest.raises(ValidationError):
            ChatRequest(model_ip="10.0.0.1", message="hi")

    def test_message_is_required(self):
        with pytest.raises(ValidationError):
            ChatRequest(model_ip="10.0.0.1", session_id="s1")

    def test_model_ip_has_no_default_value(self):
        """竞赛合规：model_ip 不得有默认值（不允许硬编码 IP）"""
        field = ChatRequest.model_fields["model_ip"]
        assert field.is_required()

    def test_class_name_is_pascal_case(self):
        """AC 4: 类名使用 PascalCase"""
        assert ChatRequest.__name__ == "ChatRequest"

    def test_exactly_three_fields(self):
        """AC 1: ChatRequest 精确包含 3 个字段，不多不少"""
        assert len(ChatRequest.model_fields) == 3

    def test_field_names_are_snake_case(self):
        """AC 4: 字段名使用 snake_case"""
        fields = list(ChatRequest.model_fields.keys())
        assert "model_ip" in fields
        assert "session_id" in fields
        assert "message" in fields


# ─────────────────────────────────────────────────────────────
# AC 2: ChatResponse
# ─────────────────────────────────────────────────────────────
class TestChatResponse:
    def _make_response(self, **kwargs):
        defaults = dict(
            session_id="sess-001",
            response="hello",
            status="success",
            tool_results=[],
            timestamp=1700000000,
            duration_ms=150,
        )
        defaults.update(kwargs)
        return ChatResponse(**defaults)

    def test_fields_exist_and_assignable(self):
        """AC 2: ChatResponse 精确包含6个字段"""
        resp = self._make_response()
        assert resp.session_id == "sess-001"
        assert resp.response == "hello"
        assert resp.status == "success"
        assert resp.tool_results == []
        assert resp.timestamp == 1700000000
        assert resp.duration_ms == 150

    def test_session_id_type_is_str(self):
        assert isinstance(self._make_response().session_id, str)

    def test_response_type_is_str(self):
        assert isinstance(self._make_response().response, str)

    def test_status_type_is_str(self):
        assert isinstance(self._make_response().status, str)

    def test_timestamp_type_is_int(self):
        assert isinstance(self._make_response().timestamp, int)

    def test_duration_ms_type_is_int(self):
        assert isinstance(self._make_response().duration_ms, int)

    def test_tool_results_accepts_empty_list(self):
        """竞赛合规：错误响应时 tool_results 允许为空列表"""
        resp = self._make_response(status="error", tool_results=[])
        assert resp.tool_results == []

    def test_tool_results_accepts_tool_result_instances(self):
        tr = ToolResult(tool_name="search_houses", result="5 results")
        resp = self._make_response(tool_results=[tr])
        assert len(resp.tool_results) == 1
        assert resp.tool_results[0].tool_name == "search_houses"

    def test_status_success_value(self):
        assert self._make_response(status="success").status == "success"

    def test_status_error_value(self):
        assert self._make_response(status="error").status == "error"

    def test_tool_results_rejects_invalid_dict(self):
        """list[ToolResult] 应拒绝不符合 ToolResult 结构的 dict"""
        with pytest.raises(ValidationError):
            ChatResponse(
                session_id="s",
                response="ok",
                status="success",
                tool_results=[{"invalid_key": "value"}],
                timestamp=1,
                duration_ms=0,
            )

    def test_class_name_is_pascal_case(self):
        """AC 4: 类名使用 PascalCase"""
        assert ChatResponse.__name__ == "ChatResponse"

    def test_exactly_six_fields(self):
        """AC 2: ChatResponse 精确包含 6 个字段，不多不少"""
        assert len(ChatResponse.model_fields) == 6

    def test_field_names_are_snake_case(self):
        """AC 4: 字段名使用 snake_case"""
        fields = list(ChatResponse.model_fields.keys())
        assert "session_id" in fields
        assert "response" in fields
        assert "status" in fields
        assert "tool_results" in fields
        assert "timestamp" in fields
        assert "duration_ms" in fields


# ─────────────────────────────────────────────────────────────
# AC 5: FastAPI 序列化验证
# ─────────────────────────────────────────────────────────────
class TestFastAPIIntegration:
    def test_all_models_importable(self):
        """AC 5: 三个模型均可无报错导入"""
        from main import ChatRequest, ChatResponse, ToolResult
        assert ChatRequest is not None
        assert ChatResponse is not None
        assert ToolResult is not None

    def test_chat_route_has_response_model(self):
        """AC 5: /api/v1/chat 路由已设置 response_model=ChatResponse"""
        from main import app
        routes = {route.path: route for route in app.routes}
        chat_route = routes.get("/api/v1/chat")
        assert chat_route is not None, "路由 /api/v1/chat 不存在"
        assert chat_route.response_model is ChatResponse, (
            f"response_model 应为 ChatResponse，实际为 {chat_route.response_model}"
        )

    def test_chat_response_json_serializable(self):
        """AC 5: ChatResponse 可正确序列化为 JSON 字典"""
        tr = ToolResult(tool_name="search_houses", result="found 3")
        resp = ChatResponse(
            session_id="test-session",
            response="已为您搜索到3套房源",
            status="success",
            tool_results=[tr],
            timestamp=1700000000,
            duration_ms=250,
        )
        data = resp.model_dump()
        assert data["session_id"] == "test-session"
        assert data["status"] == "success"
        assert data["timestamp"] == 1700000000
        assert data["duration_ms"] == 250
        assert data["tool_results"][0]["tool_name"] == "search_houses"
        assert data["tool_results"][0]["result"] == "found 3"

    def test_chat_endpoint_returns_valid_json_via_http(self):
        """AC 5: 通过 HTTP 请求验证 FastAPI 端到端 JSON 序列化"""
        from fastapi.testclient import TestClient
        from main import app

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/chat",
                json={
                    "model_ip": "10.0.0.1",
                    "session_id": "http-test",
                    "message": "hello",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "session_id" in data
            assert "response" in data
            assert "status" in data
            assert "tool_results" in data
            assert "timestamp" in data
            assert "duration_ms" in data
            assert isinstance(data["tool_results"], list)
            assert isinstance(data["timestamp"], int)
            assert isinstance(data["duration_ms"], int)

    def test_chat_response_nested_tool_results_serialize(self):
        """tool_results 嵌套序列化：list[ToolResult] 正确展开为 list[dict]"""
        trs = [
            ToolResult(tool_name="search_houses", result="r1"),
            ToolResult(tool_name="get_detail", result="r2"),
        ]
        resp = ChatResponse(
            session_id="s",
            response="ok",
            status="success",
            tool_results=trs,
            timestamp=1,
            duration_ms=0,
        )
        data = resp.model_dump()
        assert len(data["tool_results"]) == 2
        assert data["tool_results"][1]["tool_name"] == "get_detail"
