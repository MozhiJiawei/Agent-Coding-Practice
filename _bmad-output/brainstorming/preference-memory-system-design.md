# 结构化用户偏好记忆系统设计

**Date:** 2026-03-02

---

## 一、工具精简方案

### 移除的工具（4个）

| 工具 | 移除理由 |
|---|---|
| `search_houses` | 改由代码根据偏好自动调用，避免 LLM 错传/漏传参数 |
| `search_landmark` + `search_nearby_landmark` | 两步链式调用 LLM 处理不好（EV-07 中 LLM 幻觉搜索"西二旗"导致完全偏离），改由代码在检测到地标关键词时自动链式调用 |
| `get_nearby_amenities` | 测试用例极少涉及，可在展示详情时由代码自动附加 |
| `get_houses_by_community` | 指代消解（"这个小区"）由代码基于上下文记忆处理 |

### 保留的工具（3个）

| 工具 | 保留理由 |
|---|---|
| `get_house_detail` | LLM 需判断何时查看详情，结果量小 token 可控 |
| `get_house_listings` | ev18、ev22 明确要求跨平台比价 |
| `execute_action` | 租房/退租是用户明确意图 |

### 新增的工具（1个）

| 工具 | 用途 |
|---|---|
| `update_preferences` | 提取/更新结构化偏好，调用后代码自动搜索并返回匹配房源 |

### 精简结果：8 个 → 4 个

---

## 二、结构化用户偏好数据结构

LLM 侧使用统一的 `location` 字段输入位置信息，代码通过 `resolve_location` 路由后写入内部的 `_district` / `_area` / `_landmark_query`。

```python
class UserPreferences(BaseModel):
    # ── 位置（LLM 输入统一字段，代码路由后拆分为内部字段） ──
    location: Optional[list[str]] = None        # LLM 输入，如 ["望京"]、["海淀"]、["国贸附近"]
    clear_location: bool = False                # true=清除历史位置（"换XX看看"场景）
    _district: Optional[list[str]] = None       # 内部字段，resolve_location 写入
    _area: Optional[list[str]] = None           # 内部字段，resolve_location 写入
    _landmark_query: Optional[str] = None       # 内部字段，走 landmark 搜索路径时写入

    # ── 硬约束 (直接映射API参数，规则过滤) ──
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[str] = None              # "2" 或 "2,3"
    rental_type: Optional[str] = None           # "整租" / "合租"
    decoration: Optional[str] = None            # "精装" / "简装" / "豪华"
    elevator: Optional[bool] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    utilities_type: Optional[str] = None        # "民水民电"
    subway_line: Optional[str] = None           # "13号线"
    near_subway: Optional[bool] = None          # true → max_subway_dist=800
    listing_platform: Optional[str] = None      # "链家" / "安居客" / "58同城"
    available_before: Optional[str] = None      # "2026-03-31"
    max_commute_minutes: Optional[int] = None   # 到西二旗通勤上限（分钟）

    # ── 软偏好 (后过滤/评分，规则过滤) ──
    noise_preference: Optional[str] = None      # "安静"
    orientation: Optional[str] = None           # "朝南"
    floor_pref: Optional[str] = None            # "低层" / "中层" / "高层"
    no_agent_fee: Optional[bool] = None
    payment_method: Optional[str] = None        # "押一付一"

    # ── 上下文记忆 ──
    mentioned_house_ids: list[str] = []         # 对话中提到过的房源ID
    current_focus_house_id: Optional[str] = None  # 当前讨论焦点
```

### location 路由逻辑

代码在收到 LLM 的 `location` 后，自动拆分为 API 可用的参数：

```python
DISTRICTS = {"海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"}

# 从 init_houses 全量数据自动构建
AREA_TO_DISTRICT = build_area_district_map(all_houses)

def resolve_location(location: str) -> dict:
    loc = location.replace("区", "").replace("附近", "").replace("周边", "").strip()
    if loc in DISTRICTS:
        return {"district": loc}
    if loc in AREA_TO_DISTRICT:
        return {"area": loc, "district": AREA_TO_DISTRICT[loc]}
    return {"landmark_query": loc}  # 走 search_landmark → search_nearby_landmark
```

| 用户说的 | location 输入 | 路由结果 |
|---|---|---|
| "海淀区" | `["海淀"]` | `{district: "海淀"}` |
| "望京" | `["望京"]` | `{area: "望京", district: "朝阳"}` |
| "国贸附近" | `["国贸附近"]` | `{landmark_query: "国贸"}` → 自动链式调用 landmark API |
| "西二旗" | `["西二旗"]` | `{area: "西二旗", district: "海淀"}` |

---

## 三、过滤分层：规则 vs LLM辅助

### 规则过滤（代码确定性执行）

| 偏好字段 | 用户表达 → 规则映射 |
|---|---|
| location | "海淀区"/"望京"/"国贸附近" → 代码路由为 district/area/landmark（见上文） |
| price | "预算8000以内" → `max_price=8000` |
| bedrooms | "两居室" → `bedrooms="2"` |
| rental_type | "整租" → `rental_type="整租"` |
| decoration | "精装修" → `decoration="精装"` |
| elevator | "有电梯" → `elevator=true` |
| min_area_sqm | "60平以上" → `min_area=60` |
| utilities_type | "民水民电" → `utilities_type="民水民电"` |
| near_subway | "近地铁" → `near_subway=true` → 代码翻译为 `max_subway_dist=800` |
| subway_line | "13号线沿线" → `subway_line="13号线"` |
| listing_platform | "58同城" → `listing_platform="58同城"` |
| available_before | "3月可入住" → `available_before="2026-03-31"` |
| max_commute_minutes | "通勤30分钟以内" → `max_commute_minutes=30` |
| noise_preference | "安静/不要临街" → 后过滤 `hidden_noise_level=="安静"` |
| orientation | "采光好/朝南" → 后过滤 `orientation` 含"南" |

### LLM 辅助（必须由大模型理解）

| 场景 | 示例 | 原因 |
|---|---|---|
| 情绪→需求转换 | "住得不太舒服，采光不好，房间也小" → noise_preference=安静, orientation=朝南, min_area_sqm增大 | 需推理隐含偏好 |
| 指代消解 | "这套"、"最开始望京那套"、"便宜那套" | 需从对话历史定位具体房源 |
| 偏好强度判断 | "有电梯更好"（软偏好） vs "必须有电梯"（硬约束） | 需语义理解 |
| 变更检测 | "预算放宽到8000"、"换大兴区看看"（需设 clear_location=true） | 需理解是修改而非追加 |
| 意图分类 | "这套可以租吗" → 询问 or 执行? | 需判断用户真实意图 |

---

## 四、update_preferences 工具定义

LLM 通过此工具输出结构化偏好，字段与 `UserPreferences` 的 LLM 可写字段一一对应：

```python
{
    "name": "update_preferences",
    "description": "提取或更新用户的租房偏好。调用后系统自动搜索并返回匹配房源。每轮只需提取本轮新增/变更的偏好，系统自动与历史偏好合并。",
    "parameters": {
        "properties": {
            "location": {"type": "array", "items": {"type": "string"},
                         "description": "用户提到的位置（行政区/商圈/地标均可），如 ['望京']、['海淀']、['国贸附近']"},
            "clear_location": {"type": "boolean",
                               "description": "true=清除之前的位置偏好（用于'换XX看看'场景）"},
            "min_price": {"type": "integer"},
            "max_price": {"type": "integer"},
            "bedrooms": {"type": "string", "description": "卧室数，如 '2' 或 '2,3'"},
            "rental_type": {"type": "string", "description": "整租 或 合租"},
            "decoration": {"type": "string"},
            "elevator": {"type": "boolean"},
            "min_area_sqm": {"type": "integer"},
            "near_subway": {"type": "boolean", "description": "是否近地铁"},
            "subway_line": {"type": "string"},
            "utilities_type": {"type": "string"},
            "listing_platform": {"type": "string"},
            "available_before": {"type": "string"},
            "max_commute_minutes": {"type": "integer"},
            "noise_preference": {"type": "string"},
            "orientation": {"type": "string"}
        },
        "required": []
    }
}
```

---

## 五、工作流

```
用户消息
    │
    ▼
┌──────────────────────────┐
│ LLM: 意图分类 + 偏好提取  │  ← 调用 update_preferences
│ 输出: 结构化偏好 JSON      │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ 代码: 合并到 session 偏好  │  ← 增量 merge，不丢历史
│ + location 路由分类        │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ 代码: 规则过滤             │  ← 硬约束→API参数
│ - 构建 API 调用参数        │     软偏好→结果后过滤
│ - 执行 API                │     结果缓存到 session
│ - 后过滤 + 排序            │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ LLM: 生成自然语言回复      │  ← 基于过滤后结果
│ （只负责表达，不负责筛选）   │     token 大幅减少
└──────────────────────────┘
```

---

## 六、已知 Bug 修复清单

| Bug | 受影响用例 | 修复方案 |
|---|---|---|
| `houses` 列表返回空数组（regex 从 LLM 文本提取 HF_ID 失败） | EV-05, EV-17 | HF_ID 直接从 API 结果中提取，不依赖 LLM 文本 |
| LLM 幻觉性工具调用（搜索用户未提及的地标） | EV-07 | 移除 search_landmark 直接暴露，改由代码路由 |
| LLM 租了错误的房源（HF_1 是房山一居室，用户要两居室4000以内） | EV-07 | execute_action 前增加代码校验：房源是否匹配当前偏好 |
| 多轮对话偏好丢失 | EV-06 类 | UserPreferences 跨轮次持久化 |

---

Last Updated: 2026-03-02
