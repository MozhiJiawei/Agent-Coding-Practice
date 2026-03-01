"""Mock 租房 API FastAPI 应用 — 提供 15 个租房 API 端点的 Mock/透传服务"""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import SimulatorConfig, MockRule

_INIT_SUCCESS = {
    "code": 0,
    "message": "success",
    "data": {
        "action": "reset_user",
        "message": "该用户状态覆盖已清空，房源恢复为初始状态",
    },
}


def match_mock(
    method: str,
    path: str,
    params: dict[str, str],
    registry: list[MockRule],
) -> dict | None:
    """匹配规则，优先级：path+method+params 全匹配 > path+method 匹配"""
    full_match = None
    partial_match = None

    for rule in registry:
        if rule.method.upper() != method.upper():
            continue
        if rule.path != path:
            continue
        if rule.params_match:
            if all(params.get(k) == v for k, v in rule.params_match.items()):
                full_match = rule.response
                break
        else:
            partial_match = rule.response

    return full_match if full_match is not None else partial_match


def create_mock_rental_app(
    config: SimulatorConfig,
    mock_registry: list[MockRule],
) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient(timeout=60.0)
        app.state.mock_registry = mock_registry
        yield
        await app.state.client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def catch_all(request: Request, path: str):
        full_path = f"/{path}"
        method = request.method
        params = dict(request.query_params)

        # 优先级 1：/api/houses/init 硬编码（无论 rental_mode）
        if full_path == "/api/houses/init" and method == "POST":
            return JSONResponse(content=_INIT_SUCCESS)

        # 优先级 2：Mock 模式
        if config.rental_mode == "mock":
            matched = match_mock(
                method, full_path, params, request.app.state.mock_registry
            )
            if matched is not None:
                return JSONResponse(content=matched)
            return JSONResponse(
                content={"code": 404, "message": f"Mock 未匹配: {method} {full_path}"}
            )

        # 优先级 3：透传模式
        target_url = config.rental_passthrough_url.rstrip("/") + full_path
        headers = {}
        x_user_id = request.headers.get("X-User-ID")
        if x_user_id:
            headers["X-User-ID"] = x_user_id
        content_type = request.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type

        try:
            body = await request.body()
            resp = await request.app.state.client.request(
                method=method,
                url=target_url,
                params=params,
                content=body,
                headers=headers,
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"code": 502, "message": f"透传失败: {e}"},
            )

    return app
