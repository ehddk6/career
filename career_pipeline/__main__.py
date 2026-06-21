import argparse


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
    print(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
