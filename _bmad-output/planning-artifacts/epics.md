---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# AI Agent Coding - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for AI Agent Coding, decomposing the requirements from the PRD and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: 用户可通过 `POST /api/v1/chat` 发送自然语言消息，系统在 200 响应中返回 Agent 回复
FR2: 系统可在同一 `session_id` 下跨轮次完整保留所有对话历史（system + user + assistant + tool results）
FR3: 系统可对不同 `session_id` 的对话历史进行严格隔离，不同 session 间数据不互通
FR4: 系统可在新 `session_id` 首条消息时自动调用 `POST /api/houses/init` 重置房源数据
FR5: 系统可区分聊天类消息与房源查询类消息，分别返回自然语言字符串和 JSON 字符串格式响应
FR6: 用户可按北京行政区（海淀、朝阳、通州等）筛选可租房源
FR7: 用户可按月租金范围（最低价/最高价）筛选可租房源
FR8: 用户可按户型（整租/合租/一居至四居）筛选可租房源
FR9: 用户可按装修类型（精装/简装/豪华/毛坯/空房）筛选可租房源
FR10: 用户可按朝向（朝南/朝北/南北通透等）筛选可租房源
FR11: 用户可按地铁距离（如 800 米以内近地铁）筛选可租房源
FR12: 系统可对分页结果自动获取完整数据集（首页后自动拉取剩余页，上限 5 页 / 50 条）
FR13: 用户可获取单套房源的完整详细信息（地址、户型、面积、租金、装修、朝向、楼层、设施列表、噪音评级、标签）
FR14: 用户可按地标名称或关键词搜索地铁站、公司、商圈等地标，获取地标 ID 和位置信息
FR15: 用户可查询以指定地标为中心、指定距离范围内的可租房源（含步行距离和时间）
FR16: 用户可查询指定小区 1000 米范围内的生活配套信息（含商超、公园、餐饮等类别）及步行距离
FR17: 用户可对指定房源执行租房操作，系统调用 `POST /api/houses/{id}/rent` 完成状态变更（而非文字回复）
FR18: 用户可对已租房源执行退租操作，系统调用 `POST /api/houses/{id}/terminate` 完成状态变更
FR19: 用户可对指定房源执行下架操作，系统调用 `POST /api/houses/{id}/offline` 完成状态变更
FR20: 系统可在房源查询完成时，将 `response` 字段输出为合法 JSON 字符串，结构为 `{"message": "自然语言推荐说明", "houses": ["HF_x", ...]}`，支持非 ASCII 字符
FR21: 系统可在聊天类响应时，将 `response` 字段输出为纯自然语言字符串，不含任何 JSON 结构
FR22: 系统可确保 `houses` 字段仅包含有效房源 ID（格式如 `"HF_x"`），数量不超过 5 个
FR23: 系统可在容器启动 5 秒内完成初始化，绑定 `0.0.0.0:8191`，不在启动时执行外部 API 调用
FR24: 系统可以结构化格式记录关键事件日志，每条日志包含 timestamp、session_id、event_type 和 details 字段，覆盖 session 启动、工具调用（名称与参数）、模型响应摘要三类事件
FR25: 系统可在所有外部 API 调用（模型 API + 租房 API）异常时，返回 `status="error"` 响应，不向外抛出 HTTP 异常

### NonFunctional Requirements

NFR1: 单用例非模型代码执行时间 < 5 秒（不含模型调用耗时），超出则判题系统判定该用例失败
NFR2: 系统提示 Token 数 ≤ 800，以控制时间片消耗；每个用例目标时间片消耗 ≤ 5 片
NFR3: Tool Calling Loop 每用例最多执行 10 次迭代，防止无限循环耗尽全局时间片预算（300 片）
NFR4: 服务器响应 `duration_ms` 字段反映真实壁钟处理时间，误差 ≤ 10ms
NFR5: 所有 `/api/houses/*` 请求必须携带正确的 `X-User-ID` 请求头（平台注册工号）；地标接口 `/api/landmarks/*` 无需此头
NFR6: 模型 API 调用使用 OpenAI 兼容格式，`model` 字段可为空字符串，`api_key` 必须为非空占位符字符串
NFR7: HTTP 客户端连接在服务生命周期内保持复用，不在单次请求处理中重新创建
NFR8: `POST /api/v1/chat` 接口可用率 100%，所有外部 API 调用异常必须被捕获并返回 `status="error"` 响应，不得向外暴露 HTTP 5xx 错误
NFR9: `response` 字段 JSON 格式正确率 100%（房源查询场景），可通过 `json.loads(response)` 验证
NFR10: 不同 `session_id` 之间的会话历史隔离率 100%，任何实现不得允许跨 session 数据泄露

### Additional Requirements

**来自 Architecture — 项目初始化与结构：**
- 自定义极简 scaffold：`main.py`（路由层）+ `tools.py`（工具层）+ `agent.py`（Agent Loop）+ `requirements.txt` + `README.md`
- Python 3.11+，全链路 async/await
- 依赖极简：`fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `pydantic`
- 模块导入方向单向：`main.py → agent.py → tools.py`（禁止循环导入）

**来自 Architecture — Format Guard 实现约束：**
- Format Guard 触发条件：本轮 Loop 中调用了 `search_houses` 或 `search_nearby_landmark` 任一工具
- 判断方式：代码维护 `tools_called: set[str]`，基于 `HOUSE_SEARCH_TOOLS` 集合判断，禁止正则解析模型文本
- `houses` 字段最多 5 个有效 ID；`json.dumps(..., ensure_ascii=False)` 输出

**来自 Architecture — TOOLS 常量约束：**
- `TOOLS` 常量定义在 `tools.py` 顶层，不在请求处理函数内动态构建
- TOOLS 中每个工具的 `"name"` 字段必须与对应 Python 函数名完全一致
- `listing_platform` 枚举统一：`["链家", "安居客", "58同城"]`，默认 `"安居客"`

**来自 Architecture — SYSTEM_PROMPT 约束：**
- `SYSTEM_PROMPT` 定义在 `agent.py` 顶层，≤ 800 Token（约 ≤ 500 中文字符）
- 必含：角色定义、工具调用指令、意图分类指令（聊天直接回复/操作必须调用工具）、格式指令（不自行生成 JSON）
- 禁止：预设房源 ID、调用外部模型指令

**来自 Architecture — Agent Loop 约束：**
- `while` 循环 + 迭代计数器，退出条件按优先级：① `iterations >= 10` → 返回 error；② `finish_reason == "stop"` 且无 tool_calls → 正常退出
- tool message `content` 字段必须是字符串（`json.dumps` 转换），不得传递 Python dict

**来自 Architecture — Session 管理约束：**
- 全局 `sessions: dict[str, list]`，key = session_id，value = 消息历史列表
- 新 Session init 时序：先 `await init_houses(client)` → 再构建 system message → 再 append user message → 再 `run_agent()`

**来自 Architecture — httpx.AsyncClient 约束：**
- `httpx.AsyncClient(base_url="http://7.225.29.223:8080", timeout=30.0)` 通过 FastAPI `lifespan` 创建，全生命周期复用
- `USER_ID = os.environ["USER_ID"]`，在 `tools.py` 模块加载时读取一次

**来自 Architecture — 翻页实现约束：**
- `search_houses` 工具内部串行翻页，`while len(all_items) < total and page <= 5` 循环，对 agent loop 完全透明

**来自 Architecture — 异常处理约束：**
- 双层异常捕获：路由层（main.py）全局 `try/except`；工具层（tools.py）每个工具函数内部 `try/except`，返回 `{"error": "..."}` 而非 raise
- 永远返回 HTTP 200，不得向外暴露 5xx

**来自 Architecture — 日志约束：**
- `log_event(event_type, session_id, details)` 使用 `json.dumps` 格式化输出
- 覆盖事件：`SESSION_START`、`SESSION_INIT`、`TOOL_CALL`、`MODEL_RESPONSE`、`ERROR`

### FR Coverage Map

FR1  → Epic 1（POST /api/v1/chat 接口）
FR2  → Epic 2（Session 历史持久化）
FR3  → Epic 2（Session 隔离）
FR4  → Epic 2（新 Session init 钩子）
FR5  → Epic 2（意图分类：聊天/查询）
FR6  → Epic 3（按区域筛选）
FR7  → Epic 3（按价格范围筛选）
FR8  → Epic 3（按户型筛选）
FR9  → Epic 3（按装修类型筛选）
FR10 → Epic 3（按朝向筛选）
FR11 → Epic 3（按地铁距离筛选）
FR12 → Epic 3（自动翻页）
FR13 → Epic 3（单房源详情）
FR14 → Epic 3（地标搜索）
FR15 → Epic 3（地标附近房源）
FR16 → Epic 3（周边配套查询）
FR17 → Epic 3（租房操作）
FR18 → Epic 3（退租操作）
FR19 → Epic 3（下架操作）
FR20 → Epic 2（房源查询 JSON 格式守卫）
FR21 → Epic 2（聊天纯自然语言响应）
FR22 → Epic 2（houses 最多 5 条有效 ID）
FR23 → Epic 1（5 秒内启动）
FR24 → Epic 4（结构化日志）
FR25 → Epic 1（全局异常捕获）

## Epic List

### Epic 1: 项目脚手架与 API 服务基础
用户（判题系统/开发者）可以向 `POST /api/v1/chat` 发送消息并收到 HTTP 200 响应；服务在 5 秒内完成启动，具备基础错误处理和 HTTP 客户端管理能力。
**FRs covered:** FR1, FR23, FR25
**NFRs covered:** NFR4, NFR7, NFR8
**架构额外要求：** 三文件 scaffold 初始化、lifespan 上下文、Pydantic 请求/响应模型、双层异常捕获框架

### Epic 2: 会话管理与核心 Agent Loop
用户可以进行多轮对话，Agent 完整保留对话历史、隔离不同 session；Agent 内部 LLM Tool Calling Loop 正确运行，格式守卫准确区分聊天响应（纯文本）与房源查询响应（合法 JSON）。
**FRs covered:** FR2, FR3, FR4, FR5, FR20, FR21, FR22
**NFRs covered:** NFR2, NFR3, NFR6, NFR9, NFR10
**架构额外要求：** SYSTEM_PROMPT（≤800 Token）、TOOL_DISPATCH 表、HOUSE_SEARCH_TOOLS 集合、tools_called 追踪、Loop 退出条件、Session init 时序

### Epic 3: 工具层全量实现
tools.py 全部 6 个工具函数一次性实现完毕：房源搜索（多条件 + 翻页）、房源详情、地标搜索、地标附近房源、周边生活配套、租赁操作执行；所有工具共享同一基础架构（TOOLS 常量、_get_headers()、USER_ID）。
**FRs covered:** FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16, FR17, FR18, FR19
**NFRs covered:** NFR1, NFR5
**架构额外要求：** TOOLS 常量 + 函数名一致性、listing_platform 枚举统一、X-User-ID 注入、`search_houses`（串行翻页）、`get_house_detail`、`search_landmark`（无需 X-User-ID）、`search_nearby_landmark`、`get_nearby_amenities`、`execute_action`（action: rent/terminate/offline）

### Epic 4: 结构化日志与系统可观测性
开发者可通过结构化日志追踪每个请求的完整执行链路（session start / tool call / model response / error），便于打榜失分后快速定位问题工具和路径。
**FRs covered:** FR24
**NFRs covered:** NFR1, NFR4
**架构额外要求：** `log_event()` 函数（JSON 格式）、5 种 event_type 常量（SESSION_START / SESSION_INIT / TOOL_CALL / MODEL_RESPONSE / ERROR）

---

## Epic 1: 项目脚手架与 API 服务基础

用户（判题系统/开发者）可以向 `POST /api/v1/chat` 发送消息并收到 HTTP 200 响应；服务在 5 秒内完成启动，HTTP 客户端全生命周期复用，所有异常被捕获不向外抛出 5xx。

### Story 1.1: 项目文件结构初始化

As a developer,
I want the project scaffolded with the correct three-file structure and all dependencies declared,
So that there is a clean, runnable starting point with all required packages.

**Acceptance Criteria:**

**Given** a new empty project directory
**When** the initialization commands are run
**Then** the following 5 files exist in the project root: `main.py`, `tools.py`, `agent.py`, `requirements.txt`, `README.md`
**And** `requirements.txt` contains exactly: `fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `pydantic`
**And** running `pip install -r requirements.txt` completes without errors
**And** `README.md` includes the startup command `uvicorn main:app --host 0.0.0.0 --port 8191` and at least one smoke test curl example

---

### Story 1.2: Pydantic 请求与响应数据模型

As the judging system,
I want the API to accept and return strictly validated JSON structures,
So that all requests and responses are type-safe and predictable.

**Acceptance Criteria:**

**Given** `main.py` is being defined
**When** the Pydantic models are implemented
**Then** `ChatRequest` contains fields: `model_ip: str`, `session_id: str`, `message: str`
**And** `ChatResponse` contains fields: `session_id: str`, `response: str`, `status: str`, `tool_results: list`, `timestamp: int`, `duration_ms: int`
**And** `ToolResult` model exists with at minimum `tool_name: str` and `result: str` fields
**And** all models use PascalCase naming convention
**And** FastAPI can serialize `ChatResponse` to JSON automatically

---

### Story 1.3: FastAPI lifespan 与 HTTP 客户端全生命周期管理

As the system,
I want the `httpx.AsyncClient` to be created once at startup and shared across all requests,
So that connection overhead is minimized and NFR7 (client reuse) is satisfied.

**Acceptance Criteria:**

**Given** the FastAPI app is initialized with a `lifespan` context manager
**When** the service starts
**Then** `httpx.AsyncClient(base_url="http://7.225.29.223:8080", timeout=30.0)` is created exactly once and accessible to tool functions
**And** no external API calls are made during startup
**When** the service shuts down
**Then** `await client.aclose()` is called to properly release connections
**And** the client is NOT re-created inside any per-request handler function

---

### Story 1.4: POST /api/v1/chat 路由与全局异常捕获

As the judging system,
I want the chat endpoint to always return HTTP 200 regardless of any internal error,
So that the judging system never encounters unhandled HTTP 5xx responses that would break scoring.

**Acceptance Criteria:**

**Given** the service is running on `0.0.0.0:8191`
**When** `POST /api/v1/chat` is called with a valid `ChatRequest` JSON body
**Then** the response is always HTTP 200 with a `ChatResponse` JSON body
**And** `status` field is either `"success"` or `"error"`
**And** `timestamp` is a Unix integer (`int(time.time())`)
**And** `duration_ms` reflects real wall-clock processing time with error ≤ 10ms (NFR4)

**Given** an unhandled exception occurs anywhere in request processing
**When** the global `try/except` in the route handler catches it
**Then** the response is still HTTP 200 with `status="error"` and the error description in `response`
**And** no HTTP 5xx is ever returned (NFR8)

**Given** the startup command `uvicorn main:app --host 0.0.0.0 --port 8191` is run
**When** it completes initialization
**Then** the service is fully ready to accept requests within 5 seconds (FR23)

---

## Epic 2: 会话管理与核心 Agent Loop

用户可以进行多轮对话，Agent 完整保留对话历史、隔离不同 session；Agent 内部 LLM Tool Calling Loop 正确运行，格式守卫准确区分聊天响应（纯文本）与房源查询响应（合法 JSON）。

### Story 2.1: Session 内存存储与跨请求历史持久化

As a user in a multi-turn conversation,
I want my previous messages and agent responses to be remembered across multiple API calls,
So that the agent can understand context and refine results without me repeating myself.

**Acceptance Criteria:**

**Given** a `session_id` that has been used before
**When** a new message is sent with the same `session_id`
**Then** the full conversation history (all previous user + assistant + tool messages) is included in the next LLM call
**And** the history is stored as a list of OpenAI-format message dicts: `[{"role": "...", "content": "..."}]`
**And** `sessions: dict[str, list]` is defined as a module-level variable in `main.py`

**Given** two different `session_id` values are used
**When** each sends messages independently
**Then** their histories are completely independent with no data crossover (FR3, NFR10)

---

### Story 2.2: 新 Session 数据初始化钩子

As the judging system,
I want house data to be reset automatically when a new test case begins,
So that each test case starts with a clean, consistent data state.

**Acceptance Criteria:**

**Given** a `session_id` that has never been seen before
**When** the first message arrives with that `session_id`
**Then** `POST /api/houses/init` is called and awaited **before** any other processing (FR4)
**And** the init call uses the `httpx.AsyncClient` from lifespan (not a new client)
**And** the init call includes the `X-User-ID` header with the value from `os.environ["USER_ID"]`
**And** only after the init call completes is the session history initialized and the user message appended
**And** subsequent messages on the same `session_id` do NOT trigger another init call

---

### Story 2.3: Agent Loop 完整实现

As the agent,
I want a fully functional LLM tool-calling loop with intent classification and output format enforcement,
So that the system can handle both chat and house-search requests correctly end-to-end within token and iteration budgets.

**Acceptance Criteria:**

**SYSTEM_PROMPT（NFR2）**

**Given** `agent.py` is implemented
**When** `SYSTEM_PROMPT` is defined at module top level
**Then** it contains: role definition (智能租房助手), tool-calling instruction (主动调用工具), intent classification instruction (聊天直接回复/操作必须调用工具), format instruction (不自行生成 JSON)
**And** its token count is ≤ 800 (NFR2)
**And** it contains no preset house IDs or hardcoded answers

**Agent Loop 骨架（NFR3, NFR6）**

**Given** `run_agent(history, model_ip, client)` is called
**When** the Agent Loop executes
**Then** it uses a `while` loop with an `iterations` counter initialized to 0
**And** `MAX_ITERATIONS = 10` is defined as a module-level constant
**And** if `iterations >= MAX_ITERATIONS`, the loop exits immediately and returns `status="error"` with message `"Tool call limit exceeded"` (NFR3)
**And** the OpenAI client is constructed per-call as `AsyncOpenAI(base_url=f"http://{model_ip}:8888/v1", api_key="placeholder")` (NFR6)

**Tool Dispatch 与 Tool Message 格式（FR5）**

**Given** the model returns a response with `tool_calls`
**When** each tool call is dispatched
**Then** `TOOL_DISPATCH: dict[str, Callable]` in `agent.py` is used to look up and call the correct function: `await TOOL_DISPATCH[tool_name](client, **args)`
**And** the tool result (a dict) is serialized via `json.dumps(result, ensure_ascii=False)` before being appended to history
**And** the tool message appended to history has the exact format: `{"role": "tool", "tool_call_id": call.id, "content": "<json_string>"}`
**And** `content` is ALWAYS a string, never a Python dict or None

**Given** `finish_reason == "stop"` and `message.tool_calls` is empty or None
**When** the loop evaluates exit conditions
**Then** the loop exits normally and proceeds to Format Guard

**Format Guard — 意图分类与输出格式控制（FR5, FR20, FR21, FR22, NFR9）**

**Given** the Agent Loop has completed
**When** Format Guard evaluates the response type
**Then** `HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}` is defined as a module-level constant
**And** `tools_called: set[str]` is maintained throughout the loop, adding each tool name after execution
**And** if `tools_called & HOUSE_SEARCH_TOOLS` is non-empty (house query path):
- `response` is set to `json.dumps({"message": <model_content>, "houses": [<id1>, ...]}, ensure_ascii=False)`
- `houses` contains only valid IDs matching format `"HF_x"`, maximum 5 items (FR22)
- `json.loads(response)` succeeds without error (NFR9)

**And** if `tools_called & HOUSE_SEARCH_TOOLS` is empty (chat path):
- `response` is set to the raw model `content` string (FR21)
- The response contains no JSON structure

**And** Format Guard logic is based ONLY on `tools_called` set — never on regex parsing of model text output (FR5, FR20)

---

## Epic 3: 工具层全量实现

tools.py 全部 6 个工具函数一次性实现完毕：房源搜索（多条件 + 翻页）、房源详情、地标搜索、地标附近房源、周边生活配套、租赁操作执行；所有工具共享同一基础架构（TOOLS 常量、_get_headers()、USER_ID）。

### Story 3.1: tools.py 全量工具实现

As a developer and user,
I want all tool functions implemented in `tools.py` in a single story,
So that the complete tool layer is available as one cohesive unit for the agent to use.

**Acceptance Criteria:**

**基础架构**

**Given** `tools.py` is implemented
**When** module-level constants are defined
**Then** `RENTAL_API_BASE = "http://7.225.29.223:8080"` is defined
**And** `USER_ID = os.environ["USER_ID"]` is read once at module load time
**And** `MAX_PAGES = 5` is defined as a constant
**And** a helper `_get_headers() -> dict` returns `{"X-User-ID": USER_ID}`

**When** the `TOOLS` constant is defined
**Then** it is a list of OpenAI function-calling format dicts, defined at module top level (not inside any function)
**And** each tool's `"name"` field exactly matches the corresponding Python async function name
**And** `listing_platform` parameter in `search_houses`, `search_nearby_landmark`, and `execute_action` uses the same enum: `["链家", "安居客", "58同城"]` with default `"安居客"`
**And** `TOOL_DISPATCH` in `agent.py` references all 6 tool functions imported from `tools.py`

**search_houses（FR6-FR12, NFR1, NFR5）**

**Given** the model calls `search_houses` with one or more filter parameters
**When** the tool function executes
**Then** it calls `GET /api/houses/listings/{listing_platform}` with applicable query parameters: `district`, `min_price`, `max_price`, `room_type`, `decoration`, `orientation`, `max_subway_dist`
**And** the request includes `X-User-ID` header via `_get_headers()`
**And** all filter parameters are optional; omitted ones are not sent in the query
**And** the function returns a dict with the house listings data on success
**And** on any exception, returns `{"error": "search_houses failed: <reason>"}` without raising (NFR8)

**Given** a search returns multiple pages of results
**When** the first page response indicates `total > len(first_page_items)`
**Then** additional pages are fetched serially: `page = 2, 3, ...` up to `MAX_PAGES = 5`
**And** all pages are combined into a single `items` list returned to the agent (FR12)
**And** the agent loop is completely unaware of pagination — it receives one unified result (NFR1)

**get_house_detail（FR13, NFR5）**

**Given** the model calls `get_house_detail` with a `house_id` parameter
**When** the tool function executes
**Then** it calls `GET /api/houses/{house_id}` with the `X-User-ID` header
**And** the full response JSON (address, room_type, area, rent, decoration, orientation, floor, facilities, noise_level, tags, etc.) is returned as a dict (FR13)
**And** `house_id` is treated as a string throughout (never converted to integer)
**And** on any HTTP or network exception, returns `{"error": "get_house_detail failed: <reason>"}` without raising

**search_landmark（FR14）**

**Given** the model calls `search_landmark` with a `query` parameter (and optional `category`, `district`)
**When** the tool function executes
**Then** it calls `GET /api/landmarks/search` with `query` as a query parameter, plus any provided `category` and `district`
**And** the request does NOT include an `X-User-ID` header (landmark API requires no authentication, NFR5)
**And** the response containing landmark list (each with `id`, `name`, `category`, `district`, coordinates) is returned as a dict (FR14)
**And** on any exception, returns `{"error": "search_landmark failed: <reason>"}` without raising

**search_nearby_landmark（FR15, NFR5）**

**Given** the model calls `search_nearby_landmark` with `landmark_id` and optional `max_distance`, price/room filters, `listing_platform`
**When** the tool function executes
**Then** it calls `GET /api/houses/nearby` with `landmark_id` and applicable filter parameters
**And** the request includes `X-User-ID` header via `_get_headers()` (NFR5)
**And** each result item includes walking distance and walking time to the landmark (FR15)
**And** `listing_platform` uses the same enum `["链家", "安居客", "58同城"]` with default `"安居客"`
**And** the combined result dict is returned on success
**And** on any exception, returns `{"error": "search_nearby_landmark failed: <reason>"}` without raising
**And** `search_nearby_landmark` is included in `HOUSE_SEARCH_TOOLS` set in `agent.py`, triggering Format Guard on call

**get_nearby_amenities（FR16, NFR5）**

**Given** the model calls `get_nearby_amenities` with `house_id` and optional `category`, `max_distance_m`
**When** the tool function executes
**Then** it calls `GET /api/houses/nearby_landmarks` with `house_id`, `category`, and `max_distance_m` as query parameters
**And** the request includes `X-User-ID` header via `_get_headers()`
**And** the response includes amenity items each with name, category, and walking distance in meters (FR16)
**And** `max_distance_m` defaults to 1000 if not provided
**And** the result dict is returned on success
**And** on any exception, returns `{"error": "get_nearby_amenities failed: <reason>"}` without raising
**And** `get_nearby_amenities` is NOT in `HOUSE_SEARCH_TOOLS` — its response path remains plain text

**execute_action（FR17, FR18, FR19, NFR5）**

**Given** the model calls `execute_action` with `action`, `house_id`, and `listing_platform`
**When** the tool function executes
**Then** it maps `action` to the correct API endpoint:
- `"rent"` → `POST /api/houses/{house_id}/rent`
- `"terminate"` → `POST /api/houses/{house_id}/terminate`
- `"offline"` → `POST /api/houses/{house_id}/offline`

**And** each POST request includes the `X-User-ID` header via `_get_headers()` (NFR5)
**And** `listing_platform` is sent as required by the API
**And** `listing_platform` uses the enum `["链家", "安居客", "58同城"]` consistent with other tools
**And** the API response confirming the state change is returned as a dict (FR17, FR18, FR19)
**And** `house_id` is treated as a string throughout (never converted to integer)

**Given** an invalid `action` value is passed
**When** the tool function executes
**Then** it returns `{"error": "execute_action failed: unknown action <value>"}` without raising

**Given** any HTTP or network exception occurs
**When** the request fails
**Then** the function returns `{"error": "execute_action failed: <reason>"}` without raising
**And** `execute_action` is NOT in `HOUSE_SEARCH_TOOLS` — its response path remains plain text confirmation

---

## Epic 4: 结构化日志与系统可观测性

开发者可通过结构化 JSON 日志追踪每个请求的完整执行链路（session start / tool call / model response / error），便于打榜失分后快速定位问题工具和执行路径。

### Story 4.2: log_event 结构化日志系统

As a developer,
I want every key agent event logged in structured JSON format,
So that I can trace the full execution path of any request and quickly identify which tool call caused a scoring failure after competition submission.

**Acceptance Criteria:**

**Given** `agent.py` implements a `log_event(event_type, session_id, details)` function
**When** it is called
**Then** it outputs a JSON line via `print(json.dumps({...}, ensure_ascii=False))` containing exactly: `timestamp` (Unix int), `session_id` (str), `event_type` (str), `details` (dict) (FR24)

**And** the following 5 event types are logged at the correct moments:

| event_type | Logged when |
|---|---|
| `"SESSION_START"` | A new `session_id` is first seen in `main.py` |
| `"SESSION_INIT"` | `POST /api/houses/init` is called for a new session |
| `"TOOL_CALL"` | Each tool function is dispatched, with `tool_name` and arg summary in `details` |
| `"MODEL_RESPONSE"` | Model returns a response, with `finish_reason` and first 100 chars of `content` in `details` |
| `"ERROR"` | Any caught exception, with `error` string in `details` |

**Given** a complete single-turn house search request is processed
**When** the logs are reviewed
**Then** the log sequence shows: `SESSION_START` → `SESSION_INIT` → `MODEL_RESPONSE` → `TOOL_CALL` → `MODEL_RESPONSE` in correct order
**And** each log line is valid JSON parseable by `json.loads()`
**And** different `session_id` values appear correctly in their respective log entries (no cross-contamination)
