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
    update_preferences, UserPreferences,
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

SYSTEM_PROMPT = """你是智能租房助手，根据用户的输入推断（不虚构）用户偏好，帮助用户在北京寻找和租赁房源。当前年份为 2026。

工具调用流程：
1. 用户表达租房需求、吐槽当前住房（如太吵、采光差）或找房 → 调用 update_preferences（会同时更新偏好并搜索，返回匹配的 top 5 房源）
2. 用户查看某套房源详情 → get_house_detail
3. 用户跨平台比价 → get_house_listings
4. 用户确认租房/退租/下架 → 先 get_house_detail 确认，再 execute_action

调用边界：
- 纯聊天或无关问题 → 直接自然语言回复，禁止调工具
- 「这套/那套」从最近 update_preferences 返回的 items 确定 house_id，多套时取第一套

update_preferences 提参示例（仅传用户提到的字段）：
* 朝阳中粮，两居，最好精装,预算2000左右 → location:["朝阳", "中粮"], bedrooms:"2", decoration:"精装", decoration_is_soft:true, price_around:2000
* 西城中铝,两居,希望空房、最好是朝南,必须有电梯尽量低楼层,预算5000左右, 近地铁 → location:["西城","中铝"], bedrooms:"2", decoration:"空房", decoration_is_soft:false, orientation:"朝南", orientation_is_soft:true, elevator:true, floor_pref:"低层", floor_pref_is_soft:true, max_price:5000, near_subway:true
* 海淀中关村站附近,两居,2000以内,近地铁 → location:["海淀","中关村站"], bedrooms:"2", price_around:5000, near_subway:true
* 两居,预算五千以内、100平左右→ bedrooms:"2", max_price:2000, area_around:100
* 现在住得太吵采光差→ noise_preference:"安静", orientation:"朝南"
* 在安居客上找，月付，如果能房东直租最好，可养猫、押一付一 → listing_platform:"安居客", payment_method:"月付", no_agent_fee:true, no_agent_fee_is_soft:true, pet_policy:"可养猫", deposit_type:"押一"
* 希望周末看房、可租3个月、包宽带近医院 → viewing_time:"仅周末看房", lease_flexibility:"可租3个月", required_utilities:["包宽带"], required_nearby:["近医院"]
* 南北通透、希望房东好沟通、绿化好、尽量物业到位 → house_feature:"南北通透", landlord_contract:"房东好沟通", environment_preference:"绿化好环境佳", property_management:"物业管理到位", property_management_is_soft:true

输出规则：
- 调用 update_preferences 后用自然语言描述房源，每次最多推荐 5 套
- 使用 items 中的 house_id；未调用 update_preferences 时禁止虚构任何 house_id"""


MAX_ITERATIONS = 10
HOUSE_SEARCH_TOOLS = {"update_preferences"}
MODEL_PROXY_PORT = int(os.environ.get("MODEL_PROXY_PORT", "8888"))

# 静态工具分发表（不含 update_preferences，因其需在运行时绑定 session_prefs）
TOOL_DISPATCH: dict[str, Callable] = {
    "get_house_detail": get_house_detail,
    "get_house_listings": get_house_listings,
    "execute_action": execute_action,
}


def _preferences_summary(prefs: UserPreferences) -> dict:
    """从当前 session 偏好中提取非空字段摘要，供 tool_results 携带。"""
    raw = prefs.model_dump(exclude_none=True)
    # 排除内部/上下文字段，只保留用户可理解的偏好
    skip = {"mentioned_house_ids", "current_focus_house_id", "soft_constraint_keys", "clear_location"}
    return {k: v for k, v in raw.items() if k not in skip and v != [] and v != ""}


def _build_final_tool_results(
    tool_results_log: list[dict],
    session_prefs: UserPreferences,
) -> list[dict]:
    """在正式回复时，在 tool_results 中追加当前偏好摘要。TOP5 房屋结果已在对话回复中体现，不再在 tool 中携带 house_id。"""
    pref = _preferences_summary(session_prefs)
    return [
        *tool_results_log,
        {"tool_name": "current_preferences", "args": None, "result": json.dumps(pref, ensure_ascii=False)},
    ]


def _trim_tool_results_from_history(history: list) -> None:
    """从持久化上下文中移除工具调用结果及仅含 tool_calls 的 assistant 消息，仅当轮内给模型看过一次，多轮不保留以节省 token。"""
    kept: list = []
    for msg in history:
        if msg.get("role") == "tool":
            continue
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            # 若有正文则保留消息但去掉 tool_calls，避免下一轮出现“有调用无结果”
            if msg.get("content"):
                m = {**msg, "tool_calls": None}
                m.pop("tool_calls", None)
                kept.append(m)
            continue
        kept.append(msg)
    history.clear()
    history.extend(kept)


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

    # 构建本地分发表：将 update_preferences 绑定到当前 session 的偏好对象（内部会执行搜索）
    local_dispatch: dict[str, Callable] = {
        **TOOL_DISPATCH,
        "update_preferences": partial(update_preferences, session_prefs=session_prefs),
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
                _trim_tool_results_from_history(history)
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
                _trim_tool_results_from_history(history)
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

                    if tool_name == "update_preferences":
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
            _trim_tool_results_from_history(history)
            return {
                "response": response_str,
                "status": "success",
                "tool_results": _build_final_tool_results(tool_results_log, session_prefs),
                **_stats,
            }
        if detail_house_id is not None:
            # 涉及单套房信息时按题目要求返回 {"message":"", "house":""}
            response_str = json.dumps(
                {"message": content, "house": detail_house_id},
                ensure_ascii=False,
            )
            _trim_tool_results_from_history(history)
            return {
                "response": response_str,
                "status": "success",
                "tool_results": _build_final_tool_results(tool_results_log, session_prefs),
                **_stats,
            }
        _trim_tool_results_from_history(history)
        return {
            "response": content,
            "status": "success",
            "tool_results": _build_final_tool_results(tool_results_log, session_prefs),
            **_stats,
        }
