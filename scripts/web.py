"""
Run the web UI in the FOREGROUND.
Ctrl+C to stop.

    python scripts/web.py               # default port 8080
    python scripts/web.py --port 9000

Standalone entry point — bypasses Typer/Click, which silently exits with no
output when invoked via `python -m jobtracker.cli` on this Windows setup.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobtracker.logging import configure_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the jobtracker web UI.")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    configure_logging()

    import uvicorn

    print(f"Opening job board at http://localhost:{args.port}", flush=True)
    uvicorn.run(
        "jobtracker.web.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
