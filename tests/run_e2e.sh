#!/usr/bin/env bash
# =============================================================================
# run_e2e.sh — E2E 测试一键启动脚本（Linux / macOS）
#
# 执行顺序：
#   1. 后台启动 test-simulator (Model Proxy :8888 + Mock Rental :8080)
#   2. 后台启动主 Agent (:8191)，并将 RENTAL_API_BASE 指向 Mock Rental
#   3. 轮询健康探测，等待三个服务全部就绪
#   4. 执行 pytest e2e 测试套件
#   5. EXIT / INT / TERM 信号均触发 cleanup，强制终止所有已启动进程
#
# 日志输出写入 <repo_root>/logs/ 目录（自动创建，建议加入 .gitignore）。
#
# 用法：
#   bash tests/run_e2e.sh -u EMP001
#   bash tests/run_e2e.sh -u EMP001 -p "tests/e2e/ -v -m smoke"
#   bash tests/run_e2e.sh -u EMP001 -t 60
#   bash tests/run_e2e.sh -u EMP002 -m 8988 -r 8180 -d 8977 -a 8291
#
# 参数：
#   -u USER_ID      必填。竞赛注册员工 ID，作为 USER_ID 环境变量传给主 Agent。
#   -p PYTEST_ARGS  可选。传给 pytest 的参数字符串（默认: "tests/e2e/ -v"）。
#   -t TIMEOUT_SEC  可选。等待服务就绪的最大秒数（默认: 30）。
#   -m MODEL_PROXY  可选。Model Proxy 端口（默认: 8888）。
#   -r MOCK_RENTAL  可选。Mock Rental 端口（默认: 8080）。
#   -d DASHBOARD    可选。Dashboard 端口（默认: 8877）。
#   -a AGENT        可选。主 Agent 端口（默认: 8191）。
#   -h              显示帮助信息。
# =============================================================================

set -uo pipefail

# ─── 帮助信息 ─────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $(basename "$0") -u USER_ID [-p PYTEST_ARGS] [-t TIMEOUT_SEC] [-m MODEL_PROXY] [-r MOCK_RENTAL] [-d DASHBOARD] [-a AGENT]"
    echo ""
    echo "  -u USER_ID      Required. Employee ID for the agent (USER_ID env var)."
    echo "  -p PYTEST_ARGS  Optional. pytest arguments. Default: 'tests/e2e/ -v'"
    echo "  -t TIMEOUT_SEC  Optional. Service ready timeout in seconds. Default: 30"
    echo "  -m MODEL_PROXY  Optional. Model Proxy port. Default: 8888"
    echo "  -r MOCK_RENTAL  Optional. Mock Rental port. Default: 8080"
    echo "  -d DASHBOARD    Optional. Dashboard port. Default: 8877"
    echo "  -a AGENT        Optional. Agent port. Default: 8191"
    echo "  -h              Show this help message."
    exit 1
}

# ─── 参数解析 ─────────────────────────────────────────────────────────────────
USER_ID=""
PYTEST_ARGS="tests/e2e/ -v"
READY_TIMEOUT=30
MODEL_PROXY_PORT=8888
MOCK_RENTAL_PORT=8080
DASHBOARD_PORT=8877
AGENT_PORT=8191

while getopts "u:p:t:m:r:d:a:h" opt; do
    case "$opt" in
        u) USER_ID="$OPTARG" ;;
        p) PYTEST_ARGS="$OPTARG" ;;
        t) READY_TIMEOUT="$OPTARG" ;;
        m) MODEL_PROXY_PORT="$OPTARG" ;;
        r) MOCK_RENTAL_PORT="$OPTARG" ;;
        d) DASHBOARD_PORT="$OPTARG" ;;
        a) AGENT_PORT="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [[ -z "$USER_ID" ]]; then
    echo "[e2e] ERROR: -u USER_ID is required."
    echo ""
    usage
fi

# ─── 路径解析 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SIMULATOR_DIR="$REPO_ROOT/test-simulator"
LOGS_DIR="$REPO_ROOT/logs"
mkdir -p "$LOGS_DIR"

# ─── 进程 PID 记录 ────────────────────────────────────────────────────────────
MANAGED_PIDS=()

# ─── 清理函数（注册到 EXIT / INT / TERM）─────────────────────────────────────
cleanup() {
    local count=${#MANAGED_PIDS[@]}
    if [[ $count -eq 0 ]]; then return; fi

    echo ""
    echo "[e2e] ── Cleanup: stopping ${count} process(es) ──"
    for pid in "${MANAGED_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "[e2e]   Stopping PID $pid (and children)..."
            # 先尝试终止所有子进程
            pkill -P "$pid" 2>/dev/null || true
            kill -TERM "$pid" 2>/dev/null || true
            # 给进程 1 秒优雅退出时间，之后强制 KILL
            sleep 1
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
    echo "[e2e] Cleanup complete."
}

trap cleanup EXIT INT TERM

# ─── 服务健康探测 ─────────────────────────────────────────────────────────────
service_ready() {
    local url="$1"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$url" 2>/dev/null || echo "000")
    [[ "$http_code" -gt 0 && "$http_code" -lt 500 ]] 2>/dev/null
}

wait_services_ready() {
    local deadline=$(( SECONDS + READY_TIMEOUT ))
    local pending=()
    echo "[e2e] Waiting for services to be ready (timeout: ${READY_TIMEOUT}s)..."

    while [[ $SECONDS -lt $deadline ]]; do
        pending=()
        service_ready "http://localhost:${MODEL_PROXY_PORT}/docs" || pending+=("Model Proxy(${MODEL_PROXY_PORT})")
        service_ready "http://localhost:${MOCK_RENTAL_PORT}/docs" || pending+=("Mock Rental(${MOCK_RENTAL_PORT})")
        service_ready "http://localhost:${AGENT_PORT}/docs" || pending+=("Agent(${AGENT_PORT})")
        service_ready "http://localhost:${DASHBOARD_PORT}/" || pending+=("Dashboard(${DASHBOARD_PORT})")

        if [[ ${#pending[@]} -eq 0 ]]; then
            echo "[e2e] All services ready."
            return 0
        fi
        echo "[e2e]   Pending: ${pending[*]}..."
        sleep 2
    done

    echo "[e2e] ERROR: Timed out waiting for: ${pending[*]:-unknown}"
    return 1
}

# ─── 主逻辑 ───────────────────────────────────────────────────────────────────
echo "[e2e] ════════════════════════════════════════════"
echo "[e2e]  E2E Test Runner"
echo "[e2e]  USER_ID         : $USER_ID"
echo "[e2e]  pytest args     : $PYTEST_ARGS"
echo "[e2e]  service timeout : ${READY_TIMEOUT}s"
echo "[e2e]  ports           : ModelProxy=$MODEL_PROXY_PORT MockRental=$MOCK_RENTAL_PORT Dashboard=$DASHBOARD_PORT Agent=$AGENT_PORT"
echo "[e2e] ════════════════════════════════════════════"

# 将环境变量导出给所有子进程
export USER_ID
export RENTAL_API_BASE="http://localhost:${MOCK_RENTAL_PORT}"
export MODEL_PROXY_PORT
export SIM_MODEL_PROXY_PORT="$MODEL_PROXY_PORT"
export SIM_MOCK_RENTAL_PORT="$MOCK_RENTAL_PORT"
export SIM_DASHBOARD_PORT="$DASHBOARD_PORT"
export SIM_AGENT_BASE_URL="http://localhost:${AGENT_PORT}"

# ── 1. 启动 test-simulator（Model Proxy + Mock Rental + Dashboard）────────────
echo "[e2e] Starting test-simulator..."
(
    cd "$SIMULATOR_DIR"
    exec python main.py
) > "$LOGS_DIR/simulator.log" 2> "$LOGS_DIR/simulator_err.log" &
SIM_PID=$!
MANAGED_PIDS+=("$SIM_PID")
echo "[e2e]   PID $SIM_PID → logs/simulator.log"

# ── 2. 启动主 Agent ──────────────────────────────────────────────────────────
echo "[e2e] Starting main agent..."
(
    cd "$REPO_ROOT"
    exec python -m uvicorn main:app --host 0.0.0.0 --port "$AGENT_PORT"
) > "$LOGS_DIR/agent.log" 2> "$LOGS_DIR/agent_err.log" &
AGENT_PID=$!
MANAGED_PIDS+=("$AGENT_PID")
echo "[e2e]   PID $AGENT_PID → logs/agent.log"

# ── 3. 等待三个服务健康就绪 ────────────────────────────────────────────────────
if ! wait_services_ready; then
    echo "[e2e] Startup failed. Check logs/ for details."
    exit 2
fi

# ── 4. 运行 pytest ─────────────────────────────────────────────────────────────
export PYTEST_AGENT_URL="http://localhost:${AGENT_PORT}"
export PYTEST_MODEL_PROXY_URL="http://localhost:${MODEL_PROXY_PORT}"
export PYTEST_MOCK_RENTAL_URL="http://localhost:${MOCK_RENTAL_PORT}"
echo ""
echo "[e2e] Running: python -m pytest $PYTEST_ARGS"
echo "[e2e] ──────────────────────────────────────────────"

# 保留引号感知的参数拆分（bash word splitting 在此处是预期行为）
# shellcheck disable=SC2086
python -m pytest $PYTEST_ARGS
PYTEST_EXIT=$?

echo ""
echo "[e2e] Done. Exit code: $PYTEST_EXIT"
exit $PYTEST_EXIT
