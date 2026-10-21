"""
Run the bookmarklet score server in the FOREGROUND.
Ctrl+C to stop.

    python scripts/score_server.py               # default port 8765
    python scripts/score_server.py --port 9000

Standalone entry point — bypasses Typer/Click, which silently exits with no
output when invoked via `python -m jobtracker.cli` on this Windows setup.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobtracker.logging import configure_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the bookmarklet score server.")
    parser.add_argument("--port", "-p", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument(
        "--resumes",
        type=Path,
        default=Path("resumes"),
        help="Folder with *.md resumes",
    )
    args = parser.parse_args()

    configure_logging()

    import uvicorn

    from jobtracker.score_server import create_app

    app = create_app(resumes_dir=args.resumes)
    print(f"Score server on http://localhost:{args.port}  (resumes from {args.resumes}/)", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
