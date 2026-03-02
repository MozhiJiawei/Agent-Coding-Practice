# E2E 测试修改建议文档

**生成时间**: 2026-03-02  
**测试执行**: `run_e2e.ps1`（端口 8900–8903）  
**测试结果**: 35 个用例中，约 27 个通过，8 个失败

---

## 一、测试执行摘要

| 项目 | 说明 |
|------|------|
| git pull | 已执行，代码已是最新 |
| 运行端口 | ModelProxy=8900, MockRental=8901, Dashboard=8902, Agent=8903 |
| 失败用例 | ev12, ev07, multi_progressive, ev19, ev26, ev24, ev32, ev30 |

---

## 二、成功用例的 expect 增强建议

基于 logs 中的交互结果，对通过用例补充断言，提升回归能力：

### 1. ev01 / chat_hello

- **当前 expect**: has_response, response_not_empty, status_success, no_tool_call
- **建议新增**:
  - `response_contains_keywords`: 可验证回复中是否含「租房」「北京」「需求」等关键词，避免空话回复

### 2. ev02（你好，你可以做什么）

- **当前 expect**: has_response, response_not_empty, status_success, no_tool_call
- **建议新增**:
  - `response_contains_keywords`: 含「租房」「帮助」「区域」「预算」等能力描述词

### 3. single_haidian_2br

- **当前 expect**: 含 tool_call_args、houses_match_subset、house_count_min
- **建议新增**:
  - `houses_match`: 显式断言 `["HF_33"]` 或其等价子集（当前已有 subset）
  - `tool_call_args` 中增加 `search_by_preferences` 调用检查

### 4. ev08（朝阳区房子）

- **当前 expect**: tool_call_args(update_preferences), houses_match_subset, houses_match: ["HF_2"]
- **建议新增**:
  - `house_count_min: 1` 或 `houses_match_subset: true`（若尚未覆盖）
  - `tool_call_args` 中检查是否调用了 `search_by_preferences`

### 5. ev13（朝阳区两居室 → 预算放宽 → HF_67 租房）

- **建议新增**:
  - Round 2：`tool_call_args` 中 `update_preferences` 包含 `max_price: 8000`
  - Round 3：`tool_call_args` 中 `get_house_detail` 包含 `house_id: "HF_67"` 以及后续 `execute_action`（若执行租房）

### 6. ev06_wangjing_to_daxing_rental_flow

- **建议新增**:
  - Round 3：`tool_call_args` 中 `update_preferences` 含 `clear_location: true` 与 `location: ["大兴"]`
  - Round 4：`tool_call_args` 中 `get_house_detail` 含 `house_id: "HF_830"`
  - Round 5：`tool_call_args` 中 `execute_action` 含 `action: "rent"` 和 `house_id: "HF_830"`

### 7. ev09、ev10、ev11 等单轮搜索用例

- **建议新增**:
  - `house_count_min: 1` 或具体 `houses_match` 子集，避免仅检查工具调用而忽略房源内容

---

## 三、失败用例分析与修改建议

### 建议 1：ev12 — houses_match_subset 失败（缺失房源 ID）

**失败信息**: `[Round 1] houses_match_subset: missing IDs ['HF_3', 'HF_33', 'HF_37', 'HF_38', 'HF_55'] in []`

**原因**:
- Agent 只调用了 `update_preferences`，未调用 `search_by_preferences`
- 响应中 `houses` 为空，LLM 在文本中编造了 HF_102、HF_325 等不存在的 ID

**修改建议**:
- **Agent 侧**：在 `agent.py` 的 System Prompt 中强调：用户明确表达「找房」需求时，必须先 `update_preferences` 再 `search_by_preferences`，禁止在未调用 `search_by_preferences` 时虚构房源
- **可选**：若工具调用链为 update→search，可在格式守卫层检测到仅 update 无 search 时，自动触发 `search_by_preferences`

---

### 建议 2：ev07 — Round 1 不应有工具调用

**失败信息**: `[Round 1] no_tool_call: 期望无工具调用，实际调用了 ['update_preferences']`

**原因**:
- 用户首轮为吐槽：「唉，我现在的房子住得不太舒服，采光不好，房间也小」
- 期望：纯共情回复，不调工具
- 实际：Agent 将抱怨理解为偏好，调用 `update_preferences(orientation='朝南', min_area=80)`

**修改建议**:
- **Agent 侧**：在 System Prompt 中补充：只有用户明确表达「找房」「帮我找」等 actionable 意图时才调工具；单纯抱怨、吐槽当前住房时，只做共情回复，不调用 `update_preferences`
- **测试侧（备选）**：若业务上允许从抱怨中推断偏好，可改为允许 Round 1 调用工具，并校验 `orientation`、`min_area` 等参数合理性

---

### 建议 3：multi_progressive — Round 2 期望与业务不符

**失败信息**: `[Round 2] no_tool_call: 期望无工具调用，实际调用了 ['update_preferences', 'search_by_preferences']`

**原因**:
- Round 1：「我想租房子，有什么推荐吗？」→ 无工具，追问需求，符合预期
- Round 2：「海淀区有哪些两居室可以租？」→ 已给出区域和户型，属于明确搜索意图
- Agent 正确调用了 `update_preferences` + `search_by_preferences`，但用例期望 Round 2 仍为 `no_tool_call`

**修改建议**:
- **测试侧**：修改 `test_cases.yaml` 中 `multi_progressive` 的 Round 2 expect：
  - 删除 `no_tool_call: true`
  - 增加 `tool_call_args`，检查 `update_preferences`（含 `location: ["海淀"]`, `bedrooms: "2"`）和 `search_by_preferences` 调用
  - 可选增加 `houses_match_subset: true` 或 `house_count_min: 1`

---

### 建议 4：ev19 — Round 2 未调用 get_house_detail

**失败信息**: `[Round 2] tool_call_args: 工具 'get_house_detail' 未被调用（实际调用：[]）`

**原因**:
- Round 1 正确完成搜索，返回 HF_4、HF_6、HF_277、HF_805、HF_1069 等
- Round 2 用户问：「便宜那套离地铁多远？」— HF_6(2950)、HF_277/HF_805(1200) 等存在多套「便宜」房源
- Agent 基于上下文直接回答了 HF_277、HF_805 的地铁距离，并询问用户具体指哪一套，未调用 `get_house_detail`

**修改建议**:
- **Agent 侧**：当用户问「便宜那套」「第一套」等指代词时，优先按列表顺序（如第一套或最低价那套）调用 `get_house_detail` 获取详情再回答，减少歧义
- **测试侧（备选）**：若设计上允许「先澄清再查详情」，可将 Round 2 的 `get_house_detail` 改为可选，或增加「澄清式回复」的语义检查（如包含「HF_277」「HF_805」等）

---

### 建议 5：ev26、ev24 — status_success 为 error（502）

**失败信息**: `status_success: expected 'success', got 'error'`

**原因**:
- logs 显示：`Error code: 502 - {'error': 'LLM proxy unavailable: '}`
- 属于 Model Proxy 或上游 LLM 不可用导致的瞬时错误，非业务逻辑问题
- ev24、ev26 工具调用链（update_preferences、search_by_preferences 等）在 502 前均正常

**修改建议**:
- **系统侧**：为 Agent 增加 502 重试（如最多 2 次，带退避），并记录重试日志
- **测试侧**：重跑用例验证；若 502 频繁出现，可考虑降低并发或延长 ReadyTimeoutSec
- **不改用例 expect**：ev26、ev24 的 tool_call_args 和 houses 断言本身无需修改

---

### 建议 6：ev32 — decoration 期望「精装」实际为「精装修」

**失败信息**: `tool_call_args(update_preferences): decoration: 期望 '精装', 实际 '精装修'`

**原因**:
- 用户说「精装修」，LLM 原样传入 `decoration: "精装修"`
- Mock Rental / 工具 schema 期望值为「精装」

**修改建议**:
- **工具侧**：在 `tools.py` 的 `update_preferences` 中增加装修字段归一化，例如：
  ```python
  DECORATION_ALIAS = {"精装修": "精装", "简装修": "简装", "毛坯": "毛坯", "豪华": "豪华"}
  if decoration and decoration in DECORATION_ALIAS:
      decoration = DECORATION_ALIAS[decoration]
  ```
- **测试侧（备选）**：在 `tool_call_args` 的 contains 中接受 `decoration` 为 `"精装"` 或 `"精装修"`（若断言引擎支持多值）

---

### 建议 7：ev30 — Round 1 期望无工具调用

**失败信息**: `[Round 1] no_tool_call: 期望无工具调用，实际调用了 ['update_preferences', 'search_by_preferences']`

**原因**:
- 用户首轮：「我现在租的房子太吵了，睡眠质量很差」
- 期望：共情回复，不调工具
- 实际：Agent 主动理解为「想找安静的房子」，调用了工具

**修改建议**:
- **Agent 侧**：与 ev07 一致，区分「抱怨/吐槽」与「明确找房请求」。只有用户明确说「帮我找」「想换房」「推荐」等才调工具；单纯抱怨噪音、采光等时仅做共情
- **测试侧（备选）**：若产品允许主动推荐，可放宽 Round 1 的 no_tool_call 要求，改为检查工具参数合理性（如与「安静」相关）

---

## 四、修改优先级建议

| 优先级 | 建议编号 | 说明 |
|--------|----------|------|
| 高 | 1 | ev12 不调用 search_by_preferences 导致幻觉，影响核心找房流程 |
| 高 | 6 | ev32 decoration 归一化，改动小、收益高 |
| 高 | 3 | multi_progressive 用例期望与业务不符，应修正测试 |
| 中 | 2, 7 | ev07/ev30 共情 vs 工具调用边界，需统一产品策略 |
| 中 | 4 | ev19 指代消解与 get_house_detail 调用策略 |
| 低 | 5 | ev26/ev24 502 属环境问题，优先加重试与监控 |

---

## 五、快速实施检查清单

- [ ] 建议 1：在 agent System Prompt 中强调「找房必须 update + search」
- [ ] 建议 3：修改 multi_progressive 的 Round 2 expect
- [ ] 建议 6：在 tools.py 中增加 decoration 归一化（精装修→精装）
- [ ] 建议 2、7：在 System Prompt 中明确「抱怨/吐槽不调工具」的边界
- [ ] 建议 4：优化「便宜那套」等指代的处理逻辑
- [ ] 建议 5：为 Agent 增加 502 重试
- [ ] 按「二、成功用例的 expect 增强建议」逐步补充 expect
