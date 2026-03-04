# AI Agent Coding

基于 FastAPI + qwen3-32b 的智能租房助手 Agent，通过 LLM Tool Calling 实现房源搜索、地标查询和租赁操作。

## 启动服务

```powershell
$env:USER_ID = "<你的工号>"; uvicorn main:app --host 0.0.0.0 --port 8191
```

## 端到端验证

E2E 脚本自动拉起 test-simulator（Model Proxy + Mock Rental + Dashboard）和主 Agent，运行测试后清理进程。进程输出日志在 `tests/e2e/logs/`，HTML/JSON 报告在 `tests/e2e/reports/`。

### PowerShell (Windows)

```powershell
# 必填参数
.\tests\e2e\run_e2e.ps1 -UserId "<你的工号>"
```

**运行模式：**

| 模式 | 参数 | 说明 |
|------|------|------|
| 仿真全部用例 | 默认 | 运行 test_cases.yaml 全部用例 |
| 仿真单用例 | `-SimCase "ev06_wangjing_to_daxing_rental_flow"` | 运行指定 ID 用例 |
| 仿真按 tag | `-SimTag "ev03"` | 运行匹配 tag 的用例 |

**可选参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-ReadyTimeoutSec` | 30 | 等待服务就绪的最大秒数 |
| `-ModelProxyPort` | 8888 | Model Proxy 端口 |
| `-MockRentalPort` | 8080 | Mock Rental 端口 |
| `-DashboardPort` | 8877 | Dashboard 端口 |
| `-AgentPort` | 8191 | 主 Agent 端口 |

**示例：**

```powershell
# 运行仿真器全部用例（Dashboard: http://localhost:8877/）
.\tests\e2e\run_e2e.ps1 -UserId "EMP001"

# 运行指定仿真用例
.\tests\e2e\run_e2e.ps1 -UserId "EMP001" -SimCase "ev06_wangjing_to_daxing_rental_flow"

# 多实例并行（端口偏移避免冲突）
.\tests\e2e\run_e2e.ps1 -UserId "EMP002" -ModelProxyPort 8988 -MockRentalPort 8180 -DashboardPort 8977 -AgentPort 8291
```

## Mock vs 真实服务器一致性测试

验证 Mock 服务器与真实服务器的 API 行为是否一致，覆盖全部 11 个 API 函数及 22 个筛选参数组合（共 65 个用例）。失败用例及原因写入报告文件，便于离线对比。

### Mock 模式（本地直接运行）

```powershell
cd test-simulator
python -m pytest tests/test_monk_vs_real_parity.py -v `
  --parity-report=mock_data/monk_vs_real_test_results.txt
```

### 真实服务器模式（内网验证）

```powershell
cd test-simulator
$env:RENTAL_API_BASE = "http://真实服务器地址:8080"
$env:USER_ID = "<你的工号>"
python -m pytest tests/test_monk_vs_real_parity.py -v `
  --parity-report=mock_data/real_server_test_results.txt
```

### 使用完整数据集（final-test.yaml）

```powershell
cd test-simulator
$env:PARITY_USE_FINAL_TEST = "1"
python -m pytest tests/test_monk_vs_real_parity.py -v `
  --parity-report=mock_data/monk_vs_real_test_results.txt
```

也可指定任意 fixture 文件：

```powershell
$env:PARITY_FIXTURE_PATH = "mock_data/EV-06.yaml"
python -m pytest tests/test_monk_vs_real_parity.py -v `
  --parity-report=mock_data/monk_vs_real_test_results.txt
```

报告输出示例（`mock_data/monk_vs_real_test_results.txt`）：

```
============================================================
Monk vs Real Server 一致性测试结果
============================================================
总用例数: 65
通过: 65
失败: 0
============================================================
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
