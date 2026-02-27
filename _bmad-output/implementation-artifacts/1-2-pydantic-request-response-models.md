# Story 1.2: Pydantic 请求与响应数据模型

Status: done

## Story

As the judging system,
I want the API to accept and return strictly validated JSON structures,
so that all requests and responses are type-safe and predictable.

## Acceptance Criteria

1. **Given** `main.py` is reviewed  
   **When** Pydantic models are checked  
   **Then** `ChatRequest` contains exactly: `model_ip: str`, `session_id: str`, `message: str`

2. **Given** `main.py` is reviewed  
   **When** `ChatResponse` is checked  
   **Then** it contains exactly: `session_id: str`, `response: str`, `status: str`, `tool_results: list`, `timestamp: int`, `duration_ms: int`

3. **Given** `main.py` is reviewed  
   **When** `ToolResult` is checked  
   **Then** it contains at minimum: `tool_name: str`, `result: str`

4. **Given** all models are defined  
   **When** naming convention is reviewed  
   **Then** all model class names use PascalCase (`ChatRequest`, `ChatResponse`, `ToolResult`)  
   **And** all field names use `snake_case`

5. **Given** FastAPI app is running  
   **When** `POST /api/v1/chat` returns a `ChatResponse`  
   **Then** FastAPI serializes it automatically to JSON without additional configuration

## Tasks / Subtasks

- [x] Task 1: 验证现有 Pydantic 模型实现是否满足所有 AC (AC: 1-5)
  - [x] 对照 AC 逐一核查 `ChatRequest` 字段
  - [x] 对照 AC 逐一核查 `ChatResponse` 字段
  - [x] 对照 AC 逐一核查 `ToolResult` 字段
  - [x] 确认命名规范：类名 PascalCase，字段名 snake_case

- [x] Task 2: 修复发现的任何不符合项 (AC: 1-5)
  - [x] 若有字段缺失或类型错误，在 `main.py` 中修正

- [x] Task 3: 验证 FastAPI 序列化 (AC: 5)
  - [x] 确认 `response_model=ChatResponse` 在路由中已设置
  - [x] 运行 `python -c "from main import ChatRequest, ChatResponse, ToolResult; print('OK')"` 无报错

## Dev Notes

### 🚨 关键上下文：现有代码状态

**Story 1.1 完成时，开发 Agent 已在 `main.py` 中创建了以下实现（截至 2026-02-27）：**

```python
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
    tool_results: list[ToolResult]
    timestamp: int
    duration_ms: int
```

**快速评估：** 以上实现已满足所有 AC。本故事的主要任务是**验证正确性**，而不是重新实现。

**⚠️ 不得重写已正确的代码！**

### 架构合规要求

**Pydantic 模型位置（严格）：**
- 所有 3 个模型必须定义在 `main.py` 中，位于文件顶部（导入之后，全局变量之前）
- 禁止移动到单独的 `models.py` 文件（架构要求三文件结构，不得新增文件）

**`tool_results` 字段类型说明：**
- 可以使用 `list[ToolResult]`（比 `list` 更严格的类型提示）
- FastAPI 对两者的序列化结果相同，但 `list[ToolResult]` 更符合 Pydantic v2 最佳实践
- **不得将 `list[ToolResult]` 改回裸 `list`**

**`status` 字段允许值（运行时约束，不在模型中 enum 化）：**
- `"success"` — 正常响应
- `"error"` — 异常响应
- 架构决策：不使用 `Literal["success", "error"]` 约束，以保持模型简单（竞赛环境）

**`timestamp` 和 `duration_ms` 的运行时赋值（将在 Story 1.4 实现）：**
```python
timestamp=int(time.time())       # Unix 整数
duration_ms=int((time.time() - start_time) * 1000)  # 真实壁钟毫秒数
```
这两个字段在本故事中只需确保类型为 `int`，具体赋值逻辑在 Story 1.4 中实现。

### 与其他故事的依赖关系

| 故事 | 依赖关系 |
|------|---------|
| Story 1.3 (lifespan) | 不依赖本故事的模型，可并行 |
| Story 1.4 (路由) | **依赖本故事** — 路由函数的返回类型为 `ChatResponse` |
| Story 2.x (Agent Loop) | `run_agent()` 返回值将填充 `ChatResponse` 字段 |

### 竞赛合规提醒

- `model_ip` 字段来自请求体，用于动态构建 LLM URL：`f"http://{model_ip}:8888/v1"`
- **绝不**在 Pydantic 模型中添加默认值给 `model_ip`（不允许硬编码 IP）
- `tool_results` 在错误响应时允许为空列表 `[]`

### Project Structure Notes

**`main.py` 内部结构（本故事完成后应如下）：**
```
1. 导入（time, os, asynccontextmanager, FastAPI, httpx, BaseModel, run_agent）
2. Pydantic 模型（ToolResult, ChatRequest, ChatResponse）← 本故事关注点
3. 全局变量（sessions: dict[str, list] = {}）
4. lifespan 上下文管理器
5. FastAPI app 实例
6. POST /api/v1/chat 路由
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 1, Story 1.2]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Naming Patterns, Format Patterns, File Organization Patterns]
- [Source: `_bmad-output/planning-artifacts/prd.md` — Endpoint Specification, Data Schemas]
- [Source: `main.py` — 现有实现（Story 1.1 遗留）]

## Senior Developer Review (AI)

**Review Date:** 2026-02-27
**Review Outcome:** Changes Requested
**Severity Breakdown:** 0 Critical, 5 Medium, 2 Low

### Action Items

- [x] [M1] 添加字段数量精确断言（AC 1/2 的 "exactly" 约束）[tests/test_models.py]
- [x] [M2] 补全 ChatResponse snake_case 字段名验证（遗漏 response, status, timestamp）[tests/test_models.py]
- [x] [M3] 添加 tool_results 类型强验证负面测试 [tests/test_models.py]
- [x] [M4] 添加 HTTP 级 TestClient 集成测试验证端到端 JSON 序列化 [tests/test_models.py]
- [x] [M5] 移除 main.py 未使用的 import os [main.py]
- [x] [L1] requirements.txt 添加 pytest 测试依赖 [requirements.txt]
- [ ] [L2] base_url 硬编码重复（跨 Story 范围，标记待后续处理）[main.py, tools.py]

## Dev Agent Record

### Agent Model Used

claude-4.6-opus-high-thinking (Cursor Dev Agent)

### Debug Log References

- `tools.py` 模块级 `os.environ["USER_ID"]` 在测试收集阶段导致 KeyError；通过在 `tests/conftest.py` 中预设 `USER_ID=test-user-placeholder` 解决，未修改生产代码。

### Completion Notes List

- 验证 `main.py` 中 `ToolResult`、`ChatRequest`、`ChatResponse` 三个 Pydantic 模型，全部满足 AC 1-5，无需修改。
- 采用 TDD 流程：先在 `tests/test_models.py` 创建 33 条单元测试，覆盖字段存在性、类型检查、必填校验、命名规范、FastAPI 序列化等；测试全部通过（33/33）。
- 创建 `tests/conftest.py` 处理测试环境变量依赖，不影响生产代码。
- ✅ Code Review 修复：新增 4 条测试（字段精确数量、snake_case 全覆盖、类型负面验证、HTTP TestClient），移除 main.py 死代码 import，补充 pytest 依赖。测试增至 37/37 全部通过。

### File List

- `main.py`（修改 — 移除未使用的 `import os`）
- `tests/__init__.py`（新增 — 测试包初始化）
- `tests/conftest.py`（新增 — pytest 环境变量预设）
- `tests/test_models.py`（新增 — Story 1.2 Pydantic 模型单元测试，37 个测试用例）
- `requirements.txt`（修改 — 添加 pytest 依赖）

### Change Log

- 2026-02-27: Story 1.2 实现完成。TDD 验证 Pydantic 模型合规性，新增 tests/ 目录及 33 条单元测试，全部通过。状态变更为 review。
- 2026-02-27: Code Review 修复 — 解决 5 个 Medium + 1 个 Low 问题：补全精确字段数断言、snake_case 全字段覆盖、tool_results 负面类型测试、HTTP TestClient 集成测试、移除死代码 import os、添加 pytest 依赖。测试 37/37 通过。
