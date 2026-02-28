import os
import httpx

# 模块顶层常量（必须在模块加载时读取一次）
# 支持环境变量覆盖，与 debug_init_houses.py 一致；tools 不创建 client，client 由 main 传入且已设置 trust_env=False 不走代理
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
USER_ID = os.environ["USER_ID"]  # 模块加载时读取，不在函数内读取
MAX_PAGES = 5


def _get_headers() -> dict:
    return {"X-User-ID": USER_ID.encode("utf-8")}


# ── Task 1: TOOLS 常量（OpenAI function-calling 格式） ──────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_houses",
            "description": "搜索可租房源，支持多维度筛选：区域、价格、户型、装修、朝向、地铁距离。自动处理分页，返回完整结果集（最多5页）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "行政区，如 海淀、朝阳、通州、昌平、大兴、房山、西城、丰台、顺义、东城"
                    },
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "room_type": {
                        "type": "string",
                        "description": "户型，如 整租、合租、一居室、两居室、三居室、四居室"
                    },
                    "decoration": {
                        "type": "string",
                        "enum": ["精装", "简装", "豪华", "毛坯", "空房"],
                        "description": "装修类型"
                    },
                    "orientation": {
                        "type": "string",
                        "description": "朝向，如 朝南、朝北、朝东、朝西、南北、东西"
                    },
                    "max_subway_dist": {
                        "type": "integer",
                        "description": "最大地铁距离（米），800=近地铁，1000=地铁可达"
                    },
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，默认安居客"
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
            "name": "search_landmark",
            "description": "按关键词模糊搜索地标（地铁站、公司、商圈等），返回 landmark_id 供后续查地标附近房源使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如 '西二旗'、'百度'、'国贸'"},
                    "category": {"type": "string", "description": "地标类别，如 地铁站、公司、商圈"},
                    "district": {"type": "string", "description": "行政区筛选"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_nearby_landmark",
            "description": "查询以指定地标为圆心、指定距离范围内的可租房源，返回含步行距离和步行时间。需先调用 search_landmark 获取 landmark_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_id": {"type": "string", "description": "地标 ID（来自 search_landmark 返回结果）"},
                    "max_distance": {"type": "integer", "description": "最大距离（米），默认 2000"},
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "room_type": {"type": "string", "description": "户型，如 整租、合租"},
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，默认安居客"
                    }
                },
                "required": ["landmark_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_amenities",
            "description": "查询指定房源 1000 米内的生活配套（商超、公园等），返回名称、类别和步行距离。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1"},
                    "category": {"type": "string", "description": "配套类别，如 商超、公园"},
                    "max_distance_m": {"type": "integer", "description": "最大距离（米），默认 1000"}
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
            json={"listing_platform": listing_platform},
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"execute_action failed: {str(e)}"}


# ── init_houses（Story 2.2 已实现，保持不变） ───────────────────────────────
async def init_houses(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.post("/api/houses/init", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"init_houses failed: {str(e)}"}
