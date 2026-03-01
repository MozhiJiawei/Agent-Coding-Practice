---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
lastStep: 8
status: 'complete'
completedAt: '2026-03-01'
inputDocuments:
  - _bmad-output/planning-artifacts/prd-test-simulator.md
  - _bmad-output/planning-artifacts/prd-validation-report-test-simulator.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/project-context.md
  - docs/index.md
  - docs/interface.md
  - docs/interface_simulate.md
  - docs/task.md
workflowType: 'architecture'
project_name: 'AI Agent Coding - Test Simulator'
user_name: 'LJW'
date: '2026-03-01'
---

# Architecture Decision Document — 测试仿真器 (Test Simulator)

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Design Principles

1. **接口行为一致性：** 模拟所有工具调用接口，行为与 docs/interface_simulate.md 完全一致
2. **简化实现：** 不考虑并发运行、user-id 检查、session-id 隔离等需求，有需要时再添加
3. **可配置测试与报告：** 测试用例通过配置文件驱动，执行后输出测试报告

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
23 个 FR，按设计原则重新分级：

**核心（必须做好）：**
- **Mock 租房 API（FR10-16）：** 实现全部 15 个端点，响应格式与 `docs/interface_simulate.md` 的 OpenAPI 规范逐字段一致，包括动态筛选、分页、地理距离计算、三平台定价、状态变更操作（rent/terminate/offline/init）
- **测试用例配置与判定（FR17-23）：** YAML 配置驱动，支持 Chat/Single/Multi 类型，多种判定规则（JSON 有效性、houses 匹配），CLI 执行，输出测试报告

**必须有但简单实现：**
- **Chat 驱动（FR1-5）：** HTTP 客户端向 Agent 发送消息、接收响应，串行逐轮发送
- **模型代理（FR6-9）：** 监听端口接收 Agent 模型请求，透传至外部 LLM

**延迟/简化处理：**
- ~~per X-User-ID 状态隔离~~：使用固定 user-id，全局单一状态
- ~~session-id 隔离验证~~：runner 生成唯一 session_id 即可，不做隔离检查
- ~~并发执行~~：串行运行所有用例
- ~~时间片计算与预算控制~~（FR23）

**Non-Functional Requirements:**
按简化原则筛选后保留的关键 NFR：
- **NFR4：** 仿真服务响应格式与真实 API 完全兼容（**最重要**）
- **NFR5：** 模型代理与 OpenAI Chat Completions 格式兼容
- **NFR6：** 无网络环境下仿真服务可独立启动和响应
- **NFR7：** 新用例 5 分钟内可添加
- **NFR8：** 人类可读测试报告
- **NFR10：** Mock 未匹配不返回 5xx

**降低优先级的 NFR：**
- ~~NFR1 超时控制~~：串行执行，简单 timeout 即可
- ~~NFR2 模型代理延迟 < 100ms~~：不做性能优化
- ~~NFR9 四级错误归因~~：简化为基本错误日志
- ~~NFR11 异常退出保存结果~~：简化实现不考虑

**Scale & Complexity:**
- Primary domain: Python CLI 测试工具 + HTTP Mock 服务
- Complexity level: Low-Medium（简化后）
- Estimated architectural components: 4（Test Runner、Model Proxy、Mock Rental API、Config/Fixture Loader）

### Technical Constraints & Dependencies

- **接口行为一致性（第一原则）：** 仿真 API 的 15 个端点、所有查询参数、响应字段、错误码、分页结构必须与 `docs/interface_simulate.md` 完全对齐
- **与 Agent 零修改对接：** Agent 通过 `model_ip` 指向仿真器模型代理，通过 `RENTAL_API_BASE` 指向仿真器 Mock API
- **模型代理需外部 LLM：** 租房 API 完全本地仿真，但模型代理仍需转发至真实 LLM
- **数据格式约束：** 响应统一 `{"code": 0, "message": "success", "data": {...}}`，分页 `{total, page, page_size, items}`
- **三平台定价：** 安居客(100%) / 链家(92%) / 58同城(78%)，用简单比例系数实现
- **已有代码：** `test-simulator/` 已有 mock_rental.py、model_proxy.py、runner.py、config.py，架构需对齐现有结构

### Cross-Cutting Concerns Identified

1. **配置管理** — 全局配置（端口、URL）+ 用例配置（messages、expect）+ fixture 数据，三层配置统一管理
2. **Fixture 数据完整性** — 地标 + 房源数据需支持全部查询参数和筛选逻辑，这是 Mock API 行为正确性的基础
3. **响应格式一致性** — 仿真 API 响应必须与真实 API 逐字段对齐（核心关注点）

## Starter Template Evaluation

### Primary Technology Domain

Python CLI 测试工具 + HTTP Mock 服务（Brownfield — 已有部分实现代码）

### Starter Options Considered

| 选项 | 评估 |
|------|------|
| 外部 Mock 框架（wiremock / responses / respx） | 不适用：这些框架做"HTTP 客户端 Mock"（拦截请求），而我们需要"HTTP 服务端 Mock"（启动真实 HTTP 服务供 Agent 调用） |
| Connexion / Prism（OpenAPI-driven Mock） | 过重：只能返回 OpenAPI examples 中的静态数据，无法实现动态筛选和状态变更 |
| 现有代码结构 + 架构调整 | ✅ 选定：保留 FastAPI + Pydantic + asyncio 框架，将 mock_rental.py 从静态规则匹配重构为程序化端点实现 |

### Selected Starter: 现有代码结构 + 架构调整

**Rationale for Selection:**
现有技术栈（FastAPI + httpx + Pydantic + asyncio）完全正确，模块分工合理。核心问题仅在于 mock_rental.py 需从"静态规则匹配"转为"程序化逻辑"。无需引入新框架。

**关键架构调整：** 当前 mock_rental.py 使用 `MockRule`（path + method + params_match → 静态 response）的规则匹配方式，无法实现动态筛选（20+ 查询参数）、分页、状态变更、地理距离计算。需重构为程序化端点，用 Python 代码实现每个 API 的实际业务逻辑，基于内存 fixture 数据集动态计算响应。

**Architectural Decisions Provided by Existing Code:**

**Language & Runtime:** Python 3.11+，asyncio 贯穿全链路

**HTTP 服务框架:** FastAPI（mock_rental + model_proxy 各一个独立 app，由 main.py 用 uvicorn 启动）

**HTTP 客户端:** httpx.AsyncClient（runner → Agent、model_proxy → LLM、mock_rental 透传模式）

**配置管理:** Pydantic BaseModel + PyYAML，三层：config.yaml（全局）、test_cases.yaml（用例）、mock_data/（fixture）

**Code Organization:**
- `main.py` — CLI 入口 + 服务编排
- `config.py` — Pydantic 模型 + YAML 加载
- `model_proxy.py` — LLM 代理转发（已完成，无需重构）
- `mock_rental.py` — 租房 API 仿真（**需重构**：静态规则 → 程序化端点）
- `runner.py` — 测试执行 + 断言 + 报告（**需完善**：当前为 stub）

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Mock 租房 API 实现策略：独立 FastAPI 路由处理器
- Fixture 数据格式：YAML 原始数据（house list + landmark list），代码负责筛选和组装响应
- 状态管理：全局 dict，不做 per-user 隔离

**Important Decisions (Shape Architecture):**
- 断言引擎：规则名 → 检查函数的 dict 映射
- 测试报告：控制台文本 + JSON 文件双输出

**Deferred Decisions (Post-MVP):**
- per X-User-ID 状态隔离
- 并发用例执行
- 时间片计算与预算控制
- HTML 报告生成

### Mock 租房 API 架构

**决策：独立 FastAPI 路由处理器**

重构 `mock_rental.py`，为每个 API 端点编写独立的 FastAPI 路由函数，利用 FastAPI 原生 Query 参数声明实现类型解析和默认值。每个路由内部用 Python 代码基于内存中的 fixture 数据集动态计算响应。

**15 个端点分组：**

| 分组 | 端点 | 实现复杂度 |
|------|------|-----------|
| 地标（无状态） | `GET /api/landmarks`、`/name/{name}`、`/search`、`/{id}`、`/stats` | 低：纯筛选 |
| 房源查询 | `GET /api/houses/{id}`、`/listings/{id}`、`/by_community`、`/by_platform`、`/nearby`、`/nearby_landmarks`、`/stats` | 中-高：动态筛选 + 分页 + 地理计算 |
| 房源操作 | `POST /api/houses/init`、`/{id}/rent`、`/{id}/terminate`、`/{id}/offline` | 低：状态变更 |

**动态筛选实现（by_platform 端点 — 最复杂）：**
接收全部 20+ Query 参数，在内存 fixture 列表上逐条过滤：
```python
@app.get("/api/houses/by_platform")
async def houses_by_platform(
    listing_platform: str | None = None,
    district: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    bedrooms: str | None = None,
    sort_by: str | None = None,
    page: int = 1,
    page_size: int = 10,
    # ... 其余参数
):
    results = [h for h in fixtures if h["status"] == "available"]
    if district:
        results = [h for h in results if h["district"] in district.split(",")]
    if min_price:
        results = [h for h in results if h["price"] >= min_price]
    # ... 逐参数过滤
    # 排序 + 分页 + 平台定价 → 返回标准响应格式
```

**三平台定价：**
Fixture 数据存储安居客基准价。查询时按 `listing_platform` 参数应用系数：
- 安居客：× 1.00（原价）
- 链家：× 0.92
- 58同城：× 0.78

未传 `listing_platform` 时默认返回安居客数据。

**地理距离计算（nearby 端点）：**
基于地标和房源的经纬度坐标，用 Haversine 公式计算直线距离（米），筛选 `max_distance` 范围内的可租房源，计算并返回 `distance_to_landmark`、`walking_distance`（直线距离 × 1.3）、`walking_duration`（步行距离 ÷ 80 米/分钟）。

**响应格式（统一）：**
所有端点返回 `{"code": 0, "message": "success", "data": {...}}`；分页端点 data 包含 `{total, page, page_size, items}`；错误返回 `{"code": 400/404, "message": "..."}`。

### Fixture 数据架构

**决策：YAML 原始数据格式**

重新设计 `mock_data/default.yaml`，从静态 MockRule 格式改为原始数据格式：

```yaml
landmarks:
  - id: "SS_001"
    name: "西二旗站"
    category: "subway"
    district: "海淀"
    longitude: 116.3289
    latitude: 40.0567
    details:
      lines: ["13号线", "昌平线"]
      type: "transfer"
      # ... 其余字段与真实 API 一致

houses:
  - house_id: "HF_1"
    community: "中国铁建原香汇"
    district: "房山"
    area: "房山城关"
    price: 2250          # 安居客基准价
    status: "available"  # 初始状态
    longitude: 116.1458
    latitude: 39.7322
    # ... 其余字段与真实 API 返回的 house 对象完全一致
```

**数据规模要求：**
- 地标 ≥ 20 条（覆盖 subway/company/landmark 三类，≥ 5 个行政区）
- 房源 ≥ 30 条（≥ 6 个行政区，含 1/2/3 居室，整租 + 合租，价格跨度 1500–15000，初始约 90% available / 5% rented / 5% offline）

**数据来源：** 可从 `docs/interface_simulate.md` 接口调用示例中提取真实响应数据作为 fixture 种子。

### 状态管理

**决策：全局单一状态，不做 user 隔离**

```python
class MockState:
    def __init__(self, fixtures: list[dict]):
        self.houses = {h["house_id"]: dict(h) for h in fixtures}

    def init(self):
        """重置所有房源状态至 fixture 初始值"""
        for hid, h in self.houses.items():
            h["status"] = h.get("_initial_status", "available")

    def update_status(self, house_id: str, new_status: str) -> dict | None:
        h = self.houses.get(house_id)
        if h:
            h["status"] = new_status
            return h
        return None
```

- `POST /api/houses/init` → `state.init()` 重置全部
- `POST /api/houses/{id}/rent` → `state.update_status(id, "rented")`
- `POST /api/houses/{id}/terminate` → `state.update_status(id, "available")`
- `POST /api/houses/{id}/offline` → `state.update_status(id, "offline")`

### 断言引擎

**决策：规则名 → 检查函数映射**

在 `runner.py` 中实现：

```python
def check_assertions(response: dict, expect: ExpectRules) -> tuple[bool, str]:
    """逐条检查 expect 规则，第一个失败即返回 (False, reason)"""
    resp_text = response.get("response", "")

    if expect.has_response and not response:
        return False, "no response received"
    if expect.response_not_empty and not resp_text:
        return False, "response is empty"
    if expect.response_json_valid:
        try:
            json.loads(resp_text)
        except:
            return False, f"response is not valid JSON: {resp_text[:100]}"
    if expect.houses_match is not None:
        actual = extract_house_ids(resp_text)
        expected = set(expect.houses_match)
        if actual != expected:
            return False, f"houses_match: expected {expected}, got {actual}"
    # ... 其余规则
    return True, ""
```

`extract_house_ids()` 从 response 字段中解析 JSON，提取 `houses` 数组中的 ID 列表。

### 测试报告

**决策：控制台文本 + JSON 双输出**

**控制台输出格式：**
```
[sim] Running 5 test cases...

[1/5] chat_hello ............ PASS  (1.2s)
[2/5] single_haidian ........ PASS  (3.5s)
[3/5] multi_progressive ..... FAIL  (5.1s)
      ✗ houses_match: expected {HF_42, HF_107}, got {HF_42}
[4/5] single_nearby ......... PASS  (2.8s)
[5/5] chat_goodbye .......... PASS  (0.9s)

Results: 4 passed, 1 failed, 0 errors  (13.5s total)
```

**JSON 报告（写入 report_dir）：**
包含每个 `CaseResult` 的完整信息（case_id, status, duration_ms, failure_reason, actual_response, token_usage）。

### Decision Impact Analysis

**Implementation Sequence:**
1. Fixture 数据设计与加载（mock_data/default.yaml 重新设计）
2. MockState 状态管理类
3. mock_rental.py 重构（15 个端点的程序化实现）
4. runner.py 断言引擎 + 报告生成
5. main.py 集成（--all 模式 + 报告输出）

**Cross-Component Dependencies:**
- mock_rental.py 依赖 fixture 数据格式和 MockState
- runner.py 依赖 config.py 的 ExpectRules 和 CaseResult 模型
- main.py 编排 runner + mock_rental + model_proxy 的生命周期

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified：** 5 个区域

### Naming Patterns

**Python 命名约定（全局）：**
- 函数/变量：`snake_case`（如 `houses_by_platform`, `max_distance`）
- 模块级常量：`ALL_CAPS`（如 `PRICE_RATIO`, `DEFAULT_PAGE_SIZE`）
- Pydantic 模型：`PascalCase`（如 `SimulatorConfig`, `CaseResult`）
- 文件名：`snake_case.py`

**API 响应字段命名（必须与真实 API 完全一致）：**
- 全部 `snake_case`：`house_id`, `subway_distance`, `listing_platform`, `walking_duration`
- 地标 ID 格式：`SS_xxx`（subway）、`F500_xxx`（company）、`LM_xxx`（landmark）
- 房源 ID 格式：`HF_xxx`（永远字符串，不转整数）

### Format Patterns

**API 响应格式（最高优先级规则 — 必须与 docs/interface_simulate.md 逐字段一致）：**

成功 — 单条数据：`{"code": 0, "message": "success", "data": {对象}}`
成功 — 分页列表：`{"code": 0, "message": "success", "data": {"total": N, "page": P, "page_size": S, "items": [...]}}`
成功 — 统计类：`{"code": 0, "message": "success", "data": {统计对象}}`

错误响应：
- 缺 X-User-ID：`{"code": 400, "message": "请提供请求头 X-User-ID 以标识当前用户"}`
- 缺 listing_platform：`{"code": 400, "message": "请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台"}`
- 房源不存在：`{"code": 404, "message": "未找到房源 {house_id}"}`

nearby 端点额外字段：每条 house 额外包含 `distance_to_landmark`（米，整数）、`walking_distance`（米，整数）、`walking_duration`（分钟，整数）。

### Structure Patterns

**mock_rental.py 路由处理器统一模式：**
1. 从 app.state.mock_state 获取数据
2. 过滤（仅 available + 各条件）
3. 排序（如有 sort_by）
4. 应用平台定价（如有 listing_platform）
5. 分页切片
6. 返回标准响应格式

**MockState 通过 app.state 注入，不用全局变量。**

### Process Patterns

**筛选执行顺序（by_platform 端点）：**
1. 过滤 status == "available"
2. 逐参数过滤（district, area, price, bedrooms 等）
3. 排序（sort_by + sort_order）
4. 应用平台定价系数
5. 计算 total（分页前的结果总数）
6. 分页切片

**平台定价：** 筛选时用安居客基准价比较 min_price/max_price；返回时按平台系数调整 price 和 listing_platform 字段。

**rent/terminate/offline：** 未传 listing_platform → 400；已传 → 执行状态变更，返回变更后 house。

### Enforcement Guidelines

**All AI Agents MUST：**
- 响应字段名、类型、嵌套结构与 docs/interface_simulate.md 完全一致
- 房源查询默认只返回 status == "available"
- 未传 listing_platform 时默认返回安居客数据
- 分页默认 page=1, page_size=10
- 错误响应 message 文本与真实 API 一致

**Anti-Patterns（禁止）：**
- 返回非标准格式（如直接返回 list 而非 {code, message, data} 包装）
- fixture 中存储三套平台数据（应只存安居客基准价，运行时乘系数）
- 忽略 listing_platform 未传时的默认行为
- nearby 端点不返回距离字段

## Project Structure & Boundaries

### Complete Project Directory Structure

```
test-simulator/
├── main.py                    # CLI 入口 + asyncio 服务编排 + 生命周期管理
├── config.py                  # Pydantic 数据模型 + YAML 配置/用例/fixture 加载
├── model_proxy.py             # Model Proxy FastAPI 应用（已完成，无需改动）
├── mock_rental.py             # Mock 租房 API FastAPI 应用（重构：程序化端点实现）
├── runner.py                  # Test Runner：Chat 客户端 + 断言引擎 + 报告生成
├── config.yaml                # 全局配置（端口、URL、超时等）
├── test_cases.yaml            # 测试用例定义（messages + expect 规则）
└── mock_data/
    └── default.yaml           # Fixture 数据（landmarks + houses 原始数据）
```

### Architectural Boundaries

**外部边界（仿真器对外提供的 HTTP 服务）：**
```
Agent (localhost:8191)
    ├── 模型请求 → Model Proxy (:8888)  POST /v1/chat/completions
    │                  │
    │                  ▼
    │              外部 LLM (llm_proxy_url)
    │
    └── 工具调用 → Mock Rental API (:8080)  /api/landmarks/*, /api/houses/*
                       │
                       └── 内存 fixture 数据（零外部依赖）

Test Runner (main.py)
    └── 用户请求 → Agent (:8191)  POST /api/v1/chat
```

**模块职责边界：**

| 文件 | 职责 | 禁止包含 |
|------|------|---------|
| `main.py` | CLI 参数解析、asyncio 服务启动/关闭编排、调用 runner 执行用例 | API 路由定义、断言逻辑、fixture 数据处理 |
| `config.py` | Pydantic 模型定义、YAML 加载函数、TokenCounter | HTTP 服务逻辑、断言逻辑 |
| `model_proxy.py` | `/v1/chat/completions` 转发、token 统计 | 租房 API 逻辑、测试执行逻辑 |
| `mock_rental.py` | 15 个租房 API 端点实现、MockState 状态管理、fixture 数据筛选/分页/定价/距离计算 | 模型转发、测试执行、断言 |
| `runner.py` | 向 Agent 发送消息、接收响应、断言检查、报告生成 | API 路由定义、fixture 数据处理 |

### Requirements to Structure Mapping

| FR 分组 | 具体位置 | 关键实现 |
|---------|---------|---------|
| FR1-5（Chat 驱动） | `runner.py` + `main.py` | httpx POST /api/v1/chat，逐轮发送 |
| FR6-9（模型代理） | `model_proxy.py` | FastAPI POST /v1/chat/completions，透传 + token 统计 |
| FR10（15 端点 Mock） | `mock_rental.py` | 独立 FastAPI 路由处理器 |
| FR11（动态筛选） | `mock_rental.py:houses_by_platform()` | 20+ Query 参数逐条过滤 |
| FR12（nearby 距离） | `mock_rental.py:houses_nearby()` | Haversine 公式 + 距离字段 |
| FR13（状态变更） | `mock_rental.py:MockState` | init/rent/terminate/offline |
| FR14（fixture 数据） | `mock_data/default.yaml` + `config.py` | YAML 原始数据加载 |
| FR15（错误码） | `mock_rental.py` 各路由 | 400/404 标准错误响应 |
| FR16（三平台定价） | `mock_rental.py` 筛选/返回逻辑 | PRICE_RATIO 系数 |
| FR17-20（用例配置） | `test_cases.yaml` + `config.py` | YAML 加载 + Pydantic 校验 |
| FR21-22（断言+CLI） | `runner.py` + `main.py` | check_assertions() + --case/--all/--tag |
| NFR8（测试报告） | `runner.py` | 控制台文本 + JSON 文件 |

### Integration Points

**内部通信（模块间）：**
- `main.py` → `config.py`：调用 load_config(), load_test_cases(), load_fixtures()
- `main.py` → `mock_rental.py`：调用 create_mock_rental_app(config, fixtures)
- `main.py` → `model_proxy.py`：调用 create_model_proxy_app(config, token_counter)
- `main.py` → `runner.py`：调用 run_all_cases(cases, config, token_counter)
- 共享状态：TokenCounter 由 main.py 创建，注入 model_proxy 和 runner

**外部集成：**
- Model Proxy → 外部 LLM：httpx.AsyncClient.post(config.llm_proxy_url)
- Test Runner → Agent：httpx.AsyncClient.post(config.agent_base_url + "/api/v1/chat")
- Mock Rental → 无外部依赖（纯内存 fixture）
- Mock Rental 透传模式（可选）→ 真实租房 API：config.rental_passthrough_url

### Development Workflow

**启动服务（手动测试）：** `python main.py`
**执行单个用例：** `python main.py --case chat_hello`
**执行全部用例：** `python main.py --all`
**按标签筛选：** `python main.py --tag smoke`

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility：** 全部技术选型（FastAPI + httpx + Pydantic + asyncio + PyYAML）原生兼容，无冲突。FastAPI 的 Query 参数声明天然适配 Mock API 的 20+ 查询参数场景。

**Pattern Consistency：** snake_case 命名贯穿 Python 代码和 API 字段；MockState 通过 app.state 注入模式与 model_proxy 已有实现一致；响应格式统一 {code, message, data} 包装。

**Structure Alignment：** 5 文件模块结构与 4 个架构组件（Runner、Model Proxy、Mock Rental、Config）清晰对应，模块职责边界无重叠。

### Requirements Coverage Validation ✅

**Functional Requirements Coverage：** 23/23 FR 全部覆盖（详见 Requirements to Structure Mapping 表）。

**Non-Functional Requirements Coverage：** 6 个保留的关键 NFR 全部有架构支撑：
- NFR4（格式兼容）→ Format Patterns 强制规则
- NFR5（OpenAI 兼容）→ model_proxy.py 已实现
- NFR6（离线启动）→ 纯内存 fixture，零外部依赖
- NFR7（5分钟加用例）→ YAML 配置 + Pydantic 校验
- NFR8（可读报告）→ 控制台文本 + JSON 双输出
- NFR10（无 5xx）→ Anti-Patterns 规则

### Gap Analysis Results

**无 Critical Gap。**

**Important Gap — config.py 模型更新：**
当前 `config.py` 中的 `MockRule` 模型和 `load_mock_data()` 函数基于静态规则匹配设计，需替换为 fixture 数据加载：
- 移除 `MockRule` 模型
- 新增 `load_fixtures(path) -> dict`，返回 `{"landmarks": [...], "houses": [...]}`
- `MockState` 类可定义在 `mock_rental.py` 中（与其使用者共处）

**Nice-to-Have Gap — Fixture 数据种子：**
`docs/interface_simulate.md` 的接口调用示例包含大量真实响应数据，可作为 fixture 种子提取，减少手工编写数据量。

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] 项目上下文深度分析（23 FR + 11 NFR，按设计原则分级）
- [x] 规模与复杂度评估（Low-Medium）
- [x] 技术约束识别（接口一致性、零修改对接、三平台定价）
- [x] 横切关注点映射（配置管理、fixture 完整性、响应格式一致性）

**✅ Architectural Decisions**
- [x] Mock 租房 API 策略：独立 FastAPI 路由 + 程序化逻辑
- [x] Fixture 数据格式：YAML 原始数据（landmarks + houses）
- [x] 状态管理：全局 MockState，不做 user 隔离
- [x] 断言引擎：规则名 → 检查函数 dict 映射
- [x] 测试报告：控制台文本 + JSON 双输出

**✅ Implementation Patterns**
- [x] 命名约定（Python snake_case + API 字段与真实 API 一致）
- [x] 响应格式规则（{code, message, data} 包装，分页结构，错误码）
- [x] 路由处理器统一模式（过滤→排序→定价→分页→返回）
- [x] 平台定价规则（基准价 × 系数）
- [x] Enforcement Guidelines + Anti-Patterns

**✅ Project Structure**
- [x] 完整目录结构（8 个文件/目录）
- [x] 模块职责边界（5 文件，禁止事项明确）
- [x] 集成点映射（内部调用链 + 外部 API）
- [x] FR 到结构映射完整

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION ✅

**Confidence Level:** High — 架构决策完整且简洁，与设计原则高度对齐，AI Agent 可据此直接实现。

**Key Strengths:**
- 设计原则驱动的简化：聚焦接口行为一致性，去除不必要的复杂度
- 现有代码对齐：保留已验证的技术栈和模块结构，仅重构必要部分
- 实现路径清晰：mock_rental.py 重构 + runner.py 完善 + fixture 数据设计，三条主线独立

**Areas for Future Enhancement：**
- per X-User-ID 状态隔离（设计原则 #2 明确延迟）
- 并发用例执行
- HTML 报告生成
- 时间片计算与预算控制

### Implementation Handoff

**AI Agent Guidelines：**
- 读取本文档 + PRD + docs/interface_simulate.md 后开始实现
- Mock API 响应格式必须与 docs/interface_simulate.md 接口调用示例逐字段对齐
- fixture 数据可从 docs/interface_simulate.md 示例中提取种子数据
- model_proxy.py 已完成，无需改动

**Implementation Sequence：**
1. 重新设计 mock_data/default.yaml（landmarks + houses 原始数据）
2. 更新 config.py（移除 MockRule，新增 load_fixtures）
3. 重构 mock_rental.py（独立路由 + MockState + 动态筛选/分页/定价/距离）
4. 完善 runner.py（断言引擎 + 报告生成）
5. 更新 main.py（--all/--tag 支持 + 报告输出）
