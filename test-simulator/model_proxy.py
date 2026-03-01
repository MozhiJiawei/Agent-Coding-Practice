"""Model Proxy FastAPI 应用 — 转发 LLM 请求并截取 token 统计"""
from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import SimulatorConfig, TokenCounter


def load_api_key(config: SimulatorConfig) -> str:
    """优先用 config.llm_api_key，否则读 api_key_file 第一行"""
    if config.llm_api_key:
        return config.llm_api_key
    key_path = Path(config.api_key_file)
    if not key_path.exists():
        raise FileNotFoundError(
            f"API key file not found: {key_path}. "
            "Set llm_api_key in config.yaml or create the .api_key file"
        )
    return key_path.read_text(encoding="utf-8").splitlines()[0].strip()


def create_model_proxy_app(config: SimulatorConfig, token_counter: TokenCounter) -> FastAPI:
    api_key = load_api_key(config)  # 启动时加载一次，闭包捕获，不每请求读文件

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient(timeout=120.0)
        app.state.token_counter = token_counter
        yield
        await app.state.client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.post("/v1/chat/completions")
    async def proxy_chat(request: Request):
        body = await request.json()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        session_id = request.headers.get("Session-ID")
        if session_id:
            headers["Session-ID"] = session_id

        try:
            resp = await request.app.state.client.post(
                config.llm_proxy_url,
                json=body,
                headers=headers,
            )
            try:
                data = resp.json()
            except Exception:
                return JSONResponse(
                    content={"error": f"LLM returned non-JSON response (HTTP {resp.status_code})"},
                    status_code=502,
                )
            if "usage" in data:
                request.app.state.token_counter.add(data["usage"])
            return JSONResponse(content=data, status_code=resp.status_code)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": f"LLM proxy unavailable: {e}"},
            )

    return app
