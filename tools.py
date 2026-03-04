import asyncio
import os
from typing import Optional
import httpx
from pydantic import BaseModel

# 模块顶层常量（必须在模块加载时读取一次）
# 支持环境变量覆盖，与 debug_init_houses.py 一致；tools 不创建 client，client 由 main 传入且已设置 trust_env=False 不走代理
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
USER_ID = os.environ["USER_ID"]  # 模块加载时读取，不在函数内读取


def _get_headers() -> dict:
    return {"X-User-ID": USER_ID.encode("utf-8")}


# ── Story 8.1: UserPreferences 数据模型 ─────────────────────────────────────

DISTRICTS = {"海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"}

# 模块级全局映射表，由 build_area_district_map 填充（启动时由 main.py 调用）
AREA_TO_DISTRICT: dict[str, str] = {}

# 模块级地标名称集合，由 build_landmark_names 填充（启动时由 main.py 调用）
LANDMARK_NAMES: set[str] = set()

# 标签参考表（与 intent_interface_design_v2 4.1 一致，供 prompt 与过滤使用）
TAG_REFERENCE: dict[str, list[str]] = {
    "宠物": ["可养猫", "可养狗", "可养宠物", "不可养宠物", "仅限小型犬", "可养宠物需宠物押金"],
    "付款周期": ["月付", "季付", "半年付", "年付"],
    "押金": ["押一", "押二", "押三"],
    "中介/房源": ["房东直租", "收中介费"],
    "合同/房东": ["合同规范条款清晰", "合同不规范", "房东好沟通", "房东不配合", "房东难联系"],
    "看房方式": ["仅线下看房", "仅线上VR看房", "仅线上AR看房", "仅线上图片看房", "线下+线上"],
    "看房时间": [
        "全天可看房", "仅周末看房", "仅工作日看房", "工作日9-18点", "工作日14-18点",
        "工作日9-12点", "周末9-18点", "周末14-18点", "周末9-12点",
    ],
    "租期": ["可月租", "可租2个月", "可租3个月", "可租4个月", "可租5个月", "可半年租", "可年租", "仅接受年租"],
    "费用包含": [
        "包水电费", "免水电费", "水电费另付", "免宽带费", "包宽带", "网费另付",
        "包物业费", "免物业费", "物业费另付", "包车位", "免车位费", "车位费另付",
        "包取暖费", "免取暖费", "取暖费另付",
    ],
    "退租/转租": ["提前退租可协商", "提前退租扣押金", "经同意可转租", "不可转租"],
    "小区管理": [
        "车库车位", "露天车位", "无车位", "24小时保安", "门禁刷卡", "门禁形同虚设",
        "无门禁", "物业管理到位", "物业管理差", "绿化好环境佳", "绿化少环境一般",
    ],
    "周边配套": ["近公园", "近学校", "近菜市场", "近银行", "近医院", "近餐饮", "近健身房", "近警察局", "近商超", "近加油站"],
    "房屋特点": ["采光好", "南北通透", "高性价比"],
    "属性标签（软约束时用直接参数 decoration/elevator/orientation/floor_pref/rental_type）": [
        "有电梯", "精装修", "简装", "豪华装修", "朝南", "朝北", "朝东", "朝西", "西北",
        "高层", "低层", "整租", "合租",
    ],
}


class UserPreferences(BaseModel):
    # ── 位置 ──
    location: Optional[list[str]] = None
    clear_location: bool = False
    districts: Optional[list[str]] = None
    areas: Optional[list[str]] = None
    landmark_queries: Optional[list[str]] = None

    # ── API 硬约束 ──
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[str] = None
    rental_type: Optional[str] = None
    decoration: Optional[str] = None
    elevator: Optional[bool] = None
    orientation: Optional[str] = None
    floor_pref: Optional[str] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    max_subway_dist: Optional[int] = None
    subway_line: Optional[str] = None
    utilities_type: Optional[str] = None
    property_type: Optional[str] = None
    listing_platform: Optional[str] = None
    available_before: Optional[str] = None
    max_commute_minutes: Optional[int] = None
    noise_preference: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None

    # ── 独立偏好字段 ──
    no_agent_fee: Optional[bool] = None
    payment_method: Optional[str] = None
    deposit_type: Optional[str] = None

    # ── 硬约束标签类（直接参数，过滤时匹配房源 tags）──
    pet_policy: Optional[str] = None
    viewing_method: Optional[str] = None
    viewing_time: Optional[str] = None
    lease_flexibility: Optional[str] = None
    required_utilities: Optional[list[str]] = None
    termination_sublet: Optional[str] = None
    parking_type: Optional[str] = None
    security_requirement: Optional[str] = None
    property_management: Optional[str] = None
    environment_preference: Optional[str] = None
    required_nearby: Optional[list[str]] = None
    house_feature: Optional[str] = None
    landlord_contract: Optional[str] = None

    # ── 软约束标识（字段名列表，列表中的字段按软约束处理：匹配加分，不匹配不排除）──
    soft_constraint_keys: list[str] = []

    # ── 上下文记忆 ──
    mentioned_house_ids: list[str] = []
    current_focus_house_id: Optional[str] = None


def build_area_district_map(all_houses: list[dict]) -> dict[str, str]:
    """从全量房源数据中构建 area → district 映射表，跳过 area/district 为空的记录。"""
    mapping: dict[str, str] = {}
    for house in all_houses:
        area = house.get("area")
        district = house.get("district")
        if area and district:
            mapping[area] = district
    return mapping


def build_landmark_names(landmarks: list[dict]) -> set[str]:
    """从地标列表中提取 name 字段，构建用于反向子串匹配的地标名称集合。"""
    return {lm["name"] for lm in landmarks if lm.get("name")}


_LOCATION_FUZZY_SUFFIXES = ("商圈", "商业区", "片区", "附近")

# ── 装修等级常量（用于软偏好加分） ─────────────────────────────────────────────
# 归一化映射：LLM 可能输出 "精装修" 等变体
_DEC_NORM: dict[str, str] = {
    "精装修": "精装", "精修": "精装", "精": "精装",
    "简装修": "简装", "简修": "简装", "简": "简装",
    "豪华装修": "豪华", "豪装": "豪华",
    "毛坯房": "毛坯",
}
# 等级排序：值越大越高档
_DEC_LEVEL: dict[str, int] = {"毛坯": 1, "简装": 2, "精装": 3, "豪华": 4}


def resolve_location(location: str) -> dict:
    """将 LLM 输入的位置路由为 district / area / landmark_query。

    路由规则（优先级从高到低）：
    1. 去掉"区"后缀后，若在 DISTRICTS 中 → {"district": "XX"}
    2. 若在 AREA_TO_DISTRICT 中（精确匹配）→ {"area": "XX", "district": "YY"}
    2b. 模糊归一：依次去掉"商圈"/"商业区"/"片区"/"附近"后，若候选串在
        AREA_TO_DISTRICT 中 → {"area": 精确名, "district": "YY"}；
        若候选串在 DISTRICTS 中 → {"district": 精确名}
    3. 以"附近"结尾 → {"landmark_query": "XX"} （去掉"附近"）
    3b. 反向子串匹配：若系统内置 area 名称是 location 的子串 → {"area": 匹配名, "district": "YY"}
    3c. 反向子串匹配：若系统内置 district 名称是 location 的子串 → {"district": 匹配名}
    3d. 反向子串匹配：若系统内置 landmark 名称是 location 的子串 → {"landmark_query": 匹配名}
    4. 其他 → {"landmark_query": location}
    """
    # 规则1: 区名（支持"海淀"和"海淀区"两种写法）
    stripped = location.removesuffix("区")
    if stripped in DISTRICTS:
        return {"district": stripped}

    # 规则2: 商圈（依赖 AREA_TO_DISTRICT 映射，精确匹配）
    if location in AREA_TO_DISTRICT:
        return {"area": location, "district": AREA_TO_DISTRICT[location]}

    # 规则2b: 模糊归一 — 去掉常见后缀后尝试精确匹配，将 LLM 模糊输入转化为系统精确名称
    # 优先检查 AREA_TO_DISTRICT（O(1) set lookup），再检查 DISTRICTS
    for suffix in _LOCATION_FUZZY_SUFFIXES:
        if location.endswith(suffix):
            cand = location.removesuffix(suffix)
            if cand in AREA_TO_DISTRICT:
                return {"area": cand, "district": AREA_TO_DISTRICT[cand]}
            if cand in DISTRICTS:
                return {"district": cand}

    # 规则3: 地标（"XX附近"，候选串不在系统存储中时才落到此处）
    if location.endswith("附近"):
        landmark = location.removesuffix("附近")
        return {"landmark_query": landmark}

    # 规则3b: 反向子串匹配 — 系统内置 area 是 location 的子串（area 比 district 更精确，优先）
    for area, district in AREA_TO_DISTRICT.items():
        if area in location:
            return {"area": area, "district": district}

    # 规则3c: 反向子串匹配 — 系统内置 district 是 location 的子串
    for district in DISTRICTS:
        if district in location:
            return {"district": district}

    # 规则3d: 反向子串匹配 — 系统内置 landmark 名称是 location 的子串，返回精确名称作为查询词
    for name in LANDMARK_NAMES:
        if name in location:
            return {"landmark_query": name}

    # 规则4: 未知，作为地标查询
    return {"landmark_query": location}


def build_search_params(prefs: UserPreferences) -> dict:
    """将 UserPreferences 硬约束字段映射为 search_houses API 查询参数。"""
    params: dict = {}
    if prefs.districts:
        params["district"] = ",".join(prefs.districts)
    if prefs.areas:
        params["area"] = ",".join(prefs.areas)
    if prefs.min_price is not None:
        params["min_price"] = prefs.min_price
    if prefs.max_price is not None:
        params["max_price"] = prefs.max_price
    if prefs.bedrooms is not None:
        params["bedrooms"] = prefs.bedrooms
    if prefs.rental_type is not None:
        params["rental_type"] = prefs.rental_type
    if prefs.decoration is not None:
        params["decoration"] = prefs.decoration
    if prefs.elevator is True:
        params["elevator"] = "true"
    elif prefs.elevator is False:
        params["elevator"] = "false"
    if prefs.min_area is not None:
        params["min_area"] = prefs.min_area
    if prefs.max_area is not None:
        params["max_area"] = prefs.max_area
    if prefs.utilities_type is not None:
        params["utilities_type"] = prefs.utilities_type
    if prefs.subway_line is not None:
        params["subway_line"] = prefs.subway_line
    if prefs.max_subway_dist is not None:
        params["max_subway_dist"] = prefs.max_subway_dist
    if prefs.available_before is not None:
        params["available_from_before"] = prefs.available_before
    if prefs.max_commute_minutes is not None:
        params["commute_to_xierqi_max"] = prefs.max_commute_minutes
    if prefs.sort_by is not None:
        params["sort_by"] = prefs.sort_by
    if prefs.sort_order is not None:
        params["sort_order"] = prefs.sort_order
    params["listing_platform"] = prefs.listing_platform or "安居客"
    return params


async def search_by_landmark(
    client: httpx.AsyncClient, query: str, prefs: UserPreferences
) -> dict:
    """通过地标关键词搜索地标，再查询附近房源（链式调用）。

    返回格式与 search_houses 一致：{"total": N, "items": [...]}
    未找到地标时返回 {"total": 0, "items": [], "error": "..."}
    """
    landmark_result = await search_landmark(client, query=query)
    items = landmark_result.get("data", {}).get("items", [])
    if not items:
        return {"total": 0, "items": [], "error": f"未找到'{query}'相关地标"}

    landmark_id = items[0]["id"]
    nearby_params: dict = {"landmark_id": landmark_id, "page_size": 200}
    if prefs.listing_platform:
        nearby_params["listing_platform"] = prefs.listing_platform

    all_items: list = []
    page = 1
    total = None
    while True:
        nearby_params["page"] = page
        result = await search_nearby_landmark(client, **nearby_params)
        data = result.get("data", result)
        page_items = data.get("items", [])
        if total is None:
            total = data.get("total", 0)
        all_items.extend(page_items)
        if not page_items or len(all_items) >= total:
            break
        page += 1

    return {"total": total or len(all_items), "items": all_items}


def _subway_dist(item: dict) -> int:
    """返回房源地铁距离（米），缺失时返回 9999。"""
    return item.get("subway_distance") or 9999


def post_filter_and_rank(items: list[dict], prefs: UserPreferences, *, is_landmark_search: bool = False) -> list[dict]:
    """对搜索结果进行硬约束过滤和软偏好评分排序。

    硬过滤（所有路径）：
      - noise_preference="安静" → 过滤 hidden_noise_level 为"吵闹"/"临街"的房源。

    硬过滤（地标搜索路径补充，因 nearby API 不支持这些参数）：
      - min_price / max_price / bedrooms / rental_type / decoration / elevator
      - min_area / max_area / max_subway_dist / utilities_type / available_before
      - max_commute_minutes

    加分项（来自 prefs 直接字段）：
      - orientation 匹配 +10；floor_pref 匹配 +5

    直接参数→tags 硬过滤（8.1/8.3，仅当字段不在 soft_constraint_keys 时）、soft_constraint_keys 加分（8.2）见下方。
    """
    scored: list[tuple[int, dict]] = []
    soft_keys = set(prefs.soft_constraint_keys or [])
    # 单值标签类参数（过滤时要求房源 tags 包含该值，除非该字段在 soft_keys 中）
    _TAG_HARD_FIELDS = (
        "pet_policy", "viewing_method", "viewing_time", "lease_flexibility",
        "termination_sublet", "parking_type", "security_requirement",
        "property_management", "environment_preference", "house_feature", "landlord_contract",
    )
    for item in items:
        score = 0

        # 硬过滤：噪音偏好（安静 = 只保留安静，排除中等/吵闹/临街）
        if prefs.noise_preference == "安静":
            if item.get("hidden_noise_level") != "安静":
                continue

        # 硬过滤：朝向（仅当 orientation 不在 soft_keys 时）
        if prefs.orientation and "orientation" not in soft_keys:
            ori_target = prefs.orientation.replace("朝", "")
            if ori_target not in (item.get("orientation") or ""):
                continue

        # ── 直接参数 → tags 硬过滤（8.3 + 8.1），仅当字段不在 soft_keys 时 ──
        house_tags = set(item.get("tags") or [])
        if "payment_method" not in soft_keys and prefs.payment_method is not None and prefs.payment_method not in house_tags:
            continue
        if "deposit_type" not in soft_keys and prefs.deposit_type is not None and prefs.deposit_type not in house_tags:
            continue
        if "no_agent_fee" not in soft_keys and prefs.no_agent_fee is True and "房东直租" not in house_tags:
            continue
        skip_tag = False
        for field in _TAG_HARD_FIELDS:
            if field in soft_keys:
                continue
            val = getattr(prefs, field, None)
            if val is not None and val not in house_tags:
                skip_tag = True
                break
        if skip_tag:
            continue
        if "required_utilities" not in soft_keys and prefs.required_utilities and not all(t in house_tags for t in prefs.required_utilities):
            continue
        if "required_nearby" not in soft_keys and prefs.required_nearby and not all(t in house_tags for t in prefs.required_nearby):
            continue

        # ── 地标搜索补充硬过滤（仅当对应字段不在 soft_keys 时）──────────────────
        if is_landmark_search:
            if prefs.min_price is not None and (item.get("price") or 0) < prefs.min_price:
                continue
            if prefs.max_price is not None and (item.get("price") or 10**9) > prefs.max_price:
                continue
            if prefs.bedrooms is not None:
                allowed = {int(b) for b in str(prefs.bedrooms).split(",") if b.strip().isdigit()}
                if allowed and item.get("bedrooms") not in allowed:
                    continue
            if "rental_type" not in soft_keys and prefs.rental_type is not None and item.get("rental_type") != prefs.rental_type:
                continue
            if "decoration" not in soft_keys and prefs.decoration is not None:
                exp_dec = _DEC_NORM.get(prefs.decoration, prefs.decoration)
                act_dec = _DEC_NORM.get(item.get("decoration", ""), item.get("decoration", ""))
                if exp_dec and act_dec and exp_dec != act_dec:
                    continue
            if "elevator" not in soft_keys and prefs.elevator is True and not item.get("elevator"):
                continue
            if prefs.min_area is not None and (item.get("area_sqm") or 0) < prefs.min_area:
                continue
            if prefs.max_area is not None and (item.get("area_sqm") or 10**9) > prefs.max_area:
                continue
            if prefs.max_subway_dist is not None:
                dist = item.get("subway_distance")
                if dist is None or dist > prefs.max_subway_dist:
                    continue
            if prefs.utilities_type is not None and item.get("utilities_type") != prefs.utilities_type:
                continue
            if prefs.available_before is not None:
                avail = item.get("available_from", "")
                if avail and avail > prefs.available_before:
                    continue
            if prefs.max_commute_minutes is not None:
                commute = item.get("commute_to_xierqi")
                if commute is not None and int(commute) > prefs.max_commute_minutes:
                    continue
            if prefs.subway_line is not None:
                subway_info = item.get("subway") or ""
                if prefs.subway_line not in subway_info:
                    continue

        # 朝向偏好（硬约束时已过滤，此处加分；软约束时仅加分）
        if prefs.orientation:
            target = prefs.orientation.replace("朝", "")
            if target in item.get("orientation", ""):
                score += 10

        # 楼层偏好（加分）
        if prefs.floor_pref:
            if prefs.floor_pref in item.get("floor", ""):
                score += 5

        # soft_constraint_keys 对应字段的软加分（8.2，按字段名 + 取值驱动）
        for field in soft_keys:
            val = getattr(prefs, field, None)
            if val is None:
                continue
            if field == "decoration":
                exp_dec = _DEC_NORM.get(val, val)
                act_dec = _DEC_NORM.get(item.get("decoration", ""), item.get("decoration", ""))
                if exp_dec and act_dec and exp_dec == act_dec:
                    score += 5
            elif field == "elevator" and item.get("elevator") == val:
                score += 5
            elif field == "orientation":
                ori_target = str(val).replace("朝", "")
                if ori_target in (item.get("orientation") or ""):
                    score += 10
            elif field == "floor_pref":
                floor_val = item.get("floor") or ""
                if val in floor_val:
                    score += 5
                elif floor_val.startswith("共") and val == "低层":
                    try:
                        total = int(floor_val.replace("共", "").replace("层", ""))
                        if total <= 6:
                            score += 5
                    except ValueError:
                        pass
            elif field == "max_subway_dist" and isinstance(val, (int, float)):
                dist = item.get("subway_distance")
                if dist is not None and int(dist) <= int(val):
                    score += 5
            elif field == "rental_type" and item.get("rental_type") == val:
                score += 8
            elif field in _TAG_HARD_FIELDS and val in house_tags:
                score += 5
            elif field == "required_utilities" and isinstance(val, list):
                for t in val:
                    if t in house_tags:
                        score += 5
            elif field == "required_nearby" and isinstance(val, list):
                for t in val:
                    if t in house_tags:
                        score += 5
            elif field == "payment_method" and val in house_tags:
                score += 5
            elif field == "deposit_type" and val in house_tags:
                score += 5
            elif field == "no_agent_fee" and val and "房东直租" in house_tags:
                score += 5

        scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    result = [item for _, item in scored]
    return result


_SLIM_FIELDS = frozenset({
    "house_id", "community", "district", "area", "price", "bedrooms",
    "area_sqm", "decoration", "subway_station", "subway_distance",
    "rental_type", "elevator", "orientation", "floor",
    "available_from", "commute_to_xierqi",
})


async def update_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
    **kwargs,
) -> dict:
    """提取并合并用户租房偏好到 session，不执行搜索。

    调用后需再调用 search_by_preferences 获取匹配房源。
    """
    # 处理 clear_location：清除历史位置相关字段
    clear = kwargs.pop("clear_location", False)

    # 处理 location 字段：累加或替换
    new_locations: list[str] = kwargs.pop("location", None) or []
    if new_locations:
        # 解析新位置得到 district/area 集合，用于判断是否「换区」
        new_districts_set: set[str] = set()
        new_areas_set: set[str] = set()
        for loc in new_locations:
            routed = resolve_location(loc)
            if "district" in routed:
                new_districts_set.add(routed["district"])
            if "area" in routed:
                new_areas_set.add(routed["area"])
        existing_districts = set(session_prefs.districts or [])
        existing_areas = set(session_prefs.areas or [])
        # 换区语义：新位置含 district/area 且与现有位置无交集时，自动清空再设
        # 纯地标追加（new_districts_set 和 new_areas_set 均为空）不触发清除
        if not clear and (existing_districts or existing_areas):
            if (new_districts_set or new_areas_set) and not (
                new_districts_set & existing_districts or new_areas_set & existing_areas
            ):
                clear = True
        if clear:
            session_prefs.location = None
            session_prefs.districts = None
            session_prefs.areas = None
            session_prefs.landmark_queries = None
        existing = session_prefs.location or []
        if clear:
            session_prefs.location = new_locations
        else:
            merged = list(existing)
            for loc in new_locations:
                if loc not in merged:
                    merged.append(loc)
            session_prefs.location = merged

        # 路由每个位置到 district / area / landmark_query
        new_districts: list[str] = []
        new_areas: list[str] = []
        new_landmarks: list[str] = []
        for loc in (session_prefs.location or []):
            routed = resolve_location(loc)
            if "area" in routed:
                new_areas.append(routed["area"])
                if "district" in routed:
                    new_districts.append(routed["district"])
            elif "district" in routed:
                new_districts.append(routed["district"])
            if "landmark_query" in routed:
                new_landmarks.append(routed["landmark_query"])

        session_prefs.districts = new_districts if new_districts else None
        session_prefs.areas = new_areas if new_areas else None
        session_prefs.landmark_queries = new_landmarks if new_landmarks else None

    # 根据本轮回传入的 xxx_is_soft 推导 soft_constraint_keys（并集去重）
    _SOFT_ALLOWED = frozenset({
        "decoration", "elevator", "orientation", "floor_pref", "max_subway_dist", "rental_type",
        "pet_policy", "viewing_method", "viewing_time", "lease_flexibility",
        "termination_sublet", "parking_type", "security_requirement", "property_management",
        "environment_preference", "house_feature", "landlord_contract",
        "required_utilities", "required_nearby", "payment_method", "deposit_type", "no_agent_fee",
    })
    _IS_SOFT_SUFFIX = "_is_soft"
    seen = set(session_prefs.soft_constraint_keys)
    for key in list(kwargs.keys()):
        if key.endswith(_IS_SOFT_SUFFIX) and kwargs[key] is True:
            field = key[: -len(_IS_SOFT_SUFFIX)]
            if field in _SOFT_ALLOWED and field not in seen:
                seen.add(field)
                session_prefs.soft_constraint_keys.append(field)
    for key in list(kwargs.keys()):
        if key.endswith(_IS_SOFT_SUFFIX):
            kwargs.pop(key, None)

    # 合并其余偏好字段（只更新传入的非 None 字段）
    updatable_fields = {
        "min_price", "max_price", "bedrooms", "rental_type", "decoration",
        "elevator", "min_area", "max_area", "utilities_type", "subway_line",
        "max_subway_dist", "listing_platform", "available_before", "max_commute_minutes",
        "noise_preference", "orientation", "floor_pref", "no_agent_fee", "payment_method",
        "deposit_type", "property_type", "sort_by", "sort_order",
        "pet_policy", "viewing_method", "viewing_time", "lease_flexibility",
        "required_utilities", "termination_sublet", "parking_type", "security_requirement",
        "property_management", "environment_preference", "required_nearby", "house_feature",
        "landlord_contract",
    }
    for field, value in kwargs.items():
        if field in updatable_fields and value is not None:
            setattr(session_prefs, field, value)

    return {
        "preferences_summary": session_prefs.model_dump(
            exclude_none=True, exclude={"clear_location"}
        ),
    }


async def search_by_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
) -> dict:
    """按当前 session 偏好搜索并返回 top 5 精简房源列表。

    需在 update_preferences 之后调用，使用已合并的偏好进行搜索。
    支持多地标并行搜索，以及地标与区域路径并行执行。
    """
    has_landmarks = bool(session_prefs.landmark_queries)
    has_areas = bool(session_prefs.districts or session_prefs.areas)

    coros: list = []
    is_landmark_flags: list[bool] = []

    if has_landmarks:
        for lq in session_prefs.landmark_queries:
            coros.append(search_by_landmark(client, lq, session_prefs))
            is_landmark_flags.append(True)

    if has_areas or not has_landmarks:
        params = build_search_params(session_prefs)
        coros.append(search_houses(client, **params))
        is_landmark_flags.append(False)

    raw_results = await asyncio.gather(*coros)

    seen_ids: set[str] = set()
    all_filtered: list[dict] = []
    total_raw = 0

    for is_lm, raw_result in zip(is_landmark_flags, raw_results):
        raw_items = raw_result.get("items", [])
        total_raw += raw_result.get("total", len(raw_items))
        filtered_part = post_filter_and_rank(
            raw_items, session_prefs, is_landmark_search=is_lm
        )
        for item in filtered_part:
            hid = item.get("house_id")
            if hid and hid not in seen_ids:
                seen_ids.add(hid)
                all_filtered.append(item)

    filtered = all_filtered

    # 用户指定 sort_by 时，在评分排序后按 sort_by 做稳定排序（评分同分时体现用户排序）
    sort_key_map = {
        "price": lambda h: h.get("price") or 10**9,
        "area": lambda h: h.get("area_sqm") or 0,
        "subway": lambda h: h.get("subway_distance") or 9999,
    }
    if session_prefs.sort_by and session_prefs.sort_by in sort_key_map:
        reverse = session_prefs.sort_order == "desc"
        filtered.sort(key=sort_key_map[session_prefs.sort_by], reverse=reverse)
    elif session_prefs.max_commute_minutes is not None and filtered and "commute_to_xierqi" in (filtered[0] if filtered else {}):
        filtered.sort(key=lambda h: int(h.get("commute_to_xierqi", 10**9)))

    top_items = [
        {k: v for k, v in item.items() if k in _SLIM_FIELDS}
        for item in filtered[:5]
    ]

    return {
        "total_matched": len(filtered),
        "total_raw": total_raw,
        "items": top_items,
        "preferences_summary": session_prefs.model_dump(
            exclude_none=True, exclude={"clear_location"}
        ),
    }


# ── Story 8.1: 5 工具体系 TOOLS 列表（意图接口 v2）────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "提取或更新用户的租房偏好，仅合并偏好不搜索。调用后必须再调用 search_by_preferences 获取匹配房源。每轮只传本轮新增/变更的字段；用户说「最好/希望」时，除设主字段外必须同时设对应 xxx_is_soft: true。数组类（如 required_nearby）追加时只传本轮新增项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户提到的位置，行政区/商圈/地标/地铁站/小区名均可。示例：[\"海淀\"]、[\"望京\"]、[\"国贸附近\"]、[\"百子湾\"]、[\"西二旗站\"]、[\"建清园南区\"]。多位置用数组：[\"朝阳\",\"海淀\"]"
                    },
                    "clear_location": {
                        "type": "boolean",
                        "description": "true=清除之前的位置（用于「换XX看看」「改到XX」场景），默认 false"
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "最低月租金（元）。「3000以上」→ min_price=3000"
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "最高月租金（元）。「预算5000」「5000以内」→ max_price=5000；「3000左右」→ min_price=2500, max_price=3500"
                    },
                    "bedrooms": {
                        "type": "string",
                        "description": "卧室数，字符串格式。「两居室」→\"2\"，「两居或三居」→\"2,3\"，「一居」→\"1\"。合租单间也传\"1\""
                    },
                    "rental_type": {
                        "type": "string",
                        "enum": ["整租", "合租"],
                        "description": "整租或合租。「一个人住/自己住」→整租；「合租/找室友/有室友」→合租；「单间」→合租"
                    },
                    "decoration": {
                        "type": "string",
                        "enum": ["精装", "简装", "豪华", "毛坯", "空房"],
                        "description": "装修类型。「精装修/精装」→精装，「空房/自己带家具」→空房，「毛坯」→毛坯"
                    },
                    "elevator": {
                        "type": "boolean",
                        "description": "是否要求有电梯。「有电梯/要电梯/老人腿脚不便」→true"
                    },
                    "orientation": {
                        "type": "string",
                        "enum": ["朝南", "朝北", "朝东", "朝西", "南北", "东西", "西北"],
                        "description": "朝向。「朝南/采光好」→朝南，「南北通透」→南北，「西北」→西北"
                    },
                    "floor_pref": {
                        "type": "string",
                        "enum": ["低层", "中层", "高层"],
                        "description": "楼层偏好。「低楼层/一楼」→低层，「高层/视野好」→高层"
                    },
                    "min_area": {
                        "type": "integer",
                        "description": "最小面积（㎡）。「60平以上」→60"
                    },
                    "max_area": {
                        "type": "integer",
                        "description": "最大面积（㎡）"
                    },
                    "max_subway_dist": {
                        "type": "integer",
                        "description": "到最近地铁站最大距离（米）。「近地铁/交通方便」→800；「地铁500米内」→500；「地铁1公里」→1000；「走路10分钟」→800"
                    },
                    "subway_line": {
                        "type": "string",
                        "description": "地铁线路，使用包含匹配（如「13号线」也会匹配「13号线/昌平线」换乘站）。「13号线沿线」→\"13号线\""
                    },
                    "utilities_type": {
                        "type": "string",
                        "enum": ["民水民电", "商水商电"],
                        "description": "水电类型"
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["住宅", "公寓"],
                        "description": "物业类型"
                    },
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "指定挂牌平台。用户说「在链家上找」→\"链家\""
                    },
                    "available_before": {
                        "type": "string",
                        "description": "可入住日期上限，YYYY-MM-DD。「3月份入住」→\"2026-03-01\"；「3月10号前入住」→\"2026-03-10\""
                    },
                    "max_commute_minutes": {
                        "type": "integer",
                        "description": "到西二旗通勤上限（分钟）。「通勤30分钟内」→30"
                    },
                    "noise_preference": {
                        "type": "string",
                        "enum": ["安静"],
                        "description": "噪音偏好。「安静/不要吵/隔音好/睡眠浅/需要静养/睡眠不好/要安静」→必须设\"安静\""
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["price", "area", "subway"],
                        "description": "排序字段。「按价格排」→price，「按面积排」→area，「按地铁距离排」→subway"
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "排序方向。「从低到高/从近到远/从便宜到贵」→asc，「从高到低/从大到小」→desc"
                    },
                    "no_agent_fee": {
                        "type": "boolean",
                        "description": "true=用户要求免中介费/不想交中介费/房东直租。false 不传"
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["月付", "季付", "半年付", "年付"],
                        "description": "付款周期偏好。「月付/按月付/能不能月付/希望月付」→月付；「季付」→季付。用户问付款方式、月付时用本字段，不要用 lease_flexibility（租期长短）。与 xxx_is_soft 成对使用时可表示「最好能月付」"
                    },
                    "deposit_type": {
                        "type": "string",
                        "enum": ["押一", "押二", "押三"],
                        "description": "押金偏好。「押一付一」→押一，「可以押二」→押二"
                    },
                    "pet_policy": {
                        "type": "string",
                        "enum": ["可养猫", "可养狗", "可养宠物", "不可养宠物", "仅限小型犬", "可养宠物需宠物押金"],
                        "description": "宠物政策（硬约束）。「要能养猫」→可养猫，「能养狗」→可养狗"
                    },
                    "viewing_method": {
                        "type": "string",
                        "enum": ["仅线下看房", "仅线上VR看房", "仅线上AR看房", "仅线上图片看房", "线下+线上"],
                        "description": "看房方式（硬约束）"
                    },
                    "viewing_time": {
                        "type": "string",
                        "enum": ["全天可看房", "仅周末看房", "仅工作日看房", "工作日9-18点", "工作日14-18点", "工作日9-12点", "周末9-18点", "周末14-18点", "周末9-12点"],
                        "description": "看房时间（硬约束）"
                    },
                    "lease_flexibility": {
                        "type": "string",
                        "enum": ["可月租", "可租2个月", "可租3个月", "可租4个月", "可租5个月", "可半年租", "可年租", "仅接受年租"],
                        "description": "租期长短灵活性（硬约束）。「可短租/可月租/最多租3个月」→可月租/可租3个月等。与付款周期 payment_method（月付/季付）区分：用户说「月付」时用 payment_method，不要用本字段"
                    },
                    "required_utilities": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["包水电费", "免水电费", "免宽带费", "包宽带", "包物业费", "免物业费", "包车位", "免车位费", "包取暖费", "免取暖费"]},
                        "description": "必须包含的费用项（硬约束，房源 tags 须全部匹配）。「网费/宽带包含在房租里」→[\"包宽带\"]；「物业费包在房租里」→[\"包物业费\"]；「车位费包含/免费车位」→[\"免车位费\"]。注意：「包」表示含在租金内，「免」表示不另收费；用户说包含在房租里时用「包宽带」「包物业费」，不要用免宽带费/免物业费"
                    },
                    "termination_sublet": {
                        "type": "string",
                        "enum": ["提前退租可协商", "提前退租扣押金", "经同意可转租", "不可转租"],
                        "description": "退租/转租政策（硬约束）"
                    },
                    "parking_type": {
                        "type": "string",
                        "enum": ["车库车位", "露天车位", "无车位"],
                        "description": "车位有无及类型（硬约束）。仅表示要车库/露天/无车位。若用户说「有车位且最好免费」「车位费包在房租里」应用 required_utilities: [\"免车位费\"] 并设 required_utilities_is_soft，不要用本字段"
                    },
                    "security_requirement": {
                        "type": "string",
                        "enum": ["24小时保安", "门禁刷卡", "门禁形同虚设", "无门禁"],
                        "description": "安保/门禁要求（硬约束）"
                    },
                    "property_management": {
                        "type": "string",
                        "enum": ["物业管理到位", "物业管理差"],
                        "description": "物业管理要求（硬约束）"
                    },
                    "environment_preference": {
                        "type": "string",
                        "enum": ["绿化好环境佳", "绿化少环境一般"],
                        "description": "小区环境偏好（硬约束）"
                    },
                    "required_nearby": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["近公园", "近学校", "近菜市场", "近银行", "近医院", "近餐饮", "近健身房", "近警察局", "近商超", "近加油站"]},
                        "description": "必须有的周边配套（硬约束，房源 tags 须全部匹配）"
                    },
                    "house_feature": {
                        "type": "string",
                        "enum": ["采光好", "南北通透", "高性价比"],
                        "description": "房屋特点（硬约束）"
                    },
                    "landlord_contract": {
                        "type": "string",
                        "enum": ["合同规范条款清晰", "合同不规范", "房东好沟通", "房东不配合", "房东难联系"],
                        "description": "合同/房东相关要求（硬约束）"
                    },
                    "decoration_is_soft": {"type": "boolean", "description": "true=本轮回该维度为软约束（匹配加分，不匹配不排除）。仅当用户说「最好/希望/如果有」时设为 true"},
                    "elevator_is_soft": {"type": "boolean", "description": "同上，对应 elevator"},
                    "orientation_is_soft": {"type": "boolean", "description": "同上，对应 orientation"},
                    "floor_pref_is_soft": {"type": "boolean", "description": "同上，对应 floor_pref"},
                    "max_subway_dist_is_soft": {"type": "boolean", "description": "同上，对应 max_subway_dist"},
                    "rental_type_is_soft": {"type": "boolean", "description": "同上，对应 rental_type"},
                    "pet_policy_is_soft": {"type": "boolean", "description": "同上，对应 pet_policy"},
                    "viewing_method_is_soft": {"type": "boolean", "description": "同上，对应 viewing_method"},
                    "viewing_time_is_soft": {"type": "boolean", "description": "同上，对应 viewing_time"},
                    "lease_flexibility_is_soft": {"type": "boolean", "description": "同上，对应 lease_flexibility"},
                    "termination_sublet_is_soft": {"type": "boolean", "description": "同上，对应 termination_sublet"},
                    "parking_type_is_soft": {"type": "boolean", "description": "同上，对应 parking_type"},
                    "security_requirement_is_soft": {"type": "boolean", "description": "同上，对应 security_requirement"},
                    "property_management_is_soft": {"type": "boolean", "description": "同上，对应 property_management"},
                    "environment_preference_is_soft": {"type": "boolean", "description": "同上，对应 environment_preference"},
                    "house_feature_is_soft": {"type": "boolean", "description": "同上，对应 house_feature"},
                    "landlord_contract_is_soft": {"type": "boolean", "description": "同上，对应 landlord_contract"},
                    "required_utilities_is_soft": {"type": "boolean", "description": "同上，对应 required_utilities"},
                    "required_nearby_is_soft": {"type": "boolean", "description": "同上，对应 required_nearby"},
                    "payment_method_is_soft": {"type": "boolean", "description": "同上，对应 payment_method"},
                    "deposit_type_is_soft": {"type": "boolean", "description": "同上，对应 deposit_type"},
                    "no_agent_fee_is_soft": {"type": "boolean", "description": "同上，对应 no_agent_fee"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_preferences",
            "description": "按当前已合并的偏好搜索房源，返回匹配的 top 5 精简列表。必须在 update_preferences 之后调用。当用户说「帮我找找」「找一下」等明确找房意图时，若本轮有新增偏好须先 update_preferences 再调用本工具；若偏好已在之前轮次设置且本轮仅表达找房意图，可直接调用本工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_detail",
            "description": "获取单套房源完整详情：地址、户型、面积、租金、装修、朝向、楼层、设施、噪音评级、标签等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1、HF_25"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_listings",
            "description": "获取指定房源在链家/安居客/58同城三个平台的全部挂牌记录，用于比较同一房源的跨平台价格差异。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，如 HF_1"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_action",
            "description": "对指定房源执行租房、退租或下架操作，调用 API 完成状态变更（不能只回复文字，必须调用此工具）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["rent", "terminate", "offline"],
                        "description": "rent=租房，terminate=退租，offline=下架"
                    },
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1"},
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，必填"
                    }
                },
                "required": ["action", "house_id", "listing_platform"]
            }
        }
    }
]


# ── Task 2: search_houses ───────────────────────────────────────────────────
async def search_houses(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        base_params: dict = {k: v for k, v in kwargs.items() if v is not None}
        base_params["page"] = 1

        resp = await client.get(
            "/api/houses/by_platform",
            params=base_params,
            headers=_get_headers(),
        )
        resp.raise_for_status()

        result = resp.json()
        inner = result.get("data", result)
        all_items: list = list(inner.get("items", []))
        total: int = inner.get("total", len(all_items))

        page = 2
        while len(all_items) < total:
            next_params = {**base_params, "page": page}
            next_resp = await client.get(
                "/api/houses/by_platform",
                params=next_params,
                headers=_get_headers(),
            )
            next_resp.raise_for_status()
            next_result = next_resp.json()
            next_inner = next_result.get("data", next_result)
            all_items.extend(next_inner.get("items", []))
            page += 1

        return {"total": total, "items": all_items}
    except Exception as e:
        return {"error": f"search_houses failed: {str(e)}"}


# ── Task 3: get_house_detail ────────────────────────────────────────────────
async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        resp = await client.get(f"/api/houses/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_house_detail failed: {str(e)}"}


# ── Task 4: search_landmark ─────────────────────────────────────────────────
async def search_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {}
        # TOOLS schema 用 "query"，API 实际参数名为 "q"
        if kwargs.get("query") is not None:
            params["q"] = kwargs["query"]
        if kwargs.get("category") is not None:
            params["category"] = kwargs["category"]
        if kwargs.get("district") is not None:
            params["district"] = kwargs["district"]

        # 地标接口不需要 X-User-ID
        resp = await client.get("/api/landmarks/search", params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_landmark failed: {str(e)}"}


# ── Task 5: search_nearby_landmark ─────────────────────────────────────────
async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        resp = await client.get(
            "/api/houses/nearby",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_nearby_landmark failed: {str(e)}"}


# ── Task 6: get_nearby_amenities ────────────────────────────────────────────
async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        # FR16 要求 1000 米，覆盖 API 默认的 3000 米
        if "max_distance_m" not in params:
            params["max_distance_m"] = 1000
        resp = await client.get(
            "/api/houses/nearby_landmarks",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_nearby_amenities failed: {str(e)}"}


# ── Task 7: execute_action ──────────────────────────────────────────────────
async def execute_action(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        action = kwargs.get("action", "")
        house_id = str(kwargs.get("house_id", ""))
        listing_platform = kwargs.get("listing_platform", "安居客")

        valid_actions = {"rent", "terminate", "offline"}
        if action not in valid_actions:
            return {"error": f"execute_action failed: unknown action {action}"}

        resp = await client.post(
            f"/api/houses/{house_id}/{action}",
            params={"listing_platform": listing_platform},
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"execute_action failed: {str(e)}"}


# ── get_houses_by_community ─────────────────────────────────────────────────
async def get_houses_by_community(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        resp = await client.get("/api/houses/by_community", params=params, headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_houses_by_community failed: {str(e)}"}


# ── get_house_listings ───────────────────────────────────────────────────────
async def get_house_listings(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        resp = await client.get(f"/api/houses/listings/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_house_listings failed: {str(e)}"}


# ── get_all_houses_for_debug：session 初始化时获取全量房屋用于调试 ───────
PLATFORMS = ["链家", "安居客", "58同城"]


async def _fetch_all_houses_for_platform(
    client: httpx.AsyncClient, platform: str
) -> dict:
    """不受 MAX_PAGES 限制地翻页，获取单个平台的全量房源。"""
    all_items: list = []
    page = 1
    page_size = 200
    total = None
    while True:
        try:
            resp = await client.get(
                "/api/houses/by_platform",
                params={
                    "page": page,
                    "page_size": page_size,
                    "listing_platform": platform,
                },
                headers=_get_headers(),
            )
            resp.raise_for_status()
        except Exception:
            break
        inner = resp.json().get("data", resp.json())
        items = inner.get("items", [])
        if total is None:
            total = inner.get("total", 0)
        all_items.extend(items)
        if not items or len(all_items) >= total:
            break
        page += 1
    return {"total": total or len(all_items), "items": all_items}


async def get_all_houses_for_debug(client: httpx.AsyncClient) -> dict:
    """获取链家、安居客、58同城三个平台的全量房源，用于调试日志。"""
    tasks = [
        _fetch_all_houses_for_platform(client, platform) for platform in PLATFORMS
    ]
    results = await asyncio.gather(*tasks)
    return {platform: result for platform, result in zip(PLATFORMS, results)}


# ── get_all_landmarks_for_debug：session 初始化时获取全量地标用于调试 ──────
async def get_all_landmarks_for_debug(client: httpx.AsyncClient) -> dict:
    """获取全量地标数据用于调试日志。"""
    try:
        resp = await client.get("/api/landmarks")
        resp.raise_for_status()
        inner = resp.json().get("data", resp.json())
        items = inner.get("items", [])
        return {"total": len(items), "items": items}
    except Exception as e:
        return {"error": f"get_all_landmarks_for_debug failed: {str(e)}", "total": 0, "items": []}


# ── init_houses（Story 2.2 已实现，保持不变） ───────────────────────────────
async def init_houses(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.post("/api/houses/init", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"init_houses failed: {str(e)}"}
