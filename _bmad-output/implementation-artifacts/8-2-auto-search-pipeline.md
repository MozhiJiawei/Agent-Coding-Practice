# Story 8.2: 自动搜索流水线 + 规则过滤

**Epic:** 8 - 结构化用户偏好记忆系统  
**Status:** ready-for-dev  
**Priority:** P0  
**Depends on:** Story 8.1  
**Design Ref:** `_bmad-output/brainstorming/preference-memory-system-design.md`

---

## 一、目标

实现 `update_preferences` 调用后代码自动搜索的完整流水线：偏好 merge → 位置路由 → 构建 API 参数 → 调用搜索 API → 硬约束过滤 → 软偏好后过滤/排序 → 返回匹配房源。

核心变化：**搜索决策从 LLM 移交给代码，LLM 只负责偏好提取和自然语言表达**。

---

## 二、任务清单

### 2.1 实现偏好 → API 参数映射

**文件：** `tools.py`（或 `preferences.py`）

将 `UserPreferences` 中的硬约束字段映射为 `GET /api/houses/by_platform` 的查询参数：

| UserPreferences 字段 | API 参数 | 映射规则 |
|----------------------|----------|----------|
| `_district` | `district` | 逗号拼接，如 `"海淀,朝阳"` |
| `_area` | `area` | 逗号拼接 |
| `min_price` | `min_price` | 直接传递 |
| `max_price` | `max_price` | 直接传递 |
| `bedrooms` | `bedrooms` | 直接传递（已是 "2" 或 "2,3" 格式） |
| `rental_type` | `rental_type` | 直接传递 |
| `decoration` | `decoration` | 直接传递 |
| `elevator` | `elevator` | bool → "true"/"false" |
| `min_area` | `min_area` | 直接传递 |
| `max_area` | `max_area` | 直接传递 |
| `utilities_type` | `utilities_type` | 直接传递 |
| `subway_line` | `subway_line` | 直接传递 |
| `near_subway` | `max_subway_dist` | `true` → `800` |
| `listing_platform` | `listing_platform` | 直接传递，默认 "安居客" |
| `available_before` | `available_from_before` | 直接传递 |
| `max_commute_minutes` | `commute_to_xierqi_max` | 直接传递 |

```python
def build_search_params(prefs: UserPreferences) -> dict:
    """将偏好转换为 search_houses API 的查询参数"""
    params = {}
    if prefs._district:
        params["district"] = ",".join(prefs._district)
    if prefs._area:
        params["area"] = ",".join(prefs._area)
    if prefs.near_subway:
        params["max_subway_dist"] = 800
    # ... 其他字段映射
    return params
```

### 2.2 实现 Landmark 链式调用

**文件：** `tools.py`

当 `resolve_location` 返回 `landmark_query` 时，代码自动执行链式调用：

```python
async def search_by_landmark(client: httpx.AsyncClient, query: str, prefs: UserPreferences) -> dict:
    """
    1. search_landmark(q=query) → 获取 landmark_id
    2. search_nearby_landmark(landmark_id=..., 附加偏好参数) → 获取房源
    """
    landmark_result = await search_landmark(client, query=query)
    items = landmark_result.get("data", {}).get("items", [])
    if not items:
        return {"total": 0, "items": [], "error": f"未找到'{query}'相关地标"}

    landmark_id = items[0]["id"]
    nearby_params = {"landmark_id": landmark_id}
    if prefs.min_price:
        nearby_params["min_price"] = prefs.min_price
    if prefs.max_price:
        nearby_params["max_price"] = prefs.max_price
    if prefs.listing_platform:
        nearby_params["listing_platform"] = prefs.listing_platform

    return await search_nearby_landmark(client, **nearby_params)
```

### 2.3 实现软偏好后过滤

**文件：** `tools.py`（或 `preferences.py`）

对 API 返回的房源列表进行规则后过滤和评分排序：

```python
def post_filter_and_rank(items: list[dict], prefs: UserPreferences) -> list[dict]:
    """对搜索结果进行软偏好过滤和排序"""
    scored = []
    for item in items:
        score = 0
        matched = True

        # 噪音偏好（硬过滤）
        if prefs.noise_preference == "安静":
            if item.get("hidden_noise_level") in ("吵闹", "临街"):
                matched = False

        # 朝向偏好（加分）
        if prefs.orientation:
            target = prefs.orientation.replace("朝", "")
            if target in item.get("orientation", ""):
                score += 10

        # 楼层偏好（加分）
        if prefs.floor_pref:
            floor_str = item.get("floor", "")
            if prefs.floor_pref in floor_str:
                score += 5

        if matched:
            scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored]
```

### 2.4 串联完整搜索流水线

**文件：** `tools.py`

在 `update_preferences` 函数中，偏好 merge 完成后自动触发搜索：

```python
async def update_preferences(client: httpx.AsyncClient, session_prefs: UserPreferences, **kwargs) -> dict:
    # 1. 增量 merge 偏好
    merge_preferences(session_prefs, kwargs)

    # 2. 位置路由
    if kwargs.get("location"):
        for loc in kwargs["location"]:
            result = resolve_location(loc)
            # 写入 _district / _area / _landmark_query

    # 3. 根据路由结果选择搜索路径
    if session_prefs._landmark_query:
        raw_result = await search_by_landmark(client, session_prefs._landmark_query, session_prefs)
    else:
        params = build_search_params(session_prefs)
        raw_result = await search_houses(client, **params)

    # 4. 软偏好后过滤
    items = raw_result.get("items", [])
    # 如果是 nearby 接口返回，items 在 data 层
    if not items:
        data = raw_result.get("data", {})
        items = data.get("items", [])

    filtered = post_filter_and_rank(items, session_prefs)

    # 5. 截取 top 5
    top_items = filtered[:5]

    return {
        "total_matched": len(filtered),
        "total_raw": raw_result.get("total", len(items)),
        "items": top_items,
        "preferences_summary": summarize_preferences(session_prefs),
    }
```

### 2.5 更新 Agent 循环中的房源 ID 提取

**文件：** `agent.py`

当前 `HOUSE_SEARCH_TOOLS` 逻辑基于工具名触发 HF_ID 提取。改为：
- `update_preferences` 返回结果中直接包含 `items`，代码从 `items` 中提取 `house_id`
- 不再依赖 regex 从 LLM 回复文本中提取 HF_ID

```python
# 在工具调用结果处理中
if tool_name == "update_preferences":
    result_items = result.get("items", [])
    house_ids = [item["house_id"] for item in result_items if "house_id" in item]
    # 存入 session 上下文供后续使用
```

### 2.6 更新 SYSTEM_PROMPT

**文件：** `agent.py`

完善 prompt，指导 LLM 理解新的工作流：

```
核心工作流：
1. 用户表达租房需求 → 调用 update_preferences，系统自动搜索并返回匹配房源
2. 基于返回的房源结果，用自然语言向用户描述推荐房源
3. 用户想看详情 → get_house_detail
4. 用户想比价 → get_house_listings  
5. 用户要租房 → execute_action

重要规则：
- 不要自行搜索房源，所有搜索由 update_preferences 自动完成
- update_preferences 的返回结果中包含匹配的房源列表
- 每次只提取本轮新增/变更的偏好，不要重复已知偏好
- 回复中使用房源的 house_id（如 HF_87），系统会自动处理格式
```

---

## 三、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `tools.py` | 修改 | 实现 build_search_params、search_by_landmark、post_filter_and_rank；更新 update_preferences 函数增加自动搜索逻辑 |
| `agent.py` | 修改 | 更新 HF_ID 提取逻辑（从工具结果提取而非 LLM 文本）；优化 SYSTEM_PROMPT |
| `main.py` | 可能修改 | 如需传递更多上下文给 agent |

---

## 四、验收标准（AC）

### AC-1：硬约束搜索正确

用以下场景验证 API 参数构建：

| 场景 | 用户输入 | 期望 API 调用参数 |
|------|----------|-----------------|
| S1 | "找大兴区的两居室，租金4000以下" | `district=大兴, bedrooms=2, max_price=4000` |
| S2 | "找海淀区三居室，预算13000以内，精装修，近地铁" | `district=海淀, bedrooms=3, max_price=13000, decoration=精装, max_subway_dist=800` |
| S3 | "帮我找58同城上海淀区的房子" | `district=海淀, listing_platform=58同城` |

- [ ] S1 返回的房源全部满足 district=大兴, bedrooms=2, price≤4000
- [ ] S2 返回的房源全部满足 district=海淀, bedrooms=3, price≤13000, decoration=精装, subway_distance≤800
- [ ] S3 返回的房源全部来自 58同城平台

### AC-2：Landmark 链式调用正确

| 场景 | 用户输入 | 期望行为 |
|------|----------|----------|
| L1 | "国贸附近有什么房子" | 代码自动：search_landmark("国贸") → 获取 landmark_id → search_nearby_landmark |
| L2 | "望京的房子" | 路由为 area="望京" → 直接 search_houses，不走 landmark |

- [ ] L1 正确返回国贸（LM_002）附近的房源，不依赖 LLM 调用 search_landmark
- [ ] L2 正确路由为商圈查询，不走 landmark 路径

### AC-3：软偏好后过滤生效

- [ ] `noise_preference="安静"` 时，结果中不包含 `hidden_noise_level` 为"吵闹"/"临街"的房源
- [ ] `orientation="朝南"` 时，朝南房源排在结果前面
- [ ] 最终返回结果不超过 5 套

### AC-4：房源 ID 正确提取

- [ ] `update_preferences` 返回的 `items` 中包含 `house_id`
- [ ] Agent 最终响应的 `houses` 字段从工具结果中提取，不再依赖 regex 从 LLM 文本匹配
- [ ] 对比 EV-05 场景（"海淀区三居室精装近地铁"），新系统返回的 `houses` 不为空

### AC-5：多轮偏好累积正确

| 轮次 | 用户输入 | 累积偏好状态 | 搜索范围 |
|------|----------|-------------|----------|
| 1 | "找海淀区的两居室" | `district=海淀, bedrooms=2` | 海淀两居 |
| 2 | "预算8000以内" | `district=海淀, bedrooms=2, max_price=8000` | 海淀两居 ≤8000 |
| 3 | "换大兴区看看" | `district=大兴, bedrooms=2, max_price=8000` | 大兴两居 ≤8000 |

- [ ] 第 2 轮搜索结果是海淀 + 两居 + ≤8000 的交集
- [ ] 第 3 轮 `clear_location=true` 后位置从海淀切换为大兴，其他偏好保留

### AC-6：端到端 Eval 用例验证

使用以下现有 eval 用例验证完整流程：

| 用例 | 预期表现 |
|------|----------|
| EV-03（大兴两居4000以下） | 返回正确房源 + houses 非空 |
| EV-05（海淀三居精装近地铁13000以内） | 返回正确房源 + houses 非空（修复原有 houses 为空的问题） |
| EV-17（58同城海淀） | 返回正确房源 + houses 非空 |

- [ ] 上述 3 个 eval 用例的 `houses` 字段均非空
- [ ] 返回的房源符合用户偏好约束

---

## 五、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| search_houses 内部函数被 update_preferences 调用，但不再暴露给 LLM | 保留 search_houses 函数实现，仅从 TOOLS 和 TOOL_DISPATCH 中移除 |
| landmark 搜索无结果（如 EV-07 中"西二旗"搜不到） | resolve_location 优先匹配为 area，只有真正的非区名/非商圈名才走 landmark |
| API 返回数据量大导致 token 爆炸 | update_preferences 只返回 top 5 给 LLM，大幅减少 token |
| near_subway 过滤过于严格导致无结果 | 如果 subway_dist≤800 无结果，自动放宽到 1500 并提示用户 |

---

## 六、注意事项

1. `search_houses`、`search_landmark`、`search_nearby_landmark` 的函数实现保留在 `tools.py` 中供代码内部调用，但不出现在 `TOOLS` 和 `TOOL_DISPATCH` 中
2. `update_preferences` 返回给 LLM 的 items 应只包含关键字段（house_id, community, district, price, bedrooms, area_sqm, decoration, subway_station, subway_distance），减少 token 消耗
3. 位置路由逻辑必须健壮：边界情况如"海淀区"→"海淀"、"国贸附近"→"国贸"、"西二旗"→area 而非 landmark
