"""Unit tests for runner.py — send_message, ASSERTION_RULES, check_assertions,
run_single_case, print_case_result, run_all_cases, generate_reports (Story 6.1-6.2)"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from config import CaseResult, ExpectRules, SimulatorConfig, TestCase, TokenCounter, ToolCallArgsExpect
from runner import (
    ASSERTION_RULES,
    _locations_equivalent,
    _strip_location_suffix,
    check_assertions,
    extract_house_ids,
    generate_reports,
    print_case_result,
    run_all_cases,
    run_single_case,
    send_message,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_config(**kwargs) -> SimulatorConfig:
    defaults = dict(
        llm_proxy_url="http://localhost:9999",
        test_user_id="test-user",
        timeout_per_case=30,
        agent_base_url="http://localhost:8191",
    )
    defaults.update(kwargs)
    return SimulatorConfig(**defaults)


def make_case(
    id: str = "test-001",
    type: str = "Chat",
    messages: list[str] | None = None,
    expect: ExpectRules | None = None,
) -> TestCase:
    return TestCase(
        id=id,
        type=type,
        messages=messages or ["你好"],
        expect=expect,
    )


def make_agent_response(
    response_text: str = "Hello",
    status: str = "success",
    duration_ms: int = 100,
) -> dict:
    return {"response": response_text, "status": status, "duration_ms": duration_ms}


# ── extract_house_ids ─────────────────────────────────────────────────────────


def test_extract_house_ids_valid():
    text = json.dumps({"houses": ["HF_42", "HF_107"]})
    assert extract_house_ids(text) == ["HF_42", "HF_107"]


def test_extract_house_ids_empty_list():
    text = json.dumps({"houses": []})
    assert extract_house_ids(text) == []


def test_extract_house_ids_no_houses_key():
    text = json.dumps({"message": "hello"})
    assert extract_house_ids(text) == []


def test_extract_house_ids_invalid_json():
    assert extract_house_ids("not json") == []


def test_extract_house_ids_non_string_items():
    text = json.dumps({"houses": [1, 2, "HF_42"]})
    assert extract_house_ids(text) == ["HF_42"]


def test_extract_house_ids_non_list_houses():
    text = json.dumps({"houses": "HF_42"})
    assert extract_house_ids(text) == []


# ── ASSERTION_RULES — AC3 确保所有键存在 ──────────────────────────────────────

def test_assertion_rules_has_all_required_keys():
    required = {
        "has_response",
        "response_not_empty",
        "response_json_valid",
        "houses_match",
        "houses_match_subset",
        "house_count_min",
        "status_success",
    }
    assert required.issubset(set(ASSERTION_RULES.keys()))


def test_assertion_rules_all_are_callable():
    for key, fn in ASSERTION_RULES.items():
        assert callable(fn), f"ASSERTION_RULES['{key}'] is not callable"


# ── AC4: 断言函数返回 (bool, str), 永不抛异常 ───────────────────────────────────

def test_all_assertion_functions_return_bool_str_on_valid_input():
    resp = make_agent_response(json.dumps({"houses": ["HF_1"]}))
    for name, fn in ASSERTION_RULES.items():
        result = fn(resp, True)
        assert isinstance(result, tuple) and len(result) == 2, f"{name} did not return tuple"
        ok, msg = result
        assert isinstance(ok, bool), f"{name}: first element must be bool"
        assert isinstance(msg, str), f"{name}: second element must be str"


def test_all_assertion_functions_no_exception_on_bad_input():
    """AC4: 永不抛出异常，即使输入异常"""
    for name, fn in ASSERTION_RULES.items():
        try:
            result = fn({}, None)
            ok, msg = result
            assert isinstance(ok, bool)
            assert isinstance(msg, str)
        except Exception as exc:
            pytest.fail(f"ASSERTION_RULES['{name}'] raised {type(exc).__name__}: {exc}")


def test_pass_assertions_return_empty_string():
    """AC4: 通过时字符串为空"""
    resp = {"response": '{"houses": ["HF_1"]}', "status": "success"}
    ok, msg = ASSERTION_RULES["has_response"](resp, True)
    assert ok is True
    assert msg == ""


# ── has_response ──────────────────────────────────────────────────────────────

class TestHasResponse:
    def test_pass_with_response_field(self):
        ok, msg = ASSERTION_RULES["has_response"]({"response": "hi"}, True)
        assert ok is True
        assert msg == ""

    def test_fail_missing_response_key(self):
        ok, msg = ASSERTION_RULES["has_response"]({}, True)
        assert ok is False
        assert "has_response" in msg


# ── response_not_empty ────────────────────────────────────────────────────────

class TestResponseNotEmpty:
    def test_pass(self):
        ok, msg = ASSERTION_RULES["response_not_empty"]({"response": "hello"}, True)
        assert ok is True
        assert msg == ""

    def test_fail_empty_string(self):
        ok, msg = ASSERTION_RULES["response_not_empty"]({"response": ""}, True)
        assert ok is False
        assert "response_not_empty" in msg

    def test_fail_missing_key(self):
        ok, msg = ASSERTION_RULES["response_not_empty"]({}, True)
        assert ok is False


# ── response_json_valid ───────────────────────────────────────────────────────

class TestResponseJsonValid:
    def test_pass_valid_json(self):
        ok, msg = ASSERTION_RULES["response_json_valid"](
            {"response": '{"houses": ["HF_1"]}'}, True
        )
        assert ok is True
        assert msg == ""

    def test_fail_not_json(self):
        ok, msg = ASSERTION_RULES["response_json_valid"](
            {"response": "plain text"}, True
        )
        assert ok is False
        assert "response_json_valid" in msg

    def test_fail_empty_string(self):
        ok, msg = ASSERTION_RULES["response_json_valid"]({"response": ""}, True)
        assert ok is False


# ── houses_match — AC5 精确匹配 ───────────────────────────────────────────────

class TestHousesMatch:
    def test_pass_exact_match(self):
        resp = make_agent_response(json.dumps({"houses": ["HF_42", "HF_107"]}))
        ok, msg = ASSERTION_RULES["houses_match"](resp, ["HF_42", "HF_107"])
        assert ok is True
        assert msg == ""

    def test_fail_partial_match_ac5(self):
        """AC5: partial match should fail with expected vs actual in message"""
        resp = make_agent_response(json.dumps({"houses": ["HF_42"]}))
        ok, msg = ASSERTION_RULES["houses_match"](resp, ["HF_42", "HF_107"])
        assert ok is False
        assert "HF_42" in msg
        assert "HF_107" in msg
        assert "houses_match" in msg

    def test_pass_different_order(self):
        """Order should not matter — architecture specifies set-like comparison"""
        resp = make_agent_response(json.dumps({"houses": ["HF_107", "HF_42"]}))
        ok, msg = ASSERTION_RULES["houses_match"](resp, ["HF_42", "HF_107"])
        assert ok is True
        assert msg == ""

    def test_fail_empty_response(self):
        resp = make_agent_response("not json")
        ok, msg = ASSERTION_RULES["houses_match"](resp, ["HF_42"])
        assert ok is False


# ── houses_match_subset — AC6 子集匹配 ───────────────────────────────────────

class TestHousesMatchSubset:
    def test_pass_subset_ac6(self):
        """AC6: set(expected_ids) ⊆ set(actual_houses)"""
        resp = make_agent_response(json.dumps({"houses": ["HF_42", "HF_107", "HF_200"]}))
        ok, msg = ASSERTION_RULES["houses_match_subset"](resp, ["HF_42", "HF_107"])
        assert ok is True
        assert msg == ""

    def test_pass_exact_subset(self):
        resp = make_agent_response(json.dumps({"houses": ["HF_42", "HF_107"]}))
        ok, msg = ASSERTION_RULES["houses_match_subset"](resp, ["HF_42", "HF_107"])
        assert ok is True

    def test_fail_missing_id(self):
        resp = make_agent_response(json.dumps({"houses": ["HF_42"]}))
        ok, msg = ASSERTION_RULES["houses_match_subset"](resp, ["HF_42", "HF_107"])
        assert ok is False
        assert "HF_107" in msg

    def test_pass_empty_expected_with_non_empty_actual(self):
        """expected 为空列表时，只检查 actual 非空"""
        resp = make_agent_response(json.dumps({"houses": ["HF_42"]}))
        ok, msg = ASSERTION_RULES["houses_match_subset"](resp, [])
        assert ok is True

    def test_fail_no_houses_in_response(self):
        resp = make_agent_response("not json")
        ok, msg = ASSERTION_RULES["houses_match_subset"](resp, [])
        assert ok is False


# ── house_count_min ───────────────────────────────────────────────────────────

class TestHouseCountMin:
    def test_pass_meets_minimum(self):
        resp = make_agent_response(json.dumps({"houses": ["HF_1", "HF_2", "HF_3"]}))
        ok, msg = ASSERTION_RULES["house_count_min"](resp, 2)
        assert ok is True

    def test_pass_exactly_minimum(self):
        resp = make_agent_response(json.dumps({"houses": ["HF_1", "HF_2"]}))
        ok, msg = ASSERTION_RULES["house_count_min"](resp, 2)
        assert ok is True

    def test_fail_too_few(self):
        resp = make_agent_response(json.dumps({"houses": ["HF_1"]}))
        ok, msg = ASSERTION_RULES["house_count_min"](resp, 3)
        assert ok is False
        assert "3" in msg
        assert "1" in msg

    def test_invalid_expected_no_exception(self):
        """AC4: non-numeric expected must not raise, returns (False, ...)"""
        resp = make_agent_response(json.dumps({"houses": ["HF_1"]}))
        ok, msg = ASSERTION_RULES["house_count_min"](resp, "abc")
        assert ok is False
        assert "invalid" in msg


# ── status_success ────────────────────────────────────────────────────────────

class TestStatusSuccess:
    def test_pass(self):
        ok, msg = ASSERTION_RULES["status_success"]({"status": "success"}, True)
        assert ok is True
        assert msg == ""

    def test_fail_error_status(self):
        ok, msg = ASSERTION_RULES["status_success"]({"status": "error"}, True)
        assert ok is False
        assert "error" in msg

    def test_fail_missing_status(self):
        ok, msg = ASSERTION_RULES["status_success"]({}, True)
        assert ok is False


# ── tool_call_args（含 location 模糊等价）───────────────────────────────────────

class TestToolCallArgs:
    def _make_response(self, tool_name: str, args: dict) -> dict:
        return {
            "response": "ok",
            "status": "success",
            "tool_results": [{"tool_name": tool_name, "args": args}],
        }

    def test_pass_location_haidian_qu_fuzzy(self):
        """期望 ['海淀']，实际 ['海淀区'] → 模糊等价通过"""
        expect = {"tool": "update_preferences", "contains": {"location": ["海淀"]}}
        resp = self._make_response("update_preferences", {"location": ["海淀区"]})
        ok, msg = ASSERTION_RULES["tool_call_args"](resp, expect)
        assert ok is True, msg

    def test_pass_location_wangjing_shangquan_fuzzy(self):
        """期望 ['望京']，实际 ['望京商圈'] → 模糊等价通过"""
        expect = {"tool": "update_preferences", "contains": {"location": ["望京"]}}
        resp = self._make_response("update_preferences", {"location": ["望京商圈"]})
        ok, msg = ASSERTION_RULES["tool_call_args"](resp, expect)
        assert ok is True, msg

    def test_pass_location_exact_match(self):
        """精确匹配仍通过"""
        expect = {"tool": "update_preferences", "contains": {"location": ["海淀"]}}
        resp = self._make_response("update_preferences", {"location": ["海淀"]})
        ok, msg = ASSERTION_RULES["tool_call_args"](resp, expect)
        assert ok is True, msg

    def test_fail_location_mismatch(self):
        """期望 ['海淀']，实际 ['朝阳区'] → 失败"""
        expect = {"tool": "update_preferences", "contains": {"location": ["海淀"]}}
        resp = self._make_response("update_preferences", {"location": ["朝阳区"]})
        ok, msg = ASSERTION_RULES["tool_call_args"](resp, expect)
        assert ok is False
        assert "location" in msg


class TestLocationFuzzyHelpers:
    def test_strip_location_suffix(self):
        assert _strip_location_suffix("海淀区") == "海淀"
        assert _strip_location_suffix("望京商圈") == "望京"
        assert _strip_location_suffix("朝阳区") == "朝阳"
        assert _strip_location_suffix("国贸附近") == "国贸"

    def test_locations_equivalent(self):
        assert _locations_equivalent(["海淀"], ["海淀区"]) is True
        assert _locations_equivalent(["望京"], ["望京商圈"]) is True
        assert _locations_equivalent(["海淀"], ["朝阳区"]) is False


# ── check_assertions ──────────────────────────────────────────────────────────

def test_check_assertions_all_pass():
    case = make_case()
    expect = ExpectRules(has_response=True, status_success=True)
    response = {"response": "hi", "status": "success"}
    passed, reason = check_assertions(response, expect, case)
    assert passed is True
    assert reason == ""


def test_check_assertions_fail_on_first_failure():
    case = make_case()
    expect = ExpectRules(response_not_empty=True, status_success=True)
    response = {"response": "", "status": "success"}
    passed, reason = check_assertions(response, expect, case)
    assert passed is False
    assert "response_not_empty" in reason


def test_check_assertions_no_expect_rules_passes():
    case = make_case()
    expect = ExpectRules()
    response = {"response": "hi", "status": "success"}
    passed, reason = check_assertions(response, expect, case)
    assert passed is True
    assert reason == ""


def test_check_assertions_houses_match_exact_mode():
    """When houses_match set and houses_match_subset is None → exact match"""
    case = make_case()
    expect = ExpectRules(houses_match=["HF_42", "HF_107"])
    response = make_agent_response(json.dumps({"houses": ["HF_42", "HF_107"]}))
    passed, reason = check_assertions(response, expect, case)
    assert passed is True


def test_check_assertions_houses_match_subset_mode():
    """When houses_match_subset=True and houses_match=['HF_42'] → subset check"""
    case = make_case()
    expect = ExpectRules(houses_match=["HF_42"], houses_match_subset=True)
    response = make_agent_response(json.dumps({"houses": ["HF_42", "HF_107"]}))
    passed, reason = check_assertions(response, expect, case)
    assert passed is True


def test_check_assertions_tool_call_args_location_fuzzy():
    """tool_call_args 中 location 支持模糊等价：期望 ['海淀']，实际 ['海淀区'] 通过"""
    case = make_case()
    expect = ExpectRules(
        tool_call_args=ToolCallArgsExpect(
            tool="update_preferences",
            contains={"location": ["海淀"], "bedrooms": "2"},
        )
    )
    response = {
        "response": "ok",
        "status": "success",
        "tool_results": [
            {"tool_name": "update_preferences", "args": {"location": ["海淀区"], "bedrooms": "2"}}
        ],
    }
    passed, reason = check_assertions(response, expect, case)
    assert passed is True, reason


# ── send_message — AC2 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_success_ac2():
    """AC2: POST to {agent_base_url}/api/v1/chat with correct body"""
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "hello", "status": "success"}
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    body, err = await send_message(
        mock_client, "http://localhost:8191", "session-1", "127.0.0.1", "你好"
    )

    assert err is None
    assert body is not None
    assert body["status"] == "success"
    mock_client.post.assert_called_once_with(
        "http://localhost:8191/api/v1/chat",
        json={"model_ip": "127.0.0.1", "session_id": "session-1", "message": "你好"},
    )


@pytest.mark.asyncio
async def test_send_message_connect_error_ac8():
    """AC8: httpx.ConnectError → (None, 'Chat 不通: ...')"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    body, err = await send_message(
        mock_client, "http://localhost:8191", "session-1", "127.0.0.1", "你好"
    )

    assert body is None
    assert err is not None
    assert "Chat 不通" in err


@pytest.mark.asyncio
async def test_send_message_non_json_response():
    """Non-JSON response body should return error, not raise"""
    mock_response = MagicMock()
    mock_response.json.side_effect = ValueError("No JSON")
    mock_response.status_code = 502
    mock_response.text = "<html>Bad Gateway</html>"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    body, err = await send_message(
        mock_client, "http://localhost:8191", "session-1", "127.0.0.1", "你好"
    )

    assert body is None
    assert err is not None
    assert "非 JSON" in err


@pytest.mark.asyncio
async def test_send_message_timeout():
    """httpx.TimeoutException should return error, not raise"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(
        side_effect=httpx.ReadTimeout("read timed out")
    )

    body, err = await send_message(
        mock_client, "http://localhost:8191", "session-1", "127.0.0.1", "你好"
    )

    assert body is None
    assert err is not None
    assert "超时" in err


# ── run_single_case — AC1, AC7, AC8 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_single_case_sends_messages_in_order_ac1():
    """AC1: send_message called in order for each message; rounds == len(messages)"""
    config = make_config()
    case = make_case(
        messages=["你好", "帮我找房"],
        expect=ExpectRules(status_success=True),
    )
    token_counter = TokenCounter()
    agent_resp = {"response": "hi", "status": "success", "duration_ms": 100}
    mock_response = MagicMock()
    mock_response.json.return_value = agent_resp
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    result = await run_single_case(case, config, mock_client, token_counter)

    assert result.status == "PASS"
    assert result.rounds == 2
    assert mock_client.post.call_count == 2
    # Verify order: first call sends "你好", second sends "帮我找房"
    calls = mock_client.post.call_args_list
    assert calls[0].kwargs["json"]["message"] == "你好"
    assert calls[1].kwargs["json"]["message"] == "帮我找房"


@pytest.mark.asyncio
async def test_run_single_case_session_id_format_ac2():
    """AC2: session_id format = test-{case.id}-{uuid_hex8}"""
    config = make_config()
    case = make_case(id="my-case", messages=["hi"])
    token_counter = TokenCounter()
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "hi", "status": "success"}
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    await run_single_case(case, config, mock_client, token_counter)

    call_json = mock_client.post.call_args.kwargs["json"]
    session_id = call_json["session_id"]
    assert session_id.startswith("test-my-case-")
    parts = session_id.split("-")
    # Last part should be 8-char hex (uuid4 hex prefix)
    assert len(parts[-1]) == 8 and all(c in "0123456789abcdef" for c in parts[-1])


@pytest.mark.asyncio
async def test_run_single_case_connect_error_ac8():
    """AC8: ConnectError → CaseResult(status='ERROR'); loop continues (doesn't crash)"""
    config = make_config()
    case = make_case(messages=["你好"])
    token_counter = TokenCounter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    result = await run_single_case(case, config, mock_client, token_counter)

    assert result.status == "ERROR"
    assert result.failure_reason is not None
    assert "Chat 不通" in result.failure_reason


@pytest.mark.asyncio
async def test_run_single_case_timeout_ac7():
    """AC7: timeout → CaseResult(status='TIMEOUT', rounds=0, failure_reason='超时 Ns')"""
    config = make_config(timeout_per_case=1)
    case = make_case(messages=["你好"])
    token_counter = TokenCounter()

    async def slow_post(*args, **kwargs):
        await asyncio.sleep(5)
        return MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = slow_post

    result = await run_single_case(case, config, mock_client, token_counter)

    assert result.status == "TIMEOUT"
    assert result.rounds == 0
    assert result.failure_reason is not None
    assert "超时" in result.failure_reason
    assert "1" in result.failure_reason


@pytest.mark.asyncio
async def test_run_single_case_case_result_contains_rounds():
    """AC1: CaseResult.rounds equals number of messages sent"""
    config = make_config()
    case = make_case(messages=["a", "b", "c"])
    token_counter = TokenCounter()
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "x", "status": "success"}
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    result = await run_single_case(case, config, mock_client, token_counter)
    assert result.rounds == 3


# ── print_case_result — AC9, AC10 ────────────────────────────────────────────

def test_print_case_result_pass_ac9(capsys):
    """AC9: [idx/total] case_id ...... PASS  (Xs)"""
    result = CaseResult(
        case_id="test-001",
        case_type="Chat",
        status="PASS",
        duration_ms=1500,
        rounds=2,
    )
    print_case_result(1, 3, result)
    out = capsys.readouterr().out
    assert "[done 1/3]" in out or "[1/3]" in out
    assert "test-001" in out
    assert "PASS" in out
    assert "1.5s" in out


def test_print_case_result_fail_ac10(capsys):
    """AC10: [idx/total] case_id ...... FAIL  (Xs) + '       ✗ reason'"""
    result = CaseResult(
        case_id="test-002",
        case_type="Single",
        status="FAIL",
        duration_ms=2000,
        rounds=1,
        failure_reason="houses_match: expected ['HF_1'], got []",
    )
    print_case_result(2, 3, result)
    out = capsys.readouterr().out
    assert "[done 2/3]" in out or "[2/3]" in out
    assert "test-002" in out
    assert "FAIL" in out
    assert "2.0s" in out
    assert "✗" in out
    assert "houses_match" in out


def test_print_case_result_error_ac10(capsys):
    """AC10: ERROR status also shows FAIL + failure_reason"""
    result = CaseResult(
        case_id="test-003",
        case_type="Chat",
        status="ERROR",
        duration_ms=500,
        rounds=0,
        failure_reason="Chat 不通: connection refused",
    )
    print_case_result(1, 1, result)
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "✗" in out
    assert "Chat 不通" in out


def test_print_case_result_timeout_ac10(capsys):
    """AC10: TIMEOUT status shows FAIL + failure_reason"""
    result = CaseResult(
        case_id="test-004",
        case_type="Multi",
        status="TIMEOUT",
        duration_ms=60000,
        rounds=0,
        failure_reason="超时 60s",
    )
    print_case_result(3, 3, result)
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "✗" in out
    assert "超时" in out


# ── run_all_cases — Task 5 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_all_cases_resets_token_counter_per_case(monkeypatch):
    """Task 5.2: token_counter.reset() called before each case"""
    config = make_config()
    cases = [make_case(id="c1"), make_case(id="c2")]
    token_counter = TokenCounter()

    reset_calls = []
    original_reset = token_counter.reset

    def tracking_reset():
        reset_calls.append(1)
        original_reset()

    token_counter.reset = tracking_reset

    fake_result = CaseResult(
        case_id="stub", case_type="Chat", status="PASS", duration_ms=10, rounds=1
    )

    async def fake_run_single(case, cfg, client, tc):
        return CaseResult(
            case_id=case.id, case_type=case.type, status="PASS",
            duration_ms=10, rounds=1,
        )

    import runner as runner_module
    monkeypatch.setattr(runner_module, "run_single_case", fake_run_single)
    results = await run_all_cases(cases, config, token_counter)

    assert len(results) == 2
    assert len(reset_calls) == 2  # reset called once per case


@pytest.mark.asyncio
async def test_run_all_cases_returns_all_results(monkeypatch):
    """Task 5.1: returns list[CaseResult] with one entry per case"""
    config = make_config()
    cases = [make_case(id="c1"), make_case(id="c2"), make_case(id="c3")]
    token_counter = TokenCounter()

    async def fake_run_single(case, cfg, client, tc):
        return CaseResult(
            case_id=case.id, case_type=case.type, status="PASS",
            duration_ms=10, rounds=1,
        )

    import runner as runner_module
    monkeypatch.setattr(runner_module, "run_single_case", fake_run_single)
    results = await run_all_cases(cases, config, token_counter)

    assert len(results) == 3
    result_ids = [r.case_id for r in results]
    assert result_ids == ["c1", "c2", "c3"]


# ── generate_reports — Story 6.2 AC4, AC5 ────────────────────────────────────


def make_results(passed: int = 2, failed: int = 1) -> list[CaseResult]:
    results = []
    for i in range(passed):
        results.append(CaseResult(
            case_id=f"case_pass_{i}", case_type="Chat",
            status="PASS", duration_ms=1000 + i * 100, rounds=1,
        ))
    for i in range(failed):
        results.append(CaseResult(
            case_id=f"case_fail_{i}", case_type="Single",
            status="FAIL", duration_ms=2000 + i * 100, rounds=1,
            failure_reason=f"houses_match: expected ['HF_{i}'], got []",
        ))
    return results


class TestGenerateReports:
    """AC4 (JSON report) + AC5 (Markdown report)"""

    def test_json_file_created_at_correct_path(self, tmp_path):
        """AC4: JSON file saved to {report_dir}/report-{YYYY-MM-DD-HHmmss}.json"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=1, failed=0)
        json_path = generate_reports(results, config, total_duration_ms=1000)

        assert json_path.endswith(".json")
        assert os.path.exists(json_path)
        # File name matches pattern report-YYYY-MM-DD-HHmmss.json
        filename = os.path.basename(json_path)
        assert filename.startswith("report-")
        assert filename.endswith(".json")

    def test_json_file_has_meta_structure(self, tmp_path):
        """AC4: meta contains run_id, timestamp, agent_base_url, total_duration_ms"""
        config = make_config(
            report_dir=str(tmp_path),
            agent_base_url="http://localhost:8191",
        )
        results = make_results(passed=1, failed=0)
        json_path = generate_reports(results, config, total_duration_ms=5000)

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        meta = data["meta"]
        assert "run_id" in meta
        assert "timestamp" in meta
        assert meta["agent_base_url"] == "http://localhost:8191"
        assert meta["total_duration_ms"] == 5000

    def test_json_file_has_summary_structure(self, tmp_path):
        """AC4: summary contains total, passed, failed, pass_rate"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=2, failed=1)
        json_path = generate_reports(results, config, total_duration_ms=3000)

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        summary = data["summary"]
        assert summary["total"] == 3
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert "pass_rate" in summary
        assert "66" in summary["pass_rate"]  # 66.7%

    def test_json_file_has_cases_array(self, tmp_path):
        """AC4: cases array with full CaseResult data per case"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=1, failed=1)
        json_path = generate_reports(results, config, total_duration_ms=2000)

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "cases" in data
        assert len(data["cases"]) == 2
        # Each case entry should have core fields
        for case_entry in data["cases"]:
            assert "case_id" in case_entry
            assert "status" in case_entry
            assert "duration_ms" in case_entry

    def test_markdown_file_created(self, tmp_path):
        """AC5: Markdown file saved to {report_dir}/report-{timestamp}.md"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=1, failed=1)
        json_path = generate_reports(results, config, total_duration_ms=2000)

        # Corresponding .md file should also exist
        md_path = json_path.replace(".json", ".md")
        assert os.path.exists(md_path)

    def test_markdown_has_summary_table(self, tmp_path):
        """AC5: Markdown contains summary table with case_id, type, status, duration_ms, failure_reason"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=1, failed=1)
        json_path = generate_reports(results, config, total_duration_ms=2000)

        md_path = json_path.replace(".json", ".md")
        content = Path(md_path).read_text(encoding="utf-8")

        assert "case_id" in content
        assert "status" in content
        assert "duration_ms" in content
        assert "failure_reason" in content

    def test_markdown_has_totals_line(self, tmp_path):
        """AC5: Markdown contains N passed, M failed totals line"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=2, failed=1)
        json_path = generate_reports(results, config, total_duration_ms=3000)

        md_path = json_path.replace(".json", ".md")
        content = Path(md_path).read_text(encoding="utf-8")

        assert "2 passed" in content
        assert "1 failed" in content

    def test_report_dir_created_if_not_exists(self, tmp_path):
        """AC4: os.makedirs ensures report_dir is created"""
        new_dir = str(tmp_path / "nested" / "reports")
        config = make_config(report_dir=new_dir)
        results = make_results(passed=1, failed=0)

        json_path = generate_reports(results, config, total_duration_ms=500)

        assert os.path.exists(new_dir)
        assert os.path.exists(json_path)

    def test_returns_json_path_as_string(self, tmp_path):
        """generate_reports returns the JSON report file path (str)"""
        config = make_config(report_dir=str(tmp_path))
        results = make_results(passed=1, failed=0)

        result = generate_reports(results, config, total_duration_ms=500)

        assert isinstance(result, str)
        assert result.endswith(".json")
