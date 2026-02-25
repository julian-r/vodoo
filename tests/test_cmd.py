"""Tests for the Cmd ORM command helper class."""

from __future__ import annotations

from vodoo.cmd import Cmd


class TestCmd:
    """Each method returns the correct ORM command tuple."""

    def test_create(self) -> None:
        result = Cmd.create({"name": "New", "price_unit": 10.0})
        assert result == (0, 0, {"name": "New", "price_unit": 10.0})

    def test_update(self) -> None:
        result = Cmd.update(42, {"price_unit": 9.00})
        assert result == (1, 42, {"price_unit": 9.00})

    def test_delete(self) -> None:
        result = Cmd.delete(42)
        assert result == (2, 42, 0)

    def test_unlink(self) -> None:
        result = Cmd.unlink(42)
        assert result == (3, 42, 0)

    def test_link(self) -> None:
        result = Cmd.link(42)
        assert result == (4, 42, 0)

    def test_clear(self) -> None:
        result = Cmd.clear()
        assert result == (5, 0, 0)

    def test_set(self) -> None:
        result = Cmd.set([1, 2, 3])
        assert result == (6, 0, [1, 2, 3])

    def test_set_empty(self) -> None:
        result = Cmd.set([])
        assert result == (6, 0, [])


class TestCmdReturnTypes:
    """All methods return plain tuples — no subclasses or special types."""

    def test_create_is_tuple(self) -> None:
        assert type(Cmd.create({"x": 1})) is tuple

    def test_update_is_tuple(self) -> None:
        assert type(Cmd.update(1, {"x": 1})) is tuple

    def test_delete_is_tuple(self) -> None:
        assert type(Cmd.delete(1)) is tuple

    def test_unlink_is_tuple(self) -> None:
        assert type(Cmd.unlink(1)) is tuple

    def test_link_is_tuple(self) -> None:
        assert type(Cmd.link(1)) is tuple

    def test_clear_is_tuple(self) -> None:
        assert type(Cmd.clear()) is tuple

    def test_set_is_tuple(self) -> None:
        assert type(Cmd.set([1])) is tuple


class TestCmdComposition:
    """Cmd methods compose naturally into real-world x2many write values."""

    def test_mixed_commands(self) -> None:
        """Simulate a typical invoice line update."""
        commands = [
            Cmd.create({"name": "New line", "price_unit": 10.0}),
            Cmd.update(42, {"price_unit": 9.00}),
            Cmd.delete(43),
            Cmd.link(44),
        ]
        assert commands == [
            (0, 0, {"name": "New line", "price_unit": 10.0}),
            (1, 42, {"price_unit": 9.00}),
            (2, 43, 0),
            (4, 44, 0),
        ]

    def test_replace_all(self) -> None:
        """Simulate replacing all tags on a record."""
        commands = [Cmd.set([10, 20, 30])]
        assert commands == [(6, 0, [10, 20, 30])]

    def test_clear_and_recreate(self) -> None:
        """Simulate clearing and re-adding lines."""
        commands = [
            Cmd.clear(),
            Cmd.create({"name": "A"}),
            Cmd.create({"name": "B"}),
        ]
        assert commands == [
            (5, 0, 0),
            (0, 0, {"name": "A"}),
            (0, 0, {"name": "B"}),
        ]
