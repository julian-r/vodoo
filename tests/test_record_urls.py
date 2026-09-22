"""Record URLs follow the selected Odoo transport without extra requests."""

from types import SimpleNamespace
from typing import Any

import pytest

from vodoo.aio.projects import AsyncProjectNamespace
from vodoo.base import get_record_url
from vodoo.projects import ProjectNamespace


class _URLClient:
    def __init__(self, *, json2: bool) -> None:
        self.config = SimpleNamespace(url="https://odoo.example.test/")
        self.is_json2 = json2

    def __getattr__(self, name: str) -> Any:
        pytest.fail(f"URL generation unexpectedly accessed client.{name}")


@pytest.mark.parametrize(
    ("json2", "expected"),
    [
        (
            False,
            "https://odoo.example.test/web#id=7&model=project.project&view_type=form",
        ),
        (True, "https://odoo.example.test/odoo/project.project/7"),
    ],
)
def test_sync_namespace_url_uses_selected_transport(json2: bool, expected: str) -> None:
    client = _URLClient(json2=json2)
    namespace = ProjectNamespace(client)  # type: ignore[arg-type]

    assert namespace.url(7) == expected
    assert get_record_url(client, "project.project", 7) == expected


def test_get_record_url_defaults_custom_clients_to_legacy() -> None:
    client = SimpleNamespace(config=SimpleNamespace(url="https://odoo.example.test/"))

    assert get_record_url(client, "project.project", 7) == (
        "https://odoo.example.test/web#id=7&model=project.project&view_type=form"
    )


@pytest.mark.parametrize(
    ("json2", "expected"),
    [
        (
            False,
            "https://odoo.example.test/web#id=7&model=project.project&view_type=form",
        ),
        (True, "https://odoo.example.test/odoo/project.project/7"),
    ],
)
def test_async_namespace_url_uses_selected_transport_without_io(json2: bool, expected: str) -> None:
    client = _URLClient(json2=json2)
    namespace = AsyncProjectNamespace(client)  # type: ignore[arg-type]

    assert namespace.url(7) == expected
