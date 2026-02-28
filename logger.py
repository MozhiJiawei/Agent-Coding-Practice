import json
import time
import traceback
from pathlib import Path

LOG_DIR = Path("logs")


def log_event(
    event_type: str,
    session_id: str,
    details: dict,
    exc: BaseException | None = None,
) -> None:
    d = dict(details)
    if exc is not None:
        d["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{session_id}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"ts": int(time.time()), "session_id": session_id, "event": event_type, "details": d},
                ensure_ascii=False,
            )
            + "\n"
        )
