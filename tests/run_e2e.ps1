<#
.SYNOPSIS
    E2E 测试一键启动脚本 — 自动拉起服务、运行测试、强制清理进程。

.DESCRIPTION
    执行顺序：
      1. 后台启动 test-simulator (Model Proxy :8888 + Mock Rental :8080)
      2. 后台启动主 Agent (:8191)，并将 RENTAL_API_BASE 指向 Mock Rental
      3. 轮询健康探测，等待三个服务全部就绪
      4a. 若指定 -SimCase 或 -SimAll：运行 test-simulator 用例（test_cases.yaml）
      4b. 否则：执行 pytest e2e 测试套件
      5. 无论测试结果如何，在 finally 块中强制终止所有已启动的进程（含子进程）

    日志输出写入 <repo_root>/logs/ 目录（自动创建，建议加入 .gitignore）。

.PARAMETER UserId
    必填。竞赛注册员工 ID，通过 USER_ID 环境变量传给主 Agent。

.PARAMETER PytestArgs
    可选。传给 pytest 的参数字符串，默认 "tests/e2e/ -v"。
    示例：-PytestArgs "tests/e2e/ -v -m smoke"

.PARAMETER SimCase
    可选。运行 test_cases.yaml 中指定 ID 的单个用例，跳过 pytest。
    示例：-SimCase "ev06_wangjing_to_daxing_rental_flow"

.PARAMETER SimTag
    可选。运行 test_cases.yaml 中匹配 tag 的所有用例，跳过 pytest。
    示例：-SimTag "ev03"

.PARAMETER SimAll
    可选。运行 test_cases.yaml 中全部用例，跳过 pytest。

.PARAMETER ReadyTimeoutSec
    可选。等待所有服务健康就绪的最大秒数，默认 30。

.EXAMPLE
    .\tests\run_e2e.ps1 -UserId "EMP001"
    .\tests\run_e2e.ps1 -UserId "EMP001" -PytestArgs "tests/e2e/ -v -m smoke"
    .\tests\run_e2e.ps1 -UserId "EMP001" -SimCase "ev06_wangjing_to_daxing_rental_flow"
    .\tests\run_e2e.ps1 -UserId "EMP001" -SimAll
    .\tests\run_e2e.ps1 -UserId "EMP001" -ReadyTimeoutSec 60
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$UserId,

    [string]$PytestArgs = "tests/e2e/ -v",

    [string]$SimCase = "",

    [string]$SimTag = "",

    [switch]$SimAll,

    [int]$ReadyTimeoutSec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── 路径解析 ──────────────────────────────────────────────────────────────────
$repoRoot     = Split-Path -Parent $PSScriptRoot
$simulatorDir = Join-Path $repoRoot "test-simulator"
$logsDir      = Join-Path $repoRoot "logs"
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
    Write-Host "[e2e]  E2E Test Runner"
    Write-Host "[e2e]  USER_ID         : $UserId"
    Write-Host "[e2e]  pytest args     : $PytestArgs"
    Write-Host "[e2e]  service timeout : ${ReadyTimeoutSec}s"
    Write-Host "[e2e] ════════════════════════════════════════════"

    # 将环境变量注入当前进程（子进程自动继承）
    $env:USER_ID         = $UserId
    $env:RENTAL_API_BASE = "http://localhost:8080"

    # ── 1. 启动 test-simulator（Model Proxy :8888 + Mock Rental :8080）──────────
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

    # ── 2. 启动主 Agent（:8191）────────────────────────────────────────────────
    Write-Host "[e2e] Starting main agent..."
    $agentProc = Start-Process python `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8191") `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput (Join-Path $logsDir "agent.log") `
        -RedirectStandardError  (Join-Path $logsDir "agent_err.log") `
        -NoNewWindow `
        -PassThru
    $managedPids.Add($agentProc.Id)
    Write-Host "[e2e]   PID $($agentProc.Id) → logs\agent.log"

    # ── 3. 等待三个服务健康就绪 ──────────────────────────────────────────────────
    $services = [ordered]@{
        "Model Proxy(8888)" = "http://localhost:8888/docs"
        "Mock Rental(8080)" = "http://localhost:8080/docs"
        "Agent(8191)"       = "http://localhost:8191/docs"
    }
    $ready = Wait-ServicesReady -Services $services -TimeoutSec $ReadyTimeoutSec
    if (-not $ready) {
        Write-Host "[e2e] Startup failed. Check logs\ for details."
        $exitCode = 2
    } elseif ($SimCase -ne "" -or $SimTag -ne "" -or $SimAll) {
        # ── 4a. 运行 test-simulator 用例（test_cases.yaml，复用已启动服务）──────
        Write-Host ""
        if ($SimAll) {
            Write-Host "[e2e] Running simulator cases: --all"
            $simArgs = @("-u", "run_ev_tests.py", "--all")
        } elseif ($SimCase -ne "") {
            Write-Host "[e2e] Running simulator case: $SimCase"
            $simArgs = @("-u", "run_ev_tests.py", "--case", $SimCase)
        } else {
            Write-Host "[e2e] Running simulator cases by tag: $SimTag"
            $simArgs = @("-u", "run_ev_tests.py", "--tag", $SimTag)
        }
        Write-Host "[e2e] ──────────────────────────────────────────────"
        Push-Location $simulatorDir
        try {
            & python @simArgs
            $exitCode = if ($LASTEXITCODE -eq 0) { 0 } else { $LASTEXITCODE }
        } finally {
            Pop-Location
        }
    } else {
        # ── 4b. 运行 pytest ─────────────────────────────────────────────────────
        Write-Host ""
        Write-Host "[e2e] Running: python -m pytest $PytestArgs"
        Write-Host "[e2e] ──────────────────────────────────────────────"
        $pytestArgArray = $PytestArgs -split '\s+' | Where-Object { $_ -ne '' }
        & python -m pytest @pytestArgArray
        $exitCode = $LASTEXITCODE
    }

} finally {
    Invoke-Cleanup
}

Write-Host ""
Write-Host "[e2e] Done. Exit code: $exitCode"
exit $exitCode
