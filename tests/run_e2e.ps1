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

    日志输出写入 <repo_root>/logs/ 目录（自动创建，建议加入 .gitignore）。

.PARAMETER UserId
    可选。竞赛注册员工 ID，通过 USER_ID 环境变量传给主 Agent。默认 "EMP001"。

.PARAMETER SimCase
    可选。运行 test_cases.yaml 中指定 ID 的单个用例。
    示例：-SimCase "ev06_wangjing_to_daxing_rental_flow"

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

.EXAMPLE
    .\tests\run_e2e.ps1
    .\tests\run_e2e.ps1 -UserId "EMP001"
    .\tests\run_e2e.ps1 -UserId "EMP001" -SimCase "ev06_wangjing_to_daxing_rental_flow"
    .\tests\run_e2e.ps1 -UserId "EMP001" -SimTag "ev03"
    .\tests\run_e2e.ps1 -UserId "EMP002" -ReadyTimeoutSec 60
    .\tests\run_e2e.ps1 -UserId "EMP002" -ModelProxyPort 8988 -MockRentalPort 8180 -DashboardPort 8977 -AgentPort 8291
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$UserId = "EMP001",

    [string]$SimCase = "",

    [string]$SimTag = "",

    [int]$ReadyTimeoutSec = 30,

    [int]$ModelProxyPort = 8888,
    [int]$MockRentalPort = 8080,
    [int]$DashboardPort = 8877,
    [int]$AgentPort = 8191
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── 路径解析 ──────────────────────────────────────────────────────────────────
$repoRoot     = Split-Path -Parent $PSScriptRoot
$simulatorDir = Join-Path $repoRoot "test-simulator"
$logsDir      = Join-Path $repoRoot "logs"

# 删除 logs 目录内所有 jsonl 文件（文件被占用时跳过继续执行）
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
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

# ─── 进程 PID 记录表 ───────────────────────────────────────────────────────────
$managedPids = [System.Collections.Generic.List[int]]::new()

# ─── 工具函数 ─────────────────────────────────────────────────────────────────

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
    Write-Host "[e2e] ── Cleanup: stopping $($managedPids.Count) process(es) ──"
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
    Write-Host "[e2e] ════════════════════════════════════════════"
    Write-Host "[e2e]  E2E Test Runner (default: SimAll)"
    Write-Host "[e2e]  USER_ID         : $UserId"
    Write-Host "[e2e]  service timeout : ${ReadyTimeoutSec}s"
    Write-Host "[e2e]  ports           : ModelProxy=$ModelProxyPort MockRental=$MockRentalPort Dashboard=$DashboardPort Agent=$AgentPort"
    Write-Host "[e2e] ════════════════════════════════════════════"

    # 将环境变量注入当前进程（子进程自动继承）
    $env:USER_ID                = $UserId
    $env:RENTAL_API_BASE        = "http://localhost:$MockRentalPort"
    $env:MODEL_PROXY_PORT       = [string]$ModelProxyPort
    $env:SIM_MODEL_PROXY_PORT   = [string]$ModelProxyPort
    $env:SIM_MOCK_RENTAL_PORT   = [string]$MockRentalPort
    $env:SIM_DASHBOARD_PORT     = [string]$DashboardPort
    $env:SIM_AGENT_BASE_URL     = "http://localhost:$AgentPort"

    # ── 1. 启动 test-simulator（Model Proxy + Mock Rental + Dashboard）──────────
    Write-Host "[e2e] Starting test-simulator..."
    $simProc = Start-Process python `
        -ArgumentList "main.py" `
        -WorkingDirectory $simulatorDir `
        -RedirectStandardOutput (Join-Path $logsDir "simulator.log") `
        -RedirectStandardError  (Join-Path $logsDir "simulator_err.log") `
        -NoNewWindow `
        -PassThru
    $managedPids.Add($simProc.Id)
    Write-Host "[e2e]   PID $($simProc.Id) → logs\simulator.log"

    # ── 2. 启动主 Agent ────────────────────────────────────────────────────────
    Write-Host "[e2e] Starting main agent..."
    $agentProc = Start-Process python `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", [string]$AgentPort) `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput (Join-Path $logsDir "agent.log") `
        -RedirectStandardError  (Join-Path $logsDir "agent_err.log") `
        -NoNewWindow `
        -PassThru
    $managedPids.Add($agentProc.Id)
    Write-Host "[e2e]   PID $($agentProc.Id) → logs\agent.log"

    # ── 3. 等待四个服务健康就绪 ──────────────────────────────────────────────────
    $services = [ordered]@{
        "Model Proxy($ModelProxyPort)" = "http://localhost:$ModelProxyPort/docs"
        "Mock Rental($MockRentalPort)" = "http://localhost:$MockRentalPort/docs"
        "Agent($AgentPort)"            = "http://localhost:$AgentPort/docs"
        "Dashboard($DashboardPort)"    = "http://localhost:$DashboardPort/"
    }
    $ready = Wait-ServicesReady -Services $services -TimeoutSec $ReadyTimeoutSec
    if (-not $ready) {
        Write-Host "[e2e] Startup failed. Check logs\ for details."
        $exitCode = 2
    } else {
        # ── 4. 运行 test-simulator 用例（默认 SimAll 全部用例）───────────────────
        Write-Host ""
        if ($SimCase -ne "") {
            Write-Host "[e2e] Running simulator case: $SimCase"
            $simArgs = @("-u", "run_ev_tests.py", "--case", $SimCase)
        } elseif ($SimTag -ne "") {
            Write-Host "[e2e] Running simulator cases by tag: $SimTag"
            $simArgs = @("-u", "run_ev_tests.py", "--tag", $SimTag)
        } else {
            Write-Host "[e2e] Running simulator cases: --all (default)"
            $simArgs = @("-u", "run_ev_tests.py", "--all")
        }
        Write-Host "[e2e] ──────────────────────────────────────────────"
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
