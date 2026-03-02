import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import httpx
from pydantic import BaseModel
from agent import run_agent, SYSTEM_PROMPT
from logger import log_event
from tools import init_houses, get_all_houses_for_debug

# 支持环境变量覆盖，与 debug_init_houses.py 一致，便于 Mock 或不同网络环境
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")


# Pydantic 模型（PascalCase 命名，snake_case 字段）
class ToolResult(BaseModel):
    tool_name: str
    result: str


class ChatRequest(BaseModel):
    model_ip: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    status: str
    tool_results: list[ToolResult]
    timestamp: int
    duration_ms: int


# 全局 Session 存储
sessions: dict[str, list] = {}


# lifespan 上下文（httpx.AsyncClient 全生命周期）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 创建并存储 http client（startup 时不调用任何外部 API）
    app.state.client = httpx.AsyncClient(
        base_url=RENTAL_API_BASE, timeout=30.0, trust_env=False  # 不走代理
    )
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    start_time = time.time()
    client = req.app.state.client
    try:
        if request.session_id not in sessions:
            log_event("SESSION_START", request.session_id, {})
            log_event("SESSION_INIT", request.session_id, {})
            await init_houses(client)
            all_houses = await get_all_houses_for_debug(client)
            log_event("DEBUG_ALL_HOUSES", request.session_id, {"raw_response": all_houses})
            sessions[request.session_id] = []
            sessions[request.session_id].append({"role": "system", "content": SYSTEM_PROMPT})
        history = sessions[request.session_id]
        history.append({"role": "user", "content": request.message})
        log_event("RAW_REQUEST", request.session_id, {
            "model_ip": request.model_ip,
            "message": request.message,
        })
        result = await run_agent(history, request.model_ip, client, session_id=request.session_id)
        if result is None:
            result = {"response": "Agent not implemented", "status": "error", "tool_results": []}
        duration_ms = int((time.time() - start_time) * 1000)
        chat_response = ChatResponse(
            session_id=request.session_id,
            response=result.get("response", ""),
            status=result.get("status", "success") if result.get("status") in ("success", "error") else "error",
            tool_results=result.get("tool_results", []),
            timestamp=int(time.time()),
            duration_ms=duration_ms,
        )
        log_event("RAW_RESPONSE", request.session_id, {
            "status": chat_response.status,
            "duration_ms": chat_response.duration_ms,
            "response": chat_response.response,
        })
        return chat_response
    except Exception as e:
        log_event("ERROR", request.session_id, {"error": str(e)}, exc=e)
        duration_ms = int((time.time() - start_time) * 1000)
        error_response = ChatResponse(
            session_id=request.session_id,
            response=str(e),
            status="error",
            tool_results=[],
            timestamp=int(time.time()),
            duration_ms=duration_ms,
        )
        log_event("RAW_RESPONSE", request.session_id, {
            "status": error_response.status,
            "duration_ms": error_response.duration_ms,
            "response": error_response.response,
        })
        return error_response
