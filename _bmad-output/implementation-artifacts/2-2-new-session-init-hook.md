# Story 2.2: 新 Session 数据初始化钩子

Status: done

## Story

As the judging system,
I want house data to be reset automatically when a new test case begins,
so that each test case starts with a clean, consistent data state.

## Acceptance Criteria

1. **Given** a `session_id` that has never been seen before
   **When** the first message arrives with that `session_id`
   **Then** `POST /api/houses/init` is called and awaited **before** any other processing (FR4)
   **And** the init call uses the `httpx.AsyncClient` from lifespan (not a new client)
   **And** the init call includes the `X-User-ID` header with the value from `os.environ["USER_ID"]`
   **And** only after the init call completes is the session history initialized and the user message appended
   **And** subsequent messages on the same `session_id` do NOT trigger another init call

## Tasks / Subtasks

- [x] Task 1: Implement `init_houses(client)` in `tools.py` (AC: 1)
  - [x] Replace the `pass` stub body with actual `POST /api/houses/init` call
  - [x] Use `client.post("/api/houses/init", headers=_get_headers())` — client has base_url already set
  - [x] Call `resp.raise_for_status()` then return `resp.json()`
  - [x] Wrap in `try/except Exception as e:` — return `{"error": f"init_houses failed: {str(e)}"}` on failure, never raise
  - [x] Do NOT add `init_houses` to `TOOLS` list or `TOOL_DISPATCH` — it is an internal init function, NOT a model-callable tool

- [x] Task 2: Import and call `init_houses` in `main.py` (AC: 1)
  - [x] Add `from tools import init_houses` to imports in `main.py`
  - [x] Inside `if request.session_id not in sessions:` block, add `await init_houses(client)` as the FIRST line (before `sessions[session_id] = []`)
  - [x] Verify ordering: init → `sessions[session_id] = []` → user message append → `run_agent()`

- [x] Task 3: Verify subsequent requests skip init (AC: 1)
  - [x] Test: second message on same `session_id` → `init_houses` NOT called again
  - [x] Test: two different `session_id` values → each triggers its own `init_houses` call exactly once

## Dev Notes

### Current State (Story 2.1 — starting point)

**`tools.py` — `init_houses` stub (lines 43-44):**
```python
async def init_houses(client: httpx.AsyncClient) -> dict:
    pass  # ← Must be implemented this story
```

**`main.py` — new-session block (lines 53-56):**
```python
if request.session_id not in sessions:
    sessions[request.session_id] = []      # ← await init_houses(client) goes BEFORE this
history = sessions[request.session_id]
history.append({"role": "user", "content": request.message})
```

**`main.py` — current imports:**
```python
from agent import run_agent, log_event
# tools.py is NOT imported in main.py yet — must add init_houses import
```

### ✅ Implementation Target

**`tools.py` — implement `init_houses`:**
```python
async def init_houses(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.post("/api/houses/init", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"init_houses failed: {str(e)}"}
```

**`main.py` — updated import line:**
```python
from agent import run_agent, log_event
from tools import init_houses              # ← add this import
```

**`main.py` — updated new-session block (inside `chat_endpoint` try block):**
```python
if request.session_id not in sessions:
    await init_houses(client)              # ← Story 2.2 adds this first
    sessions[request.session_id] = []     # ← Story 2.1 line (unchanged)
# NOTE: Story 2.3 will add system message append here, after sessions[id] = []
history = sessions[request.session_id]
history.append({"role": "user", "content": request.message})
```

### Why `init_houses` Lives in `tools.py`, Not `main.py`

Architecture constraint: "X-User-ID：环境变量 USER_ID，工具层统一注入，不扩散到路由层"

- `USER_ID = os.environ["USER_ID"]` is read once at module load in `tools.py`
- `_get_headers()` in `tools.py` returns `{"X-User-ID": USER_ID}`
- All header injection stays in `tools.py` — `main.py` never touches `USER_ID` directly
- `main.py` calls `await init_houses(client)` without knowing the header details

### `init_houses` Is NOT a Model Tool

`init_houses` is an **internal initialization helper** — NOT a tool the LLM calls:

| | `init_houses` | Tool functions (search_houses, etc.) |
|---|---|---|
| Called by | `main.py` (internally) | Agent loop via `TOOL_DISPATCH` |
| In `TOOLS` list | ❌ NO | ✅ Yes |
| In `TOOL_DISPATCH` | ❌ NO | ✅ Yes |
| LLM can invoke | ❌ NO | ✅ Yes |
| Error behavior | Returns `{"error": "..."}` | Returns `{"error": "..."}` |

### `init_houses` Failure Behavior

`init_houses` catches all exceptions internally and returns an error dict. The calling code in `main.py` does NOT check the return value — it proceeds to session initialization regardless:

```python
if request.session_id not in sessions:
    await init_houses(client)        # error dict returned silently on failure
    sessions[request.session_id] = []
```

**Rationale:** Even if init fails (network blip, transient error), the session should still be created and the request processed. The outer `try/except` in `chat_endpoint` handles any unexpected raises. The judging system may still score partial credit with stale data, which is better than a `status="error"` response.

### Session Init Mandatory Sequence (Architecture Constraint)

The architecture mandates this exact ordering for new sessions:

```
新 session_id 首条消息
    → 1. await init_houses(client)            ← Story 2.2 (this story)
    → 2. sessions[session_id] = []            ← Story 2.1 (already done)
    → 3. append system message to history     ← Story 2.3 (next)
    → 4. append user message to history       ← Story 2.1 (already done)
    → 5. await run_agent(history, ...)        ← Story 1.4 (already done)
```

Steps 2 and 4 are already implemented. This story adds step 1. Story 2.3 adds step 3.

### Story 2.3 Integration Point

When Story 2.3 is implemented, it will add the system message append INSIDE the `if not in sessions:` block, AFTER `sessions[session_id] = []`:

```python
if request.session_id not in sessions:
    await init_houses(client)                                         # ← Story 2.2
    sessions[request.session_id] = []                                # ← Story 2.1
    sessions[request.session_id].append(                             # ← Story 2.3 adds
        {"role": "system", "content": SYSTEM_PROMPT}
    )
```

Story 2.2 should NOT add the system message — that is explicitly deferred to Story 2.3 so SYSTEM_PROMPT is defined and finalized there.

### httpx Client URL Construction

The `httpx.AsyncClient` was created with `base_url="http://7.197.86.219:8080"`. This means:

```python
# Correct — client resolves base_url + path automatically
resp = await client.post("/api/houses/init", headers=_get_headers())
# Resolves to: POST http://7.197.86.219:8080/api/houses/init

# WRONG — do NOT pass the full URL
resp = await client.post("http://7.197.86.219:8080/api/houses/init", ...)
```

The leading `/` in `/api/houses/init` is required for httpx base_url resolution.

### `USER_ID` Environment Variable — Fail-Fast Behavior

`USER_ID = os.environ["USER_ID"]` in `tools.py` raises `KeyError` at import time if the variable is missing. This is intentional fail-fast behavior — the service should not start without a valid USER_ID, because all house API calls would fail anyway.

**Startup command must include the env var:**
```bash
USER_ID=<competition_employee_id> uvicorn main:app --host 0.0.0.0 --port 8191
```

If running tests without a real USER_ID, tests must mock `tools.USER_ID` or set the env var to a dummy value (e.g., `os.environ.setdefault("USER_ID", "test_user")`).

### Previous Story Intelligence (Stories 2.1 + 1.4)

From Story 2.1 completion notes:
- 91/91 tests pass at start of this story
- `conftest.py` has autouse `_clear_sessions` fixture that resets `sessions` dict between tests — **this is critical for Story 2.2 tests** so init_houses is called for every "new session" in tests
- `sessions.get()` bug is fixed; direct-reference pattern is in place
- The `if request.session_id not in sessions:` block is the correct insertion point

### Project Structure Notes

- **`tools.py`** is modified: replace `init_houses` stub body with real implementation
- **`main.py`** is modified: add `from tools import init_houses` import + `await init_houses(client)` call
- No new files created
- `init_houses` is NOT added to `TOOLS`, `TOOL_DISPATCH`, or any LLM-facing configuration

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 2, Story 2.2 Acceptance Criteria]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Communication Patterns: Session Init 调用时序; Authentication & Security: X-User-ID 不扩散到路由层]
- [Source: `_bmad-output/project-context.md` — Session Management: "On NEW session, call POST /api/houses/init with X-User-ID header to reset data BEFORE processing the message"]
- [Source: `tools.py` — `init_houses` stub (line 43-44), `_get_headers()` (line 14-15), `USER_ID` constant (line 7)]
- [Source: `main.py` — Current new-session block (lines 53-56), missing `init_houses` import]
- [Source: `_bmad-output/implementation-artifacts/2-1-session-storage-history-persistence.md` — Story 2.2 Integration Point section]

## Dev Agent Record

### Agent Model Used

Claude claude-4.6-opus (Cursor IDE)

### Debug Log References

- Existing test baseline: 91/91 passed before implementation
- Task 1 RED: 8 tests failed (stub returns None) — confirmed
- Task 1 GREEN: 10/10 passed after implementing init_houses body
- Task 2 RED: 6 tests failed (main.py missing init_houses attribute) — confirmed
- Task 2 GREEN: discovered existing tests hung due to real HTTP calls; added autouse `_mock_init_houses` fixture to conftest.py
- Final regression: 107/107 passed (91 existing + 16 new)

### Completion Notes List

- ✅ Task 1: Replaced `init_houses` stub in `tools.py` with `POST /api/houses/init` using `_get_headers()`, `raise_for_status()`, and `try/except` error dict pattern. Not added to TOOLS/TOOL_DISPATCH.
- ✅ Task 2: Added `from tools import init_houses` import in `main.py`. Inserted `await init_houses(client)` as first line in `if request.session_id not in sessions:` block, before `sessions[session_id] = []`.
- ✅ Task 3: Verified via tests — same session_id second message skips init; different session_ids each trigger init once.
- ✅ Added autouse `_mock_init_houses` fixture in conftest.py to prevent real HTTP requests in all tests.
- TDD process followed: RED → GREEN → VERIFY for each task, full regression after each step.

### Change Log

- 2026-02-27: Story 2.2 implementation complete — init_houses implemented and wired into new-session flow
- 2026-02-27: Code review completed — 5 issues found (3M/2L), all fixed: removed unused imports, extracted test fixture, added failure resilience test, simplified assertion pattern

### File List

- tools.py (modified: init_houses stub → real implementation)
- main.py (modified: added `from tools import init_houses` import + `await init_houses(client)` call)
- tests/conftest.py (modified: added anyio_backend fixture + autouse _mock_init_houses fixture)
- tests/test_init_houses.py (new: 16 tests covering Task 1/2/3)
