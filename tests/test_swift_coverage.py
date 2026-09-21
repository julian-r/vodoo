"""Tests for the Swift coverage gate."""

import pytest

from scripts.check_swift_coverage import production_totals


def test_production_totals_excludes_generated_and_test_sources() -> None:
    def covered_file(filename: str, covered: int, count: int) -> dict[str, object]:
        metric = {"covered": covered, "count": count}
        return {
            "filename": filename,
            "summary": {"lines": metric, "functions": metric, "regions": metric},
        }

    report = {
        "data": [
            {
                "files": [
                    covered_file("/repo/Sources/Vodoo/Client.swift", 7, 10),
                    covered_file("/repo/Sources/Vodoo/Generated/Projects.swift", 0, 100),
                    covered_file("/repo/swift-tests/VodooTests/Tests.swift", 100, 100),
                ]
            }
        ]
    }

    assert production_totals(report) == {
        "lines": 70,
        "functions": 70,
        "regions": 70,
    }


def test_production_totals_requires_production_files() -> None:
    with pytest.raises(ValueError, match="no production lines"):
        production_totals({"data": [{"files": []}]})
