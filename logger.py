"""Structured JSONL logger - FIRST thing in the pipeline.

Vaibhav's #1 lesson: failures hide in the handoffs between agents,
so every agent call AND every handoff gets logged to a per-run file.
"""
import json
import os
import sys
from datetime import datetime, timezone

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

_RUN_LOG = None


def _run_log_path():
    global _RUN_LOG
    if _RUN_LOG is None:
        _RUN_LOG = os.path.join(LOGS_DIR, f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.log")
    return _RUN_LOG


def log(stage, data):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "data": data,
    }
    line = json.dumps(entry, ensure_ascii=False, default=str)
    print(f"[{entry['timestamp']}] [{stage}] {json.dumps(data, ensure_ascii=False, default=str)}", file=sys.stderr)
    with open(_run_log_path(), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return entry
