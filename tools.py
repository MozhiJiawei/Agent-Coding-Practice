import asyncio
import os
from typing import Optional
import httpx
from pydantic import BaseModel

# 模块顶层常量（必须在模块加载时读取一次）
# 支持环境变量覆盖，与 debug_init_houses.py 一致；tools 不创建 client，client 由 main 传入且已设置 trust_env=False 不走代理
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
USER_ID = os.environ["USER_ID"]  # 模块加载时读取，不在函数内读取
MAX_PAGES = 5


def _get_headers() -> dict:
    return {"X-User-ID": USER_ID.encode("utf-8")}


# ── Story 8.1: UserPreferences 数据模型 ─────────────────────────────────────

DISTRICTS = {"海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"}

# 模块级全局映射表，由 build_area_district_map 填充（启动时由 main.py 调用）
AREA_TO_DISTRICT: dict[str, str] = {}


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
    near_subway: Optional[bool] = None
    listing_platform: Optional[str] = None
    available_before: Optional[str] = None
    max_commute_minutes: Optional[int] = None

    # ── 软偏好 ──
    noise_preference: Optional[str] = None
    orientation: Optional[str] = None
    floor_pref: Optional[str] = None
    no_agent_fee: Optional[bool] = None
    payment_method: Optional[str] = None

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


def resolve_location(location: str) -> dict:
    """将 LLM 输入的位置路由为 district / area / landmark_query。

    路由规则（优先级从高到低）：
    1. 去掉"区"后缀后，若在 DISTRICTS 中 → {"district": "XX"}
    2. 若在 AREA_TO_DISTRICT 中 → {"area": "XX", "district": "YY"}
    3. 以"附近"结尾 → {"landmark_query": "XX"} （去掉"附近"）
    4. 其他 → {"landmark_query": location}
    """
    # 规则1: 区名（支持"海淀"和"海淀区"两种写法）
    stripped = location.removesuffix("区")
    if stripped in DISTRICTS:
        return {"district": stripped}

    # 规则2: 商圈（依赖 AREA_TO_DISTRICT 映射）
    if location in AREA_TO_DISTRICT:
        return {"area": location, "district": AREA_TO_DISTRICT[location]}

    # 规则3: 地标（"XX附近"）
    if location.endswith("附近"):
        landmark = location.removesuffix("附近")
        return {"landmark_query": landmark}

    # 规则4: 未知，作为地标查询
    return {"landmark_query": location}


async def update_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
    **kwargs,
) -> dict:
    """合并 LLM 提取的偏好参数到 session，调用 resolve_location 路由位置，返回当前偏好摘要。

    Story 8.1：本函数暂不触发自动搜索，仅返回偏好摘要。
    自动搜索逻辑在 Story 8.2 实现。
    """
    # 处理 clear_location：清除历史位置相关字段
    clear = kwargs.pop("clear_location", False)
    if clear:
        session_prefs.location = None
        session_prefs.districts = None
        session_prefs.areas = None
        session_prefs.landmark_queries = None

    # 处理 location 字段：累加并路由
    new_locations: list[str] = kwargs.pop("location", None) or []
    if new_locations:
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
                # 商圈路由：写入 areas，并将对应 district 也写入 districts
                new_areas.append(routed["area"])
                if "district" in routed:
                    new_districts.append(routed["district"])
            elif "district" in routed:
                # 纯区名路由
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
        "near_subway", "listing_platform", "available_before", "max_commute_minutes",
        "noise_preference", "orientation", "floor_pref", "no_agent_fee", "payment_method",
    }
    for field, value in kwargs.items():
        if field in updatable_fields and value is not None:
            setattr(session_prefs, field, value)

    # 构建并返回偏好摘要
    summary = session_prefs.model_dump(exclude_none=True, exclude={"clear_location"})
    return {"preferences": summary, "status": "updated"}


# ── Story 8.1: 4 工具体系 TOOLS 列表 ────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "提取或更新用户的租房偏好。调用后系统自动搜索并返回匹配房源。每轮只需提取本轮新增/变更的偏好，系统自动与历史偏好合并。",
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
                    "rental_type": {"type": "string", "description": "整租 或 合租"},
                    "decoration": {"type": "string", "description": "精装/简装/豪华/毛坯"},
                    "elevator": {"type": "boolean", "description": "是否需要电梯"},
                    "min_area": {"type": "integer", "description": "最小面积（平米）"},
                    "near_subway": {"type": "boolean", "description": "是否要求近地铁"},
                    "subway_line": {"type": "string", "description": "地铁线路，如 13号线"},
                    "utilities_type": {"type": "string", "description": "水电类型，如 民水民电"},
                    "listing_platform": {"type": "string", "description": "挂牌平台：链家/安居客/58同城"},
                    "available_before": {"type": "string", "description": "可入住日期上限，YYYY-MM-DD"},
                    "max_commute_minutes": {"type": "integer", "description": "到西二旗通勤上限（分钟）"},
                    "noise_preference": {"type": "string", "description": "噪音偏好，如 安静"},
                    "orientation": {"type": "string", "description": "朝向偏好，如 朝南"}
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
        while len(all_items) < total and page <= MAX_PAGES:
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
