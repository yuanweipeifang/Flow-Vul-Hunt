from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Flow Vul Hunt backend.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="Reload when backend code changes.")
    parser.add_argument(
        "--log-level",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        default=os.getenv("LOG_LEVEL", "info").lower(),
    )
    parser.add_argument("--no-access-log", action="store_true", help="Disable HTTP access logs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not BACKEND_DIR.is_dir():
        raise SystemExit(f"Backend directory not found: {BACKEND_DIR}")

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Missing backend dependencies. Run: python -m pip install -r backend/requirements.txt"
        ) from exc

    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(BACKEND_DIR)] if args.reload else None,
        log_level=args.log_level,
        access_log=not args.no_access_log,
    )


if __name__ == "__main__":
    main()
