---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-12-complete']
classification:
  projectType: cli_tool + api_backend
  domain: Testing / Developer Tooling
  complexity: medium
  projectContext: brownfield-code
  prdPurpose: implementation-spec
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - docs/interface.md
  - docs/interface_simulate.md
  - docs/task.md
  - main.py
  - agent.py
  - tools.py
documentCounts:
  briefCount: 0
  researchCount: 0
  brainstormingCount: 0
  projectDocsCount: 7
workflowType: 'prd'
---

# Product Requirements Document — Test Environment Simulator

**Author:** LJW
**Date:** 2026-02-27
**Related PRD:** `prd.md`（AI Agent Coding 主项目）

## Executive Summary

本项目为 AI Agent Coding 竞赛项目的**本地端到端测试框架**。目标是构建一套可在开发者本机完整运行的测试环境，无需依赖竞赛远端服务（租房仿真 API 和 LLM 网关），即可对 Agent 进行功能验证和回归测试。

**核心架构：三组件协同**

| 组件 | 职责 | 运行方式 |
|---|---|---|
| **Mock Rental API Server** | 模拟竞赛 15 个租房仿真端点，基于本地 YAML 配置返回房源/地标数据 | FastAPI 服务，可配置端口 |
| **LLM Proxy Server** | 监听 `{model_ip}:8888`，透传 Agent 的 OpenAI 兼容请求至后端云平台 qwen3 API | FastAPI 服务，固定端口 8888 |
| **Test Runner** | 按 YAML 用例定义调用 Agent 的 `POST /api/v1/chat`，对比结果，生成测试报告 | CLI 命令行工具 |

**核心用户价值：** 开发者在本机一条命令启动全部测试环境，运行可配置的用例集，快速定位 Agent 的意图理解、工具调用、格式输出等问题，无需每次打榜才能发现 Bug。

### Prerequisites（对主项目的变更要求）

Agent 主项目 `main.py` 中 `httpx.AsyncClient` 的 `base_url` 当前硬编码为 `http://7.225.29.223:8080`，需改为通过环境变量 `RENTAL_API_BASE` 配置：

```python
import os
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
# lifespan 中:
app.state.client = httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=30.0)
```

本地测试时设置 `RENTAL_API_BASE=http://localhost:{mock_port}` 即可将 Agent 指向 Mock 服务。

## Project Classification

| 维度 | 值 |
|---|---|
| **Project Type** | CLI Tool + API Backend（Mock 服务） |
| **Domain** | Testing / Developer Tooling |
| **Complexity** | Medium |
| **Project Context** | Brownfield — 依赖主项目已有接口契约 |
| **PRD 目的** | 实现规范 — 直接驱动开发 |

## Success Criteria

### User Success

- 开发者一条命令启动 Mock Rental API + LLM Proxy + Agent，环境 30 秒内就绪
- 开发者可运行全量用例批量测试，也可指定单个用例名进行调试
- 测试报告清晰展示每个用例的通过/失败状态、期望值 vs 实际值、耗时
- 新增用例只需编辑 YAML 文件，无需修改任何 Python 代码

### Technical Success

- Mock Rental API 覆盖 Agent 实际调用的全部 15 个端点
- LLM Proxy 透传请求至云平台 qwen3 API，Agent 无感知差异
- 测试结果判定采用精确匹配：返回的 house IDs 与期望完全一致
- 多轮对话用例仅验证最后一轮的 Agent 响应

### Measurable Outcomes

| 指标 | 目标 |
|---|---|
| Mock API 端点覆盖率 | 15/15 (100%) |
| 用例配置方式 | 纯 YAML，零代码 |
| 单用例执行时间（不含 LLM） | < 2s |
| 测试报告生成 | 每次运行自动输出 |

## User Journeys

### Journey 1：首次本地全量测试

**用户：** LJW，完成 Agent MVP 后想验证全部用例类型。

1. 编写 `tests/test_cases.yaml`，定义 Chat / Single / Multi 三类用例
2. 编写 `tests/mock_data.yaml`，配置 Mock 房源和地标数据
3. 运行 `python -m test_runner`，框架自动启动 Mock Rental API（端口 9080）、LLM Proxy（端口 8888）、Agent（端口 8191）
4. Test Runner 按用例顺序调用 Agent API，收集响应
5. 运行完成后，终端输出测试报告：通过 8/10，失败 2 个，附失败用例的期望 vs 实际对比
6. LJW 根据报告修复 Agent 逻辑，重新运行

**揭示的需求：** 一键启动、批量执行、结构化报告。

---

### Journey 2：调试单个失败用例

**用户：** LJW，全量测试中发现 `multi_commute_filter` 用例失败，需要单独调试。

1. 运行 `python -m test_runner --case multi_commute_filter`
2. 框架仅执行该用例，输出详细日志（每轮发送的消息、Agent 返回的完整响应）
3. LJW 发现第 3 轮 Agent 少调了一次 `search_nearby_landmark`，定位问题

**揭示的需求：** 按名称运行单个用例、详细模式输出。

---

### Journey 3：新增自定义测试用例

**用户：** LJW，想针对"跨平台比价"场景新增测试。

1. 在 `tests/test_cases.yaml` 中新增一条 Multi 类型用例：定义多轮对话、最终期望的 house IDs
2. 在 `tests/mock_data.yaml` 中补充相关房源数据（确保预期 house IDs 存在于 Mock 数据中）
3. 运行 `python -m test_runner --case cross_platform_compare`
4. 验证通过

**揭示的需求：** 用例和数据完全通过 YAML 配置，无需改代码。

## Architecture

### System Topology（本地运行时）

```
┌──────────────┐     POST /api/v1/chat      ┌─────────────────┐
│  Test Runner │ ──────────────────────────▶ │   Agent (8191)  │
│  (CLI tool)  │ ◀────────────────────────── │   main.py       │
└──────────────┘     ChatResponse            └────────┬────────┘
                                                      │
                                    ┌─────────────────┼─────────────────┐
                                    │ LLM calls       │ Rental API calls│
                                    ▼                 ▼                 │
                          ┌──────────────┐   ┌──────────────────┐      │
                          │ LLM Proxy    │   │ Mock Rental API  │      │
                          │ (8888)       │   │ (9080)           │      │
                          └──────┬───────┘   └──────────────────┘      │
                                 │ forward                              │
                                 ▼                                      │
                          ┌──────────────┐                              │
                          │ Cloud qwen3  │                              │
                          │ (stub/real)  │                              │
                          └──────────────┘                              │
```

### Component Details

#### Component 1: Mock Rental API Server

- **技术栈：** FastAPI
- **数据源：** 从 YAML 文件加载房源、地标数据到内存
- **端口：** 可配置，默认 9080
- **端点覆盖：** 全部 15 个竞赛 API 端点
- **行为：** 内存级 CRUD（init 重置、rent/terminate/offline 状态变更）
- **X-User-ID：** 接收但不做强制校验（本地测试无需隔离）

#### Component 2: LLM Proxy Server

- **技术栈：** FastAPI
- **端口：** 固定 8888（Agent 硬编码 `{model_ip}:8888`）
- **行为：** 纯透传 — 接收 Agent 的 `/v1/chat/completions` 请求，原样转发至配置的云端 qwen3 API，原样返回响应
- **云端 API 配置：** `LLM_API_BASE` 和 `LLM_API_KEY` 环境变量，MVP 阶段先留 stub（返回固定响应）
- **Stub 模式：** 当未配置云端 API 时，返回一个固定的 "Hello" 响应，便于测试框架本身的正确性

#### Component 3: Test Runner

- **技术栈：** Python CLI（`argparse` 或 `click`）
- **职责：**
  1. 启动 Mock Rental API 和 LLM Proxy（子进程或 asyncio 并发）
  2. 等待服务就绪
  3. 按 YAML 用例定义，逐个调用 Agent 的 `POST /api/v1/chat`
  4. 多轮用例按顺序发送每轮消息，同一 `session_id`
  5. 收集最终轮响应，与期望结果精确对比
  6. 生成并输出测试报告
  7. 运行完成后关闭子服务

## Test Case YAML Schema

### `test_cases.yaml` 结构

```yaml
test_cases:
  - name: "chat_greeting"
    type: "chat"                    # chat | single | multi
    description: "基础问候对话"
    turns:
      - message: "你好，请问你能帮我什么？"
    expected:
      type: "chat"                  # chat = 自然语言回复, house_search = JSON 含 houses
      # chat 类型无需 houses 字段，只验证 status=success 且 response 非空

  - name: "single_haidian_2bed"
    type: "single"
    description: "单轮查询海淀两居室"
    turns:
      - message: "帮我找海淀区两居室，月租8000以内"
    expected:
      type: "house_search"
      houses: ["HF_42", "HF_107"]   # 精确匹配

  - name: "multi_commute_filter"
    type: "multi"
    description: "多轮渐进筛选 - 朝阳国贸附近"
    turns:
      - message: "我想在朝阳区找房，靠近国贸"
      - message: "预算6000以内"
      - message: "最好是近地铁的"
      - message: "给我看看具体有哪些"
    expected:
      type: "house_search"
      houses: ["HF_55", "HF_78"]    # 仅验证最后一轮

  - name: "single_rent_action"
    type: "single"
    description: "租房操作"
    turns:
      - message: "我要租HF_88，平台是安居客"
    expected:
      type: "action"                 # action 类型验证 status=success
      action: "rent"
      house_id: "HF_88"
```

### `mock_data.yaml` 结构

```yaml
landmarks:
  - id: "LM_1"
    name: "国贸"
    category: "商圈"
    district: "朝阳"
    latitude: 39.9087
    longitude: 116.4605
  - id: "LM_2"
    name: "西二旗站"
    category: "地铁站"
    district: "海淀"
    latitude: 40.0508
    longitude: 116.3062

houses:
  - id: "HF_42"
    district: "海淀"
    community: "西二旗小区"
    address: "海淀区西二旗北路XX号"
    room_type: "两居室"
    layout: "2室1厅1卫"
    area: 75
    price: 6500
    decoration: "精装"
    orientation: "朝南"
    floor: "中楼层"
    has_elevator: true
    available_date: "2026-03-01"
    subway_station: "西二旗站"
    subway_distance: 500
    commute_to_xierqi: 8
    noise_level: "安静"
    status: "可租"
    tags: ["近地铁", "精装修", "朝南"]
    listings:                          # 三平台挂牌记录
      - platform: "安居客"
        status: "可租"
      - platform: "链家"
        status: "可租"
      - platform: "58同城"
        status: "可租"
    nearby_landmarks:
      - landmark_id: "LM_2"
        distance: 500
        walking_distance: 650
        walking_duration: 8
    nearby_amenities:
      - name: "永辉超市"
        category: "商超"
        distance: 300
  - id: "HF_107"
    district: "海淀"
    community: "上地小区"
    address: "海淀区上地东路XX号"
    room_type: "两居室"
    layout: "2室1厅1卫"
    area: 68
    price: 7200
    decoration: "简装"
    orientation: "南北"
    floor: "高楼层"
    has_elevator: true
    available_date: "2026-03-01"
    subway_station: "上地站"
    subway_distance: 800
    commute_to_xierqi: 12
    noise_level: "中等"
    status: "可租"
    tags: ["近地铁", "南北通透", "高楼层"]
    listings:
      - platform: "安居客"
        status: "可租"
      - platform: "链家"
        status: "可租"
      - platform: "58同城"
        status: "可租"
    nearby_landmarks: []
    nearby_amenities: []
  # ... more houses as needed
```

### Test Data Generation

框架提供一个数据生成辅助脚本 `generate_mock_data.py`，可基于简化配置快速生成符合 Mock API 要求的完整 `mock_data.yaml`：

```yaml
# generate_config.yaml — 数据生成配置
generation:
  house_count: 30
  landmark_count: 10
  districts: ["海淀", "朝阳", "通州", "昌平", "西城"]
  price_range: [1500, 15000]
  room_types: ["整租", "合租", "一居室", "两居室", "三居室"]
  platforms: ["链家", "安居客", "58同城"]
  status_distribution:
    可租: 0.9
    已租: 0.05
    下架: 0.05
```

运行 `python generate_mock_data.py --config generate_config.yaml --output tests/mock_data.yaml` 生成完整 Mock 数据集。开发者也可以手工编写或在生成数据基础上修改 `mock_data.yaml`。

## Functional Requirements

### Mock Rental API Server

- **FR1**: 系统加载 `mock_data.yaml` 中的房源和地标数据到内存，启动后立即可用
- **FR2**: 系统实现 `POST /api/houses/init` 端点，将所有房源状态重置为初始值（从 YAML 重新加载）
- **FR3**: 系统实现 `GET /api/houses/{house_id}` 端点，按 ID 返回单套房源详情，固定返回安居客平台的挂牌记录（与竞赛 API 行为一致）
- **FR4**: 系统实现 `GET /api/houses/listings/{house_id}` 端点，返回指定房源在链家/安居客/58同城各平台的全部挂牌记录，响应 `data` 结构为 `{ total, page_size, items }`
- **FR5**: 系统实现 `GET /api/houses/by_community` 端点，按小区名查询可租房源，默认每页 10 条，未传 `listing_platform` 时只返回安居客
- **FR6**: 系统实现 `GET /api/houses/by_platform` 端点，支持按 `district`、`min_price`、`max_price`、`room_type`、`decoration`、`orientation`、`max_subway_dist`、`listing_platform`、`page` 参数筛选，默认每页 10 条，未传 `listing_platform` 时默认返回安居客
- **FR7**: 系统实现 `GET /api/houses/nearby` 端点，按 `landmark_id` 和 `max_distance`（默认 2000 米）返回附近可租房源，含 `distance_to_landmark`、`walking_distance`、`walking_duration` 字段，默认每页 10 条，未传 `listing_platform` 时默认返回安居客
- **FR8**: 系统实现 `GET /api/houses/nearby_landmarks` 端点，按 `house_id`、`category`、`max_distance_m`（默认 3000 米）查询周边配套（商超、公园等），结果按距离升序排序
- **FR9**: 系统实现 `GET /api/houses/stats` 端点，返回房源统计信息（总套数、按状态/行政区/户型分布、价格区间），基于当前用户视角统计
- **FR10**: 系统实现 `POST /api/houses/{house_id}/rent`、`/terminate`、`/offline` 端点，请求体必须包含 `listing_platform`（链家/安居客/58同城），变更内存中该房源在三个平台的状态一并更新，响应返回该条房源记录
- **FR11**: 系统实现 `GET /api/landmarks` 端点，支持 `category`、`district` 同时筛选（多条件取交集）
- **FR12**: 系统实现 `GET /api/landmarks/search` 端点，`q` 为必填参数，支持关键词模糊搜索，支持 `category`、`district` 同时筛选（多条件取交集）
- **FR13**: 系统实现 `GET /api/landmarks/name/{name}` 端点，按名称精确查询，返回 `id`、经纬度等信息
- **FR14**: 系统实现 `GET /api/landmarks/{id}` 端点，按 ID 查询地标详情
- **FR15**: 系统实现 `GET /api/landmarks/stats` 端点，返回地标统计信息（总数、按类别分布等）
- **FR16**: 所有 `/api/houses/*` 端点接受 `X-User-ID` 请求头但不做强制校验（本地测试无需用户隔离）
- **FR17**: Mock API 的响应 JSON 结构与真实竞赛 API 保持一致，统一使用 `{"code": 0, "message": "success", "data": {...}}` 包装层

### LLM Proxy Server

- **FR18**: 系统实现 `POST /v1/chat/completions` 端点，接收 OpenAI 兼容格式请求（含 `model`、`messages`、`tools`、`tool_choice` 字段），接受可选的 `Session-ID` 请求头（竞赛评测系统使用，本地可忽略）
- **FR19**: 当配置了 `LLM_API_BASE` 和 `LLM_API_KEY` 环境变量时，系统将请求体原样透传至该地址，并将原始响应原样返回给 Agent
- **FR20**: 当未配置云端 API 环境变量时，系统进入 Stub 模式，返回固定格式的 OpenAI 兼容响应（`finish_reason: "stop"`，`content: "你好，有什么可以帮助你的？"`），响应结构包含 `id`、`object`、`created`、`model`、`choices`、`usage` 全部字段
- **FR21**: Stub 模式下，若请求中包含 `tools` 字段，系统不触发 tool_calls，仅返回纯文本响应

### Test Runner

- **FR22**: Test Runner 读取 `test_cases.yaml` 和 `mock_data.yaml`，启动 Mock Rental API 和 LLM Proxy 子服务
- **FR23**: Test Runner 等待 Mock API 和 LLM Proxy 的健康检查通过后（HTTP 200）开始执行测试
- **FR24**: Test Runner 对每个用例生成唯一 `session_id`，确保用例间隔离
- **FR25**: Test Runner 对每个用例开始前，调用 Agent 的新 session 触发数据重置（由 Agent 的 init hook 完成）
- **FR26**: 对 `chat` 类型用例，验证 `status == "success"` 且 `response` 非空
- **FR27**: 对 `house_search` 类型用例，解析 `response` 为 JSON，提取 `houses` 字段，与 `expected.houses` 进行精确匹配（顺序无关，集合相等）
- **FR28**: 对 `action` 类型用例，验证 `status == "success"`
- **FR29**: 多轮对话用例使用同一 `session_id` 按顺序发送每轮 `message`，仅对最后一轮响应进行结果判定
- **FR30**: 支持 `--case <name>` 参数运行单个指定用例
- **FR31**: 不指定 `--case` 时，按 YAML 中定义顺序执行全部用例
- **FR32**: 执行完毕后输出测试报告至终端，包含：总用例数、通过数、失败数、每个用例的名称/类型/状态/耗时，失败用例附带期望值 vs 实际值对比

### Test Data Generator

- **FR33**: 提供 `generate_mock_data.py` 脚本，读取简化的生成配置 YAML，输出完整 `mock_data.yaml`
- **FR34**: 生成的数据包含合法的 `HF_*` 格式房源 ID 和 `LM_*` 格式地标 ID
- **FR35**: 生成的房源数据覆盖所有字段：id、district、community、address、room_type、layout、area、price、decoration、orientation、floor、has_elevator、available_date、subway_station、subway_distance、commute_to_xierqi、noise_level、status、tags，以及三平台（安居客/链家/58同城）挂牌记录
- **FR36**: 生成的地标数据覆盖 `地铁站`、`公司`、`商圈` 三类，每个地标含 id、name、category、district、latitude、longitude，并为每个房源随机关联 1-3 个近邻地标及 0-3 个周边配套（商超/公园）

## Non-Functional Requirements

### Performance

- **NFR1**: Mock Rental API 启动时间 < 3 秒（内存数据加载）
- **NFR2**: 单个 Mock API 请求响应时间 < 50ms
- **NFR3**: Test Runner 全量运行 20 个用例（不含 LLM 耗时）< 30 秒

### Usability

- **NFR4**: 测试框架不引入 Agent 主项目的额外运行时依赖；测试相关依赖单独管理（`requirements-test.txt` 或 dev extras）
- **NFR5**: 用例和数据配置文件使用 YAML 格式，含注释说明每个字段的含义
- **NFR6**: 测试报告使用彩色终端输出（PASS 绿色、FAIL 红色），支持非彩色回退

### Maintainability

- **NFR7**: Mock API 端点实现与真实竞赛 API 的请求/响应格式文档保持一一对应，便于跟踪竞赛接口变更
- **NFR8**: 所有配置文件路径可通过环境变量或 CLI 参数覆盖，默认路径为 `tests/` 目录

### Compatibility

- **NFR9**: 支持 Python 3.10+
- **NFR10**: 支持 Windows / Linux 环境运行

## File Structure

```
tests/
├── test_cases.yaml              # 用例定义
├── mock_data.yaml               # Mock 房源/地标数据
├── generate_config.yaml         # 数据生成配置
├── generate_mock_data.py        # 数据生成脚本
├── mock_rental_api.py           # Mock Rental API Server
├── llm_proxy.py                 # LLM Proxy Server
├── test_runner.py               # Test Runner CLI
├── conftest.py                  # pytest fixtures（可选）
└── requirements-test.txt        # 测试框架依赖
```

## Phased Development

### Phase 1: MVP

- Mock Rental API：实现 Agent 实际调用的 6 个核心端点（`by_platform`、`houses/{id}`、`nearby`、`nearby_landmarks`、`landmarks/search`、`houses/init`、`rent`/`terminate`/`offline`）
- LLM Proxy：Stub 模式（固定响应）
- Test Runner：支持 chat + single 用例执行、精确匹配判定、终端报告
- 主项目 `main.py` 的 `base_url` 环境变量化

### Phase 2: Full Mock + Cloud LLM

- Mock Rental API：补齐剩余 9 个端点
- LLM Proxy：实现云端 qwen3 透传模式
- Test Runner：支持 multi 多轮用例、`--case` 单用例调试
- Mock 数据生成脚本

### Phase 3: Advanced

- 测试报告导出为 JSON/HTML 文件
- 并发用例执行
- Mock API 请求日志（调试 Agent 工具调用行为）
