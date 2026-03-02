# AI Agent Coding

基于 FastAPI + qwen3-32b 的智能租房助手 Agent，通过 LLM Tool Calling 实现房源搜索、地标查询和租赁操作。

## 启动服务

```powershell
$env:USER_ID = "<你的工号>"; uvicorn main:app --host 0.0.0.0 --port 8191
```

## 端到端验证

E2E 脚本自动拉起 test-simulator（Model Proxy + Mock Rental + Dashboard）和主 Agent，运行测试后清理进程。日志输出到 `logs/` 目录。

### PowerShell (Windows)

```powershell
# 必填参数
.\tests\run_e2e.ps1 -UserId "<你的工号>"
```

**运行模式：**

| 模式 | 参数 | 说明 |
|------|------|------|
| pytest E2E | 默认 | 执行 `tests/e2e/` 下的 pytest 用例 |
| 仿真全部用例 | `-SimAll` | 运行 test_cases.yaml 全部用例 |
| 仿真单用例 | `-SimCase "ev06_wangjing_to_daxing_rental_flow"` | 运行指定 ID 用例 |
| 仿真按 tag | `-SimTag "ev03"` | 运行匹配 tag 的用例 |

**可选参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-PytestArgs` | `"tests/e2e/ -v"` | 传给 pytest 的参数字符串 |
| `-ReadyTimeoutSec` | 30 | 等待服务就绪的最大秒数 |
| `-ModelProxyPort` | 8888 | Model Proxy 端口 |
| `-MockRentalPort` | 8080 | Mock Rental 端口 |
| `-DashboardPort` | 8877 | Dashboard 端口 |
| `-AgentPort` | 8191 | 主 Agent 端口 |

**示例：**

```powershell
# 运行 pytest 冒烟测试
.\tests\run_e2e.ps1 -UserId "EMP001" -PytestArgs "tests/e2e/ -v -m smoke"

# 运行仿真器全部用例（Dashboard: http://localhost:8877/）
.\tests\run_e2e.ps1 -UserId "EMP001" -SimAll

# 运行指定仿真用例
.\tests\run_e2e.ps1 -UserId "EMP001" -SimCase "ev06_wangjing_to_daxing_rental_flow"

# 多实例并行（端口偏移避免冲突）
.\tests\run_e2e.ps1 -UserId "EMP002" -SimAll -ModelProxyPort 8988 -MockRentalPort 8180 -DashboardPort 8977 -AgentPort 8291
```

### Bash (Linux / macOS)

```bash
# 必填参数 -u
bash tests/run_e2e.sh -u EMP001
```

**可选参数：** `-p` pytest 参数 | `-t` 超时秒数 | `-m` Model Proxy 端口 | `-r` Mock Rental 端口 | `-d` Dashboard 端口 | `-a` Agent 端口

```bash
bash tests/run_e2e.sh -u EMP001 -p "tests/e2e/ -v -m smoke" -t 60
bash tests/run_e2e.sh -u EMP002 -m 8988 -r 8180 -d 8977 -a 8291
```

## Smoke Test

```powershell
# 聊天类（response 应为自然语言字符串）
Invoke-RestMethod -Method POST -Uri http://localhost:8191/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"model_ip":"<模型IP>","session_id":"test-chat","message":"你好"}'

# 房源查询类（response 应为合法 JSON 字符串）
Invoke-RestMethod -Method POST -Uri http://localhost:8191/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"model_ip":"<模型IP>","session_id":"test-search","message":"找海淀区两居室"}'
```
