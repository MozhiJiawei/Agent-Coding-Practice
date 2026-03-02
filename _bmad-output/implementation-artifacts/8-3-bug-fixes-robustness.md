# Story 8.3: Bug 修复 + 健壮性增强

**Epic:** 8 - 结构化用户偏好记忆系统  
**Status:** ready-for-dev  
**Priority:** P1  
**Depends on:** Story 8.2  
**Design Ref:** `_bmad-output/brainstorming/preference-memory-system-design.md` 第六章

---

## 一、目标

修复设计文档中列出的 4 个已知 Bug，增强系统的健壮性和上下文记忆能力。重点解决：

1. HF_ID 提取依赖 LLM 文本导致 `houses` 为空
2. LLM 幻觉性工具调用（搜索用户未提及的地标）
3. execute_action 前无校验导致租错房
4. 多轮对话偏好丢失

---

## 二、已知 Bug 与修复方案

### Bug 1: `houses` 列表返回空数组

**受影响用例：** EV-05, EV-17

**根因分析：**
当前 `agent.py` 第 198 行使用 `re.findall(r'HF_\d+', content)` 从 LLM 回复文本中提取房源 ID。但 LLM 不一定在回复文本中使用 `HF_xxx` 格式引用房源（可能用"银座家园"等小区名），导致 regex 匹配为空。

**当前代码：**
```python
# agent.py 第 197-208 行
if tools_called & HOUSE_SEARCH_TOOLS:
    raw_ids = re.findall(r'HF_\d+', content)  # ← 依赖 LLM 文本
    seen: set[str] = set()
    houses: list[str] = []
    for hid in raw_ids:
        if hid not in seen and len(houses) < 5:
            seen.add(hid)
            houses.append(hid)
```

**修复方案：**
从工具返回结果（API 数据）中直接提取 `house_id`，不依赖 LLM 文本。

```python
# 修复后
if "update_preferences" in tools_called:
    # 从 update_preferences 返回的 items 中提取
    houses = collected_house_ids[:5]
elif tools_called & HOUSE_SEARCH_TOOLS:
    # 兼容旧路径（如有）
    houses = collected_house_ids[:5]
```

实现方式：在工具调用循环中，当 `tool_name == "update_preferences"`，解析 result 中的 `items`，收集所有 `house_id` 到 `collected_house_ids` 列表。

### Bug 2: LLM 幻觉性工具调用

**受影响用例：** EV-07

**根因分析：**
EV-07 中用户说"采光不好，房间也小"→"通勤时间太长"→"想换个房子"→"两居室，4000以内，精装修"。LLM 在第 4 轮幻觉搜索"西二旗"地标（用户从未提到西二旗），且搜索结果为空导致后续流程异常。

**修复方案（已在 Story 8.1/8.2 中覆盖）：**
- `search_landmark` 不再暴露给 LLM
- 位置路由由代码通过 `resolve_location` 自动处理
- LLM 只通过 `update_preferences` 的 `location` 字段传递位置

**本 Story 补充验证：**
- [ ] 用 EV-07 的完整多轮场景验证，确认不再出现幻觉地标搜索
- [ ] 确认 LLM 在用户未提供位置时不会凭空生成 location

### Bug 3: execute_action 前无校验，租错房源

**受影响用例：** EV-07

**根因分析：**
EV-07 中 LLM 租了 HF_1（房山一居室 2250 元），但用户明确要求"两居室，4000以内"。HF_1 是一居室，完全不匹配偏好。LLM 可能因为上下文混乱，误将 HF_1 作为推荐房源执行了 rent 操作。

**修复方案：**
在 `execute_action` 调用前，代码校验待操作房源是否匹配当前偏好。

```python
async def validate_before_action(
    client: httpx.AsyncClient,
    house_id: str,
    prefs: UserPreferences,
    action: str
) -> tuple[bool, str]:
    """校验房源是否匹配当前偏好，返回 (is_valid, reason)"""
    if action != "rent":
        return True, ""

    detail = await get_house_detail(client, house_id=house_id)
    house = detail.get("data", detail)
    if "error" in detail:
        return False, f"无法获取房源 {house_id} 的详情"

    warnings = []

    # 户型校验
    if prefs.bedrooms:
        required_bedrooms = [int(b) for b in prefs.bedrooms.split(",")]
        if house.get("bedrooms") not in required_bedrooms:
            warnings.append(
                f"户型不匹配：用户要求{prefs.bedrooms}居室，该房源是{house.get('bedrooms')}居室"
            )

    # 价格校验
    if prefs.max_price and house.get("price", 0) > prefs.max_price:
        warnings.append(
            f"价格超出预算：用户预算{prefs.max_price}元，该房源{house.get('price')}元"
        )

    # 区域校验
    if prefs._district and house.get("district") not in prefs._district:
        warnings.append(
            f"区域不匹配：用户要求{prefs._district}，该房源在{house.get('district')}"
        )

    if warnings:
        return False, "；".join(warnings)
    return True, ""
```

**集成方式：**

在 `agent.py` 的工具调用分发处，拦截 `execute_action`：

```python
if tool_name == "execute_action" and args.get("action") == "rent":
    is_valid, reason = await validate_before_action(
        client, args.get("house_id", ""), session_prefs, "rent"
    )
    if not is_valid:
        result = {
            "error": f"操作被拦截：{reason}",
            "suggestion": "请确认您要租的房源是否正确，或重新搜索符合条件的房源"
        }
        # 不执行实际 rent 操作，将校验结果返回给 LLM
    else:
        result = await execute_action(client, **args)
```

### Bug 4: 多轮对话偏好丢失

**修复方案（已在 Story 8.1 中覆盖）：**
`UserPreferences` 对象持久化在 `session_preferences` 中，跨轮次保持。

**本 Story 补充验证：**
- [ ] 构造 5+ 轮对话场景，验证第 5 轮时第 1 轮的偏好仍然生效
- [ ] 验证 `clear_location=true` 只清除位置，不影响其他偏好

---

## 三、上下文记忆增强

### 3.1 mentioned_house_ids 追踪

在工具调用结果中出现的房源 ID，自动记录到 `UserPreferences.mentioned_house_ids`：

```python
def track_mentioned_houses(prefs: UserPreferences, items: list[dict]):
    """将搜索结果中的房源 ID 加入记忆"""
    for item in items:
        hid = item.get("house_id", "")
        if hid and hid not in prefs.mentioned_house_ids:
            prefs.mentioned_house_ids.append(hid)
```

### 3.2 current_focus_house_id 更新

当 LLM 调用 `get_house_detail` 时，自动更新焦点房源：

```python
if tool_name == "get_house_detail":
    session_prefs.current_focus_house_id = args.get("house_id")
```

当 LLM 调用 `execute_action` 时，如果未指定 house_id 但 session 中有 `current_focus_house_id`，可作为默认值（但仍需 LLM 显式指定，此处仅作为日志辅助）。

### 3.3 Token 优化：精简返回字段

`update_preferences` 返回给 LLM 的房源信息只包含关键字段，减少 token 消耗：

```python
HOUSE_SUMMARY_FIELDS = [
    "house_id", "community", "district", "area", "bedrooms",
    "area_sqm", "price", "decoration", "orientation",
    "subway_station", "subway_distance", "commute_to_xierqi",
    "rental_type", "elevator", "listing_platform", "tags",
]

def summarize_house(house: dict) -> dict:
    """精简房源信息，只保留关键字段"""
    return {k: house[k] for k in HOUSE_SUMMARY_FIELDS if k in house}
```

---

## 四、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `agent.py` | 修改 | HF_ID 从工具结果提取；execute_action 前置校验；焦点房源追踪 |
| `tools.py` | 修改 | validate_before_action 函数；mentioned_house_ids 追踪；房源摘要精简 |
| `main.py` | 可能修改 | 如需传递偏好给校验逻辑 |

---

## 五、验收标准（AC）

### AC-1：HF_ID 提取修复

- [ ] EV-05 场景（"海淀区三居室精装近地铁"）：返回的 `houses` 包含正确的 HF_ID 列表（非空）
- [ ] EV-17 场景（"58同城海淀区"）：返回的 `houses` 包含正确的 HF_ID 列表（非空）
- [ ] HF_ID 来源于工具返回结果，不依赖 LLM 文本 regex

### AC-2：幻觉调用防护

- [ ] EV-07 完整场景重放：
  - 第 1-3 轮（闲聊+抱怨）：LLM 不调用工具或只做追问
  - 第 4 轮（"两居室，4000以内，精装"）：LLM 调用 update_preferences，不出现幻觉地标搜索
  - 搜索结果来自合理区域（不会搜到房山的 HF_1）

### AC-3：execute_action 前置校验

- [ ] 当 LLM 尝试租不匹配偏好的房源时，代码拦截并返回错误提示
- [ ] 测试场景：偏好为"两居室4000以内"，尝试租一居室的 HF_1 → 被拦截
- [ ] 校验通过时，正常执行 rent 操作
- [ ] terminate 和 offline 操作不受校验影响（只校验 rent）

### AC-4：上下文记忆

- [ ] `mentioned_house_ids` 正确累积：每次搜索结果中的 ID 都被记录
- [ ] `current_focus_house_id` 在调用 get_house_detail 后正确更新
- [ ] 偏好跨轮次持久化验证通过（5 轮对话场景）

### AC-5：Token 优化

- [ ] `update_preferences` 返回的房源信息只包含关键字段（不含 longitude/latitude/listing_url 等冗余字段）
- [ ] 对比优化前后，单次 LLM 调用的 total_tokens 下降（目标减少 30%+）

### AC-6：全量 Eval 回归

对照以下 eval 用例进行端到端回归测试：

| 用例 | 类型 | 核心验证 |
|------|------|----------|
| EV-01~02 | 聊天类 | 纯聊天不触发工具调用 |
| EV-03 | 单轮简单 | 大兴两居4000以下 → houses 非空 |
| EV-05 | 单轮复杂 | 海淀三居精装近地铁13000以内 → houses 非空 |
| EV-07 | 多轮复杂 | 情绪→需求→搜索→租房，无幻觉调用 |
| EV-17 | 单轮指定平台 | 58同城海淀 → houses 非空 |

- [ ] 所有上述用例通过
- [ ] 无新增的回归问题

---

## 六、注意事项

1. **execute_action 校验不应过于严格**：只校验明显不匹配（户型、价格超出）的情况。如果用户偏好中没有设置某个约束，则不校验该维度
2. **validate_before_action 需要额外一次 API 调用**（get_house_detail），注意对时间片的影响。如果 session 中已有该房源的缓存数据，优先使用缓存
3. **mentioned_house_ids 不宜无限增长**：设置上限（如最多 50 个），超出后 FIFO 淘汰最早的
4. **EV-07 是最复杂的回归用例**：涉及情绪理解、多轮累积、租房操作，是系统综合能力的试金石
