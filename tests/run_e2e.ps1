<#
.SYNOPSIS
    E2E 测试入口脚本 — 委托给 tests/e2e/run_e2e.ps1 执行。

.DESCRIPTION
    从仓库根目录或 tests 目录执行时均可使用：
      .\tests\run_e2e.ps1
      .\tests\run_e2e.ps1 -SimCase "c2"
      .\tests\run_e2e.ps1 -SimCase "c2","c3" -UserId "EMP001"
#>
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

$e2eScript = Join-Path $PSScriptRoot "e2e\run_e2e.ps1"
if (-not (Test-Path $e2eScript)) {
    Write-Error "E2E script not found: $e2eScript"
    exit 1
}
& $e2eScript @PSBoundParameters
exit $LASTEXITCODE
