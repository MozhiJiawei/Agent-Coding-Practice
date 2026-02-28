---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories']
inputDocuments:
  - _bmad-output/planning-artifacts/prd-test-simulator.md
  - _bmad-output/planning-artifacts/architecture-test-simulator.md
project_name: 'AI Agent Coding - Test Simulator'
user_name: 'LJW'
date: '2026-02-28'
---

# Test Simulator - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Test Simulator, decomposing the requirements from the PRD and Architecture into implementable stories. The Test Simulator is a local evaluation and adversarial simulation tool for the AI Agent rental project, enabling full end-to-end testing without depending on the competition platform.

**Constraint:** Max 5 stories total (user-specified). Structure: 3 Epics × [2, 2, 1] Stories.

## Requirements Inventory

### Functional Requirements

FR1: 通过 HTTP 客户端向 Agent `POST /api/v1/chat` 发送请求，携带 model_ip、session_id、message
FR2: 支持按用例配置的顺序逐轮发送消息，每轮等待 Agent 响应后再发送下一轮
FR3: 支持为每个用例生成独立的 session_id，或使用配置的固定值
FR4: 支持配置 Agent 的 Base URL（默认 `http://localhost:8191`）
FR5: 支持配置 model_ip，使 Agent 的模型请求指向测试仿真器的模型代理服务
FR6: 测试仿真器可启动 HTTP 服务，监听可配置端口（如 8888），接收 `POST /v1/chat/completions` 请求
FR7: 可将收到的请求转发至配置的外部大模型代理 URL，并返回其响应
FR8: 支持透传 Session-ID 请求头及完整请求体/响应体
FR9: 外部代理 URL 可配置（如环境变量 `LLM_PROXY_URL`）
FR10: 测试仿真器可启动 Mock 租房 API 服务，实现地标与房源相关端点（至少覆盖 Agent 工具所调用的端点）
FR11: 支持 Mock 模式：按请求路径与参数匹配，返回配置的预定义 JSON
FR12: 支持透传模式：将请求转发至真实租房 API（`http://7.225.29.223:8080`）
FR13: Mock 响应支持按用例或按场景配置，不同用例可使用不同 Mock 数据集
FR14: 必须实现 `POST /api/houses/init`，返回成功响应，以支持 Agent 的 Session 初始化
FR15: 房源相关接口的请求需支持 `X-User-ID` 请求头，可配置默认值
FR16: 支持从 YAML 或 JSON 配置文件加载测试用例
FR17: 每个用例需包含：id、type（Chat/Single/Multi）、messages（输入列表）
FR18: 每个用例可配置 expect 规则：has_response、response_not_empty、response_json_valid、houses_match、house_count_min 等
FR19: 支持 houses_match 的多种模式：精确匹配、子集匹配、包含匹配
FR20: 执行结束后输出每个用例的通过/失败状态及失败原因
FR21: 支持 `--case <id>` 执行单个用例，`--all` 执行全部用例，`--tag <tag>` 按标签筛选
FR22: （Post-MVP / Phase 3）可选：支持时间片计算与预算控制，与竞赛规则对齐

### NonFunctional Requirements

NFR1: 单用例执行超时可配置（默认 60 秒），超时则判定该用例失败（TIMEOUT）
NFR2: 模型代理转发延迟应尽可能低，避免成为瓶颈（建议 < 100ms 额外延迟）
NFR3: 与 Agent 的接口兼容 docs/interface.md 定义的 Chat 格式
NFR4: 与租房 API 的接口兼容 docs/interface_simulate.md 定义的 15 个端点规范
NFR5: 模型代理与 OpenAI Chat Completions API 格式兼容
NFR6: 配置文件具备清晰的注释和示例，新用例可在 5 分钟内添加
NFR7: 测试报告输出为人类可读格式（控制台 + 可选 JSON/Markdown 报告文件）
NFR8: 错误信息应明确指示失败环节（Chat 不通、模型转发失败、Mock 未匹配、判定不通过）
NFR9: Mock 服务在未匹配到规则时，应返回明确错误或默认空响应（HTTP 200），避免 5xx 导致 Agent 异常
NFR10: 测试仿真器异常退出时，应输出已有测试结果，不静默丢失

### Additional Requirements

- **项目脚手架（Architecture Starter）**: 自定义极简 scaffold，Python 3.11+，FastAPI + uvicorn + httpx + PyYAML + Pydantic
- **项目结构**: 5 个源文件：`config.py`、`mock_rental.py`、`model_proxy.py`、`runner.py`、`main.py`
- **多服务编排**: 单进程 asyncio + 多 ASGI 服务（Model Proxy :8888 + Mock Rental API :8080）后台并发运行
- **断言引擎**: `ASSERTION_RULES` 规则函数注册表，每个规则函数签名为 `(response, expected) -> (bool, str)`
- **报告三层输出**: 控制台实时输出 + JSON 结构化报告文件 + Markdown 摘要报告文件
- **Token 统计**: Model Proxy 截取 LLM 响应 `usage` 字段，通过共享 `token_counter` 对象累积到当前用例
- **共享状态注入**: `token_counter` 和 `mock_registry` 通过 `app.state` 注入，禁止模块级全局可变状态
- **单向导入链**: `main → runner/model_proxy/mock_rental → config`（禁止循环依赖）
- **分层错误处理**: Chat/Model Proxy/Mock Rental/Runner 各层独立捕获异常，不向上崩溃
- **Session 隔离**: 每个用例独立 session_id 格式为 `test-{case_id}-{unix_timestamp}`

### FR Coverage Map

FR1  → Epic 2, Story 2.1 — send_message Chat Client
FR2  → Epic 2, Story 2.1 — 逐轮发送，await 响应
FR3  → Epic 2, Story 2.1 — session_id 独立生成逻辑
FR4  → Epic 1, Story 1.1 — SimulatorConfig.agent_base_url
FR5  → Epic 1, Story 1.2 — model_ip 指向 Model Proxy 地址
FR6  → Epic 1, Story 1.2 — model_proxy.py FastAPI + :8888 监听
FR7  → Epic 1, Story 1.2 — LLM 请求转发
FR8  → Epic 1, Story 1.2 — Session-ID 请求头透传
FR9  → Epic 1, Story 1.1 — SimulatorConfig.llm_proxy_url
FR10 → Epic 1, Story 1.2 — mock_rental.py FastAPI + 15 端点
FR11 → Epic 1, Story 1.2 — Mock 匹配策略（路径+参数优先级）
FR12 → Epic 1, Story 1.2 — 透传模式 httpx 转发
FR13 → Epic 1, Story 1.2 — MockRule 配置驱动
FR14 → Epic 1, Story 1.2 — POST /api/houses/init 硬编码成功响应
FR15 → Epic 1, Story 1.1/1.2 — X-User-ID 配置 + 透传
FR16 → Epic 2, Story 2.1 — YAML 用例加载（config.py 已在 Story 1.1 中定义 TestCase 模型）
FR17 → Epic 2, Story 2.1 — TestCase Pydantic 模型（id/type/messages）
FR18 → Epic 2, Story 2.1 — ExpectRules 模型 + 断言注册表
FR19 → Epic 2, Story 2.1 — houses_match 三种模式断言函数
FR20 → Epic 2, Story 2.1 — CaseResult + print_case_result
FR21 → Epic 2, Story 2.2 — argparse --case/--all/--tag
FR22 → ❌ 延至 Phase 3（Post-MVP，超出当前范围）

## Epic List

### Epic 1: 可运行的仿真服务环境

开发者 LJW 能够一键启动测试仿真器，使 Agent 的模型请求和工具调用都有对应的服务接收和响应，形成完整的本地仿真网络——无需外网，无需竞赛平台。

**FRs covered:** FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15
**NFRs covered:** NFR2, NFR3, NFR4, NFR5, NFR9

### Epic 2: 测试执行与结果判定

开发者 LJW 能够通过命令行运行测试用例，仿真器自动驱动 Agent 完成多轮对话，断言引擎判定每个用例通过或失败，并输出清晰的控制台报告和结构化报告文件。

**FRs covered:** FR1, FR2, FR3, FR16, FR17, FR18, FR19, FR20, FR21
**NFRs covered:** NFR1, NFR6, NFR7, NFR8, NFR10

### Epic 3: 开箱即用示例与端到端验证

开发者 LJW 拿到代码后能立即运行，内置三类标准测试用例（Chat/Single/Multi）、完整 Mock 数据集和带注释的配置文件，首次运行 `python main.py --all` 即可验证整个链路正常工作。

**FRs covered:** FR16, FR17（示例数据），NFR6（配置可读性）
**NFRs covered:** NFR4, NFR6

---

## Epic 1: 可运行的仿真服务环境

开发者 LJW 能够一键启动测试仿真器，使 Agent 的模型请求和工具调用都有对应的服务接收和响应，形成完整的本地仿真网络——无需外网，无需竞赛平台。

### Story 1.1: 项目脚手架与配置系统

As a developer (LJW),
I want a project scaffold with a complete typed configuration system,
So that I can define simulator settings, test cases, and mock data in validated YAML files with clear structure, enabling all other simulator components to load their configuration reliably.

**Acceptance Criteria:**

**Given** a target workspace directory,
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

**Given** a valid `config.yaml` with all required fields (`agent_base_url`, `model_proxy_port`, `llm_proxy_url`, `llm_api_key`, `mock_rental_port`, `rental_mode`, `rental_passthrough_url`, `test_user_id`, `test_cases_file`, `mock_data_file`, `timeout_per_case`, `report_dir`),
**When** `load_config(path)` is called in `config.py`,
**Then** a `SimulatorConfig` Pydantic model is returned with all fields correctly typed and validated (string, int, enum for `rental_mode: mock|passthrough`)

**Given** a valid `test_cases.yaml` containing a list of test cases,
**When** `load_test_cases(path)` is called,
**Then** a `list[TestCase]` is returned where each `TestCase` has `id: str`, `type: str` (Chat/Single/Multi), `messages: list[str]`, and optional `expect: ExpectRules` and `tags: list[str]`

**Given** a valid `mock_data/default.yaml` with `mock_responses` list,
**When** `load_mock_data(path)` is called,
**Then** a `list[MockRule]` is returned where each `MockRule` has `path: str`, `method: str`, optional `params_match: dict`, and `response: dict`

**Given** a `config.yaml` or `test_cases.yaml` with a missing required field or wrong type,
**When** any load function is called,
**Then** a clear `ValidationError` or `ValueError` is raised with the field name and expected type indicated in the message

**Given** the Pydantic models `CaseResult` and `TokenUsage` defined in `config.py`,
**When** inspected,
**Then** `CaseResult` has fields: `case_id: str`, `case_type: str`, `status: str` (PASS/FAIL/ERROR/TIMEOUT), `duration_ms: int`, `rounds: int`, `failure_reason: str | None`, `actual_response: str | None`, `token_usage: TokenUsage | None`; and `TokenUsage` has `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`

---

### Story 1.2: 双 HTTP 仿真服务（Mock 租房 API + 模型代理）

As a developer (LJW),
I want Mock Rental API and Model Proxy HTTP services that handle all Agent tool calls and model inference requests,
So that the Agent under test can operate in a fully controlled local environment where every external dependency is intercepted and handled by the simulator.

**Acceptance Criteria:**

**Given** `create_mock_rental_app(config, mock_registry)` is called in `mock_rental.py`,
**When** the returned FastAPI app is inspected,
**Then** it has routes covering all 15 rental API endpoints: `/api/landmarks`, `/api/landmarks/name/{name}`, `/api/landmarks/search`, `/api/landmarks/{id}`, `/api/landmarks/stats`, `/api/houses/{id}`, `/api/houses/listings/{id}`, `/api/houses/by_community`, `/api/houses/by_platform`, `/api/houses/nearby`, `/api/houses/nearby_landmarks`, `/api/houses/stats`, `/api/houses/init`, `/api/houses/{id}/rent`, `/api/houses/{id}/terminate`, `/api/houses/{id}/offline`

**Given** a request to `POST /api/houses/init`,
**When** received by the Mock Rental API (regardless of rental_mode),
**Then** HTTP 200 is returned with body `{"code": 0, "message": "success", "data": {"action": "reset_user", "message": "该用户状态覆盖已清空，房源恢复为初始状态"}}`

**Given** `rental_mode: "mock"` and a GET request whose `path + method + params_match` all match a rule in `mock_registry`,
**When** `match_mock(method, path, params, registry)` is called,
**Then** the matching MockRule's `response` dict is returned as HTTP 200 JSON (highest-priority match wins: path+method+params > path+method only)

**Given** `rental_mode: "mock"` and a request with no matching MockRule,
**When** received,
**Then** HTTP 200 is returned with `{"code": 404, "message": "Mock 未匹配: {METHOD} {path}"}` — never a 5xx response

**Given** `rental_mode: "passthrough"` and any rental API request,
**When** received,
**Then** the request is forwarded via `httpx.AsyncClient` to `config.rental_passthrough_url` with the `X-User-ID` header preserved, and the real API response is returned unchanged

**Given** `create_model_proxy_app(config, token_counter)` is called in `model_proxy.py`,
**When** a valid OpenAI-format `POST /v1/chat/completions` request is received (with `model`, `messages`, optional `tools` and `stream` fields),
**Then** it is forwarded via `httpx.AsyncClient` to `config.llm_proxy_url` with the `Session-ID` request header and full request body preserved intact

**Given** the LLM response contains a `usage` field (`prompt_tokens`, `completion_tokens`, `total_tokens`),
**When** the proxy receives the response,
**Then** `token_counter.add(usage)` is called and the full response is returned to the Agent without modification

**Given** the LLM proxy URL is unreachable or returns an error,
**When** the Model Proxy receives a request,
**Then** HTTP 502 is returned with `{"error": "LLM proxy unavailable: {detail}"}` — the proxy does not crash

---

## Epic 2: 测试执行与结果判定

开发者 LJW 能够通过命令行运行测试用例，仿真器自动驱动 Agent 完成多轮对话，断言引擎判定每个用例通过或失败，并输出清晰的控制台报告和结构化报告文件。

### Story 2.1: Test Runner 与断言引擎

As a developer (LJW),
I want a Test Runner that drives multi-round chat with the Agent and an assertion engine that validates outcomes against configured expect rules,
So that I can automatically verify whether the Agent produces the correct responses for each test case, with precise PASS/FAIL verdicts and failure details that pinpoint exactly what went wrong.

**Acceptance Criteria:**

**Given** a `TestCase` with `messages: ["你好", "帮我找房"]` and a running Agent,
**When** `run_single_case(case, config, client, token_counter)` is called in `runner.py`,
**Then** `send_message()` is called sequentially for each message, each call `await`s the Agent's response before proceeding to the next round (FR2)

**Given** `send_message(client, agent_base_url, session_id, message)` is called,
**When** the HTTP POST is made to `{agent_base_url}/api/v1/chat`,
**Then** the request body is `{"model_ip": "127.0.0.1", "session_id": "test-{case.id}-{unix_timestamp}", "message": "{message}"}` and the session_id is unique per case execution (FR1, FR3, FR5)

**Given** `ASSERTION_RULES` dict is defined in `runner.py`,
**When** inspected,
**Then** it maps these keys to callable functions: `has_response`, `response_not_empty`, `response_json_valid`, `houses_match`, `houses_match_subset`, `house_count_min`, `status_success`

**Given** all assertion functions,
**When** any assertion function `assert_xxx(response: dict, expected: Any)` is called,
**Then** it returns `(bool, str)` — never raises an exception — where the string is empty on pass and contains a human-readable failure detail on fail (NFR8)

**Given** `expect: {houses_match: ["HF_42", "HF_107"]}` and Agent response with `houses: ["HF_42"]`,
**When** `assert_houses_match` runs,
**Then** it returns `(False, "houses_match: expected ['HF_42', 'HF_107'], got ['HF_42']")`

**Given** `expect: {houses_match_subset: true}` and the configured expected IDs are all present in the Agent's `houses` list,
**When** `assert_houses_match_subset` runs,
**Then** it returns `(True, "")` confirming `set(expected) ⊆ set(actual)` (FR19)

**Given** a test case that takes longer than `config.timeout_per_case` seconds,
**When** executed inside `asyncio.wait_for(run_single_case(...), timeout=config.timeout_per_case)`,
**Then** `CaseResult(status="TIMEOUT", failure_reason="超时 {N}s", duration_ms=N*1000, rounds=0)` is returned (NFR1)

**Given** the Agent service is unreachable (connection refused),
**When** `send_message()` raises an `httpx.ConnectError`,
**Then** `CaseResult(status="ERROR", failure_reason="Chat 不通: {error_detail}")` is returned — runner loop continues to next case (NFR8)

**Given** a completed `CaseResult`,
**When** `print_case_result(idx, total, result)` is called,
**Then** stdout shows `[{idx}/{total}] {case_id} ...... PASS ({duration}s)` for pass, or `[{idx}/{total}] {case_id} ...... FAIL ({duration}s)\n       ✗ {failure_reason}` for fail/error/timeout

---

### Story 2.2: CLI 入口、服务编排与报告生成

As a developer (LJW),
I want a single `python main.py` command that starts all services, runs the selected test cases, and saves structured reports,
So that I can run a full regression or targeted test with one command and get both real-time console feedback and persistent report files for later analysis.

**Acceptance Criteria:**

**Given** `python main.py --all` is run,
**When** `main()` executes,
**Then** in order: (1) `config.yaml` and `test_cases.yaml` are loaded, (2) `token_counter` and `mock_registry` shared state objects are created, (3) Model Proxy (:8888) and Mock Rental API (:8080) are started as background `asyncio.create_task` coroutines, (4) a readiness wait (`asyncio.sleep(0.5)` or health-check loop) completes, (5) all test cases run sequentially, (6) reports are generated, (7) both services are shut down cleanly

**Given** `python main.py --case chat_hello`,
**When** executed,
**Then** only the test case with `id == "chat_hello"` is loaded and executed; all other cases are skipped (FR21)

**Given** `python main.py --tag smoke`,
**When** executed,
**Then** only test cases whose `tags` list contains `"smoke"` are executed (FR21)

**Given** all test cases complete (or are interrupted),
**When** `generate_reports(results, config)` is called,
**Then** a JSON file is saved to `{config.report_dir}/report-{YYYY-MM-DD-HHmmss}.json` containing: `meta` (run_id, timestamp, agent_base_url, rental_mode, total_duration_ms), `summary` (total, passed, failed, pass_rate), and `cases` array with full `CaseResult` data per case (NFR7)

**Given** all test cases complete,
**When** the Markdown report is generated,
**Then** a `.md` file is saved to `{config.report_dir}/` containing: a summary table (case_id, type, status, duration, failure_reason) and a totals line `N passed, M failed`

**Given** an unhandled exception occurs anywhere in `main()` after tests have started,
**When** the exception propagates,
**Then** the `finally` block in `main()` calls `generate_reports(completed_results_so_far, config)` and prints the summary before the process exits (NFR10)

**Given** `argparse` is used in `main.py`,
**When** `python main.py --help` is run,
**Then** usage instructions show all three options (`--all`, `--case <id>`, `--tag <tag>`) with descriptions

---

## Epic 3: 开箱即用示例与端到端验证

开发者 LJW 拿到代码后能立即运行，内置三类标准测试用例（Chat/Single/Multi）、完整 Mock 数据集和带注释的配置文件，首次运行 `python main.py --all` 即可验证整个链路正常工作。

### Story 3.1: 示例配置文件、Mock 数据集与端到端冒烟验证

As a developer (LJW),
I want complete, annotated example configuration files and mock data that exercise all three test case types,
So that after cloning the repo and setting `llm_proxy_url` in config, I can run `python main.py --all` immediately and verify the full Chat→Agent→ModelProxy→MockRental→Assertion chain is working end-to-end.

**Acceptance Criteria:**

**Given** `config.yaml` is opened by a new developer,
**When** read top-to-bottom,
**Then** every configuration field has an inline comment explaining: its purpose, accepted values/format, and the default value — for example: `# rental_mode: mock | passthrough — "mock" returns predefined JSON, "passthrough" forwards to real API` (NFR6)

**Given** `test_cases.yaml` is loaded,
**When** `load_test_cases()` processes it,
**Then** it contains exactly these three sample cases:
- `id: chat_hello`, `type: Chat`, `messages: ["你好"]`, `expect: {has_response: true, response_not_empty: true}`
- `id: single_haidian_2br`, `type: Single`, `messages: ["帮我找海淀区两居室，月租8000以内"]`, `expect: {response_json_valid: true, houses_match: ["HF_42", "HF_107"], house_count_min: 1}`
- `id: multi_progressive`, `type: Multi`, `messages: ["我想在朝阳区找房", "预算6000以内", "近地铁的", "给我看看具体有哪些"]`, `expect: {response_json_valid: true, houses_match_subset: true, round_count: 4}`

**Given** `mock_data/default.yaml` is loaded,
**When** `load_mock_data()` processes it,
**Then** it contains MockRule entries covering at minimum:
- `POST /api/houses/init` → `{"code": 0, "message": "success", "data": {...}}`
- `GET /api/landmarks` (with `params_match: {category: "subway", district: "海淀"}`) → landmarks list response
- `GET /api/houses/by_platform` → `{"code": 0, ..., "data": {"total": 0, "items": []}}`
- All responses use `{"code": 0, "message": "success", "data": {...}}` structure matching real API format (NFR4)

**Given** a running Agent at `http://localhost:8191` and valid `llm_proxy_url` configured,
**When** `python main.py --all` is executed,
**Then** all three sample cases execute to a terminal state (PASS, FAIL, or TIMEOUT — never ERROR due to missing mock data or misconfiguration), and the console shows `[1/3]`, `[2/3]`, `[3/3]` progress lines followed by a summary

**Given** the final run completes,
**When** the console summary is printed,
**Then** it shows `Results: N passed, M failed ({total_duration}s)` followed by `Report: {report_dir}/report-{timestamp}.json` so LJW knows where to find the full report
