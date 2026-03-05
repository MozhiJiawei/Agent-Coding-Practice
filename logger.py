import json
import threading
import time
import traceback
from contextvars import ContextVar
from pathlib import Path

LOG_DIR = Path("logs")

# 供 agent 在调用 tools 前设置，tools 内 log_event(session_id="") 时使用此值写入对应 session 日志文件。
# ContextVar 按 asyncio Task 隔离，并发多请求时各请求的 session_id 不会串号。
current_session_id: ContextVar[str] = ContextVar("current_session_id", default="")

# 按文件路径加锁，避免同一 session 被并发请求时多 task 写同一 jsonl 导致行交错
_file_locks: dict[Path, threading.Lock] = {}
_lock_meta = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _lock_meta:
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        return _file_locks[path]


def log_event(
    event_type: str,
    session_id: str,
    details: dict,
    exc: BaseException | None = None,
) -> None:
    d = dict(details)
    if exc is not None:
        d["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    effective_sid = session_id if session_id else current_session_id.get("")
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{effective_sid}.jsonl"
    line = json.dumps(
        {"ts": int(time.time()), "session_id": effective_sid, "event": event_type, "details": d},
        ensure_ascii=False,
    ) + "\n"
    with _lock_for(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    # 同时打印到 stdout，便于实时查看（details 过长时截断）
    details_preview = json.dumps(d, ensure_ascii=False)
    if len(details_preview) > 200:
        details_preview = details_preview[:200] + "..."
    print(f"[{effective_sid or 'global'}] {event_type} {details_preview}")
