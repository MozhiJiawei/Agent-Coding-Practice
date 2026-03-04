import asyncio
import os
from typing import Optional
import httpx
from pydantic import BaseModel

from logger import log_event

# 用于 TOOL_API_RESPONSE 日志：过大列表只保留前 N 条并记录总数，便于分析又控制日志体积
def _response_for_log(response: dict, max_items: int = 20) -> dict:
    if not isinstance(response, dict):
        return {"_raw": str(response)[:500]}
    out = {}
    for k, v in response.items():
        if k == "items" and isinstance(v, list):
            if len(v) > max_items:
                out["items"] = v[:max_items]
                out["_items_truncated"] = True
                out["_total_items"] = len(v)
            else:
                out["items"] = v
        elif isinstance(v, dict):
            out[k] = _response_for_log(v, max_items)
        else:
            out[k] = v
    return out

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


def resolve_location(loc: str) -> dict:
    """将用户输入的位置字符串路由为 district / area+district / landmark_query。
    依赖模块级 DISTRICTS、AREA_TO_DISTRICT、LANDMARK_NAMES（session 初始化时填充）。
    优先级：1 行政区精确 → 2 商圈精确/模糊 → 3 地标名精确（含地铁站）→ 4 反向子串 → 5 兜底。
    """
    cleaned = loc.replace("附近", "").replace("周边", "").strip()
    if not cleaned:
        cleaned = loc.strip()

    # 规则1: 精确匹配行政区
    candidate = cleaned.rstrip("区")
    if candidate in DISTRICTS:
        return {"district": candidate}

    # 规则2: 精确/模糊匹配商圈（依次去掉后缀）
    for suffix in ("", "商圈", "商业区", "片区"):
        c = cleaned[: -len(suffix)] if suffix and cleaned.endswith(suffix) else cleaned
        if not c and suffix:
            continue
        cand = c.rstrip("区") if c else cleaned
        if cand in AREA_TO_DISTRICT:
            return {"area": cand, "district": AREA_TO_DISTRICT[cand]}

    # 规则3: 精确匹配地标名（含地铁站名），必须在反向子串之前
    if cleaned in LANDMARK_NAMES:
        return {"landmark_query": cleaned}

    # 规则4: 反向子串匹配（area 优先于 district 优先于 landmark）
    for area_name, district in AREA_TO_DISTRICT.items():
        if area_name in cleaned:
            return {"area": area_name, "district": district}
    for d in DISTRICTS:
        if d in cleaned:
            return {"district": d}
    for lm_name in LANDMARK_NAMES:
        if lm_name in cleaned:
            return {"landmark_query": lm_name}

    # 规则5: 兜底
    return {"landmark_query": cleaned if cleaned else loc}


# 供 update_preferences 使用的有效标量/数组字段名（不含 location/clear_location/xxx_is_soft）
_PREFS_SCALAR_KEYS = frozenset({
    "min_price", "max_price", "bedrooms", "rental_type", "decoration", "elevator",
    "orientation", "floor_pref", "min_area", "max_area", "max_subway_dist", "subway_line",
    "utilities_type", "property_type", "listing_platform", "available_before",
    "max_commute_minutes", "noise_preference", "sort_by", "sort_order",
    "no_agent_fee", "payment_method", "deposit_type",
    "pet_policy", "viewing_method", "viewing_time", "lease_flexibility",
    "required_utilities", "termination_sublet", "parking_type", "security_requirement",
    "property_management", "environment_preference", "required_nearby",
    "house_feature", "landlord_contract",
})
_PREFS_ARRAY_KEYS = frozenset({"required_utilities", "required_nearby"})


async def update_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
    **kwargs,
) -> dict:
    """提取并合并用户租房偏好到 session，不执行搜索。调用后需再调用 search_by_preferences 获取匹配房源。"""
    # Step 1: xxx_is_soft → soft_constraint_keys
    soft_keys = list(session_prefs.soft_constraint_keys)
    for key, value in kwargs.items():
        if key.endswith("_is_soft"):
            field = key[: -len("_is_soft")]
            if value is True and field not in soft_keys:
                soft_keys.append(field)
            elif value is False and field in soft_keys:
                soft_keys.remove(field)
    session_prefs.soft_constraint_keys = soft_keys

    # Step 2: location + clear_location
    if kwargs.get("clear_location") is True:
        session_prefs.location = None
        session_prefs.districts = None
        session_prefs.areas = None
        session_prefs.landmark_queries = None

    loc_list = kwargs.get("location")
    if loc_list:
        new_districts: list[str] = []
        new_areas: list[str] = []
        new_landmark_queries: list[str] = []
        for loc in loc_list:
            result = resolve_location(loc)
            if "district" in result:
                new_districts.append(result["district"])
            if "area" in result:
                new_areas.append(result["area"])
                new_districts.append(result["district"])
            if "landmark_query" in result:
                new_landmark_queries.append(result["landmark_query"])
        combined_loc = (session_prefs.location or []) + list(loc_list)
        seen_loc: set[str] = set()
        session_prefs.location = [x for x in combined_loc if x not in seen_loc and not seen_loc.add(x)]
        for d in new_districts:
            if session_prefs.districts is None:
                session_prefs.districts = []
            if d not in (session_prefs.districts or []):
                session_prefs.districts.append(d)
        for a in new_areas:
            if session_prefs.areas is None:
                session_prefs.areas = []
            if a not in (session_prefs.areas or []):
                session_prefs.areas.append(a)
        for q in new_landmark_queries:
            if session_prefs.landmark_queries is None:
                session_prefs.landmark_queries = []
            if q not in (session_prefs.landmark_queries or []):
                session_prefs.landmark_queries.append(q)

    # Step 3: 合并其余字段
    skip = {k for k in kwargs if k.endswith("_is_soft")} | {"location", "clear_location"}
    for key, value in kwargs.items():
        if key in skip or key not in _PREFS_SCALAR_KEYS and key not in _PREFS_ARRAY_KEYS:
            continue
        if key in _PREFS_ARRAY_KEYS and value is not None:
            existing = getattr(session_prefs, key) or []
            add = value if isinstance(value, list) else [value]
            seen = set(existing)
            for v in add:
                if v not in seen:
                    existing.append(v)
                    seen.add(v)
            setattr(session_prefs, key, existing)
        else:
            setattr(session_prefs, key, value)

    return {
        "preferences_summary": session_prefs.model_dump(
            exclude_none=True, exclude={"clear_location"}
        ),
    }


def build_search_params(prefs: UserPreferences) -> dict:
    """从 UserPreferences 构建 by_platform API 参数。软约束字段不下推；subway_line 不下推（改 post-filter 包含匹配）。"""
    soft = set(prefs.soft_constraint_keys or [])
    params: dict = {"listing_platform": prefs.listing_platform or "安居客"}
    if prefs.districts:
        params["district"] = ",".join(prefs.districts)
    if prefs.areas:
        params["area"] = ",".join(prefs.areas)
    for k, v in [
        ("min_price", prefs.min_price),
        ("max_price", prefs.max_price),
        ("bedrooms", prefs.bedrooms),
        ("min_area", prefs.min_area),
        ("max_area", prefs.max_area),
        ("property_type", prefs.property_type),
        ("utilities_type", prefs.utilities_type),
        ("available_from_before", prefs.available_before),
        ("commute_to_xierqi_max", prefs.max_commute_minutes),
        ("listing_platform", prefs.listing_platform or "安居客"),
    ]:
        if v is not None:
            params[k] = v
    # 未指定租住方式时默认整租
    if "rental_type" not in soft:
        params["rental_type"] = prefs.rental_type or "整租"
    if "decoration" not in soft and prefs.decoration is not None:
        params["decoration"] = prefs.decoration
    if "orientation" not in soft and prefs.orientation is not None:
        params["orientation"] = prefs.orientation
    if "elevator" not in soft and prefs.elevator is not None:
        params["elevator"] = "true" if prefs.elevator else "false"
    if "max_subway_dist" not in soft and prefs.max_subway_dist is not None:
        params["max_subway_dist"] = prefs.max_subway_dist
    if prefs.sort_by is not None:
        params["sort_by"] = prefs.sort_by
    if prefs.sort_order is not None:
        params["sort_order"] = prefs.sort_order
    return params


def _normalize_decoration(s: str | None) -> str:
    if not s:
        return ""
    m = {"精装修": "精装", "精修": "精装", "精": "精装", "简装修": "简装", "简修": "简装", "简": "简装"}
    return m.get(s, s)


def _match_floor(floor_val: str, pref: str) -> bool:
    if pref in (floor_val or ""):
        return True
    if (floor_val or "").startswith("共"):
        try:
            n = int(floor_val.replace("共", "").replace("层", "").strip())
            if pref == "低层" and n <= 6:
                return True
        except ValueError:
            pass
    return False


def _calc_soft_score(house: dict, prefs: UserPreferences) -> int:
    soft_keys = set(prefs.soft_constraint_keys or [])
    score = 0
    tags = set(house.get("tags") or [])
    for field in soft_keys:
        val = getattr(prefs, field, None)
        if val is None:
            continue
        matched = False
        if field == "decoration":
            matched = _normalize_decoration(house.get("decoration")) == _normalize_decoration(val)
        elif field == "elevator":
            matched = bool(house.get("elevator")) == val
        elif field == "orientation":
            matched = (val or "") in (house.get("orientation") or "")
        elif field == "floor_pref":
            matched = _match_floor(house.get("floor", ""), val)
        elif field == "rental_type":
            matched = house.get("rental_type") == val
        elif field == "max_subway_dist":
            matched = int(house.get("subway_distance") or 99999) <= val
        elif field == "no_agent_fee":
            matched = "房东直租" in tags
        elif field == "payment_method":
            matched = val in tags
        elif field == "deposit_type":
            matched = val in tags
        elif field == "required_utilities":
            for t in val or []:
                if t in tags:
                    score += 1
            continue
        elif field == "required_nearby":
            for t in val or []:
                if t in tags:
                    score += 1
            continue
        else:
            matched = val in tags
        if matched:
            score += 1
    return score


# 硬约束 tag 单值字段
_TAG_HARD_FIELDS = (
    "pet_policy", "viewing_method", "viewing_time", "lease_flexibility",
    "termination_sublet", "parking_type", "security_requirement",
    "property_management", "environment_preference", "house_feature", "landlord_contract",
)
# 噪音等级：安静 = 排除 吵闹/临街（若房源有 hidden_noise_level）
_NOISY_LEVELS = frozenset({"吵闹", "临街"})


def post_filter_and_rank(items: list[dict], prefs: UserPreferences) -> list[dict]:
    """本地硬约束过滤 + 软约束评分 + 排序。subway_line 包含匹配；floor_pref/noise 仅本地。"""
    soft = set(prefs.soft_constraint_keys or [])
    filtered: list[dict] = []
    for h in items:
        house_tags = set(h.get("tags") or [])
        if prefs.subway_line and "subway_line" not in soft:
            if prefs.subway_line not in (h.get("subway") or ""):
                continue
        if prefs.floor_pref and "floor_pref" not in soft:
            if not _match_floor(h.get("floor", ""), prefs.floor_pref):
                continue
        if prefs.noise_preference == "安静":
            lvl = h.get("hidden_noise_level")
            if lvl in _NOISY_LEVELS:
                continue
        for f in _TAG_HARD_FIELDS:
            if f in soft:
                continue
            v = getattr(prefs, f, None)
            if v is not None and v not in house_tags:
                break
        else:
            if prefs.required_utilities and "required_utilities" not in soft:
                if not all(t in house_tags for t in prefs.required_utilities):
                    continue
            if prefs.required_nearby and "required_nearby" not in soft:
                if not all(t in house_tags for t in prefs.required_nearby):
                    continue
            if prefs.payment_method and "payment_method" not in soft:
                if prefs.payment_method not in house_tags:
                    continue
            if prefs.deposit_type and "deposit_type" not in soft:
                if prefs.deposit_type not in house_tags:
                    continue
            if prefs.no_agent_fee is True and "no_agent_fee" not in soft:
                if "房东直租" not in house_tags:
                    continue
            # API 级硬约束（landmark 通道未下推时在此补滤）
            if prefs.min_price is not None and int(h.get("price") or 0) < prefs.min_price:
                continue
            if prefs.max_price is not None and int(h.get("price") or 0) > prefs.max_price:
                continue
            if prefs.bedrooms is not None:
                want = [int(x.strip()) for x in prefs.bedrooms.split(",") if x.strip().isdigit()]
                if want and h.get("bedrooms") not in want:
                    continue
            # 未指定租住方式时默认按整租过滤
            if "rental_type" not in soft:
                effective_rental = prefs.rental_type or "整租"
                if h.get("rental_type") != effective_rental:
                    continue
            if prefs.decoration and "decoration" not in soft:
                if _normalize_decoration(h.get("decoration")) != _normalize_decoration(prefs.decoration):
                    continue
            if prefs.orientation and "orientation" not in soft and (prefs.orientation or "") not in (h.get("orientation") or ""):
                continue
            if prefs.elevator is not None and "elevator" not in soft and bool(h.get("elevator")) != prefs.elevator:
                continue
            if prefs.max_subway_dist is not None and "max_subway_dist" not in soft:
                if int(h.get("subway_distance") or 99999) > prefs.max_subway_dist:
                    continue
            filtered.append(h)  # 通过所有硬约束

    scored = [(h, _calc_soft_score(h, prefs)) for h in filtered]
    has_soft = any(s > 0 for _, s in scored)
    sort_by = prefs.sort_by or "price"
    sort_order = prefs.sort_order or "asc"
    key_map = {"price": "price", "area": "area_sqm", "subway": "subway_distance"}
    key_f = key_map.get(sort_by, "price")
    reverse = sort_order == "desc"
    if has_soft:
        def _key(x):
            h, s = x
            v = float(h.get(key_f) or 0)
            return (-s, v if not reverse else -v)
        scored.sort(key=_key)
    else:
        scored.sort(key=lambda x: float(x[0].get(key_f) or 0), reverse=reverse)
    return [h for h, _ in scored]


async def search_by_landmark(
    client: httpx.AsyncClient,
    query: str,
    prefs: UserPreferences,
) -> dict:
    """地标链式调用：search_landmark → search_nearby_landmark。供测试或内部使用。"""
    try:
        lm_resp = await search_landmark(client, query=query)
        inner = lm_resp.get("data", lm_resp)
        if isinstance(inner, dict):
            items_lm = inner.get("items", [])
        else:
            items_lm = []
        if not items_lm:
            return {"total": 0, "items": [], "error": "未找到地标"}
        lm = items_lm[0]
        lm_id = lm.get("id") or lm.get("name") or query
        nearby_resp = await search_nearby_landmark(
            client,
            landmark_id=lm_id,
            max_distance=2000,
            listing_platform=prefs.listing_platform or "安居客",
        )
        data = nearby_resp.get("data", nearby_resp)
        if isinstance(data, dict):
            nearby_items = data.get("items", [])
        else:
            nearby_items = []
        return {"total": len(nearby_items), "items": nearby_items}
    except Exception as e:
        return {"total": 0, "items": [], "error": str(e)}


SUMMARY_FIELDS = (
    "house_id", "community", "district", "area", "price", "bedrooms", "area_sqm",
    "floor", "decoration", "orientation", "rental_type", "elevator",
    "subway_station", "subway_distance", "available_from", "tags",
)

# 跨平台搜索：三平台枚举，用于「搜三遍取并集」以兼容各平台 tags 差异
LISTING_PLATFORMS = ("链家", "安居客", "58同城")


def merge_cross_platform_houses(items_per_platform: list[list[dict]]) -> list[dict]:
    """将多平台搜索结果按 house_id 取并集：同一房源多条记录合并为一条，tags 取并集，价格取最低。"""
    by_id: dict[str, dict] = {}
    for platform_items in items_per_platform:
        for h in platform_items or []:
            hid = h.get("house_id")
            if not hid:
                continue
            if hid not in by_id:
                by_id[hid] = dict(h)
                by_id[hid]["tags"] = list(set(h.get("tags") or []))
                continue
            cur = by_id[hid]
            cur["tags"] = list(set(cur.get("tags") or []) | set(h.get("tags") or []))
            # 展示价取三平台最低，便于用户比价
            p_cur = int(cur.get("price") or 0)
            p_new = int(h.get("price") or 0)
            if p_new and (not p_cur or p_new < p_cur):
                cur["price"] = p_new
    return list(by_id.values())


async def search_by_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
) -> dict:
    """按当前 session 偏好搜索并返回 top 5 精简房源列表。需在 update_preferences 之后调用。
    未指定 listing_platform 时按「搜三遍取并集」做跨平台搜索，兼容各平台房屋 tags 差异。"""
    raw_items: list[dict] = []
    total_raw = 0
    has_districts_or_areas = bool(session_prefs.districts or session_prefs.areas)
    has_landmarks = bool(session_prefs.landmark_queries)
    single_platform = session_prefs.listing_platform

    if has_districts_or_areas or not has_landmarks:
        params = build_search_params(session_prefs)
        if not has_districts_or_areas:
            params.pop("district", None)
            params.pop("area", None)
        if single_platform:
            result = await search_houses(client, **params)
            if "error" not in result:
                raw_items.extend(result.get("items", []))
                total_raw += result.get("total", 0)
        else:
            # 跨平台：三平台各搜一遍，按 house_id 取并集（tags 合并，价格取最低）
            tasks = [
                search_houses(client, **{**params, "listing_platform": p})
                for p in LISTING_PLATFORMS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            per_platform: list[list[dict]] = []
            for r in results:
                if isinstance(r, Exception):
                    log_event("TOOL_API_CALL", "", {"error": str(r)})
                    log_event("TOOL_API_RESPONSE", "", {
                        "api": "/api/houses/by_platform",
                        "response": {"error": str(r)},
                    })
                    per_platform.append([])
                    continue
                if "error" not in r:
                    per_platform.append(r.get("items", []))
                else:
                    per_platform.append([])
            raw_items = merge_cross_platform_houses(per_platform)
            total_raw = len(raw_items)

    if has_landmarks:
        for q in session_prefs.landmark_queries or []:
            lm_resp = await search_landmark(client, query=q)
            inner = lm_resp.get("data", lm_resp)
            items_lm = (inner.get("items", []) if isinstance(inner, dict) else []) or []
            if not items_lm:
                continue
            lm = items_lm[0]
            lm_id = lm.get("id") or lm.get("name") or q
            if single_platform:
                near = await search_nearby_landmark(
                    client, landmark_id=lm_id, max_distance=2000,
                    listing_platform=single_platform,
                )
                data = near.get("data", near)
                near_items = (data.get("items", []) if isinstance(data, dict) else []) or []
                total_raw += len(near_items)
                seen_ids = {h["house_id"] for h in raw_items}
                for h in near_items:
                    if h.get("house_id") not in seen_ids:
                        seen_ids.add(h["house_id"])
                        raw_items.append(h)
            else:
                # 跨平台：地标附近三平台各搜一遍，取并集后按 house_id 合并再并入 raw_items
                near_tasks = [
                    search_nearby_landmark(
                        client, landmark_id=lm_id, max_distance=2000, listing_platform=p,
                    )
                    for p in LISTING_PLATFORMS
                ]
                near_results = await asyncio.gather(*near_tasks, return_exceptions=True)
                near_per_platform: list[list[dict]] = []
                for nr in near_results:
                    if isinstance(nr, Exception):
                        log_event("TOOL_API_RESPONSE", "", {
                            "api": "/api/houses/nearby",
                            "response": {"error": str(nr)},
                        })
                        near_per_platform.append([])
                        continue
                    data = nr.get("data", nr)
                    near_per_platform.append(
                        (data.get("items", []) if isinstance(data, dict) else []) or []
                    )
                merged_near = merge_cross_platform_houses(near_per_platform)
                total_raw += len(merged_near)
                seen_ids = {h["house_id"] for h in raw_items}
                for h in merged_near:
                    if h.get("house_id") not in seen_ids:
                        seen_ids.add(h["house_id"])
                        raw_items.append(h)

    filtered = post_filter_and_rank(raw_items, session_prefs)
    top5 = filtered[:5]
    scores: dict[str, int] = {}
    for h in top5:
        scores[h["house_id"]] = _calc_soft_score(h, session_prefs)
    slim = []
    for h in top5:
        row = {k: h[k] for k in SUMMARY_FIELDS if k in h}
        if scores.get(h["house_id"], 0) > 0:
            row["soft_score"] = scores[h["house_id"]]
        slim.append(row)

    return {
        "total_matched": len(filtered),
        "total_raw": total_raw,
        "items": slim,
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
                        "description": "整租或合租。未明确说明时默认整租；若预算约2000/室且用户提到两居、三居→视为整租；「一个人住/自己住」→整租；「合租/找室友/有室友」→合租；「单间」→合租"
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
        log_event("TOOL_API_CALL", "", {
            "api": "/api/houses/by_platform",
            "params": dict(base_params),
        })

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

        ret = {"total": total, "items": all_items}
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/by_platform",
            "response": _response_for_log(ret),
        })
        return ret
    except Exception as e:
        err_resp = {"error": f"search_houses failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/by_platform",
            "response": err_resp,
        })
        return err_resp


# ── Task 3: get_house_detail ────────────────────────────────────────────────
async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        log_event("TOOL_API_CALL", "", {
            "api": f"/api/houses/{house_id}",
            "params": {"house_id": house_id},
        })
        resp = await client.get(f"/api/houses/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": f"/api/houses/{house_id}",
            "response": result,
        })
        return result
    except Exception as e:
        err_resp = {"error": f"get_house_detail failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": f"/api/houses/{house_id}",
            "response": err_resp,
        })
        return err_resp


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
        log_event("TOOL_API_CALL", "", {
            "api": "/api/landmarks/search",
            "params": dict(params),
        })

        # 地标接口不需要 X-User-ID
        resp = await client.get("/api/landmarks/search", params=params)
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/landmarks/search",
            "response": _response_for_log(result),
        })
        return result
    except Exception as e:
        err_resp = {"error": f"search_landmark failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/landmarks/search",
            "response": err_resp,
        })
        return err_resp


# ── Task 5: search_nearby_landmark ─────────────────────────────────────────
async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        log_event("TOOL_API_CALL", "", {
            "api": "/api/houses/nearby",
            "params": dict(params),
        })
        resp = await client.get(
            "/api/houses/nearby",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/nearby",
            "response": _response_for_log(result),
        })
        return result
    except Exception as e:
        err_resp = {"error": f"search_nearby_landmark failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/nearby",
            "response": err_resp,
        })
        return err_resp


# ── Task 6: get_nearby_amenities ────────────────────────────────────────────
async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        # FR16 要求 1000 米，覆盖 API 默认的 3000 米
        if "max_distance_m" not in params:
            params["max_distance_m"] = 1000
        log_event("TOOL_API_CALL", "", {
            "api": "/api/houses/nearby_landmarks",
            "params": dict(params),
        })
        resp = await client.get(
            "/api/houses/nearby_landmarks",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/nearby_landmarks",
            "response": _response_for_log(result),
        })
        return result
    except Exception as e:
        err_resp = {"error": f"get_nearby_amenities failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/nearby_landmarks",
            "response": err_resp,
        })
        return err_resp


# ── Task 7: execute_action ──────────────────────────────────────────────────
async def execute_action(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        action = kwargs.get("action", "")
        house_id = str(kwargs.get("house_id", ""))
        listing_platform = kwargs.get("listing_platform", "安居客")

        valid_actions = {"rent", "terminate", "offline"}
        if action not in valid_actions:
            return {"error": f"execute_action failed: unknown action {action}"}

        log_event("TOOL_API_CALL", "", {
            "api": f"/api/houses/{house_id}/{action}",
            "params": {"house_id": house_id, "action": action, "listing_platform": listing_platform},
        })
        resp = await client.post(
            f"/api/houses/{house_id}/{action}",
            params={"listing_platform": listing_platform},
            headers=_get_headers(),
        )
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": f"/api/houses/{house_id}/{action}",
            "response": result,
        })
        return result
    except Exception as e:
        err_resp = {"error": f"execute_action failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": f"/api/houses/{house_id}/{action}",
            "response": err_resp,
        })
        return err_resp


# ── get_houses_by_community ─────────────────────────────────────────────────
async def get_houses_by_community(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        log_event("TOOL_API_CALL", "", {
            "api": "/api/houses/by_community",
            "params": dict(params),
        })
        resp = await client.get("/api/houses/by_community", params=params, headers=_get_headers())
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/by_community",
            "response": _response_for_log(result),
        })
        return result
    except Exception as e:
        err_resp = {"error": f"get_houses_by_community failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": "/api/houses/by_community",
            "response": err_resp,
        })
        return err_resp


# ── get_house_listings ───────────────────────────────────────────────────────
async def get_house_listings(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        log_event("TOOL_API_CALL", "", {
            "api": f"/api/houses/listings/{house_id}",
            "params": {"house_id": house_id},
        })
        resp = await client.get(f"/api/houses/listings/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        result = resp.json()
        log_event("TOOL_API_RESPONSE", "", {
            "api": f"/api/houses/listings/{house_id}",
            "response": _response_for_log(result),
        })
        return result
    except Exception as e:
        err_resp = {"error": f"get_house_listings failed: {str(e)}"}
        log_event("TOOL_API_RESPONSE", "", {
            "api": f"/api/houses/listings/{house_id}",
            "response": err_resp,
        })
        return err_resp


# ── get_all_houses_for_debug / get_all_landmarks_for_debug：全生命周期单次查询，session 间复用 ──
PLATFORMS = ["链家", "安居客", "58同城"]

# 进程级缓存：全生命周期内只查一次，district/area/landmark 结果在 session 间复用
_debug_houses_cache: dict | None = None
_debug_landmarks_cache: dict | None = None
_debug_houses_lock = asyncio.Lock()
_debug_landmarks_lock = asyncio.Lock()


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
    """获取链家、安居客、58同城三个平台的全量房源，用于调试；全生命周期只查一次，结果在 session 间复用。"""
    global _debug_houses_cache
    async with _debug_houses_lock:
        if _debug_houses_cache is not None:
            return _debug_houses_cache
        tasks = [
            _fetch_all_houses_for_platform(client, platform) for platform in PLATFORMS
        ]
        results = await asyncio.gather(*tasks)
        _debug_houses_cache = {platform: r for platform, r in zip(PLATFORMS, results)}
        # 首次查询时构建并更新全局 area → district，供所有 session 复用
        all_items: list[dict] = []
        for platform_data in _debug_houses_cache.values():
            all_items.extend(platform_data.get("items", []))
        area_map = build_area_district_map(all_items)
        AREA_TO_DISTRICT.update(area_map)
        return _debug_houses_cache


async def get_all_landmarks_for_debug(client: httpx.AsyncClient) -> dict:
    """获取全量地标数据用于调试；全生命周期只查一次，结果在 session 间复用。"""
    global _debug_landmarks_cache
    async with _debug_landmarks_lock:
        if _debug_landmarks_cache is not None:
            return _debug_landmarks_cache
        try:
            resp = await client.get("/api/landmarks")
            resp.raise_for_status()
            inner = resp.json().get("data", resp.json())
            items = inner.get("items", [])
            _debug_landmarks_cache = {"total": len(items), "items": items}
        except Exception as e:
            _debug_landmarks_cache = {
                "error": f"get_all_landmarks_for_debug failed: {str(e)}",
                "total": 0,
                "items": [],
            }
        # 首次查询时构建并更新全局地标名称集合，供所有 session 复用
        LANDMARK_NAMES.update(build_landmark_names(_debug_landmarks_cache.get("items", [])))
        return _debug_landmarks_cache


# ── init_houses（Story 2.2 已实现，保持不变） ───────────────────────────────
async def init_houses(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.post("/api/houses/init", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"init_houses failed: {str(e)}"}
