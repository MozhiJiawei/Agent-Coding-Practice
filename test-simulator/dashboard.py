"""Test Visualization Dashboard — Web UI for E2E test results and LLM interactions"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse


class InteractionStore:
    """In-memory store for LLM request/response logs per session."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def log(self, session_id: str, request_body: dict, response_data: dict) -> None:
        self._store[session_id].append({
            "request": request_body,
            "response": response_data,
            "timestamp": datetime.now().isoformat(),
        })

    def get(self, session_id: str) -> list[dict[str, Any]]:
        return self._store.get(session_id, [])


def create_dashboard_app(interaction_store: InteractionStore) -> FastAPI:
    case_results: list[dict[str, Any]] = []

    app = FastAPI()

    @app.post("/api/case-result")
    async def post_case_result(request: Request) -> JSONResponse:
        body = await request.json()
        case_results.append(body)
        return JSONResponse(content={"ok": True})

    def get_enriched_results() -> list[dict]:
        enriched = []
        for r in case_results:
            item = dict(r)
            session_id = r.get("session_id")
            if session_id:
                item["llm_interactions"] = interaction_store.get(session_id)
            else:
                item["llm_interactions"] = []
            enriched.append(item)
        return enriched

    @app.get("/api/results")
    async def get_results() -> dict:
        return {"cases": get_enriched_results()}

    @app.get("/api/export-html", response_class=HTMLResponse)
    async def export_html() -> str:
        """Return self-contained HTML with all data embedded for offline viewing."""
        cases = get_enriched_results()
        data_json = json.dumps({"cases": cases}, ensure_ascii=False)
        # Escape for embedding in HTML: </script> would break the parser
        data_safe = data_json.replace("</", "<\\/")
        return EXPORT_HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_safe)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return HTML_PAGE

    return app


HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>E2E Test Dashboard</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #1a1a2e; color: #eee; }
    .summary { display: flex; gap: 16px; padding: 12px; background: #16213e; border-radius: 8px; margin-bottom: 16px; flex-wrap: wrap; }
    .summary span { padding: 4px 12px; border-radius: 4px; }
    .summary .total { background: #0f3460; }
    .summary .passed { color: #4ade80; }
    .summary .failed { color: #f87171; }
    .summary .warn { color: #fbbf24; }
    .summary .other { color: #fbbf24; }
    .tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 16px; }
    .tab { padding: 8px 14px; border-radius: 6px; cursor: pointer; border: 1px solid #334155; background: #1e293b; }
    .tab:hover { background: #334155; }
    .tab.active { background: #3b82f6; border-color: #3b82f6; }
    .tab.pass { border-left: 3px solid #4ade80; }
    .tab.fail { border-left: 3px solid #f87171; }
    .tab.warn { border-left: 3px solid #fbbf24; }
    .tab.timeout { border-left: 3px solid #fbbf24; }
    .tab.error { border-left: 3px solid #94a3b8; }
    .panel { display: none; padding: 16px; background: #16213e; border-radius: 8px; }
    .panel.active { display: block; }
    .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin-bottom: 16px; }
    .meta-item { padding: 6px 10px; background: #0f3460; border-radius: 4px; font-size: 13px; }
    .round { margin-bottom: 20px; border: 1px solid #334155; border-radius: 8px; overflow: hidden; }
    .round-header { padding: 8px 12px; background: #1e293b; cursor: pointer; font-weight: 600; }
    .round-body { padding: 12px; }
    .msg { margin: 8px 0; padding: 10px; background: #0f3460; border-radius: 6px; font-size: 13px; white-space: pre-wrap; word-break: break-word; }
    .msg-label { font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
    .collapse { display: none; }
    .collapse.open { display: block; }
    pre { margin: 0; font-size: 12px; overflow-x: auto; }
    .failure { color: #f87171; padding: 8px; background: rgba(248,113,113,0.1); border-radius: 4px; margin-top: 8px; }
    .failure.expect-failure-warn { color: #d97706; background: rgba(251,191,36,0.2); border-left: 3px solid #fbbf24; }
    .warn-badge { font-size: 11px; color: #b45309; }
    .tool-results { margin-top: 8px; }
    .tool-item { padding: 6px; background: #0f3460; border-radius: 4px; margin: 4px 0; font-size: 12px; }
    .llm-detail { margin-top: 12px; padding: 10px; background: #0f3460; border-radius: 6px; font-size: 11px; }
    .llm-req { margin-bottom: 8px; }
    .llm-resp { margin-top: 8px; }
  </style>
</head>
<body>
  <h1>E2E Test Dashboard</h1>
  <div class="summary">
    <span class="total">Total: <b id="total">0</b></span>
    <span class="passed">Passed: <b id="passed">0</b></span>
    <span class="failed">Failed: <b id="failed">0</b></span>
    <span class="warn" title="仅软约束字段失败">Warn (黄灯): <b id="warn">0</b></span>
    <span class="other">Duration: <b id="duration">-</b></span>
  </div>
  <div class="tabs" id="tabs"></div>
  <div id="panels"></div>

  <script>
    const tabsEl = document.getElementById('tabs');
    const panelsEl = document.getElementById('panels');
    const totalEl = document.getElementById('total');
    const passedEl = document.getElementById('passed');
    const failedEl = document.getElementById('failed');
    const warnEl = document.getElementById('warn');
    const durationEl = document.getElementById('duration');

    function escapeHtml(s) {
      if (!s) return '';
      const div = document.createElement('div');
      div.textContent = s;
      return div.innerHTML;
    }

    function statusClass(s) {
      if (s === 'PASS') return 'pass';
      if (s === 'FAIL') return 'fail';
      if (s === 'WARN') return 'warn';
      if (s === 'TIMEOUT') return 'timeout';
      return 'error';
    }

    function renderRound(rd) {
      let html = '<div class="round"><div class="round-header">Round ' + rd.round_num + '</div><div class="round-body">';
      html += '<div class="msg"><div class="msg-label">User</div>' + escapeHtml(rd.user_message) + '</div>';
      if (rd.error) {
        html += '<div class="failure">' + escapeHtml(rd.error) + '</div>';
      } else if (rd.agent_response_raw) {
        const resp = rd.agent_response_raw;
        const text = resp.response || '';
        html += '<div class="msg"><div class="msg-label">Agent Response</div>' + escapeHtml(text) + '</div>';
        const tools = resp.tool_results || [];
        if (tools.length) {
          html += '<div class="tool-results"><div class="msg-label">Tool Calls</div>';
          tools.forEach(t => {
            html += '<div class="tool-item">' + escapeHtml(t.tool_name || '?') + ': ' + escapeHtml(JSON.stringify(t.args || {})) + '</div>';
          });
          html += '</div>';
        }
      }
      if (rd.expect_failure) {
        const failClass = (rd.expect_soft_failure ? ' failure expect-failure expect-failure-warn' : ' failure expect-failure');
        html += '<div class="' + failClass.trim() + '"><b>Expect 失败</b>' + (rd.expect_soft_failure ? ' <span class="warn-badge">(黄灯/软约束)</span>' : '') + ': ' + escapeHtml(rd.expect_failure) + '</div>';
      }
      html += '</div></div>';
      return html;
    }

    function renderLlmInteractions(llmList) {
      if (!llmList || !llmList.length) return '';
      let html = '<div class="round" style="margin-top:16px"><div class="round-header">LLM Interactions (raw)</div><div class="round-body">';
      llmList.forEach((x, i) => {
        html += '<div class="llm-detail"><div class="llm-req"><b>Request #' + (i+1) + '</b><pre>' + escapeHtml(JSON.stringify(x.request || {}, null, 2).slice(0, 2000)) + (JSON.stringify(x.request).length > 2000 ? '...' : '') + '</pre></div>';
        html += '<div class="llm-resp"><b>Response</b><pre>' + escapeHtml(JSON.stringify(x.response || {}, null, 2).slice(0, 2000)) + (JSON.stringify(x.response).length > 2000 ? '...' : '') + '</pre></div></div>';
      });
      html += '</div></div>';
      return html;
    }

    function renderPanel(c, idx) {
      let html = '<div class="meta">';
      html += '<span class="meta-item">id: ' + escapeHtml(c.case_id) + '</span>';
      html += '<span class="meta-item">type: ' + escapeHtml(c.case_type) + '</span>';
      html += '<span class="meta-item">status: ' + escapeHtml(c.status) + '</span>';
      html += '<span class="meta-item">duration: ' + (c.duration_ms || 0) + 'ms</span>';
      html += '<span class="meta-item">rounds: ' + (c.rounds || 0) + '</span>';
      html += '</div>';

      const rounds = c.rounds_detail || [];
      rounds.forEach(rd => html += renderRound(rd));

      if (c.failure_reason) {
        html += '<div class="failure"><b>Failure</b>:';
        c.failure_reason.split('\\n').forEach(function(line) { html += '<div class="failure-line">' + escapeHtml(line) + '</div>'; });
        html += '</div>';
      }

      html += renderLlmInteractions(c.llm_interactions || []);

      return html;
    }

    function poll() {
      fetch('/api/results')
        .then(r => r.json())
        .then(data => {
          const cases = data.cases || [];
          totalEl.textContent = cases.length;
          const passed = cases.filter(c => c.status === 'PASS').length;
          const failed = cases.filter(c => c.status === 'FAIL').length;
          const warn = cases.filter(c => c.status === 'WARN').length;
          passedEl.textContent = passed;
          failedEl.textContent = failed;
          if (warnEl) warnEl.textContent = warn;
          const maxDuration = cases.reduce((a, c) => Math.max(a, c.duration_ms || 0), 0);
          durationEl.textContent = maxDuration ? (maxDuration / 1000).toFixed(1) + 's' : '-';

          tabsEl.innerHTML = '';
          panelsEl.innerHTML = '';
          cases.forEach((c, i) => {
            const tab = document.createElement('div');
            tab.className = 'tab ' + statusClass(c.status);
            tab.textContent = c.case_id;
            tab.dataset.idx = String(i);
            tab.onclick = () => {
              document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
              document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
              tab.classList.add('active');
              panelsEl.children[i].classList.add('active');
            };
            tabsEl.appendChild(tab);

            const panel = document.createElement('div');
            panel.className = 'panel' + (i === 0 ? ' active' : '');
            panel.innerHTML = renderPanel(c, i);
            panelsEl.appendChild(panel);
          });

          if (cases.length && !document.querySelector('.tab.active')) {
            tabsEl.children[0].classList.add('active');
            panelsEl.children[0].classList.add('active');
          }
        })
        .catch(() => {});
    }

    poll();
    setInterval(poll, 2000);
  </script>
</body>
</html>
"""

# Static HTML template for export: data embedded, no server needed
EXPORT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>E2E Test Report</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #1a1a2e; color: #eee; }
    .summary { display: flex; gap: 16px; padding: 12px; background: #16213e; border-radius: 8px; margin-bottom: 16px; flex-wrap: wrap; }
    .summary span { padding: 4px 12px; border-radius: 4px; }
    .summary .total { background: #0f3460; }
    .summary .passed { color: #4ade80; }
    .summary .failed { color: #f87171; }
    .summary .warn { color: #fbbf24; }
    .summary .other { color: #fbbf24; }
    .tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 16px; }
    .tab { padding: 8px 14px; border-radius: 6px; cursor: pointer; border: 1px solid #334155; background: #1e293b; }
    .tab:hover { background: #334155; }
    .tab.active { background: #3b82f6; border-color: #3b82f6; }
    .tab.pass { border-left: 3px solid #4ade80; }
    .tab.fail { border-left: 3px solid #f87171; }
    .tab.warn { border-left: 3px solid #fbbf24; }
    .tab.timeout { border-left: 3px solid #fbbf24; }
    .tab.error { border-left: 3px solid #94a3b8; }
    .panel { display: none; padding: 16px; background: #16213e; border-radius: 8px; }
    .panel.active { display: block; }
    .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin-bottom: 16px; }
    .meta-item { padding: 6px 10px; background: #0f3460; border-radius: 4px; font-size: 13px; }
    .round { margin-bottom: 20px; border: 1px solid #334155; border-radius: 8px; overflow: hidden; }
    .round-header { padding: 8px 12px; background: #1e293b; font-weight: 600; }
    .round-body { padding: 12px; }
    .msg { margin: 8px 0; padding: 10px; background: #0f3460; border-radius: 6px; font-size: 13px; white-space: pre-wrap; word-break: break-word; }
    .msg-label { font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
    pre { margin: 0; font-size: 12px; overflow-x: auto; }
    .failure { color: #f87171; padding: 8px; background: rgba(248,113,113,0.1); border-radius: 4px; margin-top: 8px; }
    .failure.expect-failure-warn { color: #d97706; background: rgba(251,191,36,0.2); border-left: 3px solid #fbbf24; }
    .warn-badge { font-size: 11px; color: #b45309; }
    .tool-results { margin-top: 8px; }
    .tool-item { padding: 6px; background: #0f3460; border-radius: 4px; margin: 4px 0; font-size: 12px; }
    .llm-detail { margin-top: 12px; padding: 10px; background: #0f3460; border-radius: 6px; font-size: 11px; }
    .llm-req { margin-bottom: 8px; }
    .llm-resp { margin-top: 8px; }
  </style>
</head>
<body>
  <h1>E2E Test Report</h1>
  <div class="summary">
    <span class="total">Total: <b id="total">0</b></span>
    <span class="passed">Passed: <b id="passed">0</b></span>
    <span class="failed">Failed: <b id="failed">0</b></span>
    <span class="warn" title="仅软约束字段失败">Warn (黄灯): <b id="warn">0</b></span>
    <span class="other">Duration: <b id="duration">-</b></span>
  </div>
  <div class="tabs" id="tabs"></div>
  <div id="panels"></div>
  <script type="application/json" id="report-data">__DATA_PLACEHOLDER__</script>
  <script>
    const data = JSON.parse(document.getElementById('report-data').textContent);
    const cases = data.cases || [];
    const tabsEl = document.getElementById('tabs');
    const panelsEl = document.getElementById('panels');
    const totalEl = document.getElementById('total');
    const passedEl = document.getElementById('passed');
    const failedEl = document.getElementById('failed');
    const warnEl = document.getElementById('warn');
    const durationEl = document.getElementById('duration');

    function escapeHtml(s) {
      if (!s) return '';
      const div = document.createElement('div');
      div.textContent = s;
      return div.innerHTML;
    }
    function statusClass(s) {
      if (s === 'PASS') return 'pass';
      if (s === 'FAIL') return 'fail';
      if (s === 'WARN') return 'warn';
      if (s === 'TIMEOUT') return 'timeout';
      return 'error';
    }
    function renderRound(rd) {
      let html = '<div class="round"><div class="round-header">Round ' + rd.round_num + '</div><div class="round-body">';
      html += '<div class="msg"><div class="msg-label">User</div>' + escapeHtml(rd.user_message) + '</div>';
      if (rd.error) {
        html += '<div class="failure">' + escapeHtml(rd.error) + '</div>';
      } else if (rd.agent_response_raw) {
        const resp = rd.agent_response_raw;
        html += '<div class="msg"><div class="msg-label">Agent Response</div>' + escapeHtml(resp.response || '') + '</div>';
        const tools = resp.tool_results || [];
        if (tools.length) {
          html += '<div class="tool-results"><div class="msg-label">Tool Calls</div>';
          tools.forEach(t => {
            html += '<div class="tool-item">' + escapeHtml(t.tool_name || '?') + ': ' + escapeHtml(JSON.stringify(t.args || {})) + '</div>';
          });
          html += '</div>';
        }
      }
      if (rd.expect_failure) {
        const failClass = (rd.expect_soft_failure ? ' failure expect-failure expect-failure-warn' : ' failure expect-failure');
        html += '<div class="' + failClass.trim() + '"><b>Expect 失败</b>' + (rd.expect_soft_failure ? ' <span class="warn-badge">(黄灯/软约束)</span>' : '') + ': ' + escapeHtml(rd.expect_failure) + '</div>';
      }
      return html + '</div></div>';
    }
    function renderLlmInteractions(llmList) {
      if (!llmList || !llmList.length) return '';
      let html = '<div class="round" style="margin-top:16px"><div class="round-header">LLM Interactions (raw)</div><div class="round-body">';
      llmList.forEach((x, i) => {
        html += '<div class="llm-detail"><div class="llm-req"><b>Request #' + (i+1) + '</b><pre>' + escapeHtml(JSON.stringify(x.request || {}, null, 2).slice(0, 2000)) + (JSON.stringify(x.request).length > 2000 ? '...' : '') + '</pre></div>';
        html += '<div class="llm-resp"><b>Response</b><pre>' + escapeHtml(JSON.stringify(x.response || {}, null, 2).slice(0, 2000)) + (JSON.stringify(x.response).length > 2000 ? '...' : '') + '</pre></div></div>';
      });
      return html + '</div></div>';
    }
    function renderPanel(c) {
      let html = '<div class="meta">';
      html += '<span class="meta-item">id: ' + escapeHtml(c.case_id) + '</span>';
      html += '<span class="meta-item">type: ' + escapeHtml(c.case_type) + '</span>';
      html += '<span class="meta-item">status: ' + escapeHtml(c.status) + '</span>';
      html += '<span class="meta-item">duration: ' + (c.duration_ms || 0) + 'ms</span>';
      html += '<span class="meta-item">rounds: ' + (c.rounds || 0) + '</span></div>';
      (c.rounds_detail || []).forEach(rd => html += renderRound(rd));
      if (c.failure_reason) {
        html += '<div class="failure"><b>Failure</b>:';
        c.failure_reason.split('\\n').forEach(function(line) { html += '<div class="failure-line">' + escapeHtml(line) + '</div>'; });
        html += '</div>';
      }
      html += renderLlmInteractions(c.llm_interactions || []);
      return html;
    }
    totalEl.textContent = cases.length;
    const passed = cases.filter(c => c.status === 'PASS').length;
    const failed = cases.filter(c => c.status === 'FAIL').length;
    const warn = cases.filter(c => c.status === 'WARN').length;
    passedEl.textContent = passed;
    failedEl.textContent = failed;
    if (warnEl) warnEl.textContent = warn;
    const maxDuration = cases.reduce((a, c) => Math.max(a, c.duration_ms || 0), 0);
    durationEl.textContent = maxDuration ? (maxDuration / 1000).toFixed(1) + 's' : '-';
    cases.forEach((c, i) => {
      const tab = document.createElement('div');
      tab.className = 'tab ' + statusClass(c.status);
      tab.textContent = c.case_id;
      tab.onclick = function() {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        panelsEl.children[i].classList.add('active');
      };
      tabsEl.appendChild(tab);
      const panel = document.createElement('div');
      panel.className = 'panel' + (i === 0 ? ' active' : '');
      panel.innerHTML = renderPanel(c);
      panelsEl.appendChild(panel);
    });
  </script>
</body>
</html>"""
