#!/usr/bin/env python3
"""从 JSONL 评估日志提取 mock_data，生成 test-simulator 可用的 YAML fixture。

读取日志中的 DEBUG_ALL_HOUSES 与 DEBUG_ALL_LANDMARKS 事件，将其 items 全量转换为
fixture 格式输出（含 landmarks 与 houses）。

支持三平台（链家、安居客、58同城）：分别统计各平台数量、输出差距，去重后仅保留一个平台
（默认保留安居客）写入 YAML。

用法（在 test-simulator/ 目录下运行）：
  python extract_mock_data.py <jsonl_path> [output_yaml]

示例：
  python extract_mock_data.py ../logs/eval_l00933108_EV-06_1772426116496476236.jsonl mock_data/EV-06.yaml
  python extract_mock_data.py ../房屋数据/传输_还原/xxx.jsonl mock_data/final-test_new.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# 三平台名称（顺序：去重时优先保留链家）
PLATFORMS = ("链家", "安居客", "58同城")
# 用于跨平台去重的房源标识 key（同一套房）
DEDUP_KEY_FIELDS = ("community", "address", "area_sqm", "price", "bedrooms")

# ── 字段定义 ──────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "house_id", "community", "district", "area", "price", "status",
    "longitude", "latitude", "bedrooms", "rental_type", "decoration",
    "orientation", "elevator",
}

LANDMARK_REQUIRED_FIELDS = {"id", "name", "category", "district", "longitude", "latitude"}

# 房源输出字段顺序（可读性优先）
_ORDERED_FIELDS = [
    "house_id", "community", "district", "area", "address",
    "bedrooms", "livingrooms", "bathrooms", "area_sqm",
    "floor", "total_floors", "orientation", "decoration",
    "price", "rental_type", "property_type", "utilities_type",
    "elevator", "subway", "subway_station", "subway_distance",
    "commute_to_xierqi", "available_from", "tags", "hidden_noise_level",
    "status", "longitude", "latitude",
]

# ── 工具函数 ───────────────────────────────────────────────────────────────────


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def house_to_fixture(h: dict) -> dict:
    """将原始房源 dict 转换为 fixture 所需格式（含必填字段校验）。"""
    missing = REQUIRED_FIELDS - set(h.keys())
    if missing:
        raise ValueError(f"房源 {h.get('house_id', '?')} 缺少必填字段: {missing}")

    entry: dict = {}
    for field in _ORDERED_FIELDS:
        if field not in h:
            continue
        v = h[field]
        if field == "price":
            v = _safe_int(v)
        elif field in ("longitude", "latitude", "area_sqm"):
            v = _safe_float(v)
        elif field in (
            "bedrooms", "livingrooms", "bathrooms",
            "total_floors", "subway_distance", "commute_to_xierqi",
        ):
            v = _safe_int(v) if v is not None else v
        entry[field] = v
    return entry


def landmark_to_fixture(lm: dict) -> dict:
    """将原始地标 dict 转换为 fixture 所需格式（含必填字段校验）。保留 details 等完整字段。"""
    missing = LANDMARK_REQUIRED_FIELDS - set(lm.keys())
    if missing:
        raise ValueError(f"地标 {lm.get('id', '?')} 缺少必填字段: {missing}")

    entry: dict = {}
    for k, v in lm.items():
        if k in ("longitude", "latitude"):
            entry[k] = _safe_float(v)
        else:
            entry[k] = v
    return entry


def _house_dedup_key(h: dict) -> tuple:
    """生成用于跨平台去重的 key（同一套房：小区+地址+面积+租金+室数）。"""
    return tuple(
        h.get(f) for f in DEDUP_KEY_FIELDS
    )


def _print_platform_gap(platform_houses: dict[str, list], keep_platform: str) -> None:
    """输出三平台房源数量差距及去重统计。"""
    print("\n--- 三平台房源信息统计 ---")
    for name in PLATFORMS:
        n = len(platform_houses.get(name, []))
        print(f"  {name}: {n} 套")
    # 按去重 key 统计：各平台独立去重、跨平台去重
    seen_key: dict = {}
    for plat in PLATFORMS:
        for h in platform_houses.get(plat, []):
            try:
                k = _house_dedup_key(h)
            except Exception:
                continue
            if k not in seen_key:
                seen_key[k] = plat
    print(f"  按「小区+地址+面积+租金+室数」去重后: 共 {len(seen_key)} 套唯一房源")
    # 仅保留一个平台时的数量
    keep_list = platform_houses.get(keep_platform, [])
    keep_keys = {_house_dedup_key(h) for h in keep_list if all(h.get(f) is not None for f in DEDUP_KEY_FIELDS)}
    print(f"  仅保留「{keep_platform}」平台: {len(keep_list)} 套（去重 key 数: {len(keep_keys)}）")
    print("---\n")


def _dedup_keep_one_platform(platform_houses: dict[str, list], keep_platform: str) -> list[dict]:
    """仅保留指定平台的房源：只取 keep_platform 的 items，按去重 key 去重后返回。"""
    seen: dict[tuple, dict] = {}
    for h in platform_houses.get(keep_platform, []):
        try:
            k = _house_dedup_key(h)
        except Exception:
            continue
        if k not in seen:
            seen[k] = h
    return list(seen.values())


# ── 主提取逻辑 ────────────────────────────────────────────────────────────────


def extract_mock_data(
    jsonl_path: Path,
    output_path: Path,
    keep_platform: str = "安居客",
) -> None:
    platform_houses: dict[str, list[dict]] = {p: [] for p in PLATFORMS}
    all_landmarks: list[dict] = []
    session_id: str = "unknown"

    print(f"[extract] 读取日志: {jsonl_path}")

    with jsonl_path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"  警告: 第 {line_no} 行 JSON 解析失败: {e}", file=sys.stderr)
                continue

            if session_id == "unknown":
                session_id = event.get("session_id", "unknown")

            if event.get("event") == "DEBUG_ALL_HOUSES":
                raw_resp = event.get("details", {}).get("raw_response", {})
                # 新结构：三平台分 key
                if any(p in raw_resp for p in PLATFORMS):
                    for platform in PLATFORMS:
                        plat_data = raw_resp.get(platform, {})
                        plat_items = plat_data.get("items", []) if isinstance(plat_data, dict) else []
                        if plat_items:
                            platform_houses[platform] = plat_items
                    total = sum(len(platform_houses[p]) for p in PLATFORMS)
                    print(f"  [DEBUG_ALL_HOUSES] 三平台: 链家 {len(platform_houses['链家'])} 套, "
                          f"安居客 {len(platform_houses['安居客'])} 套, 58同城 {len(platform_houses['58同城'])} 套")
                else:
                    items = raw_resp.get("items", [])
                    if items:
                        platform_houses["链家"] = items
                        print(f"  [DEBUG_ALL_HOUSES] 找到 {len(items)} 套房源（单结构）")
            elif event.get("event") == "DEBUG_ALL_LANDMARKS":
                items = event.get("details", {}).get("raw_response", {}).get("items", [])
                if items:
                    all_landmarks = items
                    print(f"  [DEBUG_ALL_LANDMARKS] 找到 {len(all_landmarks)} 个地标")

    _print_platform_gap(platform_houses, keep_platform)
    # 仅保留一个平台：按去重 key 去重，同 key 只留一条（平台优先级：链家 > 安居客 > 58同城）
    all_houses = _dedup_keep_one_platform(platform_houses, keep_platform)

    if not all_houses:
        print("错误: 未找到 DEBUG_ALL_HOUSES 事件或 items 为空", file=sys.stderr)
        sys.exit(1)

    # ── 格式转换 ───────────────────────────────────────────────────────────────
    fixture_houses: list[dict] = []
    skipped = 0
    for h in all_houses:
        try:
            fixture_houses.append(house_to_fixture(h))
        except ValueError as e:
            print(f"  警告（跳过）: {e}", file=sys.stderr)
            skipped += 1
    if skipped:
        print(f"  共跳过 {skipped} 套字段不完整的房源")

    fixture_landmarks: list[dict] = []
    lm_skipped = 0
    for lm in all_landmarks:
        try:
            fixture_landmarks.append(landmark_to_fixture(lm))
        except ValueError as e:
            print(f"  警告（跳过地标）: {e}", file=sys.stderr)
            lm_skipped += 1
    if lm_skipped:
        print(f"  共跳过 {lm_skipped} 个字段不完整的地标")

    # ── 写出 YAML ──────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("# Mock Fixture — 由 extract_mock_data.py 自动生成\n")
        f.write(f"# 源日志: {jsonl_path.name}\n")
        f.write(f"# session_id: {session_id}\n")
        f.write(f"# 地标数量: {len(fixture_landmarks)}\n")
        f.write(f"# 房源数量: {len(fixture_houses)}\n\n")
        yaml.dump(
            {"landmarks": fixture_landmarks, "houses": fixture_houses},
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"[extract] OK 已写出: {output_path}")
    print(f"          {len(fixture_landmarks)} 个地标, {len(fixture_houses)} 套房源")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 JSONL 评估日志的 DEBUG_ALL_HOUSES、DEBUG_ALL_LANDMARKS 事件生成 mock_data YAML fixture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("jsonl", help="JSONL 日志文件路径")
    parser.add_argument(
        "output",
        nargs="?",
        default="mock_data/final-test.yaml",
        help="输出 YAML 路径（默认: mock_data/final-test.yaml）",
    )
    parser.add_argument(
        "--keep-platform",
        choices=PLATFORMS,
        default="安居客",
        help="去重时优先保留的平台（默认: 安居客）",
    )
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"错误: 日志文件不存在: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    extract_mock_data(jsonl_path, Path(args.output), keep_platform=args.keep_platform)


if __name__ == "__main__":
    main()
