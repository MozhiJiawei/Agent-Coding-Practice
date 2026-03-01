"""Test Runner — Chat Client + 断言引擎 + 报告生成 (Story 6.1-6.2)"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

import httpx

from config import (
    CaseResult,
    ExpectRules,
    SimulatorConfig,
    TestCase,
    TokenCounter,
    TokenUsage,
)

# ── 辅助函数 ──────────────────────────────────────────────────────────────────


def extract_house_ids(resp_text: str) -> list[str]:
    """从 Agent response 文本中解析房源 ID 列表。

    若非合法 JSON、无 houses 字段或元素非字符串，返回 []。
    """
    try:
        data = json.loads(resp_text)
        houses = data.get("houses", [])
        if not isinstance(houses, list):
            return []
        return [h for h in houses if isinstance(h, str)]
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
    """
    actual = extract_house_ids(response.get("response", ""))
    if isinstance(expected, list) and expected:
        missing = set(expected) - set(actual)
        if missing:
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


# ── ASSERTION_RULES ────────────────────────────────────────────────────────────

ASSERTION_RULES: dict[str, Any] = {
    "has_response": _has_response,
    "response_not_empty": _response_not_empty,
    "response_json_valid": _response_json_valid,
    "houses_match": _houses_match,
    "houses_match_subset": _houses_match_subset,
    "house_count_min": _house_count_min,
    "status_success": _status_success,
}

# ── check_assertions ──────────────────────────────────────────────────────────


def check_assertions(
    response: dict,
    expect: ExpectRules,
    case: TestCase,
) -> tuple[bool, str]:
    """按 ExpectRules 逐条调用 ASSERTION_RULES，返回 (passed, failure_reason)。"""
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
        # Subset mode: use houses_match list as expected IDs
        subset_ids = expect.houses_match if expect.houses_match else []
        checks.append(("houses_match_subset", subset_ids))
    if expect.house_count_min is not None:
        checks.append(("house_count_min", expect.house_count_min))
    if expect.status_success is not None:
        checks.append(("status_success", expect.status_success))

    for rule_name, expected_val in checks:
        fn = ASSERTION_RULES.get(rule_name)
        if fn is None:
            return (False, f"Unknown assertion rule: {rule_name}")
        try:
            passed, reason = fn(response, expected_val)
        except Exception as exc:  # noqa: BLE001
            return (False, f"{rule_name}: unexpected error: {exc}")
        if not passed:
            return (False, reason)

    return (True, "")


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


async def _execute_case(
    case: TestCase,
    config: SimulatorConfig,
    client: httpx.AsyncClient,
    token_counter: TokenCounter,
) -> CaseResult:
    """Core case execution without timeout wrapper."""
    session_id = f"test-{case.id}-{int(time.time())}"
    model_ip = "127.0.0.1"
    t_start = time.perf_counter()
    rounds = 0
    last_body: dict | None = None

    for msg in case.messages:
        body, err = await send_message(
            client, config.agent_base_url, session_id, model_ip, msg
        )
        if err is not None:
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return CaseResult(
                case_id=case.id,
                case_type=case.type,
                status="ERROR",
                duration_ms=elapsed_ms,
                rounds=rounds,
                failure_reason=err,
                token_usage=token_counter.to_token_usage(),
            )
        rounds += 1
        last_body = body

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    if case.expect is None or last_body is None:
        status = "PASS" if last_body is not None else "FAIL"
        return CaseResult(
            case_id=case.id,
            case_type=case.type,
            status=status,  # type: ignore[arg-type]
            duration_ms=elapsed_ms,
            rounds=rounds,
            failure_reason=None if status == "PASS" else "No response received",
            actual_response=last_body.get("response") if last_body else None,
            token_usage=token_counter.to_token_usage(),
        )

    passed, reason = check_assertions(last_body, case.expect, case)
    return CaseResult(
        case_id=case.id,
        case_type=case.type,
        status="PASS" if passed else "FAIL",
        duration_ms=elapsed_ms,
        rounds=rounds,
        failure_reason=reason if not passed else None,
        actual_response=last_body.get("response"),
        token_usage=token_counter.to_token_usage(),
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
    """Print formatted case result to stdout (AC9, AC10)."""
    duration_s = result.duration_ms / 1000
    label = "PASS" if result.status == "PASS" else "FAIL"
    print(f"[{idx}/{total}] {result.case_id} ...... {label}  ({duration_s:.1f}s)")
    if result.status != "PASS" and result.failure_reason:
        print(f"       \u2717 {result.failure_reason}")


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
    failed = total - passed
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

    md_lines.extend(["", f"## Total: {passed} passed, {failed} failed"])

    md_path = os.path.join(config.report_dir, f"report-{timestamp_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    return json_path
