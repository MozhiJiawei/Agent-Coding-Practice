---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
classification:
  projectType: api_backend
  domain: AI Agent / Competition
  complexity: medium-high
  projectContext: greenfield-code / brownfield-docs
  prdPurpose: architecture-alignment
inputDocuments:
  - docs/task.md
  - docs/interface.md
  - docs/interface_simulate.md
  - docs/index.md
  - _bmad-output/project-context.md
  - _bmad-output/brainstorming/brainstorming-session-2026-02-26.md
documentCounts:
  briefCount: 0
  researchCount: 0
  brainstormingCount: 1
  projectDocsCount: 4
workflowType: 'prd'
---

# Product Requirements Document - AI Agent Coding

**Author:** LJW
**Date:** 2026-02-27

## Executive Summary

本项目为「智找安居·马年省心办」租房 AI Agent 挑战赛的参赛作品。目标是构建一个运行在 `localhost:8191` 的智能租房 Agent 服务，通过 `POST /api/v1/chat` 接口接收自然语言对话，调用 qwen3-32b 大模型（OpenAI 兼容接口）和 15 个租房仿真 API，最终返回满足用户需求的候选房源（最多 5 套）及推荐说明。

**核心用户价值：** 用户输入模糊或精确的租房需求（单轮或多轮），Agent 自动完成需求理解、房源筛选、多维分析，输出高匹配度候选房源列表，无需用户手动翻阅 API 文档或逐条筛选。

**竞赛评分目标：** 在 300 时间片预算内，覆盖尽可能多的用例类型（Chat 5分/个、Single 10-15分/个、Multi 20-30分/个），Token 消耗越少排名越高。

### What Makes This Special

**核心设计哲学：把不确定性从 AI 层转移到代码层。** 大多数参赛者的失分点集中在三处：① 模型自由生成 JSON 导致格式错误（直接 0 分）；② 不分页导致漏查房源；③ 多轮上下文丢失导致意图断层。本方案通过三个确定性机制消灭这三类失分：

1. **输出格式守卫（Format Guard）** — 代码强制组装 `response` JSON，模型只输出 `message` 文本和 `house_id` 列表，彻底消除格式失分风险
2. **工具内置自适应翻页** — CLI 工具层自动并发拉取分页，模型无需感知翻页逻辑
3. **意图粒度对齐用户意图** — 工具粒度从 15 个 API 端点收敛到 6-8 个用户意图工具，降低模型决策复杂度

**MVP 策略：** 先交付一个"稳定不失分"的防守型原型，覆盖 Chat + Single 全类型用例和基础多轮对话；在打榜失分数据反馈后，再针对性补充状态机、偏好捕获等进攻型能力。

## Project Classification

| 维度 | 值 |
|---|---|
| **Project Type** | API Backend（FastAPI + LLM Tool Calling） |
| **Domain** | AI Agent / 竞赛工程 |
| **Complexity** | Medium-High（竞赛约束严苛，无行业监管） |
| **Project Context** | Greenfield（代码）+ Brownfield（需求/接口/架构文档完备） |
| **PRD 目的** | 架构对齐 — 将头脑风暴洞察转化为可驱动实现的规范 |

## Success Criteria

### User Success

- 用户以自然语言（口语/书面均可）输入租房需求，Agent 能在一轮内返回至少 1 个正确匹配的房源 ID
- 用户在多轮对话中追加条件（如"再筛选近地铁的"），Agent 能在不丢失前轮意图的情况下返回精化结果
- 用户发起聊天类消息（非房源查询），Agent 返回流畅自然语言回复，无 JSON 污染
- 用户要求执行操作（租房/退租/下架），Agent 实际调用对应 API 完成操作，而非仅在文本中标注

### Business Success（竞赛维度）

- **总分目标（MVP）：** 在 300 时间片预算内，Chat 类 100% 得分，Single 类命中率 ≥ 80%，Multi 类命中率 ≥ 50%
- **零格式失分：** 房源查询 `response` 字段 JSON 格式错误率 = 0%
- **时间片效率：** 平均每个用例消耗时间片 ≤ 5 片（控制系统提示 ≤ 800 Token，工具调用轮次 ≤ 5 次/用例）
- **Token 排名：** 同分情况下，Token 消耗低于中位数参赛队

### Technical Success

- `POST /api/v1/chat` 响应成功率 100%，无 HTTP 5xx 错误
- 非模型处理时间（代码执行）< 5 秒/用例，否则判定失败
- Session 隔离：不同 `session_id` 之间会话历史严格独立
- 新 Session 首条消息触发 `POST /api/houses/init` 数据重置，确保每次用例执行使用初始化数据
- Tool Calling Loop 最大迭代次数 ≤ 10，防止无限循环

### Measurable Outcomes

| 指标 | MVP 目标 | 迭代目标 |
|---|---|---|
| Chat 用例得分率 | 100% | 100% |
| Single 用例房源命中率 | ≥ 80% | ≥ 95% |
| Multi 用例房源命中率 | ≥ 50% | ≥ 80% |
| JSON 格式错误率 | 0% | 0% |
| 平均时间片/用例 | ≤ 5 片 | ≤ 3 片 |
| 非模型处理时间 | < 5s | < 2s |

## User Journeys

### Journey 1：单轮精准查房（主路径·成功）

**用户：** 判题系统模拟的职场人小王，刚返工，需要快速确定一套房。

**Opening Scene：** 小王知道自己要住海淀，预算 8000 以内，两居室。他打开 Agent，一句话说清楚需求。

> "帮我找海淀区两居室，月租 8000 以内"

**Rising Action：** Agent 接收请求，识别出区域=海淀、户型=两居室、价格≤8000 三个条件，调用 `search_houses` 工具（内置自动翻页），一次性拿到全量符合条件的房源，筛选前 5 套最匹配的。

**Climax：** Agent 返回合法 JSON：
```json
{"message": "为您找到海淀区3套两居室房源，月租均在8000以内...", "houses": ["HF_42", "HF_107", "HF_203"]}
```

**Resolution：** 判题系统解析 `response` 字段，验证 `houses` 中的 ID 与答案匹配，得分。小王"一句话找到房"的核心价值实现。

**揭示的需求：** 多条件房源查询、自动翻页、合法 JSON 输出格式守卫。

---

### Journey 2：多轮渐进筛选（主路径·复杂）

**用户：** 判题系统模拟的应届生小李，需求模糊，边问边想。

**Opening Scene：**
> 轮1："我想在朝阳区找房，靠近国贸"
> 轮2："预算 6000 以内"
> 轮3："最好是近地铁的"
> 轮4："给我看看具体有哪些"

**Rising Action：** 每轮对话完整历史传给模型，模型自行积累上下文。第 4 轮时模型已从历史中理解：区域=朝阳、地标=国贸附近、价格≤6000、近地铁。调用 `search_landmark` 获取国贸地标 ID，再调用 `search_nearby_landmark` 拿附近房源，结合价格和地铁距离过滤。

**Climax：** 第 4 轮返回精化结果列表，JSON 格式正确，house IDs 准确。

**Resolution：** 5 轮对话历史完整保留，无意图断层，Multi 用例得分。

**揭示的需求：** Session 消息历史完整持久化、地标搜索工具、地标附近房源工具、多工具组合调用。

---

### Journey 3：吐槽→找房→租房（边缘场景·完整闭环）

**用户：** 判题系统模拟的上班族小陈，当前住所不满意，自然语言吐槽切入。

**Opening Scene：**
> 轮1："唉，我现在住的地方太吵了，而且离公司太远"
> 轮2："想换一个安静点、通勤短点的"
> 轮3："西二旗附近有什么房吗，两居室"
> 轮4："第二个怎么样，周边有没有超市"
> 轮5："就租这个吧，HF_88"

**Rising Action：**
- 轮1-2：纯聊天类，Agent 返回自然语言，无 JSON（格式守卫正确区分）
- 轮3：触发房源查询，调用地标搜索找西二旗，再查附近两居室
- 轮4：调用 `get_nearby_amenities` 查 HF_88 小区周边商超，返回自然语言说明
- 轮5：识别租房意图，调用 `execute_action` 实际执行 `POST /api/houses/HF_88/rent`

**Climax：** 最后一轮 API 调用成功，状态变更为已租，返回确认信息。

**Resolution：** 全程无格式错误，聊天轮不返回 JSON，操作轮实际调用 API，Multi 高分用例完整覆盖。

**揭示的需求：** 聊天/查询/操作意图精准区分、周边配套查询工具、租赁操作工具、操作结果确认响应。

---

### Journey 4：判题系统（API 消费者）

**用户：** 自动化判题系统，按用例脚本顺序调用 Agent。

**关键路径：**
1. 发送首条消息 → Agent 触发 `init` 重置数据 → 正常响应
2. 解析 `response` 字段：若是房源查询，`json.loads(response)` 必须成功
3. 检查 `houses` 字段中的 ID 与答案对比，计算命中数
4. 统计本用例消耗时间片，累加至总预算

**失败场景：** `response` 包含自然语言前缀导致 JSON 解析失败 → 该用例 0 分。

**揭示的需求：** 严格的输出格式守卫（代码组装而非模型生成）、Session 首次消息数据重置钩子、响应时间保证。

---

### Journey 5：开发者本地调试（LJW）

**用户：** LJW，构建并验证 Agent。

**关键路径：**
1. `uvicorn main:app --host 0.0.0.0 --port 8191` 5 秒内就绪
2. 发送聊天类消息，确认 `response` 是自然语言字符串
3. 发送房源查询，确认 `response` 是合法 JSON 字符串，`json.loads()` 不报错
4. 发送两个不同 `session_id`，确认历史不互串
5. 打榜失分后，通过日志定位哪个工具调用出了问题

**揭示的需求：** 结构化日志（session start / tool call / model response）、快速启动、requirements.txt 依赖完整。

---

### Journey Requirements Summary

| 旅程 | 揭示的核心能力 |
|---|---|
| 单轮精准查房 | 多条件查询、自动翻页、JSON 格式守卫 |
| 多轮渐进筛选 | Session 历史持久化、地标搜索、多工具组合 |
| 吐槽→找房→租房 | 意图分类（聊天/查询/操作）、周边配套、租赁操作 |
| 判题系统 | 格式守卫、数据重置钩子、响应时间保证 |
| 开发者调试 | 日志、快速启动、依赖完整性 |

## Domain-Specific Requirements

### Competition Compliance（竞赛合规红线）

以下为竞赛强制约束，违反任意一条将导致成绩取消或用例即死：

- **禁止硬编码答案：** 不得将已知用例答案预埋进 prompt 或代码逻辑；代码审核阶段会检测，一经发现取消参赛资格
- **禁止外部模型：** 所有模型调用必须通过 `model_ip:8888` 提供的 qwen3-32b 接口，严禁调用 OpenAI / Claude / 其他外部 API
- **X-User-ID 必须为真实工号：** 所有 `/api/houses/*` 请求头必须携带平台注册工号；传错工号会导致数据隔离失败，影响全局评测成绩
- **3 月 3 日需求变更：** 赛题组将在 3/3 更新用例集并做一次需求变更；工具定义（`TOOLS` 常量）和系统提示必须模块化独立，支持 30 分钟内完成更新重新提交

### Technical Constraints（竞赛技术约束）

- **非模型处理时间 < 5 秒：** 单用例从下发到响应，扣除模型调用时间后，代码执行不得超过 5 秒，超时判定该用例失败
- **时间片预算 300 片：** 全局预算，超出后剩余用例不再执行；时间片公式 `t = 1 + max(0, (n_tokens - 1000) * 0.3)`，系统提示需控制在 800 Token 以内
- **服务端口固定 8191：** `--host 0.0.0.0 --port 8191`，不可更改
- **启动时间 < 5 秒：** 服务必须在容器启动后 5 秒内完全就绪，禁止在启动时做重型初始化

## Innovation & Novel Patterns

### Detected Innovation Areas

**创新 #1：不确定性层转移架构（Uncertainty Layer Transfer）**

绝大多数 AI Agent 实现把"格式正确性"、"分页完整性"、"操作执行"都委托给模型来决策——这是把不确定性留在了 AI 层。本方案系统性地将这三类非确定性问题转移到代码层：
- 格式守卫：代码组装最终 JSON，模型只输出结构化字段
- 自适应翻页：工具层自动完成，模型无需感知
- 操作执行：`execute_action` 工具强制调用 API，杜绝"文字回复代替实际操作"

**影响：** 把"模型遵从性"这个高风险变量，替换为"代码确定性"这个零风险常量。

**创新 #2：意图粒度压缩（Intent-Level API Composition）**

传统做法是将外部 API 1:1 映射为工具（15 个 API → 15 个工具），导致模型面临"工具选择爆炸"问题。本方案按**用户意图**而非 API 端点定义工具粒度，将 15 个原子 API 压缩为 6-8 个意图工具：
- 模型只需理解"我要找房"，不需要知道"先查地标再查附近"的实现细节
- 工具内部封装多 API 组合逻辑（如 `search_nearby_landmark` = 地标搜索 + 附近房源查询）

**影响：** 工具数量减少 50%，模型决策路径变短，Token 消耗降低，调用准确率提升。

**创新 #3：竞赛系统即测试套件（Competition-as-TDD）**

将竞赛评测系统本身作为天然的"意图覆盖率测试仪"——每次打榜等价于一次完整回归测试，失分 Case 直接暴露工具设计盲区。MVP 先上线最小可行工具集，用失分数据驱动迭代，而非预先过度设计。

**影响：** 把传统软件开发中"需要手工构建的测试套件"，转化为竞赛环境中"自动提供的真实用例集"，显著降低开发迭代成本。

### Validation Approach

| 创新点 | 验证方法 | 成功信号 |
|---|---|---|
| 不确定性层转移 | Smoke test：强制让模型尝试输出非标准格式，观察守卫是否拦截 | `json.loads(response)` 100% 成功 |
| 意图粒度压缩 | 打榜后对比工具调用次数 vs 基准实现 | 平均工具调用轮次 ≤ 3 |
| 竞赛即 TDD | 首次打榜失分 Case 分析 | 失分 Case 能被归类到具体工具盲区 |

### Risk Mitigation

- **格式守卫过度拦截风险：** 若守卫逻辑误判，将正常聊天回复包成 JSON → 单元测试聊天路径，确保意图分类准确
- **意图工具粒度过粗风险：** 某些复杂用例需要比意图工具更细粒度的控制 → 工具设计保留可组合性，支持 TDD 后拆分
- **3 月 3 日变更冲击风险：** 工具定义集中在 `TOOLS` 常量，系统提示抽取为独立模板 → 变更范围可控，30 分钟内完成更新

## API Backend Specific Requirements

### Project-Type Overview

本项目为纯 API Backend 类型：对外暴露单一 HTTP 端点，内部驱动 LLM Tool Calling Loop 与外部租房仿真 API 交互。无前端 UI、无视觉设计需求、无用户注册/权限体系。

### Endpoint Specification

**Agent 对外接口（唯一出口）：**

| 方法 | 路径 | 描述 |
|---|---|---|
| `POST` | `/api/v1/chat` | 接收用户消息，返回 Agent 响应 |

**请求体：**
```json
{"model_ip": "string", "session_id": "string", "message": "string"}
```

**响应体：**
```json
{
  "session_id": "string",
  "response": "string（聊天）或 json_string（房源查询）",
  "status": "success | error",
  "tool_results": [...],
  "timestamp": 1704067200,
  "duration_ms": 1500
}
```

**内部调用的租房仿真 API（15 个端点）：**

| 类别 | 端点 | 需要 X-User-ID |
|---|---|---|
| 地标查询 | `GET /api/landmarks`、`/api/landmarks/search`、`/api/landmarks/name/{name}`、`/api/landmarks/{id}`、`/api/landmarks/stats` | 否 |
| 房源查询 | `GET /api/houses/{id}`、`/api/houses/listings/{id}`、`/api/houses/by_community`、`/api/houses/by_platform`、`/api/houses/nearby`、`/api/houses/nearby_landmarks`、`/api/houses/stats` | 是 |
| 租赁操作 | `POST /api/houses/{id}/rent`、`/api/houses/{id}/terminate`、`/api/houses/{id}/offline` | 是 |
| 数据重置 | `POST /api/houses/init` | 是 |

### Authentication Model

- **Agent 接口**：无鉴权（竞赛环境，判题系统直接调用）
- **租房仿真 API**：`X-User-ID` 请求头携带竞赛平台注册工号；地标接口无需此头
- **模型 API**：`api_key` 为任意非空字符串（占位符），`base_url` 为 `http://{model_ip}:8888/v1`

### Data Schemas

**意图工具入参（LLM Function Calling 格式）：**

| 工具名 | 核心参数 |
|---|---|
| `search_houses` | district, min_price, max_price, room_type, decoration, orientation, max_subway_dist, listing_platform, page |
| `search_landmark` | query, category, district |
| `search_nearby_landmark` | landmark_id, max_distance, min_price, max_price, room_type, listing_platform |
| `get_house_detail` | house_id |
| `get_nearby_amenities` | house_id, category, max_distance_m |
| `execute_action` | action（rent/terminate/offline）, house_id, listing_platform |

**Format Guard 输出结构（仅房源查询时）：**
```json
{"message": "自然语言推荐说明", "houses": ["HF_x", "HF_y"]}
```
`houses` 最多 5 个有效 ID；`json.dumps(..., ensure_ascii=False)` 输出。

### Error Codes

| 状态 | status 字段 | response 字段 |
|---|---|---|
| 正常响应 | `"success"` | 自然语言或 JSON 字符串 |
| 外部 API 异常 | `"error"` | 错误描述字符串 |
| 工具调用超限 | `"error"` | `"Tool call limit exceeded"` |

不得抛出 HTTP 4xx/5xx 异常（判题系统无法处理非 200 响应）。

### Rate Limits & Resource Constraints

- **全局时间片预算**：300 片，超出后剩余用例不执行
- **单次模型调用时间片**：`t = ceil(1 + max(0, (n_tokens - 1000) * 0.3))`
- **工具调用循环上限**：每用例 ≤ 10 次
- **系统提示 Token 上限**：≤ 800 Token

### Implementation Considerations

- 单文件优先：`main.py`（路由）+ `tools.py`（工具定义 + API 调用）+ `agent.py`（LLM Loop）
- `TOOLS` 常量定义在模块顶层，不在请求处理函数内动态构建
- `httpx.AsyncClient` 通过 FastAPI lifespan 上下文管理器创建，整个生命周期复用
- `USER_ID` 通过环境变量注入，不在代码中硬编码

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach：** Problem-Solving MVP — 以"稳定不失分"为首要目标，优先覆盖全部用例类型，建立零格式失分基线，再通过打榜失分数据驱动功能迭代。

**Resource Requirements：** 单人开发，预计 MVP 实现时间 1-2 天。

### MVP Feature Set（Phase 1）

**Core User Journeys Supported：**
- Journey 1（单轮精准查房）：完整支持
- Journey 2（多轮渐进筛选）：基础支持（历史不丢，模型自行理解上下文）
- Journey 3（吐槽→找房→租房）：完整支持
- Journey 4（判题系统）：完整支持
- Journey 5（开发者调试）：完整支持

**Must-Have Capabilities：**
- `POST /api/v1/chat` 接口实现（FastAPI + Pydantic）
- Session 管理（内存 dict + 新 Session 自动 init）
- 标准 ReAct Tool Calling Loop（≤ 10 次迭代）
- 输出格式守卫（代码组装 JSON response，模型不直接输出格式）
- 工具内置自适应翻页（首次查询后自动拉取剩余页，上限 5 页）
- 结构化日志（session start / tool call / model response）
- `requirements.txt` 包含所有依赖（fastapi, uvicorn[standard], openai, httpx, pydantic）

**6 个意图工具（MVP 初始工具集）：**
1. `search_houses` — 多条件综合查询（区域/价格/户型/装修/朝向/地铁距离等）
2. `search_landmark` — 地标搜索（地铁站/公司/商圈关键词模糊匹配）
3. `search_nearby_landmark` — 以地标为中心查附近可租房源（需先获取 landmark_id）
4. `get_house_detail` — 获取单套房源完整详情
5. `get_nearby_amenities` — 查询小区周边商超/公园等生活配套
6. `execute_action` — 执行租赁操作（rent/terminate/offline）

### Post-MVP Features（Phase 2 — 打榜后迭代）

- 简化版意图状态机：会话结构化意图对象，多轮只 PATCH 变化项
- 并发工具调用：`asyncio.gather` 并发执行多个独立 tool_calls
- 动态上下文注入：系统提示 ≤ 800 Token，工具说明按需动态注入

### Expansion（Phase 3 — 时间允许）

- 会话结果集游标：解决指代消解（"第二套"、"刚才那个"）
- 被动偏好捕获：每轮提取负面描述转换为正向偏好
- 三阶段显式 Pipeline：理解→搜索→推荐，固定 3-5 次模型调用

### Risk Mitigation Strategy

| 风险类型 | 具体风险 | 应对策略 |
|---|---|---|
| 技术风险 | 格式守卫误判导致聊天回复被 JSON 包装 | MVP 阶段单元测试聊天路径，确保意图分类准确 |
| 技术风险 | 自适应翻页引入并发复杂度 | 先用串行翻页，打榜后再优化为并发 |
| 竞赛风险 | 3/3 需求变更冲击 | 工具定义和系统提示模块化，30 分钟内可完成更新 |
| 资源风险 | 时间不足无法实现全部 P0 功能 | 最小可用子集：接口 + Loop + 格式守卫，翻页可先跳过 |

## Functional Requirements

### 对话管理（Conversation Management）

- FR1：用户可通过 `POST /api/v1/chat` 发送自然语言消息，系统在 200 响应中返回 Agent 回复
- FR2：系统可在同一 `session_id` 下跨轮次完整保留所有对话历史（system + user + assistant + tool results）
- FR3：系统可对不同 `session_id` 的对话历史进行严格隔离，不同 session 间数据不互通
- FR4：系统可在新 `session_id` 首条消息时自动调用 `POST /api/houses/init` 重置房源数据
- FR5：系统可区分聊天类消息与房源查询类消息，分别返回自然语言字符串和 JSON 字符串格式响应

### 房源搜索（House Search）

- FR6：用户可按北京行政区（海淀、朝阳、通州等）筛选可租房源
- FR7：用户可按月租金范围（最低价/最高价）筛选可租房源
- FR8：用户可按户型（整租/合租/一居至四居）筛选可租房源
- FR9：用户可按装修类型（精装/简装/豪华/毛坯/空房）筛选可租房源
- FR10：用户可按朝向（朝南/朝北/南北通透等）筛选可租房源
- FR11：用户可按地铁距离（如 800 米以内近地铁）筛选可租房源
- FR12：系统可对分页结果自动获取完整数据集（首页后自动拉取剩余页，上限 5 页 / 50 条）
- FR13：用户可获取单套房源的完整详细信息（地址、户型、面积、租金、装修、朝向、楼层、设施列表、噪音评级、标签）

### 地标与通勤（Landmark & Commute）

- FR14：用户可按地标名称或关键词搜索地铁站、公司、商圈等地标，获取地标 ID 和位置信息
- FR15：用户可查询以指定地标为中心、指定距离范围内的可租房源（含步行距离和时间）
- FR16：用户可查询指定小区 1000 米范围内的生活配套信息（含商超、公园、餐饮等类别）及步行距离

### 租赁操作（Rental Operations）

- FR17：用户可对指定房源执行租房操作，系统调用 `POST /api/houses/{id}/rent` 完成状态变更（而非文字回复）
- FR18：用户可对已租房源执行退租操作，系统调用 `POST /api/houses/{id}/terminate` 完成状态变更
- FR19：用户可对指定房源执行下架操作，系统调用 `POST /api/houses/{id}/offline` 完成状态变更

### 输出格式控制（Output Format Control）

- FR20：系统可在房源查询完成时，将 `response` 字段输出为合法 JSON 字符串，结构为 `{"message": "自然语言推荐说明", "houses": ["HF_x", ...]}`，支持非 ASCII 字符
- FR21：系统可在聊天类响应时，将 `response` 字段输出为纯自然语言字符串，不含任何 JSON 结构
- FR22：系统可确保 `houses` 字段仅包含有效房源 ID（格式如 `"HF_x"`），数量不超过 5 个

### 系统运维（System Operations）

- FR23：系统可在容器启动 5 秒内完成初始化，绑定 `0.0.0.0:8191`，不在启动时执行外部 API 调用
- FR24：系统可以结构化格式记录关键事件日志，每条日志包含 timestamp、session_id、event_type 和 details 字段，覆盖 session 启动、工具调用（名称与参数）、模型响应摘要三类事件
- FR25：系统可在所有外部 API 调用（模型 API + 租房 API）异常时，返回 `status="error"` 响应，不向外抛出 HTTP 异常

## Non-Functional Requirements

### Performance

- NFR1：单用例非模型代码执行时间 < 5 秒（不含模型调用耗时），超出则判题系统判定该用例失败
- NFR2：系统提示 Token 数 ≤ 800，以控制时间片消耗；每个用例目标时间片消耗 ≤ 5 片
- NFR3：Tool Calling Loop 每用例最多执行 10 次迭代，防止无限循环耗尽全局时间片预算（300 片）
- NFR4：服务器响应 `duration_ms` 字段反映真实壁钟处理时间，误差 ≤ 10ms

### Integration

- NFR5：所有 `/api/houses/*` 请求必须携带正确的 `X-User-ID` 请求头（平台注册工号）；地标接口 `/api/landmarks/*` 无需此头
- NFR6：模型 API 调用使用 OpenAI 兼容格式，`model` 字段可为空字符串，`api_key` 必须为非空占位符字符串
- NFR7：HTTP 客户端连接在服务生命周期内保持复用，不在单次请求处理中重新创建

### Reliability

- NFR8：`POST /api/v1/chat` 接口可用率 100%，所有外部 API 调用异常必须被捕获并返回 `status="error"` 响应，不得向外暴露 HTTP 5xx 错误
- NFR9：`response` 字段 JSON 格式正确率 100%（房源查询场景），可通过 `json.loads(response)` 验证
- NFR10：不同 `session_id` 之间的会话历史隔离率 100%，任何实现不得允许跨 session 数据泄露
