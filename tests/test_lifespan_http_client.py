"""
Story 1.3: FastAPI lifespan 与 HTTP 客户端全生命周期管理 - 单元测试
AC 1-4 全覆盖，TDD RED → GREEN 循环

AC1: lifespan 启动时创建 httpx.AsyncClient(base_url=..., timeout=30.0) 并存入 app.state.client
AC2: chat_endpoint 通过 req.app.state.client 获取共享客户端
AC3: lifespan 退出时调用 await client.aclose()
AC4: 请求处理器内部不创建新的 httpx.AsyncClient
"""
import inspect

import httpx
import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────
# AC 1: lifespan 创建 httpx.AsyncClient 并存储到 app.state.client
# ─────────────────────────────────────────────────────────────
class TestLifespanClientCreation:
    def test_client_exists_in_app_state(self):
        """AC 1: 启动后 app.state 上存在 client 属性"""
        from main import app

        with TestClient(app):
            assert hasattr(app.state, "client"), "app.state 应包含 client 属性"

    def test_client_is_async_http_client(self):
        """AC 1: app.state.client 是 httpx.AsyncClient 实例"""
        from main import app

        with TestClient(app):
            assert isinstance(app.state.client, httpx.AsyncClient), (
                f"app.state.client 应为 httpx.AsyncClient，实际为 {type(app.state.client)}"
            )

    def test_client_base_url_is_correct(self):
        """AC 1: base_url 必须为 http://7.197.86.219:8080"""
        from main import app

        with TestClient(app):
            actual = str(app.state.client.base_url).rstrip("/")
            assert actual == "http://7.197.86.219:8080", (
                f"base_url 应为 'http://7.197.86.219:8080'，实际为 '{actual}'"
            )

    def test_client_timeout_is_30_seconds(self):
        """AC 1: timeout 应等于 httpx.Timeout(30.0)（即各子项均为 30 秒）"""
        from main import app

        with TestClient(app):
            assert app.state.client.timeout == httpx.Timeout(30.0), (
                f"timeout 应为 httpx.Timeout(30.0)，实际为 {app.state.client.timeout}"
            )

    def test_client_created_exactly_once(self):
        """AC 1: 多次请求后 client 对象仍是同一个实例（非每请求创建）"""
        from main import app

        with TestClient(app) as tc:
            client_id_before = id(app.state.client)
            tc.post(
                "/api/v1/chat",
                json={"model_ip": "1.1.1.1", "session_id": "s1", "message": "hi"},
            )
            tc.post(
                "/api/v1/chat",
                json={"model_ip": "1.1.1.1", "session_id": "s2", "message": "hello"},
            )
            client_id_after = id(app.state.client)
        assert client_id_before == client_id_after, "每次请求不应创建新的 httpx.AsyncClient"

    def test_no_external_api_calls_during_startup(self):
        """AC 1: lifespan startup 期间不发起任何外部 HTTP 请求"""
        from main import app

        call_count = {"count": 0}
        original_send = httpx.AsyncClient.send

        async def mock_send(self, *args, **kwargs):
            call_count["count"] += 1
            return await original_send(self, *args, **kwargs)

        import unittest.mock as mock

        with mock.patch.object(httpx.AsyncClient, "send", mock_send):
            with TestClient(app):
                assert call_count["count"] == 0, (
                    f"lifespan startup 不应发起外部请求，实际发起了 {call_count['count']} 次"
                )


# ─────────────────────────────────────────────────────────────
# AC 3: shutdown 时 client.aclose() 被正确调用
# ─────────────────────────────────────────────────────────────
class TestLifespanClientShutdown:
    def test_client_is_closed_after_context_exit(self):
        """AC 3: lifespan context 退出后 client.is_closed 为 True"""
        from main import app

        with TestClient(app):
            client_ref = app.state.client
        assert client_ref.is_closed, (
            "lifespan 退出后应调用 client.aclose()，使 is_closed=True"
        )

    def test_lifespan_source_contains_aclose(self):
        """AC 3: lifespan 函数源码包含 aclose() 调用"""
        import main

        source = inspect.getsource(main)
        assert "aclose()" in source, "lifespan 必须包含 await client.aclose() 调用"


# ─────────────────────────────────────────────────────────────
# AC 2: 路由函数通过 fastapi.Request 获取共享 client
# ─────────────────────────────────────────────────────────────
class TestRouteClientAccess:
    def test_main_imports_request_from_fastapi(self):
        """AC 2: main.py 必须从 fastapi 导入 Request"""
        import main

        source = inspect.getsource(main)
        assert "Request" in source, "main.py 应包含 Request 相关代码"
        assert "from fastapi import" in source, "main.py 应有 from fastapi import 语句"
        # 验证 Request 在同一个 fastapi 导入行
        fastapi_import_lines = [
            line for line in source.splitlines() if "from fastapi import" in line
        ]
        has_request_import = any("Request" in line for line in fastapi_import_lines)
        assert has_request_import, (
            "main.py 应包含 'from fastapi import ..., Request' 或类似语句"
        )

    def test_chat_endpoint_has_request_parameter(self):
        """AC 2: chat_endpoint 签名中包含 fastapi.Request 类型的参数"""
        from fastapi import Request
        from main import chat_endpoint

        sig = inspect.signature(chat_endpoint)
        params = sig.parameters
        request_params = [
            name for name, p in params.items() if p.annotation is Request
        ]
        assert len(request_params) >= 1, (
            f"chat_endpoint 应有 fastapi.Request 类型参数，实际参数: {list(params.keys())}"
        )

    def test_chat_endpoint_client_comes_from_app_state(self):
        """AC 2: chat_endpoint 源码通过 app.state.client 获取共享客户端"""
        from main import chat_endpoint

        source = inspect.getsource(chat_endpoint)
        assert "app.state.client" in source, (
            "chat_endpoint 应通过 req.app.state.client 访问共享客户端"
        )

    def test_shared_client_same_object_during_request(self):
        """AC 2: 请求处理期间 app.state.client 与 lifespan 创建的是同一对象"""
        from main import app

        with TestClient(app) as tc:
            shared_client = app.state.client
            resp = tc.post(
                "/api/v1/chat",
                json={"model_ip": "1.1.1.1", "session_id": "test-shared", "message": "hi"},
            )
            assert resp.status_code == 200
            assert app.state.client is shared_client, (
                "请求处理不应替换 app.state.client 对象"
            )


# ─────────────────────────────────────────────────────────────
# AC 4: 请求处理器内部不创建新的 httpx.AsyncClient
# ─────────────────────────────────────────────────────────────
class TestNoNewClientInHandler:
    def test_handler_source_does_not_instantiate_new_client(self):
        """AC 4: chat_endpoint 函数体内不包含 httpx.AsyncClient() 构造调用"""
        from main import chat_endpoint

        source = inspect.getsource(chat_endpoint)
        assert "httpx.AsyncClient(" not in source, (
            "chat_endpoint 内不应创建新的 httpx.AsyncClient，应使用 req.app.state.client"
        )

    def test_handler_does_not_use_async_with_client(self):
        """AC 4: chat_endpoint 不使用 async with httpx 模式（违反 NFR7 客户端复用）"""
        from main import chat_endpoint

        source = inspect.getsource(chat_endpoint)
        assert "async with httpx" not in source, (
            "chat_endpoint 不应使用 'async with httpx.AsyncClient()' 模式"
        )
