import json
import math
import os
import time
from functools import partial
from typing import Callable
import httpx
from openai import AsyncOpenAI
from tools import (
    TOOLS, get_house_detail, execute_action, get_house_listings,
    update_preferences, search_by_preferences, UserPreferences,
)
from logger import log_event

# 从 TOOLS schema 构建「工具名 -> 允许的参数名集合」，调用时只传 schema 内参数，避免 LLM 误传导致 TypeError
TOOL_SCHEMA_PARAMS: dict[str, set[str]] = {}
for _t in TOOLS:
    if _t.get("type") == "function" and "function" in _t:
        _name = _t["function"].get("name")
        _params = _t["function"].get("parameters") or {}
        _props = _params.get("properties") or {}
        if _name:
            TOOL_SCHEMA_PARAMS[_name] = set(_props.keys())

# 模块顶层常量（意图接口 v2：软约束由各字段 xxx_is_soft 布尔标识，与直接字段配合使用）
SYSTEM_PROMPT = """你是智能租房助手，帮助用户在北京寻找和租赁房源。当前年份为 2026。

核心工作流：
1. 用户表达租房需求时 → 先调用 update_preferences 提取/更新偏好，再调用 search_by_preferences 获取匹配房源
2. 用户想看某套房源详情 → 调用 get_house_detail
3. 用户想跨平台比价 → 调用 get_house_listings
4. 用户确认要租房/退租/下架 → 调用 execute_action

工具调用边界：
- 用户明确表达「找房」「帮我找」「推荐」「想换房」等意图时，调用 update_preferences 再 search_by_preferences
- 用户抱怨当前住房且可推断出明确偏好时，也可仅调用 update_preferences 更新该偏好（如：太吵/睡眠差→noise_preference=安静；采光不好→orientation="朝南", orientation_is_soft=true；通勤太长→sort_by=subway、sort_order=asc 或 max_subway_dist=800；房间小→sort_by=area、sort_order=desc），不必等用户明确说「找房」
- 纯聊天或与房源无关的问题 → 直接自然语言回复，禁止调工具

硬约束 vs 软约束（v2 重要）：
- 所有约束均用直接字段表达取值。是否按软约束处理由各字段的 xxx_is_soft 布尔决定：未设或为 false 时为硬约束（不满足则排除），为 true 时为软约束（匹配则加分，不匹配不排除）。
- 明确/肯定表达 → 只设直接字段，不设 xxx_is_soft。例如：「要精装」→decoration="精装"；「必须有电梯」→elevator=true；「要能养猫」→pet_policy="可养猫"；「月付」→payment_method="月付"；「附近有公园」→required_nearby=["近公园"]。
- 模糊/期望表达 → 必须同时设直接字段与对应 xxx_is_soft: true。支持 is_soft 的字段包括：decoration, elevator, orientation, floor_pref, max_subway_dist, rental_type, pet_policy, viewing_method, viewing_time, lease_flexibility, termination_sublet, parking_type, required_utilities, required_nearby, payment_method, deposit_type, no_agent_fee。示例：「最好精装」→decoration="精装", decoration_is_soft=true；「希望附近有公园」→required_nearby=["近公园"], required_nearby_is_soft=true；「希望线上VR看房」→viewing_method="仅线上VR看房", viewing_method_is_soft=true；「最好离地铁800米以内」→max_subway_dist=800, max_subway_dist_is_soft=true；「最好房东直租」→no_agent_fee=true, no_agent_fee_is_soft=true；「最好能月付」→payment_method="月付", payment_method_is_soft=true。
- 当用户说「最好XX」「希望XX」「如果有XX」时，既要设置对应的直接字段，也必须设该字段的 xxx_is_soft: true，缺一不可。

概念与参数区分（避免混用）：
- 付款周期 vs 租期：用户问「能不能月付」「希望月付」「押一付一」→ 只填 payment_method（及 payment_method_is_soft），不要填 lease_flexibility。lease_flexibility 仅表示租期长短（如可月租、可租3个月），与「按月付款」无关。
- 费用包含：用户说「网费/宽带包含在房租里」「网费能直接包含在房租里」→ required_utilities: ["包宽带"]（不要用「免宽带费」）。用户说「物业费包在房租里」→ required_utilities: ["包物业费"]（不要用「免物业费」）。用户说「车位最好免费」「车位费包在房租里」→ required_utilities: ["免车位费"] 并设 required_utilities_is_soft: true；不要用 parking_type（parking_type 仅表示有无车位类型：车库/露天/无）。
- 安静与静养：用户说「需要静养」「睡眠不好」「要安静」「环境安静」→ 必须设 noise_preference: "安静"。

价格「左右」：用户说「N元左右」时，min_price=N×0.8、max_price=N×1.2，取整百。如「3000左右」→min_price=2400, max_price=3600。

使用 update_preferences 与 search_by_preferences 的规则：
- 用户表达找房需求时，必须按顺序先 update_preferences 再 search_by_preferences；二者成对调用。当用户说「帮我找找」「找一下」时，必须调用 search_by_preferences 获取房源并回复。
- 每轮 update_preferences 只传本轮新增或变更的字段，不要传本轮未提及的字段（避免多传 orientation、house_feature 等导致断言失败）。仅当用户仅变更部分条件时，可同时传入要保留的关键条件与本轮变更的字段。
- 对于 required_nearby、required_utilities 等数组：若用户在本轮是「追加」需求（如上一轮已要近公园，本轮又说「还要菜市场」），只传本轮新增的项（如 required_nearby: ["近菜市场"]），不要重复传上一轮已有项，由后端合并。
- 位置统一放在 location 数组，支持区名/商圈/地标/地铁站/小区名。如 location: ["朝阳"]、["望京"]、["双合站"]、["国贸附近"]。
- 「换XX看看」：传新 location 与其它条件即可，系统自动处理换区；需要时传 clear_location: true。
- 用户仅表达通勤/西二旗距离时，只设置 max_commute_minutes，不要推断 location。
- 日期：用户说「X月可入住」时按 2026 年解析，如 available_before="2026-03-01"。
- 未调用 search_by_preferences 时，禁止虚构或引用任何 house_id。

租房动作：
- 用户要租某套房时，先 get_house_detail 再根据意图调用 execute_action；不要跳过 get_house_detail。
- 「这套」「那套」从最近一轮 search 返回的 items 中确定 house_id；若推荐了多套且用户说「这套可以租吗」，取列表第一套。

输出格式：
- 调用 search_by_preferences 后，用自然语言描述返回的房源，系统自动处理 JSON。使用 items 中的 house_id，禁止编造。每次最多推荐 5 套房源。"""

MAX_ITERATIONS = 10
HOUSE_SEARCH_TOOLS = {"update_preferences", "search_by_preferences"}
MODEL_PROXY_PORT = int(os.environ.get("MODEL_PROXY_PORT", "8888"))

# 静态工具分发表（不含 update_preferences、search_by_preferences，因其需在运行时绑定 session_prefs）
TOOL_DISPATCH: dict[str, Callable] = {
    "get_house_detail": get_house_detail,
    "get_house_listings": get_house_listings,
    "execute_action": execute_action,
}


async def run_agent(
    history: list,
    model_ip: str,
    client: httpx.AsyncClient,
    session_id: str = "",
    session_prefs: UserPreferences | None = None,
) -> dict:
    # trust_env=False 不走代理，避免使用 HTTP_PROXY/HTTPS_PROXY 环境变量
    # 评测接口要求必须携带 Session-ID 请求头
    if session_prefs is None:
        session_prefs = UserPreferences()

    # 构建本地分发表：将 update_preferences、search_by_preferences 绑定到当前 session 的偏好对象
    local_dispatch: dict[str, Callable] = {
        **TOOL_DISPATCH,
        "update_preferences": partial(update_preferences, session_prefs=session_prefs),
        "search_by_preferences": partial(search_by_preferences, session_prefs=session_prefs),
    }

    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as llm_http_client:
        llm_client = AsyncOpenAI(
            base_url=f"http://{model_ip}:{MODEL_PROXY_PORT}/v1",
            api_key="placeholder",
            http_client=llm_http_client,
            default_headers={"Session-ID": session_id},
        )

        tools_called: set[str] = set()
        tool_results_log: list[dict] = []
        collected_house_ids: list[str] = []
        detail_house_id: str | None = None  # 单套房详情（get_house_detail 返回）
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

            log_event("MODEL_RESPONSE", session_id, {
                "iteration": iterations,
                "finish_reason": finish_reason,
                "has_tool_calls": bool(message.tool_calls),
                "content_preview": (message.content or "")[:200],
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

                    fn = local_dispatch.get(tool_name)
                    if fn is None:
                        result = {"error": f"Unknown tool: {tool_name}"}
                        log_event("ERROR", session_id, {"error": f"Unknown tool: {tool_name}", "tool_name": tool_name})
                    else:
                        allowed = TOOL_SCHEMA_PARAMS.get(tool_name, set())
                        filtered_args = {k: v for k, v in args.items() if k in allowed}
                        result = await fn(client, **filtered_args)

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
                        "args": args,
                        "result": json.dumps(result, ensure_ascii=False)[:500],
                    })

                    if tool_name in ("update_preferences", "search_by_preferences"):
                        for item in result.get("items", []):
                            hid = item.get("house_id")
                            if hid:
                                collected_house_ids.append(hid)
                    if tool_name == "get_house_detail":
                        data = result.get("data") if isinstance(result, dict) else None
                        if isinstance(data, dict):
                            hid = data.get("house_id")
                            if isinstance(hid, str) and hid:
                                detail_house_id = hid

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
            seen: set[str] = set()
            houses: list[str] = []
            for hid in collected_house_ids:
                if hid not in seen and len(houses) < 5:
                    seen.add(hid)
                    houses.append(hid)
            response_str = json.dumps(
                {"message": content, "houses": houses},
                ensure_ascii=False,
            )
            return {"response": response_str, "status": "success", "tool_results": tool_results_log, **_stats}
        if detail_house_id is not None:
            # 涉及单套房信息时按题目要求返回 {"message":"", "house":""}
            response_str = json.dumps(
                {"message": content, "house": detail_house_id},
                ensure_ascii=False,
            )
            return {"response": response_str, "status": "success", "tool_results": tool_results_log, **_stats}
        return {"response": content, "status": "success", "tool_results": tool_results_log, **_stats}
