---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
lastStep: 8
status: 'complete'
completedAt: '2026-02-27'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
  - _bmad-output/project-context.md
  - docs/interface.md
  - docs/interface_simulate.md
  - docs/task.md
workflowType: 'architecture'
project_name: 'AI Agent Coding'
user_name: 'LJW'
date: '2026-02-27'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
25 个 FR 组织为 6 个能力域：对话管理（FR1-5）、房源搜索（FR6-13）、地标与通勤（FR14-16）、租赁操作（FR17-19）、输出格式控制（FR20-22）、系统运维（FR23-25）。无前端/UI 需求，纯 API Backend。

**Non-Functional Requirements:**
10 个 NFR 跨 Performance / Integration / Reliability 三类：
- 非模型代码执行 < 5s（NFR1）
- 系统提示 ≤ 800 Token（NFR2）
- Tool Loop ≤ 10 次（NFR3）
- X-User-ID 统一注入（NFR5）
- 接口可用率 100%，全局异常捕获（NFR8）
- response JSON 格式正确率 100%（NFR9）

**Scale & Complexity:**
- Primary domain: API Backend（FastAPI + LLM Tool Calling）
- Complexity level: Medium-High
- Estimated architectural components: 4-5（路由层、Session 管理、Agent Loop、工具层、格式守卫）

### Technical Constraints & Dependencies

- 固定端口 8191，固定租房 API base URL（`http://7.225.29.223:8080`）
- 模型 IP 动态注入（每次请求），api_key 为非空占位符
- Python 3.11+，全异步（httpx.AsyncClient 全生命周期复用）
- 依赖极简：`fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `pydantic`
- 竞赛红线：禁外部模型、禁硬编码答案、X-User-ID 必须为真实工号

### Cross-Cutting Concerns Identified

1. **Format Guard** — 代码组装最终 JSON，影响所有响应路径
2. **Session 隔离 + init 钩子** — 影响每次请求处理
3. **时间片效率** — 影响工具粒度设计、系统提示长度、Loop 计数
4. **统一异常捕获** — 包裹所有 LLM + 租房 API 调用
5. **X-User-ID 注入** — 集中在工具层，不扩散到路由层
6. **模块化可更新性** — TOOLS 常量 + 系统提示模板独立存放

## Starter Template Evaluation

### Primary Technology Domain

API Backend（Python + FastAPI + LLM Tool Calling），基于竞赛约束和 `project-context.md` 技术规范，无前端/UI，无外部数据库。

### Starter Options Considered

| 选项 | 评估结果 |
|------|---------|
| cookiecutter fastapi-template | 过重：含 SQLAlchemy/OAuth/Celery，超出竞赛需要 |
| fastapi-best-practices 分层 scaffold | 过深：目录分层违背「单文件优先」约束 |
| 自定义极简三文件 scaffold | ✅ 选定：完全匹配 project-context 规则 |

### Selected Starter: 自定义极简 scaffold

**Rationale for Selection:**
竞赛环境要求极简依赖、5 秒内启动、单文件优先，所有技术选型已在 `project-context.md` 的 38 条规则中完全锁定，无需外部模板工具引入不必要复杂度。

**Project Initialization:**

```bash
mkdir ai-agent-coding
cd ai-agent-coding
touch main.py tools.py agent.py requirements.txt
python -m venv .venv && .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" openai httpx pydantic
pip freeze > requirements.txt
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:** Python 3.11+，全异步（async/await 贯穿全链路）

**File Structure:**
- `main.py` — FastAPI 路由 + lifespan 上下文 + 请求/响应模型
- `tools.py` — TOOLS 常量 + 租房 API 调用函数（顶层定义，不动态构建）
- `agent.py` — LLM Tool Calling Loop 逻辑

**Build Tooling:** uvicorn（内置，无构建步骤）

**Testing Framework:** 无正式框架（竞赛环境），smoke test 通过 curl 手动验证

**Code Organization:** 极简模块化，TOOLS 常量 + 系统提示独立，支持 30 分钟内热更新

**Development Experience:**
- 启动：`uvicorn main:app --host 0.0.0.0 --port 8191 --reload`
- 调试：结构化 print/logging，覆盖 session start / tool call / model response

**Note:** 项目初始化（创建文件结构 + 安装依赖）是第一个实现 Story。

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Format Guard 触发策略：代码判断（工具调用检测）
- Session 状态 Schema：极简消息列表
- Agent Loop 结构：while 循环 + 迭代计数器保护
- 工具层设计：TOOLS 常量 + 意图粒度压缩（15 API → 6 工具）

**Important Decisions (Shape Architecture):**
- 自适应翻页：串行翻页，首页后顺序拉取剩余页（上限 5 页）
- 系统提示：单一字符串常量，定义在 `agent.py` 顶层（≤800 Token）
- 错误处理：全局 try/except，永远返回 200 + status="error"
- X-User-ID：环境变量 USER_ID，工具层统一注入，不扩散到路由层

**Deferred Decisions (Post-MVP):**
- 并发翻页（asyncio.gather）：打榜后性能数据支撑时再升级
- 结构化意图对象（Session Schema B/C）：失分数据驱动时再引入
- 动态系统提示分段注入：3/3 变更评估后按需决策

### Data Architecture

**Session State:**
- 存储：全局 `sessions: dict[str, list]`，key = session_id，value = 消息历史列表
- 格式：OpenAI 标准消息格式 `[{"role": "...", "content": "..."}]`，含 system/user/assistant/tool 全部角色
- 隔离：不同 session_id 完全独立，无共享状态
- init 钩子：新 session_id 首条消息时，调用 `POST /api/houses/init` 重置数据后再处理消息
- 版本：无持久化，服务重启后 session 清空（竞赛环境可接受）

**No External Database:** 竞赛约束，内存存储完全满足需求

### Authentication & Security

**三层鉴权模型：**
- Agent 对外接口（POST /api/v1/chat）：无鉴权，判题系统直接调用
- 租房仿真 API（/api/houses/*）：`X-User-ID` 请求头，值从 `os.environ["USER_ID"]` 读取，在工具层统一注入
- 模型 API（/v1/chat/completions）：`api_key="placeholder"`（非空占位符），base_url 从请求体 model_ip 动态构建

**竞赛合规：**
- X-User-ID 必须为真实工号，绝不硬编码，环境变量唯一来源
- 禁止调用 model_ip:8888 以外的任何模型 API

### API & Communication Patterns

**外部接口设计（对外）：**
- 单一端点：`POST /api/v1/chat`，请求/响应均使用 Pydantic 模型，不用裸 dict
- 响应永远 HTTP 200：异常统一转换为 `{"status": "error", "response": "..."}` 返回
- 响应时间字段：`duration_ms` 反映真实壁钟时间（含模型调用）

**内部通信（工具调用）：**
- httpx.AsyncClient 全生命周期复用（FastAPI lifespan 上下文），不在请求内重建
- 地标 API（/api/landmarks/*）：无需 X-User-ID
- 房源 API（/api/houses/*）：统一注入 X-User-ID，不依赖调用方传入
- 操作 API（rent/terminate/offline）：POST + listing_platform 参数必填

**Format Guard 决策（代码判断策略）：**
- 触发条件：本轮 Tool Calling Loop 中调用了以下任一工具：`search_houses`、`search_nearby_landmark`、`search_landmark`（若返回了房源列表）
- 代码行为：从模型最终 content 中提取 house_ids，用 `json.dumps({"message": ..., "houses": [...]}, ensure_ascii=False)` 组装 response
- 非触发条件：纯聊天、get_house_detail、get_nearby_amenities、execute_action → response 为自然语言字符串

### Infrastructure & Deployment

**运行环境：**
- 启动命令：`uvicorn main:app --host 0.0.0.0 --port 8191`
- 端口固定：8191（不可更改）
- 启动时间：< 5 秒，禁止在启动时执行任何外部 API 调用
- 环境变量：`USER_ID`（竞赛平台工号），通过容器环境变量注入

**日志策略：**
- 使用 `print()` / `logging.info()`（无需外部日志系统）
- 覆盖事件：session start、tool call（名称+参数摘要）、model response（finish_reason + content 前 100 字符）
- 格式：包含 timestamp + session_id + event_type + details

**模块化更新支持（3/3 变更红线）：**
- TOOLS 常量：定义在 `tools.py` 顶层，30 分钟内可独立更新
- SYSTEM_PROMPT：定义在 `agent.py` 顶层，30 分钟内可独立更新
- 两者互相解耦，可独立修改不影响对方

### Decision Impact Analysis

**Implementation Sequence:**
1. FastAPI 应用骨架（main.py）+ lifespan + 请求响应模型
2. Session 管理 + init 钩子
3. TOOLS 常量定义 + 工具函数（tools.py）
4. Agent Loop（agent.py）+ 迭代计数器
5. Format Guard 逻辑集成
6. 串行自适应翻页集成到 search_houses 工具
7. 结构化日志

**Cross-Component Dependencies:**
- Format Guard 依赖 Agent Loop 传递工具调用记录
- Session init 钩子依赖 httpx.AsyncClient（lifespan 创建）
- 所有工具函数依赖 USER_ID 环境变量和 httpx.AsyncClient
- 系统提示字符长度直接影响时间片消耗（NFR2）

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 7 个区域，AI Agent 可能做出不兼容选择

---

### Naming Patterns

**Python 命名约定（全局强制）：**
- 函数/变量：`snake_case`（如 `run_agent`, `session_id`, `tool_results`）
- 模块级常量：`ALL_CAPS_SNAKE`（如 `SYSTEM_PROMPT`, `TOOLS`, `RENTAL_API_BASE`, `MAX_ITERATIONS`）
- Pydantic 模型类名：`PascalCase`（如 `ChatRequest`, `ChatResponse`, `ToolResult`）
- 文件名：`snake_case.py`（`main.py`, `tools.py`, `agent.py`）

**工具命名强制对齐规则（关键）：**
- TOOLS 常量中每个工具的 `"name"` 字段 **必须** 与对应的 Python 函数名完全一致
- ✅ 正确：TOOLS 中 `"name": "search_houses"` → 函数名 `async def search_houses(...)`
- ❌ 错误：`"name": "searchHouses"` 或 `"name": "search_house"`

**日志 event_type 常量（统一大写字符串）：**
- `"SESSION_START"` — 新 session 初始化
- `"SESSION_INIT"` — 调用 /api/houses/init 重置数据
- `"TOOL_CALL"` — 工具函数被调用
- `"MODEL_RESPONSE"` — 模型返回结果
- `"ERROR"` — 外部 API 或工具异常

**API JSON 字段命名：** 全部 `snake_case`（`session_id`, `model_ip`, `duration_ms`, `tool_results`）

**House ID 格式：** 永远是字符串 `"HF_x"`，不得转换为整数

---

### Structure Patterns

**模块职责边界（严格禁止跨界）：**

| 文件 | 包含内容 | 禁止包含 |
|------|---------|---------|
| `main.py` | FastAPI app + lifespan + Pydantic 模型 + POST /api/v1/chat 路由 | LLM 调用逻辑、工具函数 |
| `tools.py` | `TOOLS` 常量 + 所有工具执行函数 + 租房 API 调用 + `RENTAL_API_BASE` + `USER_ID` | Agent Loop、系统提示 |
| `agent.py` | `SYSTEM_PROMPT` + `run_agent()` + Format Guard + 工具 dispatch 表 | 路由定义、httpx 直接调用 |

**导入方向（单向，禁止循环）：**
```
main.py → agent.py → tools.py → (无内部导入)
```

**工具 Dispatch 表（在 agent.py 定义）：**
```python
TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    "search_landmark": search_landmark,
    "search_nearby_landmark": search_nearby_landmark,
    "get_house_detail": get_house_detail,
    "get_nearby_amenities": get_nearby_amenities,
    "execute_action": execute_action,
}
```

---

### Format Patterns

**工具调用结果追加到消息历史（强制规则）：**
- `content` 字段必须是 **字符串**，不得为 dict 或 None
- 若工具返回 dict，必须先 `json.dumps(result, ensure_ascii=False)` 转字符串
- ✅ 正确格式：`{"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)}`
- ❌ 错误：`{"role": "tool", "content": result}`（result 为 dict）

**工具函数返回类型约定：**
- 成功：返回 `dict`（由 agent.py 负责序列化）
- 失败：返回 `{"error": "错误描述字符串"}`（不得 raise 异常穿透至 agent loop）

**Format Guard 判断逻辑（代码判断，基于工具调用记录）：**
```python
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}
# 在 agent loop 中维护：
tools_called: set[str] = set()
# 每次工具调用后：tools_called.add(tool_name)
# 最终判断：is_house_query = bool(tools_called & HOUSE_SEARCH_TOOLS)
```

**Error 响应结构（必须与 ChatResponse 模型一致）：**
```python
ChatResponse(
    session_id=session_id,
    response="错误描述",
    status="error",
    tool_results=[],
    timestamp=int(time.time()),
    duration_ms=int((time.time() - start_time) * 1000)
)
```

---

### Communication Patterns

**Agent Loop 退出条件（按优先级）：**
1. `iterations >= MAX_ITERATIONS (10)` → 立即退出，返回 error 响应
2. `finish_reason == "stop"` AND `message.tool_calls` 为空或 None → 正常退出
3. 工具调用全部完成后继续下一轮 → 继续循环

**翻页模式（工具内部处理，agent loop 无感知）：**
```python
# 在 search_houses 工具内部：
all_items = first_page["items"]
total = first_page["total"]
page_size = first_page.get("page_size", 10)
page = 2
while len(all_items) < total and page <= 5:
    next_page = await fetch_houses(client, params={**base_params, "page": page})
    all_items.extend(next_page["items"])
    page += 1
```

**Session Init 调用时序（强制）：**
```
新 session_id 首条消息
    → 先调用 POST /api/houses/init（await，必须完成）
    → 再构建 system message 追加到 history
    → 再追加 user message
    → 再调用 run_agent()
```

---

### Process Patterns

**全局异常捕获（main.py 路由层）：**
```python
try:
    result = await run_agent(...)
    return result
except Exception as e:
    log_event("ERROR", session_id, {"error": str(e)})
    return ChatResponse(status="error", response=str(e), ...)
```

**工具层异常处理（tools.py 工具函数内）：**
```python
async def search_houses(client, **kwargs) -> dict:
    try:
        resp = await client.get(...)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_houses failed: {str(e)}"}
```

**日志格式（每条必须包含以下字段）：**
```python
def log_event(event_type: str, session_id: str, details: dict):
    print(json.dumps({
        "timestamp": int(time.time()),
        "session_id": session_id,
        "event_type": event_type,
        "details": details
    }, ensure_ascii=False))
```

---

### Enforcement Guidelines

**All AI Agents MUST:**
- 工具函数名与 TOOLS 常量 name 字段完全一致
- tool message content 必须是字符串（json.dumps 转换）
- Format Guard 基于 `HOUSE_SEARCH_TOOLS` 集合判断，不解析模型输出文本
- 工具函数内部 try/except，不向外抛出异常
- 导入方向严格遵循 `main→agent→tools` 单向链
- 所有 `/api/houses/*` 调用在 tools.py 工具函数内统一注入 X-User-ID

**Anti-Patterns（严禁）：**
- ❌ 在 agent loop 内部直接调用 httpx（绕过工具层）
- ❌ 在路由层（main.py）拼接 LLM 消息历史
- ❌ tool content 传递 Python dict 对象（会导致 OpenAI SDK 报错）
- ❌ Format Guard 通过正则解析模型 content 文本判断是否含有房源
- ❌ 工具函数 raise 异常穿透到 agent loop（会导致整条请求失败）

## Project Structure & Boundaries

### Complete Project Directory Structure

```
ai-agent-coding/
├── main.py              # FastAPI 应用入口（路由 + lifespan + Pydantic 模型）
├── agent.py             # LLM Agent Loop（SYSTEM_PROMPT + run_agent + Format Guard）
├── tools.py             # 工具层（TOOLS 常量 + 6 个意图工具函数 + 租房 API 调用）
├── requirements.txt     # 依赖声明（fastapi, uvicorn[standard], openai, httpx, pydantic）
└── README.md            # 启动说明 + smoke test curl 命令
```

---

### Architectural Boundaries

**外部边界（对外唯一入口）：**
```
判题系统 / curl
    │
    ▼  POST /api/v1/chat  HTTP:8191
┌─────────────────────────────────────┐
│              main.py                │
│  ChatRequest → session 管理 →       │
│  run_agent() → ChatResponse         │
└─────────────────────────────────────┘
```

**内部组件边界：**
```
main.py
  │ 调用 run_agent(history, model_ip, http_client)
  ▼
agent.py
  │ OpenAI SDK → qwen3-32b (model_ip:8888/v1)
  │ TOOL_DISPATCH[tool_name](**args)
  ▼
tools.py
  │ httpx.AsyncClient → 租房仿真 API (7.225.29.223:8080)
  │ 统一注入 X-User-ID: os.environ["USER_ID"]
  ▼
外部 API
```

**数据流（完整请求生命周期）：**
```
1. POST /api/v1/chat 到达 main.py
2. 解析 ChatRequest（model_ip, session_id, message）
3. 检查 session_id 是否为新 session
   ├── 是 → await init_houses(client)  [POST /api/houses/init]
   │       → sessions[session_id] = []
   └── 否 → 直接使用现有历史
4. history.append({"role": "user", "content": message})
5. await run_agent(history, model_ip, client) → agent.py
6. Agent Loop:
   a. LLM call (OpenAI SDK) → finish_reason / tool_calls
   b. 若 tool_calls: 执行工具 → 追加 tool message → 继续循环
   c. 若 finish_reason=="stop": 退出循环
7. Format Guard:
   if tools_called & HOUSE_SEARCH_TOOLS:
       response = json.dumps({"message": ..., "houses": [...]})
   else:
       response = model_content
8. 返回 ChatResponse → main.py → HTTP 200
```

---

### Requirements to Structure Mapping

| FR | 具体位置 | 关键实现 |
|----|---------|---------|
| FR1（POST /api/v1/chat） | `main.py:chat_endpoint()` | Pydantic 模型，async def |
| FR2-3（Session 历史 + 隔离） | `main.py:sessions` | `dict[str, list]` 全局变量 |
| FR4（新 Session init） | `main.py:chat_endpoint()` | 首条消息前 await init_houses() |
| FR5（意图分类） | `agent.py:run_agent()` | HOUSE_SEARCH_TOOLS 集合判断 |
| FR6-11（多维度房源搜索） | `tools.py:search_houses()` | 含串行自适应翻页（≤5页） |
| FR12（自动翻页） | `tools.py:search_houses()` | while 循环串行拉取 |
| FR13（单房源详情） | `tools.py:get_house_detail()` | GET /api/houses/{id} |
| FR14（地标搜索） | `tools.py:search_landmark()` | GET /api/landmarks/search |
| FR15（地标附近房源） | `tools.py:search_nearby_landmark()` | GET /api/houses/nearby |
| FR16（周边配套） | `tools.py:get_nearby_amenities()` | GET /api/houses/nearby_landmarks |
| FR17-19（租赁操作） | `tools.py:execute_action()` | POST /api/houses/{id}/{action} |
| FR20-22（格式守卫） | `agent.py:run_agent()` | tools_called set + json.dumps |
| FR23（5秒启动） | `main.py:lifespan()` | httpx.AsyncClient 创建，无外部调用 |
| FR24（结构化日志） | `agent.py:log_event()` | JSON 格式 print() |
| FR25（异常捕获） | `main.py` + `tools.py` | 双层 try/except |

---

### Integration Points

**内部通信：**
- `main.py` → `agent.py`：函数调用 `await run_agent(history, model_ip, client)`
- `agent.py` → `tools.py`：`TOOL_DISPATCH` dict 动态分发 `await TOOL_DISPATCH[name](client, **args)`
- 共享状态：`sessions` dict 在 `main.py` 模块级定义，`run_agent` 不持有 session，仅操作传入的 history list

**外部集成：**
- LLM API：`openai.AsyncOpenAI(base_url=f"http://{model_ip}:8888/v1", api_key="placeholder")`，每次请求实例化（model_ip 动态）
- 租房 API：`httpx.AsyncClient(base_url="http://7.225.29.223:8080", timeout=30.0)`，lifespan 创建，全生命周期复用
- 环境变量：`USER_ID = os.environ["USER_ID"]`，`tools.py` 模块加载时读取一次

---

### File Organization Patterns

**main.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. Pydantic 模型（ChatRequest, ChatResponse, ToolResult）
# 3. 全局状态（sessions: dict[str, list]）
# 4. lifespan（httpx.AsyncClient 创建/关闭）
# 5. FastAPI app 实例化
# 6. POST /api/v1/chat 路由函数
```

**tools.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. 常量（RENTAL_API_BASE, USER_ID, MAX_PAGES）
# 3. TOOLS = [...] 常量（OpenAI function calling 格式，6个工具）
# 4. 辅助函数（_get_headers()）
# 5. 6 个工具执行函数（search_houses, search_landmark, ...）
# 6. init_houses()（数据重置函数）
```

**agent.py 内部结构（顺序）：**
```python
# 1. 导入
# 2. 常量（SYSTEM_PROMPT, MAX_ITERATIONS, HOUSE_SEARCH_TOOLS）
# 3. TOOL_DISPATCH 表
# 4. log_event() 函数
# 5. run_agent() 主函数（含 Format Guard 逻辑）
```

---

### Development Workflow Integration

**开发启动：**
```bash
USER_ID=<真实工号> uvicorn main:app --host 0.0.0.0 --port 8191 --reload
```

**Smoke Test 序列：**
```bash
# 1. 聊天类（response 应为自然语言字符串）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<ip>","session_id":"test-chat","message":"你好"}'

# 2. 房源查询（response 应为合法 JSON 字符串）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<ip>","session_id":"test-search","message":"找海淀区两居室"}'
```

**部署结构：**
```
容器 / 竞赛平台
├── 环境变量：USER_ID=<工号>
├── 启动命令：uvicorn main:app --host 0.0.0.0 --port 8191
└── 依赖安装：pip install -r requirements.txt
```

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:** 所有技术选型完全兼容——全链路异步（FastAPI + httpx + openai SDK），Pydantic v2 原生 FastAPI 支持，in-memory dict 适配竞赛单机部署。

**Pattern Consistency:** Format Guard 代码判断策略与 PRD 核心哲学（把不确定性从 AI 层转移到代码层）完全对齐。snake_case 命名、单向依赖链、双层异常捕获无矛盾。

**Structure Alignment:** 三文件结构对所有 FR/NFR 提供完整支撑，模块边界清晰，集成点明确定义。

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:** 25/25 FR 全部覆盖，详见 Step 6 映射表。

**Non-Functional Requirements Coverage:** 10/10 NFR 全部覆盖，性能/集成/可靠性三类约束均有明确架构机制支撑。

### Gap Analysis Results

**Important Gap 1 — SYSTEM_PROMPT 内容约束（已补充）：**

SYSTEM_PROMPT（定义在 `agent.py` 顶层）必须满足以下约束：

- **长度：** ≤ 800 Token（字符数约 ≤ 500 中文字符）
- **必含指令类型：**
  - 角色定义：智能租房助手
  - 工具调用指令：识别到租房需求时主动调用工具（search_houses 等），不要依赖记忆推测
  - 意图分类指令：聊天类请求直接回复自然语言；租赁操作必须调用 execute_action
  - 格式指令：不要在回复中自行生成 JSON，结果由系统处理
- **禁止内容：**
  - 任何已知用例答案或预设房源 ID（作弊，取消资格）
  - 超过 800 Token 的内容
  - 调用 model_ip:8888 以外任何模型的指令

**Important Gap 2 — listing_platform 枚举值统一（已补充）：**

以下工具的 `listing_platform` 参数必须使用相同枚举集合：
- `search_houses`、`search_nearby_landmark`、`execute_action`

枚举值：`["链家", "安居客", "58同城"]`（与租房仿真 API 一致）
默认值：`"安居客"`（未传时 API 默认返回安居客数据）

TOOLS 常量中三个工具的该参数描述和 enum 值必须完全一致，不得分别定义。

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] 项目上下文深度分析（25 FR + 10 NFR）
- [x] 规模与复杂度评估（Medium-High，API Backend）
- [x] 技术约束识别（端口/时间片/Token/合规红线）
- [x] 横切关注点映射（6 个关注点）

**✅ Architectural Decisions**
- [x] 关键决策文档化（Format Guard、Session Schema、Loop、翻页、系统提示）
- [x] 技术栈完整规定（Python 3.11+、FastAPI、openai、httpx、Pydantic）
- [x] 集成模式定义（三层鉴权、双向外部 API）
- [x] 性能约束架构支撑（MAX_ITERATIONS、串行翻页、系统提示 Token 上限）

**✅ Implementation Patterns**
- [x] 命名规范建立（snake_case、ALL_CAPS、PascalCase）
- [x] 结构模式定义（模块职责边界、导入方向）
- [x] 通信模式规定（Loop 退出条件、翻页模式、init 时序）
- [x] 过程模式文档化（双层异常捕获、日志格式）

**✅ Project Structure**
- [x] 完整目录结构（5 个文件）
- [x] 组件边界确立（三文件职责不重叠）
- [x] 集成点映射（内部调用链 + 外部 API）
- [x] FR 到结构映射完整（25 FR 全部对应到文件/函数）

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION ✅

**Confidence Level:** High — 架构决策完整、模式清晰、结构具体，AI Agent 可据此直接实现而无需额外澄清。

**Key Strengths:**
- 格式守卫机制彻底消除 JSON 格式失分风险
- 意图粒度压缩（15 API → 6 工具）降低模型决策复杂度
- 双层异常捕获保证 100% HTTP 200 可用率
- 模块化设计支持 3/3 需求变更的 30 分钟内热更新

**Areas for Future Enhancement（打榜后迭代）：**
- 串行翻页 → 并发翻页（asyncio.gather）
- 极简 Session Schema → 含 last_houses 集合的 Schema B（指代消解）
- 单一 SYSTEM_PROMPT → 动态分段注入（Token 最优化）

### Implementation Handoff

**AI Agent Guidelines:**
- 读取本文档 + PRD + project-context.md 后开始实现
- TOOLS 常量中工具名必须与函数名完全一致
- tool message content 必须是字符串（json.dumps 转换）
- Format Guard 仅基于 HOUSE_SEARCH_TOOLS 集合判断，不解析文本

**First Implementation Priority:**
```bash
# Step 1: 项目初始化
mkdir ai-agent-coding && cd ai-agent-coding
touch main.py tools.py agent.py requirements.txt README.md
python -m venv .venv
pip install fastapi "uvicorn[standard]" openai httpx pydantic
# Step 2: 实现 main.py 骨架（lifespan + ChatRequest/ChatResponse + 路由）
# Step 3: 实现 tools.py（TOOLS 常量 + 6 个工具函数）
# Step 4: 实现 agent.py（SYSTEM_PROMPT + run_agent + Format Guard）
# Step 5: Smoke test 验证
```
