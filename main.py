import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import httpx
from pydantic import BaseModel
from agent import run_agent


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
        base_url="http://7.197.86.219:8080", timeout=30.0
    )
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    client = req.app.state.client  # noqa: F841 — Story 1.4 将传递给 run_agent
    return ChatResponse(
        session_id=request.session_id,
        response="Not implemented",
        status="error",
        tool_results=[],
        timestamp=int(time.time()),
        duration_ms=0,
    )
