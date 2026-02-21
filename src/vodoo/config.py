"""Configuration management for Vodoo."""

from __future__ import annotations

import os
import re
import subprocess
import warnings
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vodoo.exceptions import ConfigurationError
from vodoo.transport import DEFAULT_RETRY, RetryConfig

_DEFAULT_INSTANCE = "default"
_INSTANCE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _project_config_dir() -> Path:
    return Path.cwd() / ".vodoo"


def _global_config_dir() -> Path:
    return Path.home() / ".config" / "vodoo"


def _normalize_instance_name(name: str) -> str:
    instance = name.strip()
    if not instance:
        return _DEFAULT_INSTANCE
    if not _INSTANCE_NAME_RE.fullmatch(instance):
        raise ConfigurationError(
            f"Invalid instance name {name!r}. Use letters, digits, '.', '_' or '-' only.",
        )
    return instance


def _read_default_instance(default_file: Path) -> str | None:
    if not default_file.exists():
        return None

    try:
        raw = default_file.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - rare filesystem errors
        raise ConfigurationError(f"Failed to read default instance file: {default_file}") from exc

    for line in raw.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#"):
            return _normalize_instance_name(candidate)
    return None


def _resolve_instance(instance: str | None = None) -> tuple[str, bool]:
    if instance is not None:
        return _normalize_instance_name(instance), True

    env_instance = os.environ.get("VODOO_INSTANCE", "")
    if env_instance.strip():
        return _normalize_instance_name(env_instance), True

    default_files = [
        _project_config_dir() / "default-instance",
        _global_config_dir() / "default-instance",
    ]
    for default_file in default_files:
        selected = _read_default_instance(default_file)
        if selected:
            return selected, True

    return _DEFAULT_INSTANCE, False


def _default_instance_file(scope: Literal["project", "global"]) -> Path:
    if scope == "project":
        return _project_config_dir() / "default-instance"
    return _global_config_dir() / "default-instance"


def _instance_config_candidates(instance: str) -> list[Path]:
    filename = f"{instance}.env"
    return [
        _project_config_dir() / "instances" / filename,
        _global_config_dir() / "instances" / filename,
    ]


def _legacy_config_candidates() -> list[Path]:
    return [
        Path.cwd() / ".vodoo.env",
        Path.cwd() / ".env",
        _global_config_dir() / "config.env",
    ]


def _has_env_credentials() -> bool:
    required = ["ODOO_URL", "ODOO_DATABASE", "ODOO_USERNAME"]
    if any(not os.environ.get(key, "").strip() for key in required):
        return False

    password = os.environ.get("ODOO_PASSWORD", "").strip()
    password_ref = os.environ.get("ODOO_PASSWORD_REF", "").strip()
    return bool(password or password_ref)


def resolve_instance(instance: str | None = None) -> str:
    """Resolve the effective instance/profile name."""
    return _resolve_instance(instance)[0]


def read_default_instance(scope: Literal["project", "global"]) -> str | None:
    """Read the default instance from the given scope."""
    return _read_default_instance(_default_instance_file(scope))


def write_default_instance(
    instance: str,
    scope: Literal["project", "global"] = "project",
) -> Path:
    """Write the default instance file and return its path."""
    normalized = _normalize_instance_name(instance)
    target = _default_instance_file(scope)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{normalized}\n", encoding="utf-8")
    return target


def list_instance_profiles() -> dict[str, list[Path]]:
    """List available instance profile files by instance name."""
    profiles: dict[str, list[Path]] = {}
    profile_dirs = [
        _project_config_dir() / "instances",
        _global_config_dir() / "instances",
    ]

    for directory in profile_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for env_file in sorted(directory.glob("*.env")):
            name = env_file.stem
            if not _INSTANCE_NAME_RE.fullmatch(name):
                continue
            profiles.setdefault(name, []).append(env_file)

    return dict(sorted(profiles.items(), key=lambda item: item[0]))


def detect_config_file(
    instance: str | None = None,
    config_path: Path | None = None,
) -> Path | None:
    """Return the selected config file path, if any."""
    if config_path is not None:
        if not config_path.exists():
            raise ConfigurationError(f"Config file not found: {config_path}")
        return config_path

    instance_name, instance_explicit = _resolve_instance(instance)

    for path in _instance_config_candidates(instance_name):
        if path.exists():
            return path

    if instance_explicit:
        return None

    for path in _legacy_config_candidates():
        if path.exists():
            return path

    return None


def _resolve_secret_reference(secret_ref: str) -> str:
    ref = secret_ref.strip()

    if ref.startswith("op://"):
        try:
            result = subprocess.run(
                ["op", "read", ref],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(
                "1Password CLI 'op' not found. Install it and run 'op signin' "
                "or use ODOO_PASSWORD directly."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise ConfigurationError(f"Failed to read secret from 1Password ({ref}): {stderr}")

        value = result.stdout.strip()
        if not value:
            raise ConfigurationError(f"1Password reference returned an empty secret: {ref}")

        return value

    raise ConfigurationError(
        f"Unsupported secret reference {secret_ref!r}. Supported format: 'op://vault/item/field'."
    )


class OdooConfig(BaseSettings):
    """Odoo connection configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ODOO_",
        case_sensitive=False,
        extra="ignore",
    )

    url: str = Field(..., description="Odoo instance URL")
    database: str = Field(..., description="Odoo database name")
    username: str = Field(..., description="Odoo username")
    password: str = Field(..., description="Odoo password or API key")
    password_ref: str | None = Field(
        None,
        description="Optional secret reference (e.g. op://...) used to resolve password",
    )
    default_user_id: int | None = Field(None, description="Default user ID for sudo operations")
    retry_count: int = Field(
        DEFAULT_RETRY.max_retries,
        description="Maximum number of retries for transient errors (0 to disable)",
    )
    retry_backoff: float = Field(
        DEFAULT_RETRY.backoff_base,
        description="Base backoff delay in seconds (exponential: base * 2^attempt)",
    )
    retry_max_backoff: float = Field(
        DEFAULT_RETRY.backoff_max,
        description="Maximum backoff delay in seconds",
    )

    @model_validator(mode="before")
    @classmethod
    def _resolve_password_refs(cls, data: Any) -> Any:
        """Resolve ``password_ref`` / secret-reference passwords before validation."""
        if not isinstance(data, dict):
            return data

        values = dict(data)
        password_value = values.get("password")
        password_ref = values.get("password_ref")

        secret_ref: str | None = None
        if isinstance(password_ref, str) and password_ref.strip():
            secret_ref = password_ref.strip()
        elif isinstance(password_value, str) and password_value.strip().startswith("op://"):
            secret_ref = password_value.strip()

        if secret_ref:
            values["password"] = _resolve_secret_reference(secret_ref)

        return values

    @property
    def retry_config(self) -> RetryConfig:
        """Build a :class:`RetryConfig` from the configuration values."""
        return RetryConfig(
            max_retries=self.retry_count,
            backoff_base=self.retry_backoff,
            backoff_max=self.retry_max_backoff,
        )

    @model_validator(mode="after")
    def _warn_insecure_url(self) -> OdooConfig:
        """Emit a warning when the Odoo URL does not use HTTPS.

        This intentionally warns rather than raises so that local
        development setups (``http://localhost``) still work.
        """
        if self.url and not self.url.startswith("https://"):
            warnings.warn(
                f"ODOO_URL ({self.url}) does not use HTTPS. "
                "Credentials will be sent in cleartext. "
                "Use https:// in production.",
                UserWarning,
                stacklevel=2,
            )
        return self

    def __repr__(self) -> str:
        """Mask password in repr to avoid leaking credentials in logs."""
        return (
            f"OdooConfig(url={self.url!r}, database={self.database!r}, "
            f"username={self.username!r}, password='***', "
            f"default_user_id={self.default_user_id!r})"
        )

    @classmethod
    def from_file(
        cls,
        config_path: Path | None = None,
        *,
        instance: str | None = None,
    ) -> OdooConfig:
        """Load configuration from file.

        Args:
            config_path: Explicit path to a config file.
            instance: Optional instance/profile name.

        Returns:
            OdooConfig instance.

        """
        selected_file = detect_config_file(instance=instance, config_path=config_path)
        if selected_file is not None:
            return cls(_env_file=str(selected_file))  # type: ignore[call-arg]

        instance_name, instance_explicit = _resolve_instance(instance)
        if instance_explicit:
            if _has_env_credentials():
                return cls(_env_file=None)  # type: ignore[call-arg]

            candidates = ", ".join(str(p) for p in _instance_config_candidates(instance_name))
            raise ConfigurationError(
                f"No config found for instance '{instance_name}'. Looked in: {candidates}."
            )

        return cls()  # type: ignore[call-arg]


def get_config(
    instance: str | None = None,
    config_path: Path | None = None,
) -> OdooConfig:
    """Get the Odoo configuration.

    Args:
        instance: Optional instance/profile name.
        config_path: Explicit path to a config file.

    Returns:
        OdooConfig instance.

    """
    try:
        return OdooConfig.from_file(config_path=config_path, instance=instance)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration: {exc}") from exc
