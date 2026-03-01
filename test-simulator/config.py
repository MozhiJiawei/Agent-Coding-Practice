"""Pydantic 数据模型 + YAML 配置加载 — test-simulator 核心配置层"""
from __future__ import annotations

# 1. 标准库导入
from typing import Literal

# 2. 第三方库导入
import yaml
from pydantic import BaseModel, model_validator

# 3. Pydantic 数据模型（按依赖顺序）


class SimulatorConfig(BaseModel):
    agent_base_url: str = "http://localhost:8191"
    model_proxy_port: int = 8888
    llm_proxy_url: str                              # 必填，无默认值
    llm_api_key: str | None = None                  # 可选：若不设置则从 api_key_file 读取
    api_key_file: str = "../.api_key"               # API Key 文件路径（相对于 test-simulator/ 运行目录）
    mock_rental_port: int = 8080
    rental_mode: Literal["mock", "passthrough"] = "mock"
    rental_passthrough_url: str = "http://7.225.29.223:8080"
    test_user_id: str                               # 必填，无默认值
    test_cases_file: str = "test_cases.yaml"
    mock_data_file: str = "mock_data/default.yaml"
    timeout_per_case: int = 60
    report_dir: str = "_bmad-output/test-reports"


class ExpectRules(BaseModel):
    has_response: bool | None = None
    response_not_empty: bool | None = None
    response_json_valid: bool | None = None
    houses_match: list[str] | None = None           # 精确匹配模式
    houses_match_subset: bool | None = None         # 子集匹配模式
    house_count_min: int | None = None              # 数量下限模式
    status_success: bool | None = None
    round_count: int | None = None


class TestCase(BaseModel):
    id: str
    type: Literal["Chat", "Single", "Multi"]
    messages: list[str]
    expect: ExpectRules | None = None
    tags: list[str] = []


class MockRule(BaseModel):
    path: str
    method: Literal["GET", "POST", "PUT", "DELETE"]
    params_match: dict[str, str] | None = None
    response: dict

    @model_validator(mode="after")
    def _check_response_format(self):
        r = self.response
        if "code" not in r or "message" not in r:
            raise ValueError(
                "response must include 'code' and 'message' keys "
                '(real API format: {"code": 0, "message": "success", "data": {...}})'
            )
        return self


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


def load_mock_data(path: str) -> list[MockRule]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_rules = data.get("mock_responses", [])
    return [MockRule(**r) for r in raw_rules]
