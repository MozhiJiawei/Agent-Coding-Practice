# Story 5.1: 项目脚手架与配置系统

Status: done

## Story

As a developer (LJW),
I want a project scaffold with a complete typed configuration system,
so that I can define simulator settings, test cases, and mock data in validated YAML files with clear structure, enabling all other simulator components to load their configuration reliably.

## Acceptance Criteria

1. **Given** a target workspace directory,
   **When** the project is initialized (files created and `pip install` run),
   **Then** the following structure exists and the virtual environment has all required dependencies (`fastapi`, `uvicorn[standard]`, `httpx`, `pyyaml`, `pydantic`):
   ```
   test-simulator/
   ├── main.py
   ├── config.py
   ├── runner.py
   ├── model_proxy.py
   ├── mock_rental.py
   ├── requirements.txt
   ├── config.yaml
   ├── test_cases.yaml
   └── mock_data/
       └── default.yaml
   ```

2. **Given** a valid `config.yaml` with all required fields (`agent_base_url`, `model_proxy_port`, `llm_proxy_url`, `llm_api_key`, `mock_rental_port`, `rental_mode`, `rental_passthrough_url`, `test_user_id`, `test_cases_file`, `mock_data_file`, `timeout_per_case`, `report_dir`),
   **When** `load_config(path)` is called in `config.py`,
   **Then** a `SimulatorConfig` Pydantic model is returned with all fields correctly typed and validated (string, int, enum for `rental_mode: mock|passthrough`)

3. **Given** a valid `test_cases.yaml` containing a list of test cases,
   **When** `load_test_cases(path)` is called,
   **Then** a `list[TestCase]` is returned where each `TestCase` has `id: str`, `type: str` (Chat/Single/Multi), `messages: list[str]`, and optional `expect: ExpectRules` and `tags: list[str]`

4. **Given** a valid `mock_data/default.yaml` with `mock_responses` list,
   **When** `load_mock_data(path)` is called,
   **Then** a `list[MockRule]` is returned where each `MockRule` has `path: str`, `method: str`, optional `params_match: dict`, and `response: dict`

5. **Given** a `config.yaml` or `test_cases.yaml` with a missing required field or wrong type,
   **When** any load function is called,
   **Then** a clear `ValidationError` or `ValueError` is raised with the field name and expected type indicated in the message

6. **Given** the Pydantic models `CaseResult` and `TokenUsage` defined in `config.py`,
   **When** inspected,
   **Then** `CaseResult` has fields: `case_id: str`, `case_type: str`, `status: str` (PASS/FAIL/ERROR/TIMEOUT), `duration_ms: int`, `rounds: int`, `failure_reason: str | None`, `actual_response: str | None`, `token_usage: TokenUsage | None`; and `TokenUsage` has `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`

## Tasks / Subtasks

- [x] Task 1: 创建项目目录结构与骨架文件 (AC: 1)
  - [x] 在项目根目录下创建 `test-simulator/` 子目录
  - [x] 创建 5 个 Python 骨架文件：`main.py`、`config.py`、`runner.py`、`model_proxy.py`、`mock_rental.py`（各含 import 骨架，不含业务逻辑）
  - [x] 创建 `requirements.txt`（含 5 个依赖：`fastapi`、`uvicorn[standard]`、`httpx`、`pyyaml`、`pydantic`）
  - [x] 创建 `mock_data/` 子目录和占位 `mock_data/default.yaml`

- [x] Task 2: 实现 `config.py` Pydantic 模型层 (AC: 2, 3, 4, 5, 6)
  - [x] 实现 `SimulatorConfig` 模型（12 个字段，含 `rental_mode` 枚举 `mock|passthrough`）
  - [x] 实现 `ExpectRules` 模型（可选字段：`has_response`、`response_not_empty`、`response_json_valid`、`houses_match`、`houses_match_subset`、`house_count_min`、`status_success`、`round_count`）
  - [x] 实现 `TestCase` 模型（`id`、`type`、`messages`、可选 `expect`、可选 `tags`）
  - [x] 实现 `MockRule` 模型（`path`、`method`、可选 `params_match`、`response`）
  - [x] 实现 `TokenUsage` 模型（`prompt_tokens`、`completion_tokens`、`total_tokens`，均默认 0）
  - [x] 实现 `CaseResult` 模型（`case_id`、`case_type`、`status`、`duration_ms`、`rounds`、可选 `failure_reason`、可选 `actual_response`、可选 `token_usage`）
  - [x] 实现 `TokenCounter` 辅助类（`add(usage: dict)`、`reset()`、`to_token_usage() -> TokenUsage`）
  - [x] 实现 `load_config(path: str) -> SimulatorConfig`
  - [x] 实现 `load_test_cases(path: str) -> list[TestCase]`
  - [x] 实现 `load_mock_data(path: str) -> list[MockRule]`

- [x] Task 3: 创建配置文件模板与占位内容 (AC: 2, 3, 4)
  - [x] 创建 `config.yaml`（含全部 12 个字段，每字段有行内中文注释说明用途/格式/默认值）
  - [x] 创建 `test_cases.yaml`（占位内容，后续 Story 5.3 完善）
  - [x] 创建 `mock_data/default.yaml`（占位内容，后续 Story 5.3 完善）

- [x] Task 4: 验证 (AC: 1, 5)
  - [x] 验证 `pip install -r requirements.txt` 成功（在 Windows PowerShell + `.venv` 环境）
  - [x] 验证 `python -c "from config import load_config, load_test_cases, load_mock_data"` 无报错
  - [x] 验证用 `config.yaml` 调用 `load_config()` 返回 `SimulatorConfig` 实例
  - [x] 验证缺少必填字段时抛出明确的 `ValidationError`

## Dev Notes

### 🚨 关键约束（必须严格遵守）

**项目位置：** 在当前主项目根目录（`d:\Git_Repo\AI Agent Coding\`）下创建 `test-simulator/` 子目录，不要在主项目之外创建。

**文件结构（只能这 9 个文件/目录，不得多也不得少）：**
```
test-simulator/
├── main.py              ← CLI 入口 + asyncio 服务编排（本 Story 仅骨架）
├── config.py            ← Pydantic 模型 + YAML 加载（本 Story 核心实现）
├── runner.py            ← Test Runner（本 Story 仅骨架）
├── model_proxy.py       ← Model Proxy FastAPI 应用（本 Story 仅骨架）
├── mock_rental.py       ← Mock 租房 API FastAPI 应用（本 Story 仅骨架）
├── requirements.txt     ← 依赖声明
├── config.yaml          ← 全局配置文件（本 Story 创建完整模板）
├── test_cases.yaml      ← 测试用例（本 Story 创建占位，Story 5.3 完善）
└── mock_data/
    └── default.yaml     ← Mock 数据（本 Story 创建占位，Story 5.3 完善）
```

**单向导入链（禁止循环依赖）：**
```
main.py → runner.py → config.py
main.py → model_proxy.py → config.py
main.py → mock_rental.py → config.py
```
本 Story 中，`config.py` 是独立模块（不导入其他同级文件）。

### `config.py` 完整实现规范

**文件内部结构顺序（必须按此顺序）：**
```python
# 1. 标准库导入
# 2. 第三方库导入（pydantic, yaml）
# 3. Pydantic 数据模型（按依赖顺序）
# 4. TokenCounter 辅助类
# 5. YAML 加载函数（load_config, load_test_cases, load_mock_data）
```

**`SimulatorConfig` 完整字段规范：**
```python
class SimulatorConfig(BaseModel):
    agent_base_url: str = "http://localhost:8191"
    model_proxy_port: int = 8888
    llm_proxy_url: str                    # 必填，无默认值
    llm_api_key: str                      # 必填，无默认值
    mock_rental_port: int = 8080
    rental_mode: Literal["mock", "passthrough"] = "mock"
    rental_passthrough_url: str = "http://7.225.29.223:8080"
    test_user_id: str                     # 必填，无默认值
    test_cases_file: str = "test_cases.yaml"
    mock_data_file: str = "mock_data/default.yaml"
    timeout_per_case: int = 60
    report_dir: str = "_bmad-output/test-reports"
```

**`ExpectRules` 完整字段规范（全部可选）：**
```python
class ExpectRules(BaseModel):
    has_response: bool | None = None
    response_not_empty: bool | None = None
    response_json_valid: bool | None = None
    houses_match: list[str] | None = None       # 精确匹配模式
    houses_match_subset: bool | None = None     # 子集匹配模式
    house_count_min: int | None = None          # 数量下限模式
    status_success: bool | None = None
    round_count: int | None = None
```

**`TestCase` 完整字段规范：**
```python
class TestCase(BaseModel):
    id: str
    type: str                              # "Chat" | "Single" | "Multi"
    messages: list[str]
    expect: ExpectRules | None = None
    tags: list[str] = []
```

**`MockRule` 完整字段规范：**
```python
class MockRule(BaseModel):
    path: str
    method: str                            # "GET" | "POST" | "PUT" | "DELETE"
    params_match: dict[str, str] | None = None
    response: dict                         # 原样返回的 JSON 响应体
```

**`TokenUsage` 和 `CaseResult` 规范：**
```python
class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class CaseResult(BaseModel):
    case_id: str
    case_type: str                         # "Chat" | "Single" | "Multi"
    status: str                            # "PASS" | "FAIL" | "ERROR" | "TIMEOUT"
    duration_ms: int
    rounds: int
    failure_reason: str | None = None
    actual_response: str | None = None
    token_usage: TokenUsage | None = None
```

**`TokenCounter` 辅助类规范：**
```python
class TokenCounter:
    """共享 token 累计器，由 main.py 创建，通过 app.state 注入 model_proxy"""
    def __init__(self):
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
            total_tokens=self._total
        )
```

**YAML 加载函数规范：**
```python
def load_config(path: str) -> SimulatorConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return SimulatorConfig(**data)   # ValidationError 自动向上抛出

def load_test_cases(path: str) -> list[TestCase]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    raw_cases = data.get("test_cases", [])
    return [TestCase(**c) for c in raw_cases]

def load_mock_data(path: str) -> list[MockRule]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    raw_rules = data.get("mock_responses", [])
    return [MockRule(**r) for r in raw_rules]
```

### `config.yaml` 模板规范（含行内注释）

每个字段必须有行内注释，说明用途/格式/默认值：
```yaml
# Test Simulator 全局配置文件
# 修改 llm_proxy_url 和 llm_api_key 后即可运行

agent_base_url: "http://localhost:8191"     # Agent 服务地址（默认 8191）
model_proxy_port: 8888                      # Model Proxy 监听端口（默认 8888）
llm_proxy_url: "https://your-llm-proxy/v1/chat/completions"  # 必填：外部 LLM 代理完整 URL
llm_api_key: "your-api-key"                 # 必填：LLM API Key（传递为 Authorization Bearer）
mock_rental_port: 8080                      # Mock 租房 API 监听端口（默认 8080）
rental_mode: "mock"                         # mock | passthrough — mock 返回预定义 JSON，passthrough 转发真实 API
rental_passthrough_url: "http://7.225.29.223:8080"  # 透传模式下的真实租房 API 地址
test_user_id: "your-employee-id"            # 必填：X-User-ID 请求头值（透传模式使用）
test_cases_file: "test_cases.yaml"          # 测试用例文件路径（相对于 test-simulator/ 目录）
mock_data_file: "mock_data/default.yaml"    # Mock 数据文件路径（相对于 test-simulator/ 目录）
timeout_per_case: 60                        # 单用例超时秒数（超时判 TIMEOUT，默认 60）
report_dir: "_bmad-output/test-reports"     # 报告输出目录（相对于项目根目录，自动创建）
```

### 骨架文件规范（非 config.py 文件）

本 Story 中 `main.py`、`runner.py`、`model_proxy.py`、`mock_rental.py` 仅需包含：
1. 必要的 import 声明（下一 Story 需要的依赖）
2. 文件顶部注释（说明该文件职责）
3. 不包含任何业务逻辑（留给后续 Story 实现）

**`main.py` 骨架示例：**
```python
"""CLI 入口 + asyncio 服务编排 + 生命周期管理"""
import asyncio
import argparse
from config import load_config, load_test_cases, load_mock_data, TokenCounter

# TODO: Story 6.2 实现 main() 和 CLI 逻辑
```

**`runner.py` 骨架示例：**
```python
"""Test Runner — Chat Client + 断言引擎 + 报告生成"""
import asyncio
import httpx
from config import SimulatorConfig, TestCase, CaseResult, TokenCounter, TokenUsage

# TODO: Story 6.1 实现 ASSERTION_RULES 和 run_all_cases()
```

**`model_proxy.py` 骨架示例：**
```python
"""Model Proxy FastAPI 应用 — 转发 LLM 请求并截取 token 统计"""
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from config import SimulatorConfig, TokenCounter

# TODO: Story 5.2 实现 create_model_proxy_app()
```

**`mock_rental.py` 骨架示例：**
```python
"""Mock 租房 API FastAPI 应用 — 提供 15 个租房 API 端点的 Mock/透传服务"""
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from config import SimulatorConfig, MockRule

# TODO: Story 5.2 实现 create_mock_rental_app()
```

### 命名规范（全局强制）

| 类别 | 规范 | 示例 |
|------|------|------|
| 函数/变量 | `snake_case` | `load_config`, `case_result` |
| 模块级常量 | `ALL_CAPS_SNAKE` | `ASSERTION_RULES`, `DEFAULT_TIMEOUT` |
| Pydantic 模型类 | `PascalCase` | `SimulatorConfig`, `TestCase`, `CaseResult` |
| 文件名 | `snake_case.py` | `config.py`, `mock_rental.py` |
| YAML 字段 | `snake_case` | `agent_base_url`, `test_cases_file` |
| 测试用例 ID | `snake_case` | `chat_hello`, `single_haidian_2br` |

### 技术栈

| 库 | 版本要求 | 用途 |
|----|----------|------|
| `fastapi` | latest stable | Mock Rental API + Model Proxy HTTP 服务 |
| `uvicorn[standard]` | latest stable | ASGI 服务器（程序化启动，不用 CLI） |
| `httpx` | latest stable | 异步 HTTP 客户端（Agent Chat + LLM 转发 + 透传） |
| `pyyaml` | latest stable | YAML 配置文件加载 |
| `pydantic` | v2（latest） | 配置/用例模型验证 |
| Python | 3.11+ | 全异步（asyncio + async/await） |

**注意：** 使用 `from __future__ import annotations` 或 Python 3.10+ 原生语法（`str | None`），Pydantic v2 完全支持。

### 反模式（严禁）

- ❌ 在 `config.py` 中包含 HTTP 服务逻辑或 FastAPI 路由
- ❌ 在 `config.py` 中使用全局可变状态（`TokenCounter` 实例由 `main.py` 创建后注入）
- ❌ 使用 `yaml.load()` 而不是 `yaml.safe_load()`（安全风险）
- ❌ 在加载函数中捕获 `ValidationError` 后静默处理（必须向上抛出）
- ❌ `MockRule.response` 使用自定义 JSON 结构（必须与真实租房 API 格式一致：`{"code": 0, "message": "success", "data": {...}}`）

### 与主项目的关系

test-simulator 是主项目的 **子目录**，位于 `d:\Git_Repo\AI Agent Coding\test-simulator\` 下，与主项目共用依赖管理（根目录 `requirements.txt`）。它不导入主项目任何 Python 模块，主项目的 `main.py`/`agent.py`/`tools.py` 等文件不需要修改。

### Git 最近提交参考

最近相关提交（供了解当前开发状态）：
- `4e50815` feat(test-simulator): add Epics and Stories breakdown（当前处于规划完成阶段）
- `ad57954` feat: 新增测试仿真器 PRD 与架构文档
- `629f466` fix(tools): 修复 X-User-ID 包含中文时的 ASCII 编码错误（主项目工具层已实现）

### Project Structure Notes

- `test-simulator/` 目录放在 `d:\Git_Repo\AI Agent Coding\` 根目录下
- `config.yaml` 中 `report_dir` 路径相对于 `test-simulator/` 运行时的工作目录，建议使用相对路径
- `requirements.txt` 使用 `pip freeze` 锁定具体版本号（在 `.venv` 环境中执行）

### References

- Epic 定义：[Source: `_bmad-output/planning-artifacts/epics-test-simulator.md` — Epic 1, Story 1.1]
- 架构约束：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — Core Architectural Decisions / Data Architecture]
- 模块边界：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — Structure Patterns / 模块职责边界]
- 命名规范：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — Naming Patterns]
- 文件内部结构：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — File Organization Patterns / config.py 内部结构]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor Agent, 2026-02-28)

### Debug Log References

无需调试，所有验证一次通过。

### Completion Notes List

- **Task 1**: 创建 `test-simulator/` 目录 + `mock_data/` 子目录，编写 4 个骨架文件（main/runner/model_proxy/mock_rental）含正确 import，`requirements.txt` 初始含 5 个包后由 pip freeze 锁定为精确版本。
- **Task 2**: 完整实现 `config.py`，按规范顺序排布：6 个 Pydantic 模型（SimulatorConfig/ExpectRules/TestCase/MockRule/TokenUsage/CaseResult）+ TokenCounter 类 + 3 个 YAML 加载函数。全部使用 `Literal["mock", "passthrough"]` 枚举、`str | None` 原生联合类型、`yaml.safe_load()`，不使用全局可变状态。
- **Task 3**: 创建 `config.yaml`（12 字段均含行内中文注释）、`test_cases.yaml`（占位空列表）、`mock_data/default.yaml`（占位空列表）。
- **Task 4**: 在 `.venv` 环境中验证：pip install 成功（Pydantic 2.12.5、FastAPI 0.134.0 等）、模块导入无报错、`load_config()` 返回 `SimulatorConfig` 实例（AC2✅）、`load_test_cases/load_mock_data` 返回空列表（AC3/4✅）、缺 3 个必填字段时 `ValidationError` 精确报告字段名（AC5✅）、`CaseResult`/`TokenUsage`/`TokenCounter` 字段完整正确（AC6✅）。
- requirements.txt 最终使用 `pip freeze` 锁定 22 个精确版本（含传递依赖），确保可复现安装。

### File List

- `test-simulator/config.py` ← 本 Story 核心新建文件
- `test-simulator/main.py` ← 骨架新建
- `test-simulator/runner.py` ← 骨架新建
- `test-simulator/model_proxy.py` ← 骨架新建
- `test-simulator/mock_rental.py` ← 骨架新建
- `test-simulator/requirements.txt` ← 新建（pip freeze 锁定版本）
- `test-simulator/config.yaml` ← 新建（含行内中文注释模板）
- `test-simulator/test_cases.yaml` ← 占位新建
- `test-simulator/mock_data/default.yaml` ← 占位新建
- `requirements.txt` ← 根目录，新增 pyyaml 依赖（共用依赖管理）

### Change Log

- 2026-02-28: Story 5.1 实现完成。创建 test-simulator/ 子项目脚手架，实现完整 config.py Pydantic 模型层（6模型+1辅助类+3加载函数），所有 AC1-AC6 验证通过，状态更新为 review。
- 2026-02-28: Code Review 修复。(1) load_config/load_test_cases/load_mock_data 增加空 YAML null guard，确保 AC5 清晰错误信息；(2) TestCase.type → Literal["Chat","Single","Multi"]；(3) MockRule.method → Literal["GET","POST","PUT","DELETE"]；(4) CaseResult.status → Literal["PASS","FAIL","ERROR","TIMEOUT"]；(5) MockRule 增加 model_validator 校验 response 必须含 code+message 键；(6) TokenCounter 增加 __repr__；(7) 修正"独立子项目"描述为"共用依赖的子目录"，File List 补充根目录 requirements.txt。
