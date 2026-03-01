# Product Requirements Document - 测试仿真器 (Test Simulator)

**Author:** LJW  
**Date:** 2026-02-28  
**Status:** Draft  
**Last Edited:** 2026-03-01  
**Related PRD:** [prd.md](./prd.md) - AI Agent 主项目

---

## Executive Summary

测试仿真器是 AI Agent 租房项目的**本地全自治评测与对抗模拟工具**，在零外部依赖的条件下，完整复现判题流程：模拟用户对话、代理模型请求、以内置仿真数据响应所有租房 API 工具调用，并通过配置文件驱动测试用例执行与通过判定。

**核心价值：** 开发者可在本地完成「用户输入 → Agent 推理 → 模型调用 → 工具调用 → 结果判定」的全链路闭环测试，**无需连接任何外部 API**（租房服务、竞赛平台），支持快速迭代与回归验证。

**仿真边界：** 测试仿真器完整替代竞赛平台的三个角色——上游（用户/判题方）、模型代理层、以及租房工具服务后端——所有角色均在本地进程内运行。

**与主项目关系：** 测试仿真器作为 Agent 的**上游（用户/判题方）**和**下游（模型代理、工具后端）**，与 Agent 形成完整的本地对抗仿真环境，无需 Agent 代码修改即可接入。

---

## Project Classification

| 维度 | 值 |
|------|-----|
| **Project Type** | 测试工具 / 仿真服务 |
| **Domain** | AI Agent 本地评测 |
| **Complexity** | Medium |
| **Project Context** | Brownfield - 依赖现有 Agent 接口与租房仿真 API 规范 |
| **PRD 目的** | 架构对齐 - 明确测试仿真器与 Agent、模型、租房 API 的协作边界 |

---

## Success Criteria

### User Success（开发者 LJW）

- 通过配置文件定义测试用例，一键执行全部或指定用例，获得通过/失败结果
- 本地模拟多轮对话，验证 Agent 在 Chat / Single / Multi 类场景下的表现
- 无需部署竞赛平台，即可复现判题逻辑（时间片、格式校验、答案匹配）
- 工具调用请求由仿真器在本地以内置仿真数据响应，无需连接任何外部租房 API

### Technical Success

- 测试仿真器与 Agent 的 Chat 接口、模型代理接口、工具/租房 API 接口均按现有规范对接
- 配置驱动的测试用例可表达：输入序列、期望输出约束、通过判定规则
- 多轮交互结束后，能根据最终 `response` 及中间状态判断用例是否通过

### Measurable Outcomes

| 指标 | 目标 |
|------|------|
| 用例配置加载成功率 | 100% |
| Chat 接口连通性 | 与 Agent 正常收发消息 |
| 模型转发正确性 | 请求/响应格式与 OpenAI API 兼容 |
| 工具仿真覆盖 | 实现全部 15 个租房 API 端点的本地仿真响应，含有状态操作 |
| 本地自治运行 | 仿真器在无外网条件下可完整执行全部测试用例，0 次外部 API 调用 |
| 判定逻辑可配置 | 支持 JSON 解析、`houses` 匹配、关键词检查等多种规则 |

---

## Core Capabilities（四大能力）

### Capability 1：通过 Chat 接口与 Agent 交互，本地模拟对抗

**描述：** 测试仿真器作为「用户/判题方」，按测试用例配置向 Agent 的 `POST /api/v1/chat` 接口发送多轮消息，模拟真实用户的对话行为，形成本地对抗仿真。

**接口规范（参考 docs/interface.md）：**

| 项目 | 说明 |
|------|------|
| 端点 | `POST {agent_base_url}/api/v1/chat` |
| 请求体 | `{"model_ip": string, "session_id": string, "message": string}` |
| 响应体 | `{"session_id", "response", "status", "tool_results", "timestamp", "duration_ms"}` |

**能力要求：**

- 支持按用例配置逐轮发送 `message`，每轮等待 Agent 返回后再发送下一轮
- `session_id` 可配置为固定或按用例生成，以隔离不同用例的会话状态
- `model_ip` 指向测试仿真器自身或代理服务的地址，使 Agent 的模型请求能被仿真器接收
- 支持在用例开始时发送 `test_run_start` 或初始化类消息（如 `"你好"`），以触发 Agent 的 Session 初始化与数据重置

**参考：** docs/interface_simulate.md 中的接口调用示例，首行用户输入 `"你好"` 后收到 `test_run_start` 类元数据。

---

### Capability 2：接收 Agent 的模型请求，转发至外部大模型代理

**描述：** Agent 在推理时会向 `http://{model_ip}:8888/v1` 发起 Chat Completions 请求。测试仿真器需监听该端口（或作为代理），接收请求并转发至外部大模型服务，再将其响应返回给 Agent。

**接口规范（参考 docs/interface.md）：**

| 项目 | 说明 |
|------|------|
| 端点 | `POST http://{model_ip}:8888/v1/chat/completions` |
| 请求头 | `Session-ID`（评测会话 ID） |
| 请求体 | OpenAI 兼容的 Chat Completion 格式（`model`, `messages`, `tools`, `stream`） |
| 响应体 | OpenAI 兼容的 Chat Completion 响应 |

**能力要求：**

- 测试仿真器提供 HTTP 服务，监听可配置端口（默认 8888），Agent 的 `model_ip` 指向本机该端口
- 将收到的请求原样转发至配置的外部大模型代理 URL（如 `https://api.openai.com/v1/chat/completions` 或内网模型服务）
- 支持请求/响应的透传，确保 `tools`、`tool_calls`、`messages` 等字段完整传递
- 可选：支持请求/响应的录制与回放，便于离线调试

---

### Capability 3：在本地完整仿真租房 API 工具服务，零外部依赖

**描述：** Agent 的工具（如 `search_houses`、`execute_action`）会调用租房仿真 API。测试仿真器以**内置仿真数据驱动的有状态 HTTP 服务**完整替代真实租房后端，接收全部 15 个端点的请求，基于内存中的仿真数据集动态计算响应，支持筛选、分页、排序及租房/退租/下架等状态变更操作。

**接口规范（参考 docs/interface_simulate.md）：**

- 仿真服务监听地址：可配置端口（默认本机 8080），Agent 通过 `RENTAL_API_BASE=http://localhost:8080` 接入
- 地标接口（无需 `X-User-ID`）：`/api/landmarks`、`/api/landmarks/name/{name}`、`/api/landmarks/search`、`/api/landmarks/{id}`、`/api/landmarks/stats`
- 房源接口（需 `X-User-ID`）：`/api/houses/{id}`、`/api/houses/listings/{id}`、`/api/houses/by_community`、`/api/houses/by_platform`、`/api/houses/nearby`、`/api/houses/nearby_landmarks`、`/api/houses/stats`、`/api/houses/init`
- 租赁操作（需 `X-User-ID`，需 `listing_platform` query 参数）：`/api/houses/{id}/rent`、`/api/houses/{id}/terminate`、`/api/houses/{id}/offline`

**能力要求：**

- 仿真服务基于**内置 fixture 数据集**（房源与地标）动态响应请求，无需外部数据库或网络连接
- **有状态仿真**：`/api/houses/init`、`/rent`、`/terminate`、`/offline` 操作均修改内存中的用户视角状态，状态按 `X-User-ID` 隔离，调用 `init` 可重置该用户的房源状态至初始值
- **动态筛选**：`by_platform` 接口支持全部查询参数（`district`、`area`、`min_price`、`max_price`、`bedrooms`、`rental_type`、`decoration`、`orientation`、`elevator`、`min_area`、`max_area`、`subway_line`、`max_subway_dist`、`subway_station`、`commute_to_xierqi_max`、`available_from_before`）；结果支持 `sort_by`（price/area/subway）与分页（`page`、`page_size`）
- **平台差异仿真**：同一房源在链家/安居客/58同城三个平台的价格独立（比例约 92%/100%/78%），`listing_platform` 未传时默认返回安居客数据
- **地标邻近计算**：`/nearby` 与 `/nearby_landmarks` 接口基于 Haversine 公式计算实际直线距离，返回 `distance_to_landmark`、`walking_distance`、`walking_duration` 字段
- 缺少 `X-User-ID` 时，房源接口返回 400；缺少 `listing_platform` 时，租赁操作返回 400；未找到房源时返回 404——行为与真实 API 一致
- Agent 通过环境变量 `RENTAL_API_BASE` 接入，无需修改 Agent 代码

---

### Capability 4：通过配置文件配置测试用例，并根据多轮交互结果判断通过

**描述：** 测试用例以配置文件（如 YAML/JSON）定义，包含输入序列、环境配置、通过判定规则。测试仿真器执行完多轮交互后，根据最终 `response` 及可选中间状态，判定用例通过或失败。

**配置文件结构（建议）：**

```yaml
# 示例：test_cases.yaml
test_cases:
  - id: chat_hello
    type: Chat
    messages:
      - "你好"
    expect:
      has_response: true
      response_not_empty: true

  - id: single_haidian_2br
    type: Single
    messages:
      - "帮我找海淀区两居室，月租8000以内"
    expect:
      response_json_valid: true
      houses_match: ["HF_42", "HF_107"]  # 完全匹配或子集匹配可配置
      house_count_min: 1

  - id: multi_progressive
    type: Multi
    messages:
      - "我想在朝阳区找房"
      - "预算6000以内"
      - "近地铁的"
      - "给我看看具体有哪些"
    expect:
      response_json_valid: true
      houses_match_subset: true  # 答案在返回的 houses 中
      round_count: 4
```

**能力要求：**

- 支持从配置文件加载测试用例，支持单用例、用例集、标签筛选执行
- 支持多种判定规则：`response` 非空、JSON 合法、`houses` 字段存在、`houses` 与期望 ID 匹配（精确/子集/包含）
- 支持按用例类型（Chat/Single/Multi）应用不同判定策略
- 输出清晰的测试报告：每个用例的通过/失败、失败原因、耗时、Token 消耗（若可统计）
- 可选：支持时间片预算、超时控制，与竞赛规则对齐

---

## User Journeys

### Journey 1：开发者执行单个测试用例

**用户：** LJW，正在开发 Agent 的房源查询逻辑。

**步骤：**

1. 编辑 `test_cases.yaml`，添加用例 `single_haidian_2br`，定义输入与期望 `houses`
2. 启动测试仿真器（Chat 驱动 + 模型代理 + Mock 租房 API）
3. 执行 `python test_runner.py --case single_haidian_2br`
4. 仿真器按配置发送消息 → Agent 调用工具 → 工具请求命中 Mock → Agent 返回 `response`
5. 仿真器解析 `response`，检查 `houses` 与期望匹配 → 输出 `PASS` 或 `FAIL` 及原因

**揭示需求：** 配置驱动、Mock 租房 API、JSON 解析与 houses 匹配判定。

---

### Journey 2：开发者执行完整回归测试

**用户：** LJW，完成一轮代码修改，需验证未引入回归。

**步骤：**

1. 执行 `python test_runner.py --all`
2. 仿真器按顺序执行全部配置用例，每个用例使用独立 `session_id`
3. 汇总输出：`3 passed, 1 failed`，失败用例详情写入报告文件
4. LJW 根据报告定位问题，修复后再次运行

**揭示需求：** 批量执行、Session 隔离、报告输出。

---

### Journey 3：多轮对话 + 模型转发验证

**用户：** LJW，验证 Agent 在多轮对话下能否正确保持上下文并调用模型。

**步骤：**

1. 配置 Multi 类用例，5 轮消息
2. 仿真器启动模型代理，将 Agent 的模型请求转发至真实 qwen3-32b 或本地模型
3. 执行用例，观察每轮 Agent 的 `response` 与工具调用
4. 最后一轮判定 `houses` 是否符合期望

**揭示需求：** 模型转发、多轮消息顺序、最终结果判定。

---

### Journey 4：Mock 模式下的快速迭代（无外网）

**用户：** LJW，在无外网或模型不可用时，希望快速验证 Agent 逻辑。

**步骤：**

1. 配置 Mock 模式：租房 API 返回预定义 JSON，模型代理返回预录制响应（若支持）
2. 执行用例，Agent 的工具调用全部命中 Mock，模型可能使用录制响应
3. 验证 Agent 的决策路径（调用了哪些工具、参数是否正确），无需真实模型与租房 API

**揭示需求：** Mock 租房 API、可选的模型响应 Mock。

---

## Functional Requirements

### Chat 驱动（Capability 1）

- **FR1**：测试仿真器可通过 HTTP 客户端向 Agent 的 `POST /api/v1/chat` 发送请求，携带 `model_ip`、`session_id`、`message`
- **FR2**：支持按用例配置的顺序逐轮发送消息，每轮等待 Agent 响应后再发送下一轮
- **FR3**：支持为每个用例生成独立的 `session_id`，或使用配置的固定值
- **FR4**：支持配置 Agent 的 Base URL（默认 `http://localhost:8191`）
- **FR5**：支持配置 `model_ip`，使 Agent 的模型请求指向测试仿真器的模型代理服务

### 模型代理（Capability 2）

- **FR6**：测试仿真器可启动 HTTP 服务，监听可配置端口（如 8888），接收 `POST /v1/chat/completions` 请求
- **FR7**：可将收到的请求转发至配置的外部大模型代理 URL，并返回其响应
- **FR8**：支持透传 `Session-ID` 请求头及完整请求体/响应体
- **FR9**：外部代理 URL 可配置（如环境变量 `LLM_PROXY_URL`）

### 租房 API 仿真服务（Capability 3）

- **FR10**：仿真服务实现全部 15 个端点（5 个地标接口 + 10 个房源接口），响应格式与真实 API 完全兼容（`{"code": 0, "message": "success", "data": {...}}`）
- **FR11**：`/api/houses/by_platform` 支持全部查询参数的动态筛选：`district`、`area`、`min_price`、`max_price`、`bedrooms`（逗号分隔）、`rental_type`、`decoration`、`orientation`、`elevator`、`min_area`、`max_area`、`subway_line`、`max_subway_dist`、`subway_station`、`commute_to_xierqi_max`、`available_from_before`；支持 `sort_by`（price/area/subway）、`sort_order`（asc/desc）与 `page`/`page_size` 分页
- **FR12**：`/api/houses/nearby` 基于地标与房源坐标计算直线距离，筛选 `max_distance` 范围内的可租房源，返回 `distance_to_landmark`（米）、`walking_distance`（估算步行距离）、`walking_duration`（估算步行时间，分钟）
- **FR13**：租赁操作（`/rent`、`/terminate`、`/offline`）更新该 `X-User-ID` 的房源状态，三个平台状态同步变更；`/api/houses/init` 将该用户的全部房源状态重置至初始 fixture 值；用户状态按 `X-User-ID` 独立隔离，互不影响
- **FR14**：仿真服务内置 fixture 数据集：地标数据不少于 20 条（覆盖 subway/company/landmark 三类，涵盖海淀、朝阳、西城、东城、丰台至少 5 个行政区）；房源数据不少于 30 条（覆盖至少 6 个行政区，含 1/2/3 居室，整租与合租均有，价格跨度 1500–15000 元/月，初始状态约 90% available / 5% rented / 5% offline）
- **FR15**：房源接口缺少 `X-User-ID` 时返回 `400`；租赁操作缺少 `listing_platform` 时返回 `400`；按 ID 查询不存在的房源时返回 `404`；行为与真实 API 规范一致
- **FR16**：同一房源在三个平台独立返回不同价格（比例约安居客 100% / 链家 92% / 58同城 78%），`listing_platform` 未传时默认返回安居客数据

### 测试用例与判定（Capability 4）

- **FR17**：支持从 YAML 或 JSON 配置文件加载测试用例
- **FR18**：每个用例需包含：`id`、`type`（Chat/Single/Multi）、`messages`（输入列表）
- **FR19**：每个用例可配置 `expect` 规则：`has_response`、`response_not_empty`、`response_json_valid`、`houses_match`、`house_count_min` 等
- **FR20**：支持 `houses_match` 的多种模式：精确匹配、子集匹配、包含匹配
- **FR21**：执行结束后输出每个用例的通过/失败状态及失败原因
- **FR22**：支持 `--case <id>` 执行单个用例，`--all` 执行全部用例，`--tag <tag>` 按标签筛选
- **FR23**：可选：支持时间片计算与预算控制，与竞赛规则对齐

---

## Non-Functional Requirements

### Performance

- **NFR1**：单用例执行超时可配置（默认 60 秒），超时则判定该用例失败
- **NFR2**：模型代理额外转发延迟 < 100ms（P95），不成为整体测试瓶颈

### Integration

- **NFR3**：与 Agent 的接口兼容 docs/interface.md 定义的 Chat 格式（`POST /api/v1/chat`，`model_ip`、`session_id`、`message` 字段）
- **NFR4**：仿真服务响应格式与 docs/interface_simulate.md 定义的 15 个端点规范完全兼容（包括字段名、数据类型、错误码），Agent 切换到真实 API 时无需修改任何代码
- **NFR5**：模型代理与 OpenAI Chat Completions API 格式兼容（`model`、`messages`、`tools`、`tool_calls`、`stream` 字段完整透传）
- **NFR6**：仿真服务在无网络环境下可启动并完整响应所有 15 个端点，不依赖任何外部服务、数据库或文件系统写入

### Usability

- **NFR7**：配置文件具备清晰的注释和示例，新用例可在 5 分钟内添加
- **NFR8**：测试报告输出为人类可读格式（控制台 + 可选 JSON/HTML 报告文件）
- **NFR9**：错误信息应明确指示失败环节（Chat 不通、模型转发失败、Mock 未匹配、判定不通过）

### Reliability

- **NFR10**：Mock 服务在未匹配到规则时，应返回明确错误或默认空响应，避免 5xx 导致 Agent 异常
- **NFR11**：测试仿真器异常退出时，应输出已有测试结果，不静默丢失

---

## API Backend Specific Requirements

### 测试仿真器服务架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Test Simulator（本地全自治）                       │
├─────────────────┬──────────────────┬────────────────────────────────────┤
│  Test Runner    │   Model Proxy    │   Rental API Simulator              │
│  (Chat Driver)  │   :8888          │   :8080 (configurable)             │
│  - Load config  │   - Forward to   │   - /api/landmarks/* (stateless)   │
│  - POST /chat   │     LLM          │   - /api/houses/* (stateful)       │
│  - Assert       │                  │   - In-memory fixture dataset      │
│                 │                  │   - Per-user state isolation       │
│                 │                  │   - Dynamic filter + geo-distance  │
└────────┬────────┴────────┬─────────┴──────────────┬──────────────────────┘
         │                 │                         │
         ▼                 │                         │
┌─────────────────────────┐│                        │
│  Agent (localhost:8191) ││                        │
│  POST /api/v1/chat      ││                        │
│  model_ip -> :8888      │◄───────────────────────-┘
│  RENTAL_API_BASE ->     │
│    http://localhost:8080 │
└─────────────────────────┘
        ↑ 无外部 API 依赖，全链路本地运行
```

### 配置项建议

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `agent_base_url` | string | `http://localhost:8191` | Agent 的 Chat 接口地址 |
| `model_proxy_port` | int | 8888 | 模型代理监听端口 |
| `llm_proxy_url` | string | (必填) | 外部大模型代理 URL |
| `sim_rental_port` | int | 8080 | 仿真租房服务监听端口 |
| `sim_fixture_file` | string | `fixtures/rental_data.yaml` | 仿真数据集文件路径（地标 + 房源） |
| `test_user_id` | string | (必填) | X-User-ID 默认值，用于自动注入测试请求头 |
| `test_cases_file` | string | `test_cases.yaml` | 测试用例配置文件路径 |
| `timeout_per_case` | int | 60 | 单用例超时（秒） |

### 判定规则参考

| 规则 Key | 类型 | 说明 |
|----------|------|------|
| `has_response` | bool | 响应对象存在 |
| `response_not_empty` | bool | `response` 字段非空 |
| `response_json_valid` | bool | `json.loads(response)` 成功 |
| `houses_match` | list[str] | `houses` 与给定 ID 列表精确匹配 |
| `houses_match_subset` | bool | 期望答案的 ID 均在 `houses` 中 |
| `house_count_min` | int | `len(houses) >= N` |
| `status_success` | bool | `status == "success"` |

---

## Project Scoping & Phased Development

### MVP（Phase 1）

**目标：** 实现四大能力的最小可用版本，支持单用例与多用例执行。

**Must-Have：**

- Chat 驱动：向 Agent 发送多轮消息，接收响应
- 模型代理：监听 8888，转发至外部 LLM
- Mock 租房 API：实现 15 个端点的 Mock，至少支持 3–5 个核心场景的预定义响应
- 配置文件：YAML 格式，支持 `messages`、`expect`（含 `response_json_valid`、`houses_match`）
- 命令行：`--case`、`--all`，输出 PASS/FAIL

**Out of Scope（MVP）：**

- 模型响应录制与回放
- 时间片计算与预算控制
- HTML 报告生成

### Post-MVP（Phase 2）

- 更丰富的判定规则：关键词检查、正则匹配
- 用例标签与筛选（`--tag`）
- JSON/HTML 测试报告
- **接口联调辅助模式**（调试专用，不用于测试用例执行）：将仿真服务切换为透传至真实租房 API，供开发者在接口联调阶段验证 Agent 与真实数据的兼容性；该模式不参与通过判定，不视为测试执行

### Expansion（Phase 3）

- 时间片与竞赛规则对齐
- 模型响应 Mock（离线测试）
- 对抗性测试：模糊输入、异常响应注入

---

## Domain-Specific Requirements

### 与竞赛环境对齐

- 测试用例设计应参考 docs/task.md 中的用例类型（Chat / Single / Multi）及评分规则
- Mock 数据应尽量贴近 docs/interface_simulate.md 中示例响应的结构
- 判定逻辑应与判题系统的预期一致（如 `response` 为 JSON 时的 `houses` 匹配方式）

### 与现有 Agent 兼容

- Agent 的 `model_ip` 需指向测试仿真器的模型代理地址（如 `127.0.0.1` 或 `localhost`）
- Agent 的 `RENTAL_API_BASE` 环境变量需指向测试仿真器的 Mock 租房 API 地址
- 无需修改 Agent 代码即可接入测试仿真器

---

## Appendix：参考资料

| 文档 | 路径 | 用途 |
|------|------|------|
| Agent 接口规范 | docs/interface.md | Chat 接口、模型转发接口格式 |
| 租房仿真 API | docs/interface_simulate.md | 15 个端点、请求/响应结构、示例 |
| 挑战赛任务说明 | docs/task.md | 用例类型、评分规则、时间片公式 |

---

*本文档为测试仿真器的产品需求规格，与主 Agent PRD (prd.md) 互补，共同构成 AI Agent Coding 项目的完整需求体系。*
