# Story 1.1: 项目文件结构初始化

Status: done

## Story

As a developer,
I want the project scaffolded with the correct three-file structure and all dependencies declared,
so that there is a clean, runnable starting point with all required packages.

## Acceptance Criteria

1. **Given** a new empty project directory  
   **When** the initialization commands are run  
   **Then** the following 5 files exist in the project root: `main.py`, `tools.py`, `agent.py`, `requirements.txt`, `README.md`

2. **Given** `requirements.txt` is created  
   **When** reviewed for content  
   **Then** it contains exactly these packages (one per line): `fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `pydantic`  
   **And** running `pip install -r requirements.txt` completes without errors

3. **Given** `README.md` is created  
   **When** reviewed  
   **Then** it includes the startup command `uvicorn main:app --host 0.0.0.0 --port 8191`  
   **And** includes at least one smoke test `curl` example for `POST /api/v1/chat`

4. **Given** all 3 Python files are created  
   **When** reviewed for structure  
   **Then** each file contains module-level skeleton code (imports, placeholder constants, empty/stub functions) that allows `python -c "import main; import agent; import tools"` without error  
   **And** the import direction is strictly `main.py → agent.py → tools.py` (no circular imports)

## Tasks / Subtasks

- [x] Task 1: 创建项目目录结构 (AC: 1)
  - [x] 创建 `main.py`，包含正确的导入骨架和模块注释
  - [x] 创建 `tools.py`，包含正确的导入骨架
  - [x] 创建 `agent.py`，包含正确的导入骨架
  - [x] 创建 `requirements.txt`，包含 5 个依赖包
  - [x] 创建 `README.md`，包含启动命令和 smoke test 示例

- [x] Task 2: 在每个 Python 文件中设置骨架结构 (AC: 4)
  - [x] `main.py`：导入 + Pydantic 占位模型类 + `sessions: dict` 占位符 + lifespan 占位符 + FastAPI app 实例 + 路由占位符
  - [x] `tools.py`：导入 + 常量占位符（`RENTAL_API_BASE`, `USER_ID`, `MAX_PAGES`）+ `TOOLS = []` 占位符 + 辅助函数占位符
  - [x] `agent.py`：导入 + `SYSTEM_PROMPT = ""` 占位符 + `MAX_ITERATIONS = 10` + `HOUSE_SEARCH_TOOLS = set()` + `TOOL_DISPATCH = {}` + `log_event()` 占位符 + `run_agent()` 占位符

- [x] Task 3: 验证 (AC: 2, 3, 4)
  - [x] 验证 `pip install -r requirements.txt` 成功
  - [x] 验证 `python -c "import main; import agent; import tools"` 无报错
  - [x] 验证无循环导入错误

## Dev Notes

### 🚨 关键约束（必须严格遵守）

**文件结构（只能这 5 个文件，不得多也不得少）：**
```
ai-agent-coding/
├── main.py              ← FastAPI 路由 + lifespan + Pydantic 模型
├── agent.py             ← LLM Agent Loop + SYSTEM_PROMPT + Format Guard
├── tools.py             ← TOOLS 常量 + 6 个工具函数 + 租房 API 调用
├── requirements.txt     ← 精确 5 个依赖
└── README.md            ← 启动说明 + smoke test curl
```

**requirements.txt 精确内容（不得添加其他包，不加版本号）：**
```
fastapi
uvicorn[standard]
openai
httpx
pydantic
```

**导入方向（单向链，禁止循环）：**
```
main.py → agent.py → tools.py → (无内部导入)
```
- `main.py` 可以 `from agent import run_agent` ✅
- `agent.py` 可以 `from tools import TOOLS, TOOL_DISPATCH` ✅
- `tools.py` 绝不导入 `agent` 或 `main` ❌

### main.py 骨架结构（按此顺序）

```python
import time
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
import httpx
from pydantic import BaseModel
from agent import run_agent

# Pydantic 模型（PascalCase 命名，snake_case 字段）
class ToolResult(BaseModel):
    tool_name: str
    result: str

class ChatRequest(BaseModel):
    model_ip: str
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    status: str
    tool_results: list
    timestamp: int
    duration_ms: int

# 全局 Session 存储
sessions: dict[str, list] = {}

# lifespan 上下文（httpx.AsyncClient 全生命周期）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 创建并存储 http client（startup 时不调用任何外部 API）
    app.state.client = httpx.AsyncClient(
        base_url="http://7.197.86.219:8080", timeout=30.0
    )
    yield
    await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    # 路由函数 + 全局 try/except 占位
    pass
```

### tools.py 骨架结构（按此顺序）

```python
import os
import json
import httpx

# 模块顶层常量（必须在模块加载时读取一次）
RENTAL_API_BASE = "http://7.197.86.219:8080"
USER_ID = os.environ["USER_ID"]   # 模块加载时读取，不在函数内读取
MAX_PAGES = 5

# TOOLS 常量（将在 Story 3.1 填充，此处为空 list 占位）
TOOLS: list[dict] = []

def _get_headers() -> dict:
    return {"X-User-ID": USER_ID}

# 工具函数占位（将在 Epic 3-5 填充）
async def search_houses(client: httpx.AsyncClient, **kwargs) -> dict:
    pass

async def search_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    pass

async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    pass

async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    pass

async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    pass

async def execute_action(client: httpx.AsyncClient, **kwargs) -> dict:
    pass

async def init_houses(client: httpx.AsyncClient) -> dict:
    pass
```

### agent.py 骨架结构（按此顺序）

```python
import json
import time
from typing import Callable
import httpx
from openai import AsyncOpenAI
from tools import (
    TOOLS, search_houses, search_landmark, search_nearby_landmark,
    get_house_detail, get_nearby_amenities, execute_action
)

# 模块顶层常量
SYSTEM_PROMPT = ""  # 将在 Story 2.3 填充，≤800 Token
MAX_ITERATIONS = 10
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}

TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    "search_landmark": search_landmark,
    "search_nearby_landmark": search_nearby_landmark,
    "get_house_detail": get_house_detail,
    "get_nearby_amenities": get_nearby_amenities,
    "execute_action": execute_action,
}

def log_event(event_type: str, session_id: str, details: dict):
    # 将在 Story 6.1 完整实现
    pass

async def run_agent(history: list, model_ip: str, client: httpx.AsyncClient) -> dict:
    # 将在 Story 2.3 填充 Agent Loop 逻辑
    pass
```

### README.md 必须包含内容

```markdown
# AI Agent Coding

## 启动服务

```bash
USER_ID=<你的工号> uvicorn main:app --host 0.0.0.0 --port 8191
```

## Smoke Test

```bash
# 聊天类（response 应为自然语言字符串）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<模型IP>","session_id":"test-chat","message":"你好"}'

# 房源查询类（response 应为合法 JSON 字符串）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<模型IP>","session_id":"test-search","message":"找海淀区两居室"}'
```
```

### Project Structure Notes

**此故事边界（范围内 vs 范围外）：**
- ✅ 范围内：创建文件结构，设置骨架代码，安装依赖
- ❌ 范围外：实现任何业务逻辑（路由函数、Agent Loop、工具函数）

**下一个故事依赖此故事：**
- Story 1.2（Pydantic 模型）将填充 `main.py` 中的 `ChatRequest`/`ChatResponse`
- Story 1.3（lifespan）将填充 `main.py` 中的 `lifespan` 函数
- Story 3.1（TOOLS 常量）将填充 `tools.py` 中的 `TOOLS` list

**环境变量：**
- `USER_ID` 在 `tools.py` 模块加载时读取，若未设置则程序启动时报 `KeyError`
- 本地开发需设置：`$env:USER_ID="<工号>"` (PowerShell) 或 `export USER_ID="<工号>"` (bash)

### 竞赛合规提醒

- ❌ 绝不硬编码 USER_ID 值到任何文件
- ❌ 绝不添加 requirements.txt 未列出的额外依赖（如 pytest, black 等开发工具不属于运行依赖）
- ✅ Python 3.11+，所有函数后续必须使用 `async def`（全链路异步）

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 1, Story 1.1]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Starter Template, Project Structure, File Organization Patterns]
- [Source: `_bmad-output/planning-artifacts/prd.md` — Implementation Considerations]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Amelia, Dev Agent)

### Debug Log References

_无_

### Completion Notes List

- ✅ 创建 `main.py`：FastAPI 骨架，Pydantic 模型（ToolResult/ChatRequest/ChatResponse），lifespan httpx client，`/api/v1/chat` 路由占位，`sessions: dict` 全局存储
- ✅ 创建 `tools.py`：模块顶层常量（RENTAL_API_BASE/USER_ID/MAX_PAGES），TOOLS 空 list，6 个工具函数占位 + init_houses 占位
- ✅ 创建 `agent.py`：SYSTEM_PROMPT/MAX_ITERATIONS/HOUSE_SEARCH_TOOLS/TOOL_DISPATCH 常量，log_event/run_agent 占位
- ✅ 创建 `requirements.txt`：精确 5 个依赖，无版本号
- ✅ 创建 `README.md`：uvicorn 启动命令 + 2 个 curl smoke test
- ✅ `pip install -r requirements.txt` 无错误（所有依赖已满足）
- ✅ `python -c "import main; import agent; import tools"` 无报错（USER_ID=test123）
- ✅ 无循环导入（tools.py 未导入 agent/main，经 AST 静态验证）
- ✅ 导入方向严格遵守：main → agent → tools

### Code Review Fixes (2026-02-27)

- ✅ [M2] chat_endpoint 返回占位 ChatResponse 替代 None（修复 response_model 验证失败）
- ✅ [M3] 添加 Dev Notes 模板中的所有骨架注释（main.py/tools.py/agent.py）
- ✅ [M1] 未使用导入评估 — 保留（Dev Notes 模板明确指定，为后续 Story 预留）
- ✅ [L1] README 添加项目描述
- ✅ [L3] ChatResponse.tool_results 类型精确化为 list[ToolResult]

### File List

- `main.py`（新建 + 审查修复）
- `tools.py`（新建 + 审查修复）
- `agent.py`（新建 + 审查修复）
- `requirements.txt`（新建）
- `README.md`（新建 + 审查修复）
