#!/usr/bin/env python3
"""Enforce production Swift coverage from SwiftPM's LLVM JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def production_totals(report: dict[str, Any]) -> dict[str, float]:
    """Aggregate non-generated Sources/Vodoo coverage percentages."""
    files = report["data"][0]["files"]
    totals: dict[str, float] = {}
    for metric in ("lines", "functions", "regions"):
        count = 0
        covered = 0
        for file in files:
            filename = str(file["filename"]).replace("\\", "/")
            if "/Sources/Vodoo/" not in filename or "/Generated/" in filename:
                continue
            summary = file["summary"][metric]
            count += int(summary["count"])
            covered += int(summary["covered"])
        if count == 0:
            raise ValueError(f"Swift coverage report contains no production {metric}")
        totals[metric] = 100 * covered / count
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-lines", type=float, default=80)
    parser.add_argument("--min-functions", type=float, default=74)
    parser.add_argument("--min-regions", type=float, default=68)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    totals = production_totals(report)
    thresholds = {
        "lines": args.min_lines,
        "functions": args.min_functions,
        "regions": args.min_regions,
    }
    failed = False
    for metric, actual in totals.items():
        minimum = thresholds[metric]
        print(f"Swift {metric}: {actual:.2f}% (minimum {minimum:.2f}%)")
        failed |= actual < minimum
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
