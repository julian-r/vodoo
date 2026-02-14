"""Pytest configuration for vodoo integration tests.

Provides fixtures and CLI options for running tests against live Odoo instances.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vodoo.client import OdooClient
from vodoo.config import OdooConfig


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--odoo-version",
        type=int,
        default=None,
        help="Odoo major version under test (17, 18, 19)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "enterprise: mark test as requiring enterprise edition")
    config.addinivalue_line("markers", "odoo17: mark test as Odoo 17 specific")
    config.addinivalue_line("markers", "odoo18: mark test as Odoo 18 specific")
    config.addinivalue_line("markers", "odoo19: mark test as Odoo 19 specific")


@pytest.fixture(scope="session")
def odoo_version(request: pytest.FixtureRequest) -> int:
    """Odoo major version under test."""
    v = request.config.getoption("--odoo-version")
    if v is None:
        env_file = os.environ.get("VODOO_TEST_ENV", "")
        if env_file and Path(env_file).exists():
            for line in Path(env_file).read_text().splitlines():
                if line.startswith("ODOO_MAJOR_VERSION="):
                    return int(line.split("=", 1)[1])
        pytest.skip("No --odoo-version specified and no env file found")
    return int(v)


@pytest.fixture(scope="session")
def is_enterprise() -> bool:
    """Whether the Odoo under test has enterprise modules."""
    env_file = os.environ.get("VODOO_TEST_ENV", "")
    if env_file and Path(env_file).exists():
        for line in Path(env_file).read_text().splitlines():
            if line.startswith("ODOO_ENTERPRISE="):
                return line.split("=", 1)[1].strip() == "1"
    return False


@pytest.fixture(scope="session")
def odoo_config() -> OdooConfig:
    """Load OdooConfig from the test env file."""
    env_file = os.environ.get("VODOO_TEST_ENV", "")
    if not env_file or not Path(env_file).exists():
        pytest.skip(f"VODOO_TEST_ENV not set or file missing: {env_file!r}")

    return OdooConfig(_env_file=env_file)  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def client(odoo_config: OdooConfig) -> OdooClient:
    """Authenticated OdooClient for the test instance."""
    c = OdooClient(odoo_config)
    # Force authentication to fail fast
    _ = c.uid
    return c


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests based on edition and version markers."""
    version = config.getoption("--odoo-version")
    env_file = os.environ.get("VODOO_TEST_ENV", "")
    enterprise = False
    if env_file and Path(env_file).exists():
        for line in Path(env_file).read_text().splitlines():
            if line.startswith("ODOO_ENTERPRISE=1"):
                enterprise = True

    for item in items:
        # Skip enterprise tests when running community
        if "enterprise" in item.keywords and not enterprise:
            item.add_marker(pytest.mark.skip(reason="Enterprise module not available"))

        # Skip version-specific tests
        if version is not None:
            for v in (17, 18, 19):
                marker = f"odoo{v}"
                if marker in item.keywords and version != v:
                    item.add_marker(pytest.mark.skip(reason=f"Test requires Odoo {v}"))
