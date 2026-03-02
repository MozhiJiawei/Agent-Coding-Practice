"""Pydantic 数据模型 + YAML 配置加载 — test-simulator 核心配置层"""
from __future__ import annotations

# 1. 标准库导入
from typing import Literal

# 2. 第三方库导入
import yaml
from pydantic import BaseModel

# 3. Pydantic 数据模型（按依赖顺序）


class SimulatorConfig(BaseModel):
    agent_base_url: str = "http://localhost:8191"
    model_proxy_port: int = 8888
    llm_proxy_url: str                              # 必填，无默认值
    llm_model: str = "Qwen/Qwen3-32B"               # 转发给 LLM 的模型名
    llm_api_key: str | None = None                  # 可选：若不设置则从 api_key_file 读取
    api_key_file: str = "../.api_key"               # API Key 文件路径（相对于 test-simulator/ 运行目录）
    mock_rental_port: int = 8080
    fixture_file: str = "mock_data/default.yaml"
    test_user_id: str                               # 必填，无默认值
    test_cases_file: str = "test_cases.yaml"
    timeout_per_case: int = 60
    report_dir: str = "_bmad-output/test-reports"
    max_concurrency: int = 15


class ToolCallArgsExpect(BaseModel):
    tool: str       # 工具名，如 "update_preferences"
    contains: dict  # 预期参数子集（精确匹配每个 key 的 value）


class ExpectRules(BaseModel):
    has_response: bool | None = None
    response_not_empty: bool | None = None
    response_json_valid: bool | None = None
    houses_match: list[str] | None = None           # 精确匹配模式
    houses_match_subset: bool | None = None         # 子集匹配模式
    house_count_min: int | None = None              # 数量下限模式
    status_success: bool | None = None
    round_count: int | None = None
    tool_call_args: ToolCallArgsExpect | None = None  # 验证工具提参
    no_tool_call: bool | None = None                  # 验证未调用任何工具


class RoundExpect(BaseModel):
    round: int          # 1-based：第几轮用户消息
    expect: ExpectRules


class TestCase(BaseModel):
    id: str
    type: Literal["Chat", "Single", "Multi"]
    messages: list[str]
    expect: ExpectRules | None = None
    tags: list[str] = []
    fixture_file: str | None = None   # 可选：为本用例加载指定 mock_data fixture
    round_expects: list[RoundExpect] = []  # 每轮独立断言


TestCase.__test__ = False  # prevent pytest collection warning


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CaseResult(BaseModel):
    case_id: str
    case_type: str                                  # "Chat" | "Single" | "Multi"
    status: Literal["PASS", "FAIL", "ERROR", "TIMEOUT"]
    duration_ms: int
    rounds: int
    failure_reason: str | None = None
    actual_response: str | None = None
    token_usage: TokenUsage | None = None


# 4. TokenCounter 辅助类

class TokenCounter:
    """共享 token 累计器，由 main.py 创建，通过 app.state 注入 model_proxy"""

    def __init__(self) -> None:
        self._prompt = 0
        self._completion = 0
        self._total = 0

    def add(self, usage: dict) -> None:
        """从 LLM 响应 usage 字段累加 token 数"""
        self._prompt += usage.get("prompt_tokens", 0)
        self._completion += usage.get("completion_tokens", 0)
        self._total += usage.get("total_tokens", 0)

    def reset(self) -> None:
        """每个 test case 执行前重置"""
        self._prompt = self._completion = self._total = 0

    def to_token_usage(self) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self._prompt,
            completion_tokens=self._completion,
            total_tokens=self._total,
        )

    def __repr__(self) -> str:
        return f"TokenCounter(prompt={self._prompt}, completion={self._completion}, total={self._total})"


# 5. YAML 加载函数

def load_config(path: str) -> SimulatorConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping with SimulatorConfig fields, got {type(data).__name__}")
    return SimulatorConfig(**data)


def load_test_cases(path: str) -> list[TestCase]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_cases = data.get("test_cases", [])
    return [TestCase(**c) for c in raw_cases]


_LANDMARK_REQUIRED = {"id", "name", "category", "district", "longitude", "latitude"}
_HOUSE_REQUIRED = {
    "house_id", "community", "district", "area", "price", "status",
    "longitude", "latitude", "bedrooms", "rental_type", "decoration",
    "orientation", "elevator",
}


def load_fixtures(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    landmarks = data.get("landmarks", [])
    houses = data.get("houses", [])
    if not isinstance(landmarks, list) or not isinstance(houses, list):
        raise ValueError(f"{path}: expected 'landmarks' and 'houses' lists")
    for i, lm in enumerate(landmarks):
        missing = _LANDMARK_REQUIRED - set(lm.keys())
        if missing:
            raise ValueError(f"{path}: landmarks[{i}] missing fields: {missing}")
    for i, h in enumerate(houses):
        missing = _HOUSE_REQUIRED - set(h.keys())
        if missing:
            raise ValueError(f"{path}: houses[{i}] missing fields: {missing}")
    return {"landmarks": landmarks, "houses": houses}
