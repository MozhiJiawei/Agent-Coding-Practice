"""
tests/test_preferences.py — Story 8.1 TDD 测试

覆盖范围：
  - UserPreferences 模型字段完整性
  - resolve_location 路由逻辑（district / area / landmark_query）
  - build_area_district_map 映射构建
  - update_preferences 增量合并逻辑、clear_location 行为
"""
import os

os.environ.setdefault("USER_ID", "test-user-placeholder")

import pytest
from unittest.mock import MagicMock
import httpx

from tools import (
    UserPreferences,
    resolve_location,
    build_area_district_map,
    update_preferences,
    AREA_TO_DISTRICT,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_client():
    """保留给非 update_preferences 的测试使用"""
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def fresh_prefs():
    return UserPreferences()


@pytest.fixture(autouse=True)
def setup_area_map():
    """每个测试前设置 AREA_TO_DISTRICT，测试后清理"""
    AREA_TO_DISTRICT.clear()
    AREA_TO_DISTRICT.update({
        "望京": "朝阳",
        "西二旗": "海淀",
        "上地": "海淀",
        "亦庄": "大兴",
        "回龙观": "昌平",
    })
    yield
    AREA_TO_DISTRICT.clear()


# ─────────────────────────────────────────────
# UserPreferences 模型字段完整性
# ─────────────────────────────────────────────

class TestUserPreferencesModel:
    """AC-1: UserPreferences 包含设计文档中定义的所有字段"""

    def test_empty_init_defaults(self, fresh_prefs):
        assert fresh_prefs.location is None
        assert fresh_prefs.clear_location is False
        assert fresh_prefs.min_price is None
        assert fresh_prefs.max_price is None
        assert fresh_prefs.mentioned_house_ids == []
        assert fresh_prefs.current_focus_house_id is None

    def test_hard_constraint_fields_settable(self):
        prefs = UserPreferences(
            min_price=3000,
            max_price=8000,
            bedrooms="2",
            rental_type="整租",
            decoration="精装",
            elevator=True,
            min_area=50,
            max_area=100,
            utilities_type="民水民电",
            subway_line="13号线",
            near_subway=True,
            listing_platform="链家",
            available_before="2026-04-01",
            max_commute_minutes=30,
        )
        assert prefs.min_price == 3000
        assert prefs.max_price == 8000
        assert prefs.bedrooms == "2"
        assert prefs.rental_type == "整租"
        assert prefs.decoration == "精装"
        assert prefs.elevator is True
        assert prefs.min_area == 50
        assert prefs.max_area == 100
        assert prefs.utilities_type == "民水民电"
        assert prefs.subway_line == "13号线"
        assert prefs.near_subway is True
        assert prefs.listing_platform == "链家"
        assert prefs.available_before == "2026-04-01"
        assert prefs.max_commute_minutes == 30

    def test_soft_preference_fields_settable(self):
        prefs = UserPreferences(
            noise_preference="安静",
            orientation="朝南",
            floor_pref="高层",
            no_agent_fee=True,
            payment_method="月付",
        )
        assert prefs.noise_preference == "安静"
        assert prefs.orientation == "朝南"
        assert prefs.floor_pref == "高层"
        assert prefs.no_agent_fee is True
        assert prefs.payment_method == "月付"

    def test_context_memory_fields_default(self, fresh_prefs):
        assert fresh_prefs.mentioned_house_ids == []
        assert fresh_prefs.current_focus_house_id is None

    def test_internal_routing_fields_exist(self, fresh_prefs):
        """内部路由字段（代码写入，LLM不直接设置）应存在"""
        assert hasattr(fresh_prefs, "districts")
        assert hasattr(fresh_prefs, "areas")
        assert hasattr(fresh_prefs, "landmark_queries")

    def test_internal_routing_fields_default_none(self, fresh_prefs):
        assert fresh_prefs.districts is None
        assert fresh_prefs.areas is None
        assert fresh_prefs.landmark_queries is None

    def test_location_is_list_type(self):
        prefs = UserPreferences(location=["海淀", "朝阳"])
        assert prefs.location == ["海淀", "朝阳"]

    def test_bedrooms_accepts_comma_separated_string(self):
        prefs = UserPreferences(bedrooms="2,3")
        assert prefs.bedrooms == "2,3"


# ─────────────────────────────────────────────
# resolve_location 路由逻辑
# ─────────────────────────────────────────────

class TestResolveLocation:
    """AC-1: resolve_location 能正确路由 district / area / landmark_query 三种情况"""

    def test_district_name_direct(self):
        assert resolve_location("海淀") == {"district": "海淀"}

    def test_district_name_with_qu_suffix(self):
        assert resolve_location("海淀区") == {"district": "海淀"}

    def test_all_10_districts(self):
        districts = ["海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"]
        for d in districts:
            result = resolve_location(d)
            assert result == {"district": d}, f"区名路由失败: {d}"

    def test_all_10_districts_with_qu_suffix(self):
        districts = ["海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"]
        for d in districts:
            result = resolve_location(f"{d}区")
            assert result == {"district": d}, f"带'区'后缀路由失败: {d}区"

    def test_area_wangjing(self):
        result = resolve_location("望京")
        assert result == {"area": "望京", "district": "朝阳"}

    def test_area_xierqi(self):
        result = resolve_location("西二旗")
        assert result == {"area": "西二旗", "district": "海淀"}

    def test_area_shangdi(self):
        result = resolve_location("上地")
        assert result == {"area": "上地", "district": "海淀"}

    def test_area_yizhuang(self):
        result = resolve_location("亦庄")
        assert result == {"area": "亦庄", "district": "大兴"}

    def test_landmark_with_fujin_suffix(self):
        """国贸附近 → landmark_query: 国贸"""
        result = resolve_location("国贸附近")
        assert result == {"landmark_query": "国贸"}

    def test_landmark_with_fujin_suffix_other(self):
        result = resolve_location("望京SOHO附近")
        assert result == {"landmark_query": "望京SOHO"}

    def test_unknown_location_as_landmark(self):
        """未知位置 → landmark_query: 原始输入"""
        result = resolve_location("某神秘地点")
        assert result == {"landmark_query": "某神秘地点"}

    def test_company_name_as_landmark(self):
        result = resolve_location("百度科技园")
        assert result == {"landmark_query": "百度科技园"}

    def test_result_is_dict(self):
        result = resolve_location("海淀")
        assert isinstance(result, dict)


# ─────────────────────────────────────────────
# build_area_district_map
# ─────────────────────────────────────────────

class TestBuildAreaDistrictMap:
    """验证 build_area_district_map 正确构建 area → district 映射表"""

    def test_basic_mapping(self):
        houses = [
            {"area": "望京", "district": "朝阳"},
            {"area": "西二旗", "district": "海淀"},
        ]
        result = build_area_district_map(houses)
        assert result["望京"] == "朝阳"
        assert result["西二旗"] == "海淀"

    def test_deduplication(self):
        houses = [
            {"area": "望京", "district": "朝阳"},
            {"area": "望京", "district": "朝阳"},
            {"area": "望京", "district": "朝阳"},
        ]
        result = build_area_district_map(houses)
        assert result["望京"] == "朝阳"
        assert len(result) == 1

    def test_empty_houses_returns_empty_dict(self):
        result = build_area_district_map([])
        assert result == {}

    def test_missing_area_field_skipped(self):
        houses = [
            {"district": "海淀"},
            {"area": "上地", "district": "海淀"},
        ]
        result = build_area_district_map(houses)
        assert "上地" in result
        assert len(result) == 1

    def test_missing_district_field_skipped(self):
        houses = [
            {"area": "望京"},
            {"area": "上地", "district": "海淀"},
        ]
        result = build_area_district_map(houses)
        assert "上地" in result
        assert "望京" not in result

    def test_none_area_skipped(self):
        houses = [
            {"area": None, "district": "海淀"},
            {"area": "上地", "district": "海淀"},
        ]
        result = build_area_district_map(houses)
        assert "上地" in result
        assert len(result) == 1

    def test_none_district_skipped(self):
        houses = [
            {"area": "望京", "district": None},
            {"area": "上地", "district": "海淀"},
        ]
        result = build_area_district_map(houses)
        assert "上地" in result
        assert "望京" not in result

    def test_multiple_areas_same_district(self):
        houses = [
            {"area": "西二旗", "district": "海淀"},
            {"area": "上地", "district": "海淀"},
            {"area": "中关村", "district": "海淀"},
        ]
        result = build_area_district_map(houses)
        assert result["西二旗"] == "海淀"
        assert result["上地"] == "海淀"
        assert result["中关村"] == "海淀"
        assert len(result) == 3

    def test_returns_dict(self):
        result = build_area_district_map([])
        assert isinstance(result, dict)


# ─────────────────────────────────────────────
# update_preferences 合并逻辑
# ─────────────────────────────────────────────

class TestUpdatePreferences:
    """AC-2/AC-3: update_preferences 合并偏好、resolve_location 路由、clear_location 行为
    所有测试对接 Mock Rental (rental_client)，Mock Rental 不可达时自动 skip。
    """

    @pytest.mark.anyio
    async def test_merge_price_fields(self, rental_client, fresh_prefs):
        result = await update_preferences(rental_client, fresh_prefs, max_price=5000)
        assert fresh_prefs.max_price == 5000
        assert isinstance(result, dict)

    @pytest.mark.anyio
    async def test_merge_multiple_fields(self, rental_client, fresh_prefs):
        await update_preferences(rental_client, fresh_prefs, bedrooms="2", max_price=4000, decoration="精装")
        assert fresh_prefs.bedrooms == "2"
        assert fresh_prefs.max_price == 4000
        assert fresh_prefs.decoration == "精装"

    @pytest.mark.anyio
    async def test_incremental_merge_across_calls(self, rental_client, fresh_prefs):
        """多轮调用时新字段添加，已有字段不清除"""
        await update_preferences(rental_client, fresh_prefs, bedrooms="2", max_price=4000)
        await update_preferences(rental_client, fresh_prefs, decoration="精装")
        assert fresh_prefs.bedrooms == "2"
        assert fresh_prefs.max_price == 4000
        assert fresh_prefs.decoration == "精装"

    @pytest.mark.anyio
    async def test_overwrite_existing_field(self, rental_client, fresh_prefs):
        """新值覆盖旧值"""
        await update_preferences(rental_client, fresh_prefs, max_price=5000)
        await update_preferences(rental_client, fresh_prefs, max_price=8000)
        assert fresh_prefs.max_price == 8000

    @pytest.mark.anyio
    async def test_location_stored(self, rental_client, fresh_prefs):
        await update_preferences(rental_client, fresh_prefs, location=["海淀"])
        assert fresh_prefs.location == ["海淀"]

    @pytest.mark.anyio
    async def test_district_location_resolved(self, rental_client, fresh_prefs):
        """区名 location 路由写入 districts 字段"""
        await update_preferences(rental_client, fresh_prefs, location=["海淀"])
        assert fresh_prefs.districts is not None
        assert "海淀" in fresh_prefs.districts

    @pytest.mark.anyio
    async def test_area_location_resolved(self, rental_client, fresh_prefs):
        """商圈 location 路由写入 areas 字段"""
        await update_preferences(rental_client, fresh_prefs, location=["望京"])
        assert fresh_prefs.areas is not None
        assert "望京" in fresh_prefs.areas

    @pytest.mark.anyio
    async def test_landmark_location_resolved(self, rental_client, fresh_prefs):
        """地标 location 路由写入 landmark_queries 字段"""
        await update_preferences(rental_client, fresh_prefs, location=["国贸附近"])
        assert fresh_prefs.landmark_queries is not None
        assert "国贸" in fresh_prefs.landmark_queries

    @pytest.mark.anyio
    async def test_multiple_locations_mixed(self, rental_client, fresh_prefs):
        """多个 location 可混合不同类型，路由结果分别写入 districts 和 areas"""
        await update_preferences(rental_client, fresh_prefs, location=["海淀", "望京"])
        assert fresh_prefs.location == ["海淀", "望京"]
        assert "海淀" in fresh_prefs.districts
        assert "朝阳" in fresh_prefs.districts
        assert "望京" in fresh_prefs.areas

    @pytest.mark.anyio
    async def test_clear_location_clears_previous(self, rental_client, fresh_prefs):
        """AC-3: clear_location=True 时清除历史位置"""
        await update_preferences(rental_client, fresh_prefs, location=["海淀"])
        await update_preferences(rental_client, fresh_prefs, location=["大兴"], clear_location=True)
        assert fresh_prefs.location == ["大兴"]
        assert fresh_prefs.districts is not None
        assert "海淀" not in fresh_prefs.districts
        assert "大兴" in fresh_prefs.districts

    @pytest.mark.anyio
    async def test_clear_location_clears_areas(self, rental_client, fresh_prefs):
        """clear_location 同时清除 areas 和 landmark_queries"""
        await update_preferences(rental_client, fresh_prefs, location=["望京"])
        await update_preferences(rental_client, fresh_prefs, location=["大兴"], clear_location=True)
        assert fresh_prefs.areas is None or "望京" not in fresh_prefs.areas

    @pytest.mark.anyio
    async def test_without_clear_location_accumulates(self, rental_client, fresh_prefs):
        """不设 clear_location 时，新 location 累加"""
        await update_preferences(rental_client, fresh_prefs, location=["海淀"])
        await update_preferences(rental_client, fresh_prefs, location=["朝阳"])
        assert fresh_prefs.location is not None
        assert "海淀" in fresh_prefs.location
        assert "朝阳" in fresh_prefs.location

    @pytest.mark.anyio
    async def test_returns_dict_with_new_format(self, rental_client, fresh_prefs):
        """返回值是 dict，包含新格式的必要字段"""
        result = await update_preferences(rental_client, fresh_prefs, max_price=5000)
        assert isinstance(result, dict)
        assert "items" in result
        assert "preferences_summary" in result

    @pytest.mark.anyio
    async def test_returns_preferences_summary_with_current_prefs(self, rental_client, fresh_prefs):
        """返回值的 preferences_summary 包含当前偏好值"""
        result = await update_preferences(rental_client, fresh_prefs, max_price=5000, bedrooms="2")
        assert result["preferences_summary"]["max_price"] == 5000
        assert result["preferences_summary"]["bedrooms"] == "2"

    @pytest.mark.anyio
    async def test_near_subway_bool(self, rental_client, fresh_prefs):
        await update_preferences(rental_client, fresh_prefs, near_subway=True)
        assert fresh_prefs.near_subway is True

    @pytest.mark.anyio
    async def test_elevator_bool(self, rental_client, fresh_prefs):
        await update_preferences(rental_client, fresh_prefs, elevator=True)
        assert fresh_prefs.elevator is True

    @pytest.mark.anyio
    async def test_max_commute_minutes(self, rental_client, fresh_prefs):
        await update_preferences(rental_client, fresh_prefs, max_commute_minutes=30)
        assert fresh_prefs.max_commute_minutes == 30

    @pytest.mark.anyio
    async def test_no_extra_args_no_error(self, rental_client, fresh_prefs):
        """空调用不报错"""
        result = await update_preferences(rental_client, fresh_prefs)
        assert isinstance(result, dict)


# ─────────────────────────────────────────────
# update_preferences schema 不包含内部字段
# ─────────────────────────────────────────────

class TestUpdatePreferencesSchema:
    """AC-2: TOOLS 中 update_preferences schema 不暴露内部字段"""

    def test_schema_exists(self):
        from tools import TOOLS
        names = [t["function"]["name"] for t in TOOLS]
        assert "update_preferences" in names

    def test_schema_no_districts_field(self):
        from tools import TOOLS
        tool = next(t for t in TOOLS if t["function"]["name"] == "update_preferences")
        props = tool["function"]["parameters"]["properties"]
        assert "districts" not in props
        assert "areas" not in props
        assert "landmark_queries" not in props

    def test_schema_has_location_field(self):
        from tools import TOOLS
        tool = next(t for t in TOOLS if t["function"]["name"] == "update_preferences")
        props = tool["function"]["parameters"]["properties"]
        assert "location" in props
        assert props["location"]["type"] == "array"

    def test_schema_has_clear_location(self):
        from tools import TOOLS
        tool = next(t for t in TOOLS if t["function"]["name"] == "update_preferences")
        props = tool["function"]["parameters"]["properties"]
        assert "clear_location" in props
        assert props["clear_location"]["type"] == "boolean"

    def test_schema_required_is_empty(self):
        from tools import TOOLS
        tool = next(t for t in TOOLS if t["function"]["name"] == "update_preferences")
        required = tool["function"]["parameters"].get("required", [])
        assert required == []
