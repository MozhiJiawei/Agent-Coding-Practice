---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
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
- **Cross-Platform Signal Handling**: Subprocess termination must work on both Windows (terminate) and Linux (SIGTERM/SIGINT)
- **Naming Conventions**: snake_case for functions/variables, ALL_CAPS_SNAKE for constants, PascalCase for classes, HF_* for house IDs, LM_* for landmark IDs
- **Unified Response Wrapper**: All Mock API endpoints use `success_response()` / `error_response()` helper functions
- **Error Handling Layers**: Startup errors (port conflict, health timeout) → exit; case errors (HTTP timeout, Agent error) → mark case as error, continue; YAML parse errors → reject before running
- **requirements-test.txt**: fastapi, uvicorn[standard], httpx, pyyaml (separate from main project dependencies)

### FR Coverage Map

FR1: Epic 1 — Load mock_data.yaml into memory
FR2: Epic 1 — POST /api/houses/init reset
FR3: Epic 1 — GET /api/houses/{id}
FR4: Epic 2 — GET /api/houses/listings/{id}
FR5: Epic 2 — GET /api/houses/by_community
FR6: Epic 1 — GET /api/houses/by_platform
FR7: Epic 1 — GET /api/houses/nearby
FR8: Epic 1 — GET /api/houses/nearby_landmarks
FR9: Epic 2 — GET /api/houses/stats
FR10: Epic 1 — POST rent/terminate/offline
FR11: Epic 2 — GET /api/landmarks (filter)
FR12: Epic 1 — GET /api/landmarks/search
FR13: Epic 2 — GET /api/landmarks/name/{name}
FR14: Epic 2 — GET /api/landmarks/{id}
FR15: Epic 2 — GET /api/landmarks/stats
FR16: Epic 1 — X-User-ID accept without enforcement
FR17: Epic 1 — Unified response JSON wrapper
FR18: Epic 1 — POST /v1/chat/completions
FR19: Epic 2 — LLM Proxy passthrough mode
FR20: Epic 1 — LLM Stub mode response
FR21: Epic 1 — Stub ignores tools field
FR22: Epic 1 — Test Runner reads YAML, starts services
FR23: Epic 1 — Health check wait
FR24: Epic 1 — Unique session_id per case
FR25: Epic 1 — Data reset before each case
FR26: Epic 1 — Chat type validation
FR27: Epic 1 — House_search exact match validation
FR28: Epic 1 — Action type validation
FR29: Epic 2 — Multi-turn case execution
FR30: Epic 2 — --case single case debug
FR31: Epic 1 — Run all cases in YAML order
FR32: Epic 1 — Terminal test report
FR33: Epic 3 — generate_mock_data.py script
FR34: Epic 3 — HF_*/LM_* ID formats
FR35: Epic 3 — Complete house data fields
FR36: Epic 3 — Landmark categories + associations

## Epic List

### Epic 1: First End-to-End Test Run
Developer can set up the test environment, run basic test cases (chat, single-turn search, and action types) against their real Agent, and see a pass/fail terminal test report — all in one command. This epic delivers the minimum viable system: Mock Rental API with core endpoints the Agent calls, LLM Proxy in Stub mode, and a Test Runner that orchestrates everything.
**FRs covered:** FR1, FR2, FR3, FR6, FR7, FR8, FR10, FR12, FR16, FR17, FR18, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27, FR28, FR31, FR32

### Epic 2: Complete Mock Coverage & Advanced Test Execution
Developer can run multi-turn conversation tests, debug individual failing test cases with `--case`, use all 15 Mock API endpoints (100% coverage), and optionally connect to a real cloud LLM for integration testing.
**FRs covered:** FR4, FR5, FR9, FR11, FR13, FR14, FR15, FR19, FR29, FR30

### Epic 3: Test Data Generation
Developer can auto-generate diverse mock datasets using a simple config file instead of hand-writing YAML, enabling rapid test scenario creation.
**FRs covered:** FR33, FR34, FR35, FR36

## Epic 1: First End-to-End Test Run

Developer can set up the test environment, run basic test cases (chat, single-turn search, and action types) against their real Agent, and see a pass/fail terminal test report — all in one command. This epic delivers the minimum viable system: Mock Rental API with core endpoints the Agent calls, LLM Proxy in Stub mode, and a Test Runner that orchestrates everything.

### Story 1.1: Project Setup, Mock Rental API & LLM Proxy

As a developer,
I want the test framework project structure created, the Agent's API base URL configurable, a Mock Rental API with core endpoints, and an LLM Proxy in Stub mode,
So that all the services my Agent depends on are available locally for testing.

**Acceptance Criteria:**

**Given** the project root exists with main.py
**When** the developer sets `RENTAL_API_BASE` environment variable
**Then** the Agent's httpx client uses that URL instead of the hardcoded competition server address

**Given** the tests/ directory does not exist
**When** this story is completed
**Then** tests/ directory contains:
- `requirements-test.txt` with fastapi, uvicorn[standard], httpx, pyyaml
- `mock_data.yaml` with at least 5 houses across 2+ districts and 3+ landmarks, all fields populated per PRD schema
- `test_cases.yaml` with at least 3 cases covering chat, single (house_search), and single (action) types
- `__init__.py` (empty, for module imports)
- `mock_rental_api.py` — Mock Rental API Server
- `llm_proxy.py` — LLM Proxy Server

**Given** `mock_data.yaml` is created
**When** the data is reviewed
**Then** each house has all required fields (id, district, community, address, room_type, layout, area, price, decoration, orientation, floor, has_elevator, available_date, subway_station, subway_distance, commute_to_xierqi, noise_level, status, tags, listings with 3 platforms, nearby_landmarks, nearby_amenities) and IDs use `HF_*` / `LM_*` format

**Given** `test_cases.yaml` is created
**When** the data is reviewed
**Then** each case has name, type, description, turns, and expected fields; YAML includes comments explaining each field (NFR5)

**Given** `mock_data.yaml` exists with house and landmark data
**When** the Mock Rental API server starts
**Then** all data is loaded into memory and `GET /health` returns `{"status": "ok"}` within 3 seconds (NFR1)

**Given** the server is running with loaded data
**When** `POST /api/houses/init` is called
**Then** all house statuses reset to their original YAML values (deep copy restore)

**Given** the server is running
**When** `GET /api/houses/{house_id}` is called with a valid ID
**Then** the response returns that house's details with 安居客 platform listing only, wrapped in `{"code": 0, "message": "success", "data": {...}}`

**Given** the server is running
**When** `GET /api/houses/by_platform` is called with filter parameters (district, min_price, max_price, room_type, decoration, orientation, max_subway_dist, listing_platform, page)
**Then** results are filtered by all provided parameters (intersection), default 10 per page, default 安居客 platform, only houses with status "可租" on that platform are returned

**Given** the server is running
**When** `GET /api/houses/nearby` is called with `landmark_id` and optional `max_distance` (default 2000m)
**Then** nearby rentable houses are returned with `distance_to_landmark`, `walking_distance`, `walking_duration` fields, default 10 per page, default 安居客

**Given** the server is running
**When** `GET /api/houses/nearby_landmarks` is called with `house_id`, optional `category`, optional `max_distance_m` (default 3000m)
**Then** nearby amenities are returned sorted by distance ascending

**Given** the server is running
**When** `POST /api/houses/{house_id}/rent` is called with `listing_platform` in body
**Then** the house status is updated to "已租" across all three platforms and the updated house record is returned
**And** `/terminate` resets status to "可租", `/offline` sets status to "下架"

**Given** the server is running
**When** `GET /api/landmarks/search` is called with required `q` parameter
**Then** landmarks matching the keyword (fuzzy name search) are returned, with optional `category` and `district` intersection filtering

**Given** any `/api/houses/*` endpoint is called with `X-User-ID` header
**When** the request is processed
**Then** the header is accepted but not enforced (no 401/403 errors)

**Given** any endpoint is called
**When** the response is returned
**Then** it follows the unified wrapper: `{"code": 0, "message": "success", "data": {...}}` and single request response time < 50ms (NFR2)

**Given** `LLM_API_BASE` and `LLM_API_KEY` environment variables are NOT set
**When** the LLM Proxy server starts on port 8888
**Then** it enters Stub mode and `GET /health` returns `{"status": "ok"}`

**Given** the Proxy is in Stub mode
**When** `POST /v1/chat/completions` is called with an OpenAI-compatible request body (model, messages)
**Then** a fixed response is returned with all required fields: `id`, `object` ("chat.completion"), `created`, `model`, `choices` (with `finish_reason: "stop"` and `content: "你好，有什么可以帮助你的？"`), and `usage`

**Given** the Proxy is in Stub mode
**When** the request body contains a `tools` field
**Then** the response does NOT include `tool_calls`; only plain text content is returned with `finish_reason: "stop"`

**Given** the request includes an optional `Session-ID` header
**When** the request is processed
**Then** the header is accepted without error (no validation required)

### Story 1.2: Test Runner — End-to-End Orchestration & Reporting

As a developer,
I want a CLI tool that starts all services, runs my test cases, and shows a terminal report,
So that I can validate my Agent's behavior with one command and quickly see what passed or failed.

**Acceptance Criteria:**

**Given** `test_cases.yaml` and `mock_data.yaml` exist in the tests/ directory
**When** the developer runs `python -m tests.test_runner`
**Then** the Test Runner starts Mock Rental API (port 9080) and LLM Proxy (port 8888) as subprocesses

**Given** subprocesses are starting
**When** `GET /health` on both services returns HTTP 200
**Then** test execution begins
**And** if health checks don't pass within 30 seconds, the runner prints an error, cleans up subprocesses, and exits with code 1

**Given** ports 9080 or 8888 are already in use
**When** the Test Runner starts
**Then** it detects the conflict, prints a clear error message identifying which port is occupied, and exits without starting any subprocesses

**Given** test execution begins
**When** each test case is processed
**Then** a unique `session_id` is generated (`test-{case_name}-{uuid_hex8}`) and `POST /api/houses/init` is called on Mock API to reset data state before the case runs

**Given** a `chat` type test case
**When** the case is executed against the Agent at `POST /api/v1/chat`
**Then** the result is PASS if `status == "success"` and `response` is non-empty; otherwise FAIL

**Given** a `house_search` type test case
**When** the case is executed and the response is received
**Then** the `response` is parsed as JSON, `houses` field is extracted, and the result is PASS if `set(actual_houses) == set(expected_houses)` (order-independent); otherwise FAIL with expected vs actual shown

**Given** an `action` type test case
**When** the case is executed
**Then** the result is PASS if `status == "success"`; otherwise FAIL

**Given** no `--case` parameter is provided
**When** all cases execute in YAML-defined order
**Then** a terminal report is printed showing: total/pass/fail counts, each case's name/type/status/duration, and failed cases include expected vs actual comparison
**And** the report uses colored output (PASS green, FAIL red) with `NO_COLOR` / non-TTY fallback (NFR6)
**And** on Windows, ANSI support is enabled via `os.system("")`

**Given** test execution completes (success or failure)
**When** the runner exits
**Then** all subprocesses (Mock API, LLM Proxy) are terminated in the `finally` block and the runner exits with code 0 (all pass) or 1 (any fail)

## Epic 2: Complete Mock Coverage & Advanced Test Execution

Developer can run multi-turn conversation tests, debug individual failing test cases with `--case`, use all 15 Mock API endpoints (100% coverage), and optionally connect to a real cloud LLM for integration testing.

### Story 2.1: Mock Rental API — Remaining Endpoints (Full 15/15 Coverage)

As a developer,
I want the Mock API to support all remaining house and landmark endpoints,
So that my Agent has 100% API coverage and tests can exercise every query scenario.

**Acceptance Criteria:**

**Given** the Mock Rental API is running
**When** `GET /api/houses/listings/{house_id}` is called
**Then** all three platform listing records (链家/安居客/58同城) are returned with `data` structure `{ total, page_size, items }`

**Given** the Mock API is running
**When** `GET /api/houses/by_community` is called with a `community` parameter
**Then** rentable houses in that community are returned, default 10 per page, default 安居客 when `listing_platform` not specified

**Given** the Mock API is running
**When** `GET /api/houses/stats` is called
**Then** statistics are returned: total house count, distribution by status/district/room_type, and price range summary

**Given** the Mock API is running
**When** `GET /api/landmarks` is called with optional `category` and/or `district` parameters
**Then** landmarks matching all provided filters (intersection) are returned

**Given** the Mock API is running
**When** `GET /api/landmarks/name/{name}` is called with an exact landmark name
**Then** the matching landmark's id, name, category, district, latitude, and longitude are returned

**Given** the Mock API is running
**When** `GET /api/landmarks/{id}` is called with a valid landmark ID
**Then** the full landmark details are returned

**Given** the Mock API is running
**When** `GET /api/landmarks/stats` is called
**Then** statistics are returned: total landmark count and distribution by category

### Story 2.2: LLM Passthrough Mode, Multi-Turn Tests & Single Case Debug

As a developer,
I want to connect to a real cloud LLM, run multi-turn conversation tests, and debug individual cases by name,
So that I can do full integration testing with real LLM reasoning and quickly isolate problems.

**Acceptance Criteria:**

**Given** `LLM_API_BASE` and `LLM_API_KEY` environment variables are set
**When** `POST /v1/chat/completions` is called on the LLM Proxy
**Then** the request body is forwarded as-is to `{LLM_API_BASE}/v1/chat/completions` with `Authorization: Bearer {LLM_API_KEY}` header, and the raw cloud response is returned to the Agent unchanged

**Given** the cloud API returns an error or is unreachable
**When** the proxy processes the request
**Then** the error is returned to the Agent with appropriate HTTP status code (not swallowed silently)

**Given** a test case with `type: "multi"` and multiple entries in `turns`
**When** the Test Runner executes this case
**Then** each turn's message is sent sequentially to the Agent using the same `session_id`, and only the last turn's response is validated against `expected`

**Given** the developer runs `python -m tests.test_runner --case multi_commute_filter`
**When** a case with that name exists in `test_cases.yaml`
**Then** only that single case is executed and its result is reported

**Given** the developer runs `python -m tests.test_runner --case nonexistent_case`
**When** no case matches that name
**Then** an error message is printed listing available case names, and the runner exits with code 1

## Epic 3: Test Data Generation

Developer can auto-generate diverse mock datasets using a simple config file instead of hand-writing YAML, enabling rapid test scenario creation.

### Story 3.1: Mock Data Generation Script

As a developer,
I want a script that generates complete `mock_data.yaml` files from a simple configuration,
So that I can quickly create diverse test datasets without manually writing hundreds of lines of YAML.

**Acceptance Criteria:**

**Given** a `generate_config.yaml` exists with house_count, landmark_count, districts, price_range, room_types, platforms, and status_distribution settings
**When** the developer runs `python tests/generate_mock_data.py --config tests/generate_config.yaml --output tests/mock_data.yaml`
**Then** a complete `mock_data.yaml` is generated with the specified number of houses and landmarks

**Given** the script generates house data
**When** the output is reviewed
**Then** each house has all required fields: id (`HF_*` format), district, community, address, room_type, layout, area, price, decoration, orientation, floor, has_elevator, available_date, subway_station, subway_distance, commute_to_xierqi, noise_level, status, tags, and three-platform listings (安居客/链家/58同城)

**Given** the script generates landmark data
**When** the output is reviewed
**Then** landmarks cover three categories (地铁站, 公司, 商圈), each with id (`LM_*` format), name, category, district, latitude, longitude
**And** each house is randomly associated with 1–3 nearby landmarks (with distance, walking_distance, walking_duration) and 0–3 nearby amenities (商超/公园)

**Given** the script is run with an optional `--seed` parameter
**When** the same seed is used twice
**Then** identical output is produced (reproducible generation)
