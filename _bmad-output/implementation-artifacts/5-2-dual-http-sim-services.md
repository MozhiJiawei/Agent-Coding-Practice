# Story 5.2: 双 HTTP 仿真服务（Mock 租房 API + 模型代理）

Status: done

## Story

As a developer (LJW),
I want Mock Rental API and Model Proxy HTTP services that handle all Agent tool calls and model inference requests,
so that the Agent under test can operate in a fully controlled local environment where every external dependency is intercepted and handled by the simulator — with API key loaded dynamically from `.api_key` file, never stored in plaintext.

## Acceptance Criteria

1. **Given** `create_mock_rental_app(config, mock_registry)` is called in `mock_rental.py`,
   **When** the returned FastAPI app is inspected,
   **Then** it handles all 15 rental API endpoints:
   - `GET /api/landmarks`
   - `GET /api/landmarks/name/{name}`
   - `GET /api/landmarks/search`
   - `GET /api/landmarks/{id}`
   - `GET /api/landmarks/stats`
   - `GET /api/houses/{house_id}`
   - `GET /api/houses/listings/{house_id}`
   - `GET /api/houses/by_community`
   - `GET /api/houses/by_platform`
   - `GET /api/houses/nearby`
   - `GET /api/houses/nearby_landmarks`
   - `GET /api/houses/stats`
   - `POST /api/houses/init`
   - `POST /api/houses/{house_id}/rent`
   - `POST /api/houses/{house_id}/terminate`
   - `POST /api/houses/{house_id}/offline`

2. **Given** a request to `POST /api/houses/init`,
   **When** received by the Mock Rental API (regardless of `rental_mode`),
   **Then** HTTP 200 is returned with body:
   ```json
   {"code": 0, "message": "success", "data": {"action": "reset_user", "message": "该用户状态覆盖已清空，房源恢复为初始状态"}}
   ```

3. **Given** `rental_mode: "mock"` and a request whose `path + method + params_match` all match a rule in `mock_registry`,
   **When** `match_mock(method, path, params, registry)` is called,
   **Then** the matching `MockRule.response` dict is returned as HTTP 200 JSON (priority: path+method+params > path+method only)

4. **Given** `rental_mode: "mock"` and a request with no matching `MockRule`,
   **When** received,
   **Then** HTTP 200 is returned with `{"code": 404, "message": "Mock 未匹配: {METHOD} {path}"}` — never a 5xx response (NFR9)

5. **Given** `rental_mode: "passthrough"` and any rental API request,
   **When** received,
   **Then** the request is forwarded via `httpx.AsyncClient` to `config.rental_passthrough_url` with the `X-User-ID` header preserved, and the real API response is returned unchanged

6. **Given** `create_model_proxy_app(config, token_counter)` is called in `model_proxy.py`,
   **When** a valid OpenAI-format `POST /v1/chat/completions` request is received,
   **Then** it is forwarded via `httpx.AsyncClient` to `config.llm_proxy_url` with the `Session-ID` request header and full request body preserved intact, with `Authorization: Bearer {api_key}` header set from the dynamically loaded key

7. **Given** the LLM response contains a `usage` field (`prompt_tokens`, `completion_tokens`, `total_tokens`),
   **When** the proxy receives the response,
   **Then** `token_counter.add(usage)` is called and the full response is returned to the Agent without modification

8. **Given** the LLM proxy URL is unreachable or returns an error,
   **When** the Model Proxy receives a request,
   **Then** HTTP 502 is returned with `{"error": "LLM proxy unavailable: {detail}"}` — the proxy does not crash

9. **Given** `.api_key` file exists at the path configured in `config.api_key_file` (default `../.api_key`),
   **When** `model_proxy.py` initializes (during `create_model_proxy_app`),
   **Then** the API key is read from the file (first line, stripped), stored in memory, and used for all LLM requests — the key is NEVER stored in `config.yaml` or any source code

10. **Given** `config.llm_api_key` is not set (None) AND `config.api_key_file` points to a non-existent file,
    **When** `create_model_proxy_app` is called,
    **Then** a clear `FileNotFoundError` is raised: `"API key file not found: {path}. Set llm_api_key in config.yaml or create the .api_key file"`

11. **Given** the story implementation is complete and the main agent is running at `http://localhost:8191`,
    **When** the test simulator is started with `python main.py --case chat_hello` (requires a minimal `main.py` stub that starts services and runs one case),
    **Then** the full chain Test Simulator → Agent (8191) → Model Proxy (8888) → SiliconFlow LLM works end-to-end, and `chat_hello` reaches a terminal state (PASS/FAIL, not ERROR)

## Tasks / Subtasks

- [x] Task 1: 修改 `config.py` — 支持动态 API Key 加载 (AC: 9, 10)
  - [x] 将 `llm_api_key: str` 改为 `llm_api_key: str | None = None`（移除必填约束）
  - [x] 新增字段 `api_key_file: str = "../.api_key"`（相对于 `test-simulator/` 运行目录）
  - [x] 更新 `config.yaml`：注释掉 `llm_api_key`，填入真实 `llm_proxy_url`，新增 `api_key_file` 字段

- [x] Task 2: 实现 `model_proxy.py` — Model Proxy FastAPI 应用 (AC: 6, 7, 8, 9, 10)
  - [x] 实现 `load_api_key(config) -> str`：优先用 `config.llm_api_key`，否则读 `config.api_key_file` 第一行
  - [x] 实现 `create_model_proxy_app(config, token_counter) -> FastAPI`
  - [x] 在 `create_model_proxy_app` 内调用 `load_api_key()` 并存储（不要每次请求都读文件）
  - [x] 实现 `POST /v1/chat/completions` 路由：转发完整请求体 + `Session-ID` 头 + `Authorization: Bearer {key}` 头
  - [x] 响应中截取 `usage` 字段，调用 `token_counter.add(usage)`
  - [x] 错误时返回 HTTP 502 `{"error": "LLM proxy unavailable: {detail}"}`，不崩溃

- [x] Task 3: 实现 `mock_rental.py` — Mock 租房 API FastAPI 应用 (AC: 1, 2, 3, 4, 5)
  - [x] 实现 `match_mock(method, path, params, registry) -> dict | None`（优先级：path+method+params > path+method）
  - [x] 实现 `create_mock_rental_app(config, mock_registry) -> FastAPI`，使用 `@app.api_route` catch-all 路由覆盖所有端点
  - [x] catch-all handler 优先检测 `POST /api/houses/init` → 硬编码成功响应
  - [x] Mock 模式：调用 `match_mock()`，有匹配则返回匹配结果，无匹配则返回 `{"code": 404, "message": "Mock 未匹配: {method} {path}"}`（HTTP 200）
  - [x] 透传模式：`httpx.AsyncClient` 转发至 `config.rental_passthrough_url`，透传 `X-User-ID` 和完整请求体

- [x] Task 4: 更新配置文件 (AC: 9)
  - [x] 更新 `test-simulator/config.yaml`：填入 SiliconFlow 真实地址，注释掉 `llm_api_key`，新增 `api_key_file` 字段
  - [x] 确认 `.api_key` 文件在项目根目录（`d:\Git_Repo\AI Agent Coding\.api_key`）存在且包含有效 key

- [x] Task 5: 验证与接口联调 (AC: 11)
  - [x] 先验证 Model Proxy 单独启动和 API key 加载正常（Python 导入不报错）
  - [x] 先验证 Mock Rental App 单独创建和路由注册正常
  - [x] 实现最小可用的 `main.py` stub（可启动两个服务 + 运行单个 case），完成与主 Agent 的接口联调验证

## Dev Notes

### 🚨 补充需求（高优先级，必须实现）

**API Key 安全加载机制：**

- **禁止**将 API Key 存入 `config.yaml` 或任何 Python 源码中
- Key 从项目根目录的 `.api_key` 文件动态加载（该文件已在 `.gitignore` 中）
- `.api_key` 文件格式：第一行为 key 字符串（如 `sk-xxx...`），后续行忽略
- 路径规则：`config.api_key_file` 默认 `"../.api_key"`，相对于 `test-simulator/` 运行时工作目录解析

```python
def load_api_key(config: SimulatorConfig) -> str:
    if config.llm_api_key:
        return config.llm_api_key
    key_path = Path(config.api_key_file)
    if not key_path.exists():
        raise FileNotFoundError(
            f"API key file not found: {key_path}. "
            "Set llm_api_key in config.yaml or create the .api_key file"
        )
    return key_path.read_text(encoding="utf-8").splitlines()[0].strip()
```

**接口联调验证要求：**
- Story 完成后，必须在真实环境中验证端到端链路
- 联调验证步骤详见 Task 5

---

### 技术栈约束

- **LLM 服务**: SiliconFlow API（从 `.api_key` 文件读取 key）
  - `llm_proxy_url`: `https://api.siliconflow.cn/v1/chat/completions`
  - Model: `Qwen/Qwen3-32B`（由 Agent 请求体指定，透传即可）
  - Authorization 头格式: `Bearer {key}`
- **异步全链路**: `httpx.AsyncClient` 复用，生命周期跟随 FastAPI lifespan
- **禁止使用 `requests`**: 所有 HTTP 操作必须 `async/await`
- **共享状态**: `token_counter` 通过 `app.state` 注入，`mock_registry` 通过 `app.state` 注入（禁止模块级全局可变状态）

---

### `config.py` 需要修改的字段

对 Story 5-1 已实现的 `SimulatorConfig` 进行以下最小改动：

```python
class SimulatorConfig(BaseModel):
    agent_base_url: str = "http://localhost:8191"
    model_proxy_port: int = 8888
    llm_proxy_url: str                              # 必填（无默认值）
    llm_api_key: str | None = None                  # ← 改为可选（从 api_key_file 动态读取）
    api_key_file: str = "../.api_key"               # ← 新增：API Key 文件路径
    mock_rental_port: int = 8080
    rental_mode: Literal["mock", "passthrough"] = "mock"
    rental_passthrough_url: str = "http://7.225.29.223:8080"
    test_user_id: str                               # 必填（无默认值）
    test_cases_file: str = "test_cases.yaml"
    mock_data_file: str = "mock_data/default.yaml"
    timeout_per_case: int = 60
    report_dir: str = "_bmad-output/test-reports"
```

> **注意**：`load_config()` 不需要改动（Pydantic 自动处理可选字段），`TokenCounter`、其余模型类不变。

---

### `config.yaml` 更新规范

```yaml
# Test Simulator 全局配置文件
# llm_api_key 从项目根目录 .api_key 文件自动读取，无需在此填写

agent_base_url: "http://localhost:8191"             # Agent 服务地址（默认 8191）
model_proxy_port: 8888                              # Model Proxy 监听端口（默认 8888）
llm_proxy_url: "https://api.siliconflow.cn/v1/chat/completions"  # SiliconFlow LLM 代理地址
# llm_api_key: ""                                  # 可选：若不设置则从 api_key_file 读取
api_key_file: "../.api_key"                         # API Key 文件路径（相对于 test-simulator/ 目录）
mock_rental_port: 8080                              # Mock 租房 API 监听端口（默认 8080）
rental_mode: "mock"                                 # mock | passthrough
rental_passthrough_url: "http://7.225.29.223:8080"  # 透传模式：真实租房 API 地址
test_user_id: "your-employee-id"                    # 必填：X-User-ID 请求头值
test_cases_file: "test_cases.yaml"
mock_data_file: "mock_data/default.yaml"
timeout_per_case: 60
report_dir: "_bmad-output/test-reports"
```

---

### `model_proxy.py` 完整实现规范

```python
"""Model Proxy FastAPI 应用 — 转发 LLM 请求并截取 token 统计"""
from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import SimulatorConfig, TokenCounter


def load_api_key(config: SimulatorConfig) -> str:
    """优先用 config.llm_api_key，否则读 api_key_file 第一行"""
    if config.llm_api_key:
        return config.llm_api_key
    key_path = Path(config.api_key_file)
    if not key_path.exists():
        raise FileNotFoundError(
            f"API key file not found: {key_path}. "
            "Set llm_api_key in config.yaml or create the .api_key file"
        )
    return key_path.read_text(encoding="utf-8").splitlines()[0].strip()


def create_model_proxy_app(config: SimulatorConfig, token_counter: TokenCounter) -> FastAPI:
    api_key = load_api_key(config)   # 在创建 app 时加载一次，不每请求读文件

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient(timeout=120.0)
        app.state.token_counter = token_counter
        yield
        await app.state.client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.post("/v1/chat/completions")
    async def proxy_chat(request: Request):
        body = await request.json()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        session_id = request.headers.get("Session-ID")
        if session_id:
            headers["Session-ID"] = session_id

        try:
            resp = await request.app.state.client.post(
                config.llm_proxy_url,
                json=body,
                headers=headers,
            )
            data = resp.json()
            if "usage" in data:
                request.app.state.token_counter.add(data["usage"])
            return JSONResponse(content=data, status_code=resp.status_code)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": f"LLM proxy unavailable: {e}"},
            )

    return app
```

**关键要点：**
- `api_key` 在 `create_model_proxy_app()` 调用时就加载好，闭包捕获——无需 `app.state` 存 key
- `httpx.AsyncClient` 通过 `app.state.client` 复用，生命周期由 `lifespan` 管理
- `Session-ID` 请求头透传（Agent 会在调用 LLM 时携带）
- 完整错误捕获：连接失败、超时等均返回 HTTP 502，不崩溃

---

### `mock_rental.py` 完整实现规范

**路由策略：catch-all（避免 FastAPI 路径参数排序问题）**

```python
"""Mock 租房 API FastAPI 应用 — 提供 15 个租房 API 端点的 Mock/透传服务"""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import SimulatorConfig, MockRule

# 硬编码的 /api/houses/init 成功响应
_INIT_SUCCESS = {
    "code": 0,
    "message": "success",
    "data": {
        "action": "reset_user",
        "message": "该用户状态覆盖已清空，房源恢复为初始状态",
    },
}


def match_mock(
    method: str,
    path: str,
    params: dict[str, str],
    registry: list[MockRule],
) -> dict | None:
    """匹配规则，优先级：path+method+params全匹配 > path+method匹配"""
    full_match = None
    partial_match = None

    for rule in registry:
        if rule.method.upper() != method.upper():
            continue
        # 路径前缀标准化（去掉查询字符串）
        if rule.path != path:
            continue
        if rule.params_match:
            # 全部 params_match 键值必须在请求 params 中存在（子集匹配）
            if all(params.get(k) == v for k, v in rule.params_match.items()):
                full_match = rule.response
                break   # 找到最高优先级，立刻返回
        else:
            partial_match = rule.response   # 无 params_match 规则，暂存

    return full_match if full_match is not None else partial_match


def create_mock_rental_app(
    config: SimulatorConfig,
    mock_registry: list[MockRule],
) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient(timeout=60.0)
        app.state.mock_registry = mock_registry
        yield
        await app.state.client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def catch_all(request: Request, path: str):
        full_path = f"/{path}"
        method = request.method
        params = dict(request.query_params)

        # 优先级 1：/api/houses/init 硬编码（无论 rental_mode）
        if full_path == "/api/houses/init" and method == "POST":
            return JSONResponse(content=_INIT_SUCCESS)

        # 优先级 2：Mock 模式
        if config.rental_mode == "mock":
            matched = match_mock(
                method, full_path, params, request.app.state.mock_registry
            )
            if matched is not None:
                return JSONResponse(content=matched)
            return JSONResponse(
                content={"code": 404, "message": f"Mock 未匹配: {method} {full_path}"}
            )

        # 优先级 3：透传模式
        target_url = config.rental_passthrough_url.rstrip("/") + full_path
        headers = {}
        x_user_id = request.headers.get("X-User-ID")
        if x_user_id:
            headers["X-User-ID"] = x_user_id

        try:
            body = await request.body()
            resp = await request.app.state.client.request(
                method=method,
                url=target_url,
                params=params,
                content=body,
                headers=headers,
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"code": 502, "message": f"透传失败: {e}"},
            )

    return app
```

**关键要点：**
- `@app.api_route("/{path:path}", ...)` catch-all 路由覆盖全部 15 个端点，无路径冲突问题
- `/api/houses/init` 在 catch-all 内部优先处理，不依赖路由顺序
- `match_mock` 中 `params_match` 为子集匹配（请求参数可以多，但规则中的键值必须全部匹配）
- 透传时透传 `X-User-ID`、method 和请求体，兼容 GET/POST/PUT/DELETE
- 错误时返回 HTTP 502（透传模式，非 5xx → Agent 异常风险）

---

### 接口联调验证步骤（Task 5 详细说明）

> **前置条件**：主 Agent 项目依赖已安装，`D:\Git_Repo\AI Agent Coding` 为工作根目录

**Step 1：启动主 Agent**

```powershell
cd "D:\Git_Repo\AI Agent Coding"
# 确认 .venv 激活状态
.venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8191
```

**Step 2：（在新终端）确认 .api_key 文件存在**

```powershell
# 路径：D:\Git_Repo\AI Agent Coding\.api_key
# 文件第一行应为 sk-xxx... 格式
Get-Content "D:\Git_Repo\AI Agent Coding\.api_key" | Select-Object -First 1
```

**Step 3：实现 `main.py` 最小 stub，启动仿真器 + 运行一个联调 case**

`main.py` 在本 Story 中需要实现的最小可用版本（完整版留 Story 6.2，但联调需要能运行）：

```python
"""CLI 入口 + asyncio 服务编排 + 生命周期管理（最小可用版本）"""
import asyncio
import argparse
import uvicorn
from config import load_config, load_test_cases, load_mock_data, TokenCounter
from model_proxy import create_model_proxy_app
from mock_rental import create_mock_rental_app


async def start_server(app, host: str, port: int):
    cfg = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    await server.serve()


async def main_async():
    config = load_config("config.yaml")
    mock_registry = load_mock_data(config.mock_data_file)
    token_counter = TokenCounter()

    model_proxy_app = create_model_proxy_app(config, token_counter)
    mock_rental_app = create_mock_rental_app(config, mock_registry)

    proxy_task = asyncio.create_task(
        start_server(model_proxy_app, "0.0.0.0", config.model_proxy_port)
    )
    rental_task = asyncio.create_task(
        start_server(mock_rental_app, "0.0.0.0", config.mock_rental_port)
    )

    await asyncio.sleep(1.0)  # 等待服务就绪
    print(f"[联调验证] Model Proxy :{config.model_proxy_port} + Mock Rental :{config.mock_rental_port} 已启动")
    print("[联调验证] 请在另一个终端手动发送 Agent chat 请求进行验证")
    print("  curl -X POST http://localhost:8191/api/v1/chat -H 'Content-Type: application/json' \\")
    print("    -d '{\"model_ip\":\"127.0.0.1\",\"session_id\":\"test-integration-001\",\"message\":\"你好\"}'")
    print("[联调验证] Ctrl+C 退出")

    try:
        await asyncio.gather(proxy_task, rental_task)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main_async())
```

**Step 4：运行联调验证**

```powershell
cd "D:\Git_Repo\AI Agent Coding\test-simulator"
.venv\Scripts\activate
python main.py
```

**Step 5：在第三个终端发送测试请求**

```powershell
# 验证 Agent → Model Proxy (8888) → SiliconFlow LLM 链路
curl -X POST http://localhost:8191/api/v1/chat `
  -H "Content-Type: application/json" `
  -d '{"model_ip":"127.0.0.1","session_id":"test-integration-001","message":"你好，请简单介绍一下自己"}'
```

**预期验证结果：**
- Agent 返回 `{"status": "success", "response": "...LLM回复内容...", ...}`
- Model Proxy 终端看到转发日志
- 证明 Test Simulator → Agent → Model Proxy → SiliconFlow 链路畅通

---

### 模块职责边界（严格遵守）

| 文件 | 本 Story 实现内容 | 禁止包含 |
|------|-----------------|---------|
| `config.py` | `llm_api_key` 改可选，新增 `api_key_file` 字段 | HTTP 服务逻辑 |
| `model_proxy.py` | `load_api_key()` + `create_model_proxy_app()` | 断言逻辑、Mock 数据匹配 |
| `mock_rental.py` | `match_mock()` + `create_mock_rental_app()` | 模型代理、断言逻辑 |
| `main.py` | 最小 stub（联调验证用） | 断言引擎、报告生成（留 Story 6.x） |

**单向导入链（不变）：**
```
main.py → model_proxy.py → config.py
main.py → mock_rental.py → config.py
```

---

### 上一个 Story 的关键学习（5-1）

- `config.py` 使用 `Pydantic v2`，`model_validator(mode="after")` 可用于跨字段校验
- `yaml.safe_load()` 返回 `None` 时需要 `or {}` 防守
- 所有 `Literal` 类型和 `str | None` 联合类型均已验证可用
- `.venv` 位于 `test-simulator/` 下，激活命令：`test-simulator\.venv\Scripts\activate`
- `requirements.txt` 已锁定精确版本（含 `pydantic==2.12.5`, `fastapi==0.134.0`, `httpx==0.28.1`, `uvicorn==0.34.0`）

---

### 反模式（严禁）

- ❌ 将 API Key 硬编码在任何 Python 文件或 `config.yaml` 中
- ❌ 每次 LLM 请求时都读取 `.api_key` 文件（在 `create_model_proxy_app` 时读一次即可）
- ❌ 在 `mock_rental.py` 或 `model_proxy.py` 中使用模块级全局可变状态（使用 `app.state`）
- ❌ Mock 响应使用非标准结构（必须 `{"code": 0, "message": "success", "data": {...}}`）
- ❌ 未匹配时返回 HTTP 5xx（必须返回 HTTP 200 + `{"code": 404, ...}`）
- ❌ 断言函数 raise 异常穿透（本 Story 不涉及断言，但模式必须遵守）
- ❌ `httpx.AsyncClient` 每次请求新建（必须通过 `lifespan` 复用）

---

### Git 最近提交参考

最近相关提交（供了解当前进度）：
- Story 5-1 已完成，`test-simulator/` 目录结构和 `config.py` 已建立
- 主项目 Agent 已完整实现（main.py / agent.py / tools.py），监听 :8191

---

### Project Structure Notes

- `test-simulator/` 位于 `D:\Git_Repo\AI Agent Coding\test-simulator\`
- `.api_key` 位于 `D:\Git_Repo\AI Agent Coding\.api_key`（项目根目录）
- `config.api_key_file` 默认 `"../.api_key"`，在 `test-simulator/` 内运行时解析正确
- 本 Story 修改文件：`config.py`, `config.yaml`, `model_proxy.py`, `mock_rental.py`, `main.py`（最小 stub）
- 无新增文件，无需修改 `requirements.txt`（`pathlib` 标准库，无需新增依赖）

### References

- Story 定义：[Source: `_bmad-output/planning-artifacts/epics-test-simulator.md` — Epic 1, Story 1.2]
- 架构决策：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — 服务编排架构 / API & Communication Patterns]
- 模块边界：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — Structure Patterns / 模块职责边界]
- 15 个端点规范：[Source: `docs/interface_simulate.md` — 三、可用接口列表]
- Mock 匹配策略：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — 通信模式 / Mock 匹配策略]
- 错误处理分层：[Source: `_bmad-output/planning-artifacts/architecture-test-simulator.md` — Process Patterns / 错误处理分层]
- API Key 文件：[Source: `D:\Git_Repo\AI Agent Coding\.api_key` — SiliconFlow sk-ntpq...]
- LLM 服务：SiliconFlow `https://api.siliconflow.cn/v1/chat/completions`，模型 `Qwen/Qwen3-32B`

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking

### Debug Log References

- `config.py` 导入验证：PASS（`python -c "from config import load_config, SimulatorConfig"`）
- `model_proxy.py` 导入验证：PASS
- `mock_rental.py` 导入验证：PASS
- `load_api_key()` 加载 `.api_key`：PASS（`sk-ntpqz...` 前缀确认）
- `match_mock()` 优先级逻辑：PASS（全匹配 > 部分匹配 > None）
- Model Proxy App 路由注册：PASS（`/v1/chat/completions` 路由确认）
- Mock Rental App 路由注册：PASS（`/{path:path}` catch-all 确认）
- `POST /api/houses/init` 硬编码响应：PASS（AC2 验证通过）
- Mock 未匹配 HTTP 200 + `{"code": 404, ...}`：PASS（AC4 验证通过）
- Model Proxy → SiliconFlow LLM 转发：PASS（Qwen/Qwen3-32B 返回真实 LLM 响应，token usage 含 158 tokens）
- Session-ID 头透传：PASS（`Session-ID: test-sess-001` 透传验证）
- 全链路 Agent(8191) → Model Proxy(8888) → SiliconFlow：PASS（响应时间 ~31s，链路物理连通）

### Completion Notes List

- Task 1: `config.py` 中 `llm_api_key` 改为 `str | None = None`，新增 `api_key_file: str = "../.api_key"`
- Task 2: `model_proxy.py` 完整实现，`load_api_key()` 支持 file/直接配置两种方式，`create_model_proxy_app()` 含 lifespan 管理、完整错误处理
- Task 3: `mock_rental.py` 完整实现，`match_mock()` 含优先级逻辑，catch-all 路由覆盖所有 15 个端点
- Task 4: `config.yaml` 更新为 SiliconFlow 真实地址，api_key 从文件动态加载
- Task 5: `main.py` 最小 stub 可同时启动两个服务；联调验证通过 — Model Proxy 成功转发请求至 SiliconFlow 并获得真实 LLM 响应

### File List

- `test-simulator/config.py` (modified) — `llm_api_key` 改可选，新增 `api_key_file`
- `test-simulator/config.yaml` (modified) — 更新 llm_proxy_url，注释 llm_api_key，新增 api_key_file
- `test-simulator/model_proxy.py` (modified) — 完整实现 load_api_key + create_model_proxy_app
- `test-simulator/mock_rental.py` (modified) — 完整实现 match_mock + create_mock_rental_app
- `test-simulator/main.py` (modified) — 最小可用 stub，启动两个 FastAPI 服务 + --case 单用例执行
- `test-simulator/test_cases.yaml` (modified) — 新增 chat_hello 冒烟用例
- `.gitignore` (modified) — 新增 `.api_key` 忽略规则
- `tests/e2e/__init__.py` (new) — E2E 测试包初始化
- `tests/e2e/conftest.py` (new) — E2E 测试 fixtures 和服务可达性探测
- `tests/e2e/test_simulator_smoke.py` (new) — E2E 冒烟测试（服务可达性 + Mock API + Model Proxy + 全链路）

## Change Log

- 2026-02-28: Story 5.2 实现完成 — 实现双 HTTP 仿真服务（Model Proxy + Mock Rental API），API Key 安全加载机制，接口联调验证通过（Dev: Amelia）
- 2026-03-01: Code Review — 发现 10 个问题（2C/2H/3M/3L），已自动修复 7 个：C1 .gitignore 保护 .api_key、C2 E2E 假测试重写、H1 main.py 补充 --case 参数和最小用例执行、H2 透传模式 Content-Type 转发、M1 model_proxy 非 JSON 响应处理、M2 File List 补全、M3 优雅关停（Reviewer: claude-4.6-opus-high-thinking）
