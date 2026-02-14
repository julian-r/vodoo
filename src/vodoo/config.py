"""Configuration management for Vodoo."""

import warnings
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vodoo.transport import DEFAULT_RETRY, RetryConfig


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

    @property
    def retry_config(self) -> RetryConfig:
        """Build a :class:`RetryConfig` from the configuration values."""
        return RetryConfig(
            max_retries=self.retry_count,
            backoff_base=self.retry_backoff,
            backoff_max=self.retry_max_backoff,
        )

    @model_validator(mode="after")
    def _warn_insecure_url(self) -> "OdooConfig":
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
    def from_file(cls, config_path: Path | None = None) -> "OdooConfig":
        """Load configuration from file.

        Args:
            config_path: Path to config file. If None, uses default locations.

        Returns:
            OdooConfig instance

        """
        if config_path is None:
            # Try config locations, most specific first (local overrides global).
            possible_paths = [
                Path.cwd() / ".vodoo.env",
                Path.cwd() / ".env",
                Path.home() / ".config" / "vodoo" / "config.env",
            ]
            for path in possible_paths:
                if path.exists():
                    config_path = path
                    break

        if config_path and config_path.exists():
            return cls(_env_file=str(config_path))  # type: ignore[call-arg]

        return cls()  # type: ignore[call-arg]


def get_config() -> OdooConfig:
    """Get the Odoo configuration.

    Returns:
        OdooConfig instance

    """
    return OdooConfig.from_file()
