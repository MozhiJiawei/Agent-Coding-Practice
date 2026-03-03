#!/usr/bin/env python3
"""
检查 test_cases.yaml 中所有 houses_match 是否符合预期：
1. 从 EV-06.yaml 加载房屋信息
2. update_preferences 视为多轮累积：到该轮为止所有 update_preferences 的 contains 合并为约束
3. 校验每个 house_id 的房屋属性是否满足该轮累积约束，并输出报告

用法（在 test-simulator 目录下）：
  python check_house_match.py
  python check_house_match.py --verbose
  python check_house_match.py --case single_haidian_2br
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# 默认 fixture 与用例文件路径（相对于脚本所在目录）
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE = SCRIPT_DIR / "mock_data" / "EV-06.yaml"
DEFAULT_TEST_CASES = SCRIPT_DIR / "test_cases.yaml"
DEFAULT_CONFIG = SCRIPT_DIR / "config.yaml"


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config_fixture_path() -> Path:
    if DEFAULT_CONFIG.exists():
        cfg = load_yaml(DEFAULT_CONFIG)
        fixture = cfg.get("fixture_file", "")
        if fixture:
            p = SCRIPT_DIR / fixture
            if p.exists():
                return p
    return DEFAULT_FIXTURE


def load_houses(fixture_path: Path) -> dict[str, dict]:
    """从 fixture YAML 加载 houses，返回 house_id -> 房屋属性字典。"""
    data = load_yaml(fixture_path)
    houses_list = data.get("houses") or []
    result = {}
    for h in houses_list:
        hid = h.get("house_id")
        if hid:
            result[hid] = h
    return result


def normalize_location(loc: str) -> str:
    """规范化位置字符串便于比较：海淀区/海淀 -> 海淀，望京商圈 -> 望京。"""
    s = str(loc).strip()
    for suffix in ("区", "商圈", "商业区", "片区", "附近"):
        if s.endswith(suffix):
            s = s.removesuffix(suffix)
    return s


def location_matches(expected_list: list, house: dict) -> bool:
    """预期 location 列表（如 ['海淀']）是否与房屋的 district/area 匹配。"""
    if not expected_list:
        return True
    house_district = (house.get("district") or "").strip()
    house_area = (house.get("area") or "").strip()
    house_loc_norm = {normalize_location(house_district), normalize_location(house_area)}
    for exp in expected_list:
        exp_norm = normalize_location(str(exp))
        if exp_norm in house_loc_norm or exp_norm == house_district or exp_norm == house_area:
            return True
    return False


def extract_constraints_from_contains(contains: dict) -> dict:
    """从 tool_call_args.contains 提取约束（用于 update_preferences 的语义）。"""
    c = contains or {}
    constraints = {}
    if "location" in c:
        constraints["location"] = c["location"] if isinstance(c["location"], list) else [c["location"]]
    if "bedrooms" in c:
        v = c["bedrooms"]
        constraints["bedrooms"] = int(v) if isinstance(v, (int, float)) else int(v) if str(v).isdigit() else v
    if "min_price" in c:
        constraints["min_price"] = int(c["min_price"])
    if "max_price" in c:
        constraints["max_price"] = int(c["max_price"])
    if "rental_type" in c:
        constraints["rental_type"] = str(c["rental_type"]).strip()
    if "elevator" in c:
        constraints["elevator"] = bool(c["elevator"])
    if "min_area" in c:
        constraints["min_area"] = int(c["min_area"]) if c["min_area"] is not None else None
    if "decoration" in c:
        constraints["decoration"] = str(c["decoration"]).strip()
    if "near_subway" in c and c["near_subway"]:
        constraints["max_subway_dist"] = 800  # 向后兼容：原 near_subway true 视为 800m
    if "max_subway_dist" in c:
        constraints["max_subway_dist"] = int(c["max_subway_dist"])
    if "subway_line" in c:
        constraints["subway_line"] = str(c["subway_line"]).strip()
    return constraints


def merge_constraints(base: dict, update: dict) -> dict:
    """合并约束：update 覆盖 base 同名字段（多轮累积时后轮覆盖前轮）。"""
    out = dict(base)
    for k, v in update.items():
        out[k] = v
    return out


def get_cumulative_constraints_for_case(tc: dict) -> dict[int, dict]:
    """
    按轮次计算累积偏好：到第 R 轮为止所有 update_preferences 的 contains 合并。
    返回 { round_idx: 累积约束 }，round_idx 为 1-based。
    """
    cumulative: dict[int, dict] = {}
    current: dict = {}
    case_type = tc.get("type", "")
    if case_type == "Single":
        top = tc.get("expect") or {}
        tca = top.get("tool_call_args")
        if tca and str(tca.get("tool")) == "update_preferences":
            current = merge_constraints(current, extract_constraints_from_contains(tca.get("contains") or {}))
        cumulative[1] = dict(current)
        return cumulative
    # Multi: 按 round 顺序处理 round_expects，每轮若有 update_preferences 则合并
    rexps = sorted((tc.get("round_expects") or []), key=lambda x: x.get("round", 0))
    for rexp in rexps:
        r = rexp.get("round", 0)
        if r <= 0:
            continue
        exp = rexp.get("expect") or {}
        tca = exp.get("tool_call_args")
        if tca and str(tca.get("tool")) == "update_preferences":
            current = merge_constraints(current, extract_constraints_from_contains(tca.get("contains") or {}))
        cumulative[r] = dict(current)
    return cumulative


def collect_houses_match_entries(
    test_cases_data: dict, fixture_path: Path, cumulative_by_case: dict[str, dict[int, dict]]
) -> list[tuple]:
    """
    从 test_cases 中收集所有 (case_id, round_idx, message, houses_match_list, 累积约束, fixture_path)。
    round_idx: 1-based；Single 视为 round 1。约束使用到该轮为止的累积偏好。
    """
    cases = test_cases_data.get("test_cases") or []
    entries = []
    for tc in cases:
        case_id = tc.get("id", "")
        messages = tc.get("messages") or []
        cum = cumulative_by_case.get(case_id, {})
        # 顶层 expect（Single 或仅顶层有 houses_match）
        top_expect = tc.get("expect") or {}
        top_houses = top_expect.get("houses_match")
        if top_houses is not None:
            msg = messages[0] if messages else ""
            constraints = cum.get(1, {})
            entries.append((case_id, 1, msg, list(top_houses), constraints, fixture_path))
        # round_expects
        for rexp in tc.get("round_expects") or []:
            round_num = rexp.get("round", 0)
            exp = rexp.get("expect") or {}
            house_list = exp.get("houses_match")
            if house_list is not None:
                msg = messages[round_num - 1] if 1 <= round_num <= len(messages) else ""
                constraints = cum.get(round_num, {})
                case_fixture = tc.get("fixture_file")
                if case_fixture:
                    fp = SCRIPT_DIR / case_fixture
                    if not fp.exists():
                        fp = fixture_path
                else:
                    fp = fixture_path
                entries.append((case_id, round_num, msg, list(house_list), constraints, fp))
    return entries


def check_house_against_constraints(house_id: str, house: dict | None, constraints: dict) -> list[str]:
    """校验单条房屋是否满足约束，返回违反项列表（空表示通过）。"""
    violations = []
    if house is None:
        return [f"房屋 {house_id} 在 fixture 中不存在"]
    # 类型兼容：YAML 可能读成 int/str
    def price(h):
        p = h.get("price")
        return int(p) if p is not None else None
    def bedrooms(h):
        b = h.get("bedrooms")
        if b is None:
            return None
        return int(b) if isinstance(b, (int, float)) else (int(b) if str(b).isdigit() else b)
    def area_sqm(h):
        a = h.get("area_sqm")
        return float(a) if a is not None else None

    if "location" in constraints:
        if not location_matches(constraints["location"], house):
            violations.append(
                f"location: 期望 {constraints['location']}, 实际 district={house.get('district')} area={house.get('area')}"
            )
    if "bedrooms" in constraints:
        exp_b = constraints["bedrooms"]
        if isinstance(exp_b, str) and exp_b.isdigit():
            exp_b = int(exp_b)
        act_b = bedrooms(house)
        if act_b is not None and exp_b is not None and act_b != exp_b:
            violations.append(f"bedrooms: 期望 {exp_b}, 实际 {act_b}")
    if "min_price" in constraints:
        p = price(house)
        if p is not None and p < constraints["min_price"]:
            violations.append(f"min_price: 期望 >={constraints['min_price']}, 实际 price={p}")
    if "max_price" in constraints:
        p = price(house)
        if p is not None and p > constraints["max_price"]:
            violations.append(f"max_price: 期望 <={constraints['max_price']}, 实际 price={p}")
    if "rental_type" in constraints:
        act = (house.get("rental_type") or "").strip()
        exp = constraints["rental_type"]
        if act and exp and act != exp:
            violations.append(f"rental_type: 期望 {exp}, 实际 {act}")
    if "elevator" in constraints:
        act = house.get("elevator")
        if act is not None and bool(act) != constraints["elevator"]:
            violations.append(f"elevator: 期望 {constraints['elevator']}, 实际 {act}")
    if "min_area" in constraints and constraints["min_area"] is not None:
        a = area_sqm(house)
        if a is not None and a < constraints["min_area"]:
            violations.append(f"min_area: 期望 >={constraints['min_area']}, 实际 area_sqm={a}")
    if "decoration" in constraints:
        act = (house.get("decoration") or "").strip()
        exp = constraints["decoration"]
        # 精装/精装修 等价
        if exp and act:
            if "精" in exp and "精" not in act:
                violations.append(f"decoration: 期望 精装, 实际 {act}")
            elif exp != act and not (exp in act or act in exp):
                violations.append(f"decoration: 期望 {exp}, 实际 {act}")
    if "max_subway_dist" in constraints:
        max_d = constraints["max_subway_dist"]
        dist = house.get("subway_distance")
        if dist is None or house.get("subway") is None or house.get("subway") == "":
            violations.append("max_subway_dist: 期望有地铁距离约束, 实际无地铁信息")
        elif not isinstance(dist, (int, float)) or dist > max_d:
            violations.append(f"max_subway_dist: 期望 <={max_d}m, 实际 subway_distance={dist}")
    if "subway_line" in constraints:
        house_line = (house.get("subway") or "").strip()
        exp_line = constraints["subway_line"]
        if exp_line and (exp_line not in house_line):
            violations.append(f"subway_line: 期望包含 {exp_line}, 实际 subway={house_line}")
    return violations


def run_check(
    test_cases_path: Path = DEFAULT_TEST_CASES,
    fixture_path: Path | None = None,
    case_id_filter: str | None = None,
    verbose: bool = False,
) -> tuple[int, int]:
    """执行检查，返回 (通过数, 失败数)。"""
    if fixture_path is None:
        fixture_path = load_config_fixture_path()
    if not fixture_path.exists():
        print(f"ERROR: Fixture 不存在: {fixture_path}", file=sys.stderr)
        return 0, 0
    if not test_cases_path.exists():
        print(f"ERROR: 用例文件不存在: {test_cases_path}", file=sys.stderr)
        return 0, 0

    test_cases_data = load_yaml(test_cases_path)
    # 按用例计算多轮累积约束
    cases_list = test_cases_data.get("test_cases") or []
    cumulative_by_case: dict[str, dict[int, dict]] = {}
    for tc in cases_list:
        cumulative_by_case[tc.get("id", "")] = get_cumulative_constraints_for_case(tc)

    # 按 fixture 文件分组加载 houses（不同 case 可能用不同 fixture）
    houses_by_fixture: dict[Path, dict[str, dict]] = {}
    def get_houses(fp: Path) -> dict[str, dict]:
        if fp not in houses_by_fixture:
            houses_by_fixture[fp] = load_houses(fp)
        return houses_by_fixture[fp]

    entries = collect_houses_match_entries(test_cases_data, fixture_path, cumulative_by_case)
    if case_id_filter:
        entries = [e for e in entries if e[0] == case_id_filter]
        if not entries:
            print(f"未找到 case_id={case_id_filter!r} 的 houses_match 条目。")
            return 0, 0

    passed = 0
    failed = 0
    for case_id, round_idx, message, house_ids, constraints, fp in entries:
        houses = get_houses(fp)
        print(f"\n--- {case_id} (round {round_idx}) ---")
        print(f"  message: {message[:80]}{'...' if len(message) > 80 else ''}")
        print(f"  constraints (cumulative to round {round_idx}): {constraints or '(无)'}")
        print(f"  houses_match: {house_ids}")
        if not constraints:
            print(f"  [SKIP] 到该轮为止无 update_preferences 约束，仅做存在性检查。")
        for hid in house_ids:
            house = houses.get(hid)
            violations = check_house_against_constraints(hid, house, constraints)
            if house is None:
                violations = [f"房屋 {hid} 在 fixture 中不存在"]
            if violations:
                failed += 1
                print(f"  FAIL {hid}: {'; '.join(violations)}")
            else:
                passed += 1
                if verbose:
                    print(f"  OK    {hid}")
    print(f"\n合计: 通过 {passed}, 失败 {failed}")
    return passed, failed


def main():
    # 保证 Windows 下控制台输出 UTF-8
    if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="检查 test_cases 中 houses_match 与 EV-06 房屋信息是否符合同轮 message 语义")
    parser.add_argument("--case", "-c", type=str, default=None, help="仅检查指定 case_id")
    parser.add_argument("--verbose", "-v", action="store_true", help="打印每条房屋的 OK 状态")
    parser.add_argument("--test-cases", type=str, default=None, help="test_cases.yaml 路径")
    parser.add_argument("--fixture", type=str, default=None, help="EV-06.yaml 等 fixture 路径")
    args = parser.parse_args()
    test_cases_path = Path(args.test_cases) if args.test_cases else DEFAULT_TEST_CASES
    fixture_path = Path(args.fixture) if args.fixture else None
    passed, failed = run_check(
        test_cases_path=test_cases_path,
        fixture_path=fixture_path,
        case_id_filter=args.case,
        verbose=args.verbose,
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
