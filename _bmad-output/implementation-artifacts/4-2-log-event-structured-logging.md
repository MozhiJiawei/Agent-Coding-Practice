# Story 4.2: log_event 结构化日志系统

Status: done

## Story

As a developer,
I want every key agent event logged in structured JSON format to per-session files,
So that I can trace the full execution path of any request, quickly identify which tool call caused a scoring failure, and reproduce test cases locally from debug logs.

## Acceptance Criteria

### 基础行为（来自 epics.md FR24）

1. `log_event` 输出包含 `ts`（Unix int timestamp）、`session_id`（str）、`event`（str）、`details`（dict）的结构化日志条目，每条日志行均可通过 `json.loads()` 解析
2. 以下 5 种 event 类型在正确时机被记录：


| event            | 触发时机                         | 调用位置               |
| ---------------- | ---------------------------- | ------------------ |
| `SESSION_START`  | 新 session_id 首次出现            | main.py            |
| `SESSION_INIT`   | `POST /api/houses/init` 被调用前 | main.py            |
| `TOOL_CALL`      | 每个工具函数被分发时                   | agent.py           |
| `MODEL_RESPONSE` | 模型返回任意响应时                    | agent.py           |
| `ERROR`          | 任何被捕获的异常                     | agent.py + main.py |


1. 不同 `session_id` 的日志条目不发生交叉污染

### 新增要求（用户补充）

1. **按 session 写入独立文件**：日志写入 `logs/{session_id}.jsonl`（JSONL 格式，每行一个 JSON 对象）；不使用 stdout；`logs/` 目录不存在时自动创建
2. **文件精简无冗余**：字段仅保留必要信息（`ts`、`session_id`、`event`、`details`），同一文件中 session_id 字段值相同但保留以支持跨文件 grep
3. **调试信息 — LLM 服务器交互**：每次 `llm_client.chat.completions.create()` 调用**前**记录 `LLM_REQUEST` 事件，details 含 `iteration`（当前迭代编号）和 `message_count`（history 消息总数）；现有 `MODEL_RESPONSE` 事件保留不变
4. **调试信息 — 工具服务器交互**：`TOOL_CALL` 事件的 details 新增 `result_preview` 字段（工具返回结果序列化后前 300 字符），供本地复现工具服务器响应使用
5. **错误日志含调用栈**：`log_event` 接受可选 `exc: BaseException | None = None` 参数；若 exc 不为 None，则 details 中追加 `traceback` 字段（`traceback.format_exc()` 输出）

## Tasks / Subtasks

- Task 1: 新建 `logger.py`（AC: #1, #4, #5, #8）
  - [x] 1.1 导入 `json`, `time`, `traceback`, `pathlib.Path`
  - [x] 1.2 定义 `LOG_DIR = Path("logs")`
  - [x] 1.3 实现 `log_event(event_type: str, session_id: str, details: dict, exc: BaseException | None = None) -> None`
    - 若 exc 不为 None，将 `traceback.format_exc()` 赋值到 `details["traceback"]`（操作副本，不修改原 dict）
    - `LOG_DIR.mkdir(exist_ok=True)` 确保目录存在
    - 写入路径：`LOG_DIR / f"{session_id}.jsonl"`（使用 `open(path, "a", encoding="utf-8")`）
    - 写入内容：`json.dumps({"ts": int(time.time()), "session_id": session_id, "event": event_type, "details": d}, ensure_ascii=False) + "\n"`
- Task 2: 更新 `agent.py`（AC: #2-TOOL_CALL, #2-MODEL_RESPONSE, #2-ERROR, #6, #7）
  - [x] 2.1 删除 `agent.py` 内置的 `log_event` 函数及其 `import time`（time 已在 logger.py 使用）；改为 `from logger import log_event`
  - [x] 2.2 在每次 `llm_client.chat.completions.create(**create_kwargs)` 调用**前**插入 `LLM_REQUEST` 事件：`log_event("LLM_REQUEST", session_id, {"iteration": iterations, "message_count": len(history)})`
  - [x] 2.3 工具调用 `result = await fn(client, **args)` 执行后，在 TOOL_CALL 的 details 中追加 `result_preview`：`json.dumps(result, ensure_ascii=False)[:300]`
  - [x] 2.4 `iterations >= MAX_ITERATIONS` 的 ERROR 调用加入 `exc=None`（无 exception 对象，现有行为不变）
- Task 3: 更新 `main.py`（AC: #2-SESSION_START, #2-SESSION_INIT, #2-ERROR）
  - [x] 3.1 将 `from agent import run_agent, log_event, SYSTEM_PROMPT` 改为 `from agent import run_agent, SYSTEM_PROMPT` + `from logger import log_event`
  - [x] 3.2 在新 session 检测处（`if request.session_id not in sessions:` 块入口）调用：`log_event("SESSION_START", request.session_id, {})`
  - [x] 3.3 在 `await init_houses(client)` 调用**前**调用：`log_event("SESSION_INIT", request.session_id, {})`
  - [x] 3.4 全局 `except Exception as e:` 块中调用：`log_event("ERROR", request.session_id, {"error": str(e)}, exc=e)`

## Dev Notes

### 关键设计约束

- **不引入新外部依赖**：`pathlib`、`traceback`、`json`、`time` 均为 Python 标准库，`requirements.txt` 无需修改
- **同步文件 I/O**：竞赛环境评判系统串行发请求，sync `open()` + `write()` 满足 NFR1（< 5s 非模型执行时间）；单次 `write()` 调用写入一行，系统级原子写，无数据竞争风险
- **import 方向约束**：`main.py → agent.py → tools.py` 禁止循环导入。`logger.py` 作为零依赖工具模块，可被 `main.py`、`agent.py` 同时导入，不产生循环依赖；`tools.py` 本次无需导入 logger（工具服务器交互细节通过 agent.py 的 `result_preview` 覆盖）
- **traceback 采集时机**：在 `except` 块内调用 `log_event(..., exc=e)` 时，`traceback.format_exc()` 自动捕获当前活跃异常的调用栈，无需额外处理
- **session_id 文件名安全**：竞赛环境下 session_id 为系统生成的 UUID 字符串，无路径遍历风险；如需防御可在 logger.py 中做 `session_id.replace("/", "_")` 处理
- `**log_event` 签名向后兼容**：新增 `exc` 为可选参数默认 None，现有所有调用无需改动

### Project Structure Notes


| 文件          | 变更类型  | 说明                                                          |
| ----------- | ----- | ----------------------------------------------------------- |
| `logger.py` | 新增    | 唯一日志工具模块，供 main.py 和 agent.py 导入                            |
| `agent.py`  | 修改    | 删除内置 log_event，更新 import，添加 LLM_REQUEST 事件和 result_preview  |
| `main.py`   | 修改    | 更新 log_event import，补充 SESSION_START/SESSION_INIT 调用，传入 exc |
| `tools.py`  | 不修改   | 工具函数签名保持不变                                                  |
| `logs/`     | 运行时创建 | 建议加入 `.gitignore` 避免日志文件提交到版本库                              |


**新增 `logger.py` 的必要性**：`agent.py` 和 `main.py` 都需要调用 `log_event`，若定义在 `agent.py` 则 `main.py` 从 `agent` 导入可行，但 `log_event` 与 Agent Loop 无关，职责不单一；更重要的是未来若 `tools.py` 也需要日志能力，无法从 `agent.py` 导入（循环依赖）。独立 `logger.py` 是最小化变更的正确分层。

### 日志事件 details 字段参考


| event            | details 关键字段                                                             |
| ---------------- | ------------------------------------------------------------------------ |
| `SESSION_START`  | `{}` (空)                                                                 |
| `SESSION_INIT`   | `{}` (空)                                                                 |
| `LLM_REQUEST`    | `{"iteration": int, "message_count": int}`                               |
| `MODEL_RESPONSE` | `{"finish_reason": str, "content_preview": str(前100字符)}`                 |
| `TOOL_CALL`      | `{"tool_name": str, "args": str(前200字符), "result_preview": str(前300字符)}` |
| `ERROR`          | `{"error": str, "traceback": str}` (traceback 仅在 exc 不为 None 时出现)        |


### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-4.2] — FR24 日志格式规范、5 种事件类型触发时机定义
- [Source: _bmad-output/planning-artifacts/epics.md#Architecture-日志约束] — `log_event()` 函数、JSON 格式输出、覆盖 5 种 event_type 常量
- [Source: _bmad-output/project-context.md#Code-Quality-Rules] — 「Single-file preferred」约束（logger.py 因跨模块共享需求为必要例外）、「No unused imports」
- [Source: agent.py#log_event L46-52] — 现有 log_event 实现（print + json.dumps），本 story 替换为文件写入
- [Source: main.py#chat_endpoint L58-86] — SESSION_START/SESSION_INIT/ERROR 插入位置

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor Agent, 2026-02-28)

### Debug Log References

TDD 方式执行：先写 `tests/test_logger.py` + 更新 `tests/test_log_event.py` / `tests/test_agent_loop.py` / `tests/test_chat_endpoint.py`（RED），确认因 `logger.py` 不存在而失败；再实现代码（GREEN）；全套 258 个测试 100% 通过。

### Completion Notes List

- **Task 1**: 新建 `logger.py`（27 行）。`LOG_DIR = Path("logs")`；`log_event` 写入 `logs/{session_id}.jsonl`，字段 `ts/session_id/event/details`；`exc` 参数操作 dict 副本注入 `traceback.format_exc()`，不修改原 dict。全新 21 个测试通过。
- **Task 2**: `agent.py` 删除内置 `log_event` 及 `import time`，改为 `from logger import log_event`；在 `create()` 前插入 `LLM_REQUEST` 事件（含 `iteration` / `message_count`）；工具执行后在 `TOOL_CALL.details` 追加 `result_preview`（前 300 字符）。新增 5 个集成测试通过。
- **Task 3**: `main.py` 更新 import；新 session 分别在 `SESSION_START` → `SESSION_INIT` 顺序调用；`except` 块传入 `exc=e`。新增 4 个测试通过。
- 全套 258 个测试，无回归。

### Code Review Fixes (AI)

- **[HIGH] logger.py:17** — `traceback.format_exc()` → `traceback.format_exception(type(exc), exc, exc.__traceback__)` — 修复在 except 块外调用时 traceback 丢失的正确性缺陷
- **[MEDIUM] .gitignore** — 新增 `logs/` 条目，防止运行时日志文件被提交到版本库
- **[MEDIUM] agent.py:129** — 未知工具名分派时新增 `log_event("ERROR", ...)` 调用，确保异常路径有日志覆盖
- 新增 2 个测试覆盖修复点，全套 260 个测试 100% 通过

### File List

- logger.py (new)
- agent.py (modified)
- main.py (modified)
- tests/test_logger.py (new)
- tests/test_log_event.py (modified — 改为测试 logger 模块文件输出)
- tests/test_agent_loop.py (modified — TestLogEventCalledInRunAgent 改为文件输出验证，新增 LLM_REQUEST / result_preview 测试)
- tests/test_chat_endpoint.py (modified — 更新 ERROR 断言，新增 TestSessionLogging 类)
- .gitignore (modified — 新增 logs/ 条目)

