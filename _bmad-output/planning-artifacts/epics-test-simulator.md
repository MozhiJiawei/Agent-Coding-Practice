---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: 'complete'
completedAt: '2026-03-01'
inputDocuments:
  - _bmad-output/planning-artifacts/prd-test-simulator.md
  - _bmad-output/planning-artifacts/architecture-test-simulator.md
project_name: 'AI Agent Coding - Test Simulator'
user_name: 'LJW'
date: '2026-03-01'
---

# Test Simulator - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Test Simulator, decomposing the requirements from the PRD (updated 2026-03-01) and Architecture into implementable stories. The Test Simulator is a local evaluation and adversarial simulation tool for the AI Agent rental project, enabling full end-to-end testing without depending on the competition platform.

## Requirements Inventory

### Functional Requirements

FR1: 通过 HTTP 客户端向 Agent `POST /api/v1/chat` 发送请求，携带 model_ip、session_id、message
FR2: 支持按用例配置的顺序逐轮发送消息，每轮等待 Agent 响应后再发送下一轮
FR3: 支持为每个用例生成独立的 session_id，或使用配置的固定值
FR4: 支持配置 Agent 的 Base URL（默认 `http://localhost:8191`）
FR5: 支持配置 model_ip，使 Agent 的模型请求指向测试仿真器的模型代理服务
FR6: 测试仿真器可启动 HTTP 服务，监听可配置端口（默认 8888），接收 `POST /v1/chat/completions` 请求
FR7: 将收到的请求转发至配置的外部大模型代理 URL，并返回其响应
FR8: 支持透传 Session-ID 请求头及完整请求体/响应体
FR9: 外部代理 URL 可配置（如环境变量 `LLM_PROXY_URL`）
FR10: 仿真服务实现全部 15 个端点（5 个地标接口 + 8 个房源查询接口 + 2 个统计/初始化 + 3 个操作接口），响应格式与真实 API 完全兼容（`{"code": 0, "message": "success", "data": {...}}`）
FR11: `/api/houses/by_platform` 支持全部 20+ 查询参数动态筛选（district、area、min_price、max_price、bedrooms、rental_type、decoration、orientation、elevator、min_area、max_area、subway_line、max_subway_dist、subway_station、commute_to_xierqi_max、available_from_before）；支持 sort_by（price/area/subway）、sort_order（asc/desc）与 page/page_size 分页
FR12: `/api/houses/nearby` 基于 Haversine 公式计算地标与房源的直线距离，筛选 max_distance 范围内的可租房源，返回 distance_to_landmark（米）、walking_distance（米）、walking_duration（分钟）字段
FR13: 租赁操作（/rent、/terminate、/offline）更新内存中的房源状态；`/api/houses/init` 将全部房源状态重置至 fixture 初始值；实现为全局单一 MockState（架构简化，不做 per-user 隔离）
FR14: 内置 fixture 数据集：地标 ≥ 20 条（覆盖 subway/company/landmark 三类，≥ 5 个行政区）；房源 ≥ 30 条（≥ 6 个行政区，含 1/2/3 居室，整租与合租均有，价格跨度 1500–15000 元/月，初始约 90% available / 5% rented / 5% offline）
FR15: 房源接口缺少 X-User-ID 时返回 400；租赁操作缺少 listing_platform 时返回 400；按 ID 查询不存在的房源时返回 404；行为与真实 API 规范一致
FR16: 同一房源三平台独立定价（安居客 100% / 链家 92% / 58同城 78%），fixture 存储安居客基准价，查询时按平台系数计算；listing_platform 未传时默认返回安居客数据
FR17: 支持从 YAML 或 JSON 配置文件加载测试用例
FR18: 每个用例需包含：id、type（Chat/Single/Multi）、messages（输入列表）
FR19: 每个用例可配置 expect 规则：has_response、response_not_empty、response_json_valid、houses_match、house_count_min、status_success 等
FR20: 支持 houses_match 的多种模式：精确匹配、子集匹配、包含匹配
FR21: 执行结束后输出每个用例的通过/失败状态及失败原因
FR22: 支持 `--case <id>` 执行单个用例，`--all` 执行全部用例，`--tag <tag>` 按标签筛选
FR23: （Post-MVP / Phase 3）可选：支持时间片计算与预算控制，与竞赛规则对齐

### NonFunctional Requirements

NFR1: 单用例执行超时可配置（默认 60 秒），超时则判定该用例失败（TIMEOUT）
NFR4: 仿真服务响应格式与 docs/interface_simulate.md 定义的 15 个端点规范完全兼容（包括字段名、数据类型、错误码）—— 最高优先级
NFR5: 模型代理与 OpenAI Chat Completions API 格式兼容（model、messages、tools、tool_calls、stream 字段完整透传）
NFR6: 仿真服务在无网络环境下可启动并完整响应所有 15 个端点，不依赖任何外部服务、数据库或文件系统写入
NFR7: 配置文件具备清晰的注释和示例，新用例可在 5 分钟内添加
NFR8: 测试报告输出为人类可读格式（控制台实时输出 + JSON 结构化报告文件）
NFR10: Mock 服务在未匹配到路由时，应返回明确错误（HTTP 200 + code: 404），避免 5xx 导致 Agent 异常

### Additional Requirements

- **技术栈**: Python 3.11+，FastAPI + uvicorn + httpx + PyYAML + Pydantic，asyncio 贯穿全链路
- **mock_rental.py 架构**: 为每个 API 端点编写独立 FastAPI 路由处理器（程序化实现），不使用静态规则匹配；MockState 通过 app.state 注入
- **MockState 类**: 全局内存状态字典 `{house_id: house_dict}`，提供 `init()` 和 `update_status()` 方法；架构明确延迟 per-user 隔离
- **config.py 更新**: 移除旧 MockRule 模型和 load_mock_data()；新增 `load_fixtures(path) -> dict`，返回 `{"landmarks": [...], "houses": [...]}`
- **Fixture 数据格式**: `mock_data/default.yaml` 存储 YAML 原始数据（landmarks list + houses list），非 MockRule 格式；fixture 存储安居客基准价，运行时乘系数
- **路由处理器统一模式**: 过滤（status == available）→ 逐参数过滤 → 排序 → 平台定价 → 计算 total → 分页切片 → 返回标准格式
- **断言引擎**: ASSERTION_RULES dict，规则名 → 检查函数 `(response: dict, expected: Any) -> (bool, str)`
- **测试报告**: 控制台文本（实时逐用例输出）+ JSON 文件（含 meta/summary/cases 完整结构）
- **单向导入链**: main → runner/model_proxy/mock_rental → config（禁止循环依赖）
- **实现顺序（Architecture）**: fixture 数据 → MockState + mock_rental → runner → main

### FR Coverage Map

FR1  → Epic 2, Story 2.1 — send_message Chat 客户端
FR2  → Epic 2, Story 2.1 — 逐轮顺序发送，await 响应
FR3  → Epic 2, Story 2.1 — session_id 格式 `test-{case.id}-{unix_timestamp}`
FR4  → Epic 1, Story 1.1 — SimulatorConfig.agent_base_url
FR5  → Epic 1, Story 1.1 — SimulatorConfig.model_proxy_port / model_ip
FR6  → Epic 1, Story 1.1 — model_proxy.py 端口配置（已有实现，config 确认）
FR7  → Epic 1, Story 1.1 — model_proxy.py LLM 转发（已有实现）
FR8  → Epic 1, Story 1.1 — Session-ID 透传（已有实现）
FR9  → Epic 1, Story 1.1 — SimulatorConfig.llm_proxy_url
FR10 → Epic 1, Story 1.2 — 15 端点路由注册，统一响应格式
FR11 → Epic 1, Story 1.2 — by_platform 20+ 查询参数动态筛选 + 分页
FR12 → Epic 1, Story 1.2 — nearby Haversine 距离计算 + 距离字段
FR13 → Epic 1, Story 1.2 — MockState init/rent/terminate/offline
FR14 → Epic 1, Story 1.1 — mock_data/default.yaml fixture 数据（≥20 地标 + ≥30 房源）
FR15 → Epic 1, Story 1.2 — 400（缺 X-User-ID / listing_platform）+ 404（房源不存在）
FR16 → Epic 1, Story 1.2 — 三平台定价系数 PRICE_RATIO
FR17 → Epic 2, Story 2.1 — YAML 用例加载（TestCase Pydantic 模型）
FR18 → Epic 2, Story 2.1 — TestCase: id/type/messages 字段
FR19 → Epic 2, Story 2.1 — ExpectRules + ASSERTION_RULES
FR20 → Epic 2, Story 2.1 — houses_match 精确/子集/包含三种断言函数
FR21 → Epic 2, Story 2.1 — print_case_result + CaseResult.status
FR22 → Epic 2, Story 2.2 — argparse --case / --all / --tag
FR23 → ❌ 延至 Phase 3（Post-MVP，超出当前范围）

## Epic List

### Epic 1: 可运行的仿真服务环境

开发者 LJW 能够一键启动测试仿真器，Agent 的模型推理请求和全部 15 个工具调用端点均有本地服务接收和响应，仿真数据覆盖动态筛选、地理距离、有状态租赁操作、三平台定价，完整替代竞赛平台的下游角色——无需外网，无需真实 API。

**FRs covered:** FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16
**NFRs covered:** NFR4, NFR5, NFR6, NFR10

### Epic 2: 测试执行与结果判定

开发者 LJW 能够通过命令行驱动 Agent 完成多轮对话，断言引擎自动判定每个用例通过或失败，控制台实时反馈进度，JSON 报告文件记录完整结果，支持单用例、全量、标签筛选三种执行模式。

**FRs covered:** FR1, FR2, FR3, FR17, FR18, FR19, FR20, FR21, FR22
**NFRs covered:** NFR1, NFR7, NFR8

### Epic 3: 开箱即用示例与端到端验证

开发者 LJW 克隆仓库后，仅需配置 llm_proxy_url 即可立即运行 `python main.py --all`，内置三类带注释的标准测试用例（Chat/Single/Multi）与完整配置示例，首次运行即可验证全链路正常工作。

**FRs covered:** FR17, FR18（示例数据驱动）
**NFRs covered:** NFR7

---

## Epic 1: 可运行的仿真服务环境

开发者 LJW 能够一键启动测试仿真器，Agent 的模型推理请求和全部 15 个工具调用端点均有本地服务接收和响应，仿真数据覆盖动态筛选、地理距离、有状态租赁操作、三平台定价，完整替代竞赛平台的下游角色——无需外网，无需真实 API。

### Story 1.1: 配置系统与 Fixture 数据架构

As a developer (LJW),
I want an updated configuration system and a complete fixture dataset loaded at startup,
So that all simulator components can read type-validated settings from a unified config, and the Mock Rental API has rich, realistic in-memory data to serve dynamic queries against.

**Acceptance Criteria:**

**Given** `config.py` is inspected after update,
**When** `SimulatorConfig` Pydantic model is reviewed,
**Then** it contains all required fields: `agent_base_url: str`, `model_proxy_port: int`, `llm_proxy_url: str`, `llm_api_key: str`, `mock_rental_port: int`, `fixture_file: str`, `test_user_id: str`, `test_cases_file: str`, `timeout_per_case: int`, `report_dir: str`; and does NOT contain `rental_mode`, `rental_passthrough_url`, or `MockRule` model

**Given** a valid `config.yaml` with all required fields,
**When** `load_config(path)` is called,
**Then** a `SimulatorConfig` is returned with all fields correctly typed and validated; any missing required field raises `ValidationError` with the field name included in the error message

**Given** `load_fixtures(path)` is called with the path to `mock_data/default.yaml`,
**When** the file is loaded,
**Then** a dict `{"landmarks": list[dict], "houses": list[dict]}` is returned; `landmarks` contains ≥ 20 entries each with fields `id`, `name`, `category` (subway/company/landmark), `district`, `longitude: float`, `latitude: float`; `houses` contains ≥ 30 entries each with fields `house_id`, `community`, `district`, `area`, `price: int` (安居客基准价), `status` (available/rented/offline), `longitude: float`, `latitude: float`, `bedrooms: int`, `rental_type`, `decoration`, `orientation`, `elevator: bool`

**Given** fixture data is loaded,
**When** the `houses` list is inspected for coverage,
**Then** all of the following are true: district coverage spans ≥ 6 行政区; bedroom variants include 1、2 and 3 bedrooms; rental_type includes both 整租 and 合租; price range spans 1500–15000 元/月; initial status distribution: ≥ 85% available, at least 1 rented, at least 1 offline; all house_id values follow the "HF_NNN" format

**Given** fixture data is loaded,
**When** the `landmarks` list is inspected for coverage,
**Then** all of the following are true: district coverage spans ≥ 5 行政区; all three categories represented: subway (SS_NNN), company (F500_NNN), landmark (LM_NNN); each landmark entry includes `longitude` and `latitude` for geo-distance calculation

**Given** `CaseResult` and `TokenUsage` models are defined in `config.py`,
**When** inspected,
**Then** `CaseResult` has: `case_id: str`, `case_type: str`, `status: str` (PASS/FAIL/ERROR/TIMEOUT), `duration_ms: int`, `rounds: int`, `failure_reason: str | None`, `actual_response: str | None`, `token_usage: TokenUsage | None`; and `TokenUsage` has: `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`

---

### Story 1.2: Mock 租房 API 全量程序化实现

As a developer (LJW),
I want a fully programmatic Mock Rental API with all 15 endpoints that dynamically respond using in-memory fixture data,
So that the Agent under test can exercise every tool call—complex filtering, geo-proximity search, stateful rental operations, and multi-platform pricing—against a locally-running service that behaves identically to the real competition API, with zero external dependencies.

**Acceptance Criteria:**

**Given** `create_mock_rental_app(config, fixtures)` is called in `mock_rental.py`,
**When** the returned FastAPI app is inspected,
**Then** routes are registered for all 15 endpoints:
地标（无状态）：`GET /api/landmarks`、`GET /api/landmarks/name/{name}`、`GET /api/landmarks/search`、`GET /api/landmarks/{id}`、`GET /api/landmarks/stats`
房源查询：`GET /api/houses/{id}`、`GET /api/houses/listings/{id}`、`GET /api/houses/by_community`、`GET /api/houses/by_platform`、`GET /api/houses/nearby`、`GET /api/houses/nearby_landmarks`、`GET /api/houses/stats`
操作：`POST /api/houses/init`、`POST /api/houses/{id}/rent`、`POST /api/houses/{id}/terminate`、`POST /api/houses/{id}/offline`

**Given** `MockState` class is defined in `mock_rental.py` and injected via `app.state.mock_state`,
**When** inspected,
**Then** it has: `__init__(fixtures: list[dict])` building `self.houses: dict[str, dict]` with `_initial_status` preserved on each entry; `init()` resetting all house statuses to their `_initial_status`; `update_status(house_id: str, new_status: str) -> dict | None` returning the updated house or None if not found; no module-level mutable global state

**Given** `GET /api/houses/by_platform` receives `listing_platform=链家`, `district=海淀`, `min_price=3000`, `max_price=8000`, `bedrooms=2`, `page=1`, `page_size=5`,
**When** the route handler processes it,
**Then** only available houses matching ALL filter criteria are returned; price in each item is 安居客基准价 × 0.92 (rounded to int); response is `{"code": 0, "message": "success", "data": {"total": N, "page": 1, "page_size": 5, "items": [...]}}` where `total` reflects the pre-pagination count

**Given** the filter execution order for `by_platform`,
**When** processing any request,
**Then** the route always applies steps in this sequence: (1) filter status == "available"; (2) apply all provided query params as AND conditions; (3) apply sort_by + sort_order; (4) apply platform pricing coefficient to price field; (5) calculate total from pre-pagination result; (6) slice by page/page_size

**Given** `GET /api/houses/nearby` receives a valid landmark `id` and `max_distance=1000` (meters),
**When** the route handler processes it using Haversine formula,
**Then** only available houses with straight-line distance ≤ 1000m from the landmark are returned; each item additionally contains: `distance_to_landmark: int` (meters, Haversine result), `walking_distance: int` (meters, = distance × 1.3, rounded), `walking_duration: int` (minutes, = walking_distance ÷ 80, rounded)

**Given** `POST /api/houses/{id}/rent` receives a request with `listing_platform=安居客` query param and any `X-User-ID` header,
**When** processed,
**Then** `mock_state.update_status(id, "rented")` is called; response is `{"code": 0, "message": "success", "data": {updated_house_dict}}`; a subsequent `GET /api/houses/{id}` returns the house with `status: "rented"`

**Given** `POST /api/houses/init` is called,
**When** processed,
**Then** `mock_state.init()` resets ALL houses to their initial fixture status; response is `{"code": 0, "message": "success", "data": {"action": "reset_user", "message": "该用户状态覆盖已清空，房源恢复为初始状态"}}`

**Given** a request to any house endpoint (queries or operations) is missing the `X-User-ID` header,
**When** processed,
**Then** HTTP 200 is returned with `{"code": 400, "message": "请提供请求头 X-User-ID 以标识当前用户"}`

**Given** a rent/terminate/offline request is missing the `listing_platform` query parameter,
**When** processed,
**Then** HTTP 200 is returned with `{"code": 400, "message": "请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台"}`

**Given** a request for a `house_id` that does not exist in fixture data,
**When** processed by any house endpoint,
**Then** HTTP 200 is returned with `{"code": 404, "message": "未找到房源 {house_id}"}`

**Given** `listing_platform` is not provided in a GET request to `by_platform` or any house query,
**When** processed,
**Then** response defaults to 安居客 pricing (coefficient 1.00) without error; `listing_platform` field in each returned item is set to "安居客"

**Given** a request to any landmark endpoint,
**When** processed,
**Then** no `X-User-ID` validation is performed; landmark endpoints are stateless, reading directly from fixture data without touching MockState

---

## Epic 2: 测试执行与结果判定

开发者 LJW 能够通过命令行驱动 Agent 完成多轮对话，断言引擎自动判定每个用例通过或失败，控制台实时反馈进度，JSON 报告文件记录完整结果，支持单用例、全量、标签筛选三种执行模式。

### Story 2.1: Test Runner 与断言引擎

As a developer (LJW),
I want a Test Runner that sequentially drives multi-round chat with the Agent and an assertion engine that validates outcomes against configured expect rules,
So that I can automatically verify whether the Agent produces correct responses for each test case, with precise PASS/FAIL/ERROR/TIMEOUT verdicts and human-readable failure details that pinpoint exactly what went wrong.

**Acceptance Criteria:**

**Given** `run_single_case(case, config, client, token_counter)` is called in `runner.py` with a `TestCase` having `messages: ["你好", "帮我找房"]`,
**When** executed against a running Agent,
**Then** `send_message()` is called sequentially for each message; each call `await`s the Agent's HTTP response before proceeding to the next round; the returned `CaseResult` has `rounds` equal to the number of messages sent

**Given** `send_message(client, agent_base_url, session_id, model_ip, message)` is called,
**When** the HTTP POST is made,
**Then** the request goes to `{agent_base_url}/api/v1/chat` with body `{"model_ip": model_ip, "session_id": session_id, "message": message}`; `session_id` follows format `test-{case.id}-{unix_timestamp}` and is unique per case execution (FR1, FR3, FR5)

**Given** `ASSERTION_RULES` dict is defined in `runner.py`,
**When** inspected,
**Then** it maps these exact keys to callable functions: `has_response`, `response_not_empty`, `response_json_valid`, `houses_match`, `houses_match_subset`, `house_count_min`, `status_success`

**Given** any assertion function `fn(response: dict, expected: Any)` is called,
**When** executing with any input,
**Then** it always returns `(bool, str)` — never raises an exception; the string is `""` on pass; the string contains a human-readable failure description on fail (NFR8)

**Given** `expect: {houses_match: ["HF_42", "HF_107"]}` and the Agent response `response` field contains JSON `{"houses": ["HF_42"]}`,
**When** the `houses_match` assertion runs,
**Then** it returns `(False, "houses_match: expected ['HF_42', 'HF_107'], got ['HF_42']")`

**Given** `expect: {houses_match_subset: true}` and expected house IDs (configured in the test case) are all present in the Agent's `houses` list,
**When** `houses_match_subset` assertion runs,
**Then** it returns `(True, "")` confirming `set(expected_ids) ⊆ set(actual_houses)` (FR20)

**Given** a test case execution exceeds `config.timeout_per_case` seconds,
**When** wrapped in `asyncio.wait_for(run_single_case(...), timeout=config.timeout_per_case)`,
**Then** `CaseResult(status="TIMEOUT", failure_reason="超时 {N}s", rounds=0, duration_ms=N*1000)` is returned (NFR1)

**Given** the Agent service is unreachable (connection refused),
**When** `send_message()` raises `httpx.ConnectError`,
**Then** `CaseResult(status="ERROR", failure_reason="Chat 不通: {error_detail}")` is returned; the runner loop continues to the next case without crashing

**Given** a completed `CaseResult` with status PASS,
**When** `print_case_result(idx, total, result)` is called,
**Then** stdout shows `[{idx}/{total}] {case_id} ...... PASS  ({duration}s)`

**Given** a completed `CaseResult` with status FAIL or ERROR or TIMEOUT,
**When** `print_case_result(idx, total, result)` is called,
**Then** stdout shows `[{idx}/{total}] {case_id} ...... FAIL  ({duration}s)` followed by `       ✗ {failure_reason}` on the next line

---

### Story 2.2: CLI 入口、服务编排与报告生成

As a developer (LJW),
I want a single `python main.py` command that orchestrates all services, runs the selected test cases, and saves structured reports,
So that I can execute a full regression or a targeted test with one command and get both real-time console feedback and a persistent, machine-readable report file for later analysis.

**Acceptance Criteria:**

**Given** `python main.py --all` is run,
**When** `main()` executes,
**Then** the following happens in order: (1) `config.yaml`, `test_cases.yaml`, and fixture file are loaded; (2) `token_counter` shared state object is created; (3) Model Proxy and Mock Rental API are started as background `asyncio.create_task` coroutines on their configured ports; (4) readiness wait (`asyncio.sleep(0.5)` or equivalent) completes; (5) all test cases run sequentially via `run_all_cases()`; (6) `generate_reports()` is called; (7) both services are shut down cleanly

**Given** `python main.py --case chat_hello` is run,
**When** executed,
**Then** only the test case with `id == "chat_hello"` is executed; console shows `[1/1]` progress; all other cases are skipped (FR22)

**Given** `python main.py --tag smoke` is run,
**When** executed,
**Then** only test cases whose `tags` list contains `"smoke"` are executed; case count reflects only tagged cases (FR22)

**Given** all test cases complete,
**When** `generate_reports(results, config)` is called,
**Then** a JSON file is saved to `{config.report_dir}/report-{YYYY-MM-DD-HHmmss}.json` containing: `meta` (run_id, timestamp, agent_base_url, total_duration_ms), `summary` (total, passed, failed, pass_rate), `cases` array with full `CaseResult` data per case (NFR8)

**Given** all test cases complete,
**When** the Markdown report is also generated,
**Then** a `.md` file is saved to `{config.report_dir}/` containing a summary table (case_id, type, status, duration_ms, failure_reason) and a totals line `N passed, M failed`

**Given** an unhandled exception occurs anywhere in `main()` after tests have started,
**When** the exception propagates,
**Then** the `finally` block calls `generate_reports(completed_results_so_far, config)` and prints the partial summary before the process exits (NFR11)

**Given** `python main.py --help` is run,
**When** processed by argparse,
**Then** usage output shows all three options: `--all`, `--case <id>`, `--tag <tag>` with descriptions

**Given** all cases complete and reports are saved,
**When** the console summary is printed,
**Then** stdout shows `Results: N passed, M failed ({total_duration}s total)` followed by `Report: {report_dir}/report-{timestamp}.json`

---

## Epic 3: 开箱即用示例与端到端验证

开发者 LJW 克隆仓库后，仅需配置 llm_proxy_url 即可立即运行 `python main.py --all`，内置三类带注释的标准测试用例（Chat/Single/Multi）与完整配置示例，首次运行即可验证全链路正常工作。

### Story 3.1: 示例配置文件与端到端冒烟验证

As a developer (LJW),
I want complete, annotated example configuration files and three ready-to-run sample test cases covering all case types,
So that after setting `llm_proxy_url` in config.yaml I can immediately run `python main.py --all` and verify the full Chat→Agent→ModelProxy→MockRental→Assertion chain is working correctly without writing any configuration from scratch.

**Acceptance Criteria:**

**Given** `config.yaml` is opened by a new developer,
**When** read top-to-bottom,
**Then** every configuration field has an inline comment explaining: its purpose, accepted values/format, and the default or example value — for example: `# timeout_per_case: 60  # 单用例最大执行时间（秒），超时判定为 TIMEOUT` (NFR7)

**Given** `test_cases.yaml` is loaded by `load_test_cases()`,
**When** processed,
**Then** it contains exactly these three sample cases with tags:
- `id: chat_hello`, `type: Chat`, `messages: ["你好"]`, `expect: {has_response: true, response_not_empty: true}`, `tags: ["smoke"]`
- `id: single_haidian_2br`, `type: Single`, `messages: ["帮我找海淀区两居室，月租8000以内"]`, `expect: {response_json_valid: true, houses_match_subset: true, house_count_min: 1}`, `tags: ["smoke", "single"]`
- `id: multi_progressive`, `type: Multi`, `messages: ["我想在朝阳区找房", "预算6000以内", "近地铁的", "给我看看具体有哪些"]`, `expect: {response_json_valid: true, houses_match_subset: true}`, `tags: ["smoke", "multi"]`

**Given** a running Agent at `http://localhost:8191` and valid `llm_proxy_url` in `config.yaml`,
**When** `python main.py --all` is executed,
**Then** all three sample cases execute to a terminal state (PASS, FAIL, or TIMEOUT — never ERROR due to missing config or missing mock data); console shows `[1/3]`, `[2/3]`, `[3/3]` progress lines followed by a summary

**Given** the final run completes,
**When** the console summary is printed,
**Then** it shows `Results: N passed, M failed ({total_duration}s total)` followed by `Report: {report_dir}/report-{timestamp}.json` so LJW knows where to find the full report

**Given** `python main.py --tag smoke` is run,
**When** executed,
**Then** all three sample cases (all tagged "smoke") are selected and executed, showing `[1/3]`, `[2/3]`, `[3/3]` progress
