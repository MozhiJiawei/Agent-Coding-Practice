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


class UserPreferences(BaseModel):
    # ── 位置（LLM 输入统一字段） ──
    location: Optional[list[str]] = None
    clear_location: bool = False

    # ── 内部字段（代码路由后写入，LLM 不直接设置） ──
    districts: Optional[list[str]] = None
    areas: Optional[list[str]] = None
    landmark_queries: Optional[list[str]] = None

    # ── 硬约束 ──
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[str] = None
    rental_type: Optional[str] = None
    decoration: Optional[str] = None
    elevator: Optional[bool] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    utilities_type: Optional[str] = None
    subway_line: Optional[str] = None
    max_subway_dist: Optional[int] = None  # 到最近地铁站最大距离（米），近地铁默认 800
    listing_platform: Optional[str] = None
    available_before: Optional[str] = None
    max_commute_minutes: Optional[int] = None

    # ── 软偏好 ──
    noise_preference: Optional[str] = None
    orientation: Optional[str] = None
    floor_pref: Optional[str] = None
    sort_by: Optional[str] = None  # price / area / subway
    sort_order: Optional[str] = None  # asc / desc
    no_agent_fee: Optional[bool] = None
    payment_method: Optional[str] = None

    # ── 模糊软偏好（「更好」「尽量」「最好」等表达，不作为 API 硬过滤，仅用于加分排序） ──
    soft_preferences: Optional[dict] = None

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
    nearby_params: dict = {"landmark_id": landmark_id}
    if prefs.listing_platform:
        nearby_params["listing_platform"] = prefs.listing_platform

    result = await search_nearby_landmark(client, **nearby_params)
    data = result.get("data", result)
    return {"total": data.get("total", 0), "items": data.get("items", [])}


def _subway_dist(item: dict) -> int:
    """返回房源地铁距离（米），缺失时返回 9999。"""
    return item.get("subway_distance") or 9999


def post_filter_and_rank(items: list[dict], prefs: UserPreferences) -> list[dict]:
    """对搜索结果进行软偏好过滤和评分排序。

    硬过滤：
      - noise_preference="安静" → 过滤 hidden_noise_level 为"吵闹"/"临街"的房源。
      - 地铁距离由 API 的 max_subway_dist 硬过滤，此处不再处理。

    加分项（来自 prefs 直接字段）：
      - orientation 匹配 +10；floor_pref 匹配 +5

    加分项（来自 soft_preferences，用户说「更好/最好/尽量/优先」等非强制表达）：
      - elevator     +5   （有电梯加分）
      - decoration   分档  （达到或超过偏好等级 +10；低一档 +3；低两档及以下 0）
      - rental_type  +8   （匹配偏好的租赁方式）
      - orientation  +10  （朝向偏好，与直接字段合并）
      - floor_pref   +5   （楼层偏好，与直接字段合并）
    """
    scored: list[tuple[int, dict]] = []
    for item in items:
        score = 0

        # 硬过滤：噪音偏好
        if prefs.noise_preference == "安静":
            if item.get("hidden_noise_level") in ("吵闹", "临街"):
                continue

        # 朝向偏好（加分）
        if prefs.orientation:
            target = prefs.orientation.replace("朝", "")
            if target in item.get("orientation", ""):
                score += 10

        # 楼层偏好（加分）
        if prefs.floor_pref:
            if prefs.floor_pref in item.get("floor", ""):
                score += 5

        # ── soft_preferences 加分 ─────────────────────────────────────────────
        if prefs.soft_preferences:
            sp = prefs.soft_preferences

            # 电梯软偏好：有电梯 +5
            if sp.get("elevator") and item.get("elevator"):
                score += 5

            # 装修等级软偏好：达到或超过偏好等级 +10，低一档 +3，低两档及以下 0
            soft_dec_raw = sp.get("decoration")
            if soft_dec_raw:
                soft_dec = _DEC_NORM.get(str(soft_dec_raw), str(soft_dec_raw))
                pref_level = _DEC_LEVEL.get(soft_dec, 0)
                item_dec_raw = item.get("decoration", "")
                item_dec = _DEC_NORM.get(str(item_dec_raw), str(item_dec_raw))
                act_level = _DEC_LEVEL.get(item_dec, 0)
                if pref_level > 0:
                    gap = pref_level - act_level
                    if gap <= 0:
                        score += 10
                    elif gap == 1:
                        score += 3

            # 租赁方式软偏好：匹配偏好方式（整租/合租）+8
            soft_rental = sp.get("rental_type")
            if soft_rental and item.get("rental_type") == soft_rental:
                score += 8

            # 朝向软偏好（与直接字段合并）
            soft_ori = sp.get("orientation")
            if soft_ori:
                target = str(soft_ori).replace("朝", "")
                if target in item.get("orientation", ""):
                    score += 10

            # 楼层软偏好（与直接字段合并）
            soft_floor = sp.get("floor_pref")
            if soft_floor and soft_floor in item.get("floor", ""):
                score += 5

        scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    result = [item for _, item in scored]
    return result


_SLIM_FIELDS = frozenset({
    "house_id", "community", "district", "price", "bedrooms",
    "area_sqm", "decoration", "subway_station", "subway_distance",
})


async def update_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
    **kwargs,
) -> dict:
    """提取并合并用户租房偏好到 session，不执行搜索。

    调用后需再调用 search_by_preferences 获取匹配房源。
    """
    # 处理 soft_preferences：合并到 session（不作为 API 硬过滤，仅用于加分排序）
    new_soft = kwargs.pop("soft_preferences", None)
    if new_soft and isinstance(new_soft, dict):
        if session_prefs.soft_preferences is None:
            session_prefs.soft_preferences = {}
        session_prefs.soft_preferences.update(
            {k: v for k, v in new_soft.items() if v is not None}
        )

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
        # 换区语义：新位置与现有位置无交集时，自动清空再设，无需调用方传 clear_location
        if not clear and (existing_districts or existing_areas):
            if not (new_districts_set & existing_districts or new_areas_set & existing_areas):
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

    # 合并其余偏好字段（只更新传入的非 None 字段）
    updatable_fields = {
        "min_price", "max_price", "bedrooms", "rental_type", "decoration",
        "elevator", "min_area", "max_area", "utilities_type", "subway_line",
        "max_subway_dist", "listing_platform", "available_before", "max_commute_minutes",
        "noise_preference", "orientation", "floor_pref", "no_agent_fee", "payment_method",
        "sort_by", "sort_order",
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
    """
    if session_prefs.landmark_queries:
        raw_result = await search_by_landmark(
            client, session_prefs.landmark_queries[0], session_prefs
        )
    else:
        params = build_search_params(session_prefs)
        raw_result = await search_houses(client, **params)

    raw_items: list[dict] = raw_result.get("items", [])
    # 当用户设置了通勤上限时，按通勤时间升序排序，优先展示最近的房源
    if session_prefs.max_commute_minutes is not None and raw_items and "commute_to_xierqi" in raw_items[0]:
        raw_items = sorted(
            raw_items,
            key=lambda h: int(h.get("commute_to_xierqi", 10**9)),
        )

    filtered = post_filter_and_rank(raw_items, session_prefs)

    top_items = [
        {k: v for k, v in item.items() if k in _SLIM_FIELDS}
        for item in filtered[:5]
    ]

    return {
        "total_matched": len(filtered),
        "total_raw": raw_result.get("total", len(raw_items)),
        "items": top_items,
        "preferences_summary": session_prefs.model_dump(
            exclude_none=True, exclude={"clear_location"}
        ),
    }


# ── Story 8.1: 4 工具体系 TOOLS 列表 ────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "提取或更新用户的租房偏好。仅合并偏好，不搜索房源。调用后需再调用 search_by_preferences 获取匹配房源。每轮只需提取本轮新增/变更的偏好，系统自动与历史偏好合并。当用户说「想换个安静一点的房子，帮我找找」等（偏好+找房意图）时，必须先调用本工具传入该偏好（如 noise_preference=\"安静\"）再调用 search_by_preferences。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "array", "items": {"type": "string"},
                        "description": "用户提到的位置（行政区/商圈/地标均可），如 ['望京']、['海淀']、['国贸附近']"
                    },
                    "clear_location": {
                        "type": "boolean",
                        "description": "true=清除之前的位置偏好（用于'换XX看看'场景）"
                    },
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "bedrooms": {"type": "string", "description": "卧室数，如 '2' 或 '2,3'"},
                    "rental_type": {"type": "string", "description": "整租 或 合租（硬约束：用户明确说「只要整租」「必须整租」时使用；若用户说「最好整租/整租优先/合租也行」等模糊表达，请改用 soft_preferences={\"rental_type\": \"整租\"}）"},
                    "decoration": {"type": "string", "description": "装修类型：精装/简装/豪华/毛坯。用户把装修作为明确条件时传此硬约束，例如「精装两居」「东城精装两居」「要精装」「精装的」「只要精装」「必须精装」→ decoration=\"精装\"。仅当用户说「精装最好/最好精装/简装也行」等软化表达时改用 soft_preferences={\"decoration\": \"精装\"}，不传本字段。"},
                    "elevator": {"type": "boolean", "description": "是否必须有电梯（硬约束：「必须有电梯」「要求电梯」时使用；若用户说「有电梯更好」等模糊表达，请改用 soft_preferences={\"elevator\": true}）"},
                    "min_area": {"type": "integer", "description": "最小面积（平米）"},
                    "max_subway_dist": {"type": "integer", "description": "到最近地铁站的最大距离（米）。用户说「近地铁」「地铁方便」等未给具体数字时默认 800；用户说「离地铁 500 米以内」时传 500。"},
                    "subway_line": {"type": "string", "description": "地铁线路，如 13号线"},
                    "utilities_type": {"type": "string", "description": "水电类型，如 民水民电"},
                    "listing_platform": {"type": "string", "description": "挂牌平台：链家/安居客/58同城"},
                    "available_before": {"type": "string", "description": "可入住日期上限，YYYY-MM-DD"},
                    "max_commute_minutes": {"type": "integer", "description": "到西二旗通勤上限（分钟）"},
                    "noise_preference": {"type": "string", "description": "噪音偏好，如 安静"},
                    "orientation": {"type": "string", "description": "朝向偏好，如 朝南"},
                    "sort_by": {"type": "string", "description": "排序字段：price/area/subway"},
                    "sort_order": {"type": "string", "description": "排序方向：asc/desc"},
                    "soft_preferences": {
                        "type": "object",
                        "description": "软偏好：用户说「XX更好」「最好XX」「尽量XX」「如果有XX就好了」「XX优先/XX也行」等模糊表达时使用，不作为搜索硬过滤条件，仅对结果加分排序，避免因非核心条件导致结果为零。出现在此字段的属性禁止同时出现在硬约束字段中。示例：「有电梯更好」→ {\"elevator\": true}；「精装最好，简装也行」→ {\"decoration\": \"精装\"}；「最好整租」→ {\"rental_type\": \"整租\"}；「最好朝南」→ {\"orientation\": \"朝南\"}",
                        "properties": {
                            "elevator": {"type": "boolean", "description": "有电梯加分 +5"},
                            "decoration": {"type": "string", "description": "装修偏好等级（精装/简装/豪华/毛坯）：达到或超过偏好等级 +10，低一档 +3"},
                            "rental_type": {"type": "string", "description": "整租/合租 偏好，匹配加分 +8"},
                            "orientation": {"type": "string", "description": "朝向偏好，如 朝南，匹配 +10"},
                            "floor_pref": {"type": "string", "description": "楼层偏好，如 低层/高层，匹配 +5"}
                        }
                    }
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
