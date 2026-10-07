"""Hermetic checks for integration service provisioning and metadata-only audit exports."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.integration.service_account import (
    ADMINISTRATIVE_GROUPS,
    SERVICE_LOGIN,
    provision_service_account,
    write_field_access_audit,
)
from tests.integration.setup_odoo import create_api_key_via_shell, write_env


@pytest.mark.parametrize("enterprise", [False, True])
@pytest.mark.parametrize("reused", [False, True])
def test_service_groups_replace_defaults_without_privileges(enterprise: bool, reused: bool) -> None:
    client = MagicMock()
    client.security.create_groups.return_value = (
        {"API Base": 10, "API Project": 11, "API Knowledge": 12, "API Helpdesk": 13},
        [],
    )
    client.search.return_value = [7] if reused else []
    client.security.create_user.return_value = (7, "secret")
    client.security._groups_field.return_value = "group_ids"
    expected = [10, 11, 12, 13] if enterprise else [10, 11]
    client.security.get_user.return_value = {"share": True, "group_ids": expected}
    client.security._get_group_id_by_xmlid.side_effect = [1, 2, 3]
    assert provision_service_account(client, enterprise=enterprise) == (7, SERVICE_LOGIN)
    client.write.assert_called_once_with("res.users", [7], {"group_ids": [(6, 0, expected)]})
    assert client.security._get_group_id_by_xmlid.call_count == len(ADMINISTRATIVE_GROUPS)
    if reused:
        client.security.create_user.assert_not_called()
    else:
        client.security.create_user.assert_called_once()


def test_audit_exports_metadata_and_source_provenance_only(tmp_path: Path) -> None:
    path = tmp_path / "audit.json"
    result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        [], 0, stdout='VODOO_FIELD_AUDIT={"models": {}}\n'
    )
    labels = {"com.vodoo.enterprise.revision": "revision", "unrelated": "not exported"}
    with (
        patch("tests.integration.service_account.subprocess.run", return_value=result) as run,
        patch(
            "tests.integration.service_account.subprocess.check_output",
            side_effect=["sha256:image\n", json.dumps(labels)],
        ),
    ):
        write_field_access_audit(path, "test-container", "test-db", 7)
    script = run.call_args.kwargs["input"]
    ast.parse(script)
    assert "records._fields.items()" in script
    assert "with_user(user)" in script
    assert "model_read_access" in script
    report = json.loads(path.read_text())
    assert report["source"] == {
        "image_id": "sha256:image",
        "enterprise_provenance": {"com.vodoo.enterprise.revision": "revision"},
    }


def test_audit_missing_sentinel_is_not_success(tmp_path: Path) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess([], 0, stdout="")
    with (
        patch("tests.integration.service_account.subprocess.run", return_value=result),
        pytest.raises(RuntimeError, match="did not return"),
    ):
        write_field_access_audit(tmp_path / "audit.json", "test-container", "test-db", 7)
    assert not (tmp_path / "audit.json").exists()


@pytest.mark.parametrize("version", [17, 18, 19])
def test_service_key_has_service_owner_and_is_not_logged(version: int, capsys: Any) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        [], 0, stdout="VODOO_API_KEY=private-key\n"
    )
    with (
        patch("tests.integration.setup_odoo._odoo_container_name", return_value="test-container"),
        patch("tests.integration.setup_odoo.subprocess.run", return_value=result) as run,
    ):
        assert (
            create_api_key_via_shell("test-project", "test-db", version, user_id=7) == "private-key"
        )
    script = run.call_args.kwargs["input"]
    ast.parse(script)
    assert ".with_user(7).sudo()" in script
    assert "private-key" not in capsys.readouterr().out


def test_service_env_is_private_and_keeps_admin_separate(tmp_path: Path) -> None:
    path = tmp_path / "service.env"
    path.touch(mode=0o644)
    write_env(
        str(path), "http://localhost:19069", "test-db", "secret", 19, False, login=SERVICE_LOGIN
    )
    assert path.stat().st_mode & 0o777 == 0o600
    assert f"ODOO_USERNAME={SERVICE_LOGIN}\n" in path.read_text()
