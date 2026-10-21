"""
Start jobtracker services in the background.
Skips any that are already running.

    python scripts/start.py               # start everything
    python scripts/start.py ingestor      # start just ingestor
    python scripts/start.py enricher      # start just enricher
    python scripts/start.py web           # start just web
"""
import os
import subprocess
import sys

from process_helpers import PYTHON, ROOT, SERVICES, ServiceSpec, build_child_env
from process_helpers import count_processes

# Windows: create process that survives after this script exits, no console window
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

ALL_SERVICES = {
    name: (spec.keywords, list(spec.args), spec.log_stem)
    for name, spec in SERVICES.items()
}


def _start(args: list[str], log_stem: str) -> int | None:
    log_out = open(ROOT / f"{log_stem}.log", "a")
    log_err = open(ROOT / f"{log_stem}.err", "a")
    try:
        process = subprocess.Popen(
            [PYTHON] + args,
            stdout=log_out,
            stderr=log_err,
            env=build_child_env(os.environ),
            cwd=str(ROOT),
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
        return process.pid
    except Exception as exc:
        print(f"  {RED}ERROR{RESET}    {exc}")
        return None
    finally:
        log_out.close()
        log_err.close()


def _launch(spec: ServiceSpec) -> None:
    if count_processes(spec.keywords) > 0:
        print(f"  {YELLOW}ALREADY RUNNING{RESET}  {spec.label}")
        return

    pid = _start(list(spec.args), spec.log_stem)
    if pid:
        print(f"  {GREEN}STARTED{RESET}          {spec.label}  (pid {pid}) -> {spec.log_stem}.log")
        return

    print(f"  {RED}FAILED{RESET}           {spec.label}  - check {spec.log_stem}.err")


def main() -> None:
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    if target != "all" and target not in SERVICES:
        print(f"{RED}Unknown service '{target}'. Use: ingestor, enricher, web, or nothing for all.{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}Starting jobtracker...{RESET}\n")

    if target == "all":
        for spec in SERVICES.values():
            _launch(spec)
    else:
        _launch(SERVICES[target])

    print("\nCheck status:  .venv\\Scripts\\python.exe scripts\\status.py\n")


if __name__ == "__main__":
    main()
