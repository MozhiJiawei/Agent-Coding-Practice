import os
import httpx

# 模块顶层常量（必须在模块加载时读取一次）
RENTAL_API_BASE = "http://7.197.86.219:8080"
USER_ID = os.environ["USER_ID"]  # 模块加载时读取，不在函数内读取
MAX_PAGES = 5

# TOOLS 常量（将在 Story 3.1 填充，此处为空 list 占位）
TOOLS: list[dict] = []


def _get_headers() -> dict:
    return {"X-User-ID": USER_ID}


# 工具函数占位（将在 Epic 3-5 填充）
async def search_houses(client: httpx.AsyncClient, **kwargs) -> dict:
    pass


async def search_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    pass


async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    pass


async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    pass


async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    pass


async def execute_action(client: httpx.AsyncClient, **kwargs) -> dict:
    pass


async def init_houses(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.post("/api/houses/init", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"init_houses failed: {str(e)}"}
