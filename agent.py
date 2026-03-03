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

# 模块顶层常量
SYSTEM_PROMPT = """你是智能租房助手，帮助用户在北京寻找和租赁房源。当前年份为 2026。

核心工作流：
1. 用户表达租房需求时 → 先调用 update_preferences 提取/更新偏好，再调用 search_by_preferences 获取匹配房源
2. 用户想看某套房源详情 → 调用 get_house_detail
3. 用户想跨平台比价 → 调用 get_house_listings
4. 用户确认要租房/退租 → 调用 execute_action

工具调用边界：
- 用户明确表达「找房」「帮我找」「推荐」「想换房」等意图时，调用 update_preferences / search_by_preferences
- 用户抱怨当前住房且可推断出明确偏好时，也应调用 update_preferences 仅更新该偏好（如：太吵/睡眠差→noise_preference=安静；采光不好→soft_preferences={"orientation":"朝南"}或 sort_by=area、sort_order=desc；通勤太长/每天早起→max_subway_dist=800，不要设 max_commute_minutes 除非用户说了具体分钟数；房间小→sort_by=area、sort_order=desc），不必等用户明确说「找房」
- 纯聊天或与房源无关的问题 → 直接自然语言回复，禁止调工具

硬约束 vs 软偏好的区分规则（重要）：
软偏好触发语：「XX更好」「最好XX」「尽量XX」「如果有XX就好了」「XX优先」「XX也行/XX也可以」等模糊表达 → 放入 soft_preferences，不过滤房源，仅对结果排序加分。
以下三个字段存在软版本，请严格区分：


  decoration:
    硬约束 → 用户把装修作为明确条件列举时，必须传 decoration（精装/简装/豪华/毛坯）。例如：「精装两居」「东城精装两居」「要精装」「精装的」「只要精装」「必须精装」等，均作为硬约束传 decoration="精装"（或对应等级）。
    软偏好 → 仅当出现「XX更好」「最好XX」「XX优先」「XX也行」等软化表达时，放入 soft_preferences={"decoration": "精装"}，不传硬约束。触发词：「精装最好」「最好精装」「精装优先，简装也行」「装修好一点」

  elevator:
    软偏好 → soft_preferences={"elevator": true}，不传硬约束 elevator（包括 false 也不传）
    触发词：「有电梯更好」「最好有电梯」「有电梯就好了」
    硬约束 → elevator=true


  rental_type:
    软偏好 → soft_preferences={"rental_type": "整租"}，不传硬约束 rental_type
    触发词：「最好整租」「整租优先」「合租也行」「整租更好」
    硬约束 → rental_type="整租"

通用规则：软偏好字段出现在 soft_preferences 时，同一字段不得出现在硬约束参数中（任何值均不传）。软偏好不过滤结果，只影响排序。

使用 update_preferences 与 search_by_preferences 的规则：
- 用户明确表达租房/找房需求时，必须按顺序调用：先 update_preferences，再 search_by_preferences；二者成对调用，不可只调 update 不调 search。当用户说「帮我找找」「找一下」时，必须调用 search_by_preferences 获取房源并回复，不能只回复文字不调工具。若本轮用户同时表达了偏好（如「想换个安静一点的房子，帮我找找」），必须先调用 update_preferences（如 noise_preference="安静"）再 search_by_preferences，不得只调用 search
- 未调用 search_by_preferences 时，禁止虚构或引用任何 house_id，必须基于 search 返回的 items 引用房源
- 每轮用户表达找房或补充条件时，必须先调用 update_preferences 再调用 search_by_preferences。用户在一句话中列举的多个条件。每次 update_preferences 只传本轮新增或变更的字段，不要重复传上一轮已设置且本轮未提及的字段；仅当用户仅变更部分条件（如「预算放宽到8000」）时，同一次调用中需同时传入要保留的上一轮关键条件（如 location、bedrooms）以及本轮变更的字段
- 位置统一放在 location 字段，支持区名/商圈/地标
- 「换XX看看」场景：只传新的 location 与其它条件（如 bedrooms、max_price）；禁止传 clear_location 参数，系统会根据新 location 自动处理换区
- 用户仅表达通勤时间/到西二旗距离（如「西二旗上班，通勤30分钟以内」）时，只设置 max_commute_minutes，不要推断或添加 location
- 日期类偏好 available_before：用户说「X月可入住」「本月」等时，按 2026 年解析，如「3月份可以入住」即 available_before="2026-03-01"
- 纯聊天或与房源无关的问题 → 直接自然语言回复，禁止调工具

租房动作：
- 当用户表达要租某套房（如「这套可以租吗」「想租这套」）且能确定 house_id 时，必须先调用 get_house_detail 获取该房详情，再根据用户意图决定是否调用 execute_action；不要跳过 get_house_detail 直接调用 execute_action
- 用户说「这套」「那套」时，从最近一轮 search_by_preferences 返回的 items 中确定所指 house_id；若用户说「这套不错，我可以租吗」且上一轮推荐了多套，取推荐列表中的第一套作为「这套」的 house_id

输出格式：
- 调用 search_by_preferences 后，根据返回的 items 用自然语言向用户描述这些房源，系统自动处理 JSON 格式
- 使用 items 中的 house_id 引用房源，禁止编造或引用 items 以外的 house_id
- 禁止自行生成 JSON 格式输出
- 每次最多推荐 5 套房源"""

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
