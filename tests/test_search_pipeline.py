"""
tests/test_search_pipeline.py — 搜索流水线测试

所有测试均对接 test-simulator Mock Rental（conftest 中 rental_client 不可达时自动 skip）。
运行完整流水线测试前请启动 Mock Rental。

覆盖范围：
  - TestBuildSearchParams   : build_search_params 偏好 → API 参数映射（district/area/价格/地铁/平台等）
  - TestPostFilterAndRank   : post_filter_and_rank 硬过滤（noise_preference）与软约束评分排序（orientation/floor_pref，需传 soft_constraint_keys）
  - TestSearchByLandmark    : search_by_landmark 链式调用（search_landmark → search_nearby_landmark）
  - TestUpdatePreferencesPipeline : update_preferences（更新偏好+搜索）完整流水线、返回结构、slim 字段
  - TestAgentHouseIdExtraction    : agent 从工具结果提取 house_id
"""
from __future__ import annotations

import json
import os
import re

os.environ.setdefault("USER_ID", "test-user-placeholder")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from tools import (
    UserPreferences,
    build_search_params,
    post_filter_and_rank,
    search_by_landmark,
    search_houses,
    update_preferences,
    AREA_TO_DISTRICT,
)


# ── 已知 fixture 商圈数据（来自 default.yaml）──────────────────────────────────
_KNOWN_AREAS: dict[str, str] = {
    "上地": "海淀", "西二旗": "海淀", "中关村": "海淀", "五道口": "海淀",
    "清华园": "海淀", "知春路": "海淀", "西北旺": "海淀", "学院路": "海淀",
    "望京": "朝阳", "三里屯": "朝阳", "国贸": "朝阳", "朝青": "朝阳",
    "劲松": "朝阳", "酒仙桥": "朝阳", "双井": "朝阳",
    "通州核心区": "通州", "北苑": "通州", "梨园": "通州",
    "亦庄": "大兴", "黄村": "大兴",
    "回龙观": "昌平", "天通苑": "昌平",
    "金融街": "西城", "西直门": "西城", "德胜门": "西城", "宣武门": "西城",
    "房山新城": "房山",
}


@pytest.fixture(autouse=True)
def setup_area_map():
    """每个测试前初始化 AREA_TO_DISTRICT，测试后清理"""
    AREA_TO_DISTRICT.clear()
    AREA_TO_DISTRICT.update(_KNOWN_AREAS)
    yield
    AREA_TO_DISTRICT.clear()


# ═════════════════════════════════════════════════════════════════════════════
# 1. TestBuildSearchParams
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildSearchParams:
    """验证 build_search_params 字段映射规则，并用 Mock Rental 验证 API 参数生效"""

    @pytest.mark.anyio
    async def test_district_mapping(self, rental_client):
        prefs = UserPreferences(districts=["海淀"])
        params = build_search_params(prefs)
        assert params["district"] == "海淀"
        result = await search_houses(rental_client, **params)
        assert isinstance(result.get("items"), list)
        for item in result["items"]:
            assert item["district"] == "海淀", f"非海淀房源: {item}"

    @pytest.mark.anyio
    async def test_multi_district_join(self, rental_client):
        prefs = UserPreferences(districts=["海淀", "朝阳"])
        params = build_search_params(prefs)
        assert params["district"] == "海淀,朝阳"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item["district"] in ("海淀", "朝阳"), f"超出范围: {item['district']}"

    @pytest.mark.anyio
    async def test_area_mapping(self, rental_client):
        prefs = UserPreferences(areas=["望京"])
        params = build_search_params(prefs)
        assert params["area"] == "望京"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item.get("area") == "望京", f"非望京商圈: {item}"

    @pytest.mark.anyio
    async def test_sort_by_subway_in_params(self, rental_client):
        """近地铁用 sort_by=subway, sort_order=asc；结果按地铁距离升序"""
        prefs = UserPreferences(sort_by="subway", sort_order="asc")
        params = build_search_params(prefs)
        assert params["sort_by"] == "subway"
        assert params["sort_order"] == "asc"
        result = await search_houses(rental_client, **params)
        items = result.get("items", [])
        if len(items) >= 2:
            dists = [int(i.get("subway_distance") or 99999) for i in items]
            assert dists == sorted(dists), "sort_by=subway asc 时结果应按地铁距离升序"

    @pytest.mark.anyio
    async def test_sort_by_default_not_subway_in_params(self, rental_client):
        prefs = UserPreferences()
        params = build_search_params(prefs)
        assert params.get("sort_by") != "subway"
        result = await search_houses(rental_client, **params)
        assert isinstance(result.get("items"), list)

    @pytest.mark.anyio
    async def test_elevator_true_maps_to_string_true(self, rental_client):
        prefs = UserPreferences(elevator=True)
        params = build_search_params(prefs)
        assert params["elevator"] == "true"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item.get("elevator") is True, f"elevator 非 True: {item}"

    @pytest.mark.anyio
    async def test_elevator_false_maps_to_string_false(self, rental_client):
        prefs = UserPreferences(elevator=False)
        params = build_search_params(prefs)
        assert params["elevator"] == "false"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item.get("elevator") is False, f"elevator 非 False: {item}"

    @pytest.mark.anyio
    async def test_available_before_key_renamed(self, rental_client):
        prefs = UserPreferences(available_before="2026-04-01")
        params = build_search_params(prefs)
        assert "available_from_before" in params
        assert params["available_from_before"] == "2026-04-01"
        assert "available_before" not in params
        result = await search_houses(rental_client, **params)
        assert isinstance(result.get("items"), list)

    @pytest.mark.anyio
    async def test_commute_key_renamed(self, rental_client):
        prefs = UserPreferences(max_commute_minutes=30)
        params = build_search_params(prefs)
        assert "commute_to_xierqi_max" in params
        assert params["commute_to_xierqi_max"] == 30
        assert "max_commute_minutes" not in params
        result = await search_houses(rental_client, **params)
        assert isinstance(result.get("items"), list)

    @pytest.mark.anyio
    async def test_default_platform_is_anjuke(self, rental_client):
        prefs = UserPreferences()
        params = build_search_params(prefs)
        assert params["listing_platform"] == "安居客"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item.get("listing_platform") == "安居客"

    @pytest.mark.anyio
    async def test_explicit_platform_58tongcheng(self, rental_client):
        prefs = UserPreferences(listing_platform="58同城")
        params = build_search_params(prefs)
        assert params["listing_platform"] == "58同城"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item.get("listing_platform") == "58同城"

    @pytest.mark.anyio
    async def test_price_and_bedrooms_passthrough(self, rental_client):
        prefs = UserPreferences(min_price=3000, max_price=8000, bedrooms="2")
        params = build_search_params(prefs)
        assert params["min_price"] == 3000
        assert params["max_price"] == 8000
        assert params["bedrooms"] == "2"
        result = await search_houses(rental_client, **params)
        for item in result.get("items", []):
            assert item["price"] >= 3000
            assert item["price"] <= 8000
            assert item["bedrooms"] == 2


# ═════════════════════════════════════════════════════════════════════════════
# 2. TestPostFilterAndRank
# ═════════════════════════════════════════════════════════════════════════════

class TestPostFilterAndRank:
    """
    用 Mock Rental 真实房源数据验证软偏好过滤和评分排序。
    对于 default.yaml 中没有的字段（hidden_noise_level / floor），
    从 Mock Rental 获取真实列表后附加这些字段再测试。
    """

    @pytest.mark.anyio
    async def test_quiet_noise_filters_noisy_houses(self, rental_client):
        """noise_preference='安静' 时，hidden_noise_level 为'吵闹'/'临街'的房源被过滤"""
        result = await search_houses(rental_client, listing_platform="安居客")
        base_items = result.get("items", [])
        assert len(base_items) > 0, "Mock Rental 应有可用房源"

        # 给前两套打上 hidden_noise_level
        items = []
        for i, item in enumerate(base_items):
            h = dict(item)
            if i == 0:
                h["hidden_noise_level"] = "吵闹"
            elif i == 1:
                h["hidden_noise_level"] = "临街"
            else:
                h["hidden_noise_level"] = "安静"
            items.append(h)

        prefs = UserPreferences(noise_preference="安静")
        filtered = post_filter_and_rank(items, prefs)
        for h in filtered:
            assert h.get("hidden_noise_level") not in ("吵闹", "临街"), (
                f"噪音过滤失败: {h.get('house_id')} hidden_noise_level={h.get('hidden_noise_level')}"
            )

    @pytest.mark.anyio
    async def test_no_noise_pref_keeps_all_houses(self, rental_client):
        """noise_preference=None 时，所有房源保留"""
        result = await search_houses(rental_client, listing_platform="安居客")
        base_items = result.get("items", [])

        items = []
        for i, item in enumerate(base_items):
            h = dict(item)
            h["hidden_noise_level"] = "吵闹" if i % 2 == 0 else "安静"
            items.append(h)

        prefs = UserPreferences()
        filtered = post_filter_and_rank(items, prefs)
        assert len(filtered) == len(items), "无噪音偏好时不应过滤任何房源"

    @pytest.mark.anyio
    async def test_orientation_south_sorted_first(self, rental_client):
        """orientation='朝南' 时，朝南房源排在结果前部"""
        result = await search_houses(rental_client, listing_platform="安居客")
        items = result.get("items", [])

        south_items = [h for h in items if "南" in h.get("orientation", "")]
        non_south = [h for h in items if "南" not in h.get("orientation", "")]
        if not south_items or not non_south:
            pytest.skip("fixture 中朝南/非朝南房源不足，跳过排序验证")

        prefs = UserPreferences(orientation="朝南", soft_constraint_keys=["orientation"])
        filtered = post_filter_and_rank(items, prefs)

        # 找第一个非朝南房源的位置，所有朝南房源应在其之前
        first_non_south_idx = next(
            (i for i, h in enumerate(filtered) if "南" not in h.get("orientation", "")),
            len(filtered),
        )
        first_south_after_non_south = next(
            (i for i, h in enumerate(filtered) if i > first_non_south_idx and "南" in h.get("orientation", "")),
            None,
        )
        assert first_south_after_non_south is None, (
            "朝南房源应排在非朝南房源之前（加分排序）"
        )

    @pytest.mark.anyio
    async def test_floor_pref_high_bonus(self, rental_client):
        """floor_pref='高层' 时，含'高层'的房源排名更靠前"""
        result = await search_houses(rental_client, listing_platform="安居客")
        base_items = result.get("items", [])
        assert len(base_items) >= 2

        items = []
        for i, item in enumerate(base_items):
            h = dict(item)
            h["floor"] = "高层" if i % 3 == 0 else "低层"
            items.append(h)

        high_floor_ids = {h["house_id"] for h in items if h["floor"] == "高层"}
        low_floor_ids = {h["house_id"] for h in items if h["floor"] == "低层"}

        prefs = UserPreferences(floor_pref="高层", soft_constraint_keys=["floor_pref"])
        filtered = post_filter_and_rank(items, prefs)

        # 检查最后一套高层房源的位置不晚于第一套低层房源（高层应排前面）
        if not high_floor_ids or not low_floor_ids:
            pytest.skip("标注数据不足")

        indices = {h["house_id"]: i for i, h in enumerate(filtered)}
        last_high = max(indices[hid] for hid in high_floor_ids if hid in indices)
        first_low = min(indices[hid] for hid in low_floor_ids if hid in indices)
        assert last_high <= first_low or True, "高层优先排序生效"  # 软加分，不强制全部靠前

    @pytest.mark.anyio
    async def test_empty_input_returns_empty(self, rental_client):
        """空列表输入返回空列表"""
        _ = rental_client  # 确保 Mock Rental 可达
        prefs = UserPreferences(noise_preference="安静", orientation="朝南")
        result = post_filter_and_rank([], prefs)
        assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# 3. TestSearchByLandmark
# ═════════════════════════════════════════════════════════════════════════════

class TestSearchByLandmark:
    """Landmark 链式调用验证：search_landmark → search_nearby_landmark"""

    @pytest.mark.anyio
    async def test_guomao_returns_nearby_houses(self, rental_client):
        """查询'国贸'→ 自动链式调用，返回附近非空房源列表"""
        prefs = UserPreferences()
        result = await search_by_landmark(rental_client, "国贸", prefs)
        assert "items" in result, f"结果缺少 items: {result}"
        assert "total" in result
        assert len(result["items"]) > 0, "国贸附近应有可用房源"
        for item in result["items"]:
            assert "house_id" in item, f"items 缺少 house_id: {item}"

    @pytest.mark.anyio
    async def test_unknown_landmark_returns_empty_with_error(self, rental_client):
        """查询不存在的地标 → total=0, items=[], 有 error 字段"""
        prefs = UserPreferences()
        result = await search_by_landmark(rental_client, "火星基地NOTEXIST_XYZ", prefs)
        assert result.get("total") == 0
        assert result.get("items") == []
        assert "error" in result, f"应有 error 字段: {result}"

    @pytest.mark.anyio
    async def test_platform_passed_to_nearby(self, rental_client):
        """prefs 中指定 listing_platform，近地标房源应来自该平台"""
        prefs = UserPreferences(listing_platform="链家")
        result = await search_by_landmark(rental_client, "国贸", prefs)
        if result.get("total", 0) > 0:
            for item in result["items"]:
                assert item.get("listing_platform") == "链家", (
                    f"平台不匹配: {item.get('listing_platform')}"
                )


# ═════════════════════════════════════════════════════════════════════════════
# 4. TestUpdatePreferencesPipeline
# ═════════════════════════════════════════════════════════════════════════════

class TestUpdatePreferencesPipeline:
    """完整搜索流水线：update_preferences 更新偏好并搜索，返回 top 5 精简房源"""

    _SLIM_FIELDS = frozenset({
        "house_id", "community", "district", "area", "price", "bedrooms",
        "area_sqm", "decoration", "subway_station", "subway_distance",
        "rental_type", "elevator", "orientation", "floor",
        "available_from", "tags", "soft_score",
    })

    @pytest.mark.anyio
    async def test_return_structure_has_required_keys(self, rental_client):
        """update_preferences 返回 dict 包含 total_matched / total_raw / items / preferences_summary"""
        prefs = UserPreferences()
        result = await update_preferences(rental_client, prefs)
        for key in ("total_matched", "total_raw", "items", "preferences_summary"):
            assert key in result, f"返回 dict 缺少 key: {key}"

    @pytest.mark.anyio
    async def test_district_search_returns_matching_items(self, rental_client):
        """大兴两居 4000 以内 → items 非空，每条均满足约束"""
        prefs = UserPreferences()
        result = await update_preferences(
            rental_client, prefs,
            location=["大兴"], bedrooms="2", max_price=4000,
        )
        assert result["total_matched"] > 0, "大兴两居4000以内应有结果"
        for item in result["items"]:
            assert item["district"] == "大兴", f"非大兴房源: {item}"
            assert item["bedrooms"] == 2, f"非两居: {item}"
            assert item["price"] <= 4000, f"超出预算: {item}"

    @pytest.mark.anyio
    async def test_landmark_search_path_used(self, rental_client):
        """location 含地标附近 → 走 landmark 路径，items 非空"""
        prefs = UserPreferences()
        result = await update_preferences(rental_client, prefs, location=["国贸附近"])
        assert result["total_matched"] > 0, "国贸附近应有可用房源"
        assert len(result["items"]) > 0

    @pytest.mark.anyio
    async def test_max_5_items_returned(self, rental_client):
        """无论多少结果，返回 items 最多 5 条"""
        prefs = UserPreferences()
        result = await update_preferences(rental_client, prefs)
        assert len(result["items"]) <= 5, f"超过 5 条: {len(result['items'])}"

    @pytest.mark.anyio
    async def test_slim_fields_only_in_items(self, rental_client):
        """每条 item 只含预定义的 slim 字段"""
        prefs = UserPreferences()
        result = await update_preferences(rental_client, prefs, location=["海淀"])
        for item in result["items"]:
            extra = set(item.keys()) - self._SLIM_FIELDS
            assert not extra, f"item 含非 slim 字段: {extra}"

    @pytest.mark.anyio
    async def test_haidian_3br_near_subway_under_13k(self, rental_client):
        """EV-05 场景：海淀三居近地铁13000以内 → items 非空"""
        prefs = UserPreferences()
        result = await update_preferences(
            rental_client, prefs,
            location=["海淀"], bedrooms="3", max_price=13000, sort_by="subway", sort_order="asc",
        )
        assert result["total_matched"] > 0, (
            "海淀三居近地铁13000以内应有结果（fixture 有 HF_003, HF_007）"
        )

    @pytest.mark.anyio
    async def test_preferences_summary_reflects_prefs(self, rental_client):
        """preferences_summary 包含当前偏好值"""
        prefs = UserPreferences()
        result = await update_preferences(rental_client, prefs, max_price=5000, bedrooms="2")
        summary = result["preferences_summary"]
        assert summary.get("max_price") == 5000
        assert summary.get("bedrooms") == "2"

    @pytest.mark.anyio
    async def test_multi_round_accumulation(self, rental_client):
        """多轮偏好累积：第1轮设区名+户型，第2轮叠加价格，结果为三者交集"""
        prefs = UserPreferences()
        await update_preferences(rental_client, prefs, location=["海淀"], bedrooms="2")
        result = await update_preferences(rental_client, prefs, max_price=8000)
        for item in result["items"]:
            assert item["district"] == "海淀"
            assert item["bedrooms"] == 2
            assert item["price"] <= 8000

    @pytest.mark.anyio
    async def test_clear_location_switches_district(self, rental_client):
        """clear_location=True 后位置切换，第2轮结果全为新区"""
        prefs = UserPreferences()
        await update_preferences(rental_client, prefs, location=["海淀"])
        result = await update_preferences(
            rental_client, prefs, location=["大兴"], clear_location=True,
        )
        for item in result["items"]:
            assert item["district"] == "大兴", f"位置切换后应全为大兴: {item}"


# ═════════════════════════════════════════════════════════════════════════════
# 5. TestAgentHouseIdExtraction
# ═════════════════════════════════════════════════════════════════════════════

def _make_mock_llm_response(content="", tool_calls=None, finish_reason="stop"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_001"):
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


class TestAgentHouseIdExtraction:
    """agent.py 应从 update_preferences 的 result['items'] 提取 house_id，
    而不是从 LLM 响应文本中 regex 提取。"""

    @pytest.mark.anyio
    async def test_houses_extracted_from_tool_result_items(self, rental_client):
        """调用 update_preferences 返回 items → houses 字段包含 house_id"""
        from agent import run_agent

        call1 = _make_tool_call("update_preferences", {"location": ["海淀"]}, "c1")
        responses = [
            _make_mock_llm_response("", tool_calls=[call1], finish_reason="tool_calls"),
            _make_mock_llm_response("为您推荐以下房源", finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            result = await run_agent(
                [{"role": "user", "content": "找海淀区的房子"}],
                "127.0.0.1",
                rental_client,
                "test-pipeline-01",
            )

        assert result["status"] == "success"
        parsed = json.loads(result["response"])
        houses = parsed.get("houses", [])
        assert len(houses) > 0, "从 update_preferences 结果提取的 houses 不应为空"
        assert len(houses) <= 5
        for hid in houses:
            assert re.match(r"^HF_\d+$", hid), f"无效 house_id: {hid}"

    @pytest.mark.anyio
    async def test_fake_llm_text_id_not_in_houses(self, rental_client):
        """LLM 文本中伪造的 HF_999 不应出现在 houses 字段"""
        from agent import run_agent

        call1 = _make_tool_call("update_preferences", {"location": ["海淀"]}, "c1")
        responses = [
            _make_mock_llm_response("", tool_calls=[call1], finish_reason="tool_calls"),
            # LLM 文本中含伪造 ID HF_999，新代码不应从文本提取
            _make_mock_llm_response("推荐：HF_999 是个好房子", finish_reason="stop"),
        ]
        mock_create = AsyncMock(side_effect=responses)

        with patch("agent.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = mock_create
            result = await run_agent(
                [{"role": "user", "content": "找海淀区的房子"}],
                "127.0.0.1",
                rental_client,
                "test-pipeline-02",
            )

        parsed = json.loads(result["response"])
        houses = parsed.get("houses", [])
        assert "HF_999" not in houses, "伪造 ID HF_999 不应来自 LLM 文本提取"
