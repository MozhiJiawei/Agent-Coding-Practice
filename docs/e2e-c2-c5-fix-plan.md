# E2E 用例 c2~c5 修改方案（让 Agent 行为符合用例定义）

## 一、测试结果摘要

运行 `tests/e2e/run_e2e.ps1 -SimCase "c2","c3","c4","c5"` 后：

| 用例 | 结果 | 失败原因 |
|------|------|----------|
| c2   | WARN | 每轮 `update_preferences` 上报参数多出 `near_subway`（用例期望为 `max_subway_dist` + `sort_by` + `sort_order`） |
| c3   | WARN | Round1 多出 `min_price`,`max_price`；Round2 多出 `min_price`,`max_price`,`rental_type` |
| c4   | WARN | 多出 `max_price`,`rental_type` |
| c5   | PASS | - |

断言规则（test-simulator/runner.py）：  
**实际上报的 `tool_results[].args` 的键必须全部落在用例 `tool_call_args.contains` 的键集合内**，多出未在 contains 中声明的参数即判为软失败（黄灯）。

当前实现里，`update_preferences` 的**上报参数**使用的是 **session 全量偏好**（`_session_prefs_to_reported_args(session_prefs)`），而不是「本轮真正传给工具的入参」。Session 会包含内部推导出的字段（如 `min_price`/`max_price`、`rental_type`、`near_subway` 等），导致与用例中「仅包含用户表达对应的字段」的 contains 不一致。

---

## 二、根因归纳

1. **上报来源错误**  
   用 session 全量作为上报的 args，会带上：
   - `min_price`/`max_price`（由 `price_around` 在 tools 内展开）
   - `rental_type`（若 session 中有默认或历史值）
   - `near_subway`（在 `_session_prefs_to_reported_args` 里根据 `max_subway_dist` 反推写入）

2. **语义与用例不一致**  
   - 用例 c2/c3 等期望「预算 N 左右」只体现为 **`price_around`**，不期望出现 `min_price`/`max_price`。  
   - 用例 c2 期望「近地铁」体现为 **`max_subway_dist` + `sort_by` + `sort_order`**，不期望出现 **`near_subway`**。  
   - 未提及整租/合租时，用例不期望出现 **`rental_type`**。

3. **多轮合并**  
   多轮时，测试会把每一轮上报的 `update_preferences` 的 args 合并成「累积实际」与「累积期望」做对比。若某一轮上报了 session 全量，就会把未在当轮/历史 contains 中的键（如 `rental_type`、`min_price`/`max_price`）带进去，导致多轮也失败。

---

## 三、修改方案（不改用例，只改 Agent 侧）

### 方案 A：改为「按本轮真实调用参数上报」并做规范化（推荐）

**思路**：  
`update_preferences` 的上报 args 改为**本轮实际传入的 `final_args`**（即经过 model args + rule 提取 + 软意图合并后的入参），并对这份入参做「与用例 contains 语义一致」的规范化，再写入 `tool_results[].args`。这样单轮/多轮合并后都只包含「用户表达对应的键」，且与 contains 一致。

**1. Agent（agent.py）**

- **上报来源**  
  - 在 `tool_name == "update_preferences"` 分支中，不再使用 `reported_args = _session_prefs_to_reported_args(session_prefs)`。  
  - 改为使用本轮调用时的 **`final_args`**（即传入 `update_preferences(client, session_prefs=session_prefs, **final_args)` 的参数字典）。

- **规范化再上报**（对 `final_args` 的副本做处理，不改变真正传入工具的 `final_args`）：  
  - **price_around 与 min/max 互斥**  
    - 若 `final_args` 中存在 `price_around`，则在上报副本中**删除** `min_price`、`max_price`，只保留 `price_around`。  
    - 若 `final_args` 中存在 `area_around`，则在上报副本中**删除** `min_area`、`max_area`，只保留 `area_around`。  
  - **near_subway → max_subway_dist + sort**  
    - 若 `final_args` 中存在 `near_subway`（且为 True），则在上报副本中：  
      - **删除** `near_subway`；  
      - **添加** `max_subway_dist: 800`、`sort_by: "subway"`、`sort_order: "asc"`（与 tools 内近地铁语义一致）。  
  - **不新增键**  
    - 仅对上述两种情况做替换/删除，不要从 session 或其它地方再补任何未在 `final_args` 中的键。

- **实现要点**  
  - 在调用 `update_preferences(..., **final_args)` 之后，用 `final_args` 的拷贝做上述规范化，得到 `reported_args`。  
  - 后续 `log_event("TOOL_CALL", ...)`、`log_event("TOOL_RESPONSE", ...)` 以及 `tool_results_log.append({"tool_name": "update_preferences", "args": reported_args, ...})` 均使用该 `reported_args`。

**2. 模型与规则侧（保证 final_args 本身不夹带多余键）**

- **Prompt（SYSTEM_PROMPT）**  
  - 明确写清：用户说「N 左右」时**只传 `price_around`**，不要传 `min_price`/`max_price`。  
  - 明确写清：用户**未提**整租/合租时，**不要传 `rental_type`**。  
  - 可选：在 `update_preferences` 的 description 中再强调一遍「仅传用户本轮提到的偏好字段，未提及的字段不传」。

- **规则提取（tools.extract_preferences_by_rules）**  
  - 确认不会在用户未提及整租/合租时写入 `rental_type`。  
  - 若存在默认或历史写入 `rental_type` 的逻辑，应去掉或改为仅当用户明确提到时才写入。

**3. 不修改的部分**

- **tools.update_preferences**  
  - 内部仍可根据 `price_around` 设置 `session_prefs.min_price`/`max_price` 用于搜索，无需改动。  
  - 仅「上报给测试」的 args 使用规范化后的 `final_args`，与内部 session 状态解耦。

- **test-simulator / 用例**  
  - 用例与断言规则保持不变。

---

### 方案 B：仅改「session 转上报」的归一化逻辑（备选）

若暂时不改为按 `final_args` 上报，可仅在 **`_session_prefs_to_reported_args`** 中做更严格的「与 contains 一致」的归一化：

- 当存在 `min_price`/`max_price` 且可视为由 `price_around` 推导时（例如成对出现且比例约 0.8/1.2），则**只输出 `price_around`**，不输出 `min_price`、`max_price`。  
- **不要**在已有 `max_subway_dist` 时再写入 `near_subway`（删除当前 `_session_prefs_to_reported_args` 中根据 `max_subway_dist` 设置 `out["near_subway"] = True` 的逻辑），并保证 `sort_by`/`sort_order` 在 session 中有正确设置且一并输出。  
- 对 `rental_type`：若没有可靠方式从 session 判断「是否用户本轮/本轮前明确提到」，则难以仅靠 session 做过滤；更稳妥仍是改为按 `final_args` 上报（方案 A）。

方案 B 无法解决「session 中带有用户未提及的 `rental_type` 等」的问题，且多轮时 session 会累积更多键，与用例「每轮只关心本轮/累积期望的 contains」仍易不一致，故**优先推荐方案 A**。

---

## 四、用例与期望对照（便于实现时自检）

| 用例 | 轮次 | 期望 contains 关键键（不全列） | 当前多出的键 |
|------|------|--------------------------------|--------------|
| c2   | 1    | location, bedrooms, max_price, **max_subway_dist**, sort_by, sort_order, decoration, decoration_is_soft | near_subway |
| c2   | 2    | pet_policy, required_nearby                                    | near_subway |
| c2   | 3    | viewing_method                                                 | near_subway |
| c3   | 1    | location, bedrooms, decoration, **price_around**               | min_price, max_price |
| c3   | 2    | 上轮 + payment_method, no_agent_fee, no_agent_fee_is_soft      | min_price, max_price, rental_type |
| c4   | Final| location, bedrooms, decoration, sort_by, sort_order, lease_flexibility | max_price, rental_type |
| c5   | -    | 含 max_price, decoration 等                                   | 无（已通过） |

实现时确保：  
- c2 各轮上报中「近地铁」以 **max_subway_dist + sort_by + sort_order** 出现，且**不**出现 `near_subway`。  
- c3/c4 上报中若用户表达的是「预算 N 左右」，只出现 **price_around**，不出现 `min_price`/`max_price`。  
- 用户未提整租/合租时，上报中**不**出现 `rental_type`。

---

## 五、小结

- **核心**：`update_preferences` 的断言看的是「上报的 args 的键集合 ⊆ 用例 contains 的键集合」。  
- **做法**：改为用**本轮真实调用参数 `final_args`** 做上报，并对 `final_args` 做**规范化**（price_around 与 min/max 互斥、near_subway 转为 max_subway_dist + sort_by + sort_order、不引入 session 中用户未提及的键）。  
- **配合**：Prompt 与规则提取保证不传 `rental_type`/min_max 等用户未提及字段。  

按上述方案修改 Agent 后，无需改测试用例或 test-simulator 断言逻辑，即可使 c2、c3、c4 的 tool_call_args 断言通过。
