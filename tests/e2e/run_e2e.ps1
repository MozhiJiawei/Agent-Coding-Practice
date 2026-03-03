<#
.SYNOPSIS
    E2E 测试一键启动脚本 — 自动拉起服务、运行测试、强制清理进程。

.DESCRIPTION
    执行顺序：
      0. 删除 <repo_root>/logs 目录内所有 jsonl 文件
      1. 后台启动 test-simulator (Model Proxy :8888 + Mock Rental :8080 + Dashboard :8877)
      2. 后台启动主 Agent (:8191)，并将 RENTAL_API_BASE 指向 Mock Rental
      3. 轮询健康探测，等待三个服务全部就绪
      4. 运行 test-simulator 用例（test_cases.yaml）：默认 SimAll 全部用例；或通过 -SimCase/-SimTag 指定
      5. 无论测试结果如何，在 finally 块中强制终止所有已启动的进程（含子进程）

    进程输出日志写入 tests/e2e/logs/；HTML/JSON/MD 报告写入 tests/e2e/reports/。
    主 Agent 的 jsonl 会话日志仍写入 <repo_root>/logs/（不修改）。

.PARAMETER UserId
    可选。竞赛注册员工 ID，通过 USER_ID 环境变量传给主 Agent。默认 "EMP001"。

.PARAMETER SimCase
    可选。运行 test_cases.yaml 中指定 ID 的用例，支持单个或列表。
    示例：-SimCase "ev06_wangjing_to_daxing_rental_flow"
    示例：-SimCase "ev01","ev02","ev03"

.PARAMETER SimTag
    可选。运行 test_cases.yaml 中匹配 tag 的所有用例。
    示例：-SimTag "ev03"

.PARAMETER ReadyTimeoutSec
    可选。等待所有服务健康就绪的最大秒数，默认 30。

.PARAMETER ModelProxyPort
    可选。Model Proxy 监听端口，默认 8888。支持多实例并行时避免端口冲突。

.PARAMETER MockRentalPort
    可选。Mock Rental 监听端口，默认 8080。

.PARAMETER DashboardPort
    可选。Dashboard 监听端口，默认 8877。

.PARAMETER AgentPort
    可选。主 Agent 监听端口，默认 8191。

.PARAMETER AutoFindPorts
    可选。默认开启：自动寻找未占用端口，避免与已有服务冲突。传 -AutoFindPorts $false 可禁用。

.EXAMPLE
    .\tests\e2e\run_e2e.ps1
    .\tests\e2e\run_e2e.ps1 -UserId "EMP001"
    .\tests\e2e\run_e2e.ps1 -UserId "EMP001" -SimCase "ev06_wangjing_to_daxing_rental_flow"
    .\tests\e2e\run_e2e.ps1 -SimCase "ev01","ev02","ev03"
    .\tests\e2e\run_e2e.ps1 -UserId "EMP001" -SimTag "ev03"
    .\tests\e2e\run_e2e.ps1 -UserId "EMP002" -ReadyTimeoutSec 60
    .\tests\e2e\run_e2e.ps1 -UserId "EMP002" -ModelProxyPort 8988 -MockRentalPort 8180 -DashboardPort 8977 -AgentPort 8291
    .\tests\e2e\run_e2e.ps1 -AutoFindPorts $false
    .\tests\e2e\run_e2e.ps1 -SimCase "ev06_wangjing_to_daxing_rental_flow"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$UserId = "EMP001",

    [string[]]$SimCase = @(),

    [string]$SimTag = "",

    [int]$ReadyTimeoutSec = 30,

    [int]$ModelProxyPort = 8888,
    [int]$MockRentalPort = 8080,
    [int]$DashboardPort = 8877,
    [int]$AgentPort = 8191,

    [bool]$AutoFindPorts = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── 路径解析（脚本位于 tests/e2e/）────────────────────────────────────────────
$repoRoot     = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$e2eDir       = $PSScriptRoot
$simulatorDir = Join-Path $repoRoot "test-simulator"
$logsDir      = Join-Path $repoRoot "logs"           # 主 Agent jsonl 目录（不修改）
$e2eLogsDir   = Join-Path $e2eDir "logs"             # simulator/agent 进程输出
$e2eReportsDir = Join-Path $e2eDir "reports"         # HTML/JSON/MD 报告

# 删除 logs 目录内所有 jsonl 文件（主 Agent 写入位置，文件被占用时跳过继续执行）
if (Test-Path $logsDir) {
    try {
        $jsonlFiles = Get-ChildItem -Path $logsDir -Filter "*.jsonl" -File -ErrorAction Stop
        foreach ($f in $jsonlFiles) {
            Remove-Item -Path $f.FullName -Force -ErrorAction Stop
        }
        if ($jsonlFiles.Count -gt 0) {
            Write-Host "[e2e] Removed $($jsonlFiles.Count) jsonl file(s) from logs"
        }
    } catch {
        Write-Host "[e2e] WARN: Could not remove jsonl files in logs (files in use?), continuing..."
    }
}
New-Item -ItemType Directory -Path $e2eLogsDir -Force | Out-Null
New-Item -ItemType Directory -Path $e2eReportsDir -Force | Out-Null

# ─── 进程 PID 记录表 ───────────────────────────────────────────────────────────
$managedPids = [System.Collections.Generic.List[int]]::new()

# ─── 工具函数 ─────────────────────────────────────────────────────────────────

function Test-PortInUse {
    param([int]$Port)
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        $listener.Stop()
        return $false  # 绑定成功，端口可用
    } catch {
        return $true   # 绑定失败，端口被占用
    }
}

function Get-FreePort {
    param([int]$PreferredPort, [int[]]$ExcludePorts = @())
    $port = $PreferredPort
    $attempts = 0
    $maxAttempts = 100
    while ($attempts -lt $maxAttempts) {
        if ($port -notin $ExcludePorts -and -not (Test-PortInUse -Port $port)) {
            return $port
        }
        $port += 1
        $attempts++
    }
    throw "Cannot find free port after $maxAttempts attempts"
}

function Get-FourFreePorts {
    param(
        [int]$BaseModelProxy = 8888,
        [int]$BaseMockRental = 8080,
        [int]$BaseDashboard = 8877,
        [int]$BaseAgent = 8191
    )
    $used = @()
    $p1 = Get-FreePort -PreferredPort $BaseModelProxy -ExcludePorts $used
    $used += $p1
    $p2 = Get-FreePort -PreferredPort $BaseMockRental -ExcludePorts $used
    $used += $p2
    $p3 = Get-FreePort -PreferredPort $BaseDashboard -ExcludePorts $used
    $used += $p3
    $p4 = Get-FreePort -PreferredPort $BaseAgent -ExcludePorts $used
    return @{ ModelProxy = $p1; MockRental = $p2; Dashboard = $p3; Agent = $p4 }
}

function Test-ServiceReady {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return ($resp.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Wait-ServicesReady {
    param(
        [hashtable]$Services,
        [int]$TimeoutSec
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $pending  = @()
    Write-Host "[e2e] Waiting for services to be ready (timeout: ${TimeoutSec}s)..."

    while ((Get-Date) -lt $deadline) {
        $pending = @()
        foreach ($name in $Services.Keys) {
            if (-not (Test-ServiceReady -Url $Services[$name])) {
                $pending += $name
            }
        }
        if ($pending.Count -eq 0) {
            Write-Host "[e2e] All services ready."
            return $true
        }
        Write-Host "[e2e]   Pending: $($pending -join ', ')..."
        Start-Sleep -Seconds 2
    }
    Write-Host "[e2e] ERROR: Timed out waiting for: $($pending -join ', ')"
    return $false
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    try {
        # 先递归终止所有子进程
        $children = Get-CimInstance Win32_Process `
            -Filter "ParentProcessId=$ProcessId" `
            -ErrorAction SilentlyContinue
        foreach ($child in $children) {
            Stop-ProcessTree -ProcessId $child.ProcessId
        }
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    } catch {
        # 进程可能已退出，静默忽略
    }
}

function Invoke-Cleanup {
    if ($managedPids.Count -eq 0) { return }
    Write-Host ""
    Write-Host "[e2e] -- Cleanup: stopping $($managedPids.Count) process(es) --"
    foreach ($procId in $managedPids) {
        Write-Host "[e2e]   Stopping PID $procId (and children)..."
        Stop-ProcessTree -ProcessId $procId
    }
    $managedPids.Clear()
    Write-Host "[e2e] Cleanup complete."
}

# ─── 主逻辑 ───────────────────────────────────────────────────────────────────
$exitCode = 1

try {
    # ── 可选：自动寻找未占用端口 ────────────────────────────────────────────────
    if ($AutoFindPorts) {
        Write-Host "[e2e] AutoFindPorts: searching for free ports..."
        $ports = Get-FourFreePorts -BaseModelProxy $ModelProxyPort -BaseMockRental $MockRentalPort `
            -BaseDashboard $DashboardPort -BaseAgent $AgentPort
        $ModelProxyPort = $ports.ModelProxy
        $MockRentalPort = $ports.MockRental
        $DashboardPort = $ports.Dashboard
        $AgentPort = $ports.Agent
        Write-Host "[e2e] Using ports: ModelProxy=$ModelProxyPort MockRental=$MockRentalPort Dashboard=$DashboardPort Agent=$AgentPort"
    }

    Write-Host "[e2e] ==============================================="
    Write-Host "[e2e]  E2E Test Runner (default: SimAll)"
    Write-Host "[e2e]  USER_ID         : $UserId"
    Write-Host "[e2e]  service timeout : ${ReadyTimeoutSec}s"
    Write-Host "[e2e]  ports           : ModelProxy=$ModelProxyPort MockRental=$MockRentalPort Dashboard=$DashboardPort Agent=$AgentPort"
    Write-Host "[e2e] ==============================================="

    # 将环境变量注入当前进程（子进程自动继承）
    $env:USER_ID                = $UserId
    $env:RENTAL_API_BASE        = "http://localhost:$MockRentalPort"
    $env:MODEL_PROXY_PORT       = [string]$ModelProxyPort
    $env:SIM_MODEL_PROXY_PORT   = [string]$ModelProxyPort
    $env:SIM_MOCK_RENTAL_PORT   = [string]$MockRentalPort
    $env:SIM_DASHBOARD_PORT     = [string]$DashboardPort
    $env:SIM_AGENT_BASE_URL     = "http://localhost:$AgentPort"
    $env:SIM_REPORT_DIR         = $e2eReportsDir   # HTML/JSON/MD 报告输出到 tests/e2e/reports

    # ── 1. 启动 test-simulator（Model Proxy + Mock Rental + Dashboard）──────────
    Write-Host "[e2e] Starting test-simulator..."
    $simProc = Start-Process python `
        -ArgumentList "main.py" `
        -WorkingDirectory $simulatorDir `
        -RedirectStandardOutput (Join-Path $e2eLogsDir "simulator.log") `
        -RedirectStandardError  (Join-Path $e2eLogsDir "simulator_err.log") `
        -NoNewWindow `
        -PassThru
    $managedPids.Add($simProc.Id)
    Write-Host "[e2e]   PID $($simProc.Id) -> tests\e2e\logs\simulator.log"

    # ── 2. 启动主 Agent ────────────────────────────────────────────────────────
    Write-Host "[e2e] Starting main agent..."
    $agentProc = Start-Process python `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", [string]$AgentPort) `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput (Join-Path $e2eLogsDir "agent.log") `
        -RedirectStandardError  (Join-Path $e2eLogsDir "agent_err.log") `
        -NoNewWindow `
        -PassThru
    $managedPids.Add($agentProc.Id)
    Write-Host "[e2e]   PID $($agentProc.Id) -> tests\e2e\logs\agent.log"

    # ── 3. 等待四个服务健康就绪 ──────────────────────────────────────────────────
    $services = [ordered]@{
        "Model Proxy($ModelProxyPort)" = "http://localhost:$ModelProxyPort/docs"
        "Mock Rental($MockRentalPort)" = "http://localhost:$MockRentalPort/docs"
        "Agent($AgentPort)"            = "http://localhost:$AgentPort/docs"
        "Dashboard($DashboardPort)"    = "http://localhost:$DashboardPort/"
    }
    $ready = Wait-ServicesReady -Services $services -TimeoutSec $ReadyTimeoutSec
    if (-not $ready) {
        Write-Host "[e2e] Startup failed. Check tests\e2e\logs\ for details."
        $exitCode = 2
    } else {
        # ── 3b. Dashboard 就绪后自动打开浏览器 ─────────────────────────────────────
        $dashboardUrl = "http://localhost:$DashboardPort/"
        Write-Host "[e2e] Opening Dashboard: $dashboardUrl"
        Start-Process $dashboardUrl

        # ── 4. 运行 test-simulator 用例（默认 SimAll 全部用例）───────────────────
        Write-Host ""
        if ($SimCase -and $SimCase.Count -gt 0) {
            Write-Host "[e2e] Running simulator case(s): $($SimCase -join ', ')"
            $simArgs = @("-u", "run_ev_tests.py") + ($SimCase | ForEach-Object { "--case"; $_ })
        } elseif ($SimTag -ne "") {
            Write-Host "[e2e] Running simulator cases by tag: $SimTag"
            $simArgs = @("-u", "run_ev_tests.py", "--tag", $SimTag)
        } else {
            Write-Host "[e2e] Running simulator cases: --all (default)"
            $simArgs = @("-u", "run_ev_tests.py", "--all")
        }
        Write-Host "[e2e] ----------------------------------------------"
        Push-Location $simulatorDir
        try {
            & python @simArgs
            $exitCode = if ($LASTEXITCODE -eq 0) { 0 } else { $LASTEXITCODE }
        } finally {
            Pop-Location
        }
    }

} finally {
    Invoke-Cleanup
}

Write-Host ""
Write-Host "[e2e] Done. Exit code: $exitCode"
exit $exitCode
