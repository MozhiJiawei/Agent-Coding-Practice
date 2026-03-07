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
# 每次查询后端最多返回的房源数量
MAX_HOUSES_PER_QUERY = 200
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
    """提取并合并用户租房偏好到 session，并立即按当前偏好搜索，返回匹配的 top 5 房源（更新偏好 + 搜索一体）。"""
    # Step 0: 语义字段转换（近地铁、XX左右）
    if kwargs.get("near_subway") is True:
        session_prefs.sort_by = "subway"
        session_prefs.sort_order = "asc"
        if kwargs.get("near_subway_is_soft") is not True:
            session_prefs.max_subway_dist = 800
    if kwargs.get("price_around") is not None:
        x = int(kwargs["price_around"])
        session_prefs.min_price = int(round(x * 0.8))
        session_prefs.max_price = int(round(x * 1.2))
    if kwargs.get("area_around") is not None:
        x = int(kwargs["area_around"])
        session_prefs.min_area = int(round(x * 0.8))
        session_prefs.max_area = int(round(x * 1.2))

    # Step 1: xxx_is_soft → soft_constraint_keys
    soft_keys = list(session_prefs.soft_constraint_keys)
    for key, value in kwargs.items():
        if key.endswith("_is_soft"):
            field = key[: -len("_is_soft")]
            if field == "near_subway":
                field = "max_subway_dist"  # near_subway 软约束对应不下推/不按距离过滤
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
    skip = {k for k in kwargs if k.endswith("_is_soft")} | {
        "location", "clear_location", "near_subway", "near_subway_is_soft", "price_around", "area_around",
    }
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

    # 更新偏好后自动执行搜索，返回与 search 一致的结构（含 items）
    return await _search_after_preferences(client, session_prefs)


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
    if "rental_type" not in soft and prefs.rental_type is not None:
        params["rental_type"] = prefs.rental_type
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
        elif field == "parking_type":
            # 用户意图「有车位」时，露天车位、车库车位都算通过，软过滤加分
            if val == "有车位":
                matched = "露天车位" in tags or "车库车位" in tags
            else:
                matched = val in tags
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
            if v is not None:
                if f == "parking_type" and v == "有车位":
                    # 「有车位」：露天车位、车库车位都算通过
                    if "露天车位" not in house_tags and "车库车位" not in house_tags:
                        break
                elif v not in house_tags:
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
            if "rental_type" not in soft and prefs.rental_type is not None:
                if h.get("rental_type") != prefs.rental_type:
                    continue
            if prefs.decoration and "decoration" not in soft:
                if _normalize_decoration(h.get("decoration")) != _normalize_decoration(prefs.decoration):
                    continue
            if prefs.orientation and "orientation" not in soft and (prefs.orientation or "") not in (h.get("orientation") or ""):
                continue
            if prefs.elevator is not None and "elevator" not in soft and bool(h.get("elevator")) != prefs.elevator:
                continue
            if "max_subway_dist" not in soft and prefs.max_subway_dist is not None:
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


async def _search_after_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
) -> dict:
    """按当前 session 偏好搜索并返回 top 5 精简房源列表（内部用，由 update_preferences 调用）。
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
                    # log_event("TOOL_API_CALL", "", {"error": str(r)})
                    # log_event("TOOL_API_RESPONSE", "", {
                    #     "api": "/api/houses/by_platform",
                    #     "response": {"error": str(r)},
                    # })
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
                        # log_event("TOOL_API_RESPONSE", "", {
                        #     "api": "/api/houses/nearby",
                        #     "response": {"error": str(nr)},
                        # })
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

    raw_items = raw_items[:MAX_HOUSES_PER_QUERY]
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


async def search_by_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
) -> dict:
    """按当前 session 偏好搜索并返回 top 5 精简房源（供测试用，工具层已合并到 update_preferences）。"""
    return await _search_after_preferences(client, session_prefs)


# ── Story 8.1: 4 工具体系 TOOLS 列表（意图接口 v3：主 Agent 仅偏好键值，无 xxx_is_soft；软意图由编排层+子 Agent 注入）────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "更新用户租房偏好（用户最新一轮表达的内容）并立即按当前偏好搜索，返回匹配的 top 5 房源。找房、推荐、吐槽当前住房时均调用本工具，调用即会触发搜索。仅传用户本轮提到的偏好字段与取值，未提及的字段不传；用户说 N 左右可用 price_around/area_around，近地铁用 near_subway。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "位置：行政区/商圈/地标/地铁站/小区名，多位置用数组"
                                       "行政区集合：朝阳、西城、海淀、东城、丰台、昌平、房山、通州、大兴、顺义"
                    },
                    "clear_location": {
                        "type": "boolean",
                        "description": "true=清除之前位置（换XX看看/改到XX），默认 false"
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "最低月租金(元)"
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "最高月租金(元)；"
                    },
                    "bedrooms": {
                        "type": "string",
                        "description": "卧室数，如 \"1\" \"2\" \"2,3\""
                    },
                    "rental_type": {
                        "type": "string",
                        "enum": ["整租", "合租"],
                        "description": "整租或合租"
                    },
                    "decoration": {
                        "type": "string",
                        "enum": ["精装", "简装", "豪华", "毛坯", "空房"],
                        "description": "装修类型"
                    },
                    "elevator": {
                        "type": "boolean",
                        "description": "是否要求有电梯"
                    },
                    "orientation": {
                        "type": "string",
                        "enum": ["朝南", "朝北", "朝东", "朝西", "南北", "东西", "西北"],
                        "description": "朝向, 采光好时推断朝南"
                    },
                    "floor_pref": {
                        "type": "string",
                        "enum": ["低层", "中层", "高层"],
                        "description": "楼层偏好"
                    },
                    "min_area": {
                        "type": "integer",
                        "description": "最小面积(㎡)"
                    },
                    "max_area": {
                        "type": "integer",
                        "description": "最大面积(㎡)"
                    },
                    "price_around": {
                        "type": "integer",
                        "description": "月租金/预算/费用/价格「XX左右」时传中心值XX(元)"
                    },
                    "area_around": {
                        "type": "integer",
                        "description": "面积「XX左右」时传中心值XX(㎡)"
                    },
                    "max_subway_dist": {
                        "type": "integer",
                        "description": "地铁最大距离(米）"
                    },
                    "near_subway": {
                        "type": "boolean",
                        "description": "true=近地铁"
                    },
                    "subway_line": {
                        "type": "string",
                        "description": "地铁线路，如13号线"
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
                        "description": "挂牌平台"
                    },
                    "available_before": {
                        "type": "string",
                        "description": "可入住日期上限 YYYY-MM-DD"
                    },
                    "max_commute_minutes": {
                        "type": "integer",
                        "description": "到西二旗通勤上限(分钟)；仅通勤时只设此项勿推断 location"
                    },
                    "noise_preference": {
                        "type": "string",
                        "enum": ["安静"],
                        "description": "噪音偏好，安静→\"安静\""
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["price", "area", "subway"],
                        "description": "排序字段 price/area/subway"
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "排序方向 asc/desc"
                    },
                    "no_agent_fee": {
                        "type": "boolean",
                        "description": "true=免中介费/房东直租"
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["月付", "季付", "半年付", "年付"],
                        "description": "付款周期(与租期 lease_flexibility 区分)"
                    },
                    "deposit_type": {
                        "type": "string",
                        "enum": ["押一", "押二", "押三"],
                        "description": "押金偏好"
                    },
                    "pet_policy": {
                        "type": "string",
                        "enum": ["可养猫", "可养狗", "可养宠物", "不可养宠物", "仅限小型犬", "可养宠物需宠物押金"],
                        "description": "宠物政策"
                    },
                    "viewing_method": {
                        "type": "string",
                        "enum": ["仅线下看房", "仅线上VR看房", "仅线上AR看房", "仅线上图片看房", "线下+线上"],
                        "description": "看房方式"
                    },
                    "viewing_time": {
                        "type": "string",
                        "enum": ["全天可看房", "仅周末看房", "仅工作日看房", "工作日9-18点", "工作日14-18点", "工作日9-12点", "周末9-18点", "周末14-18点", "周末9-12点"],
                        "description": "看房时间"
                    },
                    "lease_flexibility": {
                        "type": "string",
                        "enum": ["可月租", "可租2个月", "可租3个月", "可租4个月", "可租5个月", "可半年租", "可年租", "仅接受年租"],
                        "description": "租期长短(月付用 payment_method)"
                    },
                    "required_utilities": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["包水电费", "免水电费", "免宽带费", "包宽带", "包物业费", "免物业费", "包车位", "免车位费", "包取暖费", "免取暖费"]},
                        "description": "须含费用项(包=含在租金内)，如包宽带/包物业费"
                    },
                    "termination_sublet": {
                        "type": "string",
                        "enum": ["提前退租可协商", "提前退租扣押金", "经同意可转租", "不可转租"],
                        "description": "退租/转租政策"
                    },
                    "parking_type": {
                        "type": "string",
                        "enum": ["有车位", "车库车位", "露天车位", "无车位"],
                        "description": "车位类型(免费车位用 required_utilities)"
                    },
                    "security_requirement": {
                        "type": "string",
                        "enum": ["24小时保安", "门禁刷卡", "门禁形同虚设", "无门禁"],
                        "description": "安保/门禁"
                    },
                    "property_management": {
                        "type": "string",
                        "enum": ["物业管理到位", "物业管理差"],
                        "description": "物业管理"
                    },
                    "environment_preference": {
                        "type": "string",
                        "enum": ["绿化好环境佳", "绿化少环境一般"],
                        "description": "小区环境"
                    },
                    "required_nearby": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["近公园", "近学校", "近菜市场", "近银行", "近医院", "近餐饮", "近健身房", "近警察局", "近商超", "近加油站"]},
                        "description": "周边配套，用户提及时加入"
                    },
                    "tag_preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "软加分标签，如精装/朝南/有电梯"
                    },
                    "house_feature": {
                        "type": "string",
                        "enum": ["采光好", "南北通透", "高性价比"],
                        "description": "房屋特点"
                    },
                    "landlord_contract": {
                        "type": "string",
                        "enum": ["合同规范条款清晰", "合同不规范", "房东好沟通", "房东不配合", "房东难联系"],
                        "description": "合同/房东"
                    }
                },
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

# 意图接口 v3：支持软约束的字段名（子 Agent 输出的 soft_fields 仅限此集合，且须在 extracted_preferences 中出现）
SOFT_CONSTRAINT_FIELD_NAMES = frozenset({
    "decoration", "elevator", "orientation", "floor_pref", "rental_type", "max_subway_dist", "near_subway",
    "pet_policy", "viewing_method", "viewing_time", "lease_flexibility", "termination_sublet", "parking_type",
    "security_requirement", "property_management", "environment_preference", "house_feature", "landlord_contract",
    "required_utilities", "required_nearby", "payment_method", "deposit_type", "no_agent_fee",
})

# 规则提取字段：以下字段由 extract_preferences_by_rules 从用户原文中匹配，主 Agent schema 中不暴露
RULE_EXTRACTED_FIELD_NAMES = frozenset({
    "listing_platform", "landlord_contract", "house_feature", "tag_preferences", "required_nearby",
    "environment_preference", "property_management", "security_requirement", "parking_type", "termination_sublet",
    "required_utilities", "lease_flexibility", "viewing_time", "viewing_method", "pet_policy", "deposit_type",
    "payment_method", "no_agent_fee", "utilities_type",
})


def extract_preferences_by_rules(user_message: str) -> dict:
    """从用户本轮原文中按关键词规则抽取偏好字段（挂牌平台、付款/押金/宠物等），仅返回能匹配到的键值对。不做软/硬判断。"""
    if not (user_message and user_message.strip()):
        return {}
    msg = user_message.strip()
    out: dict = {}

    # listing_platform（挂牌平台，先匹配的优先）
    if "链家" in msg:
        out["listing_platform"] = "链家"
    elif "安居客" in msg:
        out["listing_platform"] = "安居客"
    elif "58同城" in msg or ("58" in msg and "同城" in msg):
        out["listing_platform"] = "58同城"

    # no_agent_fee
    if any(k in msg for k in ("房东直租", "免中介", "无中介", "不想交中介费", "不通过中介", "不想通过中介", "能省一点是一点")):
        out["no_agent_fee"] = True

    # payment_method（优先匹配更长/更具体的）
    if "半年付" in msg or "半年" in msg and "付" in msg:
        out["payment_method"] = "半年付"
    elif "季付" in msg or "按季度" in msg:
        out["payment_method"] = "季付"
    elif "年付" in msg and "仅接受" not in msg:
        out["payment_method"] = "年付"
    elif any(k in msg for k in ("月付", "能月付", "月付最好", "可以月付", "希望能月付", "押一付一", "按月付")):
        out["payment_method"] = "月付"

    # deposit_type
    if "押二" in msg or "两个月押金" in msg or "两个月押" in msg or "接受押二" in msg:
        out["deposit_type"] = "押二"
    elif "押三" in msg:
        out["deposit_type"] = "押三"
    elif any(k in msg for k in ("押一付一", "押一", "只押一个月", "押金只押一个月")):
        out["deposit_type"] = "押一"

    # pet_policy（优先级：小型犬 > 养狗 > 养猫 > 不养 > 可养宠物）
    if "小型犬" in msg or "小型狗" in msg:
        out["pet_policy"] = "仅限小型犬"
    elif any(k in msg for k in ("养狗", "能养狗", "金毛", "遛狗")):
        out["pet_policy"] = "可养狗"
    elif any(k in msg for k in ("养猫", "能养猫", "有猫", "养了只猫")):
        out["pet_policy"] = "可养猫"
    elif any(k in msg for k in ("不养宠物", "不能养宠物", "但是不养宠物")):
        out["pet_policy"] = "不可养宠物"
    elif any(k in msg for k in ("养宠物", "可养宠物", "允许宠物", "仓鼠", "房东允许")):
        out["pet_policy"] = "可养宠物"

    # viewing_method
    if "线下或线上" in msg or "线下+线上" in msg or "都行" in msg and "看房" in msg:
        out["viewing_method"] = "线下+线上"
    elif "线上AR" in msg or "AR看房" in msg:
        out["viewing_method"] = "仅线上AR看房"
    elif "线上图片" in msg or "图片看房" in msg:
        out["viewing_method"] = "仅线上图片看房"
    elif "实地看房" in msg or "线下看房" in msg or "去实地" in msg or "实地看看房" in msg:
        out["viewing_method"] = "仅线下看房"
    elif "VR看房" in msg or "线上VR" in msg or "不用跑现场" in msg:
        out["viewing_method"] = "仅线上VR看房"

    # viewing_time
    if ("全天" in msg and "看房" in msg) or "随时可以看房" in msg or "全天能约" in msg:
        out["viewing_time"] = "全天可看房"
    elif "工作日14" in msg or "下午能看房" in msg or ("下午才起床" in msg and "看房" in msg):
        out["viewing_time"] = "工作日14-18点"
    elif "工作日9" in msg or ("工作日白天" in msg and "看房" in msg):
        out["viewing_time"] = "工作日9-18点"
    elif "仅周末看房" in msg or "周末看房" in msg or "只能周末" in msg or ("只有周末" in msg and "看房" in msg) or "周末方便" in msg:
        out["viewing_time"] = "仅周末看房"

    # lease_flexibility
    if "可年租" in msg or "年租" in msg and "仅接受" in msg:
        out["lease_flexibility"] = "仅接受年租"
    elif "可年租" in msg or "年租" in msg:
        out["lease_flexibility"] = "可年租"
    elif "可半年租" in msg:
        out["lease_flexibility"] = "可半年租"
    elif "可租3个月" in msg or "最多租三个月" in msg or "租三个月" in msg or "我最多租三个月" in msg:
        out["lease_flexibility"] = "可租3个月"
    elif "可租2个月" in msg or "只租两个月" in msg:
        out["lease_flexibility"] = "可租2个月"
    elif "可月租" in msg or "短租" in msg or "只住一个多月" in msg:
        out["lease_flexibility"] = "可月租"

    # required_utilities（数组，多关键词合并）
    ru: list[str] = []
    if "包宽带" in msg or "网费包含" in msg or "宽带包" in msg or "网费能直接包含" in msg:
        ru.append("包宽带")
    if "包水电" in msg or "水电包" in msg or "包在房租里" in msg and ("水电" in msg or "杂费" in msg):
        ru.append("包水电费")
    if "包物业" in msg or "物业费包" in msg or "物业费能包" in msg:
        ru.append("包物业费")
    if "免车位费" in msg or "免费车位" in msg or "车位最好免费" in msg:
        ru.append("免车位费")
    if "包车位" in msg or "车位包在房租" in msg:
        ru.append("包车位")
    if ru:
        out["required_utilities"] = list(dict.fromkeys(ru))

    # required_nearby（数组）
    rn: list[str] = []
    if "近公园" in msg or "附近有公园" in msg or "公园" in msg and ("附近" in msg or "遛狗" in msg or "遛弯" in msg):
        rn.append("近公园")
    if "近医院" in msg or "离医院近" in msg or "医院近" in msg or ("复查" in msg and "医院" in msg) or "三甲医院" in msg or "离医院近点" in msg:
        rn.append("近医院")
    if "近菜市场" in msg or "菜市场" in msg and "附近" in msg or "买菜" in msg:
        rn.append("近菜市场")
    if "近餐饮" in msg or "24小时有吃的" in msg or "有吃的" in msg or "餐馆" in msg or "吃饭" in msg and "附近" in msg or "便利店" in msg and "吃饭" in msg:
        rn.append("近餐饮")
    if "近健身房" in msg or "健身" in msg and "附近" in msg:
        rn.append("近健身房")
    if "近学校" in msg or "学校附近" in msg or "高校附近" in msg:
        rn.append("近学校")
    if "近商超" in msg or "便利店" in msg:
        rn.append("近商超")
    if rn:
        out["required_nearby"] = list(dict.fromkeys(rn))

    # parking_type
    if "车库" in msg or "地下车库" in msg:
        out["parking_type"] = "车库车位"
    elif "有车位" in msg or "小区有车位" in msg:
        out["parking_type"] = "有车位"

    # termination_sublet
    if "协商退租" in msg or "商量退租" in msg or "可以协商退租" in msg or "提前退租可协商" in msg:
        out["termination_sublet"] = "提前退租可协商"
    if "可转租" in msg or "经同意可转租" in msg:
        out["termination_sublet"] = "经同意可转租"

    # security_requirement
    if "24小时保安" in msg:
        out["security_requirement"] = "24小时保安"
    elif "门禁" in msg and "形同虚设" not in msg and "无门禁" not in msg:
        out["security_requirement"] = "门禁刷卡"

    # property_management
    if "物业到位" in msg or "物业管理到位" in msg or "物业好" in msg:
        out["property_management"] = "物业管理到位"
    elif "物业管理差" in msg:
        out["property_management"] = "物业管理差"

    # environment_preference
    if "绿化好" in msg or "环境好" in msg or "小区环境" in msg and ("好" in msg or "适合跑步" in msg):
        out["environment_preference"] = "绿化好环境佳"
    elif "绿化少" in msg or "环境一般" in msg:
        out["environment_preference"] = "绿化少环境一般"

    # house_feature
    if "高性价比" in msg or "性价比高" in msg:
        out["house_feature"] = "高性价比"
    elif "南北通透" in msg:
        out["house_feature"] = "南北通透"
    elif "采光好" in msg:
        out["house_feature"] = "采光好"

    # landlord_contract
    if "房东好沟通" in msg or "好沟通的房东" in msg:
        out["landlord_contract"] = "房东好沟通"

    # utilities_type
    if "民水民电" in msg:
        out["utilities_type"] = "民水民电"
    elif "商水商电" in msg:
        out["utilities_type"] = "商水商电"

    # tag_preferences（软偏好标签，与 decoration/orientation 等区分：规则层只做关键词→标签值）
    tags: list[str] = []
    if "朝南" in msg and "朝南" not in (out.get("house_feature") or ""):
        tags.append("朝南")
    if "精装" in msg or "精装修" in msg:
        tags.append("精装")
    if "有电梯" in msg:
        tags.append("有电梯")
    if tags:
        out["tag_preferences"] = list(dict.fromkeys(tags))

    return out


# 主 Agent 用 TOOLS（v3）：update_preferences 中移除规则提取的 19 个字段与所有 xxx_is_soft，主 Agent 只做其余偏好抽取
def _build_tools_main() -> list[dict]:
    import copy
    tools_main = copy.deepcopy(TOOLS)
    for t in tools_main:
        if t.get("type") == "function" and t.get("function", {}).get("name") == "update_preferences":
            props = (t["function"].get("parameters") or {}).get("properties") or {}
            for key in list(props.keys()):
                if key in RULE_EXTRACTED_FIELD_NAMES or key.endswith("_is_soft"):
                    props.pop(key, None)
            break
    return tools_main


TOOLS_MAIN: list[dict] = _build_tools_main()


# ── Task 2: search_houses ───────────────────────────────────────────────────
async def search_houses(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        base_params: dict = {k: v for k, v in kwargs.items() if v is not None}
        base_params["page"] = 1
        base_params["page_size"] = min(
            int(base_params.get("page_size", MAX_HOUSES_PER_QUERY)),
            MAX_HOUSES_PER_QUERY,
        )
        # log_event("TOOL_API_CALL", "", {
        #     "api": "/api/houses/by_platform",
        #     "params": dict(base_params),
        # })

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
        while len(all_items) < total and len(all_items) < MAX_HOUSES_PER_QUERY:
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

        all_items = all_items[:MAX_HOUSES_PER_QUERY]
        ret = {"total": total, "items": all_items}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/by_platform",
        #     "response": _response_for_log(ret),
        # })
        return ret
    except Exception as e:
        err_resp = {"error": f"search_houses failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/by_platform",
        #     "response": err_resp,
        # })
        return err_resp


# ── Task 3: get_house_detail ────────────────────────────────────────────────
async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        # log_event("TOOL_API_CALL", "", {
        #     "api": f"/api/houses/{house_id}",
        #     "params": {"house_id": house_id},
        # })
        resp = await client.get(f"/api/houses/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        result = resp.json()
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": f"/api/houses/{house_id}",
        #     "response": result,
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"get_house_detail failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": f"/api/houses/{house_id}",
        #     "response": err_resp,
        # })
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
        # log_event("TOOL_API_CALL", "", {
        #     "api": "/api/landmarks/search",
        #     "params": dict(params),
        # })

        # 地标接口不需要 X-User-ID
        resp = await client.get("/api/landmarks/search", params=params)
        resp.raise_for_status()
        result = resp.json()
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/landmarks/search",
        #     "response": _response_for_log(result),
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"search_landmark failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/landmarks/search",
        #     "response": err_resp,
        # })
        return err_resp


# ── Task 5: search_nearby_landmark ─────────────────────────────────────────
async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        params["page_size"] = min(
            int(params.get("page_size", MAX_HOUSES_PER_QUERY)),
            MAX_HOUSES_PER_QUERY,
        )
        # log_event("TOOL_API_CALL", "", {
        #     "api": "/api/houses/nearby",
        #     "params": dict(params),
        # })
        resp = await client.get(
            "/api/houses/nearby",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        result = resp.json()
        inner = result.get("data", result)
        if isinstance(inner, dict) and "items" in inner:
            items = inner.get("items", [])
            if len(items) > MAX_HOUSES_PER_QUERY:
                inner["items"] = items[:MAX_HOUSES_PER_QUERY]
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/nearby",
        #     "response": _response_for_log(result),
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"search_nearby_landmark failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/nearby",
        #     "response": err_resp,
        # })
        return err_resp


# ── Task 6: get_nearby_amenities ────────────────────────────────────────────
async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        # FR16 要求 1000 米，覆盖 API 默认的 3000 米
        if "max_distance_m" not in params:
            params["max_distance_m"] = 1000
        # log_event("TOOL_API_CALL", "", {
        #     "api": "/api/houses/nearby_landmarks",
        #     "params": dict(params),
        # })
        resp = await client.get(
            "/api/houses/nearby_landmarks",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        result = resp.json()
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/nearby_landmarks",
        #     "response": _response_for_log(result),
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"get_nearby_amenities failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/nearby_landmarks",
        #     "response": err_resp,
        # })
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

        # log_event("TOOL_API_CALL", "", {
        #     "api": f"/api/houses/{house_id}/{action}",
        #     "params": {"house_id": house_id, "action": action, "listing_platform": listing_platform},
        # })
        resp = await client.post(
            f"/api/houses/{house_id}/{action}",
            params={"listing_platform": listing_platform},
            headers=_get_headers(),
        )
        resp.raise_for_status()
        result = resp.json()
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": f"/api/houses/{house_id}/{action}",
        #     "response": result,
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"execute_action failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": f"/api/houses/{house_id}/{action}",
        #     "response": err_resp,
        # })
        return err_resp


# ── get_houses_by_community ─────────────────────────────────────────────────
async def get_houses_by_community(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        # log_event("TOOL_API_CALL", "", {
        #     "api": "/api/houses/by_community",
        #     "params": dict(params),
        # })
        resp = await client.get("/api/houses/by_community", params=params, headers=_get_headers())
        resp.raise_for_status()
        result = resp.json()
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/by_community",
        #     "response": _response_for_log(result),
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"get_houses_by_community failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": "/api/houses/by_community",
        #     "response": err_resp,
        # })
        return err_resp


# ── get_house_listings ───────────────────────────────────────────────────────
async def get_house_listings(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        # log_event("TOOL_API_CALL", "", {
        #     "api": f"/api/houses/listings/{house_id}",
        #     "params": {"house_id": house_id},
        # })
        resp = await client.get(f"/api/houses/listings/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        result = resp.json()
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": f"/api/houses/listings/{house_id}",
        #     "response": _response_for_log(result),
        # })
        return result
    except Exception as e:
        err_resp = {"error": f"get_house_listings failed: {str(e)}"}
        # log_event("TOOL_API_RESPONSE", "", {
        #     "api": f"/api/houses/listings/{house_id}",
        #     "response": err_resp,
        # })
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
