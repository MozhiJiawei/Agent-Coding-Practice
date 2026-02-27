"""
pytest conftest：在测试收集阶段之前预设必要的环境变量，
避免 tools.py 模块级 os.environ["USER_ID"] 在无环境变量时抛出 KeyError。
不修改任何生产代码。
"""
import os

os.environ.setdefault("USER_ID", "test-user-placeholder")
