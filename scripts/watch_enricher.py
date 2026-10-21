"""
Live view of enricher activity — shows embeddings being processed and match scores.
Run from the project root:
    python scripts/watch_enricher.py

Tails enricher.log and formats the JSON lines into readable output.
"""
import json
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "enricher.log"

# ANSI colors
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
PURPLE = "\033[95m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

EVENTS = {
    "enricher.starting":      (CYAN,   "STARTED",    lambda r: "enricher is up"),
    "embedder.loading":       (YELLOW, "LOADING",    lambda r: f"model={r.get('model','?')}  device={r.get('device','?')}"),
    "embedder.ready":         (GREEN,  "GPU READY",  lambda r: f"device={r.get('device','?')}"),
    "enricher.backfill_batch":(CYAN,   "BACKFILL",   lambda r: f"processing {r.get('count','?')} unembedded jobs"),
    "enricher.processing":    (GRAY,   "PROCESSING", lambda r: f"{r.get('count','?')} jobs"),
    "embedder.done":          (PURPLE, "EMBEDDED",   lambda r: f"{r.get('count','?')} jobs  took {r.get('elapsed_s','?')}s"),
    "enricher.batch_done":    (GREEN,  "BATCH DONE", lambda r: f"embedded {r.get('embedded','?')} jobs"),
    "matcher.scored":         (GREEN,  "SCORED",     lambda r: f"{r.get('count','?')} jobs for profile {r.get('profile_id','?')}"),
    "matcher.no_profiles":    (RED,    "NO PROFILE", lambda r: "no user profile found — create one first"),
    "listen.connected":       (CYAN,   "LISTENING",  lambda r: f"channel={r.get('channel','?')}"),
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
    level = r.get("level", "info")
    ts = r.get("timestamp", "")[-8:]  # just HH:MM:SS

    if event in EVENTS:
        color, label, detail_fn = EVENTS[event]
        detail = detail_fn(r)

        # Warn if device is cpu instead of cuda
        if event == "embedder.ready" and r.get("device") != "cuda":
            return f"{GRAY}{ts}{RESET}  {RED}{BOLD}{'GPU MISSING':<12}{RESET}  {RED}device={r.get('device')} — GPU not being used! See COMMANDS.md{RESET}"

        if event == "embedder.loading" and r.get("device") != "cuda":
            return f"{GRAY}{ts}{RESET}  {RED}{label:<12}{RESET}  {RED}{detail} ← WARNING: not cuda!{RESET}"

        return f"{GRAY}{ts}{RESET}  {color}{label:<12}{RESET}  {detail}"

    if level == "error":
        return f"{GRAY}{ts}{RESET}  {RED}{'ERROR':<12}{RESET}  {r.get('event','')}  {r}"

    return None  # skip noisy/unknown events


def tail(path: Path):
    if not path.exists():
        print(f"{RED}enricher.log not found at {path}{RESET}")
        print("Is the enricher running? Start it first.")
        sys.exit(1)

    print(f"{BOLD}Watching enricher log — Ctrl+C to stop{RESET}\n")

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
