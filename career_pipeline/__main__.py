import argparse
from pathlib import Path

from .orchestrator import finalize_run, prepare_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--root", required=True)
    prepare.add_argument("--target", required=True)
    prepare.add_argument("--draft", required=True)
    prepare.add_argument("--posting")
    prepare.add_argument("--run-name")
    prepare.add_argument("--resume")

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "prepare":
        state = prepare_run(
            Path(args.root),
            args.target,
            Path(args.draft),
            args.posting,
            args.run_name,
            Path(args.resume) if args.resume else None,
        )
        print(state["run_dir"])
        return 2 if state["status"] == "blocked" else 0
    state = finalize_run(Path(args.run))
    print(state["status"])
    return 0 if state["status"] == "complete" else 3


if __name__ == "__main__":
    raise SystemExit(main())
