#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final-test.yaml 统计脚本
输出：字段取值范围与分布、house 全量字段（不含 house_id）、tags 语义分类统计、landmarks 全量信息统计
用法:
  python stats_final_test.py                    # 默认 final-test.yaml -> final-test-stats.txt
  python stats_final_test.py a.yaml b.txt       # 指定输入 yaml 与输出 txt
"""

import argparse
import yaml
import json
from pathlib import Path
from collections import Counter, defaultdict

# 当前脚本所在目录
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_YAML = SCRIPT_DIR / "final-test.yaml"
DEFAULT_OUTPUT = SCRIPT_DIR / "final-test-stats.txt"

# house 需统计的字段（不含 house_id）
HOUSE_FIELDS = [
    "community", "district", "area", "address",
    "bedrooms", "livingrooms", "bathrooms", "area_sqm",
    "floor", "total_floors", "orientation", "decoration",
    "price", "rental_type", "property_type", "utilities_type",
    "elevator", "subway", "subway_station", "subway_distance",
    "commute_to_xierqi", "available_from", "tags",
    "hidden_noise_level", "status", "longitude", "latitude",
]

# tags 语义大类：关键词 -> 大类名
TAG_SEMANTIC_MAP = [
    ("看房方式", [
        "仅线上图片看房", "仅线上VR看房", "仅线上AR看房", "仅线下看房", "线下+线上",
        "仅周末看房", "仅工作日看房", "全天可看房",
        "工作日9-18点", "工作日9-12点", "工作日14-18点",
        "周末9-18点", "周末9-12点", "周末14-18点",
    ]),
    ("周边配套", [
        "近公园", "近商超", "近健身房", "近医院", "近学校",
        "近菜市场", "近餐饮", "近加油站", "近警察局", "近地铁站", "近银行",
    ]),
    ("租期", [
        "可月租", "可租2个月", "可租3个月", "可租4个月", "可租5个月",
        "可半年租", "可年租", "仅接受年租",
    ]),
    ("押金/付款周期", [
        "押一", "押二", "押三", "押一付三",
        "月付", "季付", "半年付", "年付",
    ]),
    ("费用包含", [
        "免水电费", "包水电费", "水电费另付",
        "包物业费", "免物业费", "物业费另付",
        "包取暖费", "免取暖费", "取暖费另付",
        "免宽带费", "包宽带", "网费另付",
        "免车位费", "包车位", "车位费另付",
    ]),
    ("中介/退租", [
        "收中介费", "中介费半月租",
        "提前退租可协商", "提前退租扣押金",
    ]),
    ("宠物/转租", [
        "可养猫", "可养狗", "可养宠物", "不可养宠物",
        "仅限小型犬", "可养宠物需宠物押金",
        "经同意可转租", "不可转租",
    ]),
    ("房屋特点", [
        "采光好", "南北通透", "高性价比",
        "精装", "豪华", "毛坯", "简装",
        "朝南", "朝北", "朝东", "朝西",
        "小户型", "大户型", "大两居", "大三居", "双卫",
        "一居", "二居", "三居", "四居",
        "有电梯", "高楼层", "高层",
    ]),
    ("交通出行", ["近地铁", "双地铁", "多地铁"]),
    ("房源类型", [
        "核心区", "学区房", "近高校", "合租", "小单间",
        "商住", "农村房", "农村自建房", "房东直租",
    ]),
    ("小区管理", [
        "物业管理到位", "物业管理差",
        "绿化好环境佳", "绿化少环境一般",
        "门禁刷卡", "门禁形同虚设", "24小时保安", "无门禁",
        "车库车位", "露天车位", "无车位",
    ]),
    ("合同/房东", [
        "合同规范条款清晰", "合同不规范",
        "房东好沟通", "房东难联系", "房东不配合",
    ]),
]

# 用于快速查找 tag -> 大类
TAG_TO_CATEGORY = {}
for cat, keywords in TAG_SEMANTIC_MAP:
    for kw in keywords:
        if kw not in TAG_TO_CATEGORY:
            TAG_TO_CATEGORY[kw] = cat


def classify_tag(tag: str) -> str:
    """将单个 tag 归入语义大类，未匹配的归为「其他」。"""
    return TAG_TO_CATEGORY.get(tag, "其他")


def flatten_dict(d: dict, prefix: str = "") -> dict:
    """将嵌套 dict 压平为 prefix.key 形式，值为叶子值（非 dict/list 的保持原样）。"""
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v and not any(isinstance(x, (dict, list)) for x in v.values()):
            out[key] = v
        elif isinstance(v, dict):
            out.update(flatten_dict(v, key))
        elif isinstance(v, list):
            if v and isinstance(v[0], str):
                out[key] = v  # 如 lines: [6号线, 10号线]
            else:
                out[key] = v
        else:
            out[key] = v
    return out


def collect_nested_keys(obj, prefix=""):
    """收集所有键路径及其取值（用于 distribution）。"""
    if not isinstance(obj, dict):
        return {}
    out = defaultdict(list)
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            for subk, subv in collect_nested_keys(v, key).items():
                out[subk].extend(subv)
        elif isinstance(v, list):
            if v and isinstance(v[0], (str, int, float, bool)) and not isinstance(v[0], dict):
                out[key].append(tuple(v) if isinstance(v[0], str) else v)
            else:
                out[key].append(v)
        else:
            out[key].append(v)
    return out


def value_distribution(values, is_numeric=False):
    """计算取值的分布（频次），数值型则额外给 min/max/unique_count）。"""
    if not values:
        return {"count": 0, "unique": 0, "distribution": []}
    c = Counter(values)
    total = len(values)
    dist = sorted(c.items(), key=lambda x: -x[1])
    res = {
        "count": total,
        "unique": len(c),
        "distribution": [(k, v, round(100.0 * v / total, 2)) for k, v in dist[:30]],
    }
    if is_numeric:
        try:
            nums = [float(x) for x in values if x is not None and str(x).replace(".", "").replace("-", "").isdigit()]
            if nums:
                res["min"] = min(nums)
                res["max"] = max(nums)
        except (ValueError, TypeError):
            pass
    return res


def main(yaml_path: Path, output_path: Path):
    print(f"正在加载 YAML: {yaml_path}（文件较大，请稍候）...")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    lines = []
    write = lambda s: lines.append(s)

    # ---------- 1. 总体概况 ----------
    write("=" * 60)
    write(f"{yaml_path.name} 统计报告")
    write("=" * 60)
    landmarks = data.get("landmarks") or []
    houses = data.get("houses") or []
    write(f"地标数量: {len(landmarks)}")
    write(f"房源数量: {len(houses)}")
    write("")

    # ---------- 2. House 全量字段（不含 house_id）----------
    write("=" * 60)
    write("二、House 字段取值范围与分布（不含 house_id）")
    write("=" * 60)

    for field in HOUSE_FIELDS:
        values = []
        for h in houses:
            if field in h:
                v = h[field]
                if field == "tags":
                    values.append(v)  # 先收集列表，后面单独统计
                    continue
                if isinstance(v, (list, dict)):
                    values.append(str(type(v).__name__))
                else:
                    values.append(v)
        if field == "tags":
            # tags 在下面「三、tags 语义分类」里统计
            all_tags = []
            for h in houses:
                t = h.get("tags") or []
                all_tags.extend(t)
            write(f"\n【{field}】")
            write(f"  出现条数: {sum(1 for h in houses if (h.get('tags') or []))} 条房源")
            write(f"  标签总个数: {len(all_tags)}, 去重后: {len(set(all_tags))}")
            continue
        if not values:
            write(f"\n【{field}】 缺失或未出现")
            continue
        write(f"\n【{field}】")
        try:
            nums = []
            for x in values:
                if x is None:
                    continue
                if isinstance(x, (int, float)):
                    nums.append(float(x))
                elif isinstance(x, str) and x.replace(".", "").replace("-", "").isdigit():
                    nums.append(float(x))
            if nums and field in ("area_sqm", "price", "subway_distance", "commute_to_xierqi", "total_floors", "longitude", "latitude"):
                write(f"  取值范围: min={min(nums)}, max={max(nums)}")
        except (ValueError, TypeError):
            pass
        c = Counter(values)
        total = len(values)
        write(f"  样本数: {total}, 取值种类: {len(c)}")
        top = c.most_common(25)
        for val, cnt in top:
            pct = round(100.0 * cnt / total, 2)
            write(f"    {repr(val)[:60]}: {cnt} ({pct}%)")

    # ---------- 3. Tags 语义分类与按大类统计 ----------
    write("")
    write("=" * 60)
    write("三、Tags 语义分类及大类统计")
    write("=" * 60)

    all_tags_flat = []
    for h in houses:
        for t in (h.get("tags") or []):
            all_tags_flat.append(t)

    by_category = defaultdict(lambda: Counter())
    for t in all_tags_flat:
        cat = classify_tag(t)
        by_category[cat][t] += 1

    for cat in sorted(by_category.keys(), key=lambda x: (0 if x == "其他" else 1, x)):
        c = by_category[cat]
        total_cat = sum(c.values())
        write(f"\n【{cat}】 共 {total_cat} 次")
        for tag, cnt in c.most_common(30):
            write(f"  {tag}: {cnt}")
        if len(c) > 30:
            write(f"  ... 其余 {len(c) - 30} 种略")

    # ---------- 4. Landmarks 全量信息（name, district, category 及 details 内全量）----------
    write("")
    write("=" * 60)
    write("四、Landmarks 全量字段统计（name, district, category 及 details 等）")
    write("=" * 60)

    # 4.1 顶层字段
    top_keys = ["id", "name", "category", "district", "longitude", "latitude"]
    for key in top_keys:
        values = [lm.get(key) for lm in landmarks if lm.get(key) is not None]
        write(f"\n【landmarks.{key}】")
        write(f"  样本数: {len(values)}, 取值种类: {len(set(str(v) for v in values))}")
        c = Counter(str(v) for v in values)
        for val, cnt in c.most_common(20):
            write(f"    {val[:50]}: {cnt}")

    # 4.2 details 内全量键及分布
    write("\n【landmarks.details 内字段】")
    details_keys = defaultdict(list)
    for lm in landmarks:
        d = lm.get("details") or {}
        for k, v in d.items():
            if isinstance(v, list):
                if v and isinstance(v[0], str):
                    for item in v:
                        details_keys[k].append(item)  # 如 lines 每条线单独统计
                else:
                    details_keys[k].append(f"list(len={len(v)})")
            else:
                details_keys[k].append(v)

    for k in sorted(details_keys.keys()):
        vals = details_keys[k]
        c = Counter(str(x)[:80] for x in vals)
        write(f"  details.{k}: 出现 {len(vals)} 次, 取值种类 {len(c)}")
        for val, cnt in c.most_common(15):
            write(f"    {val}: {cnt}")
        if len(c) > 15:
            write(f"    ... 共 {len(c)} 种取值")

    # ---------- 输出到文件 ----------
    text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(text)
    print(f"统计结果已写入: {output_path}")
    print("\n--- 预览（前 80 行）---")
    print("\n".join(lines[:80]))
    return lines, data  # 供多文件对比时使用


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="final-test YAML 统计脚本")
    parser.add_argument("yaml_path", nargs="?", type=Path, default=DEFAULT_YAML, help="输入 YAML 路径")
    parser.add_argument("output_path", nargs="?", type=Path, default=None, help="输出 TXT 路径（默认：与 yaml 同目录，名为 xxx-stats.txt）")
    args = parser.parse_args()
    yaml_path = args.yaml_path.resolve()
    output_path = args.output_path
    if output_path is None:
        output_path = yaml_path.parent / (yaml_path.stem + "-stats.txt")
    else:
        output_path = output_path.resolve()
    main(yaml_path, output_path)
