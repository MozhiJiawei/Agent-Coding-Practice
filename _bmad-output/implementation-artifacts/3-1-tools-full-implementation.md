# Story 3.1: tools.py 全量工具实现

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer and user,
I want all tool functions implemented in `tools.py` in a single story,
So that the complete tool layer is available as one cohesive unit for the agent to use.

## Acceptance Criteria

**基础架构**

1. **Given** `tools.py` is implemented
   **When** module-level constants are defined
   **Then** `RENTAL_API_BASE = "http://7.225.29.223:8080"` is defined (already present)
   **And** `USER_ID = os.environ["USER_ID"]` is read once at module load time (already present)
   **And** `MAX_PAGES = 5` is defined as a constant (already present)
   **And** a helper `_get_headers() -> dict` returns `{"X-User-ID": USER_ID}` (already present)

2. **Given** the `TOOLS` constant is defined
   **When** module-level TOOLS list is populated
   **Then** it is a list of OpenAI function-calling format dicts, defined at module top level (not inside any function)
   **And** each tool's `"name"` field exactly matches the corresponding Python async function name
   **And** `listing_platform` parameter in `search_houses`, `search_nearby_landmark`, and `execute_action` uses the same enum: `["链家", "安居客", "58同城"]` with default `"安居客"`
   **And** `TOOL_DISPATCH` in `agent.py` references all 6 tool functions imported from `tools.py` (already wired)

**search_houses（FR6–FR12, NFR1, NFR5）**

3. **Given** the model calls `search_houses` with one or more filter parameters
   **When** the tool function executes
   **Then** it calls `GET /api/houses/by_platform` with applicable query parameters: `district`, `min_price`, `max_price`, `room_type`, `decoration`, `orientation`, `max_subway_dist`, `listing_platform`
   **And** the request includes `X-User-ID` header via `_get_headers()`
   **And** all filter parameters are optional; omitted ones are not sent in the query
   **And** the function returns a dict with the house listings data on success
   **And** on any exception, returns `{"error": "search_houses failed: <reason>"}` without raising (NFR8)

4. **Given** a search returns multiple pages of results
   **When** the first page response indicates `total > len(first_page_items)`
   **Then** additional pages are fetched serially: `page = 2, 3, ...` up to `MAX_PAGES = 5`
   **And** all pages are combined into a single `items` list returned to the agent (FR12)
   **And** the agent loop is completely unaware of pagination — it receives one unified result (NFR1)

**get_house_detail（FR13, NFR5）**

5. **Given** the model calls `get_house_detail` with a `house_id` parameter
   **When** the tool function executes
   **Then** it calls `GET /api/houses/{house_id}` with the `X-User-ID` header
   **And** the full response JSON is returned as a dict (FR13)
   **And** `house_id` is treated as a string throughout (never converted to integer)
   **And** on any HTTP or network exception, returns `{"error": "get_house_detail failed: <reason>"}` without raising

**search_landmark（FR14）**

6. **Given** the model calls `search_landmark` with a `query` parameter (and optional `category`, `district`)
   **When** the tool function executes
   **Then** it calls `GET /api/landmarks/search` with the `query` value mapped to API param `q`, plus any provided `category` and `district`
   **And** the request does NOT include an `X-User-ID` header (landmark API requires no auth, NFR5)
   **And** the response containing landmark list is returned as a dict (FR14)
   **And** on any exception, returns `{"error": "search_landmark failed: <reason>"}` without raising

**search_nearby_landmark（FR15, NFR5）**

7. **Given** the model calls `search_nearby_landmark` with `landmark_id` and optional `max_distance`, price/room filters, `listing_platform`
   **When** the tool function executes
   **Then** it calls `GET /api/houses/nearby` with `landmark_id` and applicable filter parameters
   **And** the request includes `X-User-ID` header via `_get_headers()` (NFR5)
   **And** each result item includes walking distance and walking time to the landmark (FR15)
   **And** `listing_platform` uses the same enum `["链家", "安居客", "58同城"]` with default `"安居客"`
   **And** the combined result dict is returned on success
   **And** on any exception, returns `{"error": "search_nearby_landmark failed: <reason>"}` without raising
   **And** `search_nearby_landmark` is included in `HOUSE_SEARCH_TOOLS` set in `agent.py` (already defined), triggering Format Guard on call

**get_nearby_amenities（FR16, NFR5）**

8. **Given** the model calls `get_nearby_amenities` with `house_id` and optional `category`, `max_distance_m`
   **When** the tool function executes
   **Then** it calls `GET /api/houses/nearby_landmarks` with `house_id`, `category`, and `max_distance_m` as query parameters
   **And** the request includes `X-User-ID` header via `_get_headers()`
   **And** `max_distance_m` defaults to 1000 if not provided (FR16: 1000m range)
   **And** the result dict is returned on success
   **And** on any exception, returns `{"error": "get_nearby_amenities failed: <reason>"}` without raising
   **And** `get_nearby_amenities` is NOT in `HOUSE_SEARCH_TOOLS` — its response path remains plain text

**execute_action（FR17, FR18, FR19, NFR5）**

9. **Given** the model calls `execute_action` with `action`, `house_id`, and `listing_platform`
   **When** the tool function executes
   **Then** it maps `action` to the correct API endpoint:
   - `"rent"` → `POST /api/houses/{house_id}/rent`
   - `"terminate"` → `POST /api/houses/{house_id}/terminate`
   - `"offline"` → `POST /api/houses/{house_id}/offline`
   **And** each POST request includes the `X-User-ID` header via `_get_headers()` (NFR5)
   **And** `listing_platform` is sent as required by the API
   **And** `listing_platform` uses the enum `["链家", "安居客", "58同城"]` consistent with other tools
   **And** the API response confirming the state change is returned as a dict (FR17, FR18, FR19)
   **And** `house_id` is treated as a string throughout (never converted to integer)

10. **Given** an invalid `action` value is passed
    **When** the tool function executes
    **Then** it returns `{"error": "execute_action failed: unknown action <value>"}` without raising

11. **Given** any HTTP or network exception occurs
    **When** the request fails
    **Then** the function returns `{"error": "execute_action failed: <reason>"}` without raising
    **And** `execute_action` is NOT in `HOUSE_SEARCH_TOOLS` — its response path remains plain text confirmation

## Tasks / Subtasks

- [x] **Task 1: 填充 `TOOLS` 常量**（AC: 2）
  - [x] 1.1: 编写全部 6 个工具的 OpenAI function-calling 格式 schema（见 Dev Notes）
  - [x] 1.2: 验证每个 tool schema 的 `"name"` 字段与对应 Python 函数名完全一致
  - [x] 1.3: 确认 `search_houses`、`search_nearby_landmark`、`execute_action` 的 `listing_platform` enum 值完全一致：`["链家", "安居客", "58同城"]`
  - [x] 1.4: 确认 `TOOL_DISPATCH` 在 `agent.py` 已正确引用全部 6 个函数（无需修改，已完成）

- [x] **Task 2: 实现 `search_houses`**（AC: 3, 4）
  - [x] 2.1: 调用 `GET /api/houses/by_platform`，传入 `_get_headers()`
  - [x] 2.2: 动态构建 query params（仅包含 kwargs 中非 None 的参数），从第 1 页开始
  - [x] 2.3: 解析响应（见 Dev Notes 响应结构说明），提取 `items` 和 `total`
  - [x] 2.4: 实现串行翻页循环：`while len(all_items) < total and page <= MAX_PAGES`
  - [x] 2.5: 返回 `{"total": total, "items": all_items}`；任何异常返回 error dict

- [x] **Task 3: 实现 `get_house_detail`**（AC: 5）
  - [x] 3.1: 调用 `GET /api/houses/{house_id}`（house_id 转 str），传入 `_get_headers()`
  - [x] 3.2: 返回 `resp.json()`；任何异常返回 error dict

- [x] **Task 4: 实现 `search_landmark`**（AC: 6）
  - [x] 4.1: 调用 `GET /api/landmarks/search`，将工具参数 `query` 映射为 API 参数 `q`
  - [x] 4.2: 可选参数 `category`、`district` 仅在非 None 时加入 params
  - [x] 4.3: **不传** `X-User-ID` 请求头；返回 `resp.json()`；异常返回 error dict

- [x] **Task 5: 实现 `search_nearby_landmark`**（AC: 7）
  - [x] 5.1: 调用 `GET /api/houses/nearby`，传入所有非 None 的 kwargs 参数
  - [x] 5.2: 传入 `_get_headers()`；返回 `resp.json()`；异常返回 error dict

- [x] **Task 6: 实现 `get_nearby_amenities`**（AC: 8）
  - [x] 6.1: 调用 `GET /api/houses/nearby_landmarks`，传入 `house_id`、可选 `category`、`max_distance_m`
  - [x] 6.2: 若 `max_distance_m` 未提供，默认设为 `1000`
  - [x] 6.3: 传入 `_get_headers()`；返回 `resp.json()`；异常返回 error dict

- [x] **Task 7: 实现 `execute_action`**（AC: 9, 10, 11）
  - [x] 7.1: 检查 `action` 是否在 `{"rent", "terminate", "offline"}` 中；否则返回 error dict
  - [x] 7.2: 发起 `POST /api/houses/{house_id}/{action}`，JSON body 为 `{"listing_platform": listing_platform}`
  - [x] 7.3: 传入 `_get_headers()`；返回 `resp.json()`；异常返回 error dict

- [x] **Task 8: 编写单元测试**
  - [x] 8.1: `tests/test_tools.py` — 6 个工具各自的 happy path（mock httpx 响应）
  - [x] 8.2: `tests/test_tools.py` — 6 个工具各自的 error path（mock httpx 抛异常）
  - [x] 8.3: `tests/test_tools.py` — `search_houses` 翻页逻辑（mock 多页响应，验证 all_items 合并）
  - [x] 8.4: `tests/test_tools.py` — `TOOLS` 常量结构验证（name 一致性、listing_platform enum 一致性）
  - [x] 8.5: `tests/test_tools.py` — `execute_action` 无效 action 返回 error dict
  - [x] 8.6: 全量回归：224 个测试全部通过（原 165 + 新增 59）

## Dev Notes

### 当前代码基线（Story 2.3 完成后）

**`tools.py` 当前状态：**
```python
# ✅ 已正确实现（不需修改）：
RENTAL_API_BASE = "http://7.225.29.223:8080"
USER_ID = os.environ["USER_ID"]   # 模块加载时读取
MAX_PAGES = 5
def _get_headers() -> dict: ...   # 返回 {"X-User-ID": USER_ID}
async def init_houses(...): ...   # POST /api/houses/init

# ← Task 1: 填充（当前为空列表）
TOOLS: list[dict] = []

# ← Tasks 2–7: 实现（当前均为 pass stub）
async def search_houses(client, **kwargs) -> dict: pass
async def search_landmark(client, **kwargs) -> dict: pass
async def search_nearby_landmark(client, **kwargs) -> dict: pass
async def get_house_detail(client, **kwargs) -> dict: pass
async def get_nearby_amenities(client, **kwargs) -> dict: pass
async def execute_action(client, **kwargs) -> dict: pass
```

**`agent.py` 当前状态（无需修改）：**
```python
# 已正确定义（Story 2.3 完成）：
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}
TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    "search_landmark": search_landmark,
    "search_nearby_landmark": search_nearby_landmark,
    "get_house_detail": get_house_detail,
    "get_nearby_amenities": get_nearby_amenities,
    "execute_action": execute_action,
}
# run_agent 中已有 if TOOLS: ... guard
# 填充 TOOLS 后，LLM 调用将自动携带工具 schema → 工具调用能力自动激活
```

### 🚨 关键 API 差异说明（架构文档 vs 实际接口文档）

**差异 1 — search_houses 端点：**
- epics.md AC 写的是 `GET /api/houses/listings/{listing_platform}`（错误）
- 实际接口文档（interface_simulate.md 接口9）：`GET /api/houses/by_platform`
- ✅ **必须使用 `/api/houses/by_platform`**（`listing_platform` 作为 query param，非路径参数）

**差异 2 — search_landmark 参数名：**
- epics.md AC 写的 TOOLS schema 参数名为 `query`
- 实际接口文档（interface_simulate.md 接口3）：API query param 名为 `q`（必填）
- ✅ **TOOLS schema 中保留 `query`（模型友好），函数内部映射为 `q` 传给 API**

**差异 3 — get_nearby_amenities 默认 max_distance_m：**
- epics.md AC / PRD FR16：1000 米
- interface_simulate.md 接口说明：API 默认 3000 米
- ✅ **工具函数内部默认传 `1000`**（匹配 FR16 要求，覆盖 API 默认值）

### API 响应结构

租房 API 统一返回包装格式（基于 interface_simulate.md init 响应示例推断）：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 100,
    "page_size": 10,
    "items": [...]
  }
}
```

**search_houses 响应解析（防御性写法）：**
```python
result = resp.json()
# 支持 { data: { total, items } } 和 { total, items } 两种结构
inner = result.get("data", result)
all_items = list(inner.get("items", []))
total = inner.get("total", len(all_items))
```

若实际 API 返回结构不同，开发者需在首次真实调用时（Smoke Test）确认并对齐。

### Task 1：`TOOLS` 常量完整实现

```python
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_houses",
            "description": "搜索可租房源，支持多维度筛选：区域、价格、户型、装修、朝向、地铁距离。自动处理分页，返回完整结果集（最多5页）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "行政区，如 海淀、朝阳、通州、昌平、大兴、房山、西城、丰台、顺义、东城"
                    },
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "room_type": {
                        "type": "string",
                        "description": "户型，如 整租、合租、一居室、两居室、三居室、四居室"
                    },
                    "decoration": {
                        "type": "string",
                        "enum": ["精装", "简装", "豪华", "毛坯", "空房"],
                        "description": "装修类型"
                    },
                    "orientation": {
                        "type": "string",
                        "description": "朝向，如 朝南、朝北、朝东、朝西、南北、东西"
                    },
                    "max_subway_dist": {
                        "type": "integer",
                        "description": "最大地铁距离（米），800=近地铁，1000=地铁可达"
                    },
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，默认安居客"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_detail",
            "description": "获取单套房源完整详情：地址、户型、面积、租金、装修、朝向、楼层、设施、噪音评级、标签等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1、HF_25"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_landmark",
            "description": "按关键词模糊搜索地标（地铁站、公司、商圈等），返回 landmark_id 供后续查地标附近房源使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如 '西二旗'、'百度'、'国贸'"},
                    "category": {"type": "string", "description": "地标类别，如 地铁站、公司、商圈"},
                    "district": {"type": "string", "description": "行政区筛选"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_nearby_landmark",
            "description": "查询以指定地标为圆心、指定距离范围内的可租房源，返回含步行距离和步行时间。需先调用 search_landmark 获取 landmark_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_id": {"type": "string", "description": "地标 ID（来自 search_landmark 返回结果）"},
                    "max_distance": {"type": "integer", "description": "最大距离（米），默认 2000"},
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "room_type": {"type": "string", "description": "户型，如 整租、合租"},
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，默认安居客"
                    }
                },
                "required": ["landmark_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_amenities",
            "description": "查询指定房源 1000 米内的生活配套（商超、公园等），返回名称、类别和步行距离。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1"},
                    "category": {"type": "string", "description": "配套类别，如 商超、公园"},
                    "max_distance_m": {"type": "integer", "description": "最大距离（米），默认 1000"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_action",
            "description": "对指定房源执行租房、退租或下架操作，调用 API 完成状态变更（不能只回复文字，必须调用此工具）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["rent", "terminate", "offline"],
                        "description": "rent=租房，terminate=退租，offline=下架"
                    },
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1"},
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，必填"
                    }
                },
                "required": ["action", "house_id", "listing_platform"]
            }
        }
    }
]
```

### Task 2：`search_houses` 完整实现

```python
async def search_houses(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        # 构建基础 params（跳过 None 值）
        base_params: dict = {k: v for k, v in kwargs.items() if v is not None}
        base_params["page"] = 1

        resp = await client.get(
            "/api/houses/by_platform",
            params=base_params,
            headers=_get_headers(),
        )
        resp.raise_for_status()

        # 防御性解析：兼容 { data: {...} } 和 {...} 两种格式
        result = resp.json()
        inner = result.get("data", result)
        all_items: list = list(inner.get("items", []))
        total: int = inner.get("total", len(all_items))

        page = 2
        while len(all_items) < total and page <= MAX_PAGES:
            next_params = {**base_params, "page": page}
            next_resp = await client.get(
                "/api/houses/by_platform",
                params=next_params,
                headers=_get_headers(),
            )
            next_resp.raise_for_status()
            next_result = next_resp.json()
            next_inner = next_result.get("data", next_result)
            all_items.extend(next_inner.get("items", []))
            page += 1

        return {"total": total, "items": all_items}
    except Exception as e:
        return {"error": f"search_houses failed: {str(e)}"}
```

**重要：`listing_platform` 自动通过 kwargs 传入 base_params，无需特殊处理。**

### Task 3：`get_house_detail` 完整实现

```python
async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        resp = await client.get(f"/api/houses/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_house_detail failed: {str(e)}"}
```

### Task 4：`search_landmark` 完整实现

```python
async def search_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {}
        # TOOLS schema 用 "query"，API 实际参数名为 "q"
        if kwargs.get("query"):
            params["q"] = kwargs["query"]
        if kwargs.get("category"):
            params["category"] = kwargs["category"]
        if kwargs.get("district"):
            params["district"] = kwargs["district"]

        # 地标接口不需要 X-User-ID
        resp = await client.get("/api/landmarks/search", params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_landmark failed: {str(e)}"}
```

### Task 5：`search_nearby_landmark` 完整实现

```python
async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        resp = await client.get(
            "/api/houses/nearby",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_nearby_landmark failed: {str(e)}"}
```

### Task 6：`get_nearby_amenities` 完整实现

```python
async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        # FR16 要求 1000 米，覆盖 API 默认的 3000 米
        if "max_distance_m" not in params:
            params["max_distance_m"] = 1000
        resp = await client.get(
            "/api/houses/nearby_landmarks",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_nearby_amenities failed: {str(e)}"}
```

### Task 7：`execute_action` 完整实现

```python
async def execute_action(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        action = kwargs.get("action", "")
        house_id = str(kwargs.get("house_id", ""))
        listing_platform = kwargs.get("listing_platform", "安居客")

        valid_actions = {"rent", "terminate", "offline"}
        if action not in valid_actions:
            return {"error": f"execute_action failed: unknown action {action}"}

        resp = await client.post(
            f"/api/houses/{house_id}/{action}",
            json={"listing_platform": listing_platform},
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"execute_action failed: {str(e)}"}
```

### 测试策略（Task 8）

**conftest.py 注意事项（沿用现有模式）：**
- `os.environ.setdefault("USER_ID", "test-user-placeholder")` 已在 conftest.py 中设置，`tools.py` 模块加载不会 KeyError
- `_mock_run_agent` autouse fixture 防止真实 LLM 调用——工具测试时不受影响（直接测试工具函数，不经过 agent loop）
- 工具函数测试需 mock `httpx.AsyncClient` 的 `get` / `post` 方法

**Mock httpx 响应的推荐模式：**
```python
from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.fixture
def mock_client():
    client = MagicMock(spec=httpx.AsyncClient)
    return client

def make_mock_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()  # 不抛异常
    return resp

# 示例：测试 search_houses
@pytest.mark.anyio
async def test_search_houses_single_page(mock_client):
    mock_client.get = AsyncMock(return_value=make_mock_response({
        "data": {"total": 2, "page_size": 10, "items": [{"id": "HF_1"}, {"id": "HF_2"}]}
    }))
    result = await search_houses(mock_client, district="海淀")
    assert result["total"] == 2
    assert len(result["items"]) == 2
    mock_client.get.assert_called_once()
```

**翻页测试模式（search_houses 多页）：**
```python
@pytest.mark.anyio
async def test_search_houses_pagination(mock_client):
    # 第 1 页返回 total=15，但只有 10 条 → 触发第 2 页请求
    page1 = make_mock_response({"data": {"total": 15, "page_size": 10, "items": [{"id": f"HF_{i}"} for i in range(10)]}})
    page2 = make_mock_response({"data": {"total": 15, "page_size": 10, "items": [{"id": f"HF_{i}"} for i in range(10, 15)]}})
    mock_client.get = AsyncMock(side_effect=[page1, page2])
    result = await search_houses(mock_client)
    assert result["total"] == 15
    assert len(result["items"]) == 15
    assert mock_client.get.call_count == 2
```

**错误路径测试模式：**
```python
@pytest.mark.anyio
async def test_search_houses_exception(mock_client):
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
    result = await search_houses(mock_client)
    assert "error" in result
    assert "search_houses failed" in result["error"]
```

### 与 Story 3.1 完成后的系统能力对比

| 能力 | Story 2.3 完成后 | Story 3.1 完成后 |
|------|-----------------|-----------------|
| 聊天回复 | ✅ 正常工作 | ✅ 正常工作 |
| 工具调用（任意工具） | ❌ TOOLS=[]，LLM 无工具可调 | ✅ 全部 6 个工具可用 |
| 房源搜索 JSON 格式 | ❌ Format Guard 不触发 | ✅ 触发并返回合法 JSON |
| 地标搜索 + 附近房源 | ❌ 无实现 | ✅ search_landmark + search_nearby_landmark |
| 租赁操作（租/退/下架） | ❌ 无实现 | ✅ execute_action |
| 系统整体可用性 | 聊天可用 | **完整可用，可打榜** |

### 打榜前 Smoke Test 验证序列

```bash
# 启动
USER_ID=<真实工号> uvicorn main:app --host 0.0.0.0 --port 8191

# 1. 聊天（response 应为纯文本字符串）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<IP>","session_id":"smoke-chat","message":"你好"}'

# 2. 房源搜索（response 应为合法 JSON 字符串，含 message 和 houses 字段）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<IP>","session_id":"smoke-search","message":"找海淀区两居室"}'

# 3. 租房操作（response 应为纯文本确认，execute_action 应被调用）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model_ip":"<IP>","session_id":"smoke-action","message":"帮我租 HF_1"}'
```

### Project Structure Notes

- **修改文件**：`tools.py` 唯一文件（TOOLS 常量 + 6 个工具函数实现）
- **无需修改**：`agent.py`（TOOL_DISPATCH 和 HOUSE_SEARCH_TOOLS 已正确配置）、`main.py`（路由层无变更）
- **imports 方向**：`main.py → agent.py → tools.py`（单向链，本 Story 不引入新导入）
- `init_houses` 函数保持不变（Story 2.2 已完成实现）

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3, Story 3.1 所有 AC 来源；Epic 3 概述]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Structure Patterns: 工具 Dispatch 表；Format Patterns: 工具函数返回类型约定；Communication Patterns: 翻页模式代码片段；tools.py 内部结构（顺序）]
- [Source: `docs/interface_simulate.md` — 接口9: GET /api/houses/by_platform; 接口3: GET /api/landmarks/search (q参数); 接口10: GET /api/houses/nearby; 接口11: GET /api/houses/nearby_landmarks; 接口13/14/15: POST 操作端点; 近距离概念说明（max_subway_dist=800/1000m）]
- [Source: `_bmad-output/project-context.md` — X-User-ID 必须为真实工号; 地标接口不需 X-User-ID; Pagination; 工具函数错误处理模式]
- [Source: `_bmad-output/implementation-artifacts/2-3-agent-loop-full-implementation.md` — TOOLS 为空时行为说明; 与 Story 3.1 集成边界表; TOOL_DISPATCH 已完成配置]
- [Source: `tools.py` — 当前基线：TOOLS=[]（line 10）；全部 6 个工具 pass stub（lines 18–39）；init_houses 已实现（lines 42–48）]
- [Source: `agent.py` — TOOL_DISPATCH 完整配置（lines 36–43）；HOUSE_SEARCH_TOOLS（line 34）；if TOOLS: guard（lines 83–85）]
- [Source: `tests/conftest.py` — os.environ.setdefault("USER_ID", ...) 在模块顶层; autouse fixtures]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor)

### Debug Log References

无阻断性问题。

### Completion Notes List

- TDD 流程：先写全量测试（59 个用例），RED 阶段确认 50 FAIL，GREEN 阶段一次实现全部通过。
- Task 1: `TOOLS` 常量填充 6 个 OpenAI function-calling schema，含完整 listing_platform enum 一致性。
- Task 2: `search_houses` 实现防御性响应解析（兼容 `{data:{}}` 和平铺两种格式）+ 串行翻页（MAX_PAGES=5）。
- Task 3: `get_house_detail` — house_id 强制转 str，X-User-ID header 附加。
- Task 4: `search_landmark` — 内部将 `query` 映射为 API 参数 `q`，不附加 X-User-ID header。
- Task 5: `search_nearby_landmark` — 过滤 None 参数，附加 X-User-ID header。
- Task 6: `get_nearby_amenities` — 未提供 `max_distance_m` 时默认 1000（覆盖 API 默认 3000）。
- Task 7: `execute_action` — 先校验 action 有效性，POST body 含 listing_platform，house_id 强制转 str。
- Task 8: 全量回归 224 passed（原有 165 + 新增 59）。

**Code Review（2026-02-27）:**
- [H1 Fixed] `search_landmark` truthiness 检查改为 `is not None` 检查，修复空字符串被静默丢弃的 bug。
- [M1 Fixed] 补充 4 个工具的端点 URL 验证测试（search_houses, search_landmark, search_nearby_landmark, get_nearby_amenities）。
- [M2 Fixed] 补充 `search_houses` 的 `listing_platform` 参数转发测试。
- [M3 Fixed] 补充 `search_landmark` 的 `district=None` 不发送测试。
- 全量回归 229 passed（原有 165 + 新增 64）。

### File List

- `tools.py` — TOOLS 常量 + 6 个工具函数完整实现（修改）
- `tests/test_tools.py` — 64 个单元测试（新增）
- `_bmad-output/implementation-artifacts/3-1-tools-full-implementation.md` — Story 文件（已更新）
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 状态更新（已更新）
