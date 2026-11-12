"""CLI entrypoint:  python apps/job-ops/cli.py  (config defaults to the
sources.yaml next to this file, so it runs from any cwd)."""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline import run_sync

DEFAULT_CONFIG = str(Path(__file__).resolve().parent / "sources.yaml")


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch fresh job listings from ATS APIs.")
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG)
    p.add_argument("--dry-run", action="store_true",
                   help="show matches without updating dedup state or notifying")
    args = p.parse_args()
    run_sync(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()