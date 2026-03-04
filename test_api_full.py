#!/usr/bin/env python3
"""
租房仿真 API 全量接口测试脚本

根据 docs/interface_simulate.md 接口文档编写，覆盖所有接口及主要场景，
并将每个接口的请求与响应写入日志文件。

运行前请设置环境变量 USER_ID（比赛平台注册的用户工号），例如：
  PowerShell: $env:USER_ID = "your_work_id"; python test_api_full.py
  Bash:       USER_ID=your_work_id python test_api_full.py

可选环境变量：
  RENTAL_API_BASE - API 基础 URL，默认 http://7.225.29.223:8080
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

# 环境变量
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
USER_ID = os.environ.get("USER_ID", "test-api-user")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 日志文件（按运行时间命名）
LOG_FILE = LOG_DIR / f"api_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


def _house_headers() -> dict:
    """房源相关接口需要的请求头"""
    return {"X-User-ID": USER_ID}


def _log(scenario: str, method: str, path: str, request_info: dict, response_info: dict) -> None:
    """将请求与响应写入日志文件"""
    resp = dict(response_info)
    if "error" in resp and not resp["error"]:
        resp["error"] = "Unknown error (empty exception message)"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scenario": scenario,
        "request": {"method": method, "path": path, **request_info},
        "response": resp,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"  [LOG] {scenario} -> {response_info.get('status_code', '?')} (已写入日志)")


def _truncate(body: str | dict, max_len: int = 2000) -> str:
    """截断过长的响应体便于日志阅读"""
    s = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
    return s[:max_len] + "..." if len(s) > max_len else s


async def run_all_tests(client: httpx.AsyncClient) -> dict:
    """执行全量接口测试，返回汇总结果"""
    results: dict = {}
    house_id_for_ops: str | None = None
    landmark_id: str | None = None
    community_name: str | None = None

    # ═══════════════════════════════════════════════════════════════
    # 一、地标接口（无需 X-User-ID）
    # ═══════════════════════════════════════════════════════════════

    # 1. GET /api/landmarks - 无参数
    scenario = "1_landmarks_list_noparam"
    try:
        resp = await client.get("/api/landmarks")
        _log(scenario, "GET", "/api/landmarks", {"params": {}}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/landmarks", {}, {"error": str(e) or repr(e)})
        results[scenario] = False

    # 2. GET /api/landmarks - category=subway, district=海淀
    scenario = "2_landmarks_list_filtered"
    try:
        params = {"category": "subway", "district": "海淀"}
        resp = await client.get("/api/landmarks", params=params)
        _log(scenario, "GET", "/api/landmarks", {"params": params}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/landmarks", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 3. GET /api/landmarks/name/{name}
    scenario = "3_landmarks_name_exact"
    try:
        resp = await client.get("/api/landmarks/name/西二旗站")
        _log(scenario, "GET", "/api/landmarks/name/西二旗站", {}, {"status_code": resp.status_code, "body": resp.json()})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 and data.get("data"):
                landmark_id = data["data"].get("id") or data["data"].get("landmark_id")
                if isinstance(landmark_id, str):
                    pass  # 已赋值
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/landmarks/name/西二旗站", {}, {"error": str(e)})
        results[scenario] = False

    # 4. GET /api/landmarks/search - q 必填
    scenario = "4_landmarks_search"
    try:
        params = {"q": "西二旗"}
        resp = await client.get("/api/landmarks/search", params=params)
        _log(scenario, "GET", "/api/landmarks/search", {"params": params}, {"status_code": resp.status_code, "body": resp.json()})
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", data).get("items", data.get("data", [])) if isinstance(data.get("data"), dict) else (data.get("data") or [])
            if isinstance(items, list) and items and not landmark_id:
                landmark_id = items[0].get("id") or items[0].get("landmark_id")
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/landmarks/search", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 4b. GET /api/landmarks/search - 带 category、district
    scenario = "4b_landmarks_search_filtered"
    try:
        params = {"q": "百度", "category": "company", "district": "海淀"}
        resp = await client.get("/api/landmarks/search", params=params)
        _log(scenario, "GET", "/api/landmarks/search", {"params": params}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/landmarks/search", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 5. GET /api/landmarks/{id} - 需要先有 landmark_id
    if landmark_id:
        scenario = "5_landmarks_by_id"
        try:
            resp = await client.get(f"/api/landmarks/{landmark_id}")
            _log(scenario, "GET", f"/api/landmarks/{landmark_id}", {}, {"status_code": resp.status_code, "body": resp.json()})
            results[scenario] = resp.status_code == 200
        except Exception as e:
            _log(scenario, "GET", f"/api/landmarks/{landmark_id}", {}, {"error": str(e)})
            results[scenario] = False
    else:
        # 使用常见 ID 兜底
        scenario = "5_landmarks_by_id"
        try:
            resp = await client.get("/api/landmarks/SS_001")
            _log(scenario, "GET", "/api/landmarks/SS_001", {}, {"status_code": resp.status_code, "body": resp.json()})
            results[scenario] = resp.status_code == 200
        except Exception as e:
            _log(scenario, "GET", "/api/landmarks/SS_001", {}, {"error": str(e)})
            results[scenario] = False

    # 6. GET /api/landmarks/stats
    scenario = "6_landmarks_stats"
    try:
        resp = await client.get("/api/landmarks/stats")
        _log(scenario, "GET", "/api/landmarks/stats", {}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/landmarks/stats", {}, {"error": str(e)})
        results[scenario] = False

    # ═══════════════════════════════════════════════════════════════
    # 二、房源初始化（必须带 X-User-ID）
    # ═══════════════════════════════════════════════════════════════

    # 7. POST /api/houses/init
    scenario = "7_houses_init"
    try:
        resp = await client.post("/api/houses/init", headers=_house_headers())
        _log(scenario, "POST", "/api/houses/init", {"headers": {"X-User-ID": USER_ID}}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "POST", "/api/houses/init", {"headers": {"X-User-ID": USER_ID}}, {"error": str(e)})
        results[scenario] = False

    # ═══════════════════════════════════════════════════════════════
    # 三、房源查询接口
    # ═══════════════════════════════════════════════════════════════

    # 8. GET /api/houses/stats
    scenario = "8_houses_stats"
    try:
        resp = await client.get("/api/houses/stats", headers=_house_headers())
        _log(scenario, "GET", "/api/houses/stats", {"headers": {"X-User-ID": USER_ID}}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/stats", {}, {"error": str(e)})
        results[scenario] = False

    # 9. GET /api/houses/by_platform - 无参数（默认安居客）
    scenario = "9_houses_by_platform_default"
    try:
        resp = await client.get("/api/houses/by_platform", headers=_house_headers())
        data = resp.json()
        _log(scenario, "GET", "/api/houses/by_platform", {"params": {}}, {"status_code": resp.status_code, "body": _truncate(data)})
        inner = data.get("data", data)
        items = inner.get("items", []) if isinstance(inner, dict) else []
        if items and not house_id_for_ops:
            house_id_for_ops = items[0].get("house_id") or items[0].get("id")
        if items and not community_name:
            community_name = items[0].get("community") or items[0].get("community_name")
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/by_platform", {}, {"error": str(e)})
        results[scenario] = False

    # 10. GET /api/houses/by_platform - 多参数组合
    scenario = "10_houses_by_platform_filtered"
    try:
        params = {
            "district": "海淀",
            "min_price": 2000,
            "max_price": 6000,
            "bedrooms": "1,2",
            "rental_type": "整租",
            "listing_platform": "安居客",
            "page": 1,
            "page_size": 5,
            "sort_by": "subway",
            "sort_order": "asc",
        }
        resp = await client.get("/api/houses/by_platform", params=params, headers=_house_headers())
        data = resp.json()
        _log(scenario, "GET", "/api/houses/by_platform", {"params": params}, {"status_code": resp.status_code, "body": _truncate(data)})
        inner = data.get("data", data)
        items = inner.get("items", []) if isinstance(inner, dict) else []
        if items and not house_id_for_ops:
            house_id_for_ops = items[0].get("house_id") or items[0].get("id")
        if items and not community_name:
            community_name = items[0].get("community") or items[0].get("community_name")
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/by_platform", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 11. GET /api/houses/by_platform - 链家、58同城
    for plat in ["链家", "58同城"]:
        scenario = f"11_houses_by_platform_{plat}"
        try:
            params = {"listing_platform": plat, "page": 1, "page_size": 3}
            resp = await client.get("/api/houses/by_platform", params=params, headers=_house_headers())
            _log(scenario, "GET", "/api/houses/by_platform", {"params": params}, {"status_code": resp.status_code, "body": _truncate(resp.json())})
            results[scenario] = resp.status_code == 200
        except Exception as e:
            _log(scenario, "GET", "/api/houses/by_platform", {"params": params}, {"error": str(e)})
            results[scenario] = False

    # 11b. GET /api/houses/by_platform - 装修、朝向、电梯、面积、通勤
    scenario = "11b_houses_by_platform_extended"
    try:
        params = {
            "decoration": "精装",
            "orientation": "朝南",
            "elevator": "true",
            "min_area": 50,
            "max_area": 120,
            "commute_to_xierqi_max": 60,
            "page": 1,
            "page_size": 3,
        }
        resp = await client.get("/api/houses/by_platform", params=params, headers=_house_headers())
        _log(scenario, "GET", "/api/houses/by_platform", {"params": params}, {"status_code": resp.status_code, "body": _truncate(resp.json())})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/by_platform", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 12. GET /api/houses/by_community - 需要 community
    if not community_name:
        community_name = "建清园(南区)"
    scenario = "12_houses_by_community"
    try:
        params = {"community": community_name, "page": 1, "page_size": 5}
        resp = await client.get("/api/houses/by_community", params=params, headers=_house_headers())
        data = resp.json()
        _log(scenario, "GET", "/api/houses/by_community", {"params": params}, {"status_code": resp.status_code, "body": _truncate(data)})
        inner = data.get("data", data)
        items = inner.get("items", []) if isinstance(inner, dict) else []
        if items and not house_id_for_ops:
            house_id_for_ops = items[0].get("house_id") or items[0].get("id")
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/by_community", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 12b. GET /api/houses/by_community - 指定 listing_platform=链家
    scenario = "12b_houses_by_community_lianjia"
    try:
        params = {"community": community_name, "listing_platform": "链家", "page": 1, "page_size": 5}
        resp = await client.get("/api/houses/by_community", params=params, headers=_house_headers())
        data = resp.json()
        _log(scenario, "GET", "/api/houses/by_community", {"params": params}, {"status_code": resp.status_code, "body": _truncate(data)})
        inner = data.get("data", data)
        items = inner.get("items", []) if isinstance(inner, dict) else []
        if items and not house_id_for_ops:
            house_id_for_ops = items[0].get("house_id") or items[0].get("id")
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/by_community", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 13. GET /api/houses/nearby - 需要 landmark_id
    lm_id = landmark_id or "SS_001"
    scenario = "13_houses_nearby"
    try:
        params = {"landmark_id": lm_id, "max_distance": 2000, "page": 1, "page_size": 5}
        resp = await client.get("/api/houses/nearby", params=params, headers=_house_headers())
        data = resp.json()
        _log(scenario, "GET", "/api/houses/nearby", {"params": params}, {"status_code": resp.status_code, "body": _truncate(data)})
        inner = data.get("data", data)
        items = inner.get("items", []) if isinstance(inner, dict) else []
        if items and not house_id_for_ops:
            house_id_for_ops = items[0].get("house_id") or items[0].get("id")
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/nearby", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 13b. GET /api/houses/nearby - 地标名称、指定 listing_platform
    scenario = "13b_houses_nearby_by_name"
    try:
        params = {"landmark_id": "西二旗站", "max_distance": 2000, "listing_platform": "链家", "page": 1, "page_size": 3}
        resp = await client.get("/api/houses/nearby", params=params, headers=_house_headers())
        _log(scenario, "GET", "/api/houses/nearby", {"params": params}, {"status_code": resp.status_code, "body": _truncate(resp.json())})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/nearby", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 14. GET /api/houses/nearby_landmarks - 小区周边地标
    scenario = "14_houses_nearby_landmarks"
    try:
        params = {"community": community_name, "type": "shopping", "max_distance_m": 3000}
        resp = await client.get("/api/houses/nearby_landmarks", params=params, headers=_house_headers())
        _log(scenario, "GET", "/api/houses/nearby_landmarks", {"params": params}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/nearby_landmarks", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 14b. GET /api/houses/nearby_landmarks - type=park
    scenario = "14b_houses_nearby_landmarks_park"
    try:
        params = {"community": community_name, "type": "park", "max_distance_m": 3000}
        resp = await client.get("/api/houses/nearby_landmarks", params=params, headers=_house_headers())
        _log(scenario, "GET", "/api/houses/nearby_landmarks", {"params": params}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", "/api/houses/nearby_landmarks", {"params": params}, {"error": str(e)})
        results[scenario] = False

    # 15. GET /api/houses/{house_id}
    h_id = house_id_for_ops or "HF_2001"
    scenario = "15_houses_detail"
    try:
        resp = await client.get(f"/api/houses/{h_id}", headers=_house_headers())
        _log(scenario, "GET", f"/api/houses/{h_id}", {}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", f"/api/houses/{h_id}", {}, {"error": str(e)})
        results[scenario] = False

    # 16. GET /api/houses/listings/{house_id}
    scenario = "16_houses_listings"
    try:
        resp = await client.get(f"/api/houses/listings/{h_id}", headers=_house_headers())
        _log(scenario, "GET", f"/api/houses/listings/{h_id}", {}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        _log(scenario, "GET", f"/api/houses/listings/{h_id}", {}, {"error": str(e)})
        results[scenario] = False

    # ═══════════════════════════════════════════════════════════════
    # 四、房源操作接口（rent / terminate / offline）
    # ═══════════════════════════════════════════════════════════════

    # 17. POST /api/houses/{house_id}/rent（listing_platform 必填，支持 query 或 body）
    scenario = "17_houses_rent"
    body_data = {"listing_platform": "安居客"}
    try:
        resp = await client.post(f"/api/houses/{h_id}/rent", json=body_data, headers=_house_headers())
        _log(scenario, "POST", f"/api/houses/{h_id}/rent", {"body": body_data}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        try:
            resp = await client.post(f"/api/houses/{h_id}/rent", params=body_data, headers=_house_headers())
            _log(scenario, "POST", f"/api/houses/{h_id}/rent", {"params": body_data}, {"status_code": resp.status_code, "body": resp.json()})
            results[scenario] = resp.status_code == 200
        except Exception as e2:
            _log(scenario, "POST", f"/api/houses/{h_id}/rent", {}, {"error": str(e2)})
            results[scenario] = False

    # 18. POST /api/houses/{house_id}/terminate
    scenario = "18_houses_terminate"
    try:
        resp = await client.post(f"/api/houses/{h_id}/terminate", json=body_data, headers=_house_headers())
        _log(scenario, "POST", f"/api/houses/{h_id}/terminate", {"body": body_data}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        try:
            resp = await client.post(f"/api/houses/{h_id}/terminate", params=body_data, headers=_house_headers())
            _log(scenario, "POST", f"/api/houses/{h_id}/terminate", {"params": body_data}, {"status_code": resp.status_code, "body": resp.json()})
            results[scenario] = resp.status_code == 200
        except Exception as e2:
            _log(scenario, "POST", f"/api/houses/{h_id}/terminate", {}, {"error": str(e2)})
            results[scenario] = False

    # 19. POST /api/houses/{house_id}/offline
    scenario = "19_houses_offline"
    try:
        resp = await client.post(f"/api/houses/{h_id}/offline", json=body_data, headers=_house_headers())
        _log(scenario, "POST", f"/api/houses/{h_id}/offline", {"body": body_data}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        try:
            resp = await client.post(f"/api/houses/{h_id}/offline", params=body_data, headers=_house_headers())
            _log(scenario, "POST", f"/api/houses/{h_id}/offline", {"params": body_data}, {"status_code": resp.status_code, "body": resp.json()})
            results[scenario] = resp.status_code == 200
        except Exception as e2:
            _log(scenario, "POST", f"/api/houses/{h_id}/offline", {}, {"error": str(e2)})
            results[scenario] = False

    # 20. 再次 terminate 恢复可租，便于后续重复测试
    scenario = "20_houses_terminate_again"
    try:
        resp = await client.post(f"/api/houses/{h_id}/terminate", json=body_data, headers=_house_headers())
        if resp.status_code != 200:
            resp = await client.post(f"/api/houses/{h_id}/terminate", params=body_data, headers=_house_headers())
        _log(scenario, "POST", f"/api/houses/{h_id}/terminate", {"body": body_data}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 200
    except Exception as e:
        try:
            resp = await client.post(f"/api/houses/{h_id}/terminate", params=body_data, headers=_house_headers())
            _log(scenario, "POST", f"/api/houses/{h_id}/terminate", {"params": body_data}, {"status_code": resp.status_code, "body": resp.json()})
            results[scenario] = resp.status_code == 200
        except Exception as e2:
            _log(scenario, "POST", f"/api/houses/{h_id}/terminate", {}, {"error": str(e2)})
            results[scenario] = False

    # ═══════════════════════════════════════════════════════════════
    # 五、异常场景：房源接口缺少 X-User-ID 应返回 400
    # ═══════════════════════════════════════════════════════════════

    scenario = "21_houses_without_userid_400"
    try:
        resp = await client.get("/api/houses/stats")
        _log(scenario, "GET", "/api/houses/stats", {"headers": "无 X-User-ID"}, {"status_code": resp.status_code, "body": resp.json()})
        results[scenario] = resp.status_code == 400
    except Exception as e:
        _log(scenario, "GET", "/api/houses/stats", {"headers": "无 X-User-ID"}, {"error": str(e)})
        results[scenario] = False

    return results


async def main() -> int:
    print("=" * 60)
    print("租房仿真 API 全量接口测试")
    print("=" * 60)
    print(f"BASE_URL: {RENTAL_API_BASE}")
    print(f"USER_ID:  {USER_ID}")
    print(f"日志文件: {LOG_FILE}")
    print("=" * 60)

    # 写入日志文件头部
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"type": "test_run_start", "base_url": RENTAL_API_BASE, "user_id": USER_ID, "timestamp": datetime.now().isoformat()},
                ensure_ascii=False,
            )
            + "\n"
        )

    async with httpx.AsyncClient(base_url=RENTAL_API_BASE, timeout=30.0, trust_env=False) as client:
        results = await run_all_tests(client)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"汇总: {passed}/{total} 通过")
    print("=" * 60)
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
