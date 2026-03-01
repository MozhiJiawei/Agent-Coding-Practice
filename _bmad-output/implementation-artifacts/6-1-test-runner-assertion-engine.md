# Story 6.1: Test Runner 与断言引擎

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer (LJW),
I want a Test Runner that sequentially drives multi-round chat with the Agent and an assertion engine that validates outcomes against configured expect rules,
So that I can automatically verify whether the Agent produces correct responses for each test case, with precise PASS/FAIL/ERROR/TIMEOUT verdicts and human-readable failure details that pinpoint exactly what went wrong.

## Acceptance Criteria

**AC1 — run_single_case 逐轮顺序发送**

**Given** `run_single_case(case, config, client, token_counter)` 在 `runner.py` 中被调用，`TestCase` 的 `messages` 为 `["你好", "帮我找房"]`，
**When** 针对运行中的 Agent 执行，
**Then** `send_message()` 对每条消息按序调用；每次调用 `await` Agent 的 HTTP 响应后再发下一轮；返回的 `CaseResult` 的 `rounds` 等于已发送的消息数

**AC2 — send_message 请求格式**

**Given** `send_message(client, agent_base_url, session_id, model_ip, message)` 被调用，
**When** 发起 HTTP POST，
**Then** 请求发送至 `{agent_base_url}/api/v1/chat`，body 为 `{"model_ip": model_ip, "session_id": session_id, "message": message}`；`session_id` 格式为 `test-{case.id}-{unix_timestamp}`，每个用例执行时唯一（FR1, FR3, FR5）

**AC3 — ASSERTION_RULES 定义**

**Given** `ASSERTION_RULES` 字典在 `runner.py` 中定义，
**When** 被检视，
**Then** 映射以下键到可调用函数：`has_response`、`response_not_empty`、`response_json_valid`、`houses_match`、`houses_match_subset`、`house_count_min`、`status_success`

**AC4 — 断言函数返回格式**

**Given** 任意断言函数 `fn(response: dict, expected: Any)` 被调用，
**When** 以任意输入执行，
**Then** 始终返回 `(bool, str)`，永不抛出异常；通过时字符串为 `""`；失败时字符串包含人类可读的失败描述（NFR8）

**AC5 — houses_match 精确匹配**

**Given** `expect: {houses_match: ["HF_42", "HF_107"]}` 且 Agent 响应的 `response` 字段包含 JSON `{"houses": ["HF_42"]}`，
**When** `houses_match` 断言执行，
**Then** 返回 `(False, "houses_match: expected ['HF_42', 'HF_107'], got ['HF_42']")`

**AC6 — houses_match_subset 子集匹配**

**Given** `expect: {houses_match_subset: true}` 且预期房源 ID（在测试用例中配置）均出现在 Agent 的 `houses` 列表中，
**When** `houses_match_subset` 断言执行，
**Then** 返回 `(True, "")`，确认 `set(expected_ids) ⊆ set(actual_houses)`（FR20）

**AC7 — 超时判定**

**Given** 测试用例执行超过 `config.timeout_per_case` 秒，
**When** 使用 `asyncio.wait_for(run_single_case(...), timeout=config.timeout_per_case)` 包装，
**Then** 返回 `CaseResult(status="TIMEOUT", failure_reason="超时 {N}s", rounds=0, duration_ms=N*1000)`（NFR1）

**AC8 — 连接失败处理**

**Given** Agent 服务不可达（connection refused），
**When** `send_message()` 抛出 `httpx.ConnectError`，
**Then** 返回 `CaseResult(status="ERROR", failure_reason="Chat 不通: {error_detail}")`；runner 循环继续下一用例，不崩溃

**AC9 — print_case_result PASS 输出**

**Given** 完成的 `CaseResult` 状态为 PASS，
**When** 调用 `print_case_result(idx, total, result)`，
**Then** stdout 显示 `[{idx}/{total}] {case_id} ...... PASS  ({duration}s)`

**AC10 — print_case_result FAIL 输出**

**Given** 完成的 `CaseResult` 状态为 FAIL 或 ERROR 或 TIMEOUT，
**When** 调用 `print_case_result(idx, total, result)`，
**Then** stdout 显示 `[{idx}/{total}] {case_id} ...... FAIL  ({duration}s)`，下一行显示 `       ✗ {failure_reason}`

---

## Tasks / Subtasks

- [x] Task 1：实现 send_message（AC: 2）
  - [x] 1.1 定义 `send_message(client, agent_base_url, session_id, model_ip, message) -> tuple[dict, None] | tuple[None, str]`
  - [x] 1.2 POST 至 `{agent_base_url}/api/v1/chat`，body `{"model_ip": model_ip, "session_id": session_id, "message": message}`
  - [x] 1.3 捕获 `httpx.ConnectError` 返回 `(None, "Chat 不通: {detail}")`
  - [x] 1.4 成功时解析 JSON 返回 `(body, None)`

- [x] Task 2：实现 ASSERTION_RULES（AC: 3, 4, 5, 6）
  - [x] 2.1 实现 `has_response(response, expected)`：检查 response 存在
  - [x] 2.2 实现 `response_not_empty(response, expected)`：检查 response.response 非空
  - [x] 2.3 实现 `response_json_valid(response, expected)`：检查 response.response 为合法 JSON
  - [x] 2.4 实现 `houses_match(response, expected)`：精确匹配 houses 列表（expected 为 list[str]）
  - [x] 2.5 实现 `houses_match_subset(response, expected)`：子集匹配，expected_ids 从 `expect.houses_match` 取；检查 `set(expected) ⊆ set(actual)`
  - [x] 2.6 实现 `house_count_min(response, expected)`：检查 houses 数量 ≥ expected
  - [x] 2.7 实现 `status_success(response, expected)`：检查 response.status == "success"
  - [x] 2.8 定义 `check_assertions(response: dict, expect: ExpectRules, case: TestCase) -> tuple[bool, str]`，逐条检查 expect 规则

- [x] Task 3：实现 run_single_case（AC: 1, 7, 8）
  - [x] 3.1 生成 `session_id = f"test-{case.id}-{int(time.time())}"`
  - [x] 3.2 使用 `model_ip = "127.0.0.1"`（与 stub 保持一致）
  - [x] 3.3 逐条消息调用 `send_message`，每轮 await 响应后再发下一轮
  - [x] 3.4 聚合最后一轮 response，调用 `check_assertions` 判定 PASS/FAIL
  - [x] 3.5 用 `asyncio.wait_for(..., timeout=config.timeout_per_case)` 包装，超时返回 TIMEOUT
  - [x] 3.6 构建 `CaseResult`，含 case_id、case_type、status、duration_ms、rounds、failure_reason、actual_response、token_usage

- [x] Task 4：实现 print_case_result（AC: 9, 10）
  - [x] 4.1 PASS：`[{idx}/{total}] {case_id} ...... PASS  ({duration}s)`
  - [x] 4.2 FAIL/ERROR/TIMEOUT：同上 + 下一行 `       ✗ {failure_reason}`

- [x] Task 5：实现 run_all_cases 与导出
  - [x] 5.1 `run_all_cases(cases, config, token_counter) -> list[CaseResult]`
  - [x] 5.2 顺序执行每个 case，每 case 前 `token_counter.reset()`，执行后累加 token 到 CaseResult
  - [x] 5.3 导出 `send_message`、`run_single_case`、`run_all_cases`、`print_case_result`、`ASSERTION_RULES`、`check_assertions`

## Dev Notes

### 关键架构背景

本 Story 是 Test Simulator 的**测试执行与断言层**。Story 5-1、5-2 已完成 config + fixture + mock_rental；本 Story 将 runner.py 从 stub 完善为完整实现，main.py 的 `--all`/`--tag` 及 `generate_reports` 留待 Story 6-2。

**当前 main.py 状态：**
- 仅有 `--case`，无 `--all`、`--tag`
- 使用 `run_single_case_stub`（无断言、无 CaseResult 结构）
- 本 Story 只需实现 runner.py 核心逻辑；main.py 在 6-2 中改为调用 `run_all_cases`、`generate_reports`

### 技术栈与约束

- Python 3.11+，httpx.AsyncClient（async），asyncio
- Agent Chat API：`POST {agent_base_url}/api/v1/chat`，body `{"model_ip", "session_id", "message"}`，响应含 `response`、`status`、`tool_results`、`duration_ms`
- 房源查询 response 格式：`{"message": "...", "houses": ["HF_x", ...]}`（JSON 字符串）
- config.py 已有：`SimulatorConfig`、`TestCase`、`ExpectRules`、`CaseResult`、`TokenUsage`、`TokenCounter`

### houses_match_subset 的 expected_ids 来源

Epics AC6：「expected house IDs (configured in the test case)」。**约定**：当 `houses_match_subset: true` 时，使用 `expect.houses_match` 作为 expected IDs（若存在）。即：

```yaml
expect:
  houses_match_subset: true
  houses_match: ["HF_42", "HF_107"]   # 子集检查的预期 ID
```

检查逻辑：`set(expect.houses_match or []) ⊆ set(actual_houses)`。若 `houses_match` 为空或未配置，则仅检查 actual 非空且为合法 JSON。

### model_ip 配置

当前 SimulatorConfig 无 model_ip。main.py stub 硬编码 `"127.0.0.1"`。可选：
- **短期**：runner 内硬编码 `"127.0.0.1"`（与 stub 一致）
- **长期**：在 config.py 增加 `model_ip: str = "127.0.0.1"`，本 Story 可不改 config，留待 6-2 统一

### 断言函数 response 参数格式

`response` 为 Agent 的 Chat 响应 body（dict），包含：
- `response`：str，Agent 回复文本
- `status`：str，如 "success"、"error"
- `duration_ms`：int

从 `response["response"]` 解析 JSON 提取 `houses` 列表时，需处理非 JSON、无 houses 字段等情况，断言函数不得抛异常，返回 `(False, "详细原因")`。

### extract_house_ids 辅助函数

实现 `extract_house_ids(resp_text: str) -> list[str]`：对 `resp_text` 做 `json.loads`，取 `["houses"]`，若非 list 或含非字符串元素则返回 `[]`。供 `houses_match`、`houses_match_subset`、`house_count_min` 复用。

### Project Structure Notes

- **runner.py** — 本 Story 唯一修改文件，实现完整
- **main.py** — 本 Story 不修改（6-2 中集成 run_all_cases + generate_reports）
- **config.py** — 已有 ExpectRules、CaseResult，无需改

### 已有文件参考路径

| 文件 | 描述 |
|------|------|
| `test-simulator/runner.py` | 当前为 stub，TODO Story 6.1 |
| `test-simulator/config.py` | SimulatorConfig、ExpectRules、TestCase、CaseResult、TokenUsage、TokenCounter |
| `test-simulator/main.py` | run_single_case_stub、--case 逻辑，可参考 HTTP 调用方式 |
| `docs/interface.md` | Agent Chat API 请求/响应格式 |
| `_bmad-output/implementation-artifacts/5-2-mock-rental-api-programmatic.md` | 上一 Test Simulator story，fixture 与 mock 行为 |

### Previous Story Intelligence（5-2-mock-rental-api-programmatic）

- **TestClient 与 lifespan**：测试时若用 TestClient，须作为上下文管理器 `with TestClient(app) as tc` 以触发 lifespan，否则 `app.state` 未初始化
- **步行距离计算**：`walking_distance` 应先 `int(dist)` 再 × 1.3，避免浮点精度问题
- **响应格式**：所有 mock 端点统一 `{"code": 0, "message": "success", "data": {...}}`
- **Agent 请求 response 格式**：房源推荐时 `response` 为 JSON 字符串 `json.dumps({"message": "...", "houses": [...]})`，断言需从 `response["response"]` 解析

### Architecture Compliance

- **单向导入链**：main → runner/model_proxy/mock_rental → config，禁止循环依赖
- **runner.py 职责**：向 Agent 发送消息、接收响应、断言检查、报告生成；禁止定义 API 路由、fixture 处理
- **httpx 客户端**：由 main 创建并传入 runner，或 runner 在 run_single_case 内创建 `async with httpx.AsyncClient(timeout=...)`，确保每 case 独立

### Library / Framework Requirements

- **httpx**：使用 `AsyncClient`，`timeout` 建议 `config.timeout_per_case` 或 120.0（单次 HTTP 可能涉及多轮 LLM）
- **asyncio**：`asyncio.wait_for` 包装整个 run_single_case
- **json**：解析 Agent response 中的 JSON 字符串

### Testing Requirements

- 单元测试建议：`test-simulator/tests/test_runner.py`，mock httpx 或 Agent 响应，验证 send_message、ASSERTION_RULES、check_assertions、run_single_case 行为
- 集成测试：需真实 Agent + Model Proxy + Mock Rental 运行，留待 E2E 或 Story 6-2 后

### References

- [Source: _bmad-output/planning-artifacts/epics-test-simulator.md#Story 2.1]
- [Source: _bmad-output/planning-artifacts/architecture-test-simulator.md#断言引擎]
- [Source: docs/interface.md]
- [Source: test-simulator/config.py]
- [Source: _bmad-output/project-context.md]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor)

### Debug Log References

无阻塞问题，所有任务一次通过。

### Completion Notes List

- **Task 1 (send_message)**：实现 async POST 函数，精确匹配 AC2 接口格式；捕获 `httpx.ConnectError` 返回 `(None, "Chat 不通: ...")` 错误元组。
- **Task 2 (ASSERTION_RULES + check_assertions)**：实现 7 个断言函数，均返回 `(bool, str)` 且永不抛异常（AC4）；`extract_house_ids` 辅助函数供三个 houses_* 断言共用；`check_assertions` 按规则逐条检查，首次失败即返回原因。
- **Task 3 (run_single_case)**：session_id 格式 `test-{case.id}-{unix_ts}`；逐轮顺序发送（AC1）；用 `asyncio.wait_for` 包装超时（AC7）；`ConnectError` 返回 ERROR（AC8）；内部拆分 `_execute_case` 避免 TimeoutError 影响 rounds 计数。
- **Task 4 (print_case_result)**：PASS 输出格式符合 AC9；FAIL/ERROR/TIMEOUT 追加 `✗ reason` 行（AC10）。
- **Task 5 (run_all_cases)**：独立创建 `AsyncClient`，每 case 前重置 `token_counter`；顺序执行返回 `list[CaseResult]`。
- **测试**：52 个单元测试，覆盖所有 AC；运行全套 193 个测试，零回归。

### File List

- `test-simulator/runner.py` — 主要实现文件（从 stub 完整实现）
- `test-simulator/tests/test_runner.py` — 单元测试（55 个测试）
- `test-simulator/tests/__init__.py` — 测试包初始化文件

### Change Log

- 2026-03-01: 实现 Story 6.1 — Test Runner 与断言引擎（runner.py 从 stub 完整实现，新增 test_runner.py）
- 2026-03-01: Code Review 修复 — [H1] houses_match 改用 sorted 比较（对齐架构 set 语义）；[M1] _house_count_min 加 ValueError 保护（AC4 合规）；[M2] send_message 扩展异常捕获（非 JSON 响应、超时、HTTP 错误）；[M3] 新增 tests/__init__.py；[M4] run_all_cases 测试改用 mock run_single_case；新增 3 个测试覆盖修复项。全套 196 测试通过，零回归。
