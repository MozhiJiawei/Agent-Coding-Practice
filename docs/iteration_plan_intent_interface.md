# 意图接口迭代计划（三步走）

> 基于 [intent_interface_design_v2.md](./intent_interface_design_v2.md) 设计，分三个迭代实现：先定义意图接口以解耦，再改 Agent 流程并用 E2E 验证提参，最后实现工具调用与 Mock 联调并保证接口与结果正确。

---

## 总体目标

- **全场景覆盖**：闲聊、单/多条件搜索、商圈/地标/地铁搜索、平台比价、标签偏好（宠物/付款/看房/配套/退租等）、操作类（租房/退租/下架）。
- **提参正确率**：参数命名贴近自然语言，枚举与硬/软偏好边界清晰，无 `soft_preferences` 嵌套。
- **工具与仿真一致**：Agent 工具调用 100% 符合 [interface_simulate.md](./interface_simulate.md)，与 [test-simulator/mock_rental.py](../test-simulator/mock_rental.py) 联调后查询与操作结果正确。

---

## 迭代一：定义意图接口，支撑后续并行开发

### 需求

1. **产出可被 Agent 与后端共用的“契约”**  
   定义并落地的内容需同时满足：  
   - Agent 侧：LLM 的 function calling 入参（update_preferences 等）仅依赖本接口。  
   - 后端/工具侧：搜索、过滤、排序的实现仅依赖同一套参数与数据模型，不依赖 Agent 内部实现。  
   这样迭代二（Agent 流程）与迭代三（工具实现、过滤排序、Mock 联调）可以并行开发。

2. **意图接口具体内容**  
   - **5 个工具的 JSON Schema**  
     按设计文档第四章：`update_preferences`、`search_by_preferences`、`get_house_detail`、`get_house_listings`、`execute_action` 的 `name`、`description`、`parameters`（含所有 properties、enum、description）。  
     - `update_preferences`：包含全部 39 个参数（含 location、价格户型等 26 个 + pet_policy、viewing_method、viewing_time、lease_flexibility、required_utilities、termination_sublet、parking_type、security_requirement、property_management、environment_preference、required_nearby、house_feature、landlord_contract 等 13 个标签类直接参数，以及 tag_preferences）；**不包含** `soft_preferences`、**不包含** `tag_requirements`（已改为上述 13 个直接参数）。  
     - 其余 4 个工具按设计文档 4.2～4.5 的 schema 定义。  
   - **UserPreferences 数据模型（代码级）**  
     与设计文档第七章一致：字段列表、类型、可选/必填；包含 13 个标签类直接参数及 `tag_preferences`，**不包含** `tag_requirements`、**不包含** `soft_preferences` 及旧嵌套结构。
   - **标签参考表（文档 + 可选代码常量）**  
     设计文档 4.1 表格中仅 **tag_preferences** 的可用值（硬约束已改为直接参数），以文档形式固定，便于迭代二写 system prompt、迭代三做过滤与映射。
   - **意图与仿真 API 的映射说明（文档）**  
     高层说明：哪些意图参数对应 [interface_simulate.md](./interface_simulate.md) 的哪些接口与 query/body 参数；13 个标签类直接参数与 tag_preferences 仅在后端过滤/排序中使用，不直接对应单一 API 参数。不要求在本迭代实现具体调用逻辑，只把映射关系写清，供迭代三实现。

3. **存放位置与形式**  
   - TOOLS 列表（JSON Schema）与 UserPreferences 模型：放在当前 Agent 工程内（如 `tools.py` 或等价模块），便于迭代二直接引用。  
   - 设计文档中“意图接口”章节可指向上述代码/配置文件，或把最终 schema 以附录形式贴在设计文档中，保证单一事实来源。  
   - 标签参考表：设计文档中已有；若在代码中使用，可增加常量列表或从设计文档生成的只读数据，与文档保持一致。

### 验收标准

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | 5 工具 Schema 完整且一致 | 与 intent_interface_design_v2 第四章逐项对照，参数名、类型、enum、description 一致；`update_preferences` 无 `soft_preferences`、无 `tag_requirements`，有 13 个标签类直接参数及 `tag_preferences`，共 39 个参数。 |
| 2 | UserPreferences 与设计一致 | 与设计文档第七章字段、类型一致；含 13 个标签类直接参数及 `tag_preferences`；无 `tag_requirements`、无 `soft_preferences` 或旧嵌套。 |
| 3 | 标签参考表可被引用 | 文档或代码中有一份与设计 4.1 表格一致的标签枚举/列表，供后续 prompt 与过滤使用。 |
| 4 | 意图→仿真 API 映射文档 | 有单独小节或文档说明：各意图参数与 interface_simulate 中接口、参数的对应关系；标注“标签类仅在后端过滤/排序使用”。 |
| 5 | 无功能行为变更 | 本迭代不实现或修改任何调用逻辑、过滤、排序；仅增加/调整接口定义与文档，现有 E2E 可仍失败或跳过，不要求通过。 |

---

## 迭代二：调整 Agent 流程，支持新意图接口并用 E2E 验证提参

### 需求

1. **Agent 流程与入口**  
   - 使用迭代一定义的 5 工具 Schema 作为 LLM function calling 的 tools（即 update_preferences、search_by_preferences、get_house_detail、get_house_listings、execute_action）。  
   - 每轮对话：若 LLM 产出上述工具调用，则解析参数并交给“工具实现层”（工具实现层在本迭代可仍为占位或旧实现，见下）；若为闲聊或无找房意图，则不调用工具、直接回复。  
   - 调用链规则与设计文档“调用链规则”一致：  
     - 用户有新偏好 + 找房 → 先 `update_preferences` 再 `search_by_preferences`；  
     - 仅找房且偏好已设 → 仅 `search_by_preferences`；  
     - 问某房详情 → `get_house_detail`；  
     - 要比价 → `get_house_listings`；  
     - 租/退/下架 → `execute_action`。

2. **System prompt 与提参规则**  
   - 更新 system prompt，包含：  
     - 硬约束 vs 软偏好的判断规则（设计文档 6.1）：明确/肯定 → 硬约束字段（含 13 个标签类直接参数）；“最好/希望/如果有” → `tag_preferences`，不设对应硬约束字段。
     - 常见隐含意图提取表（设计 6.2）及价格“左右”约定（6.3）。
     - 硬约束用直接参数、tag_preferences 使用规则（6.5）及 payment_method/deposit_type/no_agent_fee 仅用独立字段（6.6）。
     - `soft_preferences` 移除后的迁移规则（6.4）：一律用 `tag_preferences` 表达软偏好。  
   - 提供精简版标签参考表（或引用迭代一文档），便于 LLM 输出合法标签值。

3. **Session 与偏好合并**  
   - 使用迭代一的 UserPreferences 模型在 session 中存储/合并偏好。  
   - `update_preferences` 调用时：仅合并本轮传入的字段；若传入 `clear_location: true`，则清空已有位置再写入新的 `location`。  
   - 不要求本迭代实现“真实搜索/过滤”（可继续返回占位或旧逻辑），但合并逻辑必须按新模型（无 soft_preferences、无 tag_requirements，有 13 个标签类直接参数与 tag_preferences）正确实现。

4. **E2E 验证方式**  
   - 使用 [tests/e2e/run_e2e.ps1](../tests/e2e/run_e2e.ps1) 运行用例（默认或指定 `-SimCase`/`-SimTag`）。  
   - 验证重点：**意图提参正确性**——即 E2E 用例中对 `tool_call_chain`、`tool_call_args`、`contains` 的断言是否通过。  
   - 若 test_cases.yaml 中仍有对 `soft_preferences` 或 `tag_requirements` 的断言，需在本迭代中按设计文档改为对直接参数或 `tag_preferences` 的断言（参见设计文档 5.2、5.3），使“意图层”期望与 v2 设计一致。  
   - 不要求本迭代通过“查询结果正确性”或“HTTP 调用与 interface_simulate 完全一致”的用例（这些留给迭代三）；若工具实现仍为占位，部分依赖真实搜索/操作的用例可预期失败，但提参相关断言应通过。

### 验收标准

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | 使用新 TOOLS 与 UserPreferences | Agent 使用的 tools 定义与迭代一完全一致；session 中偏好存储与合并基于 UserPreferences（无 soft_preferences）。 |
| 2 | 调用链符合设计 | 多轮对话中，工具调用顺序符合设计文档“调用链规则”（如先 update 再 search；详情/比价/执行动作单独调用）。 |
| 3 | System prompt 覆盖提参规则 | 包含 6.1～6.6 要点及标签参考；LLM 输出中“最好”类表达进入 tag_preferences，不进入硬约束字段。 |
| 4 | E2E 提参断言通过 | 运行 `run_e2e.ps1`（全量或选定用例）：所有对 `tool_call_chain`、`tool_call_args`、`contains` 的断言通过；无对 `soft_preferences` 的断言，或已改为对 tag_preferences/硬约束的等价断言。 |
| 5 | 占位实现可区分 | 若工具实现仍为占位，需在代码或配置上可区分，以便迭代三替换为真实实现而不影响本迭代验收。 |

---

## 迭代三：按意图接口实现工具调用、过滤、排序，与 Mock 联调并保证接口与结果正确

### 需求

1. **工具→仿真 API 映射实现**  
   - 严格按照 [interface_simulate.md](./interface_simulate.md) 与接口详细说明（含 OpenAPI 示例）：  
     - 请求头：房源相关接口带 `X-User-ID`（用户工号）。  
     - 新 Session 时调用 `POST /api/houses/init` 做房源数据重置。  
     - `search_by_preferences`：根据当前 UserPreferences 映射到 `GET /api/houses/by_platform`（及必要时 `GET /api/houses/nearby`、地标解析等）的 query 参数；参数名、枚举值与文档一致（如 `district`、`area`、`min_price`、`max_price`、`bedrooms`、`rental_type`、`decoration`、`orientation`、`elevator`、`min_area`、`max_area`、`property_type`、`subway_line`、`max_subway_dist`、`commute_to_xierqi_max`、`available_from_before`、`sort_by`、`sort_order`、`listing_platform`、`page`、`page_size` 等）。  
     - `get_house_detail` → `GET /api/houses/{house_id}`；`get_house_listings` → `GET /api/houses/listings/{house_id}`。  
     - `execute_action`：`rent` → `POST /api/houses/{house_id}/rent`，`terminate` → `POST .../terminate`，`offline` → `POST .../offline`；body/query 中 `listing_platform` 必填且为枚举值之一。  
   - 所有请求的 path、query、body 格式与 interface_simulate 描述一致（如 `available_from_before` 与文档一致，不出现未文档化参数）。

2. **后端过滤与排序（post_filter_and_rank）**  
   - 在拿到仿真 API 返回的列表后，按设计文档第八章实现：  
     - **floor_pref**：硬过滤，支持“共N层”映射（总层数≤6 可视为低层）。  
     - **13 个标签类直接参数**（pet_policy、viewing_method、required_nearby 等）：硬过滤，房源 `tags` 须包含对应值，按设计 8.1。  
     - **tag_preferences**：软加分，含属性标签映射（有电梯、精装修、朝南、高层/低层、整租/合租等），按设计 8.2 逻辑加分。  
     - **payment_method / deposit_type / no_agent_fee**：按设计 8.3 做 tag 硬过滤（对应房源 tags）。  
     - **subway_line**：按设计 8.4 包含匹配。  
   - 排序：支持 `sort_by`（price/area/subway）与 `sort_order`（asc/desc），与文档一致；结合 tag_preferences 加分后的综合排序需正确。

3. **location 与地标/商圈/地铁解析**  
   - 用户意图中的 `location`（行政区/商圈/地标/地铁站/小区名）需正确映射到仿真 API：  
     - 能走 `by_platform` 的用 `district`/`area` 等；  
     - 需要“某地标附近”的，先调地标接口（如 `GET /api/landmarks/search` 或 `name/{name}`）再调 `GET /api/houses/nearby`，参数与文档一致（如 `landmark_id`、`max_distance`、`listing_platform`、分页）。  
   - 与 [interface_simulate.md](./interface_simulate.md) 中“近距离概念”（如近地铁 800m、地铁可达 1000m）一致。

4. **与 test-simulator 及 mock_rental 联调**  
   - 使用 [test-simulator/mock_rental.py](../test-simulator/mock_rental.py) 作为租房 API 实现，与 [tests/e2e/run_e2e.ps1](../tests/e2e/run_e2e.ps1) 一起运行：  
     - Agent 发出的 HTTP 请求（方法、路径、query、body、头）与 mock_rental 暴露的接口 100% 符合 interface_simulate；  
     - 租/退/下架必须通过对应 POST 完成，不在对话中仅用文字表示。  
   - 联调通过后：  
     - 查询类用例：返回的房源列表与偏好、过滤、排序一致（如价格区间、户型、标签、地铁距离、平台等）。  
     - 操作类用例：租/退/下架后状态与 mock 状态一致，且可被后续查询正确反映。

5. **测试用例对齐**  
   - test_cases.yaml 中所有依赖“真实搜索/过滤结果”或“操作结果”的断言（如返回条数、房源 ID、价格、状态）应在本迭代满足；  
   - 若有用例仍写“软偏好”或旧参数，需全部改为 v2 意图（tag_preferences/硬约束），并在本迭代一并通过。

### 验收标准

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | 工具调用 100% 符合 interface_simulate | 所有请求的 URL、方法、headers（X-User-ID）、query、body 与 interface_simulate 及 OpenAPI 一致；无未文档化参数或错误枚举。 |
| 2 | 过滤与排序符合设计 | post_filter_and_rank 实现设计 8.0～8.4；13 个直接参数→tags 硬过滤、tag_preferences 加分、floor_pref/subway_line/payment/deposit/no_agent_fee 行为正确。 |
| 3 | 租/退/下架通过 API 完成 | 用户确认租/退/下架时，必调对应 POST；mock 状态正确更新。 |
| 4 | E2E 全量通过 | `run_e2e.ps1` 默认（或指定范围）运行通过；包含提参正确性与查询/操作结果正确性的断言。 |
| 5 | 查询结果正确 | 针对若干典型场景（如价格+户型+标签、地标附近、地铁线、平台比价）：返回列表与 mock 数据及过滤/排序逻辑一致，无漏筛、错筛或排序错误。 |

---

## 依赖与顺序

- **迭代一** 为独立前提，不依赖二、三。  
- **迭代二** 依赖迭代一（接口与模型已定），不依赖迭代三（可用占位实现）。  
- **迭代三** 依赖迭代一（映射与模型）、迭代二（Agent 已用新接口与 UserPreferences）；并与 mock_rental、test_cases、interface_simulate 对齐。

建议顺序：**先完成迭代一 → 迭代二与迭代三可部分并行**（迭代二做 Agent+E2E 提参，迭代三做工具实现与 Mock 联调），最后在迭代三收口 E2E 全量通过与结果正确性。
