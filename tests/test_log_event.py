"""
test_log_event.py — Task 1 (AC: 6)
测试 log_event() 结构化日志输出
"""
import json
import time
import pytest

from agent import log_event


class TestLogEventOutputFormat:
    """log_event 输出合法 JSON 行，字段齐全"""

    def test_output_is_valid_json(self, capsys):
        log_event("TEST", "s1", {"k": "v"})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert isinstance(data, dict)

    def test_output_contains_timestamp_field(self, capsys):
        log_event("TEST", "s1", {"k": "v"})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert "timestamp" in data

    def test_timestamp_is_integer(self, capsys):
        log_event("TEST", "s1", {"k": "v"})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert isinstance(data["timestamp"], int)

    def test_timestamp_is_recent_unix_time(self, capsys):
        before = int(time.time())
        log_event("TEST", "s1", {"k": "v"})
        after = int(time.time())
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert before <= data["timestamp"] <= after + 1

    def test_output_contains_session_id(self, capsys):
        log_event("TEST", "my-session-123", {"k": "v"})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["session_id"] == "my-session-123"

    def test_output_contains_event_type(self, capsys):
        log_event("MODEL_RESPONSE", "s1", {})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["event_type"] == "MODEL_RESPONSE"

    def test_output_contains_details(self, capsys):
        log_event("TOOL_CALL", "s1", {"tool_name": "search_houses", "args": "..."})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["details"]["tool_name"] == "search_houses"

    def test_ensure_ascii_false_preserves_chinese(self, capsys):
        """中文字符不应被转义为 \\uXXXX"""
        log_event("TEST", "s1", {"msg": "北京租房"})
        captured = capsys.readouterr()
        assert "北京租房" in captured.out

    def test_empty_details_dict(self, capsys):
        log_event("TEST", "s1", {})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["details"] == {}

    def test_empty_session_id(self, capsys):
        log_event("TEST", "", {"k": "v"})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["session_id"] == ""

    def test_different_event_types(self, capsys):
        for event in ["MODEL_RESPONSE", "TOOL_CALL", "ERROR", "SESSION_START"]:
            log_event(event, "s1", {})
            captured = capsys.readouterr()
            data = json.loads(captured.out.strip())
            assert data["event_type"] == event
