#!/usr/bin/env python3
"""从 JSONL 评估日志提取 mock_data，生成 test-simulator 可用的 YAML fixture。

读取日志中的 DEBUG_ALL_HOUSES 与 DEBUG_ALL_LANDMARKS 事件，将其 items 全量转换为
fixture 格式输出（含 landmarks 与 houses）。

用法（在 test-simulator/ 目录下运行）：
  python extract_mock_data.py <jsonl_path> [output_yaml]

示例：
  python extract_mock_data.py ../logs/eval_l00933108_EV-06_1772426116496476236.jsonl mock_data/EV-06.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

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


# ── 主提取逻辑 ────────────────────────────────────────────────────────────────


def extract_mock_data(jsonl_path: Path, output_path: Path) -> None:
    all_houses: list[dict] = []
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
                raw = event.get("details", {}).get("raw_response", {})
                # 新结构：三平台分 key；旧结构：顶层 items
                if "链家" in raw or "安居客" in raw or "58同城" in raw:
                    items = []
                    for platform in ("链家", "安居客", "58同城"):
                        plat_data = raw.get(platform, {})
                        plat_items = plat_data.get("items", []) if isinstance(plat_data, dict) else []
                        items.extend(plat_items)
                    if items:
                        all_houses = items
                        print(f"  [DEBUG_ALL_HOUSES] 找到 {len(all_houses)} 套房源（三平台合并）")
                else:
                    items = raw.get("items", [])
                    if items:
                        all_houses = items
                        print(f"  [DEBUG_ALL_HOUSES] 找到 {len(all_houses)} 套房源")
            elif event.get("event") == "DEBUG_ALL_LANDMARKS":
                items = event.get("details", {}).get("raw_response", {}).get("items", [])
                if items:
                    all_landmarks = items
                    print(f"  [DEBUG_ALL_LANDMARKS] 找到 {len(all_landmarks)} 个地标")

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
        default="mock_data/EV-06.yaml",
        help="输出 YAML 路径（默认: mock_data/EV-06.yaml）",
    )
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"错误: 日志文件不存在: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    extract_mock_data(jsonl_path, Path(args.output))


if __name__ == "__main__":
    main()
