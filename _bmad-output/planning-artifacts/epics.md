---
stepsCompleted: ['step-01-validate-prerequisites']
inputDocuments:
  - _bmad-output/planning-artifacts/prd-test-simulator.md
  - _bmad-output/planning-artifacts/architecture-test-simulator.md
---

# AI Agent Coding — Test Environment Simulator - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for AI Agent Coding — Test Environment Simulator, decomposing the requirements from the PRD and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: System loads houses and landmark data from `mock_data.yaml` into memory; available immediately after startup
FR2: System implements `POST /api/houses/init` endpoint — resets all house statuses to initial values (reloads from YAML)
FR3: System implements `GET /api/houses/{house_id}` endpoint — returns single house detail by ID, always returns 安居客 platform listing (consistent with competition API behavior)
FR4: System implements `GET /api/houses/listings/{house_id}` endpoint — returns all platform listings (链家/安居客/58同城); response `data` structure is `{ total, page_size, items }`
FR5: System implements `GET /api/houses/by_community` endpoint — filter rentable houses by community name, default 10 per page, defaults to 安居客 when `listing_platform` not specified
FR6: System implements `GET /api/houses/by_platform` endpoint — supports filtering by `district`, `min_price`, `max_price`, `room_type`, `decoration`, `orientation`, `max_subway_dist`, `listing_platform`, `page`; default 10 per page; defaults to 安居客 when `listing_platform` not specified
FR7: System implements `GET /api/houses/nearby` endpoint — returns rentable houses near a landmark by `landmark_id` and `max_distance` (default 2000m), includes `distance_to_landmark`, `walking_distance`, `walking_duration` fields; default 10 per page; defaults to 安居客
FR8: System implements `GET /api/houses/nearby_landmarks` endpoint — queries nearby amenities by `house_id`, `category`, `max_distance_m` (default 3000m), results sorted by distance ascending
FR9: System implements `GET /api/houses/stats` endpoint — returns house statistics (total count, distribution by status/district/room_type, price range) from current user perspective
FR10: System implements `POST /api/houses/{house_id}/rent`, `/terminate`, `/offline` endpoints — request body must include `listing_platform`; updates house status across all three platforms simultaneously; response returns house record
FR11: System implements `GET /api/landmarks` endpoint — supports simultaneous filtering by `category` and `district` (intersection of multiple conditions)
FR12: System implements `GET /api/landmarks/search` endpoint — `q` is required; supports keyword fuzzy search; supports simultaneous filtering by `category` and `district`
FR13: System implements `GET /api/landmarks/name/{name}` endpoint — exact name query, returns `id`, coordinates, etc.
FR14: System implements `GET /api/landmarks/{id}` endpoint — query landmark details by ID
FR15: System implements `GET /api/landmarks/stats` endpoint — returns landmark statistics (total count, distribution by category, etc.)
FR16: All `/api/houses/*` endpoints accept `X-User-ID` request header without enforcement (no user isolation needed in local testing)
FR17: Mock API response JSON structure matches the real competition API — unified `{"code": 0, "message": "success", "data": {...}}` wrapper
FR18: System implements `POST /v1/chat/completions` endpoint — accepts OpenAI-compatible format request (including `model`, `messages`, `tools`, `tool_choice` fields); accepts optional `Session-ID` header
FR19: When `LLM_API_BASE` and `LLM_API_KEY` environment variables are configured, system passes the request body as-is to that address and returns the raw response to Agent
FR20: When cloud API environment variables are not configured, system enters Stub mode — returns fixed OpenAI-compatible response (`finish_reason: "stop"`, `content: "你好，有什么可以帮助你的？"`), response contains all required fields: `id`, `object`, `created`, `model`, `choices`, `usage`
FR21: In Stub mode, if request contains `tools` field, system does NOT trigger tool_calls; returns plain text response only
FR22: Test Runner reads `test_cases.yaml` and `mock_data.yaml`, starts Mock Rental API and LLM Proxy sub-services
FR23: Test Runner waits for health check of Mock API and LLM Proxy to pass (HTTP 200) before starting test execution
FR24: Test Runner generates unique `session_id` for each test case to ensure isolation between cases
FR25: Test Runner resets data state before each case by directly calling `POST /api/houses/init` on the Mock API (not through Agent)
FR26: For `chat` type cases, validates `status == "success"` and `response` is non-empty
FR27: For `house_search` type cases, parses `response` as JSON, extracts `houses` field, performs exact set match with `expected.houses` (order-independent, set equality)
FR28: For `action` type cases, validates `status == "success"`
FR29: Multi-turn conversation cases use the same `session_id` to send each turn's message in sequence; only the last turn's response is validated
FR30: Supports `--case <name>` parameter to run a single specified case
FR31: When `--case` is not specified, executes all cases in the order defined in YAML
FR32: Outputs test report to terminal after execution — includes: total cases, passed, failed; each case's name/type/status/duration; failed cases include expected vs. actual comparison
FR33: Provides `generate_mock_data.py` script — reads simplified generation config YAML, outputs complete `mock_data.yaml`
FR34: Generated data contains valid `HF_*` format house IDs and `LM_*` format landmark IDs
FR35: Generated house data covers all fields: id, district, community, address, room_type, layout, area, price, decoration, orientation, floor, has_elevator, available_date, subway_station, subway_distance, commute_to_xierqi, noise_level, status, tags; and three-platform (安居客/链家/58同城) listing records
FR36: Generated landmark data covers three categories: 地铁站, 公司, 商圈; each landmark has id, name, category, district, latitude, longitude; each house randomly associates 1-3 nearby landmarks and 0-3 nearby amenities (商超/公园)

### NonFunctional Requirements

NFR1: Mock Rental API startup time < 3 seconds (in-memory data loading)
NFR2: Single Mock API request response time < 50ms
NFR3: Test Runner full run of 20 cases (excluding LLM time) < 30 seconds
NFR4: Test framework does not introduce additional runtime dependencies to the main Agent project; test-related dependencies managed separately (`requirements-test.txt`)
NFR5: Test case and data config files use YAML format with comments explaining each field
NFR6: Test report uses colorized terminal output (PASS green, FAIL red), with non-color fallback support
NFR7: Mock API endpoint implementations correspond 1:1 with real competition API request/response format documentation, for easy tracking of API changes
NFR8: All config file paths can be overridden via environment variables or CLI parameters; default path is `tests/` directory
NFR9: Python 3.10+ support
NFR10: Windows and Linux dual-platform support

### Additional Requirements

- **No starter template**: All new files are created in the `tests/` directory; this is a greenfield sub-project within a brownfield main project
- **Prerequisite — Main Project Change**: `main.py`'s `httpx.AsyncClient` `base_url` must be changed from hardcoded to `RENTAL_API_BASE` environment variable before test framework can redirect Agent to Mock service
- **Subprocess Orchestration** (Decision 1): Use `subprocess.Popen` to manage Mock Rental API, LLM Proxy, and Agent as independent processes; `finally` block guarantees cleanup
- **Health Check Strategy** (Decision 2): Each service implements `GET /health` endpoint returning `{"status": "ok"}`; Test Runner polls all health endpoints concurrently; 30-second timeout
- **In-Memory Data Storage** (Decision 3): Load from YAML into memory `dict` on startup; state mutations in memory; `_original_houses` deep copy for init reset
- **LLM Proxy Dual-Mode** (Decision 4): Automatically determined by presence of `LLM_API_BASE` and `LLM_API_KEY` environment variables; no code modification needed
- **Three-Type Result Validation** (Decision 5): `chat` → status+non-empty response; `house_search` → exact set match; `action` → status only
- **Test Isolation via Direct Init Call** (Decision 6): Each case directly calls `POST /api/houses/init` before execution; does not depend on Agent session init hook
- **Colorized Output Compatibility** (Decision 7): Inline ANSI codes + `NO_COLOR` environment variable + `sys.stdout.isatty()` check for non-color fallback; Windows `os.system("")` for ANSI support
- **Port Conflict Detection**: Check port availability (9080, 8888) before starting subprocesses; provide clear error message if occupied
- **Module Boundaries**: Strict separation — `test_runner.py` must NOT import `mock_rental_api.py` directly; all communication via HTTP

### FR Coverage Map

{{requirements_coverage_map}}

## Epic List

{{epics_list}}

<!-- Repeat for each epic in epics_list (N = 1, 2, 3...) -->

## Epic {{N}}: {{epic_title_N}}

{{epic_goal_N}}

<!-- Repeat for each story (M = 1, 2, 3...) within epic N -->

### Story {{N}}.{{M}}: {{story_title_N_M}}

As a {{user_type}},
I want {{capability}},
So that {{value_benefit}}.

**Acceptance Criteria:**

<!-- for each AC on this story -->

**Given** {{precondition}}
**When** {{action}}
**Then** {{expected_outcome}}
**And** {{additional_criteria}}

<!-- End story repeat -->
