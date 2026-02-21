"""Tests for configuration loading and secret resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from vodoo.config import OdooConfig, get_config
from vodoo.exceptions import ConfigurationError

_REQUIRED_ENV_KEYS = [
    "ODOO_URL",
    "ODOO_DATABASE",
    "ODOO_USERNAME",
    "ODOO_PASSWORD",
    "ODOO_PASSWORD_REF",
    "VODOO_INSTANCE",
]


def _clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _REQUIRED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_env(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestMultiInstanceConfig:
    def test_instance_arg_prefers_project_profile(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        _write_env(
            tmp_path / ".vodoo" / "instances" / "staging.env",
            "\n".join(
                [
                    "ODOO_URL=https://project-staging.example.com",
                    "ODOO_DATABASE=project_staging",
                    "ODOO_USERNAME=project-user",
                    "ODOO_PASSWORD=project-secret",
                ]
            ),
        )
        _write_env(
            home / ".config" / "vodoo" / "instances" / "staging.env",
            "\n".join(
                [
                    "ODOO_URL=https://global-staging.example.com",
                    "ODOO_DATABASE=global_staging",
                    "ODOO_USERNAME=global-user",
                    "ODOO_PASSWORD=global-secret",
                ]
            ),
        )

        cfg = get_config(instance="staging")

        assert cfg.url == "https://project-staging.example.com"
        assert cfg.database == "project_staging"
        assert cfg.username == "project-user"
        assert cfg.password == "project-secret"

    def test_default_instance_file_is_used(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        default_instance_file = tmp_path / ".vodoo" / "default-instance"
        default_instance_file.parent.mkdir(parents=True, exist_ok=True)
        default_instance_file.write_text("staging\n", encoding="utf-8")

        _write_env(
            tmp_path / ".vodoo" / "instances" / "staging.env",
            "\n".join(
                [
                    "ODOO_URL=https://staging.example.com",
                    "ODOO_DATABASE=staging",
                    "ODOO_USERNAME=staging-user",
                    "ODOO_PASSWORD=staging-secret",
                ]
            ),
        )

        cfg = get_config()

        assert cfg.url == "https://staging.example.com"
        assert cfg.database == "staging"

    def test_missing_explicit_instance_raises_configuration_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ConfigurationError, match="No config found for instance 'prod'"):
            get_config(instance="prod")

    def test_explicit_instance_does_not_fallback_to_legacy_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        _write_env(
            tmp_path / ".env",
            "\n".join(
                [
                    "ODOO_URL=https://legacy.example.com",
                    "ODOO_DATABASE=legacy",
                    "ODOO_USERNAME=legacy-user",
                    "ODOO_PASSWORD=legacy-secret",
                ]
            ),
        )

        with pytest.raises(ConfigurationError, match="No config found for instance 'prod'"):
            get_config(instance="prod")

    def test_get_config_wraps_validation_errors(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            get_config()


class TestConfigUtilities:
    def test_write_and_read_default_instance(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        from vodoo.config import read_default_instance, write_default_instance

        project_target = write_default_instance("staging", scope="project")
        global_target = write_default_instance("prod", scope="global")

        assert project_target == tmp_path / ".vodoo" / "default-instance"
        assert global_target == home / ".config" / "vodoo" / "default-instance"
        assert read_default_instance("project") == "staging"
        assert read_default_instance("global") == "prod"

    def test_detect_config_file_prefers_project_instance(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        project_path = tmp_path / ".vodoo" / "instances" / "prod.env"
        global_path = home / ".config" / "vodoo" / "instances" / "prod.env"
        _write_env(
            project_path,
            "\n".join(
                [
                    "ODOO_URL=https://project.example.com",
                    "ODOO_DATABASE=project",
                    "ODOO_USERNAME=project",
                    "ODOO_PASSWORD=project",
                ]
            ),
        )
        _write_env(
            global_path,
            "\n".join(
                [
                    "ODOO_URL=https://global.example.com",
                    "ODOO_DATABASE=global",
                    "ODOO_USERNAME=global",
                    "ODOO_PASSWORD=global",
                ]
            ),
        )

        from vodoo.config import detect_config_file

        selected = detect_config_file(instance="prod")
        assert selected == project_path

    def test_list_instance_profiles_collects_project_and_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(tmp_path)

        project_path = tmp_path / ".vodoo" / "instances" / "staging.env"
        global_path = home / ".config" / "vodoo" / "instances" / "staging.env"
        _write_env(
            project_path,
            "\n".join(
                [
                    "ODOO_URL=https://project.example.com",
                    "ODOO_DATABASE=project",
                    "ODOO_USERNAME=project",
                    "ODOO_PASSWORD=project",
                ]
            ),
        )
        _write_env(
            global_path,
            "\n".join(
                [
                    "ODOO_URL=https://global.example.com",
                    "ODOO_DATABASE=global",
                    "ODOO_USERNAME=global",
                    "ODOO_PASSWORD=global",
                ]
            ),
        )

        from vodoo.config import list_instance_profiles

        profiles = list_instance_profiles()
        assert "staging" in profiles
        assert project_path in profiles["staging"]
        assert global_path in profiles["staging"]


class TestSecretResolution:
    def test_password_ref_uses_1password_cli(self) -> None:
        with patch("vodoo.config.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["op", "read", "op://vault/item/password"],
                returncode=0,
                stdout="resolved-secret\n",
                stderr="",
            )

            cfg = OdooConfig(
                url="https://secure.example.com",
                database="db",
                username="user",
                password_ref="op://vault/item/password",
            )

        assert cfg.password == "resolved-secret"

    def test_password_ref_in_env_file_is_resolved(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_config_env(monkeypatch)

        env_file = tmp_path / "prod.env"
        _write_env(
            env_file,
            "\n".join(
                [
                    "ODOO_URL=https://secure.example.com",
                    "ODOO_DATABASE=db",
                    "ODOO_USERNAME=user",
                    "ODOO_PASSWORD_REF=op://vault/item/password",
                ]
            ),
        )

        with patch("vodoo.config.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["op", "read", "op://vault/item/password"],
                returncode=0,
                stdout="resolved-from-file\n",
                stderr="",
            )

            cfg = OdooConfig(_env_file=str(env_file))  # type: ignore[call-arg]

        assert cfg.password == "resolved-from-file"

    def test_password_ref_errors_when_op_missing(self) -> None:
        with (
            patch("vodoo.config.subprocess.run", side_effect=FileNotFoundError),
            pytest.raises(ConfigurationError, match="1Password CLI 'op' not found"),
        ):
            OdooConfig(
                url="https://secure.example.com",
                database="db",
                username="user",
                password_ref="op://vault/item/password",
            )

    def test_password_ref_errors_on_cli_failure(self) -> None:
        with patch("vodoo.config.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["op", "read", "op://vault/item/password"],
                returncode=1,
                stdout="",
                stderr="not signed in",
            )

            with pytest.raises(ConfigurationError, match="Failed to read secret from 1Password"):
                OdooConfig(
                    url="https://secure.example.com",
                    database="db",
                    username="user",
                    password_ref="op://vault/item/password",
                )
