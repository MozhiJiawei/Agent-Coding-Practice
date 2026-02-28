---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
lastStep: 8
status: 'complete'
completedAt: '2026-02-28'
inputDocuments:
  - _bmad-output/planning-artifacts/prd-test-simulator.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/project-context.md
  - docs/interface.md
  - docs/interface_simulate.md
  - docs/task.md
workflowType: 'architecture'
project_name: 'AI Agent Coding - Test Simulator'
user_name: 'LJW'
date: '2026-02-28'
---

# Architecture Decision Document — 测试仿真器 (Test Simulator)

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
26 个 FR 组织为 5 个能力域：Chat 驱动（FR1-5）、模型代理（FR6-9）、Mock 租房 API（FR10-15）、测试用例与判定（FR16-22）、报告输出（FR23-26）。无前端/UI 需求，纯 CLI + 多 HTTP 服务编排工具。

**Non-Functional Requirements:**
10 个 NFR 跨 Performance / Integration / Usability / Reliability 四类：
- 单用例超时可配置，默认 60s（NFR1）
- 模型代理转发额外延迟 < 100ms（NFR2）
- 与 Agent Chat 接口完全兼容（NFR3）
- 与租房仿真 API 15 个端点兼容（NFR4）
- 与 OpenAI Chat Completions 格式兼容（NFR5）
- 5 分钟内可添加新用例（NFR6）
- 人类可读测试报告（NFR7）
- 明确错误归因指示（NFR8）
- Mock 未匹配不返回 5xx（NFR9）
- 异常退出不丢失已有结果（NFR10）

**Scale & Complexity:**
- Primary domain: 测试工具 / HTTP 多服务编排（Python Backend + CLI）
- Complexity level: Medium
- Estimated architectural components: 5（Test Runner、Chat Client、Model Proxy、Mock Rental API、Assertion Engine + Reporter）

### Technical Constraints & Dependencies

- 必须与 Agent 的 `POST /api/v1/chat` 接口完全兼容（docs/interface.md）
- Model Proxy 需监听 :8888，格式与 OpenAI Chat Completions 兼容
- Mock 租房 API 需覆盖 15 个端点，响应结构与真实 API 一致（docs/interface_simulate.md）
- Python 3.11+（与主项目技术栈一致）
- 本地开发工具，不涉及部署到竞赛平台
- Agent 的 `model_ip` 需指向测试仿真器自身（`127.0.0.1`）
- Agent 的 `RENTAL_API_BASE` 需指向测试仿真器的 Mock 租房 API

### Cross-Cutting Concerns Identified

1. **多服务协调** — Test Runner 与两个 HTTP Server（Model Proxy + Mock Rental API）在同一进程中运行
2. **配置驱动** — 测试用例、Mock 数据、服务端口均由 YAML 配置文件控制
3. **Session 隔离** — 每个用例独立 session_id，避免状态串扰
4. **错误归因** — 失败时需明确指示环节：Chat 不通 / 模型转发失败 / Mock 未匹配 / 断言不通过
5. **模式切换** — Mock vs 透传，在不改代码的情况下通过配置切换
6. **Token 统计** — Model Proxy 截取 LLM 响应 usage 字段，累加到当前 case 的报告中

## Starter Template Evaluation

### Primary Technology Domain

测试工具 / HTTP 多服务编排（Python + FastAPI + httpx），基于主项目技术栈约束和 `project-context.md` 规范，无前端/UI，无外部数据库。

### Starter Options Considered

| 选项 | 评估结果 |
|------|---------|
| pytest + fixtures 框架 | 过重：引入 pytest 生态，与多服务编排不兼容 |
| FastAPI cookiecutter | 方向不对：面向 API 服务，不适合测试工具 |
| 自定义极简 scaffold | ✅ 选定：与主项目风格一致，完全匹配需求 |

### Selected Starter: 自定义极简 scaffold

**Rationale for Selection:**
测试仿真器的核心是多服务编排 + 配置驱动测试执行，现有框架无法直接匹配。与主项目保持一致的极简 Python 风格最合适。

**Project Initialization:**

```bash
mkdir test-simulator
cd test-simulator
touch main.py config.py runner.py model_proxy.py mock_rental.py
touch requirements.txt config.yaml test_cases.yaml
mkdir mock_data && touch mock_data/default.yaml
python -m venv .venv && .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" httpx pyyaml pydantic
pip freeze > requirements.txt
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:** Python 3.11+，全异步（asyncio + async/await 贯穿全链路）

**File Structure:**
- `main.py` — CLI 入口 + asyncio 服务编排 + 生命周期管理
- `config.py` — Pydantic 配置/用例模型 + YAML 加载 + Mock 数据加载
- `runner.py` — Test Runner（Chat Client + 断言引擎 + 报告生成）
- `model_proxy.py` — Model Proxy FastAPI 应用 (:8888)
- `mock_rental.py` — Mock 租房 API FastAPI 应用 (:8080)

**Build Tooling:** uvicorn 程序化启动（非 CLI），无构建步骤

**Testing Framework:** 自定义 Test Runner（非 pytest，因为需要与 HTTP 服务协调启动）

**Code Organization:** 极简多文件，每个角色一个文件，与主项目风格一致

**Development Experience:**
- 启动：`python main.py --all` 或 `python main.py --case chat_hello`
- 调试：结构化 print 输出每个用例的执行过程

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- 多服务编排策略：单进程 asyncio 协调
- Mock 数据匹配机制：路径 + 参数 → 预定义响应
- 断言引擎设计：规则函数注册表
- Test Runner 执行流程：启动服务 → 逐例执行 → 生成报告

**Important Decisions (Shape Architecture):**
- 配置文件 Schema（全局配置 + 用例配置 + Mock 数据）
- 报告三层输出（控制台 + JSON + Markdown）
- Model Proxy 的 usage 统计截取
- Mock vs 透传模式切换机制

**Deferred Decisions (Post-MVP):**
- 模型响应录制与回放（离线测试）
- 用例并行执行（asyncio.gather）
- HTML 报告生成
- 时间片计算与竞赛规则对齐
- 与上次运行结果的 diff 对比

### 服务编排架构

**决策：单进程 asyncio + 多 ASGI 服务**

```
┌──────────────────────────────────────────────────────────────────┐
│                    main.py (单进程 asyncio)                       │
│                                                                  │
│  1. 加载 config.yaml + test_cases.yaml + mock_data              │
│  2. 启动 Model Proxy (uvicorn, :8888)     ──┐                    │
│  3. 启动 Mock Rental API (uvicorn, :8080) ──┤ 后台 asyncio tasks │
│  4. 运行 Test Runner                      ──┘                    │
│  5. 生成报告                                                     │
│  6. 关闭服务                                                     │
└──────────────────────────────────────────────────────────────────┘
```

**Rationale：**
- 单进程避免跨进程通信与生命周期管理复杂度
- asyncio 原生支持并发运行多个 ASGI server + HTTP client
- 所有组件共享同一 event loop，Mock 数据状态内存共享

**服务启动方式：**
```python
config = uvicorn.Config(app=model_proxy_app, host="0.0.0.0", port=8888, log_level="warning")
server = uvicorn.Server(config)
asyncio.create_task(server.serve())
```

### Data Architecture

**配置数据（config.yaml）：**

```yaml
agent_base_url: "http://localhost:8191"
model_proxy_port: 8888
llm_proxy_url: "https://your-llm-proxy/v1/chat/completions"
llm_api_key: "your-key"
mock_rental_port: 8080
rental_mode: "mock"            # mock | passthrough
rental_passthrough_url: "http://7.225.29.223:8080"
test_user_id: "your-employee-id"
test_cases_file: "test_cases.yaml"
mock_data_file: "mock_data/default.yaml"
timeout_per_case: 60
report_dir: "_bmad-output/test-reports"
```

**测试用例（test_cases.yaml）：**

```yaml
test_cases:
  - id: chat_hello
    type: Chat
    messages:
      - "你好"
    expect:
      has_response: true
      response_not_empty: true

  - id: single_haidian_2br
    type: Single
    messages:
      - "帮我找海淀区两居室，月租8000以内"
    expect:
      response_json_valid: true
      houses_match: ["HF_42", "HF_107"]
      house_count_min: 1

  - id: multi_progressive
    type: Multi
    messages:
      - "我想在朝阳区找房"
      - "预算6000以内"
      - "近地铁的"
      - "给我看看具体有哪些"
    expect:
      response_json_valid: true
      houses_match_subset: true
      round_count: 4
```

**Mock 数据（mock_data/default.yaml）：**

```yaml
mock_responses:
  - path: "/api/houses/init"
    method: "POST"
    response:
      code: 0
      message: "success"
      data:
        action: "reset_user"
        message: "该用户状态覆盖已清空，房源恢复为初始状态"

  - path: "/api/landmarks"
    method: "GET"
    params_match: { category: "subway", district: "海淀" }
    response:
      code: 0
      message: "success"
      data:
        total: 7
        items: []

  - path: "/api/houses/by_platform"
    method: "GET"
    response:
      code: 0
      message: "success"
      data:
        total: 0
        page: 1
        page_size: 10
        items: []
```

**匹配规则优先级：** path + method 精确匹配 → params_match 子集匹配 → 仅 path + method 匹配 → 默认未匹配响应

### 断言引擎

**决策：规则函数注册表 + 可组合规则**

```python
ASSERTION_RULES: dict[str, Callable] = {
    "has_response": assert_has_response,
    "response_not_empty": assert_response_not_empty,
    "response_json_valid": assert_response_json_valid,
    "houses_match": assert_houses_match,
    "houses_match_subset": assert_houses_match_subset,
    "house_count_min": assert_house_count_min,
    "status_success": assert_status_success,
}
```

每个 `expect` 字段对应一个规则函数，输入为 `(agent_response, expected_value)`，返回 `(passed: bool, detail: str)`。

**houses_match 三种模式：**

| expect 字段 | 匹配方式 |
|-------------|---------|
| `houses_match: [...]` | 精确匹配：`sorted(actual) == sorted(expected)` |
| `houses_match_subset: true` | 子集匹配：`set(expected) ⊆ set(actual)` |
| `house_count_min: N` | 数量匹配：`len(actual) >= N` |

### API & Communication Patterns

**Chat Client → Agent（runner.py）：**
- `httpx.AsyncClient` 复用，生命周期跟随 Test Runner
- 逐轮发送，每轮 `await` Agent 响应后再发送下一轮
- 每个用例独立 `session_id`（格式：`test-{case_id}-{timestamp}`）
- 每轮请求 `model_ip` 固定为 `"127.0.0.1"`（指向 Model Proxy）

**Model Proxy → 外部 LLM（model_proxy.py）：**
- 请求原样转发，透传 `Session-ID` 请求头及完整请求体
- 响应原样返回给 Agent
- 截取响应中 `usage` 字段，累计 token 统计到当前用例
- 使用 `httpx.AsyncClient` 转发，生命周期跟随 FastAPI lifespan

**Mock Rental API（mock_rental.py）：**
- Mock 模式：按 `mock_responses` 配置匹配并返回预定义 JSON
- 透传模式：`httpx.AsyncClient` 转发至真实租房 API（`rental_passthrough_url`）
- 未匹配时返回 `{"code": 404, "message": "Mock 未匹配: {method} {path}"}`（HTTP 200，避免 5xx 导致 Agent 异常）
- `X-User-ID` 请求头在透传模式下传递，Mock 模式下忽略

### 报告输出

**决策：三层输出 + token 统计**

| 层级 | 输出位置 | 内容 |
|------|---------|------|
| 控制台实时 | stdout | 每用例 PASS/FAIL + 耗时 + 最终汇总 |
| JSON 报告 | `{report_dir}/report-{timestamp}.json` | 完整结构化数据（meta + summary + cases） |
| Markdown 报告 | `{report_dir}/report-{timestamp}.md` | 人类可读摘要 + 失败详情表 |

**控制台输出示例：**
```
[1/5] chat_hello ............ PASS  (1.2s)
[2/5] single_haidian_2br .... FAIL  (3.5s)
       ✗ houses_match: expected ['HF_42','HF_107'], got ['HF_42']
[3/5] multi_progressive ..... PASS  (5.8s)
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Results: 4 passed, 1 failed (12.5s)
Report: _bmad-output/test-reports/report-2026-02-28-143000.json
```

**JSON 报告结构：**
```json
{
  "meta": {
    "run_id": "run-2026-02-28-143000",
    "timestamp": "2026-02-28T14:30:00",
    "agent_base_url": "http://localhost:8191",
    "rental_mode": "mock",
    "total_duration_ms": 12500
  },
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 1,
    "pass_rate": "80%"
  },
  "cases": [
    {
      "case_id": "chat_hello",
      "case_type": "Chat",
      "status": "PASS",
      "duration_ms": 1200,
      "rounds": 1,
      "token_usage": { "prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200 }
    },
    {
      "case_id": "single_haidian_2br",
      "case_type": "Single",
      "status": "FAIL",
      "duration_ms": 3500,
      "rounds": 1,
      "failure_reason": "houses_match: expected ['HF_42','HF_107'], got ['HF_42']",
      "actual_response": "{\"message\":\"...\",\"houses\":[\"HF_42\"]}",
      "token_usage": { "prompt_tokens": 800, "completion_tokens": 200, "total_tokens": 1000 }
    }
  ]
}
```

Token 统计来源：Model Proxy 截取每次 LLM 响应的 `usage` 字段，通过共享 `token_counter` 对象累加到当前 case。

### Decision Impact Analysis

**Implementation Sequence:**
1. `config.py` — 配置加载 + Pydantic 模型（SimulatorConfig, TestCase, MockRule, CaseResult）
2. `mock_rental.py` — Mock 租房 API FastAPI 应用
3. `model_proxy.py` — Model Proxy FastAPI 应用
4. `runner.py` — Chat Client + 断言引擎 + 报告生成
5. `main.py` — CLI 入口 + 服务编排
6. `config.yaml` + `test_cases.yaml` + `mock_data/default.yaml` — 配置与数据

**Cross-Component Dependencies:**
- `runner.py` 依赖 `config.py` 的配置模型和用例模型
- `model_proxy.py` 依赖 `config.py` 的 LLM 代理 URL 和 API Key
- `mock_rental.py` 依赖 `config.py` 的 Mock 数据 + rental_mode 配置
- `main.py` 编排所有组件，是唯一知道全局生命周期的文件
- Token 统计需要 `model_proxy.py` 与 `runner.py` 之间共享 `token_counter`（内存共享，同进程）

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 5 个区域，AI Agent 可能做出不兼容选择

---

### Naming Patterns

**Python 命名约定（全局强制）：**
- 函数/变量：`snake_case`（如 `run_tests`, `case_result`, `mock_responses`）
- 模块级常量：`ALL_CAPS_SNAKE`（如 `ASSERTION_RULES`, `DEFAULT_TIMEOUT`, `MOCK_REGISTRY`）
- Pydantic 模型类名：`PascalCase`（如 `SimulatorConfig`, `TestCase`, `CaseResult`, `TestReport`）
- 文件名：`snake_case.py`（`main.py`, `config.py`, `runner.py`, `model_proxy.py`, `mock_rental.py`）

**配置 YAML 命名：** 全部 `snake_case`（`agent_base_url`, `model_proxy_port`, `test_cases_file`）

**测试用例 ID 命名：** `snake_case`（`chat_hello`, `single_haidian_2br`, `multi_progressive`）

**Session ID 格式：** `test-{case_id}-{unix_timestamp}`（如 `test-chat_hello-1709107200`）

**报告文件命名：** `report-{YYYY-MM-DD-HHmmss}.{json|md}`

---

### Structure Patterns

**模块职责边界（严格禁止跨界）：**

| 文件 | 包含内容 | 禁止包含 |
|------|---------|---------|
| `main.py` | CLI 参数解析（argparse） + asyncio 编排 + 服务启停 | 断言逻辑、Mock 匹配、HTTP 请求发送 |
| `config.py` | Pydantic 配置/用例/Mock 模型 + YAML 加载函数 | HTTP 服务、业务逻辑 |
| `runner.py` | Chat Client（send_message） + 断言引擎（ASSERTION_RULES） + 报告生成 | FastAPI 路由、Mock 数据匹配 |
| `model_proxy.py` | FastAPI 应用 + `/v1/chat/completions` 路由 + LLM 转发 + token 截取 | 断言逻辑、测试执行、Mock 数据 |
| `mock_rental.py` | FastAPI 应用 + 租房 API 15 端点路由 + Mock 匹配 + 透传转发 | 断言逻辑、模型代理 |

**导入方向（单向，禁止循环）：**
```
main.py → runner.py → config.py
main.py → model_proxy.py → config.py
main.py → mock_rental.py → config.py
```

**共享状态传递方式（main.py 创建，通过参数/app.state 注入）：**
- `token_counter: TokenCounter` — 传递给 `model_proxy` app.state 和 `runner`
- `mock_registry: list[MockRule]` — 传递给 `mock_rental` app.state
- `config: SimulatorConfig` — 传递给所有模块

---

### Format Patterns

**Mock 响应格式必须与真实 API 完全一致：**
```python
# ✅ 正确：与真实 API 结构一致
{"code": 0, "message": "success", "data": {...}}

# ❌ 错误：自定义结构
{"status": "ok", "result": {...}}
```

**断言函数签名统一：**
```python
def assert_xxx(response: dict, expected: Any) -> tuple[bool, str]:
    """返回 (passed, detail_message)"""
```

**CaseResult 标准结构：**
```python
class CaseResult(BaseModel):
    case_id: str
    case_type: str          # Chat / Single / Multi
    status: str             # PASS / FAIL / ERROR / TIMEOUT
    duration_ms: int
    rounds: int
    failure_reason: str | None = None
    actual_response: str | None = None
    token_usage: TokenUsage | None = None

class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
```

**Agent Chat 请求格式（runner.py 发出）：**
```python
{
    "model_ip": "127.0.0.1",
    "session_id": "test-chat_hello-1709107200",
    "message": "你好"
}
```

---

### Communication Patterns

**Test Runner 执行循环（逐用例、逐轮、严格顺序）：**
```python
for case in test_cases:
    session_id = f"test-{case.id}-{int(time.time())}"
    token_counter.reset()
    responses = []
    for message in case.messages:
        resp = await send_message(client, config.agent_base_url, session_id, message)
        responses.append(resp)
    result = run_assertions(responses[-1], case.expect)
    print_case_result(idx, total, result)
    results.append(result)
```

**Model Proxy token 截取（非侵入）：**
```python
llm_response = await client.post(llm_url, json=body, headers=headers)
data = llm_response.json()
if "usage" in data:
    token_counter.add(data["usage"])
return JSONResponse(content=data)
```

**Mock 匹配策略（优先级从高到低）：**
1. path + method + params_match 全匹配（params 为子集匹配）
2. path + method 匹配（忽略 params）
3. 未匹配 → `{"code": 404, "message": "Mock 未匹配: {method} {path}"}`（HTTP 200）

---

### Process Patterns

**错误处理分层：**

| 层级 | 异常来源 | 处理方式 |
|------|---------|---------|
| Chat Client | Agent 不可达 / 超时 | `CaseResult.status = "ERROR"`，记录原因 |
| Model Proxy | LLM 不可达 / 超时 | 返回 HTTP 502 + 错误 JSON `{"error": "..."}`，不崩溃 |
| Mock Rental | 无匹配规则 | 返回 HTTP 200 + `{"code": 404, ...}`，不崩溃 |
| Runner 断言 | 断言执行异常 | `CaseResult.status = "ERROR"`，记录异常详情 |
| Main 顶层 | 任意未捕获异常 | finally 块输出已有结果后再退出（NFR10） |

**超时控制：**
```python
try:
    result = await asyncio.wait_for(run_single_case(case, ...), timeout=config.timeout_per_case)
except asyncio.TimeoutError:
    result = CaseResult(
        case_id=case.id, case_type=case.type,
        status="TIMEOUT",
        failure_reason=f"超时 {config.timeout_per_case}s",
        duration_ms=config.timeout_per_case * 1000,
        rounds=0
    )
```

---

### Enforcement Guidelines

**All AI Agents MUST:**
- Mock 响应结构与真实租房 API 完全一致（code + message + data）
- 断言函数签名统一为 `(response, expected) -> (bool, str)`
- 导入方向严格遵循 `main → runner/model_proxy/mock_rental → config` 单向链
- `token_counter` 通过 `app.state` 注入到 `model_proxy`，不使用全局变量
- `mock_registry` 通过 `app.state` 注入到 `mock_rental`，不使用全局变量
- 服务启停在 `main.py` 统一管理，其他模块不负责生命周期

**Anti-Patterns（严禁）：**
- ❌ 在 `runner.py` 中直接启动/停止 HTTP 服务
- ❌ 在 `model_proxy.py` 或 `mock_rental.py` 中使用全局可变状态
- ❌ Mock 响应使用自定义格式（必须与真实 API 一致）
- ❌ 断言函数 raise 异常穿透到 runner 循环（必须返回 tuple）
- ❌ 用例之间共享 session_id 或 token_counter 状态

## Project Structure & Boundaries

### Complete Project Directory Structure

```
test-simulator/
├── main.py              # CLI 入口（argparse）+ asyncio 服务编排 + 生命周期管理
├── config.py            # Pydantic 模型（SimulatorConfig, TestCase, MockRule, CaseResult, TokenUsage）+ YAML 加载
├── runner.py            # Test Runner（Chat Client + 断言引擎 ASSERTION_RULES + 报告生成）
├── model_proxy.py       # Model Proxy FastAPI 应用 (:8888)
├── mock_rental.py       # Mock 租房 API FastAPI 应用 (:8080)
├── requirements.txt     # 依赖声明（fastapi, uvicorn[standard], httpx, pyyaml, pydantic）
├── config.yaml          # 全局配置（端口、URL、模式、路径）
├── test_cases.yaml      # 测试用例定义（id, type, messages, expect）
└── mock_data/
    └── default.yaml     # 默认 Mock 响应数据集
```

---

### Architectural Boundaries

**外部边界（与 Agent 的交互）：**
```
Test Simulator (本工具)
    │
    ├─→ Agent (localhost:8191)     POST /api/v1/chat      [runner.py 发出]
    │     │
    │     ├─→ Model Proxy (:8888)  POST /v1/chat/completions  [model_proxy.py 提供]
    │     │
    │     └─→ Mock Rental (:8080)  GET/POST /api/*            [mock_rental.py 提供]
    │
    └── Model Proxy + Mock Rental 由 Test Simulator 自身提供
```

**内部组件边界：**
```
main.py
  │ 创建共享状态（config, token_counter, mock_registry）
  │ 启动 model_proxy_app, mock_rental_app（uvicorn 后台任务）
  │ 调用 runner.run_all_cases(config, test_cases, token_counter)
  ▼
runner.py
  │ httpx.AsyncClient → Agent (:8191) POST /api/v1/chat
  │ 断言引擎 ASSERTION_RULES[rule_name](response, expected)
  │ 报告生成 → console + JSON + Markdown
  ▼
config.py (纯数据模型 + YAML 加载，无业务逻辑)
```

**数据流（完整用例执行生命周期）：**
```
1. main.py 加载 config.yaml + test_cases.yaml + mock_data/default.yaml
2. 创建共享 token_counter 对象
3. 启动 Model Proxy (:8888) + Mock Rental API (:8080) 作为后台 asyncio 任务
4. 等待服务就绪（health check 或短暂 sleep）
5. 对每个 test case：
   a. 生成 session_id = "test-{case.id}-{timestamp}"
   b. 重置 token_counter
   c. 逐轮发送 message → POST Agent/api/v1/chat
      │  Agent 内部调用 Model Proxy (:8888) → 转发至外部 LLM
      │  Agent 内部调用 Mock Rental API (:8080) → 返回 Mock 数据
      └  Agent 返回 response 给 runner
   d. 取最后一轮 response，执行全部 expect 规则
   e. 记录 CaseResult（含 status, duration_ms, failure_reason, token_usage）
   f. 控制台实时输出 PASS/FAIL
6. 全部用例完成后生成 JSON + Markdown 报告
7. 控制台输出汇总统计
8. 关闭 Model Proxy + Mock Rental API 服务
```

---

### Requirements to Structure Mapping

| FR | 文件 | 关键实现 |
|----|------|---------|
| FR1-FR3（Chat 驱动） | `runner.py` | `send_message()` → httpx POST /api/v1/chat |
| FR4（Agent Base URL） | `config.py` | `SimulatorConfig.agent_base_url` |
| FR5（model_ip 配置） | `runner.py` | 发送时 `model_ip="127.0.0.1"` |
| FR6-FR8（模型代理转发） | `model_proxy.py` | FastAPI POST /v1/chat/completions → LLM |
| FR9（LLM URL 配置） | `config.py` | `SimulatorConfig.llm_proxy_url` |
| FR10-FR11（Mock 模式） | `mock_rental.py` | `match_mock()` → 返回预定义 JSON |
| FR12（透传模式） | `mock_rental.py` | httpx 转发至 `rental_passthrough_url` |
| FR13（按用例 Mock 数据） | `config.py` + `mock_rental.py` | MockRule 列表 |
| FR14（/api/houses/init） | `mock_rental.py` | 硬编码成功响应 |
| FR15（X-User-ID） | `mock_rental.py` | 透传模式下传递 header |
| FR16-FR17（用例加载） | `config.py` | YAML → `list[TestCase]` |
| FR18-FR19（断言规则） | `runner.py` | `ASSERTION_RULES` dispatch |
| FR20（结果输出） | `runner.py` | `run_assertions()` 返回 CaseResult |
| FR21（CLI 参数） | `main.py` | `argparse: --case, --all, --tag` |
| FR22（时间片预算） | 延迟到 Phase 3 | — |
| FR23（JSON 报告） | `runner.py` | `write_json_report()` |
| FR24（控制台实时） | `runner.py` | `print_case_result()` |
| FR25（Markdown 报告） | `runner.py` | `write_md_report()` |
| FR26（报告路径配置） | `config.py` | `SimulatorConfig.report_dir` |

---

### Integration Points

**内部通信：**
- `main.py` → `runner.py`：函数调用 `await run_all_cases(config, cases, token_counter)`
- `main.py` → `model_proxy.py`：通过 `app.state` 注入 config + token_counter
- `main.py` → `mock_rental.py`：通过 `app.state` 注入 config + mock_registry
- 共享状态：`token_counter` 在 `main.py` 创建，`model_proxy` 写入，`runner` 读取后重置

**外部集成：**
- Agent Chat API：`httpx.AsyncClient` → `POST http://localhost:8191/api/v1/chat`
- LLM 代理：`httpx.AsyncClient` → `POST {llm_proxy_url}`（model_proxy 转发）
- 真实租房 API：`httpx.AsyncClient` → `{rental_passthrough_url}/api/*`（mock_rental 透传模式）

---

### File Organization Patterns

**main.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. CLI 参数解析函数 parse_args()
# 3. 服务启动/停止辅助函数
# 4. async def main(args) 主函数
#    - 加载配置
#    - 创建共享状态
#    - 启动后台服务
#    - 运行测试
#    - 生成报告
#    - 关闭服务
# 5. if __name__ == "__main__" 入口
```

**config.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. Pydantic 模型（SimulatorConfig, TestCase, ExpectRules, MockRule, CaseResult, TokenUsage, TestReport）
# 3. load_config(path) → SimulatorConfig
# 4. load_test_cases(path) → list[TestCase]
# 5. load_mock_data(path) → list[MockRule]
```

**runner.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. 常量（DEFAULT_MODEL_IP = "127.0.0.1"）
# 3. ASSERTION_RULES 注册表
# 4. 断言函数定义（assert_has_response, assert_houses_match, ...）
# 5. send_message() — Chat Client
# 6. run_assertions() — 执行全部 expect 规则
# 7. run_single_case() — 执行单个用例
# 8. run_all_cases() — 执行全部/筛选用例
# 9. print_case_result() — 控制台实时输出
# 10. write_json_report() — JSON 报告
# 11. write_md_report() — Markdown 报告
# 12. generate_reports() — 统一调用报告生成
```

**model_proxy.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. create_model_proxy_app(config, token_counter) → FastAPI
# 3. POST /v1/chat/completions 路由
# 4. 转发逻辑 + token 截取
```

**mock_rental.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. create_mock_rental_app(config, mock_registry) → FastAPI
# 3. match_mock(method, path, params, registry) → MockRule | None
# 4. 通用路由 catch-all → Mock 匹配或透传
# 5. POST /api/houses/init 特殊处理（硬编码成功响应）
```

---

### Development Workflow Integration

**开发启动（全部用例）：**
```bash
python main.py --all
```

**执行单个用例：**
```bash
python main.py --case chat_hello
```

**执行指定标签用例：**
```bash
python main.py --tag smoke
```

**透传模式（使用真实租房 API）：**
```yaml
# config.yaml 中修改
rental_mode: "passthrough"
```

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:** 全链路异步（FastAPI + httpx + asyncio），YAML 配置 + Pydantic v2 原生支持，单进程 asyncio 编排无冲突。所有技术选型与主项目 Agent 完全一致。

**Pattern Consistency:** snake_case 命名、单向依赖链、分层错误处理与主项目风格一致。Mock 响应格式强制与真实 API 一致，确保 Agent 无需感知测试环境。

**Structure Alignment:** 5 个源文件对所有 FR/NFR 提供完整支撑，模块边界清晰，集成点明确定义。

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:** 26/26 FR 全部覆盖（含新增报告 FR23-FR26），详见 FR 映射表。FR22（时间片）明确延迟到 Phase 3。

**Non-Functional Requirements Coverage:** 10/10 NFR 全部覆盖：
- NFR1（超时）→ `asyncio.wait_for` + `config.timeout_per_case`
- NFR2（代理延迟）→ httpx 直接转发，无额外处理开销
- NFR3（Agent Chat 兼容）→ 请求格式与 docs/interface.md 完全一致
- NFR4（租房 API 兼容）→ Mock 响应格式与 docs/interface_simulate.md 一致
- NFR5（OpenAI 兼容）→ Model Proxy 原样转发，不修改请求/响应
- NFR6（5分钟添加用例）→ YAML 配置驱动，添加用例仅需编辑 test_cases.yaml
- NFR7（可读报告）→ 三层输出（控制台 + JSON + Markdown）
- NFR8（错误指示）→ 分层错误处理 + CaseResult.failure_reason 明确归因
- NFR9（Mock 不 5xx）→ 返回 HTTP 200 + `{"code": 404, ...}`
- NFR10（异常不丢结果）→ main.py finally 块输出已有结果后再退出

### Gap Analysis Results

**无关键差距。** 所有 FR/NFR 均有明确的架构支撑。

**Important Gap 1 — Mock 数据丰富度（已标注）：**

MVP 阶段 `mock_data/default.yaml` 只需包含 3-5 个核心场景的预定义响应（如 /api/houses/init、基础房源列表、地标列表）。更丰富的 Mock 数据集在实际编写测试用例时逐步补充。

**Important Gap 2 — 服务就绪检测（已标注）：**

Model Proxy 和 Mock Rental API 启动后，runner 需确保服务可用再开始执行用例。推荐方案：启动后短暂 `await asyncio.sleep(0.5)` 或循环 health check 直至响应。

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] 项目上下文深度分析（26 FR + 10 NFR）
- [x] 规模与复杂度评估（Medium，测试工具 / HTTP 多服务编排）
- [x] 技术约束识别（Agent 接口兼容、端口、响应格式）
- [x] 横切关注点映射（6 个关注点）

**✅ Architectural Decisions**
- [x] 关键决策文档化（单进程 asyncio、Mock 匹配、断言引擎、报告三层）
- [x] 技术栈完整规定（Python 3.11+、FastAPI、httpx、PyYAML、Pydantic）
- [x] 集成模式定义（Chat Client → Agent → Model Proxy / Mock Rental）
- [x] 性能约束架构支撑（asyncio.wait_for 超时、httpx 直接转发）

**✅ Implementation Patterns**
- [x] 命名规范建立（snake_case、ALL_CAPS、PascalCase）
- [x] 结构模式定义（模块职责边界、导入方向）
- [x] 通信模式规定（执行循环、token 截取、Mock 匹配策略）
- [x] 过程模式文档化（分层错误处理、超时控制）

**✅ Project Structure**
- [x] 完整目录结构（5 源文件 + 3 配置文件）
- [x] 组件边界确立（模块职责不重叠）
- [x] 集成点映射（内部调用链 + 外部 API）
- [x] FR 到结构映射完整（26 FR 全部对应到文件/函数）

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION ✅

**Confidence Level:** High — 架构决策完整、模式清晰、结构具体，AI Agent 可据此直接实现而无需额外澄清。

**Key Strengths:**
- 单进程 asyncio 极大简化了多服务生命周期管理
- YAML 配置驱动使测试用例可在 5 分钟内添加
- 断言规则注册表支持灵活扩展新规则
- 三层报告覆盖开发/归档/CI 场景
- Mock 响应格式强制与真实 API 一致，Agent 无需感知测试环境
- 与主项目技术栈完全一致，学习成本为零

**Areas for Future Enhancement（Post-MVP 迭代）：**
- 模型响应录制与回放（完全离线测试）
- 用例并行执行（asyncio.gather 加速）
- 时间片计算与竞赛规则对齐
- HTML 可视化报告
- 与上次运行结果的 diff 对比
- 对抗性测试：模糊输入、异常响应注入

### Implementation Handoff

**AI Agent Guidelines:**
- 读取本文档 + PRD (prd-test-simulator.md) + project-context.md 后开始实现
- Mock 响应格式必须与 docs/interface_simulate.md 真实 API 完全一致
- 断言函数签名统一为 `(response, expected) -> (bool, str)`
- 共享状态通过 `app.state` 或函数参数注入，不使用模块级全局可变变量
- 导入方向严格遵循单向链

**First Implementation Priority:**
```bash
# Step 1: 项目初始化
mkdir test-simulator && cd test-simulator
touch main.py config.py runner.py model_proxy.py mock_rental.py
touch requirements.txt config.yaml test_cases.yaml
mkdir mock_data && touch mock_data/default.yaml

# Step 2: 安装依赖
python -m venv .venv && .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" httpx pyyaml pydantic
pip freeze > requirements.txt

# Step 3: 实现 config.py（Pydantic 模型 + YAML 加载）
# Step 4: 实现 mock_rental.py（Mock 租房 API FastAPI 应用）
# Step 5: 实现 model_proxy.py（Model Proxy FastAPI 应用）
# Step 6: 实现 runner.py（Chat Client + 断言引擎 + 报告生成）
# Step 7: 实现 main.py（CLI + asyncio 编排）
# Step 8: 编写 config.yaml + test_cases.yaml + mock_data/default.yaml
# Step 9: Smoke test 验证
```
