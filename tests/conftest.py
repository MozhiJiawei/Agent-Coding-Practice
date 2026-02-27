"""
pytest conftest：全局测试环境配置。
- 预设 USER_ID 环境变量，避免 tools.py 模块级 KeyError
- autouse fixture 在每个测试前清空 sessions，保证测试隔离
"""
import os

os.environ.setdefault("USER_ID", "test-user-placeholder")

import pytest
import main as _main_module


@pytest.fixture(autouse=True)
def _clear_sessions():
    _main_module.sessions.clear()
    yield
    _main_module.sessions.clear()
