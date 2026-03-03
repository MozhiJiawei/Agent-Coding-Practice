import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import httpx
from pydantic import BaseModel
from agent import run_agent, SYSTEM_PROMPT
from logger import log_event
from tools import (
    init_houses, get_all_houses_for_debug, get_all_landmarks_for_debug,
    UserPreferences, build_area_district_map, AREA_TO_DISTRICT,
    build_landmark_names, LANDMARK_NAMES,
)

# 支持环境变量覆盖，与 debug_init_houses.py 一致，便于 Mock 或不同网络环境
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")


# Pydantic 模型（PascalCase 命名，snake_case 字段）
class ToolResult(BaseModel):
    tool_name: str
    args: dict | None = None
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
# 全局 Session 统计（累计 token 数和时间片数）
session_stats: dict[str, dict] = {}
# 全局 Session 偏好存储（session_id → UserPreferences）
session_preferences: dict[str, UserPreferences] = {}
# 按首次出现顺序为 session 编号（1-based），用于 PROCESS_SESSION_INDEX 过滤
_session_next_index: int = 1
_session_to_index: dict[str, int] = {}


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


def _empty_chat_response(session_id: str, duration_ms: int) -> ChatResponse:
    """不处理的 session 返回空响应"""
    return ChatResponse(
        session_id=session_id,
        response="",
        status="success",
        tool_results=[],
        timestamp=int(time.time()),
        duration_ms=duration_ms,
    )


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    # 只处理第 X 个 session（按首次出现的顺序，1-based）。0 表示处理所有 session；非 0 时其余 session 返回空响应
    PROCESS_SESSION_INDEX = 0
    start_time = time.time()
    client = req.app.state.client
    try:
        # 按首次出现顺序为 session 编号（1-based）
        if request.session_id not in _session_to_index:
            global _session_next_index
            _session_to_index[request.session_id] = _session_next_index
            _session_next_index += 1
        session_index = _session_to_index[request.session_id]
        if PROCESS_SESSION_INDEX != 0 and session_index != PROCESS_SESSION_INDEX:
            duration_ms = int((time.time() - start_time) * 1000)
            return _empty_chat_response(request.session_id, duration_ms)

        if request.session_id not in sessions:
            log_event("SESSION_START", request.session_id, {})
            log_event("SESSION_INIT", request.session_id, {})
            await init_houses(client)
            all_houses = await get_all_houses_for_debug(client)
            # log_event("DEBUG_ALL_HOUSES", request.session_id, {"raw_response": all_houses})
            for platform, data in all_houses.items():
                total = data.get("total", 0)
                items = data.get("items", [])
                print(f"[{request.session_id}] {platform}: total={total}, items={len(items)}")
            all_landmarks = await get_all_landmarks_for_debug(client)
            # log_event("DEBUG_ALL_LANDMARKS", request.session_id, {"raw_response": all_landmarks})
            # 构建 area → district 映射表并更新模块级全局
            all_items: list[dict] = []
            for platform_data in all_houses.values():
                all_items.extend(platform_data.get("items", []))
            area_map = build_area_district_map(all_items)
            AREA_TO_DISTRICT.update(area_map)
            log_event("AREA_DISTRICT_MAP", request.session_id, {"map_size": len(area_map)})
            # 构建地标名称集合并更新模块级全局
            landmark_items = all_landmarks.get("items", [])
            LANDMARK_NAMES.update(build_landmark_names(landmark_items))
            log_event("LANDMARK_NAMES", request.session_id, {"count": len(LANDMARK_NAMES)})
            sessions[request.session_id] = []
            sessions[request.session_id].append({"role": "system", "content": SYSTEM_PROMPT})
            session_stats[request.session_id] = {"total_tokens": 0, "total_time_slices": 0}
            session_preferences[request.session_id] = UserPreferences()
        history = sessions[request.session_id]
        history.append({"role": "user", "content": request.message})
        log_event("USER_REQUEST", request.session_id, {
            "model_ip": request.model_ip,
            "message": request.message,
        })
        result = await run_agent(
            history,
            request.model_ip,
            client,
            session_id=request.session_id,
            session_prefs=session_preferences.get(request.session_id),
        )
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
        log_event("USER_RESPONSE", request.session_id, {
            "status": chat_response.status,
            "duration_ms": chat_response.duration_ms,
            "response": chat_response.response,
        })
        # 累计 session 统计并打印摘要
        stats = session_stats.setdefault(request.session_id, {"total_tokens": 0, "total_time_slices": 0})
        stats["total_tokens"] += result.get("total_tokens", 0)
        stats["total_time_slices"] += result.get("total_time_slices", 0)
        llm_call_time_ms = result.get("llm_call_time_ms", 0)
        program_time_ms = duration_ms - llm_call_time_ms
        print(
            f"[{request.session_id}] "
            f"session累计token: {stats['total_tokens']} | "
            f"折算时间片: {stats['total_time_slices']} | "
            f"本次程序运行时间(扣除模型调用): {program_time_ms}ms"
        )
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
