"""Test Runner — Chat Client + 断言引擎 + 报告生成 (Story 6.1-6.2)"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Callable

import httpx

from config import (
    CaseResult,
    ExpectRules,
    RoundDetail,
    RoundExpect,
    SimulatorConfig,
    TestCase,
    TokenCounter,
    TokenUsage,
)

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

# 位置常见后缀，用于 tool_call_args 中 location 的模糊等价判定
_LOCATION_SUFFIXES = ("商圈", "商业区", "片区", "附近", "区")


def _strip_location_suffix(loc: str) -> str:
    """去掉位置常见后缀，得到规范化字符串用于等价比较。"""
    s = loc
    for suffix in _LOCATION_SUFFIXES:
        if s.endswith(suffix):
            return s.removesuffix(suffix)
    return s


def _locations_equivalent(expected: list, actual: list) -> bool:
    """判断 expected 与 actual 在位置语义上是否等价（支持 海淀区↔海淀、望京商圈↔望京 等）。"""
    if not isinstance(expected, list) or not isinstance(actual, list):
        return False
    exp_strs = [str(x) for x in expected]
    act_strs = [str(x) for x in actual]
    exp_norm = {_strip_location_suffix(e) for e in exp_strs}
    act_norm = {_strip_location_suffix(a) for a in act_strs}
    return exp_norm <= act_norm


def extract_house_ids(resp_text: str) -> list[str]:
    """从 Agent response 文本中解析房源 ID 列表。

    支持 "houses"（数组）与 "house"（单套，题目要求格式）；若非合法 JSON 返回 []。
    """
    try:
        data = json.loads(resp_text)
        # 优先 "houses" 多套；其次 "house" 单套（题目要求 {"message":"", "house":""}）
        houses = data.get("houses", [])
        if isinstance(houses, list) and houses:
            return [h for h in houses if isinstance(h, str)]
        single = data.get("house")
        if isinstance(single, str) and single:
            return [single]
        if isinstance(single, list):
            return [h for h in single if isinstance(h, str)]
        return []
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


# ── 断言函数 ──────────────────────────────────────────────────────────────────


def _has_response(response: dict, expected: Any) -> tuple[bool, str]:
    if "response" in response:
        return (True, "")
    return (False, "has_response: no 'response' field in API response")


def _response_not_empty(response: dict, expected: Any) -> tuple[bool, str]:
    text = response.get("response", "")
    if text:
        return (True, "")
    return (False, "response_not_empty: response text is empty")


def _response_json_valid(response: dict, expected: Any) -> tuple[bool, str]:
    text = response.get("response", "")
    try:
        json.loads(text)
        return (True, "")
    except (json.JSONDecodeError, TypeError):
        return (False, f"response_json_valid: not valid JSON: {text[:80]!r}")


def _houses_match(response: dict, expected: Any) -> tuple[bool, str]:
    actual = extract_house_ids(response.get("response", ""))
    exp_list = expected if isinstance(expected, list) else []
    if sorted(actual) == sorted(exp_list):
        return (True, "")
    return (False, f"houses_match: expected {sorted(exp_list)}, got {sorted(actual)}")


def _houses_match_subset(response: dict, expected: Any) -> tuple[bool, str]:
    """AC6: set(expected_ids) ⊆ set(actual_houses).

    expected 为 houses_match 中的 ID 列表（子集预期 IDs）；
    若为空列表，仅检查 actual 非空。
    当期望有房源但 actual 为空时，若未调用 search_by_preferences 则给出链式调用提示。
    """
    actual = extract_house_ids(response.get("response", ""))
    tool_results = response.get("tool_results", [])
    called_tools = {r.get("tool_name") for r in tool_results if r.get("tool_name")}

    if isinstance(expected, list) and expected:
        missing = set(expected) - set(actual)
        if missing:
            if not actual and "search_by_preferences" not in called_tools:
                return (
                    False,
                    "houses_match_subset: search_by_preferences 未被调用（找房需先 update_preferences 再 search_by_preferences），houses 为空",
                )
            return (False, f"houses_match_subset: missing IDs {sorted(missing)} in {actual}")
        return (True, "")
    # expected 为空 → 只检查 actual 非空
    if actual:
        return (True, "")
    return (False, "houses_match_subset: no houses in response")


def _house_count_min(response: dict, expected: Any) -> tuple[bool, str]:
    actual = extract_house_ids(response.get("response", ""))
    count = len(actual)
    try:
        minimum = int(expected) if expected is not None else 0
    except (ValueError, TypeError):
        return (False, f"house_count_min: invalid expected value {expected!r}")
    if count >= minimum:
        return (True, "")
    return (False, f"house_count_min: expected ≥{minimum} houses, got {count}")


def _status_success(response: dict, expected: Any) -> tuple[bool, str]:
    status = response.get("status", "")
    if status == "success":
        return (True, "")
    return (False, f"status_success: expected 'success', got {status!r}")


def _tag_list_equivalent(expected: list, actual: list) -> bool:
    """标签列表等价：无序集合一致；精装修/精装等归一化后比较。"""
    if not isinstance(expected, list) or not isinstance(actual, list):
        return False
    _tag_norm = {"精装修": "精装", "精修": "精装", "精": "精装", "简装修": "简装", "简修": "简装", "简": "简装"}
    def norm(s: str) -> str:
        return _tag_norm.get(str(s).strip(), str(s).strip())
    exp_set = {norm(x) for x in expected if isinstance(x, str)}
    act_set = {norm(x) for x in actual if isinstance(x, str)}
    return exp_set == act_set


def _tool_call_args(response: dict, expected: Any) -> tuple[bool, str]:
    """验证指定工具被调用，且参数精确匹配：实际 args 的键必须与 contains 完全一致（不含 *_is_soft 标记键）。

    expected 为 ToolCallArgsExpect.model_dump()，含 tool 和 contains 两个字段。
    contains 中以 _is_soft 结尾的键仅作为“软断言”标记，不参与键集合校验（未配置时等价于 false，校验通过）。
    当某字段配置了 XX_is_soft: true 且该字段识别错误时，视为软失败，用例标为黄灯（WARN）。
    软约束字段 XX_is_soft：若模型传入 false 而用例未在 contains 中配置，视为通过（符合默认值，见 intent_interface_design_v2）。
    location/decoration 等值仍按现有规则做模糊等价。
    """
    if not isinstance(expected, dict):
        return (False, "tool_call_args: invalid expected config")
    tool_name = expected.get("tool", "")
    contains = expected.get("contains", {}) or {}

    # 仅用非 _is_soft 的键参与“声明参数”校验，未配置 XX_is_soft 时等价为 false，校验通过
    expected_keys = {k for k in contains.keys() if not (isinstance(k, str) and k.endswith("_is_soft"))}
    allowed_keys = set(contains.keys())  # 实际 args 允许的键 = contains 全部，避免 contains 里写了 _is_soft 仍被判为"未声明"

    tool_results = response.get("tool_results", [])
    matching = [r for r in tool_results if r.get("tool_name") == tool_name]

    if not matching:
        called = [r.get("tool_name") for r in tool_results]
        return (False, f"tool_call_args: 工具 '{tool_name}' 未被调用（实际调用：{called}）")

    actual_args = matching[0].get("args") or {}
    mismatches: list[str] = []
    soft_mismatches: list[str] = []
    actual_keys = set(actual_args.keys())
    extra = actual_keys - allowed_keys
    # 软约束标记 XX_is_soft：若模型传入 false 且用例未配置，视为通过（符合默认值，见 intent_interface_design_v2）
    extra = {k for k in extra if not (
        isinstance(k, str) and k.endswith("_is_soft") and actual_args.get(k) is False
    )}
    missing = expected_keys - actual_keys
    if extra:
        # 仅多出 *_is_soft 参数时视为软失败（黄灯），与 c6 等场景一致
        extra_list = sorted(extra)
        msg = f"存在未在 contains 中声明的参数: {extra_list!r}"
        if all(isinstance(k, str) and k.endswith("_is_soft") for k in extra):
            soft_mismatches.append(msg)
        else:
            mismatches.append(msg)
    if missing:
        mismatches.append(f"缺少参数: {sorted(missing)!r}")

    def is_soft_key(key: str) -> bool:
        soft_flag = key + "_is_soft"
        return bool(contains.get(soft_flag) if isinstance(contains.get(soft_flag), bool) else False)

    for key, expected_val in contains.items():
        if isinstance(key, str) and key.endswith("_is_soft"):
            # 校验模型返回的 *_is_soft 与用例期望一致（如 no_agent_fee_is_soft: true）
            actual_soft = actual_args.get(key)
            if actual_soft is not None and actual_soft != expected_val:
                soft_mismatches.append(f"{key}: 期望 {expected_val!r}, 实际 {actual_soft!r}")
            continue
        actual_val = actual_args.get(key)
        mismatch_msg: str | None = None
        if key == "location" and isinstance(expected_val, list) and isinstance(actual_val, list):
            if not _locations_equivalent(expected_val, actual_val):
                mismatch_msg = f"{key}: 期望 {expected_val!r}, 实际 {actual_val!r}"
        elif key == "decoration" and isinstance(expected_val, str) and isinstance(actual_val, str):
            _dec_norm = {"精装修": "精装", "精修": "精装", "精": "精装", "简装修": "简装", "简修": "简装", "简": "简装"}
            exp_norm = _dec_norm.get(expected_val, expected_val)
            act_norm = _dec_norm.get(actual_val, actual_val)
            if exp_norm != act_norm:
                mismatch_msg = f"{key}: 期望 {expected_val!r}, 实际 {actual_val!r}"
        elif key in ("tag_preferences", "required_nearby", "required_utilities") and isinstance(expected_val, list) and isinstance(actual_val, list):
            if not _tag_list_equivalent(expected_val, actual_val):
                mismatch_msg = f"{key}: 期望 {expected_val!r}, 实际 {actual_val!r}"
        elif key == "bedrooms" and expected_val is not None and actual_val is not None:
            exp_b = ",".join(str(expected_val).replace(" ", "").split(","))
            act_b = ",".join(str(actual_val).replace(" ", "").split(","))
            if exp_b != act_b:
                mismatch_msg = f"{key}: 期望 {expected_val!r}, 实际 {actual_val!r}"
        elif actual_val != expected_val:
            mismatch_msg = f"{key}: 期望 {expected_val!r}, 实际 {actual_val!r}"

        if mismatch_msg:
            if is_soft_key(key):
                soft_mismatches.append(mismatch_msg)
            else:
                mismatches.append(mismatch_msg)

    if mismatches:
        return (False, f"tool_call_args({tool_name}): " + "; ".join(mismatches))
    if soft_mismatches:
        return (False, "SOFT: " + f"tool_call_args({tool_name}): " + "; ".join(soft_mismatches))
    return (True, "")


def _tool_call_chain(response: dict, expected: Any) -> tuple[bool, str]:
    """验证工具按预期顺序链式调用（先 update_preferences，再 search_by_preferences 等）。

    expected 为工具名列表，如 ["update_preferences", "search_by_preferences"]。
    实际调用序列的前缀必须与 expected 一致（允许实际有更多后续调用）。
    """
    if not isinstance(expected, list) or not expected:
        return (False, "tool_call_chain: invalid expected config (non-empty list required)")
    tool_results = response.get("tool_results", [])
    actual = [r.get("tool_name") for r in tool_results if r.get("tool_name")]
    # 实际序列的前 len(expected) 个必须与 expected 完全一致
    if len(actual) < len(expected):
        return (
            False,
            f"tool_call_chain: 期望至少 {len(expected)} 个工具调用且顺序为 {expected}，"
            f"实际仅 {len(actual)} 个: {actual}",
        )
    for i, exp_name in enumerate(expected):
        if actual[i] != exp_name:
            return (
                False,
                f"tool_call_chain: 第 {i + 1} 个调用期望 '{exp_name}'，实际为 '{actual[i]}'；"
                f"期望顺序 {expected}，实际 {actual}",
            )
    return (True, "")


def _no_tool_call(response: dict, expected: Any) -> tuple[bool, str]:
    """验证本轮响应中未调用任何工具。"""
    tool_results = response.get("tool_results", [])
    if not tool_results:
        return (True, "")
    called = [r.get("tool_name") for r in tool_results]
    return (False, f"no_tool_call: 期望无工具调用，实际调用了 {called}")


def _message_content(response: dict, expected: Any) -> tuple[bool, str]:
    """校验 agent 给用户回复的消息是否包含预期子字符串列表（全部包含才通过）。"""
    if not isinstance(expected, list) or not expected:
        return (True, "")  # 空列表或非列表视为不校验
    text = response.get("response", "") or ""
    missing: list[str] = []
    for sub in expected:
        if not isinstance(sub, str):
            continue
        if sub not in text:
            missing.append(sub)
    if missing:
        return (False, f"message_content: 回复中缺少预期子串 {missing!r}")
    return (True, "")


# ── ASSERTION_RULES ────────────────────────────────────────────────────────────

ASSERTION_RULES: dict[str, Any] = {
    "has_response": _has_response,
    "response_not_empty": _response_not_empty,
    "response_json_valid": _response_json_valid,
    "houses_match": _houses_match,
    "houses_match_subset": _houses_match_subset,
    "house_count_min": _house_count_min,
    "status_success": _status_success,
    "tool_call_args": _tool_call_args,
    "tool_call_chain": _tool_call_chain,
    "no_tool_call": _no_tool_call,
    "message_content": _message_content,
}

# ── check_assertions ──────────────────────────────────────────────────────────


def check_assertions(
    response: dict,
    expect: ExpectRules,
    case: TestCase,
) -> tuple[bool, str, bool]:
    """按 ExpectRules 逐条调用 ASSERTION_RULES，返回 (passed, failure_reason, is_soft_fail)。

    当 XX_is_soft 标记字段出现识别错误时，is_soft_fail=True，用例应标为黄灯（WARN）。
    """
    checks: list[tuple[str, Any]] = []

    if expect.has_response is not None:
        checks.append(("has_response", expect.has_response))
    if expect.response_not_empty is not None:
        checks.append(("response_not_empty", expect.response_not_empty))
    if expect.response_json_valid is not None:
        checks.append(("response_json_valid", expect.response_json_valid))
    if expect.houses_match is not None and expect.houses_match_subset is None:
        checks.append(("houses_match", expect.houses_match))
    if expect.houses_match_subset is not None:
        subset_ids = expect.houses_match if expect.houses_match else []
        checks.append(("houses_match_subset", subset_ids))
    if expect.house_count_min is not None:
        checks.append(("house_count_min", expect.house_count_min))
    if expect.status_success is not None:
        checks.append(("status_success", expect.status_success))
    if expect.tool_call_args is not None:
        checks.append(("tool_call_args", expect.tool_call_args.model_dump()))
    if expect.tool_call_chain is not None:
        checks.append(("tool_call_chain", expect.tool_call_chain))
    if expect.no_tool_call is not None:
        checks.append(("no_tool_call", expect.no_tool_call))
    if expect.message_content is not None and expect.message_content:
        checks.append(("message_content", expect.message_content))

    for rule_name, expected_val in checks:
        fn = ASSERTION_RULES.get(rule_name)
        if fn is None:
            return (False, f"Unknown assertion rule: {rule_name}", False)
        try:
            passed, reason = fn(response, expected_val)
        except Exception as exc:  # noqa: BLE001
            return (False, f"{rule_name}: unexpected error: {exc}", False)
        if not passed:
            is_soft = isinstance(reason, str) and reason.startswith("SOFT: ")
            clean_reason = reason[6:].lstrip() if is_soft else reason
            return (False, clean_reason, is_soft)

    return (True, "", False)


# ── send_message ───────────────────────────────────────────────────────────────


async def send_message(
    client: httpx.AsyncClient,
    agent_base_url: str,
    session_id: str,
    model_ip: str,
    message: str,
) -> tuple[dict, None] | tuple[None, str]:
    """POST to Agent chat API.

    Returns (body_dict, None) on success or (None, error_msg) on ConnectError.
    """
    try:
        r = await client.post(
            f"{agent_base_url}/api/v1/chat",
            json={
                "model_ip": model_ip,
                "session_id": session_id,
                "message": message,
            },
        )
        try:
            return (r.json(), None)
        except (ValueError, KeyError):
            return (None, f"Chat 响应非 JSON: status={r.status_code}, body={r.text[:200]}")
    except httpx.ConnectError as exc:
        return (None, f"Chat 不通: {exc}")
    except httpx.TimeoutException as exc:
        return (None, f"Chat 超时: {exc}")
    except httpx.HTTPError as exc:
        return (None, f"Chat HTTP 错误: {exc}")


# ── run_single_case (内部实现，不含 timeout 包装) ──────────────────────────────


async def _reload_fixture_for_case(
    case: TestCase,
    config: SimulatorConfig,
    client: httpx.AsyncClient,
) -> str | None:
    """若 case.fixture_file 已指定，则向 Mock Rental 发送重载请求。

    Returns None on success, error message on failure.
    """
    if not case.fixture_file:
        return None

    from config import load_fixtures  # noqa: PLC0415 (local import to avoid circular)

    try:
        fixtures = load_fixtures(case.fixture_file)
    except Exception as exc:  # noqa: BLE001
        return f"fixture_file 加载失败 ({case.fixture_file}): {exc}"

    reload_url = f"http://localhost:{config.mock_rental_port}/api/houses/_reload_fixture"
    try:
        resp = await client.post(reload_url, json=fixtures)
        if resp.status_code != 200:
            return f"_reload_fixture 返回非 200: {resp.status_code}"
    except httpx.ConnectError as exc:
        return f"_reload_fixture 连接失败: {exc}"
    except httpx.HTTPError as exc:
        return f"_reload_fixture HTTP 错误: {exc}"

    return None


async def _execute_case(
    case: TestCase,
    config: SimulatorConfig,
    client: httpx.AsyncClient,
    token_counter: TokenCounter,
) -> CaseResult:
    """Core case execution without timeout wrapper."""
    # ── 按用例切换 fixture（如已指定）────────────────────────────────────────
    if case.fixture_file:
        reload_err = await _reload_fixture_for_case(case, config, client)
        if reload_err:
            return CaseResult(
                case_id=case.id,
                case_type=case.type,
                status="ERROR",
                duration_ms=0,
                rounds=0,
                failure_reason=reload_err,
                token_usage=token_counter.to_token_usage(),
            )

    session_id = f"test-{case.id}-{uuid.uuid4().hex[:8]}"
    model_ip = "127.0.0.1"
    t_start = time.perf_counter()
    rounds = 0
    last_body: dict | None = None
    rounds_detail: list[RoundDetail] = []
    failure_items: list[str] = []
    soft_failure_items: list[str] = []

    def make_result(
        status: str,
        elapsed_ms: int,
        rounds: int,
        failure_reason: str | None = None,
        actual_response: str | None = None,
    ) -> CaseResult:
        return CaseResult(
            case_id=case.id,
            case_type=case.type,
            status=status,  # type: ignore[arg-type]
            duration_ms=elapsed_ms,
            rounds=rounds,
            failure_reason=failure_reason,
            actual_response=actual_response,
            token_usage=token_counter.to_token_usage(),
            rounds_detail=rounds_detail.copy(),
            session_id=session_id,
        )

    for msg in case.messages:
        body, err = await send_message(
            client, config.agent_base_url, session_id, model_ip, msg
        )
        if err is not None:
            rounds_detail.append(
                RoundDetail(round_num=rounds + 1, user_message=msg, error=err)
            )
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return make_result("ERROR", elapsed_ms, rounds, failure_reason=err)
        rounds += 1
        last_body = body
        rounds_detail.append(
            RoundDetail(
                round_num=rounds,
                user_message=msg,
                agent_response_raw=body,
                error=None,
            )
        )

        # 每轮独立断言（round_expects）：失败只记录，不终止，继续多轮
        round_expect: RoundExpect | None = next(
            (rexp for rexp in case.round_expects if rexp.round == rounds), None
        )
        if round_expect is not None and body is not None:
            r_passed, r_reason, r_soft = check_assertions(body, round_expect.expect, case)
            if not r_passed:
                if r_soft:
                    soft_failure_items.append(f"[Round {rounds}] {r_reason}")
                else:
                    failure_items.append(f"[Round {rounds}] {r_reason}")
                if rounds_detail:
                    rounds_detail[-1].expect_failure = r_reason
                    rounds_detail[-1].expect_soft_failure = r_soft

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    if case.expect is None or last_body is None:
        if failure_items:
            return make_result(
                "FAIL",
                elapsed_ms,
                rounds,
                failure_reason="\n".join(failure_items),
                actual_response=last_body.get("response") if last_body else None,
            )
        if soft_failure_items:
            return make_result(
                "WARN",
                elapsed_ms,
                rounds,
                failure_reason="\n".join(soft_failure_items),
                actual_response=last_body.get("response") if last_body else None,
            )
        status = "PASS" if last_body is not None else "FAIL"
        return make_result(
            status,
            elapsed_ms,
            rounds,
            failure_reason=None if status == "PASS" else "No response received",
            actual_response=last_body.get("response") if last_body else None,
        )

    passed, reason, is_soft_fail = check_assertions(last_body, case.expect, case)
    if not passed:
        if is_soft_fail:
            soft_failure_items.append(f"[Final] {reason}")
        else:
            failure_items.append(f"[Final] {reason}")
    # 仅当仅有软约束字段失败（无其他失败）时标为黄灯 WARN；有任何硬失败则 FAIL（见 intent_interface_design_v2）
    if failure_items:
        status = "FAIL"
        final_failure_reason = "\n".join(failure_items + soft_failure_items) if soft_failure_items else "\n".join(failure_items)
    elif soft_failure_items:
        status = "WARN"
        final_failure_reason = "\n".join(soft_failure_items)
    elif not passed:
        status = "WARN" if is_soft_fail else "FAIL"
        final_failure_reason = reason
    else:
        status = "PASS"
        final_failure_reason = None
    return make_result(
        status,
        elapsed_ms,
        rounds,
        failure_reason=final_failure_reason,
        actual_response=last_body.get("response"),
    )


async def run_single_case(
    case: TestCase,
    config: SimulatorConfig,
    client: httpx.AsyncClient,
    token_counter: TokenCounter,
) -> CaseResult:
    """Run a single test case with asyncio.wait_for timeout handling (AC7)."""
    try:
        return await asyncio.wait_for(
            _execute_case(case, config, client, token_counter),
            timeout=config.timeout_per_case,
        )
    except asyncio.TimeoutError:
        return CaseResult(
            case_id=case.id,
            case_type=case.type,
            status="TIMEOUT",
            duration_ms=config.timeout_per_case * 1000,
            rounds=0,
            failure_reason=f"超时 {config.timeout_per_case}s",
            token_usage=token_counter.to_token_usage(),
        )


# ── print_case_result ─────────────────────────────────────────────────────────


def print_case_result(idx: int, total: int, result: CaseResult) -> None:
    """Print formatted case result to stdout (AC9, AC10).

    idx 语义：并行模式下表示"已完成第 idx 个"，串行模式下表示"第 idx 个用例"。
    """
    duration_s = result.duration_ms / 1000
    if result.status == "PASS":
        label = "PASS"
    elif result.status == "WARN":
        label = "WARN"
    else:
        label = "FAIL"
    print(f"[done {idx}/{total}] {result.case_id} ...... {label}  ({duration_s:.1f}s)")
    if result.status not in ("PASS",) and result.failure_reason:
        for line in result.failure_reason.split("\n"):
            print(f"       \u2717 {line}")


# ── run_all_cases ─────────────────────────────────────────────────────────────


async def run_all_cases(
    cases: list[TestCase],
    config: SimulatorConfig,
    token_counter: TokenCounter,
) -> list[CaseResult]:
    """Run all test cases sequentially; reset token_counter before each case (Task 5)."""
    results: list[CaseResult] = []
    async with httpx.AsyncClient(timeout=config.timeout_per_case + 10.0) as client:
        for case in cases:
            token_counter.reset()
            result = await run_single_case(case, config, client, token_counter)
            results.append(result)
    return results


# ── run_cases_parallel ────────────────────────────────────────────────────────


async def _reload_global_fixture(
    config: SimulatorConfig,
    client: httpx.AsyncClient,
) -> str | None:
    """向 Mock Rental 加载全局 fixture，返回 None 成功，否则返回错误信息。"""
    from config import load_fixtures  # noqa: PLC0415

    try:
        fixtures = load_fixtures(config.fixture_file)
    except Exception as exc:  # noqa: BLE001
        return f"全局 fixture 加载失败 ({config.fixture_file}): {exc}"

    reload_url = f"http://localhost:{config.mock_rental_port}/api/houses/_reload_fixture"
    try:
        resp = await client.post(reload_url, json=fixtures)
        if resp.status_code != 200:
            return f"_reload_fixture 返回非 200: {resp.status_code}"
    except httpx.ConnectError as exc:
        return f"_reload_fixture 连接失败: {exc}"
    except httpx.HTTPError as exc:
        return f"_reload_fixture HTTP 错误: {exc}"

    return None


async def run_cases_parallel(
    cases: list[TestCase],
    config: SimulatorConfig,
    max_concurrency: int | None = None,
    on_result: Callable[[int, int, CaseResult], None] | None = None,
) -> list[CaseResult]:
    """Run all test cases in parallel with a concurrency semaphore.

    - max_concurrency: 并发上限，默认取 config.max_concurrency，最大不超过 15。
    - on_result: 每个用例完成时调用的回调，参数为 (done_count, total, result)。
    - 返回结果列表与输入 cases 顺序一致。
    """
    concurrency = min(max_concurrency or config.max_concurrency, 15)
    total = len(cases)
    results: list[CaseResult | None] = [None] * total
    completed_count = 0
    sem = asyncio.Semaphore(concurrency)
    print_lock = asyncio.Lock()

    async def _run_one(idx: int, case: TestCase, client: httpx.AsyncClient) -> None:
        nonlocal completed_count
        token_counter = TokenCounter()
        async with sem:
            result = await run_single_case(case, config, client, token_counter)
        results[idx] = result
        completed_count += 1
        done = completed_count
        if on_result is not None:
            async with print_lock:
                on_result(done, total, result)

    async with httpx.AsyncClient(timeout=config.timeout_per_case + 10.0) as client:
        # 统一加载一次全局 fixture
        err = await _reload_global_fixture(config, client)
        if err:
            print(f"[sim] WARNING: {err}，跳过 fixture 预加载，继续执行", flush=True)

        tasks = [
            asyncio.create_task(_run_one(i, case, client))
            for i, case in enumerate(cases)
        ]
        await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


# ── generate_reports ──────────────────────────────────────────────────────────


def generate_reports(
    results: list[CaseResult],
    config: SimulatorConfig,
    total_duration_ms: int,
) -> str:
    """Generate JSON and Markdown reports; return JSON report file path (AC4, AC5)."""
    os.makedirs(config.report_dir, exist_ok=True)

    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d-%H%M%S")
    timestamp_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status in ("FAIL", "ERROR", "TIMEOUT"))
    warn = sum(1 for r in results if r.status == "WARN")
    pass_rate = f"{passed / total * 100:.1f}%" if total > 0 else "0.0%"

    report_data = {
        "meta": {
            "run_id": str(uuid.uuid4()),
            "timestamp": timestamp_iso,
            "agent_base_url": config.agent_base_url,
            "total_duration_ms": total_duration_ms,
        },
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warn": warn,
            "pass_rate": pass_rate,
        },
        "cases": [r.model_dump() for r in results],
    }

    json_path = os.path.join(config.report_dir, f"report-{timestamp_str}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    md_lines = [
        f"# Test Report - {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Warn (yellow) | {warn} |",
        f"| Pass Rate | {pass_rate} |",
        "",
        "## Cases",
        "",
        "| # | case_id | type | status | duration_ms | failure_reason |",
        "|---|---------|------|--------|-------------|----------------|",
    ]
    for i, r in enumerate(results, 1):
        fr = r.failure_reason or "-"
        md_lines.append(
            f"| {i} | {r.case_id} | {r.case_type} | {r.status} | {r.duration_ms} | {fr} |"
        )

    md_lines.extend(["", f"## Total: {passed} passed, {failed} failed, {warn} warn"])

    md_path = os.path.join(config.report_dir, f"report-{timestamp_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    return json_path
