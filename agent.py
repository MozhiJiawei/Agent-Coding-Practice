import json
import math
import re
import time
from typing import Callable
import httpx
from openai import AsyncOpenAI
from tools import (
    TOOLS, search_houses, search_landmark, search_nearby_landmark,
    get_house_detail, get_nearby_amenities, execute_action,
    get_houses_by_community, get_house_listings,
)
from logger import log_event

# 模块顶层常量
SYSTEM_PROMPT = """你是智能租房助手，帮助用户在北京寻找和租赁房源。

工具使用规则：
- 搜索房源（按区域/价格/户型/装修/朝向/地铁距离）→ 调用 search_houses
- 查看房源详情 → 调用 get_house_detail
- 搜索地标（地铁站/商圈/公司）→ 调用 search_landmark
- 查找地标附近房源 → 调用 search_nearby_landmark
- 按小区名查可租房源（指代消解/查某小区详情）→ 调用 get_houses_by_community
- 查同一房源在多个平台的挂牌价对比 → 调用 get_house_listings
- 查询某小区周边商超/公园配套 → 调用 get_nearby_amenities（传小区名 community，不是房源ID）
- 租房/退租/下架操作 → 必须调用 execute_action（action: rent/terminate/offline）

意图分类：
- 涉及房源信息、租赁操作 → 必须调用工具，禁止猜测或编造数据
- 纯聊天或与房源无关的问题 → 直接自然语言回复，无需调工具

输出格式：
- 调用 search_houses、search_nearby_landmark 或 get_houses_by_community 后，用自然语言描述推荐房源，系统自动处理 JSON 格式
- 禁止自行生成 JSON 格式输出
- 禁止编造房源 ID，系统会从工具结果中自动提取
- 每次最多推荐 5 套房源"""

MAX_ITERATIONS = 10
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark", "get_houses_by_community"}

TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    "search_landmark": search_landmark,
    "search_nearby_landmark": search_nearby_landmark,
    "get_house_detail": get_house_detail,
    "get_nearby_amenities": get_nearby_amenities,
    "execute_action": execute_action,
    "get_houses_by_community": get_houses_by_community,
    "get_house_listings": get_house_listings,
}


async def run_agent(
    history: list,
    model_ip: str,
    client: httpx.AsyncClient,
    session_id: str = "",
) -> dict:
    # trust_env=False 不走代理，避免使用 HTTP_PROXY/HTTPS_PROXY 环境变量
    # 评测接口要求必须携带 Session-ID 请求头
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as llm_http_client:
        llm_client = AsyncOpenAI(
            base_url=f"http://{model_ip}:8888/v1",
            api_key="placeholder",
            http_client=llm_http_client,
            default_headers={"Session-ID": session_id},
        )

        tools_called: set[str] = set()
        tool_results_log: list[dict] = []
        iterations = 0
        total_tokens = 0
        total_time_slices = 0
        llm_call_time_ms = 0
        # 指向本轮新消息的起始位置：用户消息已被 main.py 追加，退一位
        prev_len = len(history) - 1

        while True:
            if iterations >= MAX_ITERATIONS:
                log_event("ERROR", session_id, {"error": "Tool call limit exceeded"})
                return {
                    "response": "Tool call limit exceeded",
                    "status": "error",
                    "tool_results": tool_results_log,
                    "total_tokens": total_tokens,
                    "total_time_slices": total_time_slices,
                    "llm_call_time_ms": llm_call_time_ms,
                }

            create_kwargs: dict = {
                "model": "",
                "messages": history,
            }
            if TOOLS:
                create_kwargs["tools"] = TOOLS
                create_kwargs["tool_choice"] = "auto"

            new_messages = history[prev_len:]
            # 记录完毕后立即更新，下次迭代捕获 assistant + 工具结果
            prev_len = len(history)
            log_event("LLM_REQUEST", session_id, {
                "iteration": iterations,
                "new_message_count": len(new_messages),
                "new_messages": new_messages,
            })
            _llm_start = time.time()
            response = await llm_client.chat.completions.create(**create_kwargs)
            llm_call_time_ms += int((time.time() - _llm_start) * 1000)
            if response.usage:
                call_tokens = response.usage.total_tokens
                total_tokens += call_tokens
                t = 1 + max(0, (call_tokens / 1000 - 1)) * 0.3
                total_time_slices += math.ceil(t)
            if not response.choices:
                log_event("ERROR", session_id, {"error": "LLM returned empty choices"})
                return {
                    "response": "LLM returned empty choices",
                    "status": "error",
                    "tool_results": tool_results_log,
                    "total_tokens": total_tokens,
                    "total_time_slices": total_time_slices,
                    "llm_call_time_ms": llm_call_time_ms,
                }
            choice = response.choices[0]
            message = choice.message
            finish_reason = choice.finish_reason

            # 追加 assistant message（手动构建，避免 SDK 内部字段）
            assistant_msg: dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ]
            history.append(assistant_msg)

            if finish_reason == "stop" and not message.tool_calls:
                break

            if message.tool_calls:
                for call in message.tool_calls:
                    tool_name = call.function.name
                    try:
                        args = json.loads(call.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    fn = TOOL_DISPATCH.get(tool_name)
                    if fn is None:
                        result = {"error": f"Unknown tool: {tool_name}"}
                        log_event("ERROR", session_id, {"error": f"Unknown tool: {tool_name}", "tool_name": tool_name})
                    else:
                        result = await fn(client, **args)

                    log_event("TOOL_CALL", session_id, {
                        "tool_name": tool_name,
                        "args": str(args)[:200],
                        "result_preview": json.dumps(result, ensure_ascii=False)[:300],
                    })
                    log_event("TOOL_RESPONSE", session_id, {
                        "tool_name": tool_name,
                        "args": args,
                        "raw_result": result,
                    })

                    tools_called.add(tool_name)
                    tool_results_log.append({
                        "tool_name": tool_name,
                        "result": json.dumps(result, ensure_ascii=False)[:500],
                    })

                    history.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                iterations += 1
            else:
                # finish_reason != "stop" 且无 tool_calls（异常情况）— 安全退出
                break

        content = message.content or ""

        _stats = {
            "total_tokens": total_tokens,
            "total_time_slices": total_time_slices,
            "llm_call_time_ms": llm_call_time_ms,
        }
        if tools_called & HOUSE_SEARCH_TOOLS:
            raw_ids = re.findall(r'HF_\d+', content)
            seen: set[str] = set()
            houses: list[str] = []
            for hid in raw_ids:
                if hid not in seen and len(houses) < 5:
                    seen.add(hid)
                    houses.append(hid)
            response_str = json.dumps(
                {"message": content, "houses": houses},
                ensure_ascii=False,
            )
            return {"response": response_str, "status": "success", "tool_results": tool_results_log, **_stats}
        else:
            return {"response": content, "status": "success", "tool_results": tool_results_log, **_stats}
