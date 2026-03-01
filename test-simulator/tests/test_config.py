"""
Story 5.1 测试套件：配置系统重构与 Fixture 数据集创建
覆盖 AC1, AC2, AC3, AC4, AC5, AC6
"""
from __future__ import annotations

import os
import tempfile
import pytest
import yaml
from pydantic import ValidationError

from config import (
    SimulatorConfig,
    ExpectRules,
    TestCase,
    TokenUsage,
    CaseResult,
    TokenCounter,
    load_config,
    load_test_cases,
    load_fixtures,
)

# ──────────────────────────────────────────
# AC1 — SimulatorConfig 字段校验
# ──────────────────────────────────────────

class TestSimulatorConfigFields:
    """AC1: SimulatorConfig 必须含新字段，不得含已删除字段"""

    def test_has_agent_base_url(self):
        assert "agent_base_url" in SimulatorConfig.model_fields

    def test_has_model_proxy_port(self):
        assert "model_proxy_port" in SimulatorConfig.model_fields

    def test_has_llm_proxy_url(self):
        assert "llm_proxy_url" in SimulatorConfig.model_fields

    def test_has_llm_api_key(self):
        assert "llm_api_key" in SimulatorConfig.model_fields

    def test_has_mock_rental_port(self):
        assert "mock_rental_port" in SimulatorConfig.model_fields

    def test_has_fixture_file(self):
        assert "fixture_file" in SimulatorConfig.model_fields

    def test_has_test_user_id(self):
        assert "test_user_id" in SimulatorConfig.model_fields

    def test_has_test_cases_file(self):
        assert "test_cases_file" in SimulatorConfig.model_fields

    def test_has_timeout_per_case(self):
        assert "timeout_per_case" in SimulatorConfig.model_fields

    def test_has_report_dir(self):
        assert "report_dir" in SimulatorConfig.model_fields

    def test_no_rental_mode(self):
        assert "rental_mode" not in SimulatorConfig.model_fields

    def test_no_rental_passthrough_url(self):
        assert "rental_passthrough_url" not in SimulatorConfig.model_fields

    def test_no_mock_data_file(self):
        assert "mock_data_file" not in SimulatorConfig.model_fields

    def test_fixture_file_default(self):
        """fixture_file 默认值应为 mock_data/default.yaml"""
        cfg = SimulatorConfig(
            llm_proxy_url="http://example.com",
            test_user_id="user-001",
        )
        assert cfg.fixture_file == "mock_data/default.yaml"

    def test_no_mockrule_class(self):
        """MockRule 类不应从 config 模块导出"""
        import config as cfg_module
        assert not hasattr(cfg_module, "MockRule"), "MockRule should be removed from config.py"

    def test_no_load_mock_data_function(self):
        """load_mock_data 函数不应从 config 模块导出"""
        import config as cfg_module
        assert not hasattr(cfg_module, "load_mock_data"), "load_mock_data should be removed from config.py"


# ──────────────────────────────────────────
# AC2 — load_config 正常加载
# ──────────────────────────────────────────

class TestLoadConfig:
    """AC2: load_config 应正确解析有效 YAML，缺字段时抛 ValidationError"""

    def _write_config(self, data: dict, tmp_path: str) -> str:
        path = os.path.join(tmp_path, "config.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)
        return path

    def test_load_config_valid(self, tmp_path):
        data = {
            "llm_proxy_url": "https://api.example.com/v1/chat",
            "test_user_id": "emp-001",
        }
        path = self._write_config(data, str(tmp_path))
        cfg = load_config(path)
        assert isinstance(cfg, SimulatorConfig)
        assert cfg.llm_proxy_url == "https://api.example.com/v1/chat"
        assert cfg.test_user_id == "emp-001"

    def test_load_config_all_fields(self, tmp_path):
        data = {
            "agent_base_url": "http://localhost:8191",
            "model_proxy_port": 8888,
            "llm_proxy_url": "https://api.example.com/v1/chat",
            "llm_api_key": "sk-test-key",
            "mock_rental_port": 8080,
            "fixture_file": "mock_data/default.yaml",
            "test_user_id": "emp-002",
            "test_cases_file": "test_cases.yaml",
            "timeout_per_case": 60,
            "report_dir": "_bmad-output/test-reports",
        }
        path = self._write_config(data, str(tmp_path))
        cfg = load_config(path)
        assert cfg.model_proxy_port == 8888
        assert cfg.llm_api_key == "sk-test-key"
        assert cfg.fixture_file == "mock_data/default.yaml"

    def test_load_config_missing_llm_proxy_url_raises(self, tmp_path):
        data = {"test_user_id": "emp-003"}
        path = self._write_config(data, str(tmp_path))
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "llm_proxy_url" in str(exc_info.value)

    def test_load_config_missing_test_user_id_raises(self, tmp_path):
        data = {"llm_proxy_url": "https://api.example.com/v1/chat"}
        path = self._write_config(data, str(tmp_path))
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "test_user_id" in str(exc_info.value)

    def test_load_config_llm_api_key_optional(self, tmp_path):
        data = {
            "llm_proxy_url": "https://api.example.com/v1/chat",
            "test_user_id": "emp-004",
        }
        path = self._write_config(data, str(tmp_path))
        cfg = load_config(path)
        assert cfg.llm_api_key is None

    def test_load_config_non_dict_yaml_raises(self, tmp_path):
        path = os.path.join(str(tmp_path), "list.yaml")
        with open(path, "w") as f:
            f.write("- item1\n- item2\n")
        with pytest.raises(ValueError, match="expected a YAML mapping"):
            load_config(path)


# ──────────────────────────────────────────
# AC3 — load_fixtures 函数签名与返回值
# ──────────────────────────────────────────

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "mock_data", "default.yaml"
)


class TestLoadFixtures:
    """AC3: load_fixtures 返回包含 landmarks 和 houses 列表的 dict"""

    def test_load_fixtures_returns_dict(self):
        result = load_fixtures(FIXTURE_PATH)
        assert isinstance(result, dict)

    def test_load_fixtures_has_landmarks_key(self):
        result = load_fixtures(FIXTURE_PATH)
        assert "landmarks" in result

    def test_load_fixtures_has_houses_key(self):
        result = load_fixtures(FIXTURE_PATH)
        assert "houses" in result

    def test_landmarks_is_list(self):
        result = load_fixtures(FIXTURE_PATH)
        assert isinstance(result["landmarks"], list)

    def test_houses_is_list(self):
        result = load_fixtures(FIXTURE_PATH)
        assert isinstance(result["houses"], list)

    def test_landmarks_count_ge_20(self):
        result = load_fixtures(FIXTURE_PATH)
        assert len(result["landmarks"]) >= 20, f"Expected ≥20 landmarks, got {len(result['landmarks'])}"

    def test_houses_count_ge_30(self):
        result = load_fixtures(FIXTURE_PATH)
        assert len(result["houses"]) >= 30, f"Expected ≥30 houses, got {len(result['houses'])}"

    def test_landmark_required_fields(self):
        result = load_fixtures(FIXTURE_PATH)
        required = {"id", "name", "category", "district", "longitude", "latitude"}
        for lm in result["landmarks"]:
            missing = required - set(lm.keys())
            assert not missing, f"Landmark {lm.get('id')} missing fields: {missing}"

    def test_house_required_fields(self):
        result = load_fixtures(FIXTURE_PATH)
        required = {
            "house_id", "community", "district", "area", "price", "status",
            "longitude", "latitude", "bedrooms", "rental_type", "decoration",
            "orientation", "elevator",
        }
        for h in result["houses"]:
            missing = required - set(h.keys())
            assert not missing, f"House {h.get('house_id')} missing fields: {missing}"

    def test_load_fixtures_invalid_path_raises(self):
        with pytest.raises((FileNotFoundError, OSError)):
            load_fixtures("/nonexistent/path/fixtures.yaml")

    def test_load_fixtures_invalid_content_raises(self, tmp_path):
        path = os.path.join(str(tmp_path), "bad.yaml")
        with open(path, "w") as f:
            f.write("landmarks: not_a_list\nhouses: []\n")
        with pytest.raises(ValueError):
            load_fixtures(path)

    def test_load_fixtures_missing_landmark_field_raises(self, tmp_path):
        path = os.path.join(str(tmp_path), "bad_lm.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump({"landmarks": [{"id": "SS_999", "name": "test"}], "houses": []}, f)
        with pytest.raises(ValueError, match="landmarks\\[0\\] missing fields"):
            load_fixtures(path)

    def test_load_fixtures_missing_house_field_raises(self, tmp_path):
        path = os.path.join(str(tmp_path), "bad_h.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump({"landmarks": [], "houses": [{"house_id": "HF_999"}]}, f)
        with pytest.raises(ValueError, match="houses\\[0\\] missing fields"):
            load_fixtures(path)


# ──────────────────────────────────────────
# AC4 — houses fixture 覆盖度
# ──────────────────────────────────────────

class TestHousesFixtureCoverage:
    """AC4: houses 必须满足行政区、居室、租型、价格、状态分布要求"""

    @pytest.fixture(scope="class")
    def houses(self):
        return load_fixtures(FIXTURE_PATH)["houses"]

    def test_districts_ge_6(self, houses):
        districts = {h["district"] for h in houses}
        assert len(districts) >= 6, f"Expected ≥6 districts, got {districts}"

    def test_bedrooms_includes_1_2_3(self, houses):
        bedroom_counts = {h["bedrooms"] for h in houses}
        for b in [1, 2, 3]:
            assert b in bedroom_counts, f"Missing {b}-bedroom houses"

    def test_rental_type_includes_both(self, houses):
        types = {h["rental_type"] for h in houses}
        assert "整租" in types, "Missing 整租 rental type"
        assert "合租" in types, "Missing 合租 rental type"

    def test_price_range_spans_1500_to_15000(self, houses):
        prices = [h["price"] for h in houses]
        assert min(prices) <= 2000, f"Min price {min(prices)} too high, expected ≤2000"
        assert max(prices) >= 10000, f"Max price {max(prices)} too low, expected ≥10000"

    def test_available_ge_85_percent(self, houses):
        available = sum(1 for h in houses if h["status"] == "available")
        ratio = available / len(houses)
        assert ratio >= 0.85, f"Available ratio {ratio:.1%} < 85%"

    def test_at_least_one_rented(self, houses):
        rented = sum(1 for h in houses if h["status"] == "rented")
        assert rented >= 1, "Expected at least 1 rented house"

    def test_at_least_one_offline(self, houses):
        offline = sum(1 for h in houses if h["status"] == "offline")
        assert offline >= 1, "Expected at least 1 offline house"

    def test_house_id_format(self, houses):
        import re
        pattern = re.compile(r"^HF_\d{3}$")
        for h in houses:
            assert pattern.match(h["house_id"]), f"Invalid house_id format: {h['house_id']}"

    def test_houses_have_coordinates(self, houses):
        for h in houses:
            assert isinstance(h["longitude"], float), f"House {h['house_id']}: longitude must be float"
            assert isinstance(h["latitude"], float), f"House {h['house_id']}: latitude must be float"

    def test_elevator_is_bool(self, houses):
        for h in houses:
            assert isinstance(h["elevator"], bool), f"House {h['house_id']}: elevator must be bool"

    def test_price_is_int(self, houses):
        for h in houses:
            assert isinstance(h["price"], int), f"House {h['house_id']}: price must be int"


# ──────────────────────────────────────────
# AC5 — landmarks fixture 覆盖度
# ──────────────────────────────────────────

class TestLandmarksFixtureCoverage:
    """AC5: landmarks 必须满足行政区、类别、ID格式、经纬度要求"""

    @pytest.fixture(scope="class")
    def landmarks(self):
        return load_fixtures(FIXTURE_PATH)["landmarks"]

    def test_districts_ge_5(self, landmarks):
        districts = {lm["district"] for lm in landmarks}
        assert len(districts) >= 5, f"Expected ≥5 districts, got {districts}"

    def test_category_subway_exists(self, landmarks):
        categories = {lm["category"] for lm in landmarks}
        assert "subway" in categories

    def test_category_company_exists(self, landmarks):
        categories = {lm["category"] for lm in landmarks}
        assert "company" in categories

    def test_category_landmark_exists(self, landmarks):
        categories = {lm["category"] for lm in landmarks}
        assert "landmark" in categories

    def test_subway_id_format(self, landmarks):
        import re
        pattern = re.compile(r"^SS_\d{3}$")
        for lm in landmarks:
            if lm["category"] == "subway":
                assert pattern.match(lm["id"]), f"Invalid subway id: {lm['id']}"

    def test_company_id_format(self, landmarks):
        import re
        pattern = re.compile(r"^F500_\d{3}$")
        for lm in landmarks:
            if lm["category"] == "company":
                assert pattern.match(lm["id"]), f"Invalid company id: {lm['id']}"

    def test_landmark_id_format(self, landmarks):
        import re
        pattern = re.compile(r"^LM_\d{3}$")
        for lm in landmarks:
            if lm["category"] == "landmark":
                assert pattern.match(lm["id"]), f"Invalid landmark id: {lm['id']}"

    def test_landmarks_have_coordinates(self, landmarks):
        for lm in landmarks:
            assert isinstance(lm["longitude"], float), f"Landmark {lm['id']}: longitude must be float"
            assert isinstance(lm["latitude"], float), f"Landmark {lm['id']}: latitude must be float"


# ──────────────────────────────────────────
# AC6 — CaseResult 与 TokenUsage 模型
# ──────────────────────────────────────────

class TestCaseResultAndTokenUsage:
    """AC6: CaseResult 和 TokenUsage 必须含规定字段"""

    def test_token_usage_has_prompt_tokens(self):
        assert "prompt_tokens" in TokenUsage.model_fields

    def test_token_usage_has_completion_tokens(self):
        assert "completion_tokens" in TokenUsage.model_fields

    def test_token_usage_has_total_tokens(self):
        assert "total_tokens" in TokenUsage.model_fields

    def test_case_result_has_case_id(self):
        assert "case_id" in CaseResult.model_fields

    def test_case_result_has_case_type(self):
        assert "case_type" in CaseResult.model_fields

    def test_case_result_has_status(self):
        assert "status" in CaseResult.model_fields

    def test_case_result_has_duration_ms(self):
        assert "duration_ms" in CaseResult.model_fields

    def test_case_result_has_rounds(self):
        assert "rounds" in CaseResult.model_fields

    def test_case_result_has_failure_reason(self):
        assert "failure_reason" in CaseResult.model_fields

    def test_case_result_has_actual_response(self):
        assert "actual_response" in CaseResult.model_fields

    def test_case_result_has_token_usage(self):
        assert "token_usage" in CaseResult.model_fields

    def test_case_result_status_literal(self):
        """status 只允许 PASS/FAIL/ERROR/TIMEOUT"""
        cr = CaseResult(
            case_id="tc-001",
            case_type="Chat",
            status="PASS",
            duration_ms=100,
            rounds=1,
        )
        assert cr.status == "PASS"

    def test_case_result_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            CaseResult(
                case_id="tc-002",
                case_type="Chat",
                status="INVALID",
                duration_ms=100,
                rounds=1,
            )

    def test_case_result_optional_fields_nullable(self):
        cr = CaseResult(
            case_id="tc-003",
            case_type="Single",
            status="FAIL",
            duration_ms=200,
            rounds=2,
        )
        assert cr.failure_reason is None
        assert cr.actual_response is None
        assert cr.token_usage is None
