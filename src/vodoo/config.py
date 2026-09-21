"""Configuration management for Vodoo."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shlex
import subprocess
import warnings
from datetime import UTC, datetime, timedelta
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


def _parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ConfigurationError(f"Invalid {field_name!r} timestamp: {value!r}") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validate_headers_object(payload: Any, *, source: str) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ConfigurationError(f"{source} must be a JSON object of header name/value pairs")

    headers: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigurationError(f"{source} contains an invalid header name: {key!r}")
        if not isinstance(value, str):
            raise ConfigurationError(f"{source} header {key!r} must have a string value")
        headers[key] = value
    return headers


def _parse_headers_payload(
    raw_payload: str,
    *,
    source: str,
    now: datetime,
) -> tuple[dict[str, str], datetime | None]:
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{source} must output valid JSON") from exc

    if not isinstance(decoded, dict):
        raise ConfigurationError(f"{source} must output a JSON object")

    if "headers" not in decoded:
        headers = _validate_headers_object(decoded, source=source)
        return headers, None

    headers = _validate_headers_object(decoded.get("headers"), source=f"{source}.headers")
    expires_at: datetime | None = None

    raw_expires_at = decoded.get("expires_at")
    if raw_expires_at is not None:
        if not isinstance(raw_expires_at, str):
            raise ConfigurationError(f"{source}.expires_at must be an ISO-8601 string")
        expires_at = _parse_iso_datetime(raw_expires_at, field_name=f"{source}.expires_at")

    raw_expires_in = decoded.get("expires_in")
    if raw_expires_in is not None:
        if not isinstance(raw_expires_in, int | float):
            raise ConfigurationError(f"{source}.expires_in must be a number of seconds")
        if raw_expires_in <= 0:
            raise ConfigurationError(f"{source}.expires_in must be greater than zero")
        if expires_at is None:
            expires_at = now + timedelta(seconds=float(raw_expires_in))

    return headers, expires_at


def _expand_command_placeholders(command: str, values: dict[str, str]) -> str:
    expanded = command
    for key, value in values.items():
        expanded = expanded.replace(f"{{{key}}}", value)
    return expanded


def _get_keyring_backend() -> Any:
    try:
        return importlib.import_module("keyring")
    except ModuleNotFoundError as exc:
        raise ConfigurationError(
            "ODOO_HTTP_HEADERS_CACHE_BACKEND='keyring' requires the 'keyring' package. "
            "Install it or set ODOO_HTTP_HEADERS_CACHE_BACKEND=none."
        ) from exc


def _default_headers_cache_key(url: str, database: str, username: str, command: str) -> str:
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:12]
    return f"{url}|{database}|{username}|{digest}"


def _load_cached_headers(
    *,
    service_name: str,
    cache_key: str,
    now: datetime,
) -> dict[str, str] | None:
    keyring_backend = _get_keyring_backend()
    cached_raw = keyring_backend.get_password(service_name, cache_key)
    if not cached_raw:
        return None

    try:
        headers, expires_at = _parse_headers_payload(
            cached_raw,
            source="keyring header cache",
            now=now,
        )
    except ConfigurationError:
        return None
    if expires_at is not None and expires_at <= now:
        return None
    return headers


def _store_cached_headers(
    *,
    service_name: str,
    cache_key: str,
    headers: dict[str, str],
    expires_at: datetime | None,
) -> None:
    keyring_backend = _get_keyring_backend()
    payload: dict[str, Any] = {"headers": headers}
    if expires_at is not None:
        payload["expires_at"] = expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z")

    serialized = json.dumps(payload, separators=(",", ":"))
    keyring_backend.set_password(service_name, cache_key, serialized)


def _resolve_http_headers_from_command(
    *,
    command: str,
    cache_backend: Literal["keyring", "none"],
    cache_key: str,
    cache_ttl: int,
    timeout: int,
    command_env: dict[str, str] | None = None,
    output_mode: Literal["json", "token"],
    token_header: str | None,
) -> dict[str, str]:
    now = datetime.now(UTC)
    cache_service = "vodoo-http-headers"

    if cache_backend == "keyring":
        cached_headers = _load_cached_headers(
            service_name=cache_service,
            cache_key=cache_key,
            now=now,
        )
        if cached_headers is not None:
            return cached_headers

    env = os.environ.copy()
    if command_env:
        env.update(command_env)

    expanded_command = _expand_command_placeholders(command, command_env or {})
    args = shlex.split(expanded_command)
    if not args:
        raise ConfigurationError("ODOO_HTTP_HEADERS_CMD is empty")

    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise ConfigurationError(
            f"Failed to run ODOO_HTTP_HEADERS_CMD ({command!r}): executable not found"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise ConfigurationError(f"ODOO_HTTP_HEADERS_CMD failed: {stderr}")

    stdout = result.stdout.strip()
    if not stdout:
        raise ConfigurationError("ODOO_HTTP_HEADERS_CMD returned empty output")

    if output_mode == "token":
        if token_header is None or not token_header.strip():
            raise ConfigurationError(
                "ODOO_HTTP_HEADERS_CMD_HEADER is required when ODOO_HTTP_HEADERS_CMD_OUTPUT=token"
            )
        headers = {token_header: stdout}
        expires_at = None
    else:
        headers, expires_at = _parse_headers_payload(
            stdout,
            source="ODOO_HTTP_HEADERS_CMD",
            now=now,
        )

    if expires_at is None and cache_ttl > 0:
        expires_at = now + timedelta(seconds=cache_ttl)

    if cache_backend == "keyring" and cache_ttl != 0:
        _store_cached_headers(
            service_name=cache_service,
            cache_key=cache_key,
            headers=headers,
            expires_at=expires_at,
        )

    return headers


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
    default_user_id: int | None = Field(
        None, description="Default user ID for displayed message author attribution"
    )
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
    http_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Extra HTTP headers sent with every request (JSON object)",
    )
    http_headers_cmd: str | None = Field(
        None,
        description=("Optional command to derive HTTP headers (JSON object or raw token output)"),
    )
    http_headers_cmd_output: Literal["json", "token"] = Field(
        "json",
        description="Expected ODOO_HTTP_HEADERS_CMD stdout format",
    )
    http_headers_cmd_header: str | None = Field(
        None,
        description="Header name used when ODOO_HTTP_HEADERS_CMD_OUTPUT=token",
    )
    http_headers_cmd_timeout: int = Field(
        120,
        description="Timeout in seconds for ODOO_HTTP_HEADERS_CMD execution",
    )
    http_headers_cache_backend: Literal["keyring", "none"] = Field(
        "keyring",
        description="Cache backend for command-derived headers",
    )
    http_headers_cache_key: str | None = Field(
        None,
        description="Optional cache key override for command-derived headers",
    )
    http_headers_cache_ttl: int = Field(
        300,
        description="Fallback cache TTL in seconds when command output has no expiry",
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

    @model_validator(mode="after")
    def _resolve_http_headers_cmd(self) -> OdooConfig:
        command = (self.http_headers_cmd or "").strip()
        if not command:
            return self

        if self.http_headers_cmd_timeout <= 0:
            raise ConfigurationError("ODOO_HTTP_HEADERS_CMD_TIMEOUT must be greater than zero")
        if self.http_headers_cache_ttl < 0:
            raise ConfigurationError("ODOO_HTTP_HEADERS_CACHE_TTL must be zero or greater")
        if self.http_headers_cmd_output == "token":
            header = self.http_headers_cmd_header
            if header is None or not header.strip():
                raise ConfigurationError(
                    "ODOO_HTTP_HEADERS_CMD_HEADER is required when "
                    "ODOO_HTTP_HEADERS_CMD_OUTPUT=token"
                )

        cache_key = self.http_headers_cache_key
        if cache_key is None or not cache_key.strip():
            cache_key_value = _default_headers_cache_key(
                self.url,
                self.database,
                self.username,
                command,
            )
        else:
            cache_key_value = cache_key

        dynamic_headers = _resolve_http_headers_from_command(
            command=command,
            cache_backend=self.http_headers_cache_backend,
            cache_key=cache_key_value,
            cache_ttl=self.http_headers_cache_ttl,
            timeout=self.http_headers_cmd_timeout,
            command_env={
                "ODOO_URL": self.url,
                "ODOO_DATABASE": self.database,
                "ODOO_USERNAME": self.username,
            },
            output_mode=self.http_headers_cmd_output,
            token_header=self.http_headers_cmd_header,
        )

        # Explicitly configured headers override command-derived values.
        self.http_headers = {**dynamic_headers, **self.http_headers}
        return self

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
