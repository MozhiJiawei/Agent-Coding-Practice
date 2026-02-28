---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-decisions', 'step-04-patterns', 'step-05-structure', 'step-06-validation', 'step-07-complete']
status: 'complete'
completedAt: '2026-02-28'
inputDocuments:
  - _bmad-output/planning-artifacts/prd-test-simulator.md
  - _bmad-output/planning-artifacts/architecture.md
  - docs/interface.md
  - docs/interface_simulate.md
workflowType: 'architecture'
project_name: 'AI Agent Coding — Test Environment Simulator'
user_name: 'LJW'
date: '2026-02-28'
---

# Architecture Decision Document — Test Environment Simulator

_本文档为测试仿真器子项目的独立架构决策说明书，与主项目架构文档（`architecture.md`）并列存在。所有 AI Agent 在实现测试仿真器时必须以本文档为规范依据。_

---

## Project Context Analysis

### Requirements Overview

**Functional Requirements（功能需求摘要）：**

共 36 个 FR，按组件分组：

| 组件 | FR 范围 | 核心职责 |
|------|--------|---------|
| Mock Rental API Server | FR1–FR17 | 在内存中模拟全部 15 个竞赛租房 API 端点，基于 YAML 数据文件提供一致的响应 |
| LLM Proxy Server | FR18–FR21 | 监听 8888 端口，支持 Stub 模式（固定响应）和透传模式（转发至云端 qwen3） |
| Test Runner | FR22–FR32 | CLI 工具，管理子服务生命周期，执行 YAML 用例，生成测试报告 |
| Test Data Generator | FR33–FR36 | 按生成配置批量产生 `mock_data.yaml`，便于快速搭建测试数据集 |

**Non-Functional Requirements（非功能需求摘要）：**

| NFR | 类别 | 约束 |
|-----|------|------|
| NFR1 | 性能 | Mock API 启动 < 3 秒 |
| NFR2 | 性能 | 单个 Mock API 请求响应 < 50ms |
| NFR3 | 性能 | 全量 20 个用例（不含 LLM）< 30 秒 |
| NFR4 | 可用性 | 测试框架依赖与主项目依赖分离 (`requirements-test.txt`) |
| NFR5 | 可用性 | YAML 配置含注释，可读性优先 |
| NFR6 | 可用性 | 测试报告彩色输出（PASS 绿色 / FAIL 红色），支持非彩色回退 |
| NFR7 | 可维护性 | Mock API 端点与竞赛接口文档一一对应 |
| NFR8 | 可维护性 | 配置文件路径可通过环境变量/CLI 参数覆盖，默认 `tests/` |
| NFR9 | 兼容性 | Python 3.10+ |
| NFR10 | 兼容性 | Windows / Linux 双平台 |

**Scale & Complexity：**

- Primary domain: Testing / Developer Tooling（CLI + API Backend）
- Complexity level: Medium
- Estimated components: 4（Mock Rental API + LLM Proxy + Test Runner + Data Generator）
- No external database: 全内存运行，YAML 文件为唯一持久化来源

### Technical Constraints & Dependencies

- **固定端口约束：** LLM Proxy 必须监听 8888（Agent 硬编码 `{model_ip}:8888`），Agent 固定 8191；Mock Rental API 可配置，默认 9080
- **主项目前置变更：** `main.py` 中 `httpx.AsyncClient` 的 `base_url` 必须环境变量化（`RENTAL_API_BASE`），测试框架才能将 Agent 指向 Mock 服务
- **平台兼容：** 子进程管理须同时支持 Windows (`subprocess`) 和 Linux；信号处理（SIGTERM/SIGINT）需适配两平台
- **依赖最小化：** 测试依赖不污染主项目 `requirements.txt`，单独维护 `requirements-test.txt`
- **与主项目架构对齐：** Mock Rental API 响应格式必须与真实竞赛 API 一致（统一 `{"code": 0, "message": "success", "data": {...}}` 包装层）

### Cross-Cutting Concerns Identified

1. **子进程生命周期管理** — 影响 Test Runner 全局，启动顺序、健康检查、清理退出必须统一处理
2. **YAML 配置解析** — Mock 数据、测试用例、生成配置三类文件全部基于 YAML，统一使用 `PyYAML`，路径可覆盖
3. **端口冲突处理** — 启动前检测端口是否已占用，给出明确错误信息
4. **测试隔离** — 每个用例独立 `session_id`，每次用例开始时需重置 Mock 数据状态
5. **彩色输出兼容** — 使用 ANSI 转义码但提供非彩色回退（检测 `NO_COLOR` 环境变量或 Windows 兼容性）
6. **错误与超时统一处理** — 用例执行超时、子服务崩溃、YAML 格式错误均需规范化处理，不崩溃整个 Test Runner

---

## Core Architectural Decisions

### Decision 1: 子进程编排策略

**问题：** Test Runner 需要启动 Mock Rental API、LLM Proxy、Agent 三个服务，如何管理其生命周期？

**选项对比：**

| 策略 | 优点 | 缺点 |
|------|------|------|
| A: 同进程 asyncio 并发（多 uvicorn 实例） | 无 IPC 开销，日志统一 | 端口隔离复杂，Windows 多事件循环限制 |
| B: `subprocess.Popen`（独立进程） | 完全隔离，崩溃不影响 Runner，跨平台成熟 | 需要 PID 管理和显式清理 |
| C: `threading`（线程内运行 uvicorn） | 实现简单 | 线程间共享 GIL，uvicorn 不建议多线程运行 |

**决策：选项 B — `subprocess.Popen` 独立进程**

**理由：**
- Mock API 和 LLM Proxy 独立进程意味着其崩溃不会拖垮 Test Runner
- Windows/Linux 跨平台支持成熟
- 通过 PID 明确追踪进程，`finally` 块保证清理

**实现规范：**
```python
# test_runner.py 中
processes: list[subprocess.Popen] = []
try:
    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "tests.mock_rental_api:app",
         "--host", "127.0.0.1", "--port", "9080"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    processes.append(proc)
    # ... 启动其他服务
    wait_for_health(["http://127.0.0.1:9080/health", "http://127.0.0.1:8888/health"])
    run_tests(cases)
finally:
    for proc in processes:
        proc.terminate()
        proc.wait(timeout=5)
```

---

### Decision 2: 服务健康检查策略

**问题：** Test Runner 如何判断子服务已就绪，可以开始发送测试请求？

**决策：** HTTP 健康检查轮询（最多等待 30 秒，间隔 0.5 秒）

**实现规范：**
- 每个服务实现 `GET /health` 端点，返回 `{"status": "ok"}`
- Test Runner 并发检查所有服务的健康端点，全部通过后继续
- 超过 30 秒未就绪，Test Runner 清理子进程并以非零退出码退出

```python
def wait_for_health(urls: list[str], timeout: float = 30.0):
    deadline = time.time() + timeout
    pending = set(urls)
    while pending and time.time() < deadline:
        for url in list(pending):
            try:
                r = httpx.get(url, timeout=1.0)
                if r.status_code == 200:
                    pending.discard(url)
            except Exception:
                pass
        if pending:
            time.sleep(0.5)
    if pending:
        raise RuntimeError(f"Services did not start in time: {pending}")
```

---

### Decision 3: Mock Rental API 数据存储架构

**问题：** Mock 数据如何存储、如何支持状态变更和重置？

**决策：** 启动时从 YAML 加载到内存 `dict`，状态变更在内存中更新，`/api/houses/init` 从原始数据重置

**数据结构：**
```python
# mock_rental_api.py 模块级变量
_original_houses: dict[str, dict] = {}   # 初始数据（不可变，用于 init 重置）
_houses: dict[str, dict] = {}            # 运行时状态（可变）
_landmarks: dict[str, dict] = {}         # 地标数据（只读）

def load_mock_data(path: str):
    data = yaml.safe_load(open(path, encoding="utf-8"))
    global _original_houses, _houses, _landmarks
    _houses = {h["id"]: copy.deepcopy(h) for h in data["houses"]}
    _original_houses = copy.deepcopy(_houses)
    _landmarks = {lm["id"]: lm for lm in data["landmarks"]}

def reset_houses():
    global _houses
    _houses = copy.deepcopy(_original_houses)
```

**状态变更规则（rent / terminate / offline）：**
- `rent`: 将指定平台挂牌状态改为 `"已租"`，同时将房源 `status` 改为 `"已租"`
- `terminate`: 将指定平台挂牌状态改为 `"已退租"`（可重新租用），`status` 改回 `"可租"`
- `offline`: 将指定平台挂牌状态改为 `"下架"`，同时将房源 `status` 改为 `"下架"`
- 三平台状态联动：单一操作同时更新所有三个平台的挂牌状态（与竞赛 API 行为一致）

---

### Decision 4: LLM Proxy 双模式设计

**问题：** LLM Proxy 如何在 Stub 模式（离线测试）和透传模式（真实 LLM）之间切换？

**决策：** 通过环境变量 `LLM_API_BASE` 和 `LLM_API_KEY` 自动判断模式，无需代码修改

**模式判断逻辑：**
```python
LLM_API_BASE = os.environ.get("LLM_API_BASE", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
STUB_MODE = not (LLM_API_BASE and LLM_API_KEY)
```

**Stub 响应规范（必须完整符合 OpenAI 格式，Agent 无感知）：**
```python
STUB_RESPONSE = {
    "id": "chatcmpl-stub-001",
    "object": "chat.completion",
    "created": int(time.time()),
    "model": "stub",
    "choices": [{
        "index": 0,
        "message": {"role": "assistant", "content": "你好，有什么可以帮助你的？"},
        "finish_reason": "stop"
    }],
    "usage": {"prompt_tokens": 0, "completion_tokens": 10, "total_tokens": 10}
}
```

**Stub 模式工具调用规则：** 请求包含 `tools` 字段时，Stub 不触发 `tool_calls`，仅返回纯文本响应（`finish_reason: "stop"`，无 `tool_calls`）

---

### Decision 5: 测试用例结果判定策略

**问题：** 不同类型用例（chat / house_search / action）如何验证期望结果？

**决策：** 按 `expected.type` 分三种精确验证策略

| 用例类型 | 验证目标 | 判定逻辑 |
|---------|---------|---------|
| `chat` | `status == "success"` 且 `response` 非空 | 不验证 response 内容，只验证结构 |
| `house_search` | `houses` 集合精确匹配 | `set(actual_houses) == set(expected_houses)`（顺序无关） |
| `action` | `status == "success"` | 只验证操作是否成功，不验证房源状态变更 |

**response 解析规则（house_search 类型）：**
```python
def extract_houses(response_str: str) -> list[str]:
    try:
        data = json.loads(response_str)
        return [h["id"] if isinstance(h, dict) else h for h in data.get("houses", [])]
    except (json.JSONDecodeError, TypeError):
        return []
```

---

### Decision 6: 测试隔离与数据重置策略

**问题：** 如何保证每个测试用例之间的数据状态互不干扰？

**决策：** 每个用例开始前直接调用 Mock API 的 `POST /api/houses/init` 端点（不通过 Agent）

**理由：**
- Agent 的 init 钩子是会话级别的，只在新 `session_id` 首条消息时触发
- 直接调用 Mock API init 更可靠，不依赖 Agent 实现细节
- 每个用例使用唯一 `session_id`（`f"test-{case_name}-{uuid4().hex[:8]}"`）

```python
# test_runner.py 中，每个用例执行前：
async def reset_test_state(mock_api_base: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{mock_api_base}/api/houses/init")
```

---

### Decision 7: 彩色报告输出兼容性

**问题：** 如何实现跨平台（Windows/Linux）的彩色终端输出，并支持非彩色回退？

**决策：** 内联 ANSI 码 + 环境变量控制（不引入额外依赖）

```python
# test_runner.py
import os, sys

NO_COLOR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()

GREEN = "" if NO_COLOR else "\033[32m"
RED   = "" if NO_COLOR else "\033[31m"
RESET = "" if NO_COLOR else "\033[0m"
BOLD  = "" if NO_COLOR else "\033[1m"

def pass_label(): return f"{GREEN}PASS{RESET}"
def fail_label(): return f"{RED}FAIL{RESET}"
```

**Windows 彩色支持：** 在 Windows 上启动时执行 `os.system("")`（启用 ANSI 虚拟终端序列，Python 3.10+ 在 Windows 10+ 上自动支持）

---

### Authentication & Security（测试框架视角）

测试框架为纯本地开发工具，安全模型极简：

- **Mock Rental API：** 接受但不校验 `X-User-ID` 请求头（本地无隔离需求）
- **LLM Proxy：** 不鉴权 Agent 请求，向云端透传时使用 `LLM_API_KEY` 环境变量
- **Test Runner：** 无鉴权，仅通过本地 loopback 地址（127.0.0.1）访问子服务
- **环境变量：** `LLM_API_KEY` 不得写入任何配置文件，仅通过 shell 环境注入

---

### Infrastructure & Deployment

**本地运行拓扑（全量模式）：**
```
┌──────────────────────────────────────────────────────────┐
│                    Test Runner (CLI)                     │
│  1. 启动子进程: Mock Rental API (9080) + LLM Proxy (8888) │
│  2. 等待健康检查通过                                       │
│  3. 逐用例: reset → send requests → compare → record     │
│  4. 输出测试报告                                          │
│  5. finally: terminate all subprocesses                  │
└──────────────────────────────────────────────────────────┘
         ↓ POST /api/v1/chat (session_id, message)
┌─────────────────────┐
│   Agent (8191)      │ ← RENTAL_API_BASE=http://127.0.0.1:9080
│   main.py           │   (环境变量，主项目 Prerequisites 变更)
└──────┬──────────────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
LLM Proxy  Mock Rental API
(8888)     (9080)
  │
  ▼（配置了 LLM_API_BASE 时）
Cloud qwen3 API
```

**单用例执行时序：**
```
Test Runner
  1. POST /api/houses/init → Mock API       [重置数据]
  2. POST /api/v1/chat → Agent              [第1轮消息，触发新 session init]
  3. POST /api/v1/chat → Agent              [第2...N轮消息，multi 类型]
  4. 对最后一轮响应执行 expected 验证
  5. 记录结果（PASS/FAIL + 耗时 + 错误详情）
```

---

## Implementation Patterns & Consistency Rules

### Naming Patterns（命名规范）

**Python 命名约定（全局强制）：**

| 类型 | 规范 | 示例 |
|------|------|------|
| 函数/变量 | `snake_case` | `load_mock_data`, `session_id`, `house_id` |
| 模块级常量 | `ALL_CAPS_SNAKE` | `MOCK_API_PORT`, `HEALTH_CHECK_TIMEOUT`, `STUB_MODE` |
| Pydantic/dataclass | `PascalCase` | `TestCase`, `TestResult`, `MockHouse` |
| 文件名 | `snake_case.py` | `mock_rental_api.py`, `llm_proxy.py`, `test_runner.py` |

**ID 格式规范：**
- 房源 ID：永远是字符串 `"HF_<数字>"`，不得转为整数（与主项目保持一致）
- 地标 ID：永远是字符串 `"LM_<数字>"`
- 用例 Session ID：`f"test-{case_name}-{uuid4().hex[:8]}"`，保证用例间隔离

**测试用例类型枚举：**
- 用例类型：`"chat"` | `"single"` | `"multi"`
- 期望类型：`"chat"` | `"house_search"` | `"action"`
- 用例结果状态：`"pass"` | `"fail"` | `"error"`

**平台枚举（与竞赛 API 完全一致）：**
```python
VALID_PLATFORMS = ["链家", "安居客", "58同城"]
```

---

### Structure Patterns（结构规范）

**模块职责边界（严格禁止跨界）：**

| 文件 | 包含内容 | 禁止包含 |
|------|---------|---------|
| `mock_rental_api.py` | FastAPI app + 数据加载/重置 + 全部 15 个端点路由 + `GET /health` | 测试逻辑、Test Runner 调用 |
| `llm_proxy.py` | FastAPI app + `POST /v1/chat/completions` + Stub/透传模式 + `GET /health` | 租房 API 调用、测试逻辑 |
| `test_runner.py` | CLI 入口 + 子进程管理 + 健康检查 + 用例执行 + 结果判定 + 报告输出 | FastAPI 路由定义 |
| `generate_mock_data.py` | 数据生成逻辑 + CLI 入口 | 测试执行逻辑 |
| `conftest.py` | pytest fixtures（可选，供单元测试使用） | 业务逻辑 |

**Mock Rental API 内部结构（文件内顺序）：**
```python
# 1. 导入
# 2. 模块级常量（MOCK_DATA_FILE, DEFAULT_PORT）
# 3. 内存数据（_houses, _original_houses, _landmarks）
# 4. load_mock_data() + reset_houses()
# 5. FastAPI app 实例化 + lifespan（加载数据）
# 6. GET /health
# 7. POST /api/houses/init（调用 reset_houses）
# 8. 房源端点路由（FR2-FR10：by_platform, nearby, etc.）
# 9. 地标端点路由（FR11-FR15）
```

**Test Runner 内部结构（文件内顺序）：**
```python
# 1. 导入
# 2. 常量（端口、超时、文件路径默认值）
# 3. 彩色输出工具（颜色常量 + pass_label/fail_label）
# 4. wait_for_health()
# 5. reset_test_state()
# 6. run_single_case()  — 执行单用例，返回 TestResult
# 7. run_all_cases()    — 遍历所有用例
# 8. print_report()     — 终端输出报告
# 9. main()             — CLI 入口（argparse + 子进程管理）
```

---

### Format Patterns（格式规范）

**Mock Rental API 响应统一包装（所有端点强制）：**
```python
def success_response(data):
    return {"code": 0, "message": "success", "data": data}

def error_response(msg: str, code: int = -1):
    return {"code": code, "message": msg, "data": None}
```

**分页响应格式（by_platform, nearby, by_community 等分页端点）：**
```python
{
    "code": 0,
    "message": "success",
    "data": {
        "total": 25,
        "page_size": 10,
        "items": [...]
    }
}
```

**TestResult 数据结构：**
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class TestResult:
    name: str
    case_type: str        # chat | single | multi
    status: str           # pass | fail | error
    duration_ms: float
    expected: Optional[any] = None
    actual: Optional[any] = None
    error_msg: Optional[str] = None
```

**测试报告格式规范（终端输出）：**
```
========================================
 Test Run Summary
========================================
 Total: 10  |  PASS: 8  |  FAIL: 2
 Duration: 12.4s
========================================

  PASS  [chat]    chat_greeting           0.8s
  PASS  [single]  single_haidian_2bed     2.3s
  FAIL  [multi]   multi_commute_filter    3.1s
        Expected houses: ['HF_55', 'HF_78']
        Actual houses:   ['HF_55']
  ...

========================================
 2 test(s) FAILED
========================================
```

**YAML 用例文件必填字段验证：**
```python
REQUIRED_CASE_FIELDS = {"name", "type", "turns", "expected"}
REQUIRED_TURN_FIELDS = {"message"}
REQUIRED_EXPECTED_FIELDS = {"type"}
```

---

### Communication Patterns（通信规范）

**Test Runner → Agent 请求格式：**
```python
# 调用 Agent 的标准请求体（与主项目 ChatRequest 一致）
{
    "model_ip": MODEL_IP,       # 从环境变量 MODEL_IP 读取，默认 "127.0.0.1"
    "session_id": session_id,   # 用例专属 session_id
    "message": turn["message"]  # 当轮消息
}
```

**单用例超时控制：**
```python
CASE_TIMEOUT = float(os.environ.get("CASE_TIMEOUT", "60"))  # 默认 60 秒/用例
async with httpx.AsyncClient(timeout=CASE_TIMEOUT) as client:
    resp = await client.post(agent_url, json=payload)
```

**多轮用例执行模式（同一 session_id，顺序发送）：**
```python
async def run_single_case(case: dict, agent_url: str, mock_api_url: str) -> TestResult:
    session_id = f"test-{case['name']}-{uuid4().hex[:8]}"
    await reset_test_state(mock_api_url)    # 重置 Mock 数据
    
    last_response = None
    for turn in case["turns"]:
        resp = await client.post(agent_url, json={
            "model_ip": MODEL_IP,
            "session_id": session_id,
            "message": turn["message"]
        })
        last_response = resp.json()
    
    return validate_result(case, last_response)  # 仅验证最后一轮
```

**子进程端口检测（启动前）：**
```python
import socket

def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0

# 启动前检查
for port in [MOCK_API_PORT, LLM_PROXY_PORT]:
    if not is_port_free(port):
        raise RuntimeError(f"Port {port} is already in use. Please free it before running tests.")
```

---

### Process Patterns（过程规范）

**Test Runner 错误处理层次：**

| 层次 | 场景 | 处理方式 |
|------|------|---------|
| 启动阶段 | 端口占用 / 健康检查超时 | 打印明确错误信息，`finally` 清理子进程，退出码 1 |
| 用例执行 | HTTP 超时 / Agent 返回 error status | 标记用例为 `status="error"`，记录错误信息，继续执行下一个用例 |
| YAML 解析 | 配置文件格式错误 / 必填字段缺失 | 启动前校验，打印具体错误位置，拒绝运行 |
| 结果对比 | JSON 解析失败 / houses 字段缺失 | 标记用例为 `status="fail"`，actual 设为空列表，附带错误说明 |

**Mock Rental API 端点过滤逻辑（分页 + 多条件筛选）：**
```python
# by_platform 端点过滤示例
def filter_houses(houses: list[dict], params: dict) -> list[dict]:
    result = [h for h in houses if h["status"] == "可租"]
    if params.get("district"):
        result = [h for h in result if h["district"] == params["district"]]
    if params.get("min_price"):
        result = [h for h in result if h["price"] >= params["min_price"]]
    if params.get("max_price"):
        result = [h for h in result if h["price"] <= params["max_price"]]
    if params.get("room_type"):
        result = [h for h in result if h["room_type"] == params["room_type"]]
    if params.get("max_subway_dist"):
        result = [h for h in result if h.get("subway_distance", 9999) <= params["max_subway_dist"]]
    # listing_platform 过滤：仅返回该平台状态为"可租"的房源
    platform = params.get("listing_platform", "安居客")
    result = [h for h in result if _has_available_listing(h, platform)]
    return result
```

**数据生成器随机一致性（generate_mock_data.py）：**
```python
import random, uuid

def generate_house_id(index: int) -> str:
    return f"HF_{index + 1}"

def generate_landmark_id(index: int) -> str:
    return f"LM_{index + 1}"

# 使用固定 seed 支持可重现的数据生成（可选 --seed 参数）
random.seed(config.get("seed", 42))
```

---

## Project Structure & Boundaries

### Complete Project Directory Structure

```
tests/
├── test_cases.yaml              # 用例定义（type: chat|single|multi）
├── mock_data.yaml               # Mock 房源/地标数据
├── generate_config.yaml         # 数据生成配置
├── mock_rental_api.py           # Mock Rental API Server（FastAPI，15 个端点）
├── llm_proxy.py                 # LLM Proxy Server（Stub/透传双模式）
├── test_runner.py               # Test Runner CLI（主入口）
├── generate_mock_data.py        # Mock 数据批量生成脚本
├── conftest.py                  # pytest fixtures（可选）
└── requirements-test.txt        # 测试框架专属依赖
```

**`requirements-test.txt` 内容：**
```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
pyyaml>=6.0
```
> 注：不包含 `openai`（仅 LLM Proxy 透传时需要，直接用 `httpx` 转发更轻量）

---

### Architectural Boundaries

**组件边界示意图：**
```
┌─────────────────────────────────────────────────────────────────┐
│                      tests/ 目录边界                            │
│                                                                 │
│  ┌─────────────────┐    subprocess    ┌──────────────────────┐  │
│  │  test_runner.py │ ──────────────► │ mock_rental_api.py   │  │
│  │  (CLI 主入口)   │                 │ FastAPI :9080         │  │
│  │                 │ ──────────────► │ llm_proxy.py         │  │
│  │  + 健康检查     │    subprocess   │ FastAPI :8888         │  │
│  │  + 用例执行     │                 └──────────────────────┘  │
│  │  + 报告输出     │                                            │
│  └────────┬────────┘                                            │
│           │ HTTP POST /api/v1/chat                              │
└───────────┼─────────────────────────────────────────────────────┘
            │
            ▼  主项目边界
┌─────────────────────────┐
│  Agent (main.py) :8191  │
│  RENTAL_API_BASE=:9080  │ ← 环境变量化（Prerequisites 变更）
│  model_ip 指向 :8888    │
└─────────────────────────┘
```

**严禁的跨界引用：**
- ❌ `test_runner.py` 直接 `import mock_rental_api`（应通过 HTTP 访问，不共享进程空间）
- ❌ `mock_rental_api.py` 包含任何测试断言逻辑
- ❌ `llm_proxy.py` 直接访问 Mock 数据（两个服务完全解耦）

---

### Requirements to Structure Mapping

| FR | 实现位置 | 关键实现 |
|----|---------|---------|
| FR1（加载 mock_data.yaml） | `mock_rental_api.py:load_mock_data()` | lifespan 中调用，YAML 路径可配置 |
| FR2（POST /api/houses/init） | `mock_rental_api.py:reset_houses()` | 深拷贝恢复 `_original_houses` |
| FR3（GET /api/houses/{id}） | `mock_rental_api.py` 路由 | 返回安居客平台挂牌记录 |
| FR4（GET /api/houses/listings/{id}） | `mock_rental_api.py` 路由 | 三平台挂牌记录，`data.total/page_size/items` 结构 |
| FR5（GET /api/houses/by_community） | `mock_rental_api.py` 路由 | 默认安居客，page 分页 |
| FR6（GET /api/houses/by_platform） | `mock_rental_api.py:filter_houses()` | 多条件筛选，默认安居客 |
| FR7（GET /api/houses/nearby） | `mock_rental_api.py` 路由 | 按 landmark_id + max_distance 筛选 |
| FR8（GET /api/houses/nearby_landmarks） | `mock_rental_api.py` 路由 | 按距离升序排序 |
| FR9（GET /api/houses/stats） | `mock_rental_api.py` 路由 | 内存统计，实时计算 |
| FR10（rent/terminate/offline） | `mock_rental_api.py` 路由 | 三平台状态联动更新 |
| FR11（GET /api/landmarks） | `mock_rental_api.py` 路由 | category + district 交集筛选 |
| FR12（GET /api/landmarks/search） | `mock_rental_api.py` 路由 | q 关键词模糊搜索 + 多条件 |
| FR13（GET /api/landmarks/name/{name}） | `mock_rental_api.py` 路由 | 名称精确查询 |
| FR14（GET /api/landmarks/{id}） | `mock_rental_api.py` 路由 | ID 查询 |
| FR15（GET /api/landmarks/stats） | `mock_rental_api.py` 路由 | 按类别统计 |
| FR16（X-User-ID 接受不校验） | `mock_rental_api.py` 全部路由 | `Header(default=None)` 接收但不使用 |
| FR17（响应统一包装） | `mock_rental_api.py:success_response()` | 所有路由调用同一包装函数 |
| FR18（POST /v1/chat/completions） | `llm_proxy.py` 路由 | OpenAI 兼容格式接收 |
| FR19（透传模式） | `llm_proxy.py:passthrough()` | httpx 转发，原样返回 |
| FR20（Stub 模式）| `llm_proxy.py:stub_response()` | 返回固定 OpenAI 格式响应 |
| FR21（Stub 不触发 tool_calls）| `llm_proxy.py` | 检测 `tools` 字段，强制 finish_reason="stop" |
| FR22（Test Runner 读取 YAML + 启动服务）| `test_runner.py:main()` | argparse + subprocess.Popen |
| FR23（健康检查等待）| `test_runner.py:wait_for_health()` | 轮询 /health，最多 30 秒 |
| FR24（唯一 session_id）| `test_runner.py:run_single_case()` | `uuid4().hex[:8]` 后缀 |
| FR25（用例前数据重置）| `test_runner.py:reset_test_state()` | 直接 POST /api/houses/init |
| FR26（chat 类型验证）| `test_runner.py:validate_result()` | status == "success" && response 非空 |
| FR27（house_search 精确匹配）| `test_runner.py:validate_result()` | `set(actual) == set(expected)` |
| FR28（action 类型验证）| `test_runner.py:validate_result()` | status == "success" |
| FR29（multi 多轮发送）| `test_runner.py:run_single_case()` | for 循环，同 session_id |
| FR30（--case 单用例）| `test_runner.py:main()` | argparse `--case` 参数过滤 |
| FR31（全量顺序执行）| `test_runner.py:run_all_cases()` | YAML 顺序迭代 |
| FR32（测试报告）| `test_runner.py:print_report()` | 彩色终端，失败用例附对比 |
| FR33（数据生成脚本）| `generate_mock_data.py` | 读取 generate_config.yaml |
| FR34（ID 格式）| `generate_mock_data.py` | `HF_*` / `LM_*` 格式 |
| FR35（房源字段完整性）| `generate_mock_data.py` | 三平台挂牌记录 + 全字段 |
| FR36（地标类别覆盖）| `generate_mock_data.py` | 地铁站/公司/商圈三类，近邻关联 |

---

### Integration Points（集成点定义）

**与主项目的唯一集成接口：**

| 接口 | 方向 | 协议 | 说明 |
|------|------|------|------|
| `POST /api/v1/chat` | Test Runner → Agent | HTTP/JSON | 标准 ChatRequest 格式 |
| `RENTAL_API_BASE` 环境变量 | Test Runner → Agent（启动配置） | 环境变量 | 指向 Mock Rental API |
| `RENTAL_API_BASE` 环境变量 | Agent → Mock Rental API | HTTP（Agent 内部） | 前置变更 Prerequisites |

**内部服务通信（全部通过 HTTP loopback）：**

```
Test Runner
  │ POST /api/houses/init
  ├──────────────────────► Mock Rental API (127.0.0.1:9080)
  │
  │ POST /api/v1/chat
  └──────────────────────► Agent (127.0.0.1:8191)
                               │ GET /api/houses/*
                               ├──────────────────► Mock Rental API (127.0.0.1:9080)
                               │ POST /v1/chat/completions
                               └──────────────────► LLM Proxy (127.0.0.1:8888)
                                                        │（透传模式）
                                                        └──────────► Cloud qwen3 API
```

---

### Development Workflow Integration

**快速启动命令（全量测试）：**
```bash
# 设置必要环境变量
set RENTAL_API_BASE=http://127.0.0.1:9080   # Windows
# export RENTAL_API_BASE=http://127.0.0.1:9080  # Linux

# Stub 模式（离线，不调用真实 LLM）
python -m tests.test_runner

# 透传模式（使用真实 LLM）
set LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
set LLM_API_KEY=<your_key>
python -m tests.test_runner
```

**单用例调试命令：**
```bash
python -m tests.test_runner --case multi_commute_filter
```

**数据生成命令：**
```bash
python tests/generate_mock_data.py --config tests/generate_config.yaml --output tests/mock_data.yaml
```

**Agent 启动（配合测试框架）：**
```bash
set RENTAL_API_BASE=http://127.0.0.1:9080
set USER_ID=<工号>
uvicorn main:app --host 0.0.0.0 --port 8191
```

---

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility（决策兼容性）：**

所有技术选型完全兼容。全链路 Python，FastAPI 用于两个 Mock 服务，`subprocess.Popen` 用于进程管理，`httpx` 用于 HTTP 调用，`pyyaml` 用于配置解析，ANSI 内联码用于彩色输出——无外部依赖冲突，不引入新的复杂度。

**Pattern Consistency（模式一致性）：**

Mock API 统一响应包装、命名规范、内存数据管理模式相互一致，无矛盾。测试隔离（直接调用 init 而非依赖 Agent 钩子）与多轮用例执行模式兼容。

**Main Project Alignment（与主项目对齐）：**

- 响应格式与竞赛 API 完全一致（`code/message/data` 包装层）
- House ID / Platform 枚举与主项目 architecture.md 保持一致
- LLM Proxy 返回标准 OpenAI 格式，Agent 无感知差异

### Requirements Coverage Validation ✅

- **FR Coverage:** 36/36 FR 全部覆盖，见上方映射表
- **NFR Coverage:** 10/10 NFR 均有明确架构机制支撑

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] 4 个组件职责明确（Mock API / LLM Proxy / Test Runner / Data Generator）
- [x] NFR 约束逐条映射到具体实现机制（健康检查 30s / 响应 50ms / 全量 30s）
- [x] 技术约束识别（固定端口、主项目前置变更、跨平台要求）
- [x] 横切关注点全部解决（子进程管理、YAML 解析、端口冲突、测试隔离、彩色输出、错误处理）

**✅ Architectural Decisions**
- [x] 子进程编排策略（subprocess.Popen，决策 1）
- [x] 健康检查策略（HTTP 轮询，决策 2）
- [x] Mock 数据存储（内存 dict + deepcopy 重置，决策 3）
- [x] LLM Proxy 双模式（环境变量自动判断，决策 4）
- [x] 结果判定策略（三种精确验证，决策 5）
- [x] 测试隔离策略（直接调用 init，决策 6）
- [x] 彩色输出兼容（ANSI + NO_COLOR 回退，决策 7）

**✅ Implementation Patterns**
- [x] 命名规范（snake_case / ALL_CAPS / PascalCase / ID 格式）
- [x] 模块职责边界（禁止跨界引用）
- [x] 响应格式规范（统一包装函数）
- [x] 通信规范（Agent 请求格式 / 超时控制 / 健康检查）
- [x] 过程规范（错误层次 / 过滤逻辑 / 数据生成一致性）

**✅ Project Structure**
- [x] 完整目录结构（6 个核心文件）
- [x] 组件边界确立（禁止的跨界引用明确列出）
- [x] FR 到结构映射（36 FR 全部对应到文件/函数）
- [x] 集成点定义（与主项目接口 + 内部服务通信）

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION ✅

**Confidence Level:** High — 架构决策完整覆盖所有 FR/NFR，模式清晰，结构具体，AI Agent 可据此直接实现而无需额外澄清。

**Key Strengths:**
- 子进程隔离设计保证各服务崩溃不影响 Test Runner 稳定性
- 测试隔离通过直接调用 Mock API init 实现，不依赖 Agent 内部实现细节
- LLM Proxy 双模式设计允许在无 LLM 的环境中验证框架本身的正确性
- 全链路内存运行，无数据库依赖，Mock API 启动 < 3 秒目标可实现

**Prerequisites Reminder（主项目必须先完成的变更）：**
```python
# main.py 中必须将以下硬编码替换为环境变量：
import os
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
# lifespan 中:
app.state.client = httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=30.0)
```

### Implementation Handoff

**AI Agent 实现指引：**
- 读取本文档 + `prd-test-simulator.md` 后开始实现
- 优先实现 Mock Rental API（FR1-FR17），这是整个框架的数据基础
- `GET /health` 端点对 Test Runner 健康检查至关重要，必须在所有业务路由之前实现
- 所有 Mock API 响应必须通过统一的 `success_response()` / `error_response()` 包装函数
- House ID 永远保持字符串格式 `"HF_<n>"`，不得转为整数

**Phase 1 实现优先级（MVP）：**
```
1. mock_rental_api.py：
   - load_mock_data() + reset_houses()
   - GET /health
   - POST /api/houses/init
   - GET /api/houses/{id}
   - GET /api/houses/by_platform
   - GET /api/houses/nearby
   - GET /api/houses/nearby_landmarks
   - GET /api/landmarks/search
   - POST /api/houses/{id}/rent, /terminate, /offline

2. llm_proxy.py：
   - GET /health
   - POST /v1/chat/completions（Stub 模式）

3. test_runner.py：
   - 子进程启动（Mock API + LLM Proxy）
   - wait_for_health()
   - 支持 chat + single 用例执行
   - 精确匹配判定
   - 终端报告

4. 主项目 main.py：RENTAL_API_BASE 环境变量化
```

**Phase 2 扩展：**
```
- Mock Rental API：补齐剩余端点（by_community, listings, stats 等）
- LLM Proxy：实现透传模式（LLM_API_BASE + LLM_API_KEY）
- Test Runner：支持 multi 多轮用例 + --case 单用例调试
- generate_mock_data.py：数据生成脚本
```
