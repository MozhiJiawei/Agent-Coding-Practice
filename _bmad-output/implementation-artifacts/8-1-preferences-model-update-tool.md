# Story 8.1: UserPreferences 数据模型 + update_preferences 工具 + LLM 提参验证

**Epic:** 8 - 结构化用户偏好记忆系统  
**Status:** ready-for-dev  
**Priority:** P0  
**Design Ref:** `_bmad-output/brainstorming/preference-memory-system-design.md`

---

## 一、目标

替换现有 8 个 LLM 暴露工具为新的 4 个工具体系（update_preferences + get_house_detail + get_house_listings + execute_action），建立 `UserPreferences` 数据模型和 `update_preferences` 工具，使 LLM 通过结构化方式提取用户偏好。

本 Story 的核心验证目标：**确认当前使用的 qwen3-32b 模型能正确理解 `update_preferences` 工具的 schema 并准确提取参数**。

---

## 二、任务清单

### 2.1 定义 UserPreferences 数据模型

**文件：** `tools.py`（或新建 `preferences.py`）

```python
class UserPreferences(BaseModel):
    # ── 位置（LLM 输入统一字段） ──
    location: Optional[list[str]] = None
    clear_location: bool = False

    # ── 内部字段（代码路由后写入，LLM 不直接设置） ──
    _district: Optional[list[str]] = None
    _area: Optional[list[str]] = None
    _landmark_query: Optional[str] = None

    # ── 硬约束 ──
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[str] = None
    rental_type: Optional[str] = None
    decoration: Optional[str] = None
    elevator: Optional[bool] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    utilities_type: Optional[str] = None
    subway_line: Optional[str] = None
    near_subway: Optional[bool] = None
    listing_platform: Optional[str] = None
    available_before: Optional[str] = None
    max_commute_minutes: Optional[int] = None

    # ── 软偏好 ──
    noise_preference: Optional[str] = None
    orientation: Optional[str] = None
    floor_pref: Optional[str] = None
    no_agent_fee: Optional[bool] = None
    payment_method: Optional[str] = None

    # ── 上下文记忆 ──
    mentioned_house_ids: list[str] = []
    current_focus_house_id: Optional[str] = None
```

### 2.2 实现 resolve_location 位置路由

**文件：** `tools.py`（或 `preferences.py`）

从 `init_houses` 全量数据中自动构建 `AREA_TO_DISTRICT` 映射表。

```python
DISTRICTS = {"海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"}

def build_area_district_map(all_houses: list[dict]) -> dict[str, str]:
    """从全量房源数据中构建 area → district 映射表"""
    ...

def resolve_location(location: str) -> dict:
    """将 LLM 输入的位置路由为 district / area / landmark_query"""
    ...
```

路由规则：
| 输入 | 路由结果 |
|------|----------|
| "海淀" / "海淀区" | `{"district": "海淀"}` |
| "望京" | `{"area": "望京", "district": "朝阳"}` |
| "西二旗" | `{"area": "西二旗", "district": "海淀"}` |
| "国贸附近" | `{"landmark_query": "国贸"}` |

### 2.3 定义 update_preferences 工具 Schema

**文件：** `tools.py` — 替换现有 `TOOLS` 列表

新的 `TOOLS` 列表仅包含 4 个工具：

1. **update_preferences** — 提取/更新用户偏好（新增）
2. **get_house_detail** — 获取房源详情（保留）
3. **get_house_listings** — 跨平台比价（保留）
4. **execute_action** — 租房/退租/下架（保留）

`update_preferences` 的 schema：

```python
{
    "type": "function",
    "function": {
        "name": "update_preferences",
        "description": "提取或更新用户的租房偏好。调用后系统自动搜索并返回匹配房源。每轮只需提取本轮新增/变更的偏好，系统自动与历史偏好合并。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "array", "items": {"type": "string"},
                    "description": "用户提到的位置（行政区/商圈/地标均可），如 ['望京']、['海淀']、['国贸附近']"
                },
                "clear_location": {
                    "type": "boolean",
                    "description": "true=清除之前的位置偏好（用于'换XX看看'场景）"
                },
                "min_price": {"type": "integer", "description": "最低月租金（元）"},
                "max_price": {"type": "integer", "description": "最高月租金（元）"},
                "bedrooms": {"type": "string", "description": "卧室数，如 '2' 或 '2,3'"},
                "rental_type": {"type": "string", "description": "整租 或 合租"},
                "decoration": {"type": "string", "description": "精装/简装/豪华/毛坯"},
                "elevator": {"type": "boolean", "description": "是否需要电梯"},
                "min_area": {"type": "integer", "description": "最小面积（平米）"},
                "near_subway": {"type": "boolean", "description": "是否要求近地铁"},
                "subway_line": {"type": "string", "description": "地铁线路，如 13号线"},
                "utilities_type": {"type": "string", "description": "水电类型，如 民水民电"},
                "listing_platform": {"type": "string", "description": "挂牌平台：链家/安居客/58同城"},
                "available_before": {"type": "string", "description": "可入住日期上限，YYYY-MM-DD"},
                "max_commute_minutes": {"type": "integer", "description": "到西二旗通勤上限（分钟）"},
                "noise_preference": {"type": "string", "description": "噪音偏好，如 安静"},
                "orientation": {"type": "string", "description": "朝向偏好，如 朝南"}
            },
            "required": []
        }
    }
}
```

### 2.4 实现 update_preferences 工具函数

**文件：** `tools.py`

功能：
1. 接收 LLM 提取的偏好参数
2. 增量 merge 到 session 的 `UserPreferences` 对象
3. 对 `location` 字段调用 `resolve_location` 路由
4. **本 Story 中暂时返回偏好合并结果的摘要**（自动搜索在 Story 2 实现）

```python
async def update_preferences(client: httpx.AsyncClient, session_prefs: UserPreferences, **kwargs) -> dict:
    """合并新偏好到 session，返回当前偏好摘要"""
    ...
```

### 2.5 更新 Session 管理

**文件：** `main.py`

在 `sessions` 中为每个 session 增加 `UserPreferences` 实例：

```python
# 现有
sessions: dict[str, list] = {}  # session_id → message history

# 新增
session_preferences: dict[str, UserPreferences] = {}  # session_id → 偏好状态
```

Session 初始化时创建空的 `UserPreferences` 对象，并在 `run_agent` 调用时传入。

### 2.6 更新 Agent 循环

**文件：** `agent.py`

- 更新 `TOOL_DISPATCH`：移除旧工具，添加 `update_preferences`
- 更新 `SYSTEM_PROMPT`：引导 LLM 使用新工具
- `update_preferences` 需要访问 session 的偏好状态，通过闭包或参数传递

新的 `SYSTEM_PROMPT` 要点：
```
你是智能租房助手，帮助用户在北京寻找和租赁房源。

核心工作流：
1. 用户表达租房需求时 → 调用 update_preferences 提取偏好，系统自动搜索匹配房源
2. 用户想看某套房源详情 → 调用 get_house_detail
3. 用户想跨平台比价 → 调用 get_house_listings
4. 用户确认要租房/退租 → 调用 execute_action

使用 update_preferences 的规则：
- 每轮对话只提取本轮新增或变更的偏好字段
- 位置统一放在 location 字段，支持区名/商圈/地标
- "换XX看看" 场景需设置 clear_location=true
- 用户只是闲聊时不要调用 update_preferences
- 纯聊天或与房源无关的问题 → 直接自然语言回复
```

### 2.7 构建 LLM 提参测试场景

**重要：** 本 Story 的核心验证是确认 qwen3-32b 能正确使用 `update_preferences` 工具提取参数。

需要构建以下测试场景并通过 test-simulator 或手动验证：

#### 场景分类

| 编号 | 场景类型 | 用户输入示例 | 期望 LLM 提取的参数 |
|------|----------|-------------|-------------------|
| T1 | 单条件简单查询 | "找海淀区的房子" | `location: ["海淀"]` |
| T2 | 多条件查询 | "找大兴区的两居室，租金4000元以下" | `location: ["大兴"], bedrooms: "2", max_price: 4000` |
| T3 | 复杂多条件 | "找海淀区三居室，预算13000以内，精装修，近地铁" | `location: ["海淀"], bedrooms: "3", max_price: 13000, decoration: "精装", near_subway: true` |
| T4 | 指定平台 | "帮我找58同城上海淀区的房子" | `location: ["海淀"], listing_platform: "58同城"` |
| T5 | 情绪→需求转换 | "住得不太舒服，采光不好，房间也小" | LLM 应追问而非瞎猜；或提取 `orientation: "朝南"` 等合理推断 |
| T6 | 渐进式多轮偏好 | 第1轮: "两居室，4000以内" → 第2轮: "最好是精装修的" | 第1轮: `bedrooms: "2", max_price: 4000`；第2轮: `decoration: "精装"` |
| T7 | 位置变更 | "换大兴区看看" | `location: ["大兴"], clear_location: true` |
| T8 | 纯聊天 | "你好" / "谢谢" | 不调用任何工具，直接回复 |
| T9 | 地标位置 | "国贸附近有什么房子" | `location: ["国贸附近"]` 或 `location: ["国贸"]` |
| T10 | 通勤需求 | "通勤30分钟以内的房子" | `max_commute_minutes: 30` |

#### 验证方法

1. 通过 test-simulator 构造上述场景的 test case
2. 观察 LLM 返回的 `tool_calls` 中 `update_preferences` 的参数
3. 记录提参准确率，如发现系统性问题则调整 prompt 或 schema description

---

## 三、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `tools.py` | 修改 | 新增 UserPreferences 模型、resolve_location、update_preferences 函数；TOOLS 列表替换为 4 个工具 |
| `agent.py` | 修改 | 更新 SYSTEM_PROMPT、TOOL_DISPATCH（4 个工具）、HOUSE_SEARCH_TOOLS |
| `main.py` | 修改 | 新增 session_preferences 存储；构建 area_district_map；传偏好到 agent |

---

## 四、验收标准（AC）

### AC-1：数据模型完整
- [ ] `UserPreferences` 包含设计文档中定义的所有字段
- [ ] `resolve_location` 能正确路由 district / area / landmark_query 三种情况

### AC-2：工具体系替换完成
- [ ] `TOOLS` 列表仅包含 4 个工具：update_preferences, get_house_detail, get_house_listings, execute_action
- [ ] `TOOL_DISPATCH` 映射正确，旧工具（search_houses, search_landmark 等）已移除
- [ ] `update_preferences` 函数能正确接收参数并 merge 到 session 偏好

### AC-3：Session 偏好持久化
- [ ] 每个 session 有独立的 `UserPreferences` 实例
- [ ] 偏好支持跨轮次增量 merge（新字段覆盖旧值，未传字段保持不变）
- [ ] `clear_location=true` 时正确清除历史位置

### AC-4：LLM 提参准确性验证（核心）
- [ ] **T1-T4**（显式偏好）：LLM 正确调用 update_preferences 且参数准确，准确率 ≥ 90%
- [ ] **T5**（情绪场景）：LLM 不会幻觉出用户未提及的硬约束（如凭空生成 district）
- [ ] **T6**（多轮增量）：第 2 轮仅提取新增偏好，不重复已有偏好
- [ ] **T7**（位置变更）：LLM 正确设置 `clear_location=true`
- [ ] **T8**（纯聊天）：LLM 不调用任何工具
- [ ] 所有测试场景记录在日志中，便于后续分析

### AC-5：不回归
- [ ] `get_house_detail`、`get_house_listings`、`execute_action` 三个保留工具功能正常
- [ ] Agent 循环（MAX_ITERATIONS、错误处理等）行为不变

---

## 五、技术决策记录

| 决策 | 选项 | 选择 | 原因 |
|------|------|------|------|
| UserPreferences 存储位置 | 嵌入 sessions dict / 独立 dict | 独立 `session_preferences` dict | 职责清晰，不污染消息历史 |
| AREA_TO_DISTRICT 构建时机 | 启动时 / 每次 session init | 每次 session init（从 DEBUG_ALL_HOUSES 数据构建） | 数据已在 init 时获取，复用即可 |
| update_preferences 返回值 | 偏好摘要 / 搜索结果 | 本 Story 返回偏好摘要（搜索在 Story 2） | 分步验证，先确认提参准确 |

---

## 六、注意事项

1. **不保留旧工具兼容**：直接替换 TOOLS 列表，不做并行过渡
2. **本 Story 的 update_preferences 尚不触发自动搜索**：调用后返回偏好合并摘要，LLM 基于摘要生成回复。自动搜索逻辑在 Story 2 实现
3. **SYSTEM_PROMPT 是关键**：prompt 的措辞直接影响 LLM 提参质量，需反复调试
4. **日志要记录 LLM 传给 update_preferences 的完整参数**：方便事后分析提参准确率
