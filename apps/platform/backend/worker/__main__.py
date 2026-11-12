"""Run the apply worker on the host:  python -m worker

It needs a display (the browser is visible on purpose) and the API reachable
at --api. It fills forms and stops; you review and submit."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .runner import Worker

PLATFORM_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA = PLATFORM_DIR / "data"
WORKER_ENV = PLATFORM_DIR / ".worker.env"


def load_worker_env(path: Path = WORKER_ENV) -> bool:
    """Read KEY=VALUE lines from .worker.env, written by deploy/deploy.sh when
    the API lives on a server: it holds the API's URL and the worker token.
    Variables already set in the environment win."""
    if not path.is_file():
        return False
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    return True


def main() -> None:
    from_file = load_worker_env()
    ap = argparse.ArgumentParser(prog="python -m worker", description=__doc__)
    ap.add_argument("--api", default=os.getenv("COPILOT_API", "http://127.0.0.1:8000"),
                    help="base URL of the Copilot API")
    ap.add_argument("--data-dir", type=Path,
                    default=Path(os.getenv("COPILOT_DATA_DIR", DEFAULT_DATA)),
                    help="where the browser profile lives")
    ap.add_argument("--max-tabs", type=int, default=3,
                    help="how many forms may be open for review at once")
    ap.add_argument("--channel", default=os.getenv("COPILOT_BROWSER_CHANNEL") or None,
                    help="'chrome' to use installed Chrome instead of bundled Chromium")
    ap.add_argument("--once", action="store_true", help="handle one fill, then exit")
    ap.add_argument("--headless", action="store_true",
                    help="no window; for automated tests only, since you cannot review "
                         "or submit a form you cannot see")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = os.getenv("COPILOT_WORKER_TOKEN") or None
    logging.info("API: %s%s%s", args.api, " (worker token set)" if token else "",
                 f" (from {WORKER_ENV.name})" if from_file else "")
    if args.api.startswith("http://") and "127.0.0.1" not in args.api and "localhost" not in args.api:
        logging.warning("the API is remote but not HTTPS: the worker token and your "
                        "resume would travel unencrypted")
    worker = Worker(args.api, args.data_dir.expanduser().resolve(),
                    max_tabs=max(1, args.max_tabs), channel=args.channel,
                    headless=args.headless, token=token)
    try:
        worker.run(once=args.once)
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop()


if __name__ == "__main__":
    main()
