# test-simulator/tests

本目录包含 Monk vs 真实服务器一致性测试（`test_monk_vs_real_parity.py`）等用例。

## 本地回放（无需连真实服务器）

在无法直连内网真实 API 时，可以用**服务端已跑出的双端结果日志**在本地做对比迭代：本地只请求 Mock，用日志里记录的真实服务端响应与 Mock 响应做严格比对。

### 1. 准备日志文件

在能连真实服务器的环境跑一次双端一致性，生成带「服务端原始响应」的日志：

```bash
# 在内网或可访问真实 API 的机器上执行
PARITY_DUAL=1 RENTAL_API_BASE=http://内网地址 USER_ID=xxx pytest tests/test_monk_vs_real_parity.py -v --parity-report=mock_data/parity_dual_results.txt
```

将生成的 `parity_dual_results.txt`（或你指定的报告路径）拷贝到本机，例如放到本目录：

- `test-simulator/tests/parity_dual_results.txt`

### 2. 本地用日志回放跑测

在 **test-simulator** 根目录下执行：

**方式一：使用默认日志路径**

默认会读取 `tests/parity_dual_results.txt`（相对本测试文件所在目录）：

```bash
PARITY_REAL_LOG=1 pytest tests/test_monk_vs_real_parity.py -v --parity-report=mock_data/parity_dual_results.txt
```

**方式二：指定日志路径**

相对路径为相对 `tests/` 目录，也可写绝对路径：

```bash
PARITY_REAL_LOG=tests/parity_dual_results.txt pytest tests/test_monk_vs_real_parity.py -v --parity-report=...
```

### 3. 行为说明

- 本地**只请求 Mock**，不访问真实 API。
- 每次请求会按 `(case_id, api_name, params_summary)` 在日志中查找对应的「服务端原始响应」。
- 若找到则与 Mock 响应做**严格一致**比对；不一致会记入双端失败并报错，便于你改 Mock 做迭代。
- 若某请求在日志中无对应条目，则跳过比对（仅走 Mock）。
- **fixture 一致**：为让回放全部通过，双端结果日志应在「Mock 与真实服务器使用同一份 fixture」时生成（例如两边都用 `final-test.yaml` / 安居客房源）。若日志来自「Mock 最小 fixture vs 真实全量」等不一致场景，回放会因 total/items 数量不同而失败，属预期；此时真实端 404 而 Mock 200 的请求会**跳过比对**并打 warning，不阻塞用例。

这样即可在本地反复跑测、修改 Mock，用同一份日志做对比，直到 Mock 与当时抓到的真实响应一致。
