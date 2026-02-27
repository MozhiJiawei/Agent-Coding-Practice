---
project_name: 'AI Agent Coding'
user_name: 'LJW'
date: '2026-02-26'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 38
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Language**: Python 3.11+
- **Web Framework**: FastAPI (latest) + Uvicorn (ASGI server)
- **Model SDK**: openai (latest) — used in OpenAI-compatible mode for qwen3-32b
- **HTTP Client**: httpx (async, for calling rental simulation API)
- **Session State**: In-memory dict (no external DB required for competition)
- **Server Port**: 8191 (fixed, per competition spec)
- **Model API**: OpenAI-compatible endpoint at `{model_ip}:8888`, model field can be empty string
- **Rental API Base**: `http://7.225.29.223:8080`

---

## Critical Implementation Rules

### Language-Specific Rules (Python)

- **Async throughout**: All FastAPI route handlers MUST be `async def`; use `await` for all httpx and openai calls — never use sync `requests` library inside async handlers
- **httpx client reuse**: Create a single `httpx.AsyncClient` at startup (lifespan context), do NOT create a new client per request (causes connection overhead)
- **openai client init**: Initialize `openai.AsyncOpenAI(base_url=f"http://{model_ip}:8888/v1", api_key="placeholder")` per request using the `model_ip` from request body — the api_key value is ignored but must be non-empty
- **Error handling**: Wrap all external API calls (model + rental API) in try/except; return `{"status": "error", "response": "...", ...}` rather than raising HTTP exceptions that break the judge
- **Type hints**: Use Pydantic models for all FastAPI request/response bodies — do not use plain `dict`
- **Environment**: No `.env` file needed; `model_ip` is passed dynamically per request

### Framework-Specific Rules (FastAPI + LLM Tool Calling)

**FastAPI Structure:**
- Entry point: `main.py` with `POST /api/v1/chat` as the only required route
- Use FastAPI `lifespan` context manager for startup/shutdown (not deprecated `@app.on_event`)
- Request model must accept `model_ip`, `session_id`, `message`; response must include `session_id`, `response`, `status`, `tool_results`, `timestamp`, `duration_ms`
- `duration_ms` must reflect actual wall-clock processing time (judge may validate reasonableness)

**Session Management:**
- Use a global `dict[str, list]` to store conversation history keyed by `session_id`
- On NEW session (first message), call `POST /api/houses/init` with `X-User-ID` header to reset data BEFORE processing the message
- Conversation history must include all prior messages (system + user + assistant + tool results) to support multi-turn context

**LLM Tool Calling Loop:**
- Use OpenAI function-calling format (`tools=[...]`) — qwen3-32b supports this natively
- After model responds with `tool_calls`, execute ALL tool calls, append results, then call model again — loop until `finish_reason == "stop"`
- Do NOT hardcode tool selection logic — let the model decide which tools to call
- Limit tool call loop to max 10 iterations to prevent infinite loops consuming time slices

**Response Format (CRITICAL):**
- If the final response contains house recommendations: `response` field MUST be a JSON-encoded string: `json.dumps({"message": "...", "houses": ["HF_x", ...]}, ensure_ascii=False)`
- For normal conversation: `response` is plain natural language string
- NEVER mix JSON and natural language in the same `response` field
- `houses` list must contain only valid house IDs (e.g. `"HF_4"`), max 5 items

### Testing Rules

- **No formal test framework required** for competition, but manual curl testing is essential before submission
- **Smoke test sequence**: Start server → send a plain chat message → send a house query → verify `response` is valid JSON string when houses are returned
- **Session isolation test**: Send two different `session_id` values — they must NOT share conversation history
- **Data reset validation**: After calling `POST /api/houses/init`, verify subsequent house queries return full available listings (not empty)
- **Token budget awareness**: Each test run consumes time slices; avoid running full multi-turn test cases repeatedly — use single-turn smoke tests for iteration
- **Response format validation**: Use `json.loads(response_field)` to verify house query responses are valid JSON before submitting — malformed JSON will score zero for that case

### Code Quality & Style Rules

- **Single-file preferred**: Keep implementation in as few files as possible — `main.py` (server + routes), `tools.py` (tool definitions + rental API calls), `agent.py` (LLM loop logic)
- **No global mutable state except sessions**: Only `sessions: dict` and the shared `httpx.AsyncClient` should be module-level globals
- **Tool definitions as constants**: Define all LLM tool schemas as a top-level `TOOLS = [...]` constant — never construct them dynamically inside the request handler
- **X-User-ID header**: NEVER hardcode a user ID — configure via startup environment variable `USER_ID`
- **Logging**: Use `print()` or `logging.info()` for key events (session start, tool calls, model responses) — helps debug judge failures without adding latency
- **No unused imports**: Keep dependencies minimal; unused imports increase container startup time
- **String formatting**: Use f-strings throughout — never `%` formatting or `.format()`

### Development Workflow Rules

- **Startup command**: `uvicorn main:app --host 0.0.0.0 --port 8191` — host must be `0.0.0.0` (not `127.0.0.1`) so the judge can reach the container
- **Dependencies file**: Maintain `requirements.txt` with pinned versions; judge environment installs from this file — missing a dependency causes immediate failure
- **Required dependencies**: `fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `pydantic`
- **Non-blocking startup**: Server must be fully ready within 5 seconds of launch — do NOT perform heavy initialization at startup
- **No external network calls at import time**: All API calls happen inside request handlers only — never at module level
- **Competition constraint**: Do NOT call any external model or API outside `model_ip:8888` and `7.225.29.223:8080` — disqualification risk
- **3 March update**: Task spec will be updated on March 3rd — keep tool definitions and system prompt modular for quick updates

### Critical Don't-Miss Rules

**API Gotchas:**
- **X-User-ID must be real employee ID**: All `/api/houses/*` calls require `X-User-ID` header with competition-registered employee ID; wrong ID causes data isolation failure affecting all scores
- **Landmark endpoints need NO X-User-ID**: `/api/landmarks/*` does not require this header
- **Rent/terminate/offline require API calls**: Outputting "[已租]" in text is invalid — must call `POST /api/houses/{id}/rent` to complete the operation
- **Pagination**: House listing endpoints default to 10 items per page — use pagination params when filtering or results may be incomplete

**Response Format Gotchas:**
- **House query response MUST be JSON string**: Use `json.dumps({...})` — returning a Python dict will be treated as plain conversation and `houses` field won't be scored
- **No natural language prefix in JSON response**: `"为您推荐：{\"houses\": [...]}"` is INVALID — must be pure valid JSON
- **Never return JSON string for non-house queries**: Plain chat responses as JSON will cause judge parse failures

**Token Efficiency Gotchas:**
- **Time slice formula**: `t = 1 + max(0, (n_tokens - 1000) * 0.3)` — keep system prompt concise; every 1k tokens above 1k adds 0.3 slices
- **5-second non-model processing limit**: Code execution time excluding model calls must stay under 5 seconds per case, or case is marked failed
- **Prevent redundant tool calls**: Instruct model in system prompt not to re-query already-retrieved results

**Compliance:**
- **No hardcoded test answers**: Pre-filling prompts with known case answers is cheating — disqualification
- **No external models**: Only use `model_ip:8888` provided by the platform — using OpenAI/Claude/etc. results in disqualification

---

## Usage Guidelines

**For AI Agents:**
- Read this file before implementing any code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**
- Keep this file lean and focused on agent needs
- Update when technology stack or competition rules change
- Review after the March 3rd spec update
- Remove rules that become obvious over time

Last Updated: 2026-02-26
