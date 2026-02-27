# Story 2.1: Session 内存存储与跨请求历史持久化

Status: done

## Story

As a user in a multi-turn conversation,
I want my previous messages and agent responses to be remembered across multiple API calls,
so that the agent can understand context and refine results without me repeating myself.

## Acceptance Criteria

1. **Given** a `session_id` that has been used before
   **When** a new message is sent with the same `session_id`
   **Then** the full conversation history (all previous user + assistant + tool messages) is included in the next LLM call
   **And** the history is stored as a list of OpenAI-format message dicts: `[{"role": "...", "content": "..."}]`
   **And** `sessions: dict[str, list]` is defined as a module-level variable in `main.py`

2. **Given** two different `session_id` values are used
   **When** each sends messages independently
   **Then** their histories are completely independent with no data crossover (FR3, NFR10)

## Tasks / Subtasks

- [x] Task 1: Fix sessions reference pattern — replace `sessions.get()` with direct reference (AC: 1)
  - [x] Replace `history = sessions.get(request.session_id, [])` with the correct direct-reference pattern
  - [x] Initialize new session: `if request.session_id not in sessions: sessions[request.session_id] = []`
  - [x] Get direct list reference: `history = sessions[request.session_id]`
  - [x] Verify: after run_agent modifies `history` in-place, `sessions[session_id]` reflects changes automatically

- [x] Task 2: Append user message to history before calling run_agent (AC: 1)
  - [x] Add: `history.append({"role": "user", "content": request.message})` AFTER getting history reference and BEFORE calling `run_agent`
  - [x] Confirm: user messages accumulate across turns (turn 2 history has turn 1 user message)

- [x] Task 3: Verify session isolation (AC: 2 — NFR10)
  - [x] Test: two different `session_id` values → separate history lists, no crossover
  - [x] Test: `sessions["id_A"]` and `sessions["id_B"]` are different list objects
  - [x] Confirm: writing to one session never touches the other

- [x] Task 4: Verify multi-turn accumulation (AC: 1)
  - [x] Test: send 3 messages on same session_id → history grows: user[1], assistant[1], user[2], assistant[2], user[3]
  - [x] Note: assistant message accumulation requires Story 2.3 (run_agent stub currently returns None); verify user message accumulation at minimum

## Dev Notes

### 🚨 Critical Bug in Story 1.4 Implementation — Must Fix

The current `main.py` (Story 1.4 state) has this **broken persistence pattern**:

```python
# ❌ WRONG — sessions.get(..., []) returns a NEW empty list for new sessions
# This new list is NOT stored in sessions dict — history is lost after the request!
history = sessions.get(request.session_id, [])
result = await run_agent(history, request.model_ip, client)
```

**Why it's broken:** `sessions.get(session_id, [])` returns the default `[]` for new sessions, but that list is a temporary object not stored in `sessions`. Any messages appended to `history` vanish when the request ends. Even for existing sessions, user messages appended to `history` during *this* request aren't being appended yet.

### ✅ Correct Pattern — Story 2.1 Implementation

```python
# Step 1: Initialize session if new (Story 2.2 will add init_houses() call here)
if request.session_id not in sessions:
    sessions[request.session_id] = []
    # NOTE: Story 2.2 adds: await init_houses(client) BEFORE this line

# Step 2: Get DIRECT reference to stored list (not a copy)
history = sessions[request.session_id]

# Step 3: Append user message BEFORE calling run_agent
history.append({"role": "user", "content": request.message})

# Step 4: Call run_agent — it will append assistant + tool messages in-place
result = await run_agent(history, request.model_ip, client)

# sessions[request.session_id] is now auto-updated (same list object)
# No explicit save needed — in-place mutations are reflected immediately
```

**Why direct reference works:** `sessions[session_id]` and `history` point to the **same list object** in memory. When `run_agent` appends messages (Story 2.3) or when we append the user message above, those changes are immediately visible through `sessions[session_id]` without any explicit save step.

### Full Updated chat_endpoint (Story 2.1 state)

```python
@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    start_time = time.time()
    client = req.app.state.client
    try:
        # Session initialization (Story 2.2 adds init_houses call here)
        if request.session_id not in sessions:
            sessions[request.session_id] = []

        history = sessions[request.session_id]
        history.append({"role": "user", "content": request.message})

        result = await run_agent(history, request.model_ip, client)
        if result is None:
            result = {"response": "Agent not implemented", "status": "error", "tool_results": []}
        duration_ms = int((time.time() - start_time) * 1000)
        return ChatResponse(
            session_id=request.session_id,
            response=result.get("response", ""),
            status=result.get("status", "success") if result.get("status") in ("success", "error") else "error",
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

### OpenAI Message Format — Exact Dict Structure

All messages appended to `history` MUST use this exact OpenAI-compatible format:

| Role | Structure | When Added |
|------|-----------|------------|
| `"system"` | `{"role": "system", "content": SYSTEM_PROMPT}` | Story 2.3 — new session only, prepended first |
| `"user"` | `{"role": "user", "content": request.message}` | Story 2.1 — every request |
| `"assistant"` | `{"role": "assistant", "content": "...", "tool_calls": [...]}` | Story 2.3 — inside run_agent |
| `"tool"` | `{"role": "tool", "tool_call_id": "...", "content": "..."}` | Story 2.4 — inside run_agent |

Story 2.1 is only responsible for the `"user"` role append. The others are handled in Stories 2.3 and 2.4.

### Multi-Turn History Accumulation Example

After 2 turns (Stories 2.1 + 2.3 fully implemented), `sessions["abc"]` will look like:

```python
[
    {"role": "system",    "content": "你是智能租房助手..."},          # Story 2.3
    {"role": "user",      "content": "海淀区有什么房源？"},            # Story 2.1, turn 1
    {"role": "assistant", "content": "...", "tool_calls": [...]},    # Story 2.3, turn 1
    {"role": "tool",      "tool_call_id": "...", "content": "..."},  # Story 2.4, turn 1
    {"role": "assistant", "content": "为您推荐..."},                  # Story 2.3, turn 1
    {"role": "user",      "content": "第一套的详情呢？"},              # Story 2.1, turn 2
    # ... turn 2 assistant/tool messages added by run_agent
]
```

For Story 2.1 (run_agent still stub), the history will only accumulate user messages until Story 2.3 implements the full loop.

### Session Isolation Guarantee (NFR10)

Each `session_id` key maps to an independent list. Python dict keys are isolated by design. Concrete guarantees:

```python
sessions["user_A"] = []
sessions["user_B"] = []
assert sessions["user_A"] is not sessions["user_B"]  # Different objects
sessions["user_A"].append({"role": "user", "content": "hello"})
assert len(sessions["user_B"]) == 0  # B is untouched
```

There is NO shared state between sessions. The `sessions` dict is the only global store (besides the `httpx.AsyncClient`).

### Scope Clarification — What Story 2.1 Does NOT Implement

| Feature | Deferred To |
|---------|-------------|
| `POST /api/houses/init` on new session | Story 2.2 |
| `log_event("SESSION_START", ...)` | Story 6.1 (log_event is currently a stub) |
| System message prepend (`{"role": "system", ...}`) | Story 2.3 |
| Assistant message append inside run_agent | Story 2.3 |
| Tool result message append | Story 2.4 |

Story 2.1 only implements user message persistence and session dict initialization. Stories 2.2–2.4 each augment the handler further.

### Story 2.2 Integration Point

When Story 2.2 is implemented, it will intercept the `if request.session_id not in sessions:` block to add `init_houses()` BEFORE the `sessions[session_id] = []` initialization:

```python
# Story 2.1 adds:
if request.session_id not in sessions:
    sessions[request.session_id] = []

# Story 2.2 will expand to:
if request.session_id not in sessions:
    await init_houses(client)          # ← Story 2.2 inserts this
    sessions[request.session_id] = []
```

Story 2.1's initialization block is deliberately placed so Story 2.2 can cleanly insert before it without restructuring the code.

### Previous Story Intelligence (Story 1.4)

From Story 1.4 completion notes:
- `main.py` now has full try/except structure, `start_time` timing, `log_event` import
- `run_agent` is called and result is handled; `None` guard is in place
- `sessions.get(request.session_id, [])` is the **current broken pattern** — Story 2.1 replaces it
- 76/76 tests pass at Story 1.4 state; Story 2.1 tests must not break any of them

### Project Structure Notes

- **Only `main.py` is modified** in this story
- No new files created
- No new imports required — `sessions` dict is already defined, no new dependencies
- Change 1: Replace `history = sessions.get(request.session_id, [])` with the 3-line initialization + direct-reference pattern
- Change 2: Add `history.append({"role": "user", "content": request.message})` before the `run_agent` call
- The existing `None` guard and try/except structure from Story 1.4 remain unchanged

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 2, Story 2.1 Acceptance Criteria]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Data Architecture: Session State, Communication Patterns: Session Init 调用时序]
- [Source: `_bmad-output/project-context.md` — Session Management, Critical Don't-Miss Rules (NFR10 session isolation)]
- [Source: `main.py` — Current implementation (Story 1.4 state) — contains the broken `sessions.get()` pattern to fix]
- [Source: `_bmad-output/implementation-artifacts/1-4-chat-route-global-exception-handler.md` — Dev Notes: Session Management Note for Future Stories]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking

### Debug Log References

None — implementation was straightforward per story Dev Notes.

### Completion Notes List

- ✅ Task 1: Replaced `sessions.get(request.session_id, [])` with 3-line direct-reference pattern: guard check → `sessions[session_id] = []` → `history = sessions[session_id]`. Sessions dict now persists history across requests.
- ✅ Task 2: Added `history.append({"role": "user", "content": request.message})` after history reference, before `run_agent` call. User messages now accumulate in correct OpenAI dict format `{"role": "user", "content": "..."}`.
- ✅ Task 3: Session isolation verified via 3 tests — two session_ids produce different list objects, no cross-session data leakage confirmed.
- ✅ Task 4: Multi-turn accumulation verified — 3 consecutive requests on same session_id produce history `["msg1", "msg2", "msg3"]`; turn-2 run_agent call receives turn-1 user message in history.
- TDD cycle: 12 RED tests written first (all failed against broken `sessions.get()` pattern), then `main.py` fixed, 89/89 GREEN (zero regressions).
- Only `main.py` modified in production code; `tests/test_chat_endpoint.py` extended with 4 new test classes (13 tests covering Tasks 1-4).

### File List

- `main.py` — replaced broken `sessions.get()` with 3-line init + direct reference + user message append
- `tests/test_chat_endpoint.py` — added 6 test classes (15 tests total); imports consolidated to top, walrus operator removed
- `tests/conftest.py` — added autouse `_clear_sessions` fixture for global test isolation

## Senior Developer Review (AI)

**Review Date:** 2026-02-27
**Review Outcome:** Approve (after fixes)
**Reviewer Model:** claude-4.6-opus-high-thinking

### Action Items

- [x] [MEDIUM] M1 — Mid-file `import main as _main_module` at line 286 violates PEP 8 E402; moved to top of file
- [x] [MEDIUM] M2 — Unnecessary walrus operator `:=` in `test_existing_session_reuses_same_list_object`; replaced with plain variable
- [x] [MEDIUM] M3 — Story 1.4 test classes lack session cleanup → created autouse fixture in `conftest.py`
- [x] [MEDIUM] M4 — No test for exception-path session persistence; added `TestExceptionPathSessionPersistence` (2 tests)
- [x] [LOW] L1 — Outdated file header docstring; updated to include Story 2.1
- [x] [LOW] L2 — `_clear_sessions` not a pytest fixture; replaced with conftest autouse fixture

### Summary

All 4 MEDIUM and 2 LOW issues fixed. Implementation is correct — ACs fully satisfied, task completion claims verified against code. 91/91 tests pass.

## Change Log

- 2026-02-27: Story 2.1 implemented — fixed sessions persistence bug, added user message append, verified session isolation and multi-turn accumulation. 89/89 tests pass.
- 2026-02-27: Code review — fixed 6 issues (4M/2L): moved import to top, removed walrus operator, added conftest autouse session cleanup fixture, added exception-path persistence tests, updated docstring. 91/91 tests pass.
