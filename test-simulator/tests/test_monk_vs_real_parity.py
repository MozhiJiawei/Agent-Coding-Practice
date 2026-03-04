"""
Monk vs 真实服务器行为一致性测试（test-simulator）。

使用 tools.py 的同一套调用请求 Monk（mock_rental），覆盖所有 API 及关键参数组合，
失败用例及原因写入 --parity-report 指定文件，便于内网与真实服务器结果对比。

运行（仅 Mock，默认最小 fixture）:
  cd test-simulator && pytest tests/test_monk_vs_real_parity.py -v --parity-report=mock_data/monk_vs_real_test_results.txt

内网真实服务器（同一套用例）:
  RENTAL_API_BASE=http://真实地址 USER_ID=xxx pytest tests/test_monk_vs_real_parity.py -v --parity-report=mock_data/real_server_test_results.txt

内网双端一致性（同时请求 mock 与内网 API，严格校验响应完全一致）:
  PARITY_DUAL=1 RENTAL_API_BASE=http://内网地址 USER_ID=xxx pytest tests/test_monk_vs_real_parity.py -v --parity-report=mock_data/parity_dual_results.txt

使用 final-test.yaml 做完整数据一致性验证（数据量大、耗时长）:
  PARITY_USE_FINAL_TEST=1 pytest tests/test_monk_vs_real_parity.py -v --parity-report=...
  或 PARITY_FIXTURE_PATH=path/to/final-test.yaml pytest ...
"""
from __future__ import annotations

import contextvars
import os
import sys
from datetime import datetime

# 必须在 import tools 之前设置 USER_ID
os.environ.setdefault("USER_ID", "parity-test-user")
# 项目根目录加入 path，以便 import tools
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# test-simulator 根已在 conftest 加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import logging
import pytest
import pytest_asyncio
import httpx
from config import SimulatorConfig, load_fixtures
from mock_rental import create_mock_rental_app

# 失败记录（供 conftest pytest_sessionfinish 写入报告）
PARITY_FAILURES: list[dict] = []
PARITY_RUNS: list[str] = []  # 每跑一个用例 append case_id，用于统计总数
PARITY_REPORT_META: dict = {}
# 双端模式：Mock 与内网 API 响应不一致时记录（mock_rental 行为须与内网 API 完全一致）
PARITY_DUAL_FAILURES: list[dict] = []

logger = logging.getLogger(__name__)

# 双端模式：PARITY_DUAL=1 且已设置 RENTAL_API_BASE 时，每次请求同时发往 mock 与 real 并严格比较响应
_PARITY_DUAL = os.environ.get("PARITY_DUAL") == "1" and bool(os.environ.get("RENTAL_API_BASE"))
_current_parity_case_id: contextvars.ContextVar[str] = contextvars.ContextVar("parity_case_id", default="")

# 可选：使用 final-test.yaml 做完整一致性验证（内网或本地有大文件时）
_PARITY_FIXTURE_PATH = os.environ.get("PARITY_FIXTURE_PATH", "")
_TEST_SIMULATOR_ROOT = os.path.join(os.path.dirname(__file__), "..")


# 实际加载的数据源描述（供报告使用）
_FIXTURE_SOURCE_LABEL: str = "minimal"


def _load_fixtures():
    global _FIXTURE_SOURCE_LABEL
    if _PARITY_FIXTURE_PATH and os.path.isfile(_PARITY_FIXTURE_PATH):
        _FIXTURE_SOURCE_LABEL = _PARITY_FIXTURE_PATH
        return load_fixtures(_PARITY_FIXTURE_PATH)
    rel_path = os.path.join(_TEST_SIMULATOR_ROOT, "mock_data", "final-test.yaml")
    if os.environ.get("PARITY_USE_FINAL_TEST") == "1" and os.path.isfile(rel_path):
        _FIXTURE_SOURCE_LABEL = "mock_data/final-test.yaml"
        return load_fixtures(rel_path)
    _FIXTURE_SOURCE_LABEL = "minimal"
    return _MINIMAL_FIXTURES


_MINIMAL_FIXTURES = {
    "landmarks": [
        {
            "id": "SS_001",
            "name": "西二旗站",
            "category": "subway",
            "district": "海淀",
            "longitude": 116.3289,
            "latitude": 40.0567,
            "details": {"lines": ["13号线", "昌平线"], "type": "transfer"},
        },
        {"id": "LM_008", "name": "中关村广场", "category": "landmark", "district": "海淀", "longitude": 116.3189, "latitude": 39.9856, "details": {"type": "shopping"}},
    ],
    "houses": [
        {
            "house_id": "HF_001",
            "community": "智学苑",
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
            "commute_to_xierqi": 36,
            "available_from": "2026-03-01",
            "tags": [],
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
            "commute_to_xierqi": 8,
            "available_from": "2026-03-15",
            "tags": [],
        },
    ],
}


def _record_fail(case_id: str, api_name: str, params_summary: str, reason: str):
    PARITY_FAILURES.append({
        "case_id": case_id,
        "api_name": api_name,
        "params_summary": params_summary,
        "reason": reason,
    })


def _params_summary(**kwargs) -> str:
    parts = [f"{k}={repr(v)}" for k, v in kwargs.items() if v is not None]
    return ", ".join(parts[:5]) + ("..." if len(parts) > 5 else "")


def record_parity_start(case_id: str) -> None:
    """每个用例开头调用：记录 case_id 并供双端模式失败时关联用例。"""
    PARITY_RUNS.append(case_id)
    _current_parity_case_id.set(case_id)


def _response_json_strict_equal(mock_body: dict, real_body: dict) -> tuple[bool, str]:
    """严格比较两段 JSON 响应是否完全一致（mock_rental 行为须与内网 API 完全一致）。"""
    if type(mock_body) != type(real_body):
        return False, f"type mismatch: {type(mock_body).__name__} vs {type(real_body).__name__}"
    if isinstance(mock_body, dict):
        mock_keys = set(mock_body.keys())
        real_keys = set(real_body.keys())
        if mock_keys != real_keys:
            only_mock = mock_keys - real_keys
            only_real = real_keys - mock_keys
            return False, f"keys differ: only_in_mock={only_mock!r}, only_in_real={only_real!r}"
        for k in mock_keys:
            ok, msg = _response_json_strict_equal(mock_body[k], real_body[k])
            if not ok:
                return False, f".{k}: {msg}"
        return True, ""
    if isinstance(mock_body, list):
        if len(mock_body) != len(real_body):
            return False, f"list length {len(mock_body)} vs {len(real_body)}"
        for i, (a, b) in enumerate(zip(mock_body, real_body)):
            ok, msg = _response_json_strict_equal(a, b)
            if not ok:
                return False, f"[{i}]: {msg}"
        return True, ""
    if mock_body != real_body:
        return False, f"value {mock_body!r} != {real_body!r}"
    return True, ""


def _log_dual_failure(case_id: str, reason: str, real_status: int, real_raw_response: str) -> None:
    """双端对比失败时，将服务端原始响应写入日志便于后续分析。"""
    max_log_len = 4000
    raw_preview = real_raw_response if len(real_raw_response) <= max_log_len else real_raw_response[:max_log_len] + "\n... (truncated)"
    logger.warning(
        "[双端对比失败] case_id=%s reason=%s real_status=%s\n服务端原始响应:\n%s",
        case_id,
        reason,
        real_status,
        raw_preview,
    )


class DualClient:
    """双端 Client：每次 get/post 同时发往 mock 与内网 API，严格比较响应后返回 mock 端结果。"""

    def __init__(self, client_mock: httpx.AsyncClient, client_real: httpx.AsyncClient) -> None:
        self._mock = client_mock
        self._real = client_real

    async def get(self, url: str, **kwargs) -> httpx.Response:
        resp_mock = await self._mock.get(url, **kwargs)
        resp_real = await self._real.get(url, **kwargs)
        self._compare(resp_mock, resp_real, "GET", url, kwargs)
        return resp_mock

    async def post(self, url: str, **kwargs) -> httpx.Response:
        resp_mock = await self._mock.post(url, **kwargs)
        resp_real = await self._real.post(url, **kwargs)
        self._compare(resp_mock, resp_real, "POST", url, kwargs)
        return resp_mock

    def _compare(
        self,
        resp_mock: httpx.Response,
        resp_real: httpx.Response,
        method: str,
        url: str,
        kwargs: dict,
    ) -> None:
        try:
            mock_json = resp_mock.json()
        except Exception as e:
            mock_json = {"_parse_error": str(e)}
        try:
            real_json = resp_real.json()
        except Exception as e:
            real_json = {"_parse_error": str(e)}
        ok, msg = _response_json_strict_equal(mock_json, real_json)
        if not ok:
            case_id = _current_parity_case_id.get() or "unknown"
            summary = _params_summary(**kwargs.get("params") or kwargs.get("json") or {})
            reason = f"Mock vs Real 响应不一致: {msg}"
            try:
                real_raw = resp_real.text
            except Exception:
                real_raw = repr(resp_real.content[:2000]) if resp_real.content else "(empty)"
            failure_entry = {
                "case_id": case_id,
                "api_name": f"{method} {url}",
                "params_summary": summary,
                "reason": reason,
                "mock_status": resp_mock.status_code,
                "real_status": resp_real.status_code,
                "real_raw_response": real_raw,
            }
            PARITY_DUAL_FAILURES.append(failure_entry)
            # 双端对比失败时记录服务端原始响应到日志，便于后续分析
            _log_dual_failure(case_id, reason, resp_real.status_code, real_raw)
            raise AssertionError(reason)

    async def aclose(self) -> None:
        await self._mock.aclose()
        await self._real.aclose()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fixtures():
    return _load_fixtures()


@pytest.fixture(scope="module")
def app(fixtures):
    config = SimulatorConfig(llm_proxy_url="http://localhost:8888", test_user_id=os.environ.get("USER_ID", "parity-test-user"))
    return create_mock_rental_app(config, fixtures)


@pytest.fixture(scope="module")
def base_url():
    return "http://testserver"


@pytest_asyncio.fixture(scope="module")
async def _app_lifespan(app):
    """Hold app lifespan open so app.state.mock_state and app.state.landmarks exist when using ASGITransport."""
    async with app.router.lifespan_context(app):
        yield


@pytest_asyncio.fixture
async def client(_app_lifespan, app, base_url):
    real_server = os.environ.get("RENTAL_API_BASE")
    if _PARITY_DUAL and real_server:
        transport = httpx.ASGITransport(app=app)
        client_mock = httpx.AsyncClient(transport=transport, base_url=base_url, timeout=30.0, trust_env=False)
        client_real = httpx.AsyncClient(base_url=real_server, timeout=30.0, trust_env=False)
        c = DualClient(client_mock, client_real)
    elif real_server:
        c = httpx.AsyncClient(base_url=real_server, timeout=30.0, trust_env=False)
    else:
        transport = httpx.ASGITransport(app=app)
        c = httpx.AsyncClient(transport=transport, base_url=base_url, timeout=30.0, trust_env=False)
    try:
        yield c
    finally:
        await c.aclose()
    PARITY_REPORT_META["timestamp"] = datetime.now().isoformat()
    PARITY_REPORT_META["base_url"] = real_server or base_url
    PARITY_REPORT_META["fixture_source"] = _FIXTURE_SOURCE_LABEL
    PARITY_REPORT_META["parity_dual"] = _PARITY_DUAL


# ---------------------------------------------------------------------------
# 导入 tools（在 env 和 path 就绪后）
# ---------------------------------------------------------------------------
from tools import (
    init_houses,
    search_houses,
    get_house_detail,
    search_landmark,
    search_nearby_landmark,
    get_nearby_amenities,
    get_houses_by_community,
    get_house_listings,
    execute_action,
    get_all_houses_for_debug,
    get_all_landmarks_for_debug,
)


# ---------------------------------------------------------------------------
# TestInitHouses
# ---------------------------------------------------------------------------
class TestInitHouses:
    @pytest.mark.asyncio
    async def test_init_houses_returns_ok(self, client):
        case_id = "init_houses_returns_ok"
        record_parity_start(case_id)
        try:
            r = await init_houses(client)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert "action" in data or "message" in data or "user_id" in data
        except Exception as e:
            _record_fail(case_id, "init_houses", "", str(e))
            raise

    @pytest.mark.asyncio
    async def test_init_houses_resets_state(self, client, fixtures):
        """rent → init → 验证房源恢复 available"""
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "init_houses_resets_state"
        record_parity_start(case_id)
        try:
            await execute_action(client, action="rent", house_id=house_id, listing_platform="安居客")
            r = await init_houses(client)
            assert "error" not in r, r.get("error", "")
            detail = await get_house_detail(client, house_id=house_id)
            data = detail.get("data", detail)
            assert data.get("status") == "available", f"expected available, got {data.get('status')}"
        except Exception as e:
            _record_fail(case_id, "init_houses", f"house_id={house_id}", str(e))
            raise


# ---------------------------------------------------------------------------
# TestSearchHouses (by_platform) — 覆盖全部 20+ 筛选参数
# ---------------------------------------------------------------------------
class TestSearchHouses:
    @pytest.mark.asyncio
    async def test_search_houses_no_params(self, client):
        case_id = "search_houses_no_params"
        record_parity_start(case_id)
        try:
            r = await search_houses(client)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
        except Exception as e:
            _record_fail(case_id, "search_houses", "", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_district_haidian(self, client):
        case_id = "search_houses_district_haidian"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, district="海淀")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("district") == "海淀"
        except Exception as e:
            _record_fail(case_id, "search_houses", "district=海淀", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_district_chaoyang(self, client):
        case_id = "search_houses_district_chaoyang"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, district="朝阳")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
        except Exception as e:
            _record_fail(case_id, "search_houses", "district=朝阳", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_max_price(self, client):
        case_id = "search_houses_max_price"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, district="海淀", max_price=5000)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert int(item.get("price", 0)) <= 5000
        except Exception as e:
            _record_fail(case_id, "search_houses", "district=海淀, max_price=5000", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_bedrooms_listing_platform(self, client):
        case_id = "search_houses_bedrooms_platform"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, district="海淀", bedrooms="2", listing_platform="链家")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
        except Exception as e:
            _record_fail(case_id, "search_houses", "district=海淀, bedrooms=2, listing_platform=链家", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_sort_by_price(self, client):
        case_id = "search_houses_sort_price"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, district="海淀", sort_by="price", sort_order="asc")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
        except Exception as e:
            _record_fail(case_id, "search_houses", "sort_by=price, sort_order=asc", str(e))
            raise

    # ── 新增：覆盖剩余筛选参数 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_houses_area(self, client, fixtures):
        area = fixtures["houses"][0].get("area", "上地")
        case_id = "search_houses_area"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, area=area)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("area") == area
        except Exception as e:
            _record_fail(case_id, "search_houses", f"area={area}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_min_price(self, client):
        case_id = "search_houses_min_price"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, min_price=4000)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert int(item.get("price", 0)) >= 4000
        except Exception as e:
            _record_fail(case_id, "search_houses", "min_price=4000", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_price_range(self, client):
        case_id = "search_houses_price_range"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, min_price=3000, max_price=4000)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                p = int(item.get("price", 0))
                assert 3000 <= p <= 4000, f"price {p} not in [3000, 4000]"
        except Exception as e:
            _record_fail(case_id, "search_houses", "min_price=3000, max_price=4000", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_rental_type(self, client):
        case_id = "search_houses_rental_type"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, rental_type="整租")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("rental_type") == "整租"
        except Exception as e:
            _record_fail(case_id, "search_houses", "rental_type=整租", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_decoration(self, client):
        case_id = "search_houses_decoration"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, decoration="精装")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("decoration") == "精装"
        except Exception as e:
            _record_fail(case_id, "search_houses", "decoration=精装", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_decoration_normalized(self, client):
        """Mock 服务器应将 '精装修' 归一化为 '精装' 进行匹配"""
        case_id = "search_houses_decoration_normalized"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, decoration="精装修")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("decoration") == "精装"
        except Exception as e:
            _record_fail(case_id, "search_houses", "decoration=精装修", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_elevator_true(self, client):
        case_id = "search_houses_elevator_true"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, elevator="true")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("elevator") is True
        except Exception as e:
            _record_fail(case_id, "search_houses", "elevator=true", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_elevator_false(self, client):
        case_id = "search_houses_elevator_false"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, elevator="false")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("elevator") is not True
        except Exception as e:
            _record_fail(case_id, "search_houses", "elevator=false", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_orientation(self, client):
        case_id = "search_houses_orientation"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, orientation="朝南")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("orientation") == "朝南"
        except Exception as e:
            _record_fail(case_id, "search_houses", "orientation=朝南", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_min_area(self, client):
        case_id = "search_houses_min_area"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, min_area=60)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert float(item.get("area_sqm", 0)) >= 60
        except Exception as e:
            _record_fail(case_id, "search_houses", "min_area=60", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_max_area(self, client):
        case_id = "search_houses_max_area"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, max_area=50)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert float(item.get("area_sqm", 0)) <= 50
        except Exception as e:
            _record_fail(case_id, "search_houses", "max_area=50", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_subway_line(self, client):
        case_id = "search_houses_subway_line"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, subway_line="13号线")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
        except Exception as e:
            _record_fail(case_id, "search_houses", "subway_line=13号线", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_max_subway_dist(self, client):
        case_id = "search_houses_max_subway_dist"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, max_subway_dist=400)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert int(item.get("subway_distance", 0)) <= 400
        except Exception as e:
            _record_fail(case_id, "search_houses", "max_subway_dist=400", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_subway_station(self, client, fixtures):
        station = fixtures["houses"][0].get("subway_station", "上地站")
        case_id = "search_houses_subway_station"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, subway_station=station)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("subway_station") == station
        except Exception as e:
            _record_fail(case_id, "search_houses", f"subway_station={station}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_commute_max(self, client):
        case_id = "search_houses_commute_max"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, commute_to_xierqi_max=20)
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert int(item.get("commute_to_xierqi", 10**9)) <= 20
        except Exception as e:
            _record_fail(case_id, "search_houses", "commute_to_xierqi_max=20", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_property_type(self, client):
        case_id = "search_houses_property_type"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, property_type="住宅")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("property_type") == "住宅"
        except Exception as e:
            _record_fail(case_id, "search_houses", "property_type=住宅", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_utilities_type(self, client):
        case_id = "search_houses_utilities_type"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, utilities_type="民水民电")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("utilities_type") == "民水民电"
        except Exception as e:
            _record_fail(case_id, "search_houses", "utilities_type=民水民电", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_available_before(self, client):
        case_id = "search_houses_available_before"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, available_from_before="2026-03-10")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("available_from", "9999") <= "2026-03-10"
        except Exception as e:
            _record_fail(case_id, "search_houses", "available_from_before=2026-03-10", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_multi_district(self, client):
        case_id = "search_houses_multi_district"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, district="海淀,朝阳")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("district") in ("海淀", "朝阳")
        except Exception as e:
            _record_fail(case_id, "search_houses", "district=海淀,朝阳", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_multi_bedrooms(self, client):
        case_id = "search_houses_multi_bedrooms"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, bedrooms="1,2")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("bedrooms") in (1, 2)
        except Exception as e:
            _record_fail(case_id, "search_houses", "bedrooms=1,2", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_sort_by_area_asc(self, client):
        case_id = "search_houses_sort_area_asc"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, sort_by="area", sort_order="asc")
            assert "error" not in r, r.get("error", "")
            items = r.get("items", [])
            if len(items) >= 2:
                areas = [float(i.get("area_sqm", 0)) for i in items]
                assert areas == sorted(areas), f"not sorted asc: {areas}"
        except Exception as e:
            _record_fail(case_id, "search_houses", "sort_by=area, sort_order=asc", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_sort_price_desc(self, client):
        case_id = "search_houses_sort_price_desc"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, sort_by="price", sort_order="desc")
            assert "error" not in r, r.get("error", "")
            items = r.get("items", [])
            if len(items) >= 2:
                prices = [int(i.get("price", 0)) for i in items]
                assert prices == sorted(prices, reverse=True), f"not sorted desc: {prices}"
        except Exception as e:
            _record_fail(case_id, "search_houses", "sort_by=price, sort_order=desc", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_sort_by_subway(self, client):
        case_id = "search_houses_sort_subway"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, sort_by="subway", sort_order="asc")
            assert "error" not in r, r.get("error", "")
            items = r.get("items", [])
            if len(items) >= 2:
                dists = [float(i.get("subway_distance", 0)) for i in items]
                assert dists == sorted(dists), f"not sorted asc: {dists}"
        except Exception as e:
            _record_fail(case_id, "search_houses", "sort_by=subway, sort_order=asc", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_auto_pagination(self, client):
        """page_size=1 时 tools.py 自动翻页，结果应包含所有匹配项"""
        case_id = "search_houses_auto_pagination"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, page_size=1)
            assert "error" not in r, r.get("error", "")
            assert r["total"] >= 1
            assert len(r["items"]) == r["total"], (
                f"auto-pagination mismatch: total={r['total']}, items={len(r['items'])}"
            )
        except Exception as e:
            _record_fail(case_id, "search_houses", "page_size=1", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_platform_lianjia(self, client):
        """指定链家平台，验证返回的 listing_platform"""
        case_id = "search_houses_platform_lianjia"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, listing_platform="链家")
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("listing_platform") == "链家"
        except Exception as e:
            _record_fail(case_id, "search_houses", "listing_platform=链家", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_platform_58(self, client):
        """指定 58 同城平台"""
        case_id = "search_houses_platform_58"
        record_parity_start(case_id)
        try:
            r = await search_houses(client, listing_platform="58同城")
            assert "error" not in r, r.get("error", "")
            for item in r.get("items", []):
                assert item.get("listing_platform") == "58同城"
        except Exception as e:
            _record_fail(case_id, "search_houses", "listing_platform=58同城", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_houses_combined_filters(self, client):
        """多条件组合过滤"""
        case_id = "search_houses_combined"
        record_parity_start(case_id)
        try:
            r = await search_houses(
                client,
                district="海淀",
                max_price=5000,
                bedrooms="2",
                rental_type="整租",
                elevator="true",
            )
            assert "error" not in r, r.get("error", "")
            assert "total" in r and "items" in r
            for item in r.get("items", []):
                assert item.get("district") == "海淀"
                assert int(item.get("price", 0)) <= 5000
                assert item.get("bedrooms") == 2
        except Exception as e:
            _record_fail(case_id, "search_houses",
                         "district=海淀, max_price=5000, bedrooms=2, rental_type=整租, elevator=true", str(e))
            raise


# ---------------------------------------------------------------------------
# TestGetHouseDetail
# ---------------------------------------------------------------------------
class TestGetHouseDetail:
    @pytest.mark.asyncio
    async def test_get_house_detail_exists(self, client, fixtures):
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "get_house_detail_exists"
        record_parity_start(case_id)
        try:
            r = await get_house_detail(client, house_id=house_id)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert data.get("house_id") == house_id or data.get("id") == house_id
        except Exception as e:
            _record_fail(case_id, "get_house_detail", f"house_id={house_id}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_house_detail_not_found(self, client):
        case_id = "get_house_detail_404"
        record_parity_start(case_id)
        try:
            r = await get_house_detail(client, house_id="HF_NONEXISTENT")
            assert "error" in r or r.get("code") != 0
        except Exception as e:
            _record_fail(case_id, "get_house_detail", "house_id=HF_NONEXISTENT", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_house_detail_response_fields(self, client, fixtures):
        """验证返回的详情包含关键字段"""
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "get_house_detail_response_fields"
        record_parity_start(case_id)
        try:
            r = await get_house_detail(client, house_id=house_id)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            required = {"house_id", "community", "district", "price", "bedrooms", "decoration"}
            missing = required - set(data.keys())
            assert not missing, f"missing fields: {missing}"
        except Exception as e:
            _record_fail(case_id, "get_house_detail", f"house_id={house_id}", str(e))
            raise


# ---------------------------------------------------------------------------
# TestSearchLandmark
# ---------------------------------------------------------------------------
class TestSearchLandmark:
    @pytest.mark.asyncio
    async def test_search_landmark_q(self, client, fixtures):
        name = fixtures["landmarks"][0]["name"]
        case_id = "search_landmark_q"
        record_parity_start(case_id)
        try:
            r = await search_landmark(client, query=name)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", data.get("landmarks", []))
            assert isinstance(items, list)
        except Exception as e:
            _record_fail(case_id, "search_landmark", f"query={name}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_landmark_with_category_district(self, client):
        case_id = "search_landmark_category_district"
        record_parity_start(case_id)
        try:
            r = await search_landmark(client, query="站", category="subway", district="海淀")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", data.get("landmarks", []))
            assert isinstance(items, list)
        except Exception as e:
            _record_fail(case_id, "search_landmark", "query=站, category=subway, district=海淀", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_landmark_no_results(self, client):
        """不存在的关键词应返回空列表而非报错"""
        case_id = "search_landmark_no_results"
        record_parity_start(case_id)
        try:
            r = await search_landmark(client, query="完全不存在的地标XYZ")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", data.get("landmarks", []))
            assert isinstance(items, list) and len(items) == 0
        except Exception as e:
            _record_fail(case_id, "search_landmark", "query=完全不存在的地标XYZ", str(e))
            raise


# ---------------------------------------------------------------------------
# TestSearchNearbyLandmark
# ---------------------------------------------------------------------------
class TestSearchNearbyLandmark:
    @pytest.mark.asyncio
    async def test_search_nearby_landmark_by_id(self, client, fixtures):
        lm = fixtures["landmarks"][0]
        lid = lm["id"]
        case_id = "search_nearby_landmark_by_id"
        record_parity_start(case_id)
        try:
            r = await search_nearby_landmark(client, landmark_id=lid, max_distance=2000)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            assert isinstance(items, list)
        except Exception as e:
            _record_fail(case_id, "search_nearby_landmark", f"landmark_id={lid}, max_distance=2000", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_nearby_landmark_by_name(self, client, fixtures):
        name = fixtures["landmarks"][0]["name"]
        case_id = "search_nearby_landmark_by_name"
        record_parity_start(case_id)
        try:
            r = await search_nearby_landmark(client, landmark_id=name, max_distance=5000, listing_platform="安居客")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            assert isinstance(items, list)
        except Exception as e:
            _record_fail(case_id, "search_nearby_landmark", f"landmark_id={name}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_nearby_landmark_not_found(self, client):
        """不存在的地标应返回 404 / error"""
        case_id = "search_nearby_landmark_not_found"
        record_parity_start(case_id)
        try:
            r = await search_nearby_landmark(client, landmark_id="NONEXISTENT_LM")
            assert "error" in r or r.get("code") != 0
        except Exception as e:
            _record_fail(case_id, "search_nearby_landmark", "landmark_id=NONEXISTENT_LM", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_nearby_landmark_small_radius(self, client, fixtures):
        """极小搜索半径（10m），验证距离过滤生效"""
        lm = fixtures["landmarks"][0]
        case_id = "search_nearby_landmark_small_radius"
        record_parity_start(case_id)
        try:
            r = await search_nearby_landmark(client, landmark_id=lm["id"], max_distance=10)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            assert isinstance(items, list)
            for item in items:
                assert item.get("distance_to_landmark", 0) <= 10
        except Exception as e:
            _record_fail(case_id, "search_nearby_landmark", f"landmark_id={lm['id']}, max_distance=10", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_nearby_landmark_distance_sorted(self, client, fixtures):
        """验证返回结果包含 distance_to_landmark 字段且按距离排序"""
        lm = fixtures["landmarks"][0]
        case_id = "search_nearby_landmark_distance_sorted"
        record_parity_start(case_id)
        try:
            r = await search_nearby_landmark(client, landmark_id=lm["id"], max_distance=5000)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            if items:
                dists = [item.get("distance_to_landmark", 0) for item in items]
                assert dists == sorted(dists), f"items not sorted by distance: {dists}"
        except Exception as e:
            _record_fail(case_id, "search_nearby_landmark", f"landmark_id={lm['id']}, max_distance=5000", str(e))
            raise

    @pytest.mark.asyncio
    async def test_search_nearby_landmark_with_platform(self, client, fixtures):
        """指定平台，验证 listing_platform 一致"""
        lm = fixtures["landmarks"][0]
        case_id = "search_nearby_landmark_platform"
        record_parity_start(case_id)
        try:
            r = await search_nearby_landmark(client, landmark_id=lm["id"], max_distance=5000, listing_platform="链家")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            for item in items:
                assert item.get("listing_platform") == "链家"
        except Exception as e:
            _record_fail(case_id, "search_nearby_landmark", f"landmark_id={lm['id']}, listing_platform=链家", str(e))
            raise


# ---------------------------------------------------------------------------
# TestGetNearbyAmenities (by_community)
# ---------------------------------------------------------------------------
class TestGetNearbyAmenities:
    @pytest.mark.asyncio
    async def test_get_nearby_amenities_community(self, client, fixtures):
        community = fixtures["houses"][0]["community"]
        case_id = "get_nearby_amenities_community"
        record_parity_start(case_id)
        try:
            r = await get_nearby_amenities(client, community=community, max_distance_m=1000)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            assert items is None or isinstance(items, list)
        except Exception as e:
            _record_fail(case_id, "get_nearby_amenities", f"community={community}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_nearby_amenities_with_type(self, client, fixtures):
        community = fixtures["houses"][0]["community"]
        case_id = "get_nearby_amenities_type"
        record_parity_start(case_id)
        try:
            r = await get_nearby_amenities(client, community=community, type="park", max_distance_m=3000)
            assert "error" not in r, r.get("error", "")
        except Exception as e:
            _record_fail(case_id, "get_nearby_amenities", f"community={community}, type=park", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_nearby_amenities_nonexistent_community(self, client):
        """不存在的小区应返回空列表而非报错"""
        case_id = "get_nearby_amenities_nonexistent"
        record_parity_start(case_id)
        try:
            r = await get_nearby_amenities(client, community="完全不存在的小区XYZ")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert data.get("total") == 0
        except Exception as e:
            _record_fail(case_id, "get_nearby_amenities", "community=完全不存在的小区XYZ", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_nearby_amenities_large_distance(self, client, fixtures):
        """大搜索半径，验证距离排序"""
        community = fixtures["houses"][0]["community"]
        case_id = "get_nearby_amenities_large_dist"
        record_parity_start(case_id)
        try:
            r = await get_nearby_amenities(client, community=community, max_distance_m=10000)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items") or []
            if len(items) >= 2:
                dists = [item.get("distance_m", 0) for item in items]
                assert dists == sorted(dists), f"not sorted by distance: {dists}"
        except Exception as e:
            _record_fail(case_id, "get_nearby_amenities", f"community={community}, max_distance_m=10000", str(e))
            raise


# ---------------------------------------------------------------------------
# TestGetHousesByCommunity
# ---------------------------------------------------------------------------
class TestGetHousesByCommunity:
    @pytest.mark.asyncio
    async def test_get_houses_by_community(self, client, fixtures):
        community = fixtures["houses"][0]["community"]
        case_id = "get_houses_by_community"
        record_parity_start(case_id)
        try:
            r = await get_houses_by_community(client, community=community)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert "total" in data and "items" in data
        except Exception as e:
            _record_fail(case_id, "get_houses_by_community", f"community={community}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_houses_by_community_platform_page(self, client, fixtures):
        community = fixtures["houses"][0]["community"]
        case_id = "get_houses_by_community_platform_page"
        record_parity_start(case_id)
        try:
            r = await get_houses_by_community(client, community=community, listing_platform="58同城", page=1, page_size=5)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert "items" in data
        except Exception as e:
            _record_fail(case_id, "get_houses_by_community", f"community={community}, listing_platform=58同城", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_houses_by_community_nonexistent(self, client):
        """不存在的小区应返回空列表"""
        case_id = "get_houses_by_community_nonexistent"
        record_parity_start(case_id)
        try:
            r = await get_houses_by_community(client, community="完全不存在的小区XYZ")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert data.get("total") == 0
        except Exception as e:
            _record_fail(case_id, "get_houses_by_community", "community=完全不存在的小区XYZ", str(e))
            raise


# ---------------------------------------------------------------------------
# TestGetHouseListings
# ---------------------------------------------------------------------------
class TestGetHouseListings:
    @pytest.mark.asyncio
    async def test_get_house_listings_exists(self, client, fixtures):
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "get_house_listings_exists"
        record_parity_start(case_id)
        try:
            r = await get_house_listings(client, house_id=house_id)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            assert isinstance(items, list) and len(items) >= 1
        except Exception as e:
            _record_fail(case_id, "get_house_listings", f"house_id={house_id}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_house_listings_not_found(self, client):
        case_id = "get_house_listings_404"
        record_parity_start(case_id)
        try:
            r = await get_house_listings(client, house_id="HF_NONE")
            assert "error" in r or r.get("code") != 0
        except Exception as e:
            _record_fail(case_id, "get_house_listings", "house_id=HF_NONE", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_house_listings_all_platforms(self, client, fixtures):
        """验证返回 3 个平台的挂牌记录"""
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "get_house_listings_all_platforms"
        record_parity_start(case_id)
        try:
            r = await get_house_listings(client, house_id=house_id)
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            items = data.get("items", [])
            platforms_seen = {item.get("listing_platform") for item in items}
            assert len(platforms_seen) >= 3, f"expected >=3 platforms, got {platforms_seen}"
            for item in items:
                assert "price" in item, f"missing price for {item.get('listing_platform')}"
        except Exception as e:
            _record_fail(case_id, "get_house_listings", f"house_id={house_id}", str(e))
            raise


# ---------------------------------------------------------------------------
# TestExecuteAction
# ---------------------------------------------------------------------------
class TestExecuteAction:
    @pytest.mark.asyncio
    async def test_execute_action_rent(self, client, fixtures):
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "execute_action_rent"
        record_parity_start(case_id)
        try:
            r = await execute_action(client, action="rent", house_id=house_id, listing_platform="安居客")
            assert "error" not in r, r.get("error", "")
        except Exception as e:
            _record_fail(case_id, "execute_action", f"action=rent, house_id={house_id}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_execute_action_terminate(self, client, fixtures):
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "execute_action_terminate"
        record_parity_start(case_id)
        try:
            r = await execute_action(client, action="terminate", house_id=house_id, listing_platform="链家")
            assert "error" not in r, r.get("error", "")
        except Exception as e:
            _record_fail(case_id, "execute_action", f"action=terminate, house_id={house_id}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_execute_action_offline(self, client, fixtures):
        house_id = fixtures["houses"][1]["house_id"]
        case_id = "execute_action_offline"
        record_parity_start(case_id)
        try:
            r = await execute_action(client, action="offline", house_id=house_id, listing_platform="58同城")
            assert "error" not in r, r.get("error", "")
        except Exception as e:
            _record_fail(case_id, "execute_action", f"action=offline, house_id={house_id}", str(e))
            raise

    @pytest.mark.asyncio
    async def test_execute_action_invalid_returns_error(self, client):
        case_id = "execute_action_invalid"
        record_parity_start(case_id)
        try:
            r = await execute_action(client, action="invalid_action", house_id="HF_001", listing_platform="安居客")
            assert "error" in r and "unknown action" in r.get("error", "").lower()
        except Exception as e:
            _record_fail(case_id, "execute_action", "action=invalid_action", str(e))
            raise

    @pytest.mark.asyncio
    async def test_execute_action_house_not_found(self, client):
        """对不存在的房源执行操作应返回 404 / error"""
        case_id = "execute_action_house_not_found"
        record_parity_start(case_id)
        try:
            r = await execute_action(client, action="rent", house_id="HF_NONEXISTENT", listing_platform="安居客")
            assert "error" in r or r.get("code") != 0
        except Exception as e:
            _record_fail(case_id, "execute_action", "action=rent, house_id=HF_NONEXISTENT", str(e))
            raise

    @pytest.mark.asyncio
    async def test_execute_action_rent_then_verify(self, client, fixtures):
        """租房后验证状态变更，再恢复"""
        house_id = fixtures["houses"][0]["house_id"]
        case_id = "execute_action_rent_verify"
        record_parity_start(case_id)
        try:
            r = await execute_action(client, action="rent", house_id=house_id, listing_platform="安居客")
            assert "error" not in r, r.get("error", "")
            data = r.get("data", r)
            assert data.get("status") == "rented", f"expected rented, got {data.get('status')}"
            await execute_action(client, action="terminate", house_id=house_id, listing_platform="安居客")
        except Exception as e:
            _record_fail(case_id, "execute_action", f"action=rent+verify, house_id={house_id}", str(e))
            await execute_action(client, action="terminate", house_id=house_id, listing_platform="安居客")
            raise


# ---------------------------------------------------------------------------
# TestGetAllForDebug (optional)
# ---------------------------------------------------------------------------
class TestGetAllForDebug:
    @pytest.mark.asyncio
    async def test_get_all_landmarks_for_debug(self, client):
        case_id = "get_all_landmarks_for_debug"
        record_parity_start(case_id)
        try:
            r = await get_all_landmarks_for_debug(client)
            assert "error" not in r, r.get("error", "")
            assert "items" in r and "total" in r
        except Exception as e:
            _record_fail(case_id, "get_all_landmarks_for_debug", "", str(e))
            raise

    @pytest.mark.asyncio
    async def test_get_all_houses_for_debug(self, client):
        case_id = "get_all_houses_for_debug"
        record_parity_start(case_id)
        try:
            r = await get_all_houses_for_debug(client)
            assert isinstance(r, dict)
            for platform in ("链家", "安居客", "58同城"):
                assert platform in r
                assert "items" in r[platform]
        except Exception as e:
            _record_fail(case_id, "get_all_houses_for_debug", "", str(e))
            raise
