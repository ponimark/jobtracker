"""
Stop ingestor, enricher, and/or web processes.

    python scripts/stop.py           # stop everything
    python scripts/stop.py ingestor  # stop just ingestor
    python scripts/stop.py enricher  # stop just enricher
    python scripts/stop.py web       # stop just web
"""
import sys

from process_helpers import SERVICES, get_processes, stop_process

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

SERVICES = {name: (spec.label, spec.keywords) for name, spec in SERVICES.items()}


def _stop(label: str, keywords: tuple[str, ...]) -> None:
    processes = get_processes(keywords)

    if not processes:
        print(f"  {YELLOW}NOT RUNNING{RESET}  {label}")
        return

    for proc in processes:
        try:
            stop_process(int(proc["ProcessId"]))
        except (KeyError, TypeError, ValueError):
            continue

    count = len(processes)
    suffix = "es" if count > 1 else ""
    print(f"  {GREEN}STOPPED{RESET}      {label}  ({count} process{suffix})")


def main() -> None:
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    print(f"\n{BOLD}Stopping jobtracker...{RESET}\n")

    if target == "all":
        for label, keywords in SERVICES.values():
            _stop(label, keywords)
    elif target in SERVICES:
        label, keywords = SERVICES[target]
        _stop(label, keywords)
    else:
        print(f"{RED}Unknown service '{target}'. Use: ingestor, enricher, web, or nothing for all.{RESET}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
