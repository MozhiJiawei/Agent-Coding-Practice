import json
import time
from typing import Callable
import httpx
from openai import AsyncOpenAI
from tools import (
    TOOLS, search_houses, search_landmark, search_nearby_landmark,
    get_house_detail, get_nearby_amenities, execute_action
)

# 模块顶层常量
SYSTEM_PROMPT = ""  # 将在 Story 2.3 填充，≤800 Token
MAX_ITERATIONS = 10
HOUSE_SEARCH_TOOLS = {"search_houses", "search_nearby_landmark"}

TOOL_DISPATCH: dict[str, Callable] = {
    "search_houses": search_houses,
    "search_landmark": search_landmark,
    "search_nearby_landmark": search_nearby_landmark,
    "get_house_detail": get_house_detail,
    "get_nearby_amenities": get_nearby_amenities,
    "execute_action": execute_action,
}


def log_event(event_type: str, session_id: str, details: dict):
    # 将在 Story 6.1 完整实现
    pass


async def run_agent(history: list, model_ip: str, client: httpx.AsyncClient) -> dict:
    # 将在 Story 2.3 填充 Agent Loop 逻辑
    pass
