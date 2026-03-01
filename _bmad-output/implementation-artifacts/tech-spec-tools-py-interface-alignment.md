---
title: 'tools.py 接口对齐重写'
slug: 'tools-py-interface-alignment'
created: '2026-03-01'
status: 'Implementation Complete'
stepsCompleted: [1, 2, 3, 4]
tech_stack: ['Python 3.11+', 'httpx (async)', 'FastAPI', 'OpenAI function-calling (qwen3-32b)']
files_to_modify: ['tools.py', 'agent.py', 'tests/test_tools.py']
code_patterns: ['async def fn(client: httpx.AsyncClient, **kwargs) -> dict', 'TOOLS list as module-level constant', 'TOOL_DISPATCH dict in agent.py', 'try/except returning error dict', 'params= vs json= in httpx POST']
test_patterns: ['pytest + anyio', 'AsyncMock for httpx client', 'make_mock_response helper', 'test class per tool']
---

# Tech-Spec: tools.py 接口对齐重写

**Created:** 2026-03-01

## Overview

### Problem Statement

当前 `tools.py` 的 TOOLS 函数定义（OpenAI function-calling schema）和函数实现与 `docs/interface_simulate.md` 中描述的真实 API 接口存在多处不对齐，导致 Agent 无法正确调用部分接口，或传参方式错误导致 API 返回 400。

### Solution

以 `docs/interface_simulate.md`（含 OpenAPI 3.0 spec 和真实测试日志）为权威参考，对照 `test-simulator/mock_rental.py` 的实现逻辑，系统性重写 `tools.py` 中的 TOOLS schema 和所有函数实现，消除所有接口不对齐问题，并补充文档中存在但当前 TOOLS 未暴露的重要接口工具。

### Scope

**In Scope:**
- `tools.py`：修正 `search_houses` TOOLS schema 参数名和缺失参数
- `tools.py`：修正 `execute_action` 函数，将 `listing_platform` 从 JSON body 改为 query param
- `tools.py`：修正 `get_nearby_amenities` TOOLS schema 及实现（`house_id`→`community`，`category`→`type`）
- `tools.py`：新增 `get_houses_by_community` 工具（接口8）
- `tools.py`：新增 `get_house_listings` 工具（接口7）
- `agent.py`：更新 TOOL_DISPATCH 注册新增工具，更新 SYSTEM_PROMPT 说明
- `tests/test_tools.py`：修正已过时的测试断言（execute_action JSON body 测试、TOOLS 数量、get_nearby_amenities 参数）

**Out of Scope:**
- 修改 `main.py`（仅 chat 路由，无需改动）
- 修改 `mock_rental.py` 或 `test-simulator/` 下任何文件
- 新增大量单元测试（仅修正现有不对齐测试）
- 接口1(`/api/landmarks`)、接口4、5、12 的 tool 封装（优先级低，不影响核心场景）

## Context for Development

### Codebase Patterns

- `tools.py` 模块顶层常量：`RENTAL_API_BASE`, `USER_ID`, `MAX_PAGES=5`；模块加载时读取 `USER_ID`
- 所有工具函数签名统一：`async def func_name(client: httpx.AsyncClient, **kwargs) -> dict`
- `_get_headers()` → `{"X-User-ID": USER_ID.encode("utf-8")}`；所有 `/api/houses/*` 必须带此 header；`/api/landmarks/*` 不需要
- 函数内所有 API 调用用 `try/except Exception as e` 包裹，失败返回 `{"error": f"func_name failed: {str(e)}"}`
- `search_houses` 已实现多页自动翻页（`MAX_PAGES=5`），其他接口目前未实现分页
- `agent.py` 中 `TOOL_DISPATCH` dict 维护函数名→函数引用的映射；新增工具必须同时在此注册，否则 LLM 调用时返回 `{"error": "Unknown tool: ..."}`
- `agent.py` 中 `HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}` 控制哪些工具触发 JSON 格式响应

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `tools.py` | 主要修改目标：TOOLS schema + 函数实现 |
| `agent.py` | 需更新 TOOL_DISPATCH + imports + SYSTEM_PROMPT |
| `tests/test_tools.py` | 需修正 3 处过时断言（见下方 Technical Decisions） |
| `docs/interface_simulate.md` | 权威 API 文档（含 OpenAPI 3.0 spec 和真实测试日志） |

### Technical Decisions

**TD-1：`execute_action` 传参方式**
- 当前：`json={"listing_platform": listing_platform}` → API 返回 400（日志 scenario 17-19 证实）
- 修正：改为 `params={"listing_platform": listing_platform}`（API 文档明确 `"in": "query"`）
- 测试影响：`test_listing_platform_in_json_body` 需改为 `test_listing_platform_in_query_params`

**TD-2：`get_nearby_amenities` 参数重构**
- 当前 TOOLS schema 用 `house_id`（房源ID），但 `/api/houses/nearby_landmarks` 接口要求 `community`（小区名）
- 当前 TOOLS 用 `category`（中文类别），但 API 要求 `type`（`shopping`/`park` 英文枚举）
- 修正：TOOLS schema 改为 `community: string` + `type: enum[shopping, park]`；函数实现直接透传
- 测试影响：`test_returns_amenities` 和相关测试需改为传 `community="小区名"` 和 `type="shopping"`

**TD-3：`search_houses` schema 参数对齐**
- 删除：`room_type`（API 无此参数）
- 新增：`rental_type`（整租/合租）、`bedrooms`（卧室数，如"1,2"）、`area`（商圈）、`elevator`（true/false）、`min_area`、`max_area`、`property_type`、`subway_line`、`subway_station`、`utilities_type`、`available_from_before`、`commute_to_xierqi_max`、`sort_by`（price/area/subway）、`sort_order`（asc/desc）

**TD-4：新增两个工具**
- `get_houses_by_community(community, listing_platform?, page?, page_size?)` → `GET /api/houses/by_community`；需要 X-User-ID
- `get_house_listings(house_id)` → `GET /api/houses/listings/{house_id}`；需要 X-User-ID；响应 `data.items` 为三平台挂牌记录
- 两者都需在 `agent.py` TOOL_DISPATCH 注册，并在 imports 中引入
- 测试影响：`test_tools_has_six_entries` 需改为 8（或按实际新增数量）

**TD-5：`get_nearby_amenities` 默认距离**
- API 默认 `max_distance_m=3000`，当前代码覆盖为 1000；保持 1000m 覆盖（符合 FR16 业务需求）

## Implementation Plan

### Tasks

- [x] **Task 1 — `tools.py`：修正 `execute_action` 传参方式（最高优先级）**
  - File: `tools.py`
  - Action: 第 266 行附近，将 `resp = await client.post(f"/api/houses/{house_id}/{action}", json={"listing_platform": listing_platform}, headers=_get_headers())` 改为 `resp = await client.post(f"/api/houses/{house_id}/{action}", params={"listing_platform": listing_platform}, headers=_get_headers())`
  - Notes: API 文档 OpenAPI spec 明确 `listing_platform` 的 `"in": "query"`；真实测试日志 scenario 17-19 均因 body 传参返回 400，scenario 20 正确传参返回 200

- [x] **Task 2 — `tools.py`：修正 `search_houses` TOOLS schema**
  - File: `tools.py`
  - Action: 找到 TOOLS list 中 `"name": "search_houses"` 的 `parameters.properties`，执行以下精确改动：
    1. **删除** `room_type` 字段（整个 key-value 块）
    2. **新增** 以下字段（全部 `required: []` 不变）：
       - `"rental_type": {"type": "string", "description": "整租 或 合租"}`
       - `"bedrooms": {"type": "string", "description": "卧室数，逗号分隔，如 \"1,2\""}`
       - `"area": {"type": "string", "description": "商圈，逗号分隔，如 \"西二旗,上地\""}`
       - `"elevator": {"type": "string", "description": "是否有电梯：true 或 false"}`
       - `"min_area": {"type": "integer", "description": "最小面积（平米）"}`
       - `"max_area": {"type": "integer", "description": "最大面积（平米）"}`
       - `"property_type": {"type": "string", "description": "物业类型，如 住宅"}`
       - `"subway_line": {"type": "string", "description": "地铁线路，如 13号线"}`
       - `"subway_station": {"type": "string", "description": "地铁站名，如 车公庄站"}`
       - `"utilities_type": {"type": "string", "description": "水电类型，如 民水民电"}`
       - `"available_from_before": {"type": "string", "description": "可入住日期上限，YYYY-MM-DD，如 2026-03-10"}`
       - `"commute_to_xierqi_max": {"type": "integer", "description": "到西二旗通勤时间上限（分钟）"}`
       - `"sort_by": {"type": "string", "enum": ["price", "area", "subway"], "description": "排序字段"}`
       - `"sort_order": {"type": "string", "enum": ["asc", "desc"], "description": "排序方向"}`
  - Notes: `async def search_houses` 函数体使用 `**kwargs` 透传，无需修改；`district` 描述可补充"逗号分隔可传多区"

- [x] **Task 3 — `tools.py`：重构 `get_nearby_amenities` schema 和实现**
  - File: `tools.py`
  - Action — Schema 部分（TOOLS list 中 `get_nearby_amenities`）：
    1. 将 `house_id` 字段替换为 `"community": {"type": "string", "description": "小区名，如 建清园(南区)，需与房源信息中的 community 字段完全一致"}`，并加入 `"required": ["community"]`
    2. 将 `category` 字段替换为 `"type": {"type": "string", "enum": ["shopping", "park"], "description": "地标类型：shopping(商超)/park(公园)，不传则返回全部"}`
    3. `description` 改为：`"查询指定小区周边生活配套（商超/公园），按距离排序。需先通过 search_houses 或 get_house_detail 获知小区名。"`
    4. 保留 `max_distance_m` 字段不变
  - Action — 函数实现部分（`async def get_nearby_amenities`）：
    1. 删除 `if "max_distance_m" not in params: params["max_distance_m"] = 1000` 之前对 `house_id` 相关的特殊处理（实际上当前代码直接透传 kwargs，但函数名和旧 schema 传入了 `house_id`，参数名不匹配导致 API 忽略）
    2. 将默认值逻辑改为：`if "max_distance_m" not in params: params["max_distance_m"] = 1000`（保持不变）
    3. 函数签名和整体逻辑保持 `**kwargs` 透传模式，调用 `/api/houses/nearby_landmarks`

- [x] **Task 4 — `tools.py`：新增 `get_houses_by_community` 工具**
  - File: `tools.py`
  - Action — Schema（在 TOOLS list 末尾追加）：
    ```python
    {
        "type": "function",
        "function": {
            "name": "get_houses_by_community",
            "description": "按小区名查询该小区下可租房源，用于指代消解（如用户说'这个小区'）或查某小区地铁/隐性属性。需传入精确小区名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string", "description": "小区名，需与数据完全一致，如 建清园(南区)、保利锦上(二期)"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"], "description": "挂牌平台，不传默认安居客"},
                    "page": {"type": "integer", "description": "页码，默认 1"},
                    "page_size": {"type": "integer", "description": "每页条数，默认 10"}
                },
                "required": ["community"]
            }
        }
    }
    ```
  - Action — 函数实现（在文件末尾追加）：
    ```python
    async def get_houses_by_community(client: httpx.AsyncClient, **kwargs) -> dict:
        try:
            params: dict = {k: v for k, v in kwargs.items() if v is not None}
            resp = await client.get("/api/houses/by_community", params=params, headers=_get_headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": f"get_houses_by_community failed: {str(e)}"}
    ```

- [x] **Task 5 — `tools.py`：新增 `get_house_listings` 工具**
  - File: `tools.py`
  - Action — Schema（在 TOOLS list 末尾追加）：
    ```python
    {
        "type": "function",
        "function": {
            "name": "get_house_listings",
            "description": "获取指定房源在链家/安居客/58同城三个平台的全部挂牌记录，用于比较同一房源的跨平台价格差异。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，如 HF_1"}
                },
                "required": ["house_id"]
            }
        }
    }
    ```
  - Action — 函数实现（在文件末尾追加）：
    ```python
    async def get_house_listings(client: httpx.AsyncClient, **kwargs) -> dict:
        try:
            house_id = str(kwargs.get("house_id", ""))
            resp = await client.get(f"/api/houses/listings/{house_id}", headers=_get_headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": f"get_house_listings failed: {str(e)}"}
    ```

- [x] **Task 6 — `agent.py`：注册新工具 + 更新 SYSTEM_PROMPT + 更新 HOUSE_SEARCH_TOOLS**
  - File: `agent.py`
  - Action 6-A（imports 第 6-9 行）：在 `from tools import (...)` 中新增 `get_houses_by_community, get_house_listings`
  - Action 6-B（`HOUSE_SEARCH_TOOLS` 第 34 行）：改为 `HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark", "get_houses_by_community"}` — 使按小区名搜索的结果也以 JSON+houses 格式返回
  - Action 6-C（`TOOL_DISPATCH` 第 36-43 行）：新增两个条目：
    ```python
    "get_houses_by_community": get_houses_by_community,
    "get_house_listings": get_house_listings,
    ```
  - Action 6-D（`SYSTEM_PROMPT` 第 13-31 行）：精确改动如下：
    1. 工具使用规则部分新增两条（在 `- 查询周边生活配套` 之前）：
       - `- 按小区名查可租房源（指代消解/查某小区详情）→ 调用 get_houses_by_community`
       - `- 查同一房源在多个平台的挂牌价对比 → 调用 get_house_listings`
    2. 修改 `- 查询周边生活配套` 一条，补充参数提示：
       - 改为：`- 查询某小区周边商超/公园配套 → 调用 get_nearby_amenities（传小区名 community，不是房源ID）`
    3. `输出格式` 部分第一条，补充 `get_houses_by_community`：
       - 改为：`- 调用 search_houses、search_nearby_landmark 或 get_houses_by_community 后，用自然语言描述推荐房源，系统自动处理 JSON 格式`
  - Notes: SYSTEM_PROMPT 长度影响 token 消耗（`t = 1 + max(0, (n_tokens-1000)*0.3)`），改动保持简短，每行不超过原有风格

- [x] **Task 7 — `tests/test_tools.py`：修正 4 处过时断言**
  - File: `tests/test_tools.py`
  - Action 7-A（第 70 行）：`assert len(TOOLS) == 6` → `assert len(TOOLS) == 8`
  - Action 7-B（第 79-88 行，`test_tool_names_match_python_functions`）：`expected_names` 集合新增 `"get_houses_by_community"` 和 `"get_house_listings"`
  - Action 7-C（第 388-393 行，`test_listing_platform_in_json_body`）：
    - 函数名改为 `test_listing_platform_in_query_params`
    - 断言改为：`params = mock_client.post.call_args.kwargs.get("params", {}); assert params.get("listing_platform") == "链家"`
    - 同时确认 `json_body = mock_client.post.call_args.kwargs.get("json")` 为 None 或空
  - Action 7-D（第 308-350 行，`TestGetNearbyAmenitiesHappyPath` 全部方法）：
    - 所有调用改为 `get_nearby_amenities(mock_client, community="建清园(南区)")` 替换 `house_id="HF_1"`
    - `test_optional_category_included_when_provided`：改为传 `type="shopping"`，断言 `params.get("type") == "shopping"`
    - `test_returns_amenities`：调用参数更新为 `community="建清园(南区)"`

### Acceptance Criteria

- [x] **AC-1（execute_action 传参修复）**
  - Given：调用 `execute_action(client, action="rent", house_id="HF_1", listing_platform="安居客")`
  - When：函数向真实 API 发出 HTTP POST
  - Then：URL 为 `/api/houses/HF_1/rent`；`listing_platform=安居客` 在 query string 中（`?listing_platform=安居客`）；HTTP body 为空；API 返回 200

- [x] **AC-2（search_houses schema 完整性）**
  - Given：检查 `TOOLS` 中 `search_houses` 的 `parameters.properties`
  - When：枚举所有参数 key
  - Then：包含 `rental_type`、`bedrooms`、`area`、`elevator`、`min_area`、`max_area`、`commute_to_xierqi_max`、`sort_by`、`sort_order`；**不**包含 `room_type`；`required` 为空列表

- [x] **AC-3（get_nearby_amenities 参数对齐）**
  - Given：调用 `get_nearby_amenities(client, community="建清园(南区)", type="shopping")`
  - When：函数发出 HTTP GET
  - Then：路径为 `/api/houses/nearby_landmarks`；params 包含 `community="建清园(南区)"`、`type="shopping"`、`max_distance_m=1000`；带 X-User-ID header

- [x] **AC-4（get_nearby_amenities 默认 max_distance_m）**
  - Given：调用 `get_nearby_amenities(client, community="建清园(南区)")` 不传 `max_distance_m`
  - When：函数发出 HTTP GET
  - Then：params 中 `max_distance_m=1000`（而非 API 默认的 3000）

- [x] **AC-5（get_houses_by_community 注册与实现）**
  - Given：TOOLS 含 `get_houses_by_community`；调用 `get_houses_by_community(client, community="智学苑")`
  - When：函数发出 HTTP GET
  - Then：路径为 `/api/houses/by_community`；params 含 `community="智学苑"`；带 X-User-ID header；`required` 为 `["community"]`

- [x] **AC-6（get_house_listings 注册与实现）**
  - Given：TOOLS 含 `get_house_listings`；调用 `get_house_listings(client, house_id="HF_1")`
  - When：函数发出 HTTP GET
  - Then：路径为 `/api/houses/listings/HF_1`；带 X-User-ID header；响应 data.items 包含三平台记录

- [x] **AC-7（agent.py 路由完整）**
  - Given：agent 收到 LLM 生成的 `tool_call.function.name = "get_houses_by_community"`
  - When：`TOOL_DISPATCH.get(tool_name)` 查找
  - Then：返回函数引用（非 None），不触发 `{"error": "Unknown tool: ..."}`

- [x] **AC-8（SYSTEM_PROMPT 引导正确）**
  - Given：用户问"这个小区还有别的房源吗？"
  - When：LLM 读取 SYSTEM_PROMPT
  - Then：SYSTEM_PROMPT 含 `get_houses_by_community` 的使用引导，LLM 能选择正确工具

- [x] **AC-9（get_nearby_amenities SYSTEM_PROMPT 引导）**
  - Given：SYSTEM_PROMPT 中 `get_nearby_amenities` 的说明
  - When：LLM 需要查询周边配套
  - Then：说明明确提示传入 `community`（小区名）而非 house_id，避免参数传错

- [x] **AC-10（tests 全部通过）**
  - Given：修改完成后运行 `pytest tests/test_tools.py -v`
  - Then：所有 test 通过，0 FAILED，包括修正后的 `test_tools_has_six_entries`（现为 8）、`test_listing_platform_in_query_params`、`TestGetNearbyAmenitiesHappyPath` 全部方法

## Additional Context

### Dependencies

无新增外部依赖，全部使用已有 `httpx`、`os`

### Testing Strategy

**修正现有测试（Task 7，4处改动）：**
- `tests/test_tools.py`：7-A 改数量断言；7-B 更新函数名集合；7-C 改 execute_action 传参断言；7-D 改 get_nearby_amenities 测试调用参数
- 运行命令：`pytest tests/test_tools.py -v`

**手动验证顺序（高价值）：**
1. 先验 Task 1（execute_action）：直接对真实 API 发 POST，观察是否返回 200 而非 400
2. 验 Task 2（search_houses）：用 `commute_to_xierqi_max=30` 过滤，观察结果
3. 验 Task 3（get_nearby_amenities）：传正确 community，观察返回

### Notes

**风险点：**
- `get_nearby_amenities` 的 `required` 从 `[]` 改为 `["community"]`，已有测试中会有影响，Task 7-D 需全部覆盖
- `HOUSE_SEARCH_TOOLS` 加入 `get_houses_by_community` 后，LLM 按小区名搜索的回复也会走 JSON+houses 格式，需确认 agent 的 houses 提取正则 `r'HF_\d+'` 能从 `get_houses_by_community` 结果中正确提取
- SYSTEM_PROMPT token 预算：当前系统提示约 180 tokens，新增 3 行约 +30 tokens，在 1000 token 阈值内安全
- March 3rd spec 更新后，可能需要再次调整 `search_houses` schema（`available_from_before` 格式等）

**不在本次迭代内但值得跟踪：**
- `search_nearby_landmark` 无分页逻辑（仅取第 1 页），若结果超 10 条会遗漏
- 接口12（`/api/houses/stats`）未暴露为工具，对"有多少可租房源"类问题无法精准回答
