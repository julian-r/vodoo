#!/usr/bin/env python3
"""Securely download official Odoo Enterprise source distributions.

The download code is read from the repository-local, Git-ignored
``.odoo-license`` file. Secrets and signed download URLs are never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import stat
import sys
import tarfile
import tempfile
from http.client import HTTPResponse
from pathlib import Path, PurePosixPath
from typing import IO
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LICENSE_FILE = PROJECT_ROOT / ".odoo-license"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / ".odoo-enterprise"
SUPPORTED_VERSIONS = (17, 18, 19)
DOWNLOAD_PAGE = "https://www.odoo.com/thanks/download"
DOWNLOAD_HOST = "download.odoocdn.com"
MAX_HANDOFF_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 500_000
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class EnterpriseSourceError(RuntimeError):
    """Raised when an Enterprise source download or archive is invalid."""


def _require_no_redirect(requested_url: str, final_url: str) -> None:
    """Reject redirects so validated hosts cannot be bypassed."""
    if final_url != requested_url:
        raise EnterpriseSourceError("Refusing redirected Enterprise download response")


def _open_url(request: Request, timeout: int = 120) -> HTTPResponse:
    response = urlopen(request, timeout=timeout)
    try:
        _require_no_redirect(request.full_url, response.geturl())
    except EnterpriseSourceError:
        response.close()
        raise
    if not isinstance(response, HTTPResponse):
        response.close()
        raise EnterpriseSourceError("Unexpected HTTP response type")
    return response


def read_download_code(path: Path) -> str:
    """Read a non-empty download code from a private, non-symlink file."""
    if path.is_symlink() or not path.is_file():
        raise EnterpriseSourceError(f"Missing or unsafe download-code file: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise EnterpriseSourceError(f"Download-code file must have 0600 permissions: {path}")
    code = path.read_text(encoding="utf-8").strip()
    if not code or "\n" in code or "\r" in code:
        raise EnterpriseSourceError("Download-code file must contain exactly one non-empty line")
    return code


def validate_signed_download_url(signed_url: str, version: int) -> str:
    """Validate and return an official, version-specific CDN URL."""
    parsed = urlsplit(signed_url)
    expected_path = f"/download/{version}e/src"
    query_values = parse_qs(parsed.query, strict_parsing=True)
    if (
        parsed.scheme != "https"
        or parsed.hostname != DOWNLOAD_HOST
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or parsed.fragment
        or set(query_values) != {"payload"}
        or len(query_values["payload"]) != 1
        or not query_values["payload"][0]
    ):
        raise EnterpriseSourceError("Odoo returned an unexpected Enterprise download target")
    return signed_url


def get_signed_download_url(version: int, code: str) -> str:
    """Exchange the download code for a short-lived official CDN URL."""
    query = urlencode({"code": code, "platform_version": f"src_{version}e"})
    request = Request(
        f"{DOWNLOAD_PAGE}?{query}",
        headers={"User-Agent": "vodoo-enterprise-integration-fetch/1"},
    )
    with _open_url(request) as response:
        content_type = response.headers.get_content_type()
        body = response.read(MAX_HANDOFF_BYTES + 1)
    if len(body) > MAX_HANDOFF_BYTES:
        raise EnterpriseSourceError("Odoo download handoff page is unexpectedly large")
    if content_type != "text/html":
        raise EnterpriseSourceError(f"Unexpected Odoo handoff content type: {content_type}")

    page = body.decode("utf-8", errors="strict")
    match = re.search(r"window\.location\.assign\('([^']+)'\)", page)
    if match is None:
        raise EnterpriseSourceError("Odoo did not provide an Enterprise source download URL")
    return validate_signed_download_url(html.unescape(match.group(1)), version)


def _stream_archive(url: str, destination: IO[bytes]) -> tuple[str, int]:
    """Download an archive while calculating its SHA-256 digest."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != DOWNLOAD_HOST:
        raise EnterpriseSourceError("Refusing a non-official Enterprise download URL")
    request = Request(url, headers={"User-Agent": "vodoo-enterprise-integration-fetch/1"})
    digest = hashlib.sha256()
    size = 0
    with _open_url(request, timeout=600) as response:
        if response.headers.get_content_type() != "application/octet-stream":
            raise EnterpriseSourceError("Enterprise source response is not a binary archive")
        while chunk := response.read(CHUNK_SIZE):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise EnterpriseSourceError("Enterprise source archive exceeds the size limit")
            destination.write(chunk)
            digest.update(chunk)
    if size == 0:
        raise EnterpriseSourceError("Enterprise source archive is empty")
    destination.flush()
    return digest.hexdigest(), size


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise EnterpriseSourceError(f"Unsafe archive member path: {name!r}")
    return path


def validate_archive(  # noqa: PLR0912, PLR0915
    path: Path, version: int
) -> tuple[str, str, int]:
    """Validate an official source distribution without extracting it.

    Returns ``(sha256, package_version, member_count)``.
    """
    if path.is_symlink() or not path.is_file():
        raise EnterpriseSourceError(f"Missing or unsafe Enterprise archive: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)

    expected_prefix = f"odoo-{version}.0+e."
    roots: set[str] = set()
    normalized_names: set[str] = set()
    regular_file_names: set[str] = set()
    package_info_name: str | None = None
    member_count = 0
    uncompressed_size = 0
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise EnterpriseSourceError("Enterprise archive has too many members")
                member_path = _safe_member_path(member.name)
                normalized_name = str(member_path)
                if normalized_name in normalized_names:
                    raise EnterpriseSourceError(
                        f"Duplicate archive member path: {normalized_name!r}"
                    )
                normalized_names.add(normalized_name)
                roots.add(member_path.parts[0])
                if not member.isfile() and not member.isdir():
                    raise EnterpriseSourceError(f"Unsupported archive member type: {member.name!r}")
                if member.isfile():
                    uncompressed_size += member.size
                    if uncompressed_size > MAX_UNCOMPRESSED_BYTES:
                        raise EnterpriseSourceError(
                            "Enterprise archive exceeds the uncompressed size limit"
                        )
                if member.isfile() and len(member_path.parts) > 1:
                    relative_name = "/".join(member_path.parts[1:])
                    regular_file_names.add(relative_name)
                    if relative_name == "PKG-INFO":
                        package_info_name = member.name

            if len(roots) != 1:
                raise EnterpriseSourceError("Enterprise archive must have exactly one root")
            root = next(iter(roots))
            if not root.startswith(expected_prefix):
                raise EnterpriseSourceError(
                    f"Enterprise archive root {root!r} does not match Odoo {version}"
                )
            required = {
                "PKG-INFO",
                "setup.py",
                "requirements.txt",
                "odoo/addons/base/__manifest__.py",
                "odoo/addons/helpdesk/__manifest__.py",
            }
            missing = sorted(required - regular_file_names)
            if missing:
                raise EnterpriseSourceError(
                    f"Enterprise archive is missing required files: {', '.join(missing)}"
                )
            if package_info_name is None:
                raise EnterpriseSourceError("Enterprise archive has no package metadata")
            package_info_file = archive.extractfile(package_info_name)
            if package_info_file is None:
                raise EnterpriseSourceError("Could not read Enterprise package metadata")
            package_info = package_info_file.read(64 * 1024).decode("utf-8", errors="strict")
    except (tarfile.TarError, OSError) as exc:
        raise EnterpriseSourceError(f"Invalid Enterprise source archive: {exc}") from exc

    name_match = re.search(r"(?m)^Name: (.+)$", package_info)
    version_match = re.search(r"(?m)^Version: (.+)$", package_info)
    package_name = name_match.group(1).strip() if name_match else ""
    package_version = version_match.group(1).strip() if version_match else ""
    if package_name != "odoo" or not package_version.startswith(f"{version}.0+e."):
        raise EnterpriseSourceError(
            f"Unexpected Enterprise package metadata: {package_name} {package_version}"
        )
    if member_count < 1_000:
        raise EnterpriseSourceError("Enterprise source archive has too few members")
    return digest.hexdigest(), package_version, member_count


def archive_path(output_dir: Path, version: int) -> Path:
    """Return the stable local archive path for a version."""
    return output_dir / f"odoo-{version}e-source.tar.gz"


def fetch_version(
    version: int,
    *,
    code: str,
    output_dir: Path,
    force: bool,
) -> Path:
    """Download and validate one official Enterprise source distribution."""
    if output_dir.is_symlink():
        raise EnterpriseSourceError(f"Refusing symlinked output directory: {output_dir}")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_dir.chmod(0o700)

    destination = archive_path(output_dir, version)
    if destination.exists() and not force:
        if destination.is_symlink():
            raise EnterpriseSourceError(f"Refusing symlinked Enterprise archive: {destination}")
        destination.chmod(0o600)
        digest, package_version, members = validate_archive(destination, version)
        print(
            f"Odoo {version} Enterprise already present: {package_version}, "
            f"{members} members, sha256={digest}"
        )
        return destination

    signed_url = get_signed_download_url(version, code)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=f"odoo-{version}e-",
            suffix=".part",
            dir=output_dir,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary_path.chmod(0o600)
            _, size = _stream_archive(signed_url, temporary.file)
        digest, package_version, members = validate_archive(temporary_path, version)
        temporary_path.replace(destination)
        destination.chmod(0o600)
        print(
            f"Downloaded Odoo {version} Enterprise: {package_version}, "
            f"{size} bytes, {members} members, sha256={digest}"
        )
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="download Enterprise sources")
    fetch_parser.add_argument(
        "versions",
        type=int,
        choices=SUPPORTED_VERSIONS,
        nargs="+",
        help="Odoo major versions to fetch",
    )
    fetch_parser.add_argument("--force", action="store_true", help="replace existing archives")
    fetch_parser.add_argument("--license-file", type=Path, default=DEFAULT_LICENSE_FILE)
    fetch_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    validate_parser = subparsers.add_parser("validate", help="validate one local archive")
    validate_parser.add_argument("version", type=int, choices=SUPPORTED_VERSIONS)
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument(
        "--sha-only",
        action="store_true",
        help="print only the archive SHA-256 for scripting",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the downloader or validator."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "fetch":
            code = read_download_code(args.license_file)
            for version in args.versions:
                fetch_version(version, code=code, output_dir=args.output_dir, force=args.force)
            return 0

        digest, package_version, members = validate_archive(args.path, args.version)
        if args.sha_only:
            print(digest)
        else:
            print(
                f"Valid Odoo {args.version} Enterprise archive: {package_version}, "
                f"{members} members, sha256={digest}"
            )
        return 0
    except EnterpriseSourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
