"""Stage a publishable npm package using the repository-derived version."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from importlib.metadata import version as distribution_version
from pathlib import Path

from packaging.version import InvalidVersion, Version

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def npm_version(value: str) -> str:
    """Convert a git/PEP 440 version into npm-compatible SemVer."""
    raw = value.strip().removeprefix("v")
    try:
        parsed = Version(raw)
    except InvalidVersion as error:
        raise ValueError(f"Version {value!r} cannot be represented as npm SemVer") from error
    release_parts = [*parsed.release[:3]]
    release_parts.extend([0] * (3 - len(release_parts)))
    release = ".".join(str(part) for part in release_parts)
    prerelease: list[str] = []
    if parsed.pre is not None:
        prerelease.extend((parsed.pre[0], str(parsed.pre[1])))
    if parsed.dev is not None:
        prerelease.extend(("dev", str(parsed.dev)))
    candidate = release
    if prerelease:
        candidate += "-" + ".".join(prerelease)
    if parsed.local is not None:
        candidate += "+" + parsed.local.replace("_", ".")
    if _SEMVER.fullmatch(candidate) is None:
        raise ValueError(f"Version {value!r} cannot be represented as npm SemVer")
    return candidate


def repository_version(root: Path) -> str:
    """Return a version derived from a release tag or hatch-vcs metadata."""
    try:
        tag = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        tag = distribution_version("vodoo")
    return npm_version(tag)


def stage(root: Path, output: Path, version: str | None = None) -> Path:
    """Create a package directory containing built output and a release manifest."""
    source = root / "packages/typescript"
    dist = source / "dist"
    if not dist.is_dir():
        raise FileNotFoundError("TypeScript dist/ is missing; run the package build first")
    resolved_version = npm_version(version) if version is not None else repository_version(root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    manifest = json.loads((source / "package.json").read_text(encoding="utf-8"))
    manifest.pop("private", None)
    manifest["version"] = resolved_version
    manifest.pop("devDependencies", None)
    manifest.pop("scripts", None)
    manifest.pop("packageManager", None)
    (output / "package.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    shutil.copytree(dist, output / "dist")
    shutil.copy2(source / "README.md", output / "README.md")
    shutil.copy2(root / "LICENSE", output / "LICENSE")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version")
    args = parser.parse_args()
    output = stage(args.root.resolve(), args.output.resolve(), args.version)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
