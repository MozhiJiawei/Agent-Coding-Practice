"""
test_logger.py — Story 4.2 (AC: #1, #3, #4, #5, #8)
测试 logger.py 结构化 JSONL 文件日志行为
"""
import json
import time
import pytest
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Fixture：将 LOG_DIR 重定向到 tmp_path，确保测试隔离
# ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def temp_log_dir(tmp_path, monkeypatch):
    import logger
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger, "LOG_DIR", log_dir)
    return log_dir


# ─────────────────────────────────────────────────────────────
# AC#1: 基础字段与文件写入
# ─────────────────────────────────────────────────────────────

class TestLogEventFileOutput:
    """log_event 写入 JSONL 文件，字段齐全，格式正确"""

    def test_creates_log_file(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "session_abc", {"k": "v"})
        assert (temp_log_dir / "session_abc.jsonl").exists()

    def test_output_is_valid_json(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {"k": "v"})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert isinstance(data, dict)

    def test_has_ts_field_as_int(self, temp_log_dir):
        from logger import log_event
        before = int(time.time())
        log_event("TEST", "s1", {})
        after = int(time.time()) + 1
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert "ts" in data
        assert isinstance(data["ts"], int)
        assert before <= data["ts"] <= after

    def test_has_session_id_field(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "my-session-123", {})
        line = (temp_log_dir / "my-session-123.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["session_id"] == "my-session-123"

    def test_has_event_field(self, temp_log_dir):
        from logger import log_event
        log_event("MODEL_RESPONSE", "s1", {})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["event"] == "MODEL_RESPONSE"

    def test_has_details_field(self, temp_log_dir):
        from logger import log_event
        log_event("TOOL_CALL", "s1", {"tool_name": "search_houses"})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["details"]["tool_name"] == "search_houses"

    def test_ensure_ascii_false_preserves_chinese(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {"msg": "北京租房"})
        content = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8")
        assert "北京租房" in content

    def test_empty_details_dict(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["details"] == {}

    def test_stdout_output(self, temp_log_dir, capsys):
        """log_event 同时写入文件并打印到 stdout"""
        from logger import log_event
        log_event("TEST", "s1", {"k": "v"})
        captured = capsys.readouterr()
        assert "s1" in captured.out and "TEST" in captured.out and '"k": "v"' in captured.out

    def test_different_event_types_all_recorded(self, temp_log_dir):
        from logger import log_event
        for event in ["SESSION_START", "SESSION_INIT", "TOOL_CALL", "MODEL_RESPONSE", "ERROR"]:
            log_event(event, "s1", {})
        content = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8")
        lines = [l for l in content.strip().split("\n") if l]
        recorded_events = [json.loads(l)["event"] for l in lines]
        for event in ["SESSION_START", "SESSION_INIT", "TOOL_CALL", "MODEL_RESPONSE", "ERROR"]:
            assert event in recorded_events


# ─────────────────────────────────────────────────────────────
# AC#4: 自动创建 logs/ 目录
# ─────────────────────────────────────────────────────────────

class TestLogEventAutoCreateDir:
    def test_creates_logs_dir_if_not_exists(self, tmp_path, monkeypatch):
        import logger
        new_log_dir = tmp_path / "brand_new_logs"
        monkeypatch.setattr(logger, "LOG_DIR", new_log_dir)
        assert not new_log_dir.exists()
        from logger import log_event
        log_event("TEST", "s1", {})
        assert new_log_dir.exists()


# ─────────────────────────────────────────────────────────────
# AC#1: 追加写入（多次调用同一 session）
# ─────────────────────────────────────────────────────────────

class TestLogEventAppend:
    def test_multiple_calls_append_lines(self, temp_log_dir):
        from logger import log_event
        log_event("SESSION_START", "s1", {})
        log_event("MODEL_RESPONSE", "s1", {"finish_reason": "stop"})
        content = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8")
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 2

    def test_each_appended_line_is_valid_json(self, temp_log_dir):
        from logger import log_event
        for i in range(3):
            log_event("EVENT", "s1", {"i": i})
        content = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8")
        for line in content.strip().split("\n"):
            if line:
                data = json.loads(line)
                assert "ts" in data


# ─────────────────────────────────────────────────────────────
# AC#3: session 隔离（不同 session_id → 不同文件）
# ─────────────────────────────────────────────────────────────

class TestLogEventSessionIsolation:
    def test_different_sessions_create_different_files(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "session_A", {"data": "A"})
        log_event("TEST", "session_B", {"data": "B"})
        assert (temp_log_dir / "session_A.jsonl").exists()
        assert (temp_log_dir / "session_B.jsonl").exists()

    def test_session_files_not_cross_contaminated(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "session_A", {"data": "A_only"})
        log_event("TEST", "session_B", {"data": "B_only"})
        content_a = (temp_log_dir / "session_A.jsonl").read_text(encoding="utf-8")
        content_b = (temp_log_dir / "session_B.jsonl").read_text(encoding="utf-8")
        assert "A_only" in content_a
        assert "B_only" not in content_a
        assert "B_only" in content_b
        assert "A_only" not in content_b


# ─────────────────────────────────────────────────────────────
# AC#5: exc 参数 — 异常 traceback 注入
# ─────────────────────────────────────────────────────────────

class TestLogEventWithException:
    def test_no_exc_no_traceback_field(self, temp_log_dir):
        from logger import log_event
        log_event("ERROR", "s1", {"error": "something"})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert "traceback" not in data["details"]

    def test_with_exc_adds_traceback_to_details(self, temp_log_dir):
        from logger import log_event
        try:
            raise ValueError("test error")
        except ValueError as e:
            log_event("ERROR", "s1", {"error": "test"}, exc=e)
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert "traceback" in data["details"]
        assert "ValueError" in data["details"]["traceback"]

    def test_exc_does_not_mutate_original_dict(self, temp_log_dir):
        from logger import log_event
        original_details = {"error": "test"}
        try:
            raise RuntimeError("oops")
        except RuntimeError as e:
            log_event("ERROR", "s1", original_details, exc=e)
        assert "traceback" not in original_details

    def test_exc_none_is_valid_default(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {}, exc=None)
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert "traceback" not in data["details"]

    def test_exc_traceback_contains_stack_info(self, temp_log_dir):
        from logger import log_event
        try:
            raise RuntimeError("stack trace test")
        except RuntimeError as e:
            log_event("ERROR", "s1", {}, exc=e)
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        tb = data["details"]["traceback"]
        assert isinstance(tb, str)
        assert len(tb) > 0

    def test_exc_outside_except_block_still_captures_traceback(self, temp_log_dir):
        """format_exception 从异常对象提取 traceback，不依赖 except 上下文"""
        from logger import log_event
        saved_exc = None
        try:
            raise ValueError("deferred error")
        except ValueError as e:
            saved_exc = e
        log_event("ERROR", "s1", {}, exc=saved_exc)
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert "traceback" in data["details"]
        assert "ValueError" in data["details"]["traceback"]
        assert "deferred error" in data["details"]["traceback"]


# ─────────────────────────────────────────────────────────────
# AC#6: LLM_REQUEST 事件格式（由 agent.py 调用，此处验证字段规范）
# ─────────────────────────────────────────────────────────────

class TestLLMRequestEventFormat:
    """验证 log_event 可正确记录 LLM_REQUEST 事件所需字段"""

    def test_llm_request_event_fields(self, temp_log_dir):
        from logger import log_event
        log_event("LLM_REQUEST", "s1", {"iteration": 1, "message_count": 3})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["event"] == "LLM_REQUEST"
        assert data["details"]["iteration"] == 1
        assert data["details"]["message_count"] == 3
