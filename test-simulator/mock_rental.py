"""Mock 租房 API FastAPI 应用 — 15 个程序化端点（Story 5.2）"""
from __future__ import annotations

import math
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import SimulatorConfig

# ── 平台定价系数 ──────────────────────────────────────────────────────────────
PLATFORM_FACTORS: dict[str, float] = {
    "安居客": 1.00,
    "链家": 0.92,
    "58同城": 0.78,
}
VALID_PLATFORMS = set(PLATFORM_FACTORS.keys())
DEFAULT_PLATFORM = "安居客"


# ── 标准响应工具 ──────────────────────────────────────────────────────────────

def _ok(data) -> JSONResponse:
    return JSONResponse({"code": 0, "message": "success", "data": data})


def _err400(msg: str) -> JSONResponse:
    return JSONResponse({"code": 400, "message": msg})


def _err404(msg: str) -> JSONResponse:
    return JSONResponse({"code": 404, "message": msg})


# ── Haversine 距离（米）────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两经纬度点的直线距离（米）。"""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── 平台数据生成 ──────────────────────────────────────────────────────────────

def _house_num(house_id: str) -> int:
    """从 house_id 提取数字部分：HF_001 → 1。"""
    return int(house_id.split("_")[-1])


def _listing_url(house_id: str, platform: str) -> str:
    n = _house_num(house_id)
    if platform == "链家":
        return f"https://bj.lianjia.com/zufang/BJ{1_000_000 + n}.html"
    if platform == "58同城":
        return f"https://bj.58.com/zufang/pn{2_000_000 + n}.shtml"
    return "https://bj.zu.anjuke.com/"


def _apply_platform(house: dict, platform: str) -> dict:
    """返回应用平台定价后的房源副本（不修改原始数据）。"""
    factor = PLATFORM_FACTORS.get(platform, 1.00)
    result = dict(house)
    result["listing_platform"] = platform
    result["listing_url"] = _listing_url(house["house_id"], platform)
    result["price"] = int(house["price"] * factor)
    return result


# ── 分页辅助 ──────────────────────────────────────────────────────────────────

def _parse_int(val, default: int) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _parse_float(val, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _paginate(items: list, page: int, page_size: int) -> list:
    start = (page - 1) * page_size
    return items[start: start + page_size]


# ── MockState ─────────────────────────────────────────────────────────────────

class MockState:
    """在内存中维护房源状态，支持重置和状态变更。无模块级可变全局状态。"""

    def __init__(self, fixtures_houses: list[dict]) -> None:
        self.houses: dict[str, dict] = {}
        for h in fixtures_houses:
            entry = dict(h)
            entry["_initial_status"] = h["status"]
            self.houses[h["house_id"]] = entry

    def init(self) -> None:
        """将所有房源状态重置为 fixture 初始状态。"""
        for h in self.houses.values():
            h["status"] = h["_initial_status"]

    def update_status(self, house_id: str, new_status: str) -> dict | None:
        """更新指定房源状态，返回更新后的房源（不含内部字段）或 None。"""
        h = self.houses.get(house_id)
        if h is None:
            return None
        h["status"] = new_status
        return {k: v for k, v in h.items() if not k.startswith("_")}

    def get_house(self, house_id: str) -> dict | None:
        h = self.houses.get(house_id)
        if h is None:
            return None
        return {k: v for k, v in h.items() if not k.startswith("_")}

    def all_houses(self) -> list[dict]:
        return [{k: v for k, v in h.items() if not k.startswith("_")} for h in self.houses.values()]


# ── 地标辅助 ──────────────────────────────────────────────────────────────────

def _landmark_view(lm: dict) -> dict:
    """返回地标的完整视图（透传所有 fixture 字段，包括 details）。"""
    return dict(lm)


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def create_mock_rental_app(
    config: SimulatorConfig,
    fixtures: dict,
) -> FastAPI:
    """
    创建并返回 Mock Rental FastAPI 应用。
    fixtures: {"landmarks": [...], "houses": [...]}（来自 load_fixtures）
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mock_state = MockState(fixtures["houses"])
        app.state.landmarks: list[dict] = fixtures["landmarks"]
        yield

    app = FastAPI(title="Mock Rental API", lifespan=lifespan)

    # ── 校验辅助（闭包访问 app.state）────────────────────────────────────────

    def _check_user_id(request: Request) -> Optional[str]:
        """返回 X-User-ID 或 None（需调用方返回 400）。"""
        return request.headers.get("X-User-ID")

    # ══════════════════════════════════════════════════════════════════════════
    # 地标端点（5 个）— 无 X-User-ID 校验
    # ══════════════════════════════════════════════════════════════════════════

    @app.get("/api/landmarks")
    async def get_landmarks(
        request: Request,
        category: Optional[str] = None,
        district: Optional[str] = None,
    ):
        """获取地标列表，支持 category、district 同时筛选（取交集）。"""
        landmarks: list[dict] = request.app.state.landmarks
        result = landmarks
        if category:
            result = [lm for lm in result if lm.get("category") == category]
        if district:
            result = [lm for lm in result if lm.get("district") == district]
        items = [_landmark_view(lm) for lm in result]
        return _ok({"total": len(items), "items": items})

    @app.get("/api/landmarks/name/{name}")
    async def get_landmark_by_name(request: Request, name: str):
        """按名称精确查询地标。"""
        landmarks: list[dict] = request.app.state.landmarks
        for lm in landmarks:
            if lm["name"] == name:
                return _ok(_landmark_view(lm))
        return _err404(f"未找到地标：{name}")

    @app.get("/api/landmarks/search")
    async def search_landmarks(
        request: Request,
        q: str,
        category: Optional[str] = None,
        district: Optional[str] = None,
    ):
        """关键词模糊搜索地标，q 必填。支持 category、district 同时筛选（取交集）。"""
        landmarks: list[dict] = request.app.state.landmarks
        result = [lm for lm in landmarks if q in lm["name"]]
        if category:
            result = [lm for lm in result if lm.get("category") == category]
        if district:
            result = [lm for lm in result if lm.get("district") == district]
        items = [_landmark_view(lm) for lm in result]
        return _ok({"total": len(items), "items": items})

    @app.get("/api/landmarks/stats")
    async def get_landmark_stats(request: Request):
        """获取地标统计信息（总数、按类别/行政区分布）。"""
        landmarks: list[dict] = request.app.state.landmarks
        by_category: dict[str, int] = {}
        by_district: dict[str, int] = {}
        for lm in landmarks:
            cat = lm.get("category", "")
            by_category[cat] = by_category.get(cat, 0) + 1
            dist = lm.get("district", "")
            by_district[dist] = by_district.get(dist, 0) + 1
        return _ok({
            "total": len(landmarks),
            "by_category": by_category,
            "by_district": by_district,
        })

    @app.get("/api/landmarks/{landmark_id}")
    async def get_landmark_by_id(request: Request, landmark_id: str):
        """按地标 id 查询地标详情。"""
        landmarks: list[dict] = request.app.state.landmarks
        for lm in landmarks:
            if lm["id"] == landmark_id:
                return _ok(_landmark_view(lm))
        return _err404(f"未找到地标 {landmark_id}")

    # ══════════════════════════════════════════════════════════════════════════
    # 房源查询端点（7 个）— 需 X-User-ID
    # ══════════════════════════════════════════════════════════════════════════

    @app.get("/api/houses/stats")
    async def get_house_stats(request: Request):
        """获取房源统计信息（总套数、按状态/行政区/户型分布、价格区间）。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        mock_state: MockState = request.app.state.mock_state
        all_h = mock_state.all_houses()
        by_status: dict[str, int] = {}
        by_district: dict[str, int] = {}
        by_bedrooms: dict[str, int] = {}
        prices: list[int] = []
        for h in all_h:
            s = h.get("status", "")
            by_status[s] = by_status.get(s, 0) + 1
            d = h.get("district", "")
            by_district[d] = by_district.get(d, 0) + 1
            b = str(h.get("bedrooms", ""))
            by_bedrooms[b] = by_bedrooms.get(b, 0) + 1
            if "price" in h:
                prices.append(int(h["price"]))
        price_range = {}
        if prices:
            price_range = {
                "min": min(prices),
                "max": max(prices),
                "avg": int(sum(prices) / len(prices)),
            }
        return _ok({
            "total": len(all_h),
            "by_status": by_status,
            "by_district": by_district,
            "by_bedrooms": by_bedrooms,
            "price_range": price_range,
        })

    @app.get("/api/houses/listings/{house_id}")
    async def get_house_listings(request: Request, house_id: str):
        """根据房源 ID 获取该房源在各平台的全部挂牌记录。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        mock_state: MockState = request.app.state.mock_state
        house = mock_state.get_house(house_id)
        if house is None:
            return _err404(f"未找到房源 {house_id}")
        platforms = ["58同城", "安居客", "链家"]
        items = [_apply_platform(house, p) for p in platforms]
        return _ok({"total": len(items), "page": 1, "page_size": len(items), "items": items})

    @app.get("/api/houses/by_community")
    async def get_houses_by_community(
        request: Request,
        community: str,
        listing_platform: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ):
        """按小区名查询该小区下可租房源。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        platform = listing_platform if listing_platform in VALID_PLATFORMS else DEFAULT_PLATFORM
        mock_state: MockState = request.app.state.mock_state
        result = [
            h for h in mock_state.all_houses()
            if h.get("status") == "available" and h.get("community") == community
        ]
        total = len(result)
        page = max(1, page)
        page_size = min(max(1, page_size), 10000)
        items = [_apply_platform(h, platform) for h in _paginate(result, page, page_size)]
        return _ok({"total": total, "page": page, "page_size": len(items), "items": items})

    @app.get("/api/houses/by_platform")
    async def get_houses_by_platform(request: Request):
        """按挂牌平台筛选房源，支持 20+ 参数动态筛选 + 分页 + 平台定价。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        params = dict(request.query_params)
        platform = params.get("listing_platform", DEFAULT_PLATFORM)
        if platform not in VALID_PLATFORMS:
            platform = DEFAULT_PLATFORM

        mock_state: MockState = request.app.state.mock_state

        # AC4 步骤 1：过滤 status == "available"
        result = [h for h in mock_state.all_houses() if h.get("status") == "available"]

        # AC4 步骤 2：AND 条件过滤
        if "district" in params:
            districts = [d.strip() for d in params["district"].split(",")]
            result = [h for h in result if h.get("district") in districts]
        if "area" in params:
            areas = [a.strip() for a in params["area"].split(",")]
            result = [h for h in result if h.get("area") in areas]
        if "min_price" in params:
            mn = _parse_int(params["min_price"], 0)
            result = [h for h in result if int(h.get("price", 0)) >= mn]
        if "max_price" in params:
            mx = _parse_int(params["max_price"], 10**9)
            result = [h for h in result if int(h.get("price", 0)) <= mx]
        if "bedrooms" in params:
            bedrooms_set = {int(b.strip()) for b in params["bedrooms"].split(",") if b.strip().isdigit()}
            result = [h for h in result if h.get("bedrooms") in bedrooms_set]
        if "rental_type" in params:
            result = [h for h in result if h.get("rental_type") == params["rental_type"]]
        if "decoration" in params:
            result = [h for h in result if h.get("decoration") == params["decoration"]]
        if "orientation" in params:
            result = [h for h in result if h.get("orientation") == params["orientation"]]
        if "elevator" in params:
            want = params["elevator"].lower() == "true"
            result = [h for h in result if bool(h.get("elevator")) == want]
        if "min_area" in params:
            mn = _parse_float(params["min_area"], 0)
            result = [h for h in result if float(h.get("area_sqm", 0)) >= mn]
        if "max_area" in params:
            mx = _parse_float(params["max_area"], 10**9)
            result = [h for h in result if float(h.get("area_sqm", mx)) <= mx]
        if "subway_line" in params:
            result = [h for h in result if h.get("subway") == params["subway_line"]]
        if "max_subway_dist" in params:
            mx = _parse_int(params["max_subway_dist"], 10**9)
            result = [h for h in result if int(h.get("subway_distance", 10**9)) <= mx]
        if "subway_station" in params:
            result = [h for h in result if h.get("subway_station") == params["subway_station"]]
        if "commute_to_xierqi_max" in params:
            mx = _parse_int(params["commute_to_xierqi_max"], 10**9)
            result = [h for h in result if int(h.get("commute_to_xierqi", 10**9)) <= mx]
        if "property_type" in params:
            result = [h for h in result if h.get("property_type") == params["property_type"]]
        if "utilities_type" in params:
            result = [h for h in result if h.get("utilities_type") == params["utilities_type"]]
        if "available_from_before" in params:
            cutoff = params["available_from_before"]
            result = [h for h in result if h.get("available_from", "9999") <= cutoff]

        # AC4 步骤 3：排序
        sort_by = params.get("sort_by", "")
        sort_order = params.get("sort_order", "asc")
        reverse = sort_order == "desc"
        sort_map = {"price": "price", "area": "area_sqm", "subway": "subway_distance"}
        if sort_by in sort_map:
            field = sort_map[sort_by]
            result.sort(key=lambda h: float(h.get(field, 0)), reverse=reverse)

        # AC4 步骤 4：平台定价
        result_with_platform = [_apply_platform(h, platform) for h in result]

        # AC4 步骤 5：计算分页前总数
        total = len(result_with_platform)

        # AC4 步骤 6：分页
        page = _parse_int(params.get("page"), 1)
        page_size = min(_parse_int(params.get("page_size"), 10), 10000)
        page = max(1, page)
        page_size = max(1, page_size)
        items = _paginate(result_with_platform, page, page_size)

        return _ok({"total": total, "page": page, "page_size": page_size, "items": items})

    @app.get("/api/houses/nearby")
    async def get_houses_nearby(
        request: Request,
        landmark_id: str,
        max_distance: float = 2000.0,
        listing_platform: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ):
        """以地标为圆心，查询指定距离内的可租房源，含 Haversine 距离字段。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        platform = listing_platform if listing_platform in VALID_PLATFORMS else DEFAULT_PLATFORM

        landmarks: list[dict] = request.app.state.landmarks
        # 支持按 id 或按 name 查找地标
        lm = None
        for item in landmarks:
            if item["id"] == landmark_id or item["name"] == landmark_id:
                lm = item
                break
        if lm is None:
            return _err404(f"未找到地标 {landmark_id}")

        lm_lat, lm_lon = float(lm["latitude"]), float(lm["longitude"])
        mock_state: MockState = request.app.state.mock_state

        nearby: list[dict] = []
        for h in mock_state.all_houses():
            if h.get("status") != "available":
                continue
            h_lat, h_lon = float(h.get("latitude", 0)), float(h.get("longitude", 0))
            dist = _haversine_m(lm_lat, lm_lon, h_lat, h_lon)
            if dist <= max_distance:
                entry = _apply_platform(h, platform)
                d_int = int(dist)
                entry["distance_to_landmark"] = d_int
                walking_dist = int(d_int * 1.3)
                entry["walking_distance"] = walking_dist
                entry["walking_duration"] = int(walking_dist / 80)
                nearby.append(entry)

        nearby.sort(key=lambda x: x["distance_to_landmark"])
        total = len(nearby)
        page = max(1, page)
        page_size = min(max(1, page_size), 10000)
        items = _paginate(nearby, page, page_size)

        return _ok({
            "landmark": {
                "id": lm["id"],
                "name": lm["name"],
                "longitude": lm["longitude"],
                "latitude": lm["latitude"],
            },
            "total": total,
            "items": items,
        })

    @app.get("/api/houses/nearby_landmarks")
    async def get_nearby_landmarks(
        request: Request,
        community: str,
        type: Optional[str] = None,
        max_distance_m: float = 3000.0,
    ):
        """查询某小区周边某类地标（商超/公园），按距离排序。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        mock_state: MockState = request.app.state.mock_state

        # 找小区基准坐标（取该小区第一套房源）
        ref_house = None
        for h in mock_state.all_houses():
            if h.get("community") == community:
                ref_house = h
                break
        if ref_house is None:
            return _ok({"community": community, "type": type, "total": 0, "items": []})

        ref_lat = float(ref_house["latitude"])
        ref_lon = float(ref_house["longitude"])
        landmarks: list[dict] = request.app.state.landmarks

        result: list[dict] = []
        for lm in landmarks:
            if type is not None:
                lm_category = lm.get("category", "")
                lm_detail_type = (lm.get("details") or {}).get("type", "")
                if lm_category != type and lm_detail_type != type:
                    continue
            dist = _haversine_m(ref_lat, ref_lon, float(lm["latitude"]), float(lm["longitude"]))
            if dist <= max_distance_m:
                entry = _landmark_view(lm)
                entry["distance_m"] = int(dist)
                result.append(entry)

        result.sort(key=lambda x: x["distance_m"])
        return _ok({"community": community, "type": type, "total": len(result), "items": result or None})

    @app.get("/api/houses/{house_id}")
    async def get_house_by_id(request: Request, house_id: str):
        """根据房源 ID 获取单套房源详情（默认安居客定价）。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        mock_state: MockState = request.app.state.mock_state
        house = mock_state.get_house(house_id)
        if house is None:
            return _err404(f"未找到房源 {house_id}")
        return _ok(_apply_platform(house, DEFAULT_PLATFORM))

    # ══════════════════════════════════════════════════════════════════════════
    # 操作端点（4 个）— 需 X-User-ID + listing_platform (query param)
    # ══════════════════════════════════════════════════════════════════════════

    @app.post("/api/houses/init")
    async def init_houses(request: Request):
        """重置所有房源至 fixture 初始状态。"""
        mock_state: MockState = request.app.state.mock_state
        mock_state.init()
        user_id = request.headers.get("X-User-ID", "")
        return _ok({
            "action": "reset_user",
            "message": "该用户状态覆盖已清空，房源恢复为初始状态",
            "user_id": user_id,
        })

    @app.post("/api/houses/{house_id}/rent")
    async def rent_house(
        request: Request,
        house_id: str,
        listing_platform: Optional[str] = None,
    ):
        """将房源状态设为已租。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        if not listing_platform:
            return _err400("请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台")
        mock_state: MockState = request.app.state.mock_state
        updated = mock_state.update_status(house_id, "rented")
        if updated is None:
            return _err404(f"未找到房源 {house_id}")
        return _ok(_apply_platform(updated, listing_platform))

    @app.post("/api/houses/{house_id}/terminate")
    async def terminate_rental(
        request: Request,
        house_id: str,
        listing_platform: Optional[str] = None,
    ):
        """将房源状态恢复为可租。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        if not listing_platform:
            return _err400("请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台")
        mock_state: MockState = request.app.state.mock_state
        updated = mock_state.update_status(house_id, "available")
        if updated is None:
            return _err404(f"未找到房源 {house_id}")
        return _ok(_apply_platform(updated, listing_platform))

    @app.post("/api/houses/{house_id}/offline")
    async def offline_house(
        request: Request,
        house_id: str,
        listing_platform: Optional[str] = None,
    ):
        """将房源状态设为下架。"""
        if not _check_user_id(request):
            return _err400("请提供请求头 X-User-ID 以标识当前用户")
        if not listing_platform:
            return _err400("请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台")
        mock_state: MockState = request.app.state.mock_state
        updated = mock_state.update_status(house_id, "offline")
        if updated is None:
            return _err404(f"未找到房源 {house_id}")
        return _ok(_apply_platform(updated, listing_platform))

    return app
