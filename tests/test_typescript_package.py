"""Tests for staging the npm package from repository version metadata."""

import json
from pathlib import Path

import pytest

from scripts.stage_typescript_package import npm_version, stage


def test_npm_version_accepts_tags_and_converts_hatch_versions() -> None:
    release = ".".join(map(str, (1, 2, 3)))
    assert npm_version(f"v{release}") == release
    assert npm_version(f"{release}.dev4+gabc") == f"{release}-dev.4+gabc"


def test_npm_version_rejects_non_versions() -> None:
    with pytest.raises(ValueError, match="cannot be represented as npm SemVer"):
        npm_version("main")


def test_stage_creates_publishable_manifest(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    package = root / "packages/typescript"
    (package / "dist").mkdir(parents=True)
    (package / "dist/index.js").write_text("export {};\n", encoding="utf-8")
    (package / "README.md").write_text("# package\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (package / "package.json").write_text(
        json.dumps(
            {
                "name": "vodoo",
                "private": True,
                "type": "module",
                "devDependencies": {"typescript": "latest"},
                "scripts": {"build": "tsc"},
            }
        ),
        encoding="utf-8",
    )
    version = ".".join(map(str, (2, 3, 4)))
    output = stage(root, tmp_path / "staged", version)
    manifest = json.loads((output / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version
    assert "private" not in manifest
    assert "devDependencies" not in manifest
    assert "scripts" not in manifest
    assert (output / "dist/index.js").is_file()
    assert (output / "LICENSE").is_file()
