# E2E 测试进度报告

**日期**: 2026-03-02  
**模型**: Qwen3-32B  
**测试范围**: 全量 35 个用例（chat_hello / single_haidian_2br / multi_progressive + ev01–ev32）  
**执行命令**: `.\tests\run_e2e.ps1 -UserId "37274" -SimAll -ReadyTimeoutSec 60`  
**说明**: 测试因耗时过长（单用例最长 309s）被中途手动终止，已完成 18/35 个用例

---

## 测试结果汇总（已完成部分）

| # | 用例 ID | 类型 | 结果 | 耗时 | 失败原因 |
|---|---------|------|------|------|----------|
| 1 | chat_hello | Chat | ✅ PASS | 14.9s | — |
| 2 | single_haidian_2br | Single | ✅ PASS | 135.3s | — |
| 3 | multi_progressive | Multi | ✅ PASS | 60.3s | — |
| 4 | ev06_wangjing_to_daxing_rental_flow | Multi | ❌ FAIL | 153.7s | `[Round 1] tool_call_args: 工具 'update_preferences' 未被调用（实际调用：[]）` |
| 5 | ev01 | Chat | ✅ PASS | 16.0s | — |
| 6 | ev02 | Chat | ✅ PASS | 10.4s | — |
| 7 | ev03 | Single | ✅ PASS | 66.6s | — |
| 8 | ev04 | Single | ✅ PASS | 48.4s | — |
| 9 | ev05 | Single | ✅ PASS | 89.5s | — |
| 10 | ev07 | Multi | ❌ FAIL | 75.2s | `[Round 1] no_tool_call: 期望无工具调用，实际调用了 ['update_preferences']` |
| 11 | ev08 | Single | ✅ PASS | 52.6s | — |
| 12 | ev09 | Single | ❌ FAIL | 26.4s | `tool_call_args: 工具 'update_preferences' 未被调用（实际调用：[]）` |
| 13 | ev10 | Single | ❌ FAIL | 28.3s | `tool_call_args: 工具 'update_preferences' 未被调用（实际调用：[]）` |
| 14 | ev11 | Single | ✅ PASS | 42.1s | — |
| 15 | ev12 | Multi | ✅ PASS | 106.8s | — |
| 16 | ev13 | Multi | ✅ PASS | 309.3s | — |
| 17 | ev14 | Single | ❌ FAIL | 34.7s | `tool_call_args: 工具 'update_preferences' 未被调用（实际调用：[]）` |
| 18 | ev15 | Single | ❌ FAIL | 158.8s | `status_success: expected 'success', got 'error'` |
| 19–35 | ev16–ev32 | — | ⏸ 未执行 | — | 测试被中断 |

**已完成**: 18 / 35  
**PASS**: 11 &nbsp;**FAIL**: 7 &nbsp;**未执行**: 17

---

## 失败用例分类分析

### 类型 A：LLM 未调工具（应调未调）
> 对于简短/模糊表达，LLM 有时直接生成文字回复，未触发 `update_preferences`

| 用例 | 用户消息 |
|------|---------|
| ev06 | `"我想在望京租一套两居室，预算8000以内，有电梯"` |
| ev09 | `"我想找4000元以内的房子，有哪些"` |
| ev10 | `"帮我找两居室的房子"` |
| ev14 | `"我想找合租的房子，海淀区，预算3000以内"` |

### 类型 B：LLM 误调工具（不该调却调了）
> 对于纯情绪/上下文闲聊，LLM 提前提取了偏好，触发了 `update_preferences`

| 用例 | 用户消息（Round 1）| 期望 |
|------|-------------------|------|
| ev07 | `"唉，我现在的房子住得不太舒服，采光不好，房间也小"` | `no_tool_call` |

### 类型 C：服务错误
| 用例 | 失败原因 |
|------|---------|
| ev15 | `status_success: expected 'success', got 'error'`（需查 agent 日志定位根因）|

---

## 当前测试框架状态

本次 Story 已完成：
- ✅ `agent.py`：`tool_results_log` 新增 `args` 字段，记录 LLM 实际传参
- ✅ `main.py`：`ToolResult` 模型新增 `args: dict | None`
- ✅ `test-simulator/config.py`：新增 `ToolCallArgsExpect`、`RoundExpect` 模型；`ExpectRules` 新增 `tool_call_args`、`no_tool_call` 字段；`TestCase` 新增 `round_expects`
- ✅ `test-simulator/runner.py`：实现 `_tool_call_args`、`_no_tool_call` 断言；支持 per-round 校验
- ✅ `test-simulator/run_ev_tests.py`：新建独立运行脚本，不重复启动服务
- ✅ `tests/run_e2e.ps1`：新增 `-SimCase`、`-SimTag`、`-SimAll` 参数支持
- ✅ `test-simulator/test_cases.yaml`：ev01–ev32 全量配置工具提参校验，Multi 用例简化为首轮校验

## 待后续 Story 跟进

- [ ] **类型 A**：排查 LLM 对简短请求的 tool-calling 决策，可能需优化系统提示词或 tool description
- [ ] **类型 B（ev07）**：确认纯情绪发言是否应当调工具，视 agent 业务设计决定是否修改期望值
- [ ] **类型 C（ev15）**：分析 `logs/agent.log`，定位 `"帮我找13号线沿线的两居室房子"` 返回 error 的根因
- [ ] **ev16–ev32**：完成剩余 17 个用例的验证
