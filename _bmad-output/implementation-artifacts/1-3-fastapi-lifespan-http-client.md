# Story 1.3: FastAPI lifespan 与 HTTP 客户端全生命周期管理

Status: done

## Story

As the system,
I want the `httpx.AsyncClient` to be created once at startup and shared across all requests,
so that connection overhead is minimized and NFR7 (client reuse) is satisfied.

## Acceptance Criteria

1. **Given** the FastAPI app is initialized with a `lifespan` context manager  
   **When** the service starts  
   **Then** `httpx.AsyncClient(base_url="http://7.197.86.219:8080", timeout=30.0)` is created **exactly once** and stored in `app.state.client`  
   **And** no external API calls are made during startup

2. **Given** the service is running  
   **When** `POST /api/v1/chat` receives a request  
   **Then** the route handler retrieves the shared client via `request.app.state.client` (using FastAPI `Request` object)  
   **And** passes it to downstream functions (e.g., `run_agent(history, model_ip, client)`)

3. **Given** the service is shutting down  
   **When** the lifespan context exits  
   **Then** `await client.aclose()` is called to properly release connections

4. **Given** a per-request handler is executing  
   **When** it needs an HTTP client  
   **Then** it uses the shared `app.state.client` — **never** creates a new `httpx.AsyncClient` inside the handler

## Tasks / Subtasks

- [x] Task 1: 验证现有 lifespan 实现 (AC: 1, 3)
  - [x] 确认 `httpx.AsyncClient(base_url="http://7.197.86.219:8080", timeout=30.0)` 参数正确
  - [x] 确认存储路径为 `app.state.client`
  - [x] 确认 `yield` 后执行 `await app.state.client.aclose()`
  - [x] 确认 lifespan 内无任何外部 API 调用

- [x] Task 2: 修复路由函数以正确获取 client (AC: 2, 4) ← **核心任务**
  - [x] 在 `chat_endpoint` 签名中添加 `req: Request` 参数（来自 `fastapi.Request`）
  - [x] 在函数体内通过 `client = req.app.state.client` 获取共享客户端
  - [x] 确保 `client` 变量可传递给 `run_agent(history, model_ip, client)`（Story 1.4 实现）
  - [x] 更新 `main.py` 导入以包含 `from fastapi import FastAPI, Request`

- [x] Task 3: 验证 (AC: 1-4)
  - [x] 启动服务：`USER_ID=test uvicorn main:app --host 0.0.0.0 --port 8191`
  - [x] 确认启动在 5 秒内完成，无外部 API 报错
  - [x] 确认 `POST /api/v1/chat` 可调用（即使返回 stub 响应也可）

## Dev Notes

### 🚨 关键上下文：现有代码状态

**截至 Story 1.1/1.2 完成，`main.py` 现有实现：**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        base_url="http://7.197.86.219:8080", timeout=30.0
    )
    yield
    await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):  # ← 问题在这里
    return ChatResponse(...)  # stub
```

**✅ lifespan 实现正确，满足 AC 1 和 3。**

**❌ 关键缺口：`chat_endpoint` 无法访问 `app.state.client`**

当前 `chat_endpoint(request: ChatRequest)` 只有 Pydantic 请求体参数，无法访问 `app.state`。需修复如下：

### 修复方案（唯一正确方式）

**在路由函数签名中添加 `req: Request`：**

```python
from fastapi import FastAPI, Request  # 添加 Request 导入

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    client = req.app.state.client   # 获取共享 httpx.AsyncClient
    # Story 1.4 中：await run_agent(history, request.model_ip, client)
    ...
```

**为什么 `request: ChatRequest` 和 `req: Request` 可以同时存在：**
- FastAPI 自动区分：`ChatRequest`（Pydantic BaseModel）→ 从请求体解析
- `Request`（FastAPI 原生类型）→ 直接注入 HTTP 请求对象
- 两个参数命名不同，FastAPI 不会混淆

**禁止的替代方案：**
```python
# ❌ 错误：在请求处理中创建新 client
async def chat_endpoint(request: ChatRequest):
    async with httpx.AsyncClient() as client:  # 违反 NFR7
        ...

# ❌ 错误：全局变量存储 client（不支持 lifespan 生命周期）
http_client = httpx.AsyncClient(...)  # 在模块顶层

# ❌ 错误：依赖注入 Depends()（过度工程化，竞赛无需）
```

### 架构约束说明

**httpx.AsyncClient 配置参数（不得更改）：**
```python
httpx.AsyncClient(
    base_url="http://7.197.86.219:8080",  # 租房 API base URL，固定
    timeout=30.0                           # 30 秒超时，固定
)
```

**client 的传递路径（整条链路）：**
```
lifespan → app.state.client
    ↓ (通过 req.app.state.client)
chat_endpoint(req: Request)
    ↓ (作为参数传递)
run_agent(history, model_ip, client)        ← agent.py
    ↓ (通过 TOOL_DISPATCH 分发)
search_houses(client, **kwargs)             ← tools.py
```

**关键：`client` 是 `tools.py` 所有工具函数的第一个参数（已在 Story 1.1 中定义为骨架）**。

### `main.py` 完成后的结构

```python
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request      # ← 新增 Request
import httpx
from pydantic import BaseModel
from agent import run_agent

class ToolResult(BaseModel): ...
class ChatRequest(BaseModel): ...
class ChatResponse(BaseModel): ...

sessions: dict[str, list] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        base_url="http://7.197.86.219:8080", timeout=30.0
    )
    yield
    await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):  # ← 修复
    client = req.app.state.client
    # Story 1.4 将在此实现完整逻辑
    return ChatResponse(
        session_id=request.session_id,
        response="Not implemented",
        status="error",
        tool_results=[],
        timestamp=int(time.time()),
        duration_ms=0,
    )
```

### 与其他故事的依赖关系

| 故事 | 依赖关系 |
|------|---------|
| Story 1.2 (Pydantic 模型) | ✅ 已完成，本故事依赖其模型定义 |
| **Story 1.4 (路由逻辑)** | 依赖本故事提供的 `client` 变量 |
| Story 2.2 (Session init) | 依赖 `client` 传递给 `init_houses(client)` |
| Epic 3-5 所有工具 | 依赖 `client` 作为第一个参数 |

### 竞赛合规提醒

- `lifespan` 中绝不调用 `POST /api/houses/init` 或任何外部 API（违反 FR23：5 秒内启动）
- `httpx.AsyncClient` 的 `base_url` 固定为 `"http://7.197.86.219:8080"`，不得参数化
- 启动命令：`USER_ID=<工号> uvicorn main:app --host 0.0.0.0 --port 8191`（端口 8191 固定不变）

### Project Structure Notes

**本故事仅修改 `main.py`，无新文件创建。**

修改范围：
1. 导入行：`from fastapi import FastAPI, Request`（添加 `Request`）
2. 路由函数签名：添加 `req: Request` 参数
3. 路由函数体：添加 `client = req.app.state.client`

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 1, Story 1.3]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Infrastructure & Deployment, API & Communication Patterns, Integration Points]
- [Source: `_bmad-output/planning-artifacts/prd.md` — Implementation Considerations (httpx.AsyncClient lifespan)]
- [Source: `main.py` — 现有实现（Story 1.1/1.2 遗留）]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor Dev Agent)

### Debug Log References

_无_

### Completion Notes List

- ✅ Task 1: 验证现有 lifespan 实现完全正确 — `httpx.AsyncClient(base_url="http://7.197.86.219:8080", timeout=30.0)` 存储到 `app.state.client`，`yield` 后执行 `aclose()`，启动期间零外部 API 调用
- ✅ Task 2: 修复 `chat_endpoint` 签名 — 添加 `req: Request` 参数，函数体通过 `client = req.app.state.client` 获取共享客户端，`from fastapi import FastAPI, Request` 导入已更新
- ✅ Task 3: 全量测试验证通过 — 51/51 测试通过，零回归，TDD 红绿重构流程完整执行
- TDD 执行记录：RED(3 失败 / 11 通过) → 修复 main.py → GREEN(14/14 通过) → 全量回归(51/51 通过)

### Code Review Record (2026-02-27)

- 🔍 **审查结果：Approved（修复后通过）**
- M1（已修复）: `client` 变量添加 `# noqa: F841` 抑制 linter 警告（Story 1.4 将使用）
- M2（已验证）: 实际执行 uvicorn 启动 → HTTP 200，响应结构正确
- M3（设计意图）: `USER_ID = os.environ["USER_ID"]` 是竞赛要求的 fail-fast 行为，非 bug
- L1-L3: 低优先级建议（未使用导入 `run_agent` 为 1.4 预留、`conftest.py` 可选优化、源码检查测试可接受）
- 修复后全量测试：51/51 通过，零回归

### File List

- `main.py`（修改 — 添加 `Request` 导入，修复路由函数签名和 client 获取逻辑，添加 noqa 注释）
- `tests/test_lifespan_http_client.py`（新增 — Story 1.3 AC1-4 全覆盖测试，14 个测试用例）
