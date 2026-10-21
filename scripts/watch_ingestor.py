"""
Live view of ingestor activity — shows new jobs flowing in, errors, and source stats.
Run from the project root:
    python scripts/watch_ingestor.py

Tails ingestor.log and formats the JSON lines into readable output.
"""
import json
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "ingestor.log"

# ANSI colors
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

EVENTS = {
    "ingestor.running":      (CYAN,   "STARTED",      lambda r: f"{r.get('source_count', '?')} sources loaded"),
    "scheduler.added":       (GRAY,   "SCHEDULED",    lambda r: f"{r.get('source', '?')}  every {r.get('interval_s', '?')}s"),
    "worker.done":           (GREEN,  "FETCHED",      lambda r: f"{r.get('ats','?')}/{r.get('slug','?')}  new={r.get('new',0)}  changed={r.get('changed',0)}  total={r.get('total',0)}  {r.get('duration_ms',0)}ms"),
    "worker.not_modified":   (GRAY,   "CACHED",       lambda r: f"{r.get('ats','?')}/{r.get('slug','?')}  (304 no change)"),
    "worker.error":          (RED,    "ERROR",        lambda r: f"{r.get('ats','?')}/{r.get('slug','?')}  {r.get('error','')}"),
    "scheduler.backed_off":  (YELLOW, "BACKOFF",      lambda r: f"{r.get('source','?')}  new interval={r.get('interval_s','?')}s"),
    "scheduler.reset":       (GREEN,  "RESET",        lambda r: f"{r.get('source','?')}  back to {r.get('interval_s','?')}s"),
    "ingestor.sync_sources": (CYAN,   "SYNC",         lambda r: f"active sources={r.get('active','?')}"),
}

def format_line(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        r = json.loads(raw)
    except json.JSONDecodeError:
        return f"{GRAY}{raw}{RESET}"

    event = r.get("event", "")
    ts = r.get("timestamp", "")[-8:]  # just HH:MM:SS

    if event in EVENTS:
        color, label, detail_fn = EVENTS[event]
        detail = detail_fn(r)
        # Highlight lines with new jobs
        if event == "worker.done" and r.get("new", 0) > 0:
            return f"{GRAY}{ts}{RESET}  {BOLD}{color}{label:<12}{RESET}  {detail}"
        return f"{GRAY}{ts}{RESET}  {color}{label:<12}{RESET}  {detail}"

    # Unknown event — show raw but dim
    return f"{GRAY}{ts}  {event}  {raw}{RESET}"


def tail(path: Path):
    if not path.exists():
        print(f"{RED}ingestor.log not found at {path}{RESET}")
        print("Is the ingestor running? Start it first.")
        sys.exit(1)

    print(f"{BOLD}Watching ingestor log — Ctrl+C to stop{RESET}\n")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        # Jump to end
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                formatted = format_line(line)
                if formatted:
                    print(formatted)
            else:
                time.sleep(0.2)


if __name__ == "__main__":
    try:
        tail(LOG_PATH)
    except KeyboardInterrupt:
        print(f"\n{GRAY}Stopped.{RESET}")
