# Story 5.1: 配置系统重构与 Fixture 数据集创建

Status: done

## Story

As a developer (LJW),
I want an updated configuration system and a complete fixture dataset loaded at startup,
So that all simulator components can read type-validated settings from a unified config, and the Mock Rental API has rich, realistic in-memory data to serve dynamic queries against.

## Acceptance Criteria

**AC1 — SimulatorConfig 字段校验**

**Given** `config.py` 中的 `SimulatorConfig` 被检视，
**When** 字段列表被检查，
**Then** 必须包含：`agent_base_url: str`、`model_proxy_port: int`、`llm_proxy_url: str`、`llm_api_key: str | None`、`mock_rental_port: int`、`fixture_file: str`、`test_user_id: str`、`test_cases_file: str`、`timeout_per_case: int`、`report_dir: str`；**且不能包含** `rental_mode`、`rental_passthrough_url`、`MockRule`。

**AC2 — load_config 正常加载**

**Given** 一个含全部必填字段的有效 `config.yaml`，
**When** 调用 `load_config(path)`，
**Then** 返回 `SimulatorConfig`，所有字段正确类型化；缺少任何必填字段时抛出 `ValidationError`，错误信息包含字段名。

**AC3 — load_fixtures 函数签名与返回值**

**Given** 调用 `load_fixtures(path)` 并传入 `mock_data/default.yaml` 路径，
**When** 文件被加载，
**Then** 返回 `dict`，结构为 `{"landmarks": list[dict], "houses": list[dict]}`；`landmarks` ≥ 20 条，每条含字段：`id`、`name`、`category`（subway/company/landmark）、`district`、`longitude: float`、`latitude: float`；`houses` ≥ 30 条，每条含字段：`house_id`、`community`、`district`、`area`、`price: int`（安居客基准价）、`status`（available/rented/offline）、`longitude: float`、`latitude: float`、`bedrooms: int`、`rental_type`、`decoration`、`orientation`、`elevator: bool`。

**AC4 — houses fixture 覆盖度**

**Given** fixture 数据被加载，
**When** 检查 `houses` 列表，
**Then** 以下所有条件成立：行政区覆盖 ≥ 6 个；bedroom 包含 1、2、3 居室；rental_type 包含整租和合租；价格区间跨越 1500–15000 元/月；初始状态分布：≥ 85% available、≥ 1 rented、≥ 1 offline；所有 house_id 遵循 `HF_NNN` 格式（如 HF_001）。

**AC5 — landmarks fixture 覆盖度**

**Given** fixture 数据被加载，
**When** 检查 `landmarks` 列表，
**Then** 以下所有条件成立：行政区覆盖 ≥ 5 个；三种 category 均存在：subway（`SS_NNN`）、company（`F500_NNN`）、landmark（`LM_NNN`）；每条 landmark 含 `longitude` 和 `latitude`（供 Haversine 距离计算）。

**AC6 — CaseResult 与 TokenUsage 模型**

**Given** `CaseResult` 和 `TokenUsage` 已在 `config.py` 中定义，
**When** 被检视，
**Then** `CaseResult` 含：`case_id: str`、`case_type: str`、`status: str`（PASS/FAIL/ERROR/TIMEOUT）、`duration_ms: int`、`rounds: int`、`failure_reason: str | None`、`actual_response: str | None`、`token_usage: TokenUsage | None`；`TokenUsage` 含：`prompt_tokens: int`、`completion_tokens: int`、`total_tokens: int`。

## Tasks / Subtasks

- [x] Task 1：更新 `config.py` (AC: 1, 2, 3, 6)
  - [x] 1.1 从 `SimulatorConfig` 中移除 `rental_mode`、`rental_passthrough_url`、`mock_data_file`
  - [x] 1.2 向 `SimulatorConfig` 新增 `fixture_file: str = "mock_data/default.yaml"`
  - [x] 1.3 删除整个 `MockRule` 类（含其 `@model_validator`）
  - [x] 1.4 删除 `load_mock_data(path)` 函数
  - [x] 1.5 新增 `load_fixtures(path: str) -> dict` 函数，加载并验证 YAML 中的 landmarks + houses 列表
  - [x] 1.6 确保 `CaseResult`、`TokenUsage`、`TokenCounter`、`ExpectRules`、`TestCase` 保持不变

- [x] Task 2：创建 `mock_data/default.yaml` fixture 数据集 (AC: 3, 4, 5)
  - [x] 2.1 设计并填充 ≥ 20 条 landmark（SS_NNN subway + F500_NNN company + LM_NNN landmark，覆盖 ≥ 5 个行政区，每条含经纬度）
  - [x] 2.2 设计并填充 ≥ 30 条 house（HF_NNN 格式，覆盖 ≥ 6 个行政区，1/2/3 居室，整租+合租，价格 1500–15000，初始 ≥ 85% available，≥ 1 rented，≥ 1 offline）
  - [x] 2.3 每条 house 必须含经纬度（供 Story 5-2 的 Haversine 距离计算）
  - [x] 2.4 每条 house 必须含完整字段（见 AC3），且字段名与 `docs/interface_simulate.md` 真实 API 完全一致

- [x] Task 3：更新 `config.yaml`（运行时配置文件）
  - [x] 3.1 移除 `rental_mode` 和 `rental_passthrough_url` 配置项
  - [x] 3.2 将 `mock_data_file` 改名为 `fixture_file`，值保持 `mock_data/default.yaml`

## Review Follow-ups (AI)

- [ ] [AI-Review][HIGH] H2: Fixture 房源缺少真实 API 返回的大量字段（area_sqm, commute_to_xierqi, available_from, livingrooms, bathrooms, floor, total_floors, price_unit, property_type, utilities_type, hidden_noise_level, address, listing_url, coordinate_system）。by_platform 的 min_area/max_area/commute_to_xierqi_max/available_from_before 筛选将无法工作。建议在 Story 5-2 开始前补充这些字段到 mock_data/default.yaml。[mock_data/default.yaml: 全部 32 条 house]
- [ ] [AI-Review][MEDIUM] M1: Fixture house_id 格式 HF_NNN（零填充 HF_001）与真实 API HF_N（非零填充 HF_1）不一致。AC4 明确指定 HF_NNN，已保留。如需对齐真实 API，需同步修改 fixture + 测试。[mock_data/default.yaml + tests/test_config.py]
- [ ] [AI-Review][MEDIUM] M2: api_key_file 字段已加入 SimulatorConfig 但不在 AC1 规格中——功能有用，已保留为接受的设计选择。[config.py:19]
- [ ] [AI-Review][MEDIUM] M3: Fixture landmarks 缺少 `details` 嵌套对象（真实 API 包含 lines/type/station_id/address/industry 等）。Story 5-2 landmark 端点需要这些数据。建议在 Story 5-2 开始前补充。[mock_data/default.yaml: 全部 21 条 landmark]

## Dev Notes

### 关键架构背景

本 Story 是 Test Simulator 重构的**基础层**，后续 Story（5-2 mock_rental 重构、6-1 runner、6-2 main）均依赖本 Story 产出的 `SimulatorConfig.fixture_file` 和 `load_fixtures()` 函数。

**实现顺序（Architecture 文档明确）：**
```
fixture 数据 → MockState + mock_rental → runner → main
```
本 Story 完成第一步（fixture 数据 + config 更新）。

### 已有代码状态（重要：防止重复造轮子）

当前 `config.py` 已有以下内容**无需修改**：
- `SimulatorConfig`（部分字段需更新，见下文）
- `ExpectRules`（完整保留）
- `TestCase`（完整保留）
- `TokenUsage`（完整保留）
- `CaseResult`（完整保留）
- `TokenCounter`（完整保留）
- `load_config()` 函数（完整保留）
- `load_test_cases()` 函数（完整保留）

**需要删除的内容：**
- `MockRule` 类（整个删除）
- `load_mock_data()` 函数（整个删除）
- `SimulatorConfig` 中的 `rental_mode`、`rental_passthrough_url`、`mock_data_file` 三个字段

**需要新增的内容：**
- `SimulatorConfig` 中新增 `fixture_file: str = "mock_data/default.yaml"`
- 新增函数 `load_fixtures(path: str) -> dict`

### 破坏性变更警告（开发者必读）

删除 `MockRule` 和 `load_mock_data()` 后，以下文件**将产生导入错误**：

| 文件 | 破坏内容 | 由哪个 Story 修复 |
|------|----------|------------------|
| `mock_rental.py` | `from config import MockRule`（第 10 行） | Story 5-2 |
| `main.py` | `from config import load_mock_data`（第 13 行）、`load_mock_data(config.mock_data_file)` | Epic 6 Stories |

**本 Story 只需完成 config.py + mock_data/default.yaml 的更新，不需要修复 mock_rental.py 或 main.py。** 这些文件在 Story 5-2 和 Epic 6 中会被完整重写。

### 技术栈（项目约束）

- Python 3.11+，所有类型注解使用 `str | None`（PEP 604）而非 `Optional[str]`
- Pydantic v2（`BaseModel`、`model_validator`）
- PyYAML（`yaml.safe_load`）
- 文件编码：UTF-8

### load_fixtures 实现规范

```python
def load_fixtures(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    landmarks = data.get("landmarks", [])
    houses = data.get("houses", [])
    if not isinstance(landmarks, list) or not isinstance(houses, list):
        raise ValueError(f"{path}: expected 'landmarks' and 'houses' lists")
    return {"landmarks": landmarks, "houses": houses}
```

不需要 Pydantic 验证 fixture 字段——代码由开发者控制，运行时检查足够。

### mock_data/default.yaml 数据规范

**YAML 顶层结构（必须）：**
```yaml
landmarks:
  - id: "SS_001"
    name: "西二旗站"
    category: "subway"
    district: "海淀"
    longitude: 116.3289
    latitude: 40.0567
  # ...

houses:
  - house_id: "HF_001"
    community: "某小区名"
    district: "海淀"
    area: "西二旗"
    price: 4500          # 安居客基准价（整数，元/月）
    status: "available"  # 初始状态（由 MockState._initial_status 保存）
    longitude: 116.3300
    latitude: 40.0500
    bedrooms: 2
    rental_type: "整租"   # 整租 or 合租
    decoration: "精装"    # 简装/精装/豪华/毛坯/空房
    orientation: "朝南"   # 朝南/朝北/朝东/朝西/南北/东西
    elevator: true
    subway_line: "13号线"
    subway_station: "西二旗站"
    subway_distance: 350   # 米
    tags: ["近地铁", "精装修"]
  # ...
```

**ID 格式（必须严格遵循）：**
- Subway 地标：`SS_001`、`SS_002` … `SS_NNN`
- Company 地标：`F500_001`、`F500_002` … `F500_NNN`
- Landmark 地标：`LM_001`、`LM_002` … `LM_NNN`
- House：`HF_001`、`HF_002` … `HF_NNN`（字符串，不转整数）

**价格系数参考（Story 5-2 使用，fixture 仅存安居客基准价）：**
- 安居客：× 1.00（原价）
- 链家：× 0.92
- 58同城：× 0.78

**行政区覆盖要求：**

Landmarks（≥ 5 个行政区建议）：海淀、朝阳、西城、东城、昌平
Houses（≥ 6 个行政区建议）：海淀、朝阳、西城、通州、大兴、房山

**初始状态分布示例（30 条 house 中）：**
- 26 条 available（约 87%）
- 2 条 rented（约 7%）
- 2 条 offline（约 7%）

### Project Structure Notes

- **`config.py`** — 本 Story 唯一修改的 Python 文件
- **`mock_data/default.yaml`** — 重写此文件（原内容 `mock_responses: []` 完全替换）
- **`config.yaml`** — 移除 `rental_mode`/`rental_passthrough_url`，新增/改名 `fixture_file`
- **`mock_rental.py`、`main.py`** — 本 Story **不触碰**，即使产生导入错误也属预期

### 已有文件参考路径

| 文件 | 描述 |
|------|------|
| `test-simulator/config.py` | 当前完整实现，本 Story 的修改基础 |
| `test-simulator/mock_data/default.yaml` | 当前为空文件（`mock_responses: []`），需完整重写 |
| `test-simulator/config.yaml` | 运行时配置，需同步更新字段名 |
| `docs/interface_simulate.md` | 真实 API 接口规范，fixture house 字段必须与之对齐 |

### References

- [Source: _bmad-output/planning-artifacts/epics-test-simulator.md#Story 1.1]
- [Source: _bmad-output/planning-artifacts/architecture-test-simulator.md#Fixture 数据架构]
- [Source: _bmad-output/planning-artifacts/architecture-test-simulator.md#Project Structure]
- [Source: docs/interface_simulate.md — house 字段定义]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor, 2026-03-01)

### Debug Log References

- 无阻断性问题，所有任务一次通过

### Completion Notes List

- **Task 1 (config.py)**：移除 `MockRule`、`load_mock_data`、`rental_mode`、`rental_passthrough_url`、`mock_data_file`；新增 `fixture_file: str = "mock_data/default.yaml"` 和 `load_fixtures(path) -> dict`；保留 `CaseResult`、`TokenUsage`、`TokenCounter`、`ExpectRules`、`TestCase` 不变。
- **Task 2 (mock_data/default.yaml)**：创建 21 条 landmark（10 subway SS_NNN、6 company F500_NNN、5 landmark LM_NNN，覆盖海淀/朝阳/西城/东城/通州/大兴/昌平）和 32 条 house（HF_001–HF_032，覆盖 7 个行政区，含 1/2/3 居室，整租+合租，价格 1500–15000 元/月，28 available/2 rented/2 offline，所有 house 含完整经纬度）。
- **Task 3 (config.yaml)**：移除 `rental_mode`、`rental_passthrough_url`；将 `mock_data_file` 改名为 `fixture_file`。
- **测试**：编写 `test-simulator/tests/test_config.py`，65 个测试用例，全部 PASS（AC1–AC6 完整覆盖）。TDD 红绿流程：ImportError 验证 RED，实现后 65/65 绿灯。
- **Code Review 修复（2026-03-01）**：
  - [H1] fixture `subway_line` 重命名为 `subway` 以对齐真实 API 响应字段名
  - [M4] 添加 `TestCase.__test__ = False` 消除 pytest 收集警告
  - [M5] `load_fixtures()` 新增字段级校验（landmark 6 字段 + house 13 字段必须存在）
  - [L1] 创建 `tests/conftest.py` 替代 test_config.py 中的 sys.path hack
  - [L2] 新增 3 个测试：load_config 非 dict YAML + load_fixtures 字段缺失校验（landmark/house 各 1 个）
  - 测试套件：65 → 68 个用例，全部 PASS，0 warnings

### File List

- `test-simulator/config.py` — 移除 MockRule/load_mock_data，新增 load_fixtures/fixture_file；Review: 增强 load_fixtures 字段校验 + TestCase.__test__
- `test-simulator/mock_data/default.yaml` — 全新创建（21 landmarks + 32 houses）；Review: subway_line → subway
- `test-simulator/config.yaml` — 移除旧字段，新增 fixture_file
- `test-simulator/tests/test_config.py` — 新建，68 个测试用例（AC1–AC6 + review 补充）；Review: 移除 sys.path hack
- `test-simulator/tests/conftest.py` — Review 新建：pytest 路径配置

## Change Log

- 2026-03-01: Story 5.1 实现完成 — 配置系统重构（移除 MockRule/rental 字段）+ 创建 fixture 数据集（21 landmarks, 32 houses）+ 65 测试用例全部通过，状态更新为 review
- 2026-03-01: Code Review 修复 — [H1] subway_line→subway 字段对齐、[M4] pytest 警告修复、[M5] load_fixtures 字段校验增强、[L1] conftest.py 路径管理、[L2] 新增 3 测试用例（68 passed, 0 warnings）；4 个 action items 记录待 Story 5-2 处理（H2 缺失 house 字段、M1 ID 格式、M3 landmark details）
