from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .choreography import ChoreographyError, describe_show, load_show
from .control import RunOptions, run_show


DEFAULT_SHOW = Path("choreographies/six_drone_show.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a CoDrone EDU swarm show.")
    parser.add_argument("--show", default=DEFAULT_SHOW, type=Path, help="Path to a choreography JSON file.")
    parser.add_argument("--arm", action="store_true", help="Actually connect to drones and fly. Without this, dry-run only.")
    parser.add_argument("--yes", action="store_true", help="Skip the final DONE confirmation. Use only for rehearsed runs.")
    parser.add_argument("--connect-pause", action="store_true", help="Use Swarm's built-in press-Enter pause after connecting.")
    args = parser.parse_args(argv)

    try:
        show = load_show(args.show)
    except (OSError, ChoreographyError) as exc:
        print(f"Invalid show: {exc}", file=sys.stderr)
        return 2

    print(describe_show(show))

    if not args.arm:
        print()
        print("Dry run only. Re-run with --arm to connect and fly.")
        return 0

    try:
        from codrone_edu import swarm as swarm_module
    except ImportError as exc:
        print(f"Unable to import codrone_edu.swarm: {exc}", file=sys.stderr)
        print("Install dependencies with: python -m pip install -e .", file=sys.stderr)
        return 2

    try:
        run_show(
            show,
            swarm_module,
            RunOptions(require_confirmation=not args.yes, connect_pause=args.connect_pause),
        )
    except Exception as exc:
        print(f"Show failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
