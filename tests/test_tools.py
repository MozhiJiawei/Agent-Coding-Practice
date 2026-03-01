"""
tests/test_tools.py — Story 3.1: tools.py 全量工具实现 TDD 测试

覆盖范围（Task 8）:
  8.1 — 6 个工具各自 happy path（mock httpx 响应）
  8.2 — 6 个工具各自 error path（mock httpx 抛异常）
  8.3 — search_houses 翻页逻辑（多页 mock，验证 all_items 合并）
  8.4 — TOOLS 常量结构验证（name 一致性、listing_platform enum 一致性）
  8.5 — execute_action 无效 action 返回 error dict
  8.6 — 全量回归由运行全套测试套件保障（此处仅包含 tools 测试）
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

from tools import (
    TOOLS,
    search_houses,
    get_house_detail,
    search_landmark,
    search_nearby_landmark,
    get_nearby_amenities,
    execute_action,
    get_houses_by_community,
    get_house_listings,
)

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_client():
    client = MagicMock(spec=httpx.AsyncClient)
    return client


def make_mock_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def make_error_response(status_code: int = 500):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock()
        )
    )
    return resp


# ─────────────────────────────────────────────
# Task 8.4 — TOOLS 常量结构验证
# ─────────────────────────────────────────────

class TestToolsConstant:
    """验证 TOOLS 常量格式与一致性（AC: 2）"""

    def test_tools_is_list(self):
        assert isinstance(TOOLS, list)

    def test_tools_has_six_entries(self):
        assert len(TOOLS) == 8

    def test_each_tool_has_type_function(self):
        for tool in TOOLS:
            assert tool.get("type") == "function", f"tool missing type=function: {tool}"

    def test_tool_names_match_python_functions(self):
        """每个 schema 的 name 字段必须与 Python 函数名完全一致"""
        expected_names = {
            "search_houses",
            "get_house_detail",
            "search_landmark",
            "search_nearby_landmark",
            "get_nearby_amenities",
            "execute_action",
            "get_houses_by_community",
            "get_house_listings",
        }
        actual_names = {tool["function"]["name"] for tool in TOOLS}
        assert actual_names == expected_names

    def test_listing_platform_enum_consistent(self):
        """search_houses / search_nearby_landmark / execute_action 的 listing_platform enum 必须一致"""
        expected_enum = ["链家", "安居客", "58同城"]
        tools_with_platform = ["search_houses", "search_nearby_landmark", "execute_action"]
        for tool in TOOLS:
            name = tool["function"]["name"]
            if name in tools_with_platform:
                props = tool["function"]["parameters"]["properties"]
                assert "listing_platform" in props, f"{name} missing listing_platform"
                actual_enum = props["listing_platform"].get("enum")
                assert actual_enum == expected_enum, (
                    f"{name} listing_platform enum mismatch: {actual_enum}"
                )

    def test_search_houses_has_no_required_params(self):
        for tool in TOOLS:
            if tool["function"]["name"] == "search_houses":
                required = tool["function"]["parameters"].get("required", [])
                assert required == [], f"search_houses should have no required params, got {required}"

    def test_get_house_detail_requires_house_id(self):
        for tool in TOOLS:
            if tool["function"]["name"] == "get_house_detail":
                required = tool["function"]["parameters"].get("required", [])
                assert "house_id" in required

    def test_search_landmark_requires_query(self):
        for tool in TOOLS:
            if tool["function"]["name"] == "search_landmark":
                required = tool["function"]["parameters"].get("required", [])
                assert "query" in required

    def test_search_nearby_landmark_requires_landmark_id(self):
        for tool in TOOLS:
            if tool["function"]["name"] == "search_nearby_landmark":
                required = tool["function"]["parameters"].get("required", [])
                assert "landmark_id" in required

    def test_execute_action_required_fields(self):
        for tool in TOOLS:
            if tool["function"]["name"] == "execute_action":
                required = tool["function"]["parameters"].get("required", [])
                assert "action" in required
                assert "house_id" in required
                assert "listing_platform" in required


# ─────────────────────────────────────────────
# Task 8.1 — Happy paths (all 6 tools)
# ─────────────────────────────────────────────

class TestSearchHousesHappyPath:
    """AC: 3 — search_houses 正常调用"""

    @pytest.mark.anyio
    async def test_single_page_returns_items(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({
            "data": {"total": 2, "page_size": 10, "items": [{"id": "HF_1"}, {"id": "HF_2"}]}
        }))
        result = await search_houses(mock_client, district="海淀")
        assert result["total"] == 2
        assert len(result["items"]) == 2

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({
            "data": {"total": 1, "items": [{"id": "HF_1"}]}
        }))
        await search_houses(mock_client, district="朝阳")
        call_kwargs = mock_client.get.call_args
        assert "headers" in call_kwargs.kwargs
        assert "X-User-ID" in call_kwargs.kwargs["headers"]

    @pytest.mark.anyio
    async def test_none_params_not_sent(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({
            "data": {"total": 0, "items": []}
        }))
        await search_houses(mock_client, district=None, min_price=None, max_price=3000)
        call_kwargs = mock_client.get.call_args
        sent_params = call_kwargs.kwargs.get("params", {})
        assert "district" not in sent_params
        assert "min_price" not in sent_params
        assert "max_price" in sent_params

    @pytest.mark.anyio
    async def test_flat_response_structure(self, mock_client):
        """兼容无 data 包装的平铺响应"""
        mock_client.get = AsyncMock(return_value=make_mock_response({
            "total": 1, "items": [{"id": "HF_5"}]
        }))
        result = await search_houses(mock_client)
        assert result["total"] == 1
        assert result["items"][0]["id"] == "HF_5"

    @pytest.mark.anyio
    async def test_calls_correct_endpoint(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"total": 0, "items": []}}))
        await search_houses(mock_client)
        call_args = mock_client.get.call_args
        assert call_args.args[0] == "/api/houses/by_platform"

    @pytest.mark.anyio
    async def test_listing_platform_forwarded(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"total": 0, "items": []}}))
        await search_houses(mock_client, listing_platform="链家")
        params = mock_client.get.call_args.kwargs["params"]
        assert params.get("listing_platform") == "链家"


class TestGetHouseDetailHappyPath:
    """AC: 5 — get_house_detail 正常调用"""

    @pytest.mark.anyio
    async def test_returns_full_json(self, mock_client):
        house_data = {"id": "HF_10", "address": "北京市海淀区", "price": 5000}
        mock_client.get = AsyncMock(return_value=make_mock_response(house_data))
        result = await get_house_detail(mock_client, house_id="HF_10")
        assert result == house_data

    @pytest.mark.anyio
    async def test_house_id_as_string_in_url(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"id": "HF_25"}))
        await get_house_detail(mock_client, house_id="HF_25")
        call_args = mock_client.get.call_args
        assert "/api/houses/HF_25" in call_args.args[0]

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"id": "HF_1"}))
        await get_house_detail(mock_client, house_id="HF_1")
        call_kwargs = mock_client.get.call_args
        assert "headers" in call_kwargs.kwargs
        assert "X-User-ID" in call_kwargs.kwargs["headers"]


class TestSearchLandmarkHappyPath:
    """AC: 6 — search_landmark 正常调用"""

    @pytest.mark.anyio
    async def test_returns_landmark_list(self, mock_client):
        landmark_data = {"landmarks": [{"id": "LM_1", "name": "西二旗地铁站"}]}
        mock_client.get = AsyncMock(return_value=make_mock_response(landmark_data))
        result = await search_landmark(mock_client, query="西二旗")
        assert result == landmark_data

    @pytest.mark.anyio
    async def test_query_mapped_to_q_param(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_landmark(mock_client, query="国贸")
        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("q") == "国贸"
        assert "query" not in params  # TOOLS 用 query，API 用 q

    @pytest.mark.anyio
    async def test_no_x_user_id_header(self, mock_client):
        """地标接口不需要 X-User-ID"""
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_landmark(mock_client, query="百度")
        call_kwargs = mock_client.get.call_args
        sent_headers = call_kwargs.kwargs.get("headers", {})
        assert "X-User-ID" not in sent_headers

    @pytest.mark.anyio
    async def test_optional_params_included_when_provided(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_landmark(mock_client, query="地铁", category="地铁站", district="海淀")
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert params.get("category") == "地铁站"
        assert params.get("district") == "海淀"

    @pytest.mark.anyio
    async def test_none_optional_params_not_sent(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_landmark(mock_client, query="百度", category=None, district=None)
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert "category" not in params
        assert "district" not in params

    @pytest.mark.anyio
    async def test_calls_correct_endpoint(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_landmark(mock_client, query="西二旗")
        assert mock_client.get.call_args.args[0] == "/api/landmarks/search"


class TestSearchNearbyLandmarkHappyPath:
    """AC: 7 — search_nearby_landmark 正常调用"""

    @pytest.mark.anyio
    async def test_returns_nearby_houses(self, mock_client):
        nearby_data = {"items": [{"id": "HF_3", "walk_distance": 500, "walk_time": 6}]}
        mock_client.get = AsyncMock(return_value=make_mock_response(nearby_data))
        result = await search_nearby_landmark(mock_client, landmark_id="LM_1")
        assert result == nearby_data

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_nearby_landmark(mock_client, landmark_id="LM_1")
        assert "X-User-ID" in mock_client.get.call_args.kwargs["headers"]

    @pytest.mark.anyio
    async def test_none_params_not_sent(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_nearby_landmark(mock_client, landmark_id="LM_1", max_distance=None, min_price=2000)
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert "max_distance" not in params
        assert params.get("min_price") == 2000

    @pytest.mark.anyio
    async def test_calls_correct_endpoint(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await search_nearby_landmark(mock_client, landmark_id="LM_1")
        assert mock_client.get.call_args.args[0] == "/api/houses/nearby"


class TestGetNearbyAmenitiesHappyPath:
    """AC: 8 — get_nearby_amenities 正常调用"""

    @pytest.mark.anyio
    async def test_returns_amenities(self, mock_client):
        amenities_data = {"amenities": [{"name": "家乐福", "category": "商超", "distance": 300}]}
        mock_client.get = AsyncMock(return_value=make_mock_response(amenities_data))
        result = await get_nearby_amenities(mock_client, community="建清园(南区)")
        assert result == amenities_data

    @pytest.mark.anyio
    async def test_default_max_distance_1000(self, mock_client):
        """未提供 max_distance_m 时默认为 1000（FR16）"""
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await get_nearby_amenities(mock_client, community="建清园(南区)")
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert params.get("max_distance_m") == 1000

    @pytest.mark.anyio
    async def test_custom_max_distance_used(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await get_nearby_amenities(mock_client, community="建清园(南区)", max_distance_m=500)
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert params.get("max_distance_m") == 500

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await get_nearby_amenities(mock_client, community="建清园(南区)")
        assert "X-User-ID" in mock_client.get.call_args.kwargs["headers"]

    @pytest.mark.anyio
    async def test_optional_category_included_when_provided(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await get_nearby_amenities(mock_client, community="建清园(南区)", type="shopping")
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert params.get("type") == "shopping"

    @pytest.mark.anyio
    async def test_calls_correct_endpoint(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({}))
        await get_nearby_amenities(mock_client, community="建清园(南区)")
        assert mock_client.get.call_args.args[0] == "/api/houses/nearby_landmarks"


class TestExecuteActionHappyPath:
    """AC: 9 — execute_action 正常调用"""

    @pytest.mark.anyio
    async def test_rent_action(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({"status": "rented"}))
        result = await execute_action(mock_client, action="rent", house_id="HF_1", listing_platform="安居客")
        assert result == {"status": "rented"}

    @pytest.mark.anyio
    async def test_terminate_action(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({"status": "terminated"}))
        result = await execute_action(mock_client, action="terminate", house_id="HF_2", listing_platform="链家")
        assert result == {"status": "terminated"}

    @pytest.mark.anyio
    async def test_offline_action(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({"status": "offline"}))
        result = await execute_action(mock_client, action="offline", house_id="HF_3", listing_platform="58同城")
        assert result == {"status": "offline"}

    @pytest.mark.anyio
    async def test_uses_correct_url(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({}))
        await execute_action(mock_client, action="rent", house_id="HF_10", listing_platform="安居客")
        call_args = mock_client.post.call_args
        assert "/api/houses/HF_10/rent" in call_args.args[0]

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({}))
        await execute_action(mock_client, action="rent", house_id="HF_1", listing_platform="安居客")
        assert "X-User-ID" in mock_client.post.call_args.kwargs["headers"]

    @pytest.mark.anyio
    async def test_listing_platform_in_query_params(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({}))
        await execute_action(mock_client, action="rent", house_id="HF_1", listing_platform="链家")
        params = mock_client.post.call_args.kwargs.get("params", {})
        assert params.get("listing_platform") == "链家"
        json_body = mock_client.post.call_args.kwargs.get("json")
        assert not json_body

    @pytest.mark.anyio
    async def test_house_id_as_string(self, mock_client):
        mock_client.post = AsyncMock(return_value=make_mock_response({}))
        await execute_action(mock_client, action="rent", house_id="HF_25", listing_platform="安居客")
        call_args = mock_client.post.call_args
        assert "HF_25" in call_args.args[0]


# ─────────────────────────────────────────────
# Task 8.2 — Error paths (all 6 tools)
# ─────────────────────────────────────────────

class TestSearchHousesErrorPath:
    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        result = await search_houses(mock_client)
        assert "error" in result
        assert "search_houses failed" in result["error"]

    @pytest.mark.anyio
    async def test_http_error_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_error_response(500))
        result = await search_houses(mock_client)
        assert "error" in result
        assert "search_houses failed" in result["error"]

    @pytest.mark.anyio
    async def test_no_exception_raised(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        result = await search_houses(mock_client)
        assert isinstance(result, dict)  # 不抛异常，返回 dict


class TestGetHouseDetailErrorPath:
    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("Timeout"))
        result = await get_house_detail(mock_client, house_id="HF_1")
        assert "error" in result
        assert "get_house_detail failed" in result["error"]

    @pytest.mark.anyio
    async def test_no_exception_raised(self, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        result = await get_house_detail(mock_client, house_id="HF_1")
        assert isinstance(result, dict)


class TestSearchLandmarkErrorPath:
    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("DNS error"))
        result = await search_landmark(mock_client, query="西二旗")
        assert "error" in result
        assert "search_landmark failed" in result["error"]

    @pytest.mark.anyio
    async def test_no_exception_raised(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        result = await search_landmark(mock_client, query="百度")
        assert isinstance(result, dict)


class TestSearchNearbyLandmarkErrorPath:
    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("503 Service Unavailable"))
        result = await search_nearby_landmark(mock_client, landmark_id="LM_1")
        assert "error" in result
        assert "search_nearby_landmark failed" in result["error"]

    @pytest.mark.anyio
    async def test_no_exception_raised(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("network down"))
        result = await search_nearby_landmark(mock_client, landmark_id="LM_1")
        assert isinstance(result, dict)


class TestGetNearbyAmenitiesErrorPath:
    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("Read timeout"))
        result = await get_nearby_amenities(mock_client, community="建清园(南区)")
        assert "error" in result
        assert "get_nearby_amenities failed" in result["error"]

    @pytest.mark.anyio
    async def test_no_exception_raised(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        result = await get_nearby_amenities(mock_client, community="建清园(南区)")
        assert isinstance(result, dict)


class TestExecuteActionErrorPath:
    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.post = AsyncMock(side_effect=Exception("Connection reset"))
        result = await execute_action(mock_client, action="rent", house_id="HF_1", listing_platform="安居客")
        assert "error" in result
        assert "execute_action failed" in result["error"]

    @pytest.mark.anyio
    async def test_no_exception_raised(self, mock_client):
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        result = await execute_action(mock_client, action="rent", house_id="HF_1", listing_platform="安居客")
        assert isinstance(result, dict)


# ─────────────────────────────────────────────
# Task 8.3 — search_houses 翻页逻辑
# ─────────────────────────────────────────────

class TestSearchHousesPagination:
    """AC: 4 — 自动分页，最多 MAX_PAGES=5 页"""

    @pytest.mark.anyio
    async def test_two_page_pagination(self, mock_client):
        page1 = make_mock_response({
            "data": {"total": 15, "page_size": 10,
                     "items": [{"id": f"HF_{i}"} for i in range(10)]}
        })
        page2 = make_mock_response({
            "data": {"total": 15, "page_size": 10,
                     "items": [{"id": f"HF_{i}"} for i in range(10, 15)]}
        })
        mock_client.get = AsyncMock(side_effect=[page1, page2])
        result = await search_houses(mock_client)
        assert result["total"] == 15
        assert len(result["items"]) == 15
        assert mock_client.get.call_count == 2

    @pytest.mark.anyio
    async def test_max_pages_respected(self, mock_client):
        """total 超过 MAX_PAGES*page_size 时，最多请求 5 页"""
        def make_page(page_num):
            return make_mock_response({
                "data": {"total": 100, "page_size": 10,
                         "items": [{"id": f"HF_{page_num}_{i}"} for i in range(10)]}
            })
        pages = [make_page(p) for p in range(1, 10)]
        mock_client.get = AsyncMock(side_effect=pages)
        result = await search_houses(mock_client)
        assert mock_client.get.call_count == 5  # MAX_PAGES = 5
        assert len(result["items"]) == 50

    @pytest.mark.anyio
    async def test_single_page_no_extra_calls(self, mock_client):
        page1 = make_mock_response({
            "data": {"total": 3, "page_size": 10, "items": [{"id": f"HF_{i}"} for i in range(3)]}
        })
        mock_client.get = AsyncMock(return_value=page1)
        result = await search_houses(mock_client)
        assert mock_client.get.call_count == 1
        assert len(result["items"]) == 3

    @pytest.mark.anyio
    async def test_page_param_increments(self, mock_client):
        """验证每次请求的 page 参数正确递增"""
        page1 = make_mock_response({
            "data": {"total": 12, "items": [{"id": f"HF_{i}"} for i in range(10)]}
        })
        page2 = make_mock_response({
            "data": {"total": 12, "items": [{"id": f"HF_{i}"} for i in range(10, 12)]}
        })
        mock_client.get = AsyncMock(side_effect=[page1, page2])
        await search_houses(mock_client, district="海淀")

        calls = mock_client.get.call_args_list
        page1_params = calls[0].kwargs["params"]
        page2_params = calls[1].kwargs["params"]
        assert page1_params["page"] == 1
        assert page2_params["page"] == 2

    @pytest.mark.anyio
    async def test_pagination_error_on_second_page(self, mock_client):
        """第二页请求失败时，整体返回 error dict"""
        page1 = make_mock_response({
            "data": {"total": 15, "items": [{"id": f"HF_{i}"} for i in range(10)]}
        })
        mock_client.get = AsyncMock(side_effect=[page1, Exception("timeout on page 2")])
        result = await search_houses(mock_client)
        assert "error" in result
        assert "search_houses failed" in result["error"]


# ─────────────────────────────────────────────
# Task 8.5 — execute_action 无效 action
# ─────────────────────────────────────────────

class TestExecuteActionInvalidAction:
    """AC: 10 — 无效 action 返回 error dict，不抛异常，不发 HTTP 请求"""

    @pytest.mark.anyio
    async def test_unknown_action_returns_error_dict(self, mock_client):
        mock_client.post = AsyncMock()
        result = await execute_action(mock_client, action="buy", house_id="HF_1", listing_platform="安居客")
        assert "error" in result
        assert "execute_action failed" in result["error"]
        assert "buy" in result["error"]

    @pytest.mark.anyio
    async def test_unknown_action_no_http_call(self, mock_client):
        mock_client.post = AsyncMock()
        await execute_action(mock_client, action="delete", house_id="HF_1", listing_platform="安居客")
        mock_client.post.assert_not_called()

    @pytest.mark.anyio
    async def test_empty_action_returns_error_dict(self, mock_client):
        mock_client.post = AsyncMock()
        result = await execute_action(mock_client, action="", house_id="HF_1", listing_platform="安居客")
        assert "error" in result
        assert "execute_action failed" in result["error"]

    @pytest.mark.anyio
    async def test_valid_actions_accepted(self, mock_client):
        for action in ["rent", "terminate", "offline"]:
            mock_client.post = AsyncMock(return_value=make_mock_response({"ok": True}))
            result = await execute_action(mock_client, action=action, house_id="HF_1", listing_platform="安居客")
            assert "error" not in result, f"Valid action '{action}' should not return error"


# ─────────────────────────────────────────────
# get_houses_by_community 测试
# ─────────────────────────────────────────────

class TestGetHousesByCommunityHappyPath:
    """AC-5 — get_houses_by_community 正常调用"""

    @pytest.mark.anyio
    async def test_calls_correct_endpoint(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"items": []}}))
        await get_houses_by_community(mock_client, community="智学苑")
        assert mock_client.get.call_args.args[0] == "/api/houses/by_community"

    @pytest.mark.anyio
    async def test_community_in_params(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"items": []}}))
        await get_houses_by_community(mock_client, community="智学苑")
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert params.get("community") == "智学苑"

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"items": []}}))
        await get_houses_by_community(mock_client, community="智学苑")
        assert "X-User-ID" in mock_client.get.call_args.kwargs["headers"]

    @pytest.mark.anyio
    async def test_none_params_not_sent(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"items": []}}))
        await get_houses_by_community(mock_client, community="智学苑", listing_platform=None)
        params = mock_client.get.call_args.kwargs.get("params", {})
        assert "listing_platform" not in params

    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("Connection error"))
        result = await get_houses_by_community(mock_client, community="智学苑")
        assert "error" in result
        assert "get_houses_by_community failed" in result["error"]


# ─────────────────────────────────────────────
# get_house_listings 测试
# ─────────────────────────────────────────────

class TestGetHouseListingsHappyPath:
    """AC-6 — get_house_listings 正常调用"""

    @pytest.mark.anyio
    async def test_calls_correct_endpoint(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"items": []}}))
        await get_house_listings(mock_client, house_id="HF_1")
        assert mock_client.get.call_args.args[0] == "/api/houses/listings/HF_1"

    @pytest.mark.anyio
    async def test_uses_x_user_id_header(self, mock_client):
        mock_client.get = AsyncMock(return_value=make_mock_response({"data": {"items": []}}))
        await get_house_listings(mock_client, house_id="HF_1")
        assert "X-User-ID" in mock_client.get.call_args.kwargs["headers"]

    @pytest.mark.anyio
    async def test_exception_returns_error_dict(self, mock_client):
        mock_client.get = AsyncMock(side_effect=Exception("Timeout"))
        result = await get_house_listings(mock_client, house_id="HF_1")
        assert "error" in result
        assert "get_house_listings failed" in result["error"]
