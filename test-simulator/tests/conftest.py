"""pytest configuration — adds test-simulator root to sys.path; parity report option."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def pytest_addoption(parser):
    parser.addoption(
        "--parity-report",
        action="store",
        default=None,
        help="Path to write Monk vs real server parity test failure report (e.g. mock_data/monk_vs_real_test_results.txt)",
    )


def pytest_sessionfinish(session, exitstatus):
    report_path = session.config.getoption("--parity-report", default=None)
    if not report_path:
        return
    for _name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        failures = getattr(mod, "PARITY_FAILURES", None)
        if not isinstance(failures, list):
            continue
        meta = getattr(mod, "PARITY_REPORT_META", None) or {}
        runs = getattr(mod, "PARITY_RUNS", None)
        total = len(runs) if isinstance(runs, list) else getattr(mod, "PARITY_TOTAL", 0)
        out_path = report_path
        if not os.path.isabs(out_path):
            base = os.path.join(os.path.dirname(__file__), "..")
            out_path = os.path.abspath(os.path.join(base, report_path))
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        failed_count = len(failures)
        dual_failures = getattr(mod, "PARITY_DUAL_FAILURES", None)
        if not isinstance(dual_failures, list):
            dual_failures = []
        dual_count = len(dual_failures)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("============================================================\n")
            f.write("Monk vs Real Server 一致性测试结果\n")
            f.write("============================================================\n")
            f.write(f"运行时间: {meta.get('timestamp', datetime.now().isoformat())}\n")
            f.write(f"RENTAL_API_BASE: {meta.get('base_url', 'N/A')}\n")
            f.write(f"数据源: {meta.get('fixture_source', 'N/A')}\n")
            f.write(f"双端模式 (Mock vs Real 同请求比对): {meta.get('parity_dual', False)}\n")
            f.write("------------------------------------------------------------\n")
            f.write(f"总用例数: {total}\n")
            f.write(f"通过: {total - failed_count}\n")
            f.write(f"失败: {failed_count}\n")
            if dual_count:
                f.write(f"双端响应不一致数: {dual_count}\n")
            f.write("============================================================\n\n")
            if failures:
                f.write("失败列表（用例ID / 函数名 / 参数摘要 → 原因）:\n\n")
                for item in failures:
                    f.write(
                        f"[FAIL] {item.get('case_id', '')}  {item.get('api_name', '')}  "
                        f"{item.get('params_summary', '')}  →  {item.get('reason', '')}\n"
                    )
            if dual_failures:
                f.write("\n双端响应不一致（Mock vs Real 须完全一致）:\n\n")
                for item in dual_failures:
                    f.write(
                        f"[DUAL] {item.get('case_id', '')}  {item.get('api_name', '')}  "
                        f"{item.get('params_summary', '')}  →  {item.get('reason', '')}\n"
                    )
                    if item.get("mock_status") is not None or item.get("real_status") is not None:
                        f.write(f"       mock_status={item.get('mock_status')} real_status={item.get('real_status')}\n")
        break
