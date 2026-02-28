"""
test_log_event.py — Story 4.2 (AC: #1, #2)
验证 log_event() 从 logger 模块导入，写入 JSONL 文件（非 stdout）
"""
import json
import time
import pytest


@pytest.fixture(autouse=True)
def temp_log_dir(tmp_path, monkeypatch):
    import logger
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger, "LOG_DIR", log_dir)
    return log_dir


class TestLogEventOutputFormat:
    """log_event 输出合法 JSONL，字段使用新规范（ts / event）"""

    def test_output_is_valid_json(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {"k": "v"})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert isinstance(data, dict)

    def test_output_contains_ts_field(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {"k": "v"})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert "ts" in data

    def test_ts_is_integer(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "s1", {"k": "v"})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert isinstance(data["ts"], int)

    def test_ts_is_recent_unix_time(self, temp_log_dir):
        from logger import log_event
        before = int(time.time())
        log_event("TEST", "s1", {"k": "v"})
        after = int(time.time())
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert before <= data["ts"] <= after + 1

    def test_output_contains_session_id(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "my-session-123", {"k": "v"})
        line = (temp_log_dir / "my-session-123.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["session_id"] == "my-session-123"

    def test_output_contains_event_field(self, temp_log_dir):
        from logger import log_event
        log_event("MODEL_RESPONSE", "s1", {})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["event"] == "MODEL_RESPONSE"

    def test_output_contains_details(self, temp_log_dir):
        from logger import log_event
        log_event("TOOL_CALL", "s1", {"tool_name": "search_houses", "args": "..."})
        line = (temp_log_dir / "s1.jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["details"]["tool_name"] == "search_houses"

    def test_ensure_ascii_false_preserves_chinese(self, temp_log_dir):
        """中文字符不应被转义为 \\uXXXX"""
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

    def test_empty_session_id(self, temp_log_dir):
        from logger import log_event
        log_event("TEST", "", {"k": "v"})
        line = (temp_log_dir / ".jsonl").read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["session_id"] == ""

    def test_different_event_types(self, temp_log_dir):
        from logger import log_event
        for event in ["MODEL_RESPONSE", "TOOL_CALL", "ERROR", "SESSION_START"]:
            log_event(event, event, {})
            line = (temp_log_dir / f"{event}.jsonl").read_text(encoding="utf-8").strip()
            data = json.loads(line)
            assert data["event"] == event
