---
title: 'tools.py 接口对齐重写'
slug: 'tools-py-interface-alignment'
created: '2026-03-01'
status: 'in-progress'
stepsCompleted: [1, 2]
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

**Task 1 — `tools.py`：修正 `execute_action` 传参方式（最高优先级，1 处改动）**
- 文件：`tools.py`，行 266-271
- 动作：将 `json={"listing_platform": listing_platform}` 改为 `params={"listing_platform": listing_platform}`
- 验证：`POST /api/houses/{house_id}/rent?listing_platform=安居客` 应返回 200

**Task 2 — `tools.py`：修正 `search_houses` TOOLS schema**
- 文件：`tools.py`，TOOLS list 中 `search_houses` 的 `parameters.properties`
- 动作：
  - 删除 `room_type` 字段
  - 新增字段：`rental_type`、`bedrooms`、`area`、`elevator`、`min_area`、`max_area`、`property_type`、`subway_line`、`subway_station`、`utilities_type`、`available_from_before`、`commute_to_xierqi_max`、`sort_by`、`sort_order`
  - 参数描述与 API 文档保持一致
- 注意：函数实现（`async def search_houses`）使用 `**kwargs` 透传，参数名对齐后无需改动函数体

**Task 3 — `tools.py`：重构 `get_nearby_amenities` schema 和实现**
- 文件：`tools.py`，TOOLS list 中 `get_nearby_amenities` + `async def get_nearby_amenities`
- Schema 改动：
  - 删除 `house_id` 字段，新增 `community: {type: string, description: "小区名，用于定位基准点"}`
  - 将 `category` 改为 `type: {type: string, enum: ["shopping", "park"], description: "地标类型：shopping(商超)/park(公园)"}`
  - 保留 `max_distance_m`（默认 1000）
- 函数改动：移除 `house_id` 相关逻辑，直接透传 `community`, `type`, `max_distance_m` 到 API

**Task 4 — `tools.py`：新增 `get_houses_by_community` 工具**
- 文件：`tools.py`，在 TOOLS list 末尾新增 schema + 文件末尾新增函数
- Schema：`name="get_houses_by_community"`，参数：`community`（必填）、`listing_platform`（可选）、`page`（可选）、`page_size`（可选）
- 函数：`GET /api/houses/by_community`，带 X-User-ID header，透传所有非 None 参数
- 用途说明（description）：按小区名查询可租房源，用于指代消解或查某小区详情

**Task 5 — `tools.py`：新增 `get_house_listings` 工具**
- 文件：`tools.py`，在 TOOLS list 末尾新增 schema + 文件末尾新增函数
- Schema：`name="get_house_listings"`，参数：`house_id`（必填）
- 函数：`GET /api/houses/listings/{house_id}`，带 X-User-ID header，响应包含三平台挂牌价对比
- 用途说明：获取同一房源在链家/安居客/58同城的全部挂牌记录（价格可能不同）

**Task 6 — `agent.py`：注册新增工具并更新 SYSTEM_PROMPT**
- 文件：`agent.py`
- 改动 1：imports 行新增 `get_houses_by_community, get_house_listings`
- 改动 2：`TOOL_DISPATCH` dict 新增两个条目
- 改动 3：`SYSTEM_PROMPT` 工具使用规则部分新增说明：
  - 按小区名查可租房源 → 调用 `get_houses_by_community`
  - 查同一房源多平台挂牌价 → 调用 `get_house_listings`

**Task 7 — `tests/test_tools.py`：修正过时断言**
- 文件：`tests/test_tools.py`
- 改动 1：`test_tools_has_six_entries` → 改为 8（新增 2 个工具后）
- 改动 2：`test_listing_platform_in_json_body` → 改为 `test_listing_platform_in_query_params`，验证 `params` 而非 `json`
- 改动 3：`TestGetNearbyAmenitiesHappyPath` 中所有传 `house_id=` 的测试 → 改为传 `community="建清园(南区)"`；`category="公园"` → `type="park"` 等
- 改动 4：`test_tool_names_match_python_functions` → `expected_names` 新增 `get_houses_by_community` 和 `get_house_listings`

### Acceptance Criteria

**AC-1（execute_action）**
- Given：调用 `execute_action(client, action="rent", house_id="HF_1", listing_platform="安居客")`
- When：发出 HTTP POST 请求
- Then：请求 URL 为 `/api/houses/HF_1/rent`，`listing_platform=安居客` 在 query params 中，JSON body 为空

**AC-2（search_houses schema）**
- Given：TOOLS 中 `search_houses` 的 schema
- When：检查参数列表
- Then：包含 `rental_type`、`bedrooms`、`area`、`elevator`、`min_area`、`max_area`、`commute_to_xierqi_max`、`sort_by`、`sort_order`；不包含 `room_type`

**AC-3（get_nearby_amenities）**
- Given：调用 `get_nearby_amenities(client, community="建清园(南区)", type="shopping")`
- When：发出 HTTP GET 请求
- Then：请求路径为 `/api/houses/nearby_landmarks`，params 含 `community="建清园(南区)"` 和 `type="shopping"`，默认 `max_distance_m=1000`

**AC-4（get_houses_by_community）**
- Given：TOOLS 含 `get_houses_by_community`；调用 `get_houses_by_community(client, community="智学苑")`
- When：发出 HTTP GET 请求
- Then：路径为 `/api/houses/by_community`，params 含 `community="智学苑"`，带 X-User-ID header

**AC-5（get_house_listings）**
- Given：TOOLS 含 `get_house_listings`；调用 `get_house_listings(client, house_id="HF_1")`
- When：发出 HTTP GET 请求
- Then：路径为 `/api/houses/listings/HF_1`，带 X-User-ID header，返回三平台挂牌列表

**AC-6（agent.py dispatch）**
- Given：LLM 生成 tool_call `get_houses_by_community`
- When：agent loop 处理此 tool call
- Then：`TOOL_DISPATCH` 能正确路由，不返回 `{"error": "Unknown tool: ..."}`

**AC-7（tests 通过）**
- Given：运行 `pytest tests/test_tools.py`
- Then：所有测试通过，无 FAILED

## Additional Context

### Dependencies

无新增外部依赖（全部使用已有 httpx）

### Testing Strategy

- 修正 `tests/test_tools.py` 中现有不对齐断言（7 处）
- 不新增测试类，仅修正已有测试
- 运行命令：`pytest tests/test_tools.py -v`

### Notes

- 真实测试日志（`interface_simulate.md` 末尾）scenarios 17-19 返回 400，scenario 20 返回 200：差异在于 scenario 20 的 request body 已被修正为 query param（可能是测试脚本的修正版）
- `agent.py` 中 `HOUSE_SEARCH_TOOLS` 目前只含搜索工具；`get_houses_by_community` 也返回房源列表，可考虑加入集合——但当前 agent response 格式处理逻辑与此相关，保守起见暂不修改
- March 3rd 后比赛 spec 可能更新（project-context.md 提示），tools.py 模块化设计便于快速响应
