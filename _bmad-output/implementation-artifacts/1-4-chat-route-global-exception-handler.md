# Story 1.4: POST /api/v1/chat 路由与全局异常捕获

Status: done

## Story

As the judging system,
I want the chat endpoint to always return HTTP 200 regardless of any internal error,
so that the judging system never encounters unhandled HTTP 5xx responses that would break scoring.

## Acceptance Criteria

1. **Given** the service is running on `0.0.0.0:8191`
   **When** `POST /api/v1/chat` is called with a valid `ChatRequest` JSON body
   **Then** the response is always HTTP 200 with a `ChatResponse` JSON body
   **And** `status` field is either `"success"` or `"error"`
   **And** `timestamp` is a Unix integer (`int(time.time())`)
   **And** `duration_ms` reflects real wall-clock processing time with error ≤ 10ms (NFR4)

2. **Given** an unhandled exception occurs anywhere in request processing
   **When** the global `try/except` in the route handler catches it
   **Then** the response is still HTTP 200 with `status="error"` and the error description in `response`
   **And** no HTTP 5xx is ever returned (NFR8)

3. **Given** the startup command `uvicorn main:app --host 0.0.0.0 --port 8191` is run
   **When** it completes initialization
   **Then** the service is fully ready to accept requests within 5 seconds (FR23)

## Tasks / Subtasks

- [x] Task 1: Implement wall-clock timing for duration_ms (AC: 1 — NFR4)
  - [x] Add `start_time = time.time()` as the FIRST statement in `chat_endpoint`
  - [x] Calculate `duration_ms = int((time.time() - start_time) * 1000)` on BOTH the success and error return paths (after all processing completes)

- [x] Task 2: Implement global try/except wrapper (AC: 2 — NFR8)
  - [x] Wrap the entire handler body in `try/except Exception as e:`
  - [x] On exception: call `log_event("ERROR", request.session_id, {"error": str(e)})` (stub-safe; currently `pass`)
  - [x] On exception: return `ChatResponse(status="error", response=str(e), tool_results=[], ...)` — still HTTP 200
  - [x] Ensure NO `raise` or unhandled exception can reach FastAPI's default error handler

- [x] Task 3: Wire run_agent and build ChatResponse (AC: 1)
  - [x] Get sessions history: `history = sessions.get(request.session_id, [])`
  - [x] Call `result = await run_agent(history, request.model_ip, client)`
  - [x] Guard against `None` return (stub phase): treat `None` as `{"response": "Agent not implemented", "status": "error", "tool_results": []}`
  - [x] Build success `ChatResponse` from result dict keys: `response`, `status`, `tool_results`

- [x] Task 4: Verify HTTP 200 always returned (AC: 1, 2)
  - [x] Test: valid request body → HTTP 200 (status may be "error" while run_agent is stub — that is fine)
  - [x] Test: force an exception inside handler → still HTTP 200, `status="error"`

## Dev Notes

### 🚨 Current State of main.py (from Story 1.3 — starting point for this story)

```python
@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    client = req.app.state.client  # noqa: F841 — Story 1.4 will use this
    return ChatResponse(
        session_id=request.session_id,
        response="Not implemented",
        status="error",
        tool_results=[],
        timestamp=int(time.time()),
        duration_ms=0,
    )
```

**Problems to fix:**
- ❌ `duration_ms=0` is hardcoded — must be real wall-clock time (NFR4)
- ❌ No `try/except` — any exception propagates to FastAPI and returns HTTP 5xx (violates NFR8)
- ❌ `client` is unused (noqa suppressed) — must be passed to `run_agent`
- ❌ `run_agent` is imported but never called

### ✅ Implementation Target (complete Story 1.4 handler)

```python
@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    start_time = time.time()
    client = req.app.state.client
    try:
        history = sessions.get(request.session_id, [])
        # NOTE: Session init logic (POST /api/houses/init) added in Story 2.2
        # NOTE: Session persistence (append messages to sessions dict) added in Story 2.1
        result = await run_agent(history, request.model_ip, client)
        if result is None:
            result = {"response": "Agent not implemented", "status": "error", "tool_results": []}
        duration_ms = int((time.time() - start_time) * 1000)
        return ChatResponse(
            session_id=request.session_id,
            response=result.get("response", ""),
            status=result.get("status", "success"),
            tool_results=result.get("tool_results", []),
            timestamp=int(time.time()),
            duration_ms=duration_ms,
        )
    except Exception as e:
        log_event("ERROR", request.session_id, {"error": str(e)})
        duration_ms = int((time.time() - start_time) * 1000)
        return ChatResponse(
            session_id=request.session_id,
            response=str(e),
            status="error",
            tool_results=[],
            timestamp=int(time.time()),
            duration_ms=duration_ms,
        )
```

### Critical NFR4 Constraint: duration_ms Accuracy ≤ 10ms

- `start_time = time.time()` MUST be the **very first line** of the function body — before any other logic
- `duration_ms` MUST be computed **after** all processing (after `await run_agent(...)` returns or after the exception is caught)
- Both the success path and the error path MUST have their own `duration_ms = int((time.time() - start_time) * 1000)` calculation
- The error path `duration_ms` is placed AFTER `log_event()` call (log_event is currently `pass`, negligible overhead)
- Using `int(...)` rounding is acceptable — Python `int()` truncates toward zero, max error ≈ 1ms

### run_agent Return Value Contract

Story 1.4 wires the call to `run_agent`. The function is currently a stub (`return None`). The handler must be robust to this.

When Story 2.3 fully implements `run_agent`, it MUST return:
```python
{
    "response": str,       # final model content or error message
    "status": str,         # "success" or "error"
    "tool_results": list   # list of {"tool_name": str, "result": str} dicts (can be empty)
}
```

Story 1.4's `None` guard (`if result is None: result = {...}`) can be removed once Story 2.3 is complete, but leaving it is harmless.

### log_event Call on Error Path

Architecture mandates calling `log_event("ERROR", session_id, {"error": str(e)})` in the exception handler:
```python
# From architecture.md:
except Exception as e:
    log_event("ERROR", session_id, {"error": str(e)})
    return ChatResponse(status="error", response=str(e), ...)
```

`log_event` is currently a stub in `agent.py` (just `pass`), so this call is safe and produces no output. Story 6.1 will implement actual JSON logging. The import chain is: `main.py` imports `run_agent` from `agent.py`; `log_event` must also be imported from `agent.py`.

**Import update required:**
```python
from agent import run_agent, log_event  # add log_event
```

### Scope Clarification — What Story 1.4 Does NOT Implement

| Feature | Deferred To |
|---------|-------------|
| Session history persistence across requests | Story 2.1 |
| `POST /api/houses/init` on new session | Story 2.2 |
| Actual Agent Loop logic inside run_agent | Story 2.3 |
| Tool dispatch table | Story 2.4 |
| Format Guard (chat vs house query) | Story 2.5 |

Story 1.4 provides the **route skeleton** — correct timing, dual-path try/except, and run_agent wiring. Full end-to-end functionality requires all of Story 2.x.

### Architecture Double-Layer Exception Pattern

The architecture mandates two independent exception layers:

| Layer | Location | Behavior |
|-------|----------|----------|
| Route layer (outer) | `main.py` → `chat_endpoint` try/except | Catches ANYTHING; returns HTTP 200 `status="error"` |
| Tool layer (inner) | `tools.py` → each tool function try/except | Returns `{"error": "..."}` dict; never raises |

Story 1.4 implements the **route layer** only. Tool layer is built in Stories 3.x–5.x.

### Session Management Note for Future Stories

Story 1.4 reads `history = sessions.get(request.session_id, [])` but does NOT modify `sessions`. This is intentional:
- **Story 2.1** will add: append user/assistant messages to `sessions[session_id]`
- **Story 2.2** will add: detect new session → call `await init_houses(client)` before processing

When Story 2.1 is implemented, the route handler will be updated to persist the conversation results back into `sessions`. Story 1.4's `history` read is the correct starting pattern.

### Dependency Chain Reference

```
lifespan (Story 1.3) → app.state.client
    ↓ req.app.state.client
chat_endpoint (Story 1.4)  ← THIS STORY
    ↓ await run_agent(history, model_ip, client)
run_agent (Story 2.3)
    ↓ TOOL_DISPATCH[tool_name](client, **args)
tools.py functions (Stories 3.x–5.x)
```

### Project Structure Notes

- **Only `main.py` is modified** in this story
- No new files created
- Change 1: `from agent import run_agent, log_event` (add `log_event`)
- Change 2: Replace stub `chat_endpoint` body with the try/except pattern above
- Remove `# noqa: F841` comment from `client` variable (it is now used)
- `sessions` dict already defined at module level in `main.py` — no change needed

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 1, Story 1.4 Acceptance Criteria]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Process Patterns: 全局异常捕获, Error 响应结构]
- [Source: `_bmad-output/project-context.md` — Error Handling, Framework Rules (duration_ms), Critical Don't-Miss Rules (NFR8)]
- [Source: `main.py` — Current stub implementation (Story 1.3 state)]
- [Source: `agent.py` — run_agent stub and log_event stub signatures]
- [Source: `_bmad-output/implementation-artifacts/1-3-fastapi-lifespan-http-client.md` — Dependency chain and client passing pattern]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking

### Debug Log References

None — implementation matched Dev Notes specification exactly.

### Completion Notes List

- Task 1: `start_time = time.time()` placed as first line of handler; `duration_ms` computed on both success and error paths. Validated via 50ms sleep test (>=40ms assertion).
- Task 2: Full `try/except Exception as e:` wrapping entire handler body. `log_event("ERROR", session_id, {"error": str(e)})` called on exception path. Exception response returns HTTP 200 with `status="error"` and `response=str(e)`.
- Task 3: `log_event` added to `from agent import run_agent, log_event`. `sessions.get(request.session_id, [])` fetches history. `await run_agent(history, model_ip, client)` called. `None` guard applied. `ChatResponse` built from result dict.
- Task 4: 21 unit tests in `tests/test_chat_endpoint.py` cover all ACs. 72/72 tests pass (zero regressions).
- TDD cycle: RED (11 failures confirmed) → GREEN (all 21 pass) → full suite 72/72.
- Code Review: 4 MEDIUM + 3 LOW issues found and auto-fixed. Added status validation guard, httpx.AsyncClient arg test, malformed tool_results edge case, empty dict edge case, duration_ms upper bound, precise log_event assertion. Removed unused pytest import. Tests: 21→25. Full suite: 76/76.

### File List

- `main.py` — added `log_event` import; replaced stub `chat_endpoint` body with full try/except implementation; added status field validation guard
- `tests/test_chat_endpoint.py` — new: 25 TDD tests covering Tasks 1-4 (AC1, AC2, NFR4, NFR8) + review edge cases
