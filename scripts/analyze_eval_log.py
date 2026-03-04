#!/usr/bin/env python3
"""
评测日志分析脚本：根据比赛规则校验真实环境运行日志，分析可能失分原因。

规则依据：docs/task.md、docs/interface.md
- 计分：单轮/多轮任务按「给出的答案与用例答案匹配的数量」给分；房源查询完成后 response 必须为合法 JSON，含 message 和 houses。
- 约束：response 不能包含自然语言前缀；单用例「任务下发到响应最终答案时间 - 模型调用时间」不得超过 5 秒。
"""

import json
import re
import sys
from pathlib import Path


def load_events(log_path: str) -> list[dict]:
    events = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def parse_response(response_str: str) -> tuple[dict | None, list[str], list[str]]:
    """解析 response 字符串。返回 (parsed_obj, houses_list, errors)。"""
    errors = []
    houses: list[str] = []

    if not response_str or not response_str.strip():
        errors.append("response 为空")
        return None, [], errors

    stripped = response_str.strip()
    if not stripped.startswith("{"):
        errors.append("违反规则：response 不能包含自然语言前缀，必须以 '{' 开头")
        # 尝试从字符串中提取 JSON 块
        match = re.search(r"\{[\s\S]*\"houses\"\s*:\s*\[[\s\S]*?\]\s*[\s\S]*\}", stripped)
        if match:
            try:
                obj = json.loads(match.group(0))
                houses = obj.get("houses") or []
                if isinstance(houses, list):
                    houses = [str(x) for x in houses if x]
                return obj, houses, errors
            except json.JSONDecodeError:
                pass
        return None, [], errors

    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as e:
        errors.append(f"response 不是合法 JSON: {e}")
        return None, [], errors

    if "houses" not in obj:
        errors.append("response 缺少 'houses' 字段（房源查询完成后必须包含）")
    else:
        h = obj["houses"]
        if isinstance(h, list):
            houses = [str(x) for x in h if x]
        else:
            errors.append("'houses' 应为数组")

    if "message" not in obj:
        errors.append("response 缺少 'message' 字段")

    return obj, houses, errors


def main() -> None:
    workspace = Path(__file__).resolve().parent.parent
    default_log = workspace / "restored" / "eval_l00933108_EV-002-0_1772635308097670897.jsonl"
    log_path = sys.argv[1] if len(sys.argv) > 1 else str(default_log)

    if not Path(log_path).exists():
        print(f"文件不存在: {log_path}")
        sys.exit(1)

    events = load_events(log_path)
    print(f"共 {len(events)} 条事件\n")

    # 按轮次提取 USER_REQUEST / USER_RESPONSE
    round_pairs: list[tuple[dict, dict | None]] = []
    last_request = None
    for ev in events:
        if ev.get("event") == "USER_REQUEST":
            last_request = ev.get("details") or {}
        elif ev.get("event") == "USER_RESPONSE":
            round_pairs.append((last_request or {}, ev.get("details") or {}))
            last_request = None

    if not round_pairs:
        print("未发现 USER_REQUEST / USER_RESPONSE 配对。")
        sys.exit(0)

    total_duration_ms = 0
    all_round_issues: list[list[str]] = []

    for i, (req, resp) in enumerate(round_pairs, 1):
        user_msg = (req.get("message") or "")[:80]
        status = resp.get("status", "")
        duration_ms = resp.get("duration_ms") or 0
        response_str = resp.get("response") or ""

        total_duration_ms += duration_ms
        issues: list[str] = []

        print(f"——— 第 {i} 轮 ———")
        print(f"  用户: {user_msg}...")
        print(f"  status: {status}, duration_ms: {duration_ms}")

        if status != "success":
            issues.append(f"status 不为 success，当前为 '{status}'（判题可能按失败处理）")

        obj, houses, parse_errors = parse_response(response_str)
        if parse_errors:
            issues.extend(parse_errors)
            for e in parse_errors:
                print(f"  ⚠ {e}")
        else:
            print(f"  houses 数量: {len(houses)}, IDs: {houses[:10]}{'...' if len(houses) > 10 else ''}")

        if issues:
            all_round_issues.append(issues)
        print()

    # 规则提醒
    print("======== 比赛规则与可能失分点 ========")
    print("1. 计分规则（task.md）：单轮/多轮任务按「给出的答案与用例答案匹配的数量」给分，匹配越多得分越高。")
    print("2. 接口规则（interface.md）：房源查询完成后 response 必须为合法 JSON，包含 message 和 houses；不能包含自然语言前缀。")
    print("3. 时间规则（task.md 说明4）：执行单个用例「从任务下发到响应最终答案时间 - 模型调用时间」不能超过 5 秒，超过则当前用例任务执行失败。")
    print()

    if total_duration_ms > 0:
        print(f"本日志各轮 duration_ms 合计: {total_duration_ms} ms（约 {total_duration_ms/1000:.1f} 秒）。")
        print("说明：上述为每轮请求的完整耗时（含模型调用）。判题使用的「超 5 秒」为：总耗时 - 模型调用时间；若该差值 > 5s 则整用例判失败。")
    print()

    if all_round_issues:
        print("本轮日志中发现的问题（可能导致扣分或判失败）：")
        for i, issues in enumerate(all_round_issues, 1):
            for j in issues:
                print(f"  第{i}轮: {j}")
    else:
        print("本日志中 response 格式均通过校验（合法 JSON、含 message 与 houses、无自然语言前缀）。")
        print("若仍失分，可能原因包括：")
        print("  - 最终答案 houses 与判题标准答案不一致（命中数不足）。多轮用例通常以最后一轮的 houses 作为最终答案参与匹配。")
        print("  - 单用例「总耗时 - 模型调用时间」超过 5 秒，导致该用例被判执行失败。")
        print("  - 可结合平台提供的得分明细或标准答案（若有）进一步对比 houses 列表。")


def check_hit_rate(houses: list[str], expected_path: str) -> None:
    """若存在标准答案文件，计算最后一轮 houses 的命中数与命中率。"""
    path = Path(expected_path)
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8").strip()
    expected = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 支持每行一个 ID 或 JSON 数组
        if line.startswith("["):
            try:
                expected.update(json.loads(line))
            except json.JSONDecodeError:
                continue
        else:
            expected.add(line)
    if not expected:
        return
    actual_set = set(houses)
    hit = actual_set & expected
    n_expected = len(expected)
    n_actual = len(actual_set)
    n_hit = len(hit)
    print(f"\n======== 与标准答案比对（{path.name}）======== ")
    print(f"  标准答案数量: {n_expected}, 本轮返回数量: {n_actual}, 命中: {n_hit}")
    if n_expected:
        print(f"  命中率(按标准答案): {n_hit / n_expected * 100:.1f}%")
    if n_actual:
        print(f"  命中率(按返回数): {n_hit / n_actual * 100:.1f}%")
    missing = expected - actual_set
    if missing:
        print(f"  未命中的标准答案: {sorted(missing)[:20]}{'...' if len(missing) > 20 else ''}")


if __name__ == "__main__":
    log_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "restored" / "eval_l00933108_EV-002-0_1772635308097670897.jsonl")
    main()
    # 可选第二参数：标准答案文件路径，用于计算最后一轮 houses 的命中率
    if len(sys.argv) >= 3:
        expected_path = sys.argv[2]
        events = load_events(log_path)
        round_pairs = []
        last_request = None
        for ev in events:
            if ev.get("event") == "USER_REQUEST":
                last_request = ev.get("details") or {}
            elif ev.get("event") == "USER_RESPONSE":
                round_pairs.append((last_request or {}, ev.get("details") or {}))
                last_request = None
        if round_pairs:
            _, last_resp = round_pairs[-1]
            _, houses, _ = parse_response(last_resp.get("response") or "")
            if houses:
                check_hit_rate(houses, expected_path)
