"""
Run the enricher in the FOREGROUND with readable output.
Use this to debug or watch what it's doing.
Ctrl+C to stop.

    python scripts/enricher.py
"""
import asyncio
import atexit
import ctypes
import logging
import multiprocessing
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog

from jobtracker.time import format_pacific  # noqa: E402

# Human-readable when run in terminal, JSON when output is redirected to a log file
_renderer = structlog.dev.ConsoleRenderer() if sys.stdout.isatty() else structlog.processors.JSONRenderer()


def _add_pacific_timestamp(_: object, __: str, event_dict: dict) -> dict:
    event_dict["timestamp"] = format_pacific(datetime.now(UTC), with_seconds=True)
    return event_dict


structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        _add_pacific_timestamp,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _renderer,
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)
logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

from jobtracker.enrich.runner import run_enricher  # noqa: E402

_mutex_handle = None


def _configure_multiprocessing() -> None:
    multiprocessing.freeze_support()
    multiprocessing.set_executable(sys.executable)


def _acquire_single_instance() -> bool:
    if sys.platform != "win32":
        return True

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Local\\jobtracker-enricher")
    if not mutex:
        return True

    last_error = ctypes.GetLastError()
    if last_error == 183:
        kernel32.CloseHandle(mutex)
        return False

    global _mutex_handle
    _mutex_handle = mutex
    atexit.register(_release_single_instance)
    return True


def _release_single_instance() -> None:
    global _mutex_handle
    if _mutex_handle and sys.platform == "win32":
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None


if __name__ == "__main__":
    if not _acquire_single_instance():
        print("Enricher already running; exiting duplicate process.")
        sys.exit(0)
    _configure_multiprocessing()
    print("Starting enricher... (Ctrl+C to stop)\n")
    try:
        asyncio.run(run_enricher())
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
