"""Unit tests for main.py — parse_args (Story 6.2)"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

# parse_args lives in main.py; import it directly
sys.path.insert(0, ".")
from main import parse_args


class TestParseArgs:
    """AC7: --help shows --all, --case, --tag; AC2 and AC3 parsing"""

    def test_all_flag(self):
        """AC7 + AC1: --all sets args.all = True"""
        with patch("sys.argv", ["main.py", "--all"]):
            args = parse_args()
        assert args.all is True
        assert args.case is None
        assert args.tag is None

    def test_case_flag(self):
        """AC2: --case <id> sets args.case = id"""
        with patch("sys.argv", ["main.py", "--case", "chat_hello"]):
            args = parse_args()
        assert args.case == "chat_hello"
        assert args.all is False
        assert args.tag is None

    def test_tag_flag(self):
        """AC3: --tag <tag> sets args.tag = tag"""
        with patch("sys.argv", ["main.py", "--tag", "smoke"]):
            args = parse_args()
        assert args.tag == "smoke"
        assert args.all is False
        assert args.case is None

    def test_no_args_defaults(self):
        """No args → all defaults: all=False, case=None, tag=None"""
        with patch("sys.argv", ["main.py"]):
            args = parse_args()
        assert args.all is False
        assert args.case is None
        assert args.tag is None

    def test_help_output_contains_all_options(self, capsys):
        """AC7: --help shows all three options"""
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["main.py", "--help"]):
                parse_args()
        captured = capsys.readouterr()
        help_text = captured.out
        assert "--all" in help_text
        assert "--case" in help_text
        assert "--tag" in help_text
