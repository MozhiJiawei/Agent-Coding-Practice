# Story 2.3: Agent Loop 完整实现

Status: done

## Story

As the agent,
I want a fully functional LLM tool-calling loop with intent classification and output format enforcement,
so that the system can handle both chat and house-search requests correctly end-to-end within token and iteration budgets.

## Acceptance Criteria

1. **SYSTEM_PROMPT（NFR2）**
   - **Given** `agent.py` is implemented
   - **When** `SYSTEM_PROMPT` is defined at module top level
   - **Then** it contains: role definition（智能租房助手）、tool-calling instruction（主动调用工具）、intent classification instruction（聊天直接回复/操作必须调用工具）、format instruction（不自行生成 JSON）
   - **And** its token count is ≤ 800（NFR2）
   - **And** it contains no preset house IDs or hardcoded answers

2. **Agent Loop 骨架（NFR3, NFR6）**
   - **Given** `run_agent(history, model_ip, client, session_id="")` is called
   - **When** the Agent Loop executes
   - **Then** it uses a `while` loop with an `iterations` counter initialized to 0
   - **And** `MAX_ITERATIONS = 10` is defined as a module-level constant
   - **And** if `iterations >= MAX_ITERATIONS`, the loop exits immediately and returns `status="error"` with message `"Tool call limit exceeded"`（NFR3）
   - **And** the OpenAI client is constructed per-call as `AsyncOpenAI(base_url=f"http://{model_ip}:8888/v1", api_key="placeholder")`（NFR6）

3. **Tool Dispatch 与 Tool Message 格式（FR5）**
   - **Given** the model returns a response with `tool_calls`
   - **When** each tool call is dispatched
   - **Then** `TOOL_DISPATCH: dict[str, Callable]` in `agent.py` is used to look up and call the correct function: `await TOOL_DISPATCH[tool_name](client, **args)`
   - **And** the tool result（a dict）is serialized via `json.dumps(result, ensure_ascii=False)` before being appended to history
   - **And** the tool message appended to history has the exact format: `{"role": "tool", "tool_call_id": call.id, "content": "<json_string>"}`
   - **And** `content` is ALWAYS a string, never a Python dict or None

4. **Loop 退出条件**
   - **Given** `finish_reason == "stop"` and `message.tool_calls` is empty or None
   - **When** the loop evaluates exit conditions
   - **Then** the loop exits normally and proceeds to Format Guard

5. **Format Guard — 意图分类与输出格式控制（FR5, FR20, FR21, FR22, NFR9）**
   - **Given** the Agent Loop has completed
   - **When** Format Guard evaluates the response type
   - **Then** `HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}` is defined as a module-level constant
   - **And** `tools_called: set[str]` is maintained throughout the loop, adding each tool name after execution
   - **And** if `tools_called & HOUSE_SEARCH_TOOLS` is non-empty（house query path）:
     - `response` is set to `json.dumps({"message": <model_content>, "houses": [<id1>, ...]}, ensure_ascii=False)`
     - `houses` contains only valid IDs matching format `"HF_\d+"`, maximum 5 items（FR22）
     - `json.loads(response)` succeeds without error（NFR9）
   - **And** if `tools_called & HOUSE_SEARCH_TOOLS` is empty（chat path）:
     - `response` is set to the raw model `content` string（FR21）
     - The response contains no JSON structure
   - **And** Format Guard logic is based ONLY on `tools_called` set — the DECISION uses set membership, never regex on model output（FR5, FR20）

6. **log_event 实现**
   - **Given** `log_event(event_type, session_id, details)` is called
   - **When** it executes
   - **Then** it outputs a JSON line via `print(json.dumps({...}, ensure_ascii=False))` containing: `timestamp`（Unix int）、`session_id`（str）、`event_type`（str）、`details`（dict）
   - **And** `MODEL_RESPONSE` events are logged（with `finish_reason` + first 100 chars of `content`）inside `run_agent()`
   - **And** `TOOL_CALL` events are logged（with `tool_name` + truncated args）before each tool dispatch inside `run_agent()`

7. **main.py — 新 Session system message 注入**
   - **Given** a `session_id` that has never been seen before
   - **When** the new-session block in `chat_endpoint` executes
   - **Then** after `sessions[session_id] = []`, the system message is appended: `sessions[session_id].append({"role": "system", "content": SYSTEM_PROMPT})`
   - **And** `SYSTEM_PROMPT` is imported from `agent` in `main.py`
   - **And** this insertion happens AFTER `init_houses(client)` and AFTER `sessions[session_id] = []`（Story 2.2 order preserved）

## Tasks / Subtasks

- [x] **Task 1: 实现 `log_event()` 函数**（AC: 6）
  - [x] 替换 `agent.py` 中的 `pass` stub，实现 JSON 结构化输出
  - [x] 字段：`timestamp`（`int(time.time())`）、`session_id`、`event_type`、`details`
  - [x] 使用 `print(json.dumps({...}, ensure_ascii=False))` 输出
  - [x] 验证：调用 `log_event("TEST", "s1", {"k": "v"})` 后输出合法 JSON

- [x] **Task 2: 定义 `SYSTEM_PROMPT` 常量**（AC: 1）
  - [x] 在 `agent.py` 顶层（模块级）定义 `SYSTEM_PROMPT`，替换空字符串占位
  - [x] 必须包含：角色定义（智能租房助手）+ 工具调用指令 + 意图分类（聊天直接回复/房源操作必须调工具）+ 格式指令（不自行生成 JSON）
  - [x] 禁止：预设房源 ID、硬编码答案、调用外部模型指令
  - [x] Token 数 ≤ 800（中文字符 ≤ 500 个）
  - [x] 验证：`len(SYSTEM_PROMPT)` 合理（约 300–500 字符）

- [x] **Task 3: 补充 `main.py` system message 注入**（AC: 7）
  - [x] 在 `main.py` 的 `from agent import run_agent, log_event` 行，增加 `SYSTEM_PROMPT` 到导入列表
  - [x] 在 `if request.session_id not in sessions:` 块内，`sessions[session_id] = []` 之后插入：`sessions[request.session_id].append({"role": "system", "content": SYSTEM_PROMPT})`
  - [x] 验证时序：init → `sessions[id] = []` → system message append → user message append → `run_agent()`

- [x] **Task 4: 实现 `run_agent()` 完整 Agent Loop**（AC: 2, 3, 4, 5）
  - [x] 替换 `agent.py` 中 `run_agent` 的 `pass` stub
  - [x] 添加 `session_id: str = ""` 为第 4 个可选参数（向后兼容，不破坏现有 mock 测试）
  - [x] 构建 `AsyncOpenAI` client（`base_url=f"http://{model_ip}:8888/v1"`, `api_key="placeholder"`）
  - [x] 初始化：`tools_called: set[str] = set()`、`tool_results_log: list[dict] = []`、`iterations = 0`
  - [x] 实现 `while True:` 循环：
    - 先检查 `if iterations >= MAX_ITERATIONS:` → 立即返回 error dict
    - 调用 `llm_client.chat.completions.create()`，若 `TOOLS` 为空则不传 `tools` 参数
    - 提取 `message` 和 `finish_reason`
    - 调用 `log_event("MODEL_RESPONSE", ...)`
    - 将 assistant message 追加到 `history`（手动构建 dict，见 Dev Notes）
    - 如果 `finish_reason == "stop"` 且 `not message.tool_calls` → `break`
    - 如果有 `tool_calls` → 遍历，调用 `log_event("TOOL_CALL", ...)`，dispatch 并追加 tool message，`tools_called.add(tool_name)`，`iterations += 1`
  - [x] 实现 Format Guard（循环后）：
    - 若 `tools_called & HOUSE_SEARCH_TOOLS` 非空 → 从 content 提取 `HF_\d+` IDs（max 5，去重）→ `json.dumps({"message": content, "houses": ids}, ensure_ascii=False)`
    - 否则 → 直接返回 content 字符串
  - [x] 返回 `{"response": ..., "status": "success"/"error", "tool_results": tool_results_log}`
  - [x] 同步更新 `main.py` 调用处，传递 `session_id=request.session_id`

- [x] **Task 5: 编写单元测试**
  - [x] `test_log_event.py`：测试 JSON 格式、timestamp 类型、ensure_ascii=False（11 个测试）
  - [x] `test_agent_loop.py`：
    - `run_agent` 在 max iterations 时返回 error
    - `run_agent` 在 `finish_reason="stop"` 且无 tool_calls 时正常退出
    - tool message content 是字符串（非 dict）
    - Format Guard：调用 `search_houses` 后 response 可被 `json.loads()` 解析
    - Format Guard：纯聊天时 response 是纯字符串
    - `tools_called` 空时 Format Guard 不触发 JSON 格式（27 个测试）
  - [x] `test_e2e_epic2.py`：Epic 2 原型系统可运行能力 E2E 测试（18 个测试，用户额外要求）
  - [x] 全量回归：165 个测试（原有 107 个 + 新增 58 个）全部通过

## Dev Notes

### 当前代码基线（Story 2.2 完成后的状态）

**`agent.py` 当前状态：**
```python
# 模块顶层常量
SYSTEM_PROMPT = ""          # ← Task 2: 替换为实际 Prompt
MAX_ITERATIONS = 10         # ✅ 已定义
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}  # ✅ 已定义

TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    # ...全部 6 个工具已在 dispatch 表中 ✅
}

def log_event(event_type: str, session_id: str, details: dict):
    pass  # ← Task 1: 实现

async def run_agent(history: list, model_ip: str, client: httpx.AsyncClient) -> dict:
    pass  # ← Task 4: 实现
```

**`main.py` 当前新 Session 块（Story 2.2 完成后）：**
```python
from agent import run_agent, log_event    # ← Task 3: 增加 SYSTEM_PROMPT
# ...
if request.session_id not in sessions:
    await init_houses(client)             # ✅ Story 2.2 已完成
    sessions[request.session_id] = []    # ✅ Story 2.1 已完成
    # ← Task 3: 在此处插入 system message append（Story 2.3）
history = sessions[request.session_id]
history.append({"role": "user", "content": request.message})
result = await run_agent(history, request.model_ip, client)  # ← Task 4: 传递 session_id
```

**`tools.py` 当前状态：**
- 所有工具函数均为 `pass` stub（Story 3.1 实现）
- `TOOLS: list[dict] = []`（空占位，Story 3.1 填充）
- `init_houses()` 已正确实现（Story 2.2 完成）

### Task 1：`log_event()` 完整实现

```python
def log_event(event_type: str, session_id: str, details: dict):
    print(json.dumps({
        "timestamp": int(time.time()),
        "session_id": session_id,
        "event_type": event_type,
        "details": details
    }, ensure_ascii=False))
```

注意：`json` 已在 `agent.py` 的 import 列表中，`time` 也是，无需新增 import。

### Task 2：SYSTEM_PROMPT 设计目标

Token 预算分析：
- 中文字符 1 个 ≈ 1.5 token
- 目标 ≤ 800 token → 中文字符 ≤ 500 个
- 预估 300–400 字符即可满足要求，留足余量

必须包含的 4 个要素：
1. **角色定义**：智能租房助手，帮助用户在北京寻找和租赁房源
2. **工具调用指令**：涉及房源/操作时主动调用工具，禁止编造数据
3. **意图分类**：聊天→直接文字回复；房源搜索/操作→必须调工具
4. **格式指令**：不自行生成 JSON，不编造 HF_x ID，系统会自动处理格式

参考实现（仅供参考，开发者可优化措辞，不得删减 4 要素）：
```python
SYSTEM_PROMPT = """你是智能租房助手，帮助用户在北京寻找和租赁房源。

工具使用规则：
- 搜索房源（按区域/价格/户型/装修/朝向/地铁距离）→ 调用 search_houses
- 查看房源详情 → 调用 get_house_detail
- 搜索地标（地铁站/商圈/公司）→ 调用 search_landmark
- 查找地标附近房源 → 调用 search_nearby_landmark
- 查询周边生活配套 → 调用 get_nearby_amenities
- 租房/退租/下架操作 → 必须调用 execute_action（action: rent/terminate/offline）

意图分类：
- 涉及房源信息、租赁操作 → 必须调用工具，禁止猜测或编造数据
- 纯聊天或与房源无关的问题 → 直接自然语言回复，无需调工具

输出格式：
- 调用 search_houses 或 search_nearby_landmark 后，用自然语言描述推荐房源，系统自动处理 JSON 格式
- 禁止自行生成 JSON 格式输出
- 禁止编造房源 ID（格式如 HF_1）
- 每次最多推荐 5 套房源"""
```

### Task 3：main.py system message 注入的精确位置

完成后 `chat_endpoint` 新 Session 块应为：
```python
from agent import run_agent, log_event, SYSTEM_PROMPT   # ← 增加 SYSTEM_PROMPT

# ...

if request.session_id not in sessions:
    await init_houses(client)                              # Story 2.2（顺序不变）
    sessions[request.session_id] = []                     # Story 2.1（顺序不变）
    sessions[request.session_id].append(                  # ← Story 2.3 新增
        {"role": "system", "content": SYSTEM_PROMPT}
    )
history = sessions[request.session_id]
history.append({"role": "user", "content": request.message})
result = await run_agent(history, request.model_ip, client, session_id=request.session_id)
```

**关键注意**：`history = sessions[request.session_id]` 是引用赋值（Python dict value 引用），所以 history.append 直接修改 sessions 中的列表，这是正确的。system message 在 `sessions[id] = []` 后立即追加，确保后续所有轮次的 LLM 调用都包含 system message。

### Task 4：run_agent() 完整实现指南

**函数签名（向后兼容）：**
```python
async def run_agent(
    history: list,
    model_ip: str,
    client: httpx.AsyncClient,
    session_id: str = ""       # 新增可选参数，不影响现有 mock 测试
) -> dict:
```

**Assistant Message 追加格式（关键）：**
OpenAI SDK 返回的 `message` 对象需要转为 dict 追加到 history。手动构建最可靠：
```python
# 当有 tool_calls 时
assistant_msg: dict = {"role": "assistant", "content": message.content}
if message.tool_calls:
    assistant_msg["tool_calls"] = [
        {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments
            }
        }
        for call in message.tool_calls
    ]
history.append(assistant_msg)
```
⚠️ **禁止** 使用 `message.model_dump()` 或 `dict(message)`，这些可能引入 OpenAI SDK 内部字段导致后续 API 调用报错。

**LLM 调用（TOOLS 为空时不传 tools 参数）：**
```python
create_kwargs: dict = {
    "model": "",
    "messages": history,
}
if TOOLS:
    create_kwargs["tools"] = TOOLS
    create_kwargs["tool_choice"] = "auto"

response = await llm_client.chat.completions.create(**create_kwargs)
```

**Tool 调用循环（iterations 计数时机）：**
```python
# iterations 仅在 tool_calls 执行后递增，非每次 LLM 调用都计
if message.tool_calls:
    for call in message.tool_calls:
        tool_name = call.function.name
        args = json.loads(call.function.arguments)

        log_event("TOOL_CALL", session_id, {
            "tool_name": tool_name,
            "args": str(args)[:200]
        })

        fn = TOOL_DISPATCH.get(tool_name)
        result = await fn(client, **args) if fn else {"error": f"Unknown tool: {tool_name}"}

        tools_called.add(tool_name)
        tool_results_log.append({
            "tool_name": tool_name,
            "result": json.dumps(result, ensure_ascii=False)[:500]
        })

        history.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(result, ensure_ascii=False)   # ← 必须是字符串
        })

    iterations += 1
else:
    # finish_reason != "stop" 但无 tool_calls（异常情况）— 安全退出
    break
```

**Format Guard（循环退出后）：**
```python
import re   # 加到文件顶部 import

content = message.content or ""

if tools_called & HOUSE_SEARCH_TOOLS:
    # 从模型 content 提取有效 house ID，最多 5 个，去重保序
    raw_ids = re.findall(r'HF_\d+', content)
    seen: set[str] = set()
    houses: list[str] = []
    for hid in raw_ids:
        if hid not in seen and len(houses) < 5:
            seen.add(hid)
            houses.append(hid)
    response_str = json.dumps(
        {"message": content, "houses": houses},
        ensure_ascii=False
    )
    return {"response": response_str, "status": "success", "tool_results": tool_results_log}
else:
    return {"response": content, "status": "success", "tool_results": tool_results_log}
```

**Max iterations 退出路径：**
```python
if iterations >= MAX_ITERATIONS:
    log_event("ERROR", session_id, {"error": "Tool call limit exceeded"})
    return {
        "response": "Tool call limit exceeded",
        "status": "error",
        "tool_results": tool_results_log
    }
```

### TOOLS 为空时的行为（Story 2.3 阶段）

`tools.py` 中 `TOOLS = []` 目前是空列表占位（Story 3.1 才填充）。此时：
- `run_agent` 调用 LLM 时不传 `tools` 参数 → 模型以纯对话模式响应
- `message.tool_calls` 将为 None 或空
- `tools_called` 集合始终为空
- Format Guard 走聊天路径，返回 content 字符串
- 系统此时可运行，但无法执行工具（房源查询会返回对话而非 JSON）

**这是预期行为**，Story 3.1 补充 TOOLS 常量和工具函数实现后，系统才具备完整的工具调用能力。

### conftest.py 注意事项（沿用 Story 2.2 模式）

- `_clear_sessions` autouse fixture 已存在，每个测试前清空 sessions
- `_mock_init_houses` autouse fixture 已存在，防止真实 HTTP 请求
- 新的 `run_agent` 测试需要 mock LLM 调用：使用 `AsyncMock` patch `openai.AsyncOpenAI` 或 patch `agent.AsyncOpenAI`
- Story 2.3 相关测试推荐创建 `tests/test_agent_loop.py` 和 `tests/test_log_event.py`

**Mock LLM 调用模式（参考）：**
```python
from unittest.mock import AsyncMock, MagicMock, patch

def make_mock_response(content="hello", tool_calls=None, finish_reason="stop"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = MagicMock()
    resp.choices = [choice]
    return resp

# 在测试中：
mock_create = AsyncMock(return_value=make_mock_response("你好，有什么可以帮助您的？"))
with patch("agent.AsyncOpenAI") as mock_client_cls:
    mock_client_cls.return_value.chat.completions.create = mock_create
    result = await run_agent(history, "10.0.0.1", mock_httpx_client, "test-session")
    assert result["status"] == "success"
    assert result["response"] == "你好，有什么可以帮助您的？"
```

### 为什么 Story 2.3 同时实现 `log_event()`

`log_event()` 当前是 `pass` stub，但：
1. `run_agent()` 中需要调用 `log_event("MODEL_RESPONSE", ...)` 和 `log_event("TOOL_CALL", ...)`
2. `main.py` 已有 `log_event("ERROR", ...)` 调用（Storm 1.4 完成时加入）
3. Story 4.2 负责的是在 `main.py` 中增加 `SESSION_START` 和 `SESSION_INIT` 事件的调用点，不负责 `log_event()` 函数本身的实现
4. 故 Story 2.3 必须将 `log_event()` 从 `pass` 实现为真实函数，否则 `run_agent()` 无法正常工作

Story 4.2 只需在此基础上：在 `main.py` 的新 Session 块中增加两行 `log_event()` 调用即可（`SESSION_START` 和 `SESSION_INIT`）。

### 生产测试准备

完成本 Story 后，系统将具备以下能力（可在生产环境实测）：

**启动命令：**
```bash
USER_ID=<你的竞赛工号> uvicorn main:app --host 0.0.0.0 --port 8191
```

**Smoke Test 序列：**
```bash
# 1. 纯聊天测试（应返回自然语言字符串）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<模型IP>","session_id":"test-001","message":"你好"}'

# 2. 房源查询测试（暂时返回对话，Story 3.1 后返回 JSON）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<模型IP>","session_id":"test-002","message":"帮我找朝阳区两居室"}'

# 3. 多轮对话测试（同 session_id，第二次不应再触发 init）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<模型IP>","session_id":"test-001","message":"我需要在海淀区租房"}'
```

**验证要点：**
- 所有请求返回 HTTP 200（`status_code == 200`）
- `status` 字段为 `"success"` 或 `"error"`
- 第一次请求日志中出现 `SESSION_INIT` 事件（init_houses 被调用）
- 相同 session_id 第二次请求日志中不再出现 `SESSION_INIT`
- `duration_ms` 字段为非负整数（反映真实处理时间含 LLM 调用）

### 与 Story 3.1 的集成边界

| 能力 | Story 2.3 完成后状态 | Story 3.1 完成后状态 |
|------|-------------------|-------------------|
| 聊天回复 | ✅ 正常工作 | ✅ 正常工作 |
| 工具调用 | ❌ TOOLS 为空，LLM 无工具可调 | ✅ 全部 6 个工具可用 |
| 房源搜索 JSON 格式 | ❌ Format Guard 不触发（无工具调用） | ✅ 触发并返回合法 JSON |
| 意图分类（Agent Loop 逻辑） | ✅ 已实现（工具实现后自动生效） | ✅ 完整生效 |

### 文件变更范围

- `agent.py`：实现 `log_event()`、`SYSTEM_PROMPT`、`run_agent()`，新增 `import re`
- `main.py`：更新 import（添加 `SYSTEM_PROMPT`）+ 插入 system message append + 传递 `session_id` 给 `run_agent`
- `tests/test_log_event.py`：新建，覆盖 log_event 基础行为
- `tests/test_agent_loop.py`：新建，覆盖 run_agent 逻辑

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 2, Story 2.3 Acceptance Criteria（所有 AC 来源）]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Format Patterns: Format Guard 判断逻辑; Communication Patterns: Agent Loop 退出条件; Process Patterns: 日志格式]
- [Source: `_bmad-output/project-context.md` — LLM Tool Calling Loop; Response Format (CRITICAL); Critical Don't-Miss Rules]
- [Source: `_bmad-output/implementation-artifacts/2-2-new-session-init-hook.md` — Story 2.3 Integration Point section（system message 注入位置）]
- [Source: `agent.py` — 当前文件结构：SYSTEM_PROMPT="" 占位（line 12）、HOUSE_SEARCH_TOOLS（line 14）、TOOL_DISPATCH（line 16-23）、run_agent stub（line 31-33）]
- [Source: `main.py` — 当前 chat_endpoint 实现（lines 49-81）；新 Session 块（lines 54-56）；run_agent 调用点（line 59）]
- [Source: `tests/conftest.py` — autouse _clear_sessions 和 _mock_init_houses fixtures]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor Agent, 2026-02-27)

### Debug Log References

- conftest.py 需新增 `_mock_run_agent` autouse fixture，防止 `test_lifespan_http_client.py` 等原有测试因 `run_agent` 真实实现而挂起
- `test_chat_endpoint.py` 中 4 个 `capture_agent` 函数签名改为 `**kwargs` 接受新增 `session_id` 关键字参数
- `test_e2e_epic2.py` 中需 module 级 autouse fixture `_use_real_run_agent` 覆盖 conftest 默认 mock，确保 E2E 测试运行真实 Agent Loop
- SYSTEM_PROMPT 初始含 `HF_1` 示例，触发 `test_system_prompt_no_hardcoded_house_ids` 失败；改为不含具体 ID 的说明文字

### Completion Notes List

- **Task 1** ✅ `log_event()` 实现：JSON 结构化输出含 timestamp/session_id/event_type/details，ensure_ascii=False 保留中文
- **Task 2** ✅ `SYSTEM_PROMPT` 实现：4 要素齐全（角色/工具调用/意图分类/格式指令），中文字符约 300 个（≤500 预算），无预设 ID
- **Task 3** ✅ `main.py` 更新：导入 SYSTEM_PROMPT，新 session 初始化后立即注入 system message，`run_agent` 调用传递 `session_id`
- **Task 4** ✅ `run_agent()` 完整实现：while 循环/MAX_ITERATIONS 保护/AsyncOpenAI per-call/手动构建 assistant_msg/tool dispatch/Format Guard
- **Task 5** ✅ 新增 58 个测试（11+27+18+conftest），165 个测试全通过；原有 107 个测试零回归
- **E2E 测试** ✅ `test_e2e_epic2.py` 18 个测试覆盖：HTTP 可达性/响应字段结构/Session 管理/Agent Loop 执行/错误处理

### File List

- `agent.py` — 实现 `log_event()`、`SYSTEM_PROMPT`、`run_agent()`，新增 `import re`
- `main.py` — 更新 import（添加 `SYSTEM_PROMPT`）+ 插入 system message append + 传递 `session_id` 给 `run_agent`
- `tests/test_log_event.py` — 新建，11 个测试覆盖 log_event 基础行为
- `tests/test_agent_loop.py` — 新建，27 个测试覆盖 run_agent 完整逻辑
- `tests/test_e2e_epic2.py` — 新建，18 个 E2E 测试覆盖原型系统可运行能力（用户额外要求）
- `tests/conftest.py` — 新增 `_mock_run_agent` autouse fixture，防止真实 LLM 调用
- `tests/test_chat_endpoint.py` — 更新 4 个 `capture_agent` 函数签名（向后兼容 session_id 参数）
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 更新 Story 2.3 状态

## Senior Developer Review (AI)

**Reviewer:** LJW on 2026-02-27
**Outcome:** Approved (with fixes applied)

**Review Summary:**
- All 7 ACs verified as IMPLEMENTED
- All 5 Tasks marked [x] verified as DONE
- Git vs Story File List: 1 discrepancy (sprint-status.yaml undocumented, now fixed)
- 165 tests pass, zero regression

**Issues Found & Fixed (3 MEDIUM, 2 LOW):**
1. [M1] agent.py — `json.loads(call.function.arguments)` 添加 try/except 防护畸形 LLM 参数
2. [M2] agent.py — `response.choices[0]` 添加空 choices 列表防御性检查
3. [M3] test_log_event.py — 移除未使用 import (`io`, `sys`)
4. [L1] test_agent_loop.py — `import re` 移至模块顶层
5. [L2] Story File List — 补充 sprint-status.yaml 条目

## Change Log

- 2026-02-27: Story 2.3 实现完成。实现 log_event()、SYSTEM_PROMPT、run_agent() 完整 Agent Loop；新增 58 个测试（含 18 个 E2E 测试）；全量 165 个测试通过。
- 2026-02-27: Code Review 完成。修复 3 个 MEDIUM + 2 个 LOW 问题（json.loads 异常处理、空 choices 防护、未使用 import、import 位置、File List 遗漏）；165 测试全通过，Status → done。
