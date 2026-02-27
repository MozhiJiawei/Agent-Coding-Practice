---
stepsCompleted: ["step-01-document-discovery", "step-02-prd-analysis", "step-03-epic-coverage-validation", "step-04-ux-alignment", "step-05-epic-quality-review", "step-06-final-assessment"]
documentsIncluded:
  prd: "_bmad-output/planning-artifacts/prd.md"
  architecture: "_bmad-output/planning-artifacts/architecture.md"
  epics: "_bmad-output/planning-artifacts/epics.md"
  ux: null
regeneratedAfterEpicRestructure: true
epicRestructureDate: "2026-02-27T17:36"
---

# Implementation Readiness Assessment Report

**Date:** 2026-02-27
**Project:** AI Agent Coding
**Note:** 本报告基于 17:36 重构后的最新 epics.md 重新生成，取代此前 15:21 版本。

---

## Document Inventory

| Document Type | File | Status |
|---|---|---|
| PRD | `_bmad-output/planning-artifacts/prd.md` | ✅ Ready |
| Architecture | `_bmad-output/planning-artifacts/architecture.md` | ✅ Ready |
| Epics & Stories | `_bmad-output/planning-artifacts/epics.md` | ✅ Ready（重构后版本）|
| UX Design | *(not found)* | ✅ N/A — 纯 API Backend，无 UI |

---

## PRD Analysis

### Functional Requirements

FR1: 用户可通过 `POST /api/v1/chat` 发送自然语言消息，系统在 200 响应中返回 Agent 回复
FR2: 系统可在同一 `session_id` 下跨轮次完整保留所有对话历史（system + user + assistant + tool results）
FR3: 系统可对不同 `session_id` 的对话历史进行严格隔离，不同 session 间数据不互通
FR4: 系统可在新 `session_id` 首条消息时自动调用 `POST /api/houses/init` 重置房源数据
FR5: 系统可区分聊天类消息与房源查询类消息，分别返回自然语言字符串和 JSON 字符串格式响应
FR6: 用户可按北京行政区（海淀、朝阳、通州等）筛选可租房源
FR7: 用户可按月租金范围（最低价/最高价）筛选可租房源
FR8: 用户可按户型（整租/合租/一居至四居）筛选可租房源
FR9: 用户可按装修类型（精装/简装/豪华/毛坯/空房）筛选可租房源
FR10: 用户可按朝向（朝南/朝北/南北通透等）筛选可租房源
FR11: 用户可按地铁距离（如 800 米以内近地铁）筛选可租房源
FR12: 系统可对分页结果自动获取完整数据集（首页后自动拉取剩余页，上限 5 页 / 50 条）
FR13: 用户可获取单套房源的完整详细信息（地址、户型、面积、租金、装修、朝向、楼层、设施列表、噪音评级、标签）
FR14: 用户可按地标名称或关键词搜索地铁站、公司、商圈等地标，获取地标 ID 和位置信息
FR15: 用户可查询以指定地标为中心、指定距离范围内的可租房源（含步行距离和时间）
FR16: 用户可查询指定小区 1000 米范围内的生活配套信息（含商超、公园、餐饮等类别）及步行距离
FR17: 用户可对指定房源执行租房操作，系统调用 `POST /api/houses/{id}/rent` 完成状态变更（而非文字回复）
FR18: 用户可对已租房源执行退租操作，系统调用 `POST /api/houses/{id}/terminate` 完成状态变更
FR19: 用户可对指定房源执行下架操作，系统调用 `POST /api/houses/{id}/offline` 完成状态变更
FR20: 系统可在房源查询完成时，将 `response` 字段输出为合法 JSON 字符串，结构为 `{"message": "自然语言推荐说明", "houses": ["HF_x", ...]}`，支持非 ASCII 字符
FR21: 系统可在聊天类响应时，将 `response` 字段输出为纯自然语言字符串，不含任何 JSON 结构
FR22: 系统可确保 `houses` 字段仅包含有效房源 ID（格式如 `"HF_x"`），数量不超过 5 个
FR23: 系统可在容器启动 5 秒内完成初始化，绑定 `0.0.0.0:8191`，不在启动时执行外部 API 调用
FR24: 系统可以结构化格式记录关键事件日志，每条日志包含 timestamp、session_id、event_type 和 details 字段，覆盖 session 启动、工具调用（名称与参数）、模型响应摘要三类事件
FR25: 系统可在所有外部 API 调用（模型 API + 租房 API）异常时，返回 `status="error"` 响应，不向外抛出 HTTP 异常

**Total FRs: 25**

### Non-Functional Requirements

NFR1: 单用例非模型代码执行时间 < 5 秒（不含模型调用耗时），超出则判题系统判定该用例失败
NFR2: 系统提示 Token 数 ≤ 800，以控制时间片消耗；每个用例目标时间片消耗 ≤ 5 片
NFR3: Tool Calling Loop 每用例最多执行 10 次迭代，防止无限循环耗尽全局时间片预算（300 片）
NFR4: 服务器响应 `duration_ms` 字段反映真实壁钟处理时间，误差 ≤ 10ms
NFR5: 所有 `/api/houses/*` 请求必须携带正确的 `X-User-ID` 请求头（平台注册工号）；地标接口 `/api/landmarks/*` 无需此头
NFR6: 模型 API 调用使用 OpenAI 兼容格式，`model` 字段可为空字符串，`api_key` 必须为非空占位符字符串
NFR7: HTTP 客户端连接在服务生命周期内保持复用，不在单次请求处理中重新创建
NFR8: `POST /api/v1/chat` 接口可用率 100%，所有外部 API 调用异常必须被捕获并返回 `status="error"` 响应，不得向外暴露 HTTP 5xx 错误
NFR9: `response` 字段 JSON 格式正确率 100%（房源查询场景），可通过 `json.loads(response)` 验证
NFR10: 不同 `session_id` 之间的会话历史隔离率 100%，任何实现不得允许跨 session 数据泄露

**Total NFRs: 10**

### Additional Requirements & Constraints

**竞赛合规红线：**
- COMP1: 禁止硬编码答案（代码审核阶段会检测，一经发现取消参赛资格）
- COMP2: 禁止外部模型，所有调用必须通过 `model_ip:8888` 的 qwen3-32b 接口
- COMP3: X-User-ID 必须为平台注册真实工号，传错工号导致数据隔离失败
- COMP4: 3 月 3 日需求变更——工具定义（`TOOLS` 常量）和系统提示必须模块化，支持 30 分钟内完成更新

**技术约束：**
- TECH1: 服务端口固定 8191，`--host 0.0.0.0 --port 8191`
- TECH2: 全局时间片预算 300 片，`t = 1 + max(0, (n_tokens - 1000) * 0.3)`
- TECH3: 不得抛出 HTTP 4xx/5xx 异常（判题系统无法处理非 200 响应）
- TECH4: `USER_ID` 通过环境变量注入，不在代码中硬编码
- TECH5: `httpx.AsyncClient` 通过 FastAPI lifespan 上下文管理器创建，整个生命周期复用

### PRD Completeness Assessment

PRD 文档结构完整，覆盖执行摘要、成功标准、用户旅程（5 条）、领域需求（竞赛合规红线 + 技术约束）、创新设计、API 端点规范、数据结构、错误码、分阶段开发策略（MVP/Post-MVP/Expansion）、完整 FR/NFR 列表。需求数量充足（25 FR + 10 NFR），分类清晰，量化指标明确（时间片、Token 上限、迭代上限均有具体数值）。

**评估：PRD 完整性 ✅ HIGH**

---

## Epic Coverage Validation

### Coverage Matrix（基于重构后 epics.md）

| FR | PRD Requirement (摘要) | Epic Coverage | Story | Status |
|---|---|---|---|---|
| FR1 | POST /api/v1/chat 接口 | Epic 1 | Story 1.4 | ✅ Covered |
| FR2 | 跨轮次保留对话历史 | Epic 2 | Story 2.1 | ✅ Covered |
| FR3 | 不同 session 历史隔离 | Epic 2 | Story 2.1 | ✅ Covered |
| FR4 | 新 Session 自动 init 钩子 | Epic 2 | Story 2.2 | ✅ Covered |
| FR5 | 聊天/查询意图分类 | Epic 2 | Story 2.3 | ✅ Covered |
| FR6 | 按行政区筛选房源 | Epic 3 | Story 3.1 | ✅ Covered |
| FR7 | 按月租金范围筛选 | Epic 3 | Story 3.1 | ✅ Covered |
| FR8 | 按户型筛选 | Epic 3 | Story 3.1 | ✅ Covered |
| FR9 | 按装修类型筛选 | Epic 3 | Story 3.1 | ✅ Covered |
| FR10 | 按朝向筛选 | Epic 3 | Story 3.1 | ✅ Covered |
| FR11 | 按地铁距离筛选 | Epic 3 | Story 3.1 | ✅ Covered |
| FR12 | 分页结果自动完整拉取 | Epic 3 | Story 3.1 | ✅ Covered |
| FR13 | 单套房源完整详情 | Epic 3 | Story 3.1 | ✅ Covered |
| FR14 | 地标关键词搜索 | Epic 3 | Story 3.1 | ✅ Covered |
| FR15 | 地标附近可租房源查询 | Epic 3 | Story 3.1 | ✅ Covered |
| FR16 | 小区周边生活配套查询 | Epic 3 | Story 3.1 | ✅ Covered |
| FR17 | 租房操作 API 执行 | Epic 3 | Story 3.1 | ✅ Covered |
| FR18 | 退租操作 API 执行 | Epic 3 | Story 3.1 | ✅ Covered |
| FR19 | 下架操作 API 执行 | Epic 3 | Story 3.1 | ✅ Covered |
| FR20 | 房源查询输出合法 JSON 格式 | Epic 2 | Story 2.3 | ✅ Covered |
| FR21 | 聊天响应输出纯自然语言 | Epic 2 | Story 2.3 | ✅ Covered |
| FR22 | houses 最多 5 个有效 ID | Epic 2 | Story 2.3 | ✅ Covered |
| FR23 | 5 秒内启动绑定 0.0.0.0:8191 | Epic 1 | Story 1.4 | ✅ Covered |
| FR24 | 结构化事件日志 | Epic 4 | Story 4.2 | ✅ Covered |
| FR25 | 全局异常捕获不抛 5xx | Epic 1 | Story 1.4 | ✅ Covered |

### NFR Coverage Matrix

| NFR | Requirement (摘要) | Epic Coverage | Status |
|---|---|---|---|
| NFR1 | 非模型执行时间 < 5s | Epic 3 (Story 3.1 串行翻页), Epic 4 (Story 4.2) | ✅ Covered |
| NFR2 | 系统提示 ≤ 800 Token，≤ 5 片/用例 | Epic 2 (Story 2.3) | ✅ Covered |
| NFR3 | Loop 最多 10 次迭代 | Epic 2 (Story 2.3) | ✅ Covered |
| NFR4 | duration_ms 误差 ≤ 10ms | Epic 1 (Story 1.4), Epic 4 (Story 4.2) | ✅ Covered |
| NFR5 | X-User-ID 请求头规则（地标无需/房源需要）| Epic 3 (Story 3.1) | ✅ Covered |
| NFR6 | OpenAI 兼容格式，api_key 非空 | Epic 2 (Story 2.3) | ✅ Covered |
| NFR7 | HTTP 客户端生命周期内复用 | Epic 1 (Story 1.3) | ✅ Covered |
| NFR8 | 所有异常返回 status="error" | Epic 1 (Story 1.4), Epic 3 (Story 3.1 双层异常) | ✅ Covered |
| NFR9 | response JSON 正确率 100% | Epic 2 (Story 2.3 Format Guard) | ✅ Covered |
| NFR10 | Session 间历史隔离率 100% | Epic 2 (Story 2.1) | ✅ Covered |

### Missing Requirements

**无缺失 FR。** 所有 25 个功能需求均有对应 Epic + Story 覆盖。

**无缺失 NFR。** 所有 10 个非功能需求均有对应 Epic + Story 覆盖。

### Coverage Statistics

- Total PRD FRs: 25
- FRs covered in epics: 25
- **FR Coverage: 100%**
- Total PRD NFRs: 10
- NFRs covered in epics: 10
- **NFR Coverage: 100%**

---

## UX Alignment Assessment

### UX Document Status

**Not Found** — 在 `_bmad-output/planning-artifacts/` 下未找到任何 `*ux*.md` 文件。

### Implied UX Assessment

本项目为 **纯 API Backend** 类型（PRD 明确声明：`Project Type: API Backend（FastAPI + LLM Tool Calling）`，"无前端 UI、无视觉设计需求、无用户注册/权限体系"）。

- PRD 中未提及任何用户界面（UI）
- 无 Web / Mobile 组件
- 对外仅暴露单一 HTTP 端点 `POST /api/v1/chat`，直接由判题系统调用
- 最终用户交互通过自然语言 API 完成，无需 UX 文档

### Alignment Issues

无对齐问题。本项目性质决定 UX 文档不适用。

### Warnings

⚠️ **INFO（非阻塞）：** UX 文档缺失为预期状态。作为竞赛 API Backend 项目，无 UI 是设计决策，非遗漏。此项对实现就绪度无影响。

---

## Epic Quality Review

### 重构影响说明（与旧报告对比）

本次 Epic 重构将原 11 个 backlog story（2.3-2.5, 3.1-3.3, 4.1-4.3, 5.1, 6.1）合并为 3 个 story（2.3, 3.1, 4.2），对原有 Major Issues 的影响：

| 原 Issue | 类型 | 重构后状态 |
|---|---|---|
| M1: Story 2.4 前向依赖 Epic 3-5 工具函数 | 🟠 Major | ✅ **已解决** — "所有工具集成"AC 现在明确归属 Story 3.1 |
| M2: `init_houses()` 函数归属未定义 | 🟠 Major | ✅ **已解决** — Story 2.2 已 done，架构文档明确归属 `tools.py` |
| C1: Story 2.4 与 Story 3.1 AC 重叠 | 🟡 Minor | ✅ **已解决** — 合并后无重叠 |
| C2: Story 2.5 houses ID 提取机制不明确 | 🟡 Minor | 🔄 **持续存在** — 现在在 Story 2.3 中 |
| C3: Epic 6 日志排在最后 | 🟡 Minor | 🔄 **持续存在** — 现在是 Epic 4，仍在末尾 |

---

### Epic 结构验证

#### Epic 1: 项目脚手架与 API 服务基础（**全部 done**）

| 检查项 | 结果 |
|---|---|
| 用户价值明确 | ⚠️ 技术偏重，但作为基础设施可接受 |
| Epic 可独立运行 | ✅ 服务可启动并接收请求 |
| 无前向依赖 | ✅ 无 |
| ACs 质量 | ✅ 具体可测，已验收 |

**状态：** 4/4 stories 全部 done，Epic 1 实际已完成。✅

---

#### Epic 2: 会话管理与核心 Agent Loop（2.1、2.2 done，**2.3 backlog**）

| 检查项 | 结果 |
|---|---|
| 用户价值明确 | ✅ "用户可以进行多轮对话，Agent 完整保留历史" |
| Epic 可独立运行 | ⚠️ Story 2.3 完成后具备基本运行能力，但无实际工具能力（Epic 3 提供） |
| 无前向依赖 | 🟡 见下方 C1（新） |

**Story 独立性：**
- Story 2.1 ✅ — done，Session 存储完整实现
- Story 2.2 ✅ — done，init 钩子完整实现
- Story 2.3 🟡 — 见下方 C1（新）

---

**🟡 Minor Concern #1（新）— Story 2.3 实现顺序需开发者注意：**

Story 2.3 包含 AC：
> "TOOL_DISPATCH: dict[str, Callable] in agent.py is used to look up and call the correct function"

但 6 个工具函数在 Story 3.1 中实现。开发者在实现 Story 2.3 时，需用空 dict 或 stub 占位，在 Story 3.1 完成后回填。**这不是架构缺陷**（epics.md 已将"引用所有 6 个工具"的 AC 正确归属到 Story 3.1），但开发者需理解：Story 2.3 → Story 3.1 之间存在一次 `agent.py` 的更新动作（填充 TOOL_DISPATCH）。

**建议：** 在 Story 3.1 的 AC 中（已有）明确包含"更新 agent.py TOOL_DISPATCH 引用全部工具"，开发者据此执行即可。无需修改文档，仅需开发者知晓实现顺序。

---

**🟡 Minor Concern #2（持续）— Story 2.3 houses ID 提取机制不明确：**

Story 2.3 要求 `houses` 仅包含格式如 `"HF_x"` 的有效 ID，但架构文档中仅说"从模型最终 content 中提取 house_ids"，未明确说明：
- 模型被 SYSTEM_PROMPT 引导后以何种固定字段格式输出 house_ids？
- Format Guard 是解析模型 content 字符串中的 ID，还是从 tool_results 中聚合？

**建议：** 在 SYSTEM_PROMPT 设计（Story 2.3）中明确：引导模型在需要返回房源时，将 house_id 列表明确输出于 content 中（如 `推荐房源：HF_42, HF_107`），Format Guard 通过正则 `HF_\w+` 从 content 中提取并去重，裁剪为最多 5 个。或者，Format Guard 改为从本轮工具返回结果中聚合 house_id 字段，这样更可靠（不依赖模型格式遵从性）。

---

#### Epic 3: 工具层全量实现（**backlog**）

| 检查项 | 结果 |
|---|---|
| 用户价值明确 | ✅ 用户可搜索房源、查详情、找地标、查配套、执行操作 |
| Epic 可独立运行 | ✅ 配合 Epic 1+2 基础设施可完整运行 |
| 无前向依赖 | ✅ 仅向后引用已有 Epic 组件 |

**Story 3.1 独立性：** ✅ — `tools.py` 可完整独立实现，不依赖其他未完成的模块（仅需 Epic 1 中 lifespan 创建的 httpx client）

**ACs 质量：**
- 基础架构 ACs：TOOLS 常量、USER_ID、_get_headers()、MAX_PAGES — ✅ 清晰具体
- search_houses ACs：多条件参数、串行翻页（while + MAX_PAGES=5）、agent 透明 — ✅ 完整
- get_house_detail ACs：house_id 字符串处理、完整字段返回 — ✅
- search_landmark ACs：无 X-User-ID 头规则明确 — ✅
- search_nearby_landmark ACs：HOUSE_SEARCH_TOOLS 集合归属、X-User-ID — ✅
- get_nearby_amenities ACs：max_distance_m 默认值、不在 HOUSE_SEARCH_TOOLS — ✅
- execute_action ACs：action 映射、无效 action 处理、不在 HOUSE_SEARCH_TOOLS — ✅
- 所有工具均有错误处理 ACs（返回 {"error": "..."} 不 raise）— ✅

**🟡 Minor Concern #3（新）— Story 3.1 体量较大，建议分组实现：**

Story 3.1 合并了原 7 个 story（3.1-3.3 + 4.1-4.3 + 5.1），单 story 覆盖 6 个工具函数 + 基础架构。虽然 ACs 清晰，但实现量较大。建议开发者在 **一次实现** 中按逻辑分组处理：

1. **第一组**（基础架构 + 房源工具）：TOOLS 常量 + `_get_headers()` + `search_houses` + `get_house_detail`
2. **第二组**（地标工具）：`search_landmark` + `search_nearby_landmark` + `get_nearby_amenities`
3. **第三组**（操作工具）：`execute_action`

全部完成后，更新 `agent.py` 的 TOOL_DISPATCH 引用（见 C1 建议）。

---

#### Epic 4: 结构化日志与系统可观测性（**backlog**）

| 检查项 | 结果 |
|---|---|
| 用户价值明确 | ⚠️ 开发者价值（"As a developer"），但作为竞赛调试核心工具完全合理 |
| Epic 可独立运行 | ✅ 横切关注点，可叠加到其他 Epic 完成后 |
| 无前向依赖 | ✅ 无 |

**Story 4.2 ACs 质量：**
- `log_event(event_type, session_id, details)` 函数签名明确 ✅
- 5 种 event_type 常量及触发时机完整定义 ✅
- JSON 格式输出（json.dumps + ensure_ascii=False）✅
- 日志序列验证 AC（SESSION_START → SESSION_INIT → MODEL_RESPONSE → TOOL_CALL）✅

**🟡 Minor Concern #4（持续）— 日志基础设施排在最后：**

结构化日志是打榜失分定位的核心工具。当前排序意味着 Epic 2（Agent Loop）和 Epic 3（工具层）的开发和早期测试期间缺乏结构化日志。

**建议（可选）：** 考虑在 Story 2.3 实现过程中，顺手实现 `log_event()` 函数骨架（仅 `SESSION_START` 和 `MODEL_RESPONSE` 两种事件），其余事件类型在 Story 4.2 中补全。这使 Agent Loop 开发期间就有可用的日志，同时保持 Story 4.2 的完整验收价值。

---

### Best Practices Compliance Summary

| Epic | 用户价值 | 独立性 | 无前向依赖 | ACs 质量 | FR 可追踪 |
|---|---|---|---|---|---|
| Epic 1 | ⚠️ 技术偏重 | ✅ | ✅ | ✅ (已验收) | ✅ |
| Epic 2 | ✅ | ✅ | 🟡 C1 注意 | ✅ | ✅ |
| Epic 3 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Epic 4 | ⚠️ 开发者价值 | ✅ | ✅ | ✅ | ✅ |

### Quality Findings by Severity

#### 🔴 Critical Violations
无。

#### 🟠 Major Issues（不阻塞）
无。（原 M1、M2 已通过重构解决。）

#### 🟡 Minor Concerns（建议改善，不阻塞）

| # | Concern | 位置 | 建议 |
|---|---|---|---|
| C1 | Story 2.3 实现时 TOOL_DISPATCH 为空，需 Story 3.1 完成后回填 | Epic 2, Story 2.3 / Epic 3, Story 3.1 | 开发者知晓两 story 间存在一次 agent.py 更新动作，Story 3.1 AC 中已明确，无需修改文档 |
| C2 | Story 2.3 Format Guard 中 houses ID 来源逻辑未明确说明 | Epic 2, Story 2.3 | 在 SYSTEM_PROMPT 设计时明确模型输出 house_id 格式，或改为从 tool_results 中聚合 |
| C3 | Story 3.1 体量较大（6 工具 + 基础架构），建议分组实现 | Epic 3, Story 3.1 | 按"基础+房源 → 地标 → 操作"三组顺序实现，分组验收后合并 |
| C4 | Epic 4（日志）排在最后，开发早期缺少调试可见性 | Epic 4, Story 4.2 | 可选：在 Story 2.3 中提前实现 log_event() 骨架（SESSION_START + MODEL_RESPONSE），Story 4.2 补全其余事件 |

---

## Summary and Recommendations

### Overall Readiness Status

## ✅ READY（无阻塞问题，可立即开始实现）

文档体系完整、需求覆盖率 100%、Epic/Story 结构清晰合理。旧报告中的 2 个 Major Issues 均已通过本次 Epic 重构解决。剩余 4 个 Minor Concerns 均不阻塞实现，可在开发过程中按需处理。

---

### Assessment Summary

| 维度 | 状态 | 关键发现 |
|---|---|---|
| **PRD 完整性** | ✅ HIGH | 25 FR + 10 NFR，量化指标清晰，分阶段策略明确 |
| **FR 覆盖率** | ✅ 100% | 25/25 FRs 有对应 Epic + Story，FR 到新 story 编号映射正确 |
| **NFR 覆盖率** | ✅ 100% | 性能、集成、可靠性全部有 AC 对应 |
| **UX 对齐** | ✅ N/A | 纯 API Backend，无 UI，UX 文档不适用 |
| **架构对齐** | ✅ 已对齐 | Epics 文档明确引用了架构约束并逐条落入 AC |
| **Epic 质量** | ✅ 轻微提示 | 无 Critical / Major 问题，4 个 Minor Concerns（均为实现建议） |
| **Story 质量** | ✅ 良好 | ACs 总体清晰具体，重构消除了原有的依赖歧义 |
| **重构收益** | ✅ 积极 | 从 17 stories 缩减为 9 stories，2 个 Major Issues 消除，代码边界更清晰 |

---

### Critical Issues Requiring Immediate Action

**无 Critical Issues。** 可直接开始下一个 backlog story（Story 2.3）的实现。

---

### Recommended Next Steps

1. **[立即执行] 开始 Story 2.3 实现（Agent Loop 完整实现）：**
   按以下顺序实现 `agent.py`：
   - SYSTEM_PROMPT（≤800 Token，含角色定义、工具调用、意图分类、格式指令）
   - while loop 骨架 + MAX_ITERATIONS = 10
   - TOOL_DISPATCH（初始为空 dict `{}`，等 Story 3.1 完成后回填）
   - tool message 格式强制（json.dumps + role="tool"）
   - HOUSE_SEARCH_TOOLS + tools_called 追踪 + Format Guard

2. **[C2 建议] 在 SYSTEM_PROMPT 中明确 house_id 输出约定：**
   在设计 SYSTEM_PROMPT 时，明确引导模型在 assistant content 中以固定格式包含 house_id（如列出房源 ID），使 Format Guard 可稳定提取。或者在 Format Guard 逻辑中改为从本轮 tool_results 聚合 house_id，不依赖模型 content 格式。

3. **[C3 建议] Story 3.1 实现时分三组推进：**
   - 第一组：TOOLS 常量 + _get_headers() + search_houses（含翻页）+ get_house_detail → 验证后继续
   - 第二组：search_landmark + search_nearby_landmark + get_nearby_amenities
   - 第三组：execute_action → 全部完成后更新 agent.py TOOL_DISPATCH

4. **[C4 可选] 在 Story 2.3 中提前引入 log_event() 骨架：**
   实现 `SESSION_START` 和 `MODEL_RESPONSE` 两种事件类型，覆盖 Agent Loop 开发期最需要的日志。Story 4.2 再补全 `SESSION_INIT`、`TOOL_CALL`、`ERROR` 三种事件。

5. **[实现顺序] 推荐执行序列：**
   Story 2.3（agent.py 骨架）→ Story 3.1（tools.py 全量）→ 回填 TOOL_DISPATCH → Story 4.2（日志完整）→ 全量 smoke test

---

### Final Note

本次评估共发现 **4 个 Minor Concerns**（0 Critical / 0 Major），与前次报告相比质量显著提升（原 5 个问题含 2 个 Major，现全部降至 Minor 级别）。

**Epic 重构的核心收益已得到验证：**
- 工具层（Story 3.1）作为统一边界，消除了跨 Epic 的 AC 依赖歧义
- TOOL_DISPATCH 归属明确（2.3 定义机制，3.1 填充实现）
- 总 story 数从 17 个缩减为 9 个，每个 story 对应一个清晰的代码文件或功能边界

**项目文档体系质量高。** PRD、架构、Epics 三文档高度一致，架构决策完整落入 Story ACs，竞赛约束红线（格式守卫、翻页、Session 隔离）均有专属 AC 保障。**可以立即进入实现阶段。**

**Assessed by:** LJW (via BMAD Implementation Readiness Workflow — regenerated post-epic-restructure)
**Assessment Date:** 2026-02-27
**Report File:** `_bmad-output/planning-artifacts/implementation-readiness-report-2026-02-27.md`
