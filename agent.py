import json
import re
import time
from typing import Callable
import httpx
from openai import AsyncOpenAI
from tools import (
    TOOLS, search_houses, search_landmark, search_nearby_landmark,
    get_house_detail, get_nearby_amenities, execute_action
)

# 模块顶层常量
SYSTEM_PROMPT = """你是智能租房助手，帮助用户在北京寻找和租赁房源。

工具使用规则：
- 搜索房源（按区域/价格/户型/装修/朝向/地铁距离）→ 调用 search_houses
- 查看房源详情 → 调用 get_house_detail
- 搜索地标（地铁站/商圈/公司）→ 调用 search_landmark
- 查找地标附近房源 → 调用 search_nearby_landmark
- 查询周边生活配套 → 调用 get_nearby_amenities
- 租房/退租/下架操作 → 必须调用 execute_action（action: rent/terminate/offline）

意图分类：
- 涉及房源信息、租赁操作 → 必须调用工具，禁止猜测或编造数据
- 纯聊天或与房源无关的问题 → 直接自然语言回复，无需调工具

输出格式：
- 调用 search_houses 或 search_nearby_landmark 后，用自然语言描述推荐房源，系统自动处理 JSON 格式
- 禁止自行生成 JSON 格式输出
- 禁止编造房源 ID，系统会从工具结果中自动提取
- 每次最多推荐 5 套房源"""

MAX_ITERATIONS = 10
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}

TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    "search_landmark": search_landmark,
    "search_nearby_landmark": search_nearby_landmark,
    "get_house_detail": get_house_detail,
    "get_nearby_amenities": get_nearby_amenities,
    "execute_action": execute_action,
}


def log_event(event_type: str, session_id: str, details: dict):
    print(json.dumps({
        "timestamp": int(time.time()),
        "session_id": session_id,
        "event_type": event_type,
        "details": details,
    }, ensure_ascii=False))


async def run_agent(
    history: list,
    model_ip: str,
    client: httpx.AsyncClient,
    session_id: str = "",
) -> dict:
    llm_client = AsyncOpenAI(
        base_url=f"http://{model_ip}:8888/v1",
        api_key="placeholder",
    )

    tools_called: set[str] = set()
    tool_results_log: list[dict] = []
    iterations = 0

    while True:
        if iterations >= MAX_ITERATIONS:
            log_event("ERROR", session_id, {"error": "Tool call limit exceeded"})
            return {
                "response": "Tool call limit exceeded",
                "status": "error",
                "tool_results": tool_results_log,
            }

        create_kwargs: dict = {
            "model": "",
            "messages": history,
        }
        if TOOLS:
            create_kwargs["tools"] = TOOLS
            create_kwargs["tool_choice"] = "auto"

        response = await llm_client.chat.completions.create(**create_kwargs)
        if not response.choices:
            log_event("ERROR", session_id, {"error": "LLM returned empty choices"})
            return {
                "response": "LLM returned empty choices",
                "status": "error",
                "tool_results": tool_results_log,
            }
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason

        log_event("MODEL_RESPONSE", session_id, {
            "finish_reason": finish_reason,
            "content_preview": (message.content or "")[:100],
        })

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

                log_event("TOOL_CALL", session_id, {
                    "tool_name": tool_name,
                    "args": str(args)[:200],
                })

                fn = TOOL_DISPATCH.get(tool_name)
                result = await fn(client, **args) if fn else {"error": f"Unknown tool: {tool_name}"}

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
        return {"response": response_str, "status": "success", "tool_results": tool_results_log}
    else:
        return {"response": content, "status": "success", "tool_results": tool_results_log}
