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
from logger import log_event, current_session_id

# 从 TOOLS schema 构建「工具名 -> 允许的参数名集合」，调用时只传 schema 内参数，避免 LLM 误传导致 TypeError
TOOL_SCHEMA_PARAMS: dict[str, set[str]] = {}
for _t in TOOLS:
    if _t.get("type") == "function" and "function" in _t:
        _name = _t["function"].get("name")
        _params = _t["function"].get("parameters") or {}
        _props = _params.get("properties") or {}
        if _name:
            TOOL_SCHEMA_PARAMS[_name] = set(_props.keys())

SYSTEM_PROMPT = """你是智能租房助手，帮助用户在北京寻找和租赁房源。当前年份为 2026。

工具调用流程：
1. 用户表达租房需求 → 先 update_preferences 再 search_by_preferences（必须成对调用）
2. 用户查看某套房源详情 → get_house_detail
3. 用户跨平台比价 → get_house_listings
4. 用户确认租房/退租/下架 → 先 get_house_detail 确认，再 execute_action

调用边界：
- 用户明确「找房/推荐/帮我找/想换房」→ 成对调用 update_preferences + search_by_preferences
- 用户抱怨当前住房且可推断偏好（如太吵→安静、采光差→朝南、通勤长→近地铁）→ 可仅调 update_preferences
- 纯聊天或无关问题 → 直接自然语言回复，禁止调工具
- 「这套/那套」从最近 search 返回的 items 确定 house_id；多套时取第一套

update_preferences 提参示例（仅传用户提到的字段）：
1) 海淀两居整租3000~6000 → location:["海淀"], bedrooms:"2", rental_type:"整租", min_price:3000, max_price:6000
2) 换大兴看看两居5000左右 → clear_location:true, location:["大兴"], bedrooms:"2", min_price:4000, max_price:6000
3) 80~100平两居或三居4000以内 → min_area:80, max_area:100, bedrooms:"2,3", max_price:4000
4) 朝阳两居5000以内最好精装地铁从近到远 → location:["朝阳"], bedrooms:"2", max_price:5000, decoration:"精装", decoration_is_soft:true, sort_by:"subway", sort_order:"asc"
5) 海淀合租3000民水民电希望月付最好房东直租 → location:["海淀"], rental_type:"合租", max_price:3000, utilities_type:"民水民电", payment_method:"月付", no_agent_fee:true, no_agent_fee_is_soft:true
6) 13号线沿线两居近地铁 → subway_line:"13号线", max_subway_dist:800, sort_by:"subway", sort_order:"asc", bedrooms:"2"
7) 朝阳两居要安静最好朝南有电梯尽量低楼层 → location:["朝阳"], bedrooms:"2", noise_preference:"安静", orientation:"朝南", orientation_is_soft:true, elevator:true, floor_pref:"低层", floor_pref_is_soft:true
8) 月付房东直租押一付一可养猫3月10日前入住通勤30分钟内按价格从低到高 → payment_method:"月付", no_agent_fee:true, deposit_type:"押一", pet_policy:"可养猫", available_before:"2026-03-10", max_commute_minutes:30, sort_by:"price", sort_order:"asc"
9) 希望线下看房仅周末、最多租3个月包宽带近医院南北通透房东好沟通 → viewing_method:"仅线下看房", viewing_time:"仅周末看房", lease_flexibility:"可租3个月", required_utilities:["包宽带"], required_nearby:["近医院"], house_feature:"南北通透", landlord_contract:"房东好沟通"
10) 住宅不要公寓、车库车位24小时保安绿化好物业到位提前退租可协商 → property_type:"住宅", parking_type:"车库车位", security_requirement:"24小时保安", environment_preference:"绿化好环境佳", property_management:"物业管理到位", termination_sublet:"提前退租可协商"

输出规则：
- 调用 search_by_preferences 后用自然语言描述房源，每次最多推荐 5 套
- 使用 items 中的 house_id，未调用 search_by_preferences 时禁止虚构任何 house_id"""


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
            call_tokens = 0
            this_round_slices = 0
            if response.usage:
                call_tokens = response.usage.total_tokens
                total_tokens += call_tokens
                t = 1 + max(0, (call_tokens / 1000 - 1)) * 0.3
                this_round_slices = math.ceil(t)
                total_time_slices += this_round_slices
            # 每轮 LLM 调用后打印：本轮 token/时间片、累计 token/时间片（便于分析哪轮耗 token 多）
            print(
                f"[{session_id}] 第{iterations + 1}轮 | "
                f"本轮token: {call_tokens} 本轮时间片: {this_round_slices} | "
                f"累计token: {total_tokens} 累计时间片: {total_time_slices}"
            )
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
                        token = current_session_id.set(session_id)
                        try:
                            result = await fn(client, **filtered_args)
                        finally:
                            current_session_id.reset(token)

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
