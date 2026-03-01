"""
test-simulator/tests/test_mock_rental.py — Mock Rental API 单元测试（Story 5.2 / ER1）

覆盖所有 15 个端点：
  - 地标（5 个）：/api/landmarks, /api/landmarks/name/{name}, /api/landmarks/search,
                   /api/landmarks/{id}, /api/landmarks/stats
  - 房源查询（7 个）：/api/houses/{id}, /api/houses/listings/{id}, /api/houses/by_community,
                       /api/houses/by_platform, /api/houses/nearby, /api/houses/nearby_landmarks,
                       /api/houses/stats
  - 操作（3 个）：/api/houses/{id}/rent, /api/houses/{id}/terminate, /api/houses/{id}/offline
  - 重置（1 个）：/api/houses/init
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SimulatorConfig
from mock_rental import create_mock_rental_app, MockState, PLATFORM_FACTORS


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

FIXTURES = {
    "landmarks": [
        {
            "id": "SS_001",
            "name": "西二旗站",
            "category": "subway",
            "district": "海淀",
            "longitude": 116.3289,
            "latitude": 40.0567,
            "details": {
                "lines": ["13号线", "昌平线"],
                "type": "transfer",
            },
        },
        {
            "id": "LM_001",
            "name": "中关村广场",
            "category": "landmark",
            "district": "海淀",
            "longitude": 116.3103,
            "latitude": 39.9832,
            "details": {
                "type": "shopping",
                "type_name": "购物中心",
            },
        },
        {
            "id": "F500_001",
            "name": "百度科技园",
            "category": "company",
            "district": "海淀",
            "longitude": 116.3074,
            "latitude": 40.0565,
            "details": {
                "industry": "互联网",
            },
        },
    ],
    "houses": [
        {
            "house_id": "HF_001",
            "community": "上地嘉园",
            "district": "海淀",
            "area": "上地",
            "price": 4800,
            "status": "available",
            "longitude": 116.3110,
            "latitude": 40.0460,
            "bedrooms": 2,
            "rental_type": "整租",
            "decoration": "精装",
            "orientation": "朝南",
            "elevator": True,
            "area_sqm": 75,
            "property_type": "住宅",
            "utilities_type": "民水民电",
            "subway": "13号线",
            "subway_station": "上地站",
            "subway_distance": 320,
            "tags": ["近地铁", "精装修"],
        },
        {
            "house_id": "HF_002",
            "community": "西二旗嘉苑",
            "district": "海淀",
            "area": "西二旗",
            "price": 3600,
            "status": "available",
            "longitude": 116.3320,
            "latitude": 40.0580,
            "bedrooms": 1,
            "rental_type": "整租",
            "decoration": "简装",
            "orientation": "朝东",
            "elevator": False,
            "area_sqm": 45,
            "property_type": "住宅",
            "utilities_type": "商水商电",
            "subway": "13号线",
            "subway_station": "西二旗站",
            "subway_distance": 500,
            "tags": ["近地铁"],
        },
        {
            "house_id": "HF_003",
            "community": "朝阳公寓",
            "district": "朝阳",
            "area": "三里屯",
            "price": 8000,
            "status": "rented",
            "longitude": 116.4522,
            "latitude": 39.9317,
            "bedrooms": 3,
            "rental_type": "整租",
            "decoration": "豪华",
            "orientation": "南北",
            "elevator": True,
            "area_sqm": 120,
            "property_type": "住宅",
            "utilities_type": "民水民电",
            "subway": "10号线",
            "subway_station": "团结湖站",
            "subway_distance": 600,
            "tags": ["豪华装修"],
        },
    ],
}

CONFIG = SimulatorConfig(
    llm_proxy_url="http://localhost:8888",
    test_user_id="test-user",
)

USER_HEADER = {"X-User-ID": "test-user"}


@pytest.fixture
def client():
    app = create_mock_rental_app(CONFIG, FIXTURES)
    with TestClient(app) as tc:
        yield tc


# ─────────────────────────────────────────────────────────────────────────────
# MockState 单元测试
# ─────────────────────────────────────────────────────────────────────────────

class TestMockState:
    def test_init_stores_initial_status(self):
        state = MockState(FIXTURES["houses"])
        assert "HF_001" in state.houses
        assert state.houses["HF_001"]["_initial_status"] == "available"
        assert state.houses["HF_003"]["_initial_status"] == "rented"

    def test_update_status_returns_updated_house(self):
        state = MockState(FIXTURES["houses"])
        result = state.update_status("HF_001", "rented")
        assert result is not None
        assert result["status"] == "rented"
        assert "_initial_status" not in result

    def test_update_status_returns_none_for_missing_house(self):
        state = MockState(FIXTURES["houses"])
        assert state.update_status("HF_999", "rented") is None

    def test_init_resets_all_to_initial_status(self):
        state = MockState(FIXTURES["houses"])
        state.update_status("HF_001", "offline")
        state.init()
        assert state.houses["HF_001"]["status"] == "available"
        assert state.houses["HF_003"]["status"] == "rented"

    def test_get_house_excludes_internal_fields(self):
        state = MockState(FIXTURES["houses"])
        h = state.get_house("HF_001")
        assert h is not None
        assert "_initial_status" not in h

    def test_get_house_returns_none_for_missing(self):
        state = MockState(FIXTURES["houses"])
        assert state.get_house("HF_999") is None

    def test_all_houses_excludes_internal_fields(self):
        state = MockState(FIXTURES["houses"])
        for h in state.all_houses():
            assert "_initial_status" not in h


# ─────────────────────────────────────────────────────────────────────────────
# Task 2: 地标端点（5 个）— AC12：无 X-User-ID 校验
# ─────────────────────────────────────────────────────────────────────────────

class TestLandmarksEndpoints:
    """地标端点无需 X-User-ID，直接从 fixture 读取。"""

    # 1. GET /api/landmarks
    def test_get_landmarks_no_filter(self, client):
        r = client.get("/api/landmarks")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 3
        assert len(body["data"]["items"]) == 3

    def test_get_landmarks_filter_by_category(self, client):
        r = client.get("/api/landmarks?category=subway")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["id"] == "SS_001"

    def test_get_landmarks_filter_by_district(self, client):
        r = client.get("/api/landmarks?district=海淀")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 3

    def test_get_landmarks_filter_category_and_district_intersection(self, client):
        r = client.get("/api/landmarks?category=company&district=海淀")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["id"] == "F500_001"

    def test_get_landmarks_no_userid_required(self, client):
        """AC12: 地标端点不需要 X-User-ID。"""
        r = client.get("/api/landmarks")
        assert r.status_code == 200
        assert r.json()["code"] == 0

    # 2. GET /api/landmarks/name/{name}
    def test_get_landmark_by_name_found(self, client):
        r = client.get("/api/landmarks/name/西二旗站")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["id"] == "SS_001"

    def test_get_landmark_by_name_not_found(self, client):
        r = client.get("/api/landmarks/name/不存在的地标")
        assert r.status_code == 200
        assert r.json()["code"] == 404

    # 3. GET /api/landmarks/search
    def test_search_landmarks_by_keyword(self, client):
        r = client.get("/api/landmarks/search?q=西二旗")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "西二旗站"

    def test_search_landmarks_with_category_filter(self, client):
        r = client.get("/api/landmarks/search?q=百度&category=company")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_search_landmarks_no_results(self, client):
        r = client.get("/api/landmarks/search?q=不存在的关键词")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    # 4. GET /api/landmarks/{id}
    def test_get_landmark_by_id_found(self, client):
        r = client.get("/api/landmarks/SS_001")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "西二旗站"

    def test_get_landmark_by_id_includes_details(self, client):
        """M1 fix: 地标响应应包含 details 字段。"""
        r = client.get("/api/landmarks/SS_001")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "details" in data
        assert data["details"]["lines"] == ["13号线", "昌平线"]

    def test_get_landmark_by_id_not_found(self, client):
        r = client.get("/api/landmarks/SS_999")
        assert r.status_code == 200
        assert r.json()["code"] == 404

    # 5. GET /api/landmarks/stats
    def test_get_landmark_stats(self, client):
        r = client.get("/api/landmarks/stats")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 3
        assert "by_category" in data
        assert "by_district" in data
        assert data["by_category"]["subway"] == 1
        assert data["by_category"]["landmark"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Task 3: 房源查询端点（7 个）— AC8: 缺 X-User-ID 返回 400
# ─────────────────────────────────────────────────────────────────────────────

class TestHouseQueryEndpoints:

    # AC8: 缺 X-User-ID 返回 400
    def test_houses_stats_no_userid_returns_400(self, client):
        r = client.get("/api/houses/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 400
        assert "X-User-ID" in body["message"]

    def test_houses_by_id_no_userid_returns_400(self, client):
        r = client.get("/api/houses/HF_001")
        assert r.status_code == 200
        assert r.json()["code"] == 400

    # 6. GET /api/houses/{id}
    def test_get_house_by_id_success(self, client):
        r = client.get("/api/houses/HF_001", headers=USER_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        h = body["data"]
        assert h["house_id"] == "HF_001"
        assert h["listing_platform"] == "安居客"
        assert h["price"] == 4800  # factor=1.00

    def test_get_house_by_id_not_found(self, client):
        r = client.get("/api/houses/HF_999", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 404

    # AC11: GET /api/houses/{id} 默认安居客定价
    def test_get_house_by_id_default_anjuke_platform(self, client):
        r = client.get("/api/houses/HF_001", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["listing_platform"] == "安居客"

    # 7. GET /api/houses/listings/{id}
    def test_get_house_listings_success(self, client):
        r = client.get("/api/houses/listings/HF_001", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 3
        platforms = {item["listing_platform"] for item in data["items"]}
        assert platforms == {"安居客", "链家", "58同城"}

    def test_get_house_listings_platform_pricing(self, client):
        r = client.get("/api/houses/listings/HF_001", headers=USER_HEADER)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        price_map = {item["listing_platform"]: item["price"] for item in items}
        assert price_map["安居客"] == 4800
        assert price_map["链家"] == int(4800 * 0.92)
        assert price_map["58同城"] == int(4800 * 0.78)

    def test_get_house_listings_not_found(self, client):
        r = client.get("/api/houses/listings/HF_999", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 404

    # 8. GET /api/houses/by_community
    def test_get_houses_by_community_success(self, client):
        r = client.get("/api/houses/by_community?community=上地嘉园", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["house_id"] == "HF_001"

    def test_get_houses_by_community_only_available(self, client):
        """by_community 只返回 available 房源。"""
        r = client.get("/api/houses/by_community?community=朝阳公寓", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_get_houses_by_community_platform_pricing(self, client):
        r = client.get("/api/houses/by_community?community=上地嘉园&listing_platform=链家", headers=USER_HEADER)
        assert r.status_code == 200
        item = r.json()["data"]["items"][0]
        assert item["listing_platform"] == "链家"
        assert item["price"] == int(4800 * 0.92)

    # AC11: by_community 默认安居客
    def test_get_houses_by_community_default_anjuke(self, client):
        r = client.get("/api/houses/by_community?community=上地嘉园", headers=USER_HEADER)
        assert r.status_code == 200
        item = r.json()["data"]["items"][0]
        assert item["listing_platform"] == "安居客"

    # 9. GET /api/houses/by_platform — AC3, AC4, AC11
    def test_get_houses_by_platform_default_anjuke(self, client):
        """AC11: 不传 listing_platform 默认安居客。"""
        r = client.get("/api/houses/by_platform", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 2  # available: HF_001, HF_002
        for item in data["items"]:
            assert item["listing_platform"] == "安居客"

    def test_get_houses_by_platform_lianjia_pricing(self, client):
        """AC3: 链家定价 = 基准价 × 0.92（取整）。"""
        r = client.get("/api/houses/by_platform?listing_platform=链家", headers=USER_HEADER)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        prices = {item["house_id"]: item["price"] for item in items}
        assert prices["HF_001"] == int(4800 * 0.92)
        assert prices["HF_002"] == int(3600 * 0.92)

    def test_get_houses_by_platform_58_pricing(self, client):
        r = client.get("/api/houses/by_platform?listing_platform=58同城", headers=USER_HEADER)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        prices = {item["house_id"]: item["price"] for item in items}
        assert prices["HF_001"] == int(4800 * 0.78)

    def test_get_houses_by_platform_filter_district(self, client):
        r = client.get("/api/houses/by_platform?district=朝阳", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        # HF_003 是 rented，所以 total=0
        assert data["total"] == 0

    def test_get_houses_by_platform_filter_bedrooms(self, client):
        r = client.get("/api/houses/by_platform?bedrooms=1", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["house_id"] == "HF_002"

    def test_get_houses_by_platform_filter_elevator(self, client):
        r = client.get("/api/houses/by_platform?elevator=true", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert all(item["elevator"] for item in data["items"])

    def test_get_houses_by_platform_pagination(self, client):
        r = client.get("/api/houses/by_platform?page=1&page_size=1", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 2  # 分页前总数
        assert len(data["items"]) == 1

    def test_get_houses_by_platform_ac4_filter_order(self, client):
        """AC4: 过滤 available → AND 条件 → 排序 → 平台定价 → total → 分页。"""
        r = client.get(
            "/api/houses/by_platform?listing_platform=链家&bedrooms=2&sort_by=price&sort_order=asc",
            headers=USER_HEADER,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["house_id"] == "HF_001"
        assert data["items"][0]["price"] == int(4800 * 0.92)

    def test_get_houses_by_platform_filter_min_area(self, client):
        r = client.get("/api/houses/by_platform?min_area=50", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["house_id"] == "HF_001"

    def test_get_houses_by_platform_filter_max_area(self, client):
        r = client.get("/api/houses/by_platform?max_area=50", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["house_id"] == "HF_002"

    def test_get_houses_by_platform_filter_property_type(self, client):
        r = client.get("/api/houses/by_platform?property_type=住宅", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2

    def test_get_houses_by_platform_filter_utilities_type(self, client):
        r = client.get("/api/houses/by_platform?utilities_type=商水商电", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["house_id"] == "HF_002"

    def test_get_houses_by_platform_no_userid_returns_400(self, client):
        r = client.get("/api/houses/by_platform")
        assert r.status_code == 200
        assert r.json()["code"] == 400

    # 10. GET /api/houses/nearby — AC5
    def test_get_houses_nearby_haversine(self, client):
        """AC5: Haversine 距离计算，含 distance_to_landmark/walking_distance/walking_duration。"""
        # SS_001 (116.3289, 40.0567) — HF_001 和 HF_002 都在附近
        r = client.get("/api/houses/nearby?landmark_id=SS_001&max_distance=5000", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "landmark" in data
        assert data["landmark"]["id"] == "SS_001"
        assert data["total"] > 0
        for item in data["items"]:
            assert "distance_to_landmark" in item
            assert "walking_distance" in item
            assert "walking_duration" in item
            assert item["distance_to_landmark"] <= 5000

    def test_get_houses_nearby_by_landmark_name(self, client):
        """AC5: 支持按地标名称查找。"""
        r = client.get("/api/houses/nearby?landmark_id=西二旗站&max_distance=5000", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["landmark"]["name"] == "西二旗站"

    def test_get_houses_nearby_only_available(self, client):
        """nearby 只返回 available 房源。"""
        r = client.get("/api/houses/nearby?landmark_id=SS_001&max_distance=100000", headers=USER_HEADER)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        for item in items:
            assert item["status"] == "available"

    def test_get_houses_nearby_distance_calculation(self, client):
        """验证 walking_distance = distance × 1.3，walking_duration = walking_distance / 80。"""
        r = client.get("/api/houses/nearby?landmark_id=SS_001&max_distance=5000", headers=USER_HEADER)
        assert r.status_code == 200
        for item in r.json()["data"]["items"]:
            d = item["distance_to_landmark"]
            wd = item["walking_distance"]
            wt = item["walking_duration"]
            assert wd == int(d * 1.3)
            assert wt == int(wd / 80)

    def test_get_houses_nearby_invalid_landmark(self, client):
        r = client.get("/api/houses/nearby?landmark_id=SS_999&max_distance=2000", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 404

    def test_get_houses_nearby_platform_pricing(self, client):
        r = client.get(
            "/api/houses/nearby?landmark_id=SS_001&max_distance=5000&listing_platform=链家",
            headers=USER_HEADER,
        )
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        if items:
            assert items[0]["listing_platform"] == "链家"

    # 11. GET /api/houses/nearby_landmarks
    def test_get_nearby_landmarks_success(self, client):
        r = client.get("/api/houses/nearby_landmarks?community=上地嘉园", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "community" in data
        assert "total" in data

    def test_get_nearby_landmarks_filter_by_details_type(self, client):
        """H2 fix: type 参数应匹配 details.type（如 shopping），不仅是 category。"""
        r = client.get("/api/houses/nearby_landmarks?community=上地嘉园&type=shopping&max_distance_m=50000", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 1
        names = [item["name"] for item in data["items"]]
        assert "中关村广场" in names

    def test_get_nearby_landmarks_not_found_community_returns_empty(self, client):
        r = client.get("/api/houses/nearby_landmarks?community=不存在的小区", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0

    # 12. GET /api/houses/stats
    def test_get_house_stats_success(self, client):
        r = client.get("/api/houses/stats", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 3
        assert "by_status" in data
        assert data["by_status"]["available"] == 2
        assert data["by_status"]["rented"] == 1
        assert "by_district" in data
        assert "by_bedrooms" in data
        assert "price_range" in data


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: 操作端点（4 个）— AC6, AC7, AC8, AC9, AC10
# ─────────────────────────────────────────────────────────────────────────────

class TestHouseOperationEndpoints:

    # 13. POST /api/houses/init — AC7
    def test_init_resets_to_fixture_state(self, client):
        """AC7: init() 重置所有房源至初始状态。"""
        client.post("/api/houses/HF_001/rent?listing_platform=安居客", headers=USER_HEADER)
        r_init = client.post("/api/houses/init", headers=USER_HEADER)
        assert r_init.status_code == 200
        body = r_init.json()
        assert body["code"] == 0
        assert body["data"]["action"] == "reset_user"
        # 验证重置后 HF_001 可再次查询
        r = client.get("/api/houses/by_platform", headers=USER_HEADER)
        ids = [h["house_id"] for h in r.json()["data"]["items"]]
        assert "HF_001" in ids

    def test_init_success_response_format(self, client):
        r = client.post("/api/houses/init", headers=USER_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["message"] == "success"
        assert "该用户状态覆盖已清空" in body["data"]["message"]
        assert body["data"]["user_id"] == "test-user"

    # 14. POST /api/houses/{id}/rent — AC6, AC8, AC9, AC10
    def test_rent_success_changes_status(self, client):
        """AC6: rent 调用后状态变为 rented，后续 GET 返回 rented。"""
        r = client.post("/api/houses/HF_001/rent?listing_platform=安居客", headers=USER_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "rented"

        r2 = client.get("/api/houses/HF_001", headers=USER_HEADER)
        assert r2.json()["data"]["status"] == "rented"

    def test_rent_no_userid_returns_400(self, client):
        """AC8: 缺 X-User-ID 返回 code=400。"""
        r = client.post("/api/houses/HF_001/rent?listing_platform=安居客")
        assert r.status_code == 200
        assert r.json()["code"] == 400
        assert "X-User-ID" in r.json()["message"]

    def test_rent_no_listing_platform_returns_400(self, client):
        """AC9: 缺 listing_platform 返回 code=400。"""
        r = client.post("/api/houses/HF_001/rent", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 400
        assert "listing_platform" in r.json()["message"]

    def test_rent_invalid_house_returns_404(self, client):
        """AC10: 房源不存在返回 code=404。"""
        r = client.post("/api/houses/HF_999/rent?listing_platform=安居客", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 404

    def test_rent_response_includes_platform_pricing(self, client):
        r = client.post("/api/houses/HF_001/rent?listing_platform=链家", headers=USER_HEADER)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["listing_platform"] == "链家"
        assert data["price"] == int(4800 * 0.92)

    # 15. POST /api/houses/{id}/terminate
    def test_terminate_changes_status_to_available(self, client):
        client.post("/api/houses/HF_001/rent?listing_platform=安居客", headers=USER_HEADER)
        r = client.post("/api/houses/HF_001/terminate?listing_platform=安居客", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "available"

    def test_terminate_no_userid_returns_400(self, client):
        r = client.post("/api/houses/HF_001/terminate?listing_platform=安居客")
        assert r.status_code == 200
        assert r.json()["code"] == 400

    def test_terminate_no_platform_returns_400(self, client):
        r = client.post("/api/houses/HF_001/terminate", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 400

    def test_terminate_invalid_house_returns_404(self, client):
        r = client.post("/api/houses/HF_999/terminate?listing_platform=安居客", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 404

    # 16. POST /api/houses/{id}/offline
    def test_offline_changes_status(self, client):
        r = client.post("/api/houses/HF_001/offline?listing_platform=安居客", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "offline"

    def test_offline_no_userid_returns_400(self, client):
        r = client.post("/api/houses/HF_001/offline?listing_platform=安居客")
        assert r.status_code == 200
        assert r.json()["code"] == 400

    def test_offline_no_platform_returns_400(self, client):
        r = client.post("/api/houses/HF_001/offline", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 400

    def test_offline_invalid_house_returns_404(self, client):
        r = client.post("/api/houses/HF_999/offline?listing_platform=安居客", headers=USER_HEADER)
        assert r.status_code == 200
        assert r.json()["code"] == 404


# ─────────────────────────────────────────────────────────────────────────────
# 端点注册验证（AC1）
# ─────────────────────────────────────────────────────────────────────────────

class TestEndpointRegistration:
    """AC1: 验证 15 个端点均已注册。"""

    EXPECTED_ROUTES = [
        ("GET", "/api/landmarks"),
        ("GET", "/api/landmarks/name/{name}"),
        ("GET", "/api/landmarks/search"),
        ("GET", "/api/landmarks/stats"),
        ("GET", "/api/landmarks/{landmark_id}"),
        ("GET", "/api/houses/stats"),
        ("GET", "/api/houses/listings/{house_id}"),
        ("GET", "/api/houses/by_community"),
        ("GET", "/api/houses/by_platform"),
        ("GET", "/api/houses/nearby"),
        ("GET", "/api/houses/nearby_landmarks"),
        ("GET", "/api/houses/{house_id}"),
        ("POST", "/api/houses/init"),
        ("POST", "/api/houses/{house_id}/rent"),
        ("POST", "/api/houses/{house_id}/terminate"),
        ("POST", "/api/houses/{house_id}/offline"),
    ]

    def test_all_endpoints_registered(self):
        app = create_mock_rental_app(CONFIG, FIXTURES)
        route_map = set()
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    route_map.add((method, route.path))

        for method, path in self.EXPECTED_ROUTES:
            assert (method, path) in route_map, f"端点未注册: {method} {path}"

    def test_all_endpoints_no_5xx(self):
        """15 个端点均不返回 5xx。"""
        app = create_mock_rental_app(CONFIG, FIXTURES)
        endpoints = [
            ("GET", "/api/landmarks"),
            ("GET", "/api/landmarks/name/test"),
            ("GET", "/api/landmarks/search?q=test"),
            ("GET", "/api/landmarks/stats"),
            ("GET", "/api/landmarks/SS_001"),
            ("GET", "/api/houses/HF_001", {"X-User-ID": "u"}),
            ("GET", "/api/houses/listings/HF_001", {"X-User-ID": "u"}),
            ("GET", "/api/houses/by_community?community=上地嘉园", {"X-User-ID": "u"}),
            ("GET", "/api/houses/by_platform", {"X-User-ID": "u"}),
            ("GET", "/api/houses/nearby?landmark_id=SS_001&max_distance=2000", {"X-User-ID": "u"}),
            ("GET", "/api/houses/nearby_landmarks?community=上地嘉园", {"X-User-ID": "u"}),
            ("GET", "/api/houses/stats", {"X-User-ID": "u"}),
            ("POST", "/api/houses/init", {"X-User-ID": "u"}),
            ("POST", "/api/houses/HF_001/rent?listing_platform=安居客", {"X-User-ID": "u"}),
            ("POST", "/api/houses/HF_002/terminate?listing_platform=安居客", {"X-User-ID": "u"}),
            ("POST", "/api/houses/HF_002/offline?listing_platform=安居客", {"X-User-ID": "u"}),
        ]
        failed = []
        with TestClient(app) as tc:
            for entry in endpoints:
                method, path = entry[0], entry[1]
                headers = entry[2] if len(entry) > 2 else {}
                r = tc.request(method, path, headers=headers)
                if r.status_code >= 500:
                    failed.append(f"{method} {path} → {r.status_code}")
        assert not failed, "以下端点返回 5xx:\n" + "\n".join(failed)
