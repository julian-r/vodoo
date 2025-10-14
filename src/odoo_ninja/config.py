"""Configuration management for Odoo Ninja."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OdooConfig(BaseSettings):
    """Odoo connection configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ODOO_",
        case_sensitive=False,
    )

    url: str = Field(..., description="Odoo instance URL")
    database: str = Field(..., description="Odoo database name")
    username: str = Field(..., description="Odoo username")
    password: str = Field(..., description="Odoo password or API key")
    default_user_id: int | None = Field(None, description="Default user ID for sudo operations")
    allow_harmful_operations: bool = Field(
        False,
        description="Allow harmful operations like posting public comments (visible to customers)",
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
            # Try common config locations
            possible_paths = [
                Path.cwd() / ".odoo-ninja.env",
                Path.home() / ".config" / "odoo-ninja" / "config.env",
                Path.cwd() / ".env",
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
