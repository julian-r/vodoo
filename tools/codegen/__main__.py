"""CLI for deterministic Vodoo SDK generation."""

import argparse
from pathlib import Path

from tools.codegen.generator import OUTPUT_PATH, check_generated, generate


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Vodoo SDK sources")
    parser.add_argument("command", choices=("generate", "check"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root: Path = args.root.resolve()
    if args.command == "generate":
        path = generate(root)
        print(path.relative_to(root))
        return 0
    if check_generated(root):
        print(f"generated source is current: {OUTPUT_PATH}")
        return 0
    print(f"generated source is stale: {OUTPUT_PATH}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
