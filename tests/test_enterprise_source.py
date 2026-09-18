from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from tests.integration import fetch_enterprise
from tests.integration.fetch_enterprise import (
    EnterpriseSourceError,
    _require_no_redirect,
    fetch_version,
    read_download_code,
    validate_archive,
    validate_signed_download_url,
)


def _add_file(archive: tarfile.TarFile, name: str, content: bytes = b"x") -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))


def _write_archive(
    path: Path,
    *,
    version: int = 19,
    extra_member: tarfile.TarInfo | None = None,
    setup_as_directory: bool = False,
) -> None:
    root = f"odoo-{version}.0+e.20260918"
    required = {
        "PKG-INFO": f"Name: odoo\nVersion: {version}.0+e.20260918\n".encode(),
        "setup.py": b"from setuptools import setup; setup()\n",
        "requirements.txt": b"",
        "odoo/addons/base/__manifest__.py": b"{}\n",
        "odoo/addons/helpdesk/__manifest__.py": b"{}\n",
    }
    with tarfile.open(path, mode="w:gz") as archive:
        for name, content in required.items():
            if setup_as_directory and name == "setup.py":
                directory = tarfile.TarInfo(f"{root}/{name}")
                directory.type = tarfile.DIRTYPE
                archive.addfile(directory)
            else:
                _add_file(archive, f"{root}/{name}", content)
        for index in range(1_000):
            _add_file(archive, f"{root}/odoo/addons/test_{index}/__init__.py", b"")
        if extra_member is not None:
            archive.addfile(extra_member)


def test_validate_archive_accepts_versioned_enterprise_distribution(tmp_path: Path) -> None:
    archive = tmp_path / "odoo-19e.tar.gz"
    _write_archive(archive)

    digest, package_version, members = validate_archive(archive, 19)

    assert len(digest) == 64
    assert package_version == "19.0+e.20260918"
    assert members == 1_005


def test_validate_archive_rejects_wrong_version(tmp_path: Path) -> None:
    archive = tmp_path / "odoo-18e.tar.gz"
    _write_archive(archive, version=18)

    with pytest.raises(EnterpriseSourceError, match="does not match Odoo 19"):
        validate_archive(archive, 19)


def test_validate_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    unsafe = tarfile.TarInfo("../secret")
    _write_archive(archive, extra_member=unsafe)

    with pytest.raises(EnterpriseSourceError, match="Unsafe archive member path"):
        validate_archive(archive, 19)


def test_validate_archive_rejects_links(tmp_path: Path) -> None:
    archive = tmp_path / "link.tar.gz"
    link = tarfile.TarInfo("odoo-19.0+e.20260918/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    _write_archive(archive, extra_member=link)

    with pytest.raises(EnterpriseSourceError, match="Unsupported archive member type"):
        validate_archive(archive, 19)


def test_validate_archive_rejects_required_directory_in_place_of_file(tmp_path: Path) -> None:
    archive = tmp_path / "required-directory.tar.gz"
    _write_archive(archive, setup_as_directory=True)

    with pytest.raises(EnterpriseSourceError, match=r"missing required files: setup\.py"):
        validate_archive(archive, 19)


def test_validate_archive_rejects_duplicate_paths(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.tar.gz"
    duplicate = tarfile.TarInfo("odoo-19.0+e.20260918/setup.py")
    _write_archive(archive, extra_member=duplicate)

    with pytest.raises(EnterpriseSourceError, match="Duplicate archive member path"):
        validate_archive(archive, 19)


def test_validate_archive_bounds_uncompressed_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "large.tar.gz"
    _write_archive(archive)
    monkeypatch.setattr(fetch_enterprise, "MAX_UNCOMPRESSED_BYTES", 1)

    with pytest.raises(EnterpriseSourceError, match="uncompressed size limit"):
        validate_archive(archive, 19)


def test_validate_archive_bounds_member_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "many-members.tar.gz"
    _write_archive(archive)
    monkeypatch.setattr(fetch_enterprise, "MAX_ARCHIVE_MEMBERS", 10)

    with pytest.raises(EnterpriseSourceError, match="too many members"):
        validate_archive(archive, 19)


def test_validate_signed_download_url_accepts_expected_target() -> None:
    url = "https://download.odoocdn.com/download/19e/src?payload=signed-value"

    assert validate_signed_download_url(url, 19) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://download.odoocdn.com/download/19e/src?payload=x",
        "https://evil.example/download/19e/src?payload=x",
        "https://download.odoocdn.com/download/18e/src?payload=x",
        "https://download.odoocdn.com/download/19e/src?payload=x&code=secret",
        "https://user@download.odoocdn.com/download/19e/src?payload=x",
    ],
)
def test_validate_signed_download_url_rejects_unexpected_target(url: str) -> None:
    with pytest.raises(EnterpriseSourceError, match="unexpected Enterprise download target"):
        validate_signed_download_url(url, 19)


def test_redirected_responses_are_rejected() -> None:
    with pytest.raises(EnterpriseSourceError, match="redirected"):
        _require_no_redirect(
            "https://download.odoocdn.com/download/19e/src?payload=x",
            "https://evil.example/source.tar.gz",
        )


def test_reused_archive_permissions_are_restricted(tmp_path: Path) -> None:
    output_dir = tmp_path / "enterprise"
    output_dir.mkdir(mode=0o755)
    archive = output_dir / "odoo-19e-source.tar.gz"
    _write_archive(archive)
    archive.chmod(0o644)

    result = fetch_version(19, code="unused", output_dir=output_dir, force=False)

    assert result == archive
    assert output_dir.stat().st_mode & 0o777 == 0o700
    assert archive.stat().st_mode & 0o777 == 0o600


def test_symlinked_output_directory_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    output_dir = tmp_path / "enterprise"
    output_dir.symlink_to(target, target_is_directory=True)

    with pytest.raises(EnterpriseSourceError, match="symlinked output directory"):
        fetch_version(19, code="unused", output_dir=output_dir, force=False)


def test_read_download_code_requires_private_permissions(tmp_path: Path) -> None:
    license_file = tmp_path / "license"
    license_file.write_text("secret\n")
    license_file.chmod(0o644)

    with pytest.raises(EnterpriseSourceError, match="0600"):
        read_download_code(license_file)

    license_file.chmod(0o600)
    assert read_download_code(license_file) == "secret"
