"""CLI for deterministic Vodoo SDK generation."""

import argparse
from pathlib import Path

from tools.codegen.generator import (
    check_generated,
    generate,
    missing_custom_implementations,
    stale_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Vodoo SDK sources")
    parser.add_argument("command", choices=("generate", "check"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root: Path = args.root.resolve()
    if args.command == "generate":
        for path in generate(root):
            print(path.relative_to(root))
        return 0
    if check_generated(root):
        print("generated sources are current")
        return 0
    for path in stale_outputs(root):
        print(f"generated source is stale: {path}")
    for implementation in missing_custom_implementations(root):
        print(f"custom implementation is missing: {implementation}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
