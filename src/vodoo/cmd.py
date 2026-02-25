"""Readable helpers for Odoo One2many / Many2many ORM command tuples.

Odoo's ORM uses numeric command tuples to manipulate relational fields::

    # Raw tuples — hard to read and remember
    client.write("account.move", [446], {
        "invoice_line_ids": [
            (0, 0, {"name": "Line 1", "price_unit": 10.0}),
            (1, 42, {"price_unit": 9.00}),
            (2, 43, 0),
            (6, 0, [1, 2, 3]),
        ]
    })

The :class:`Cmd` class wraps each command in a named static method::

    from vodoo import Cmd

    client.write("account.move", [446], {
        "invoice_line_ids": [
            Cmd.create({"name": "Line 1", "price_unit": 10.0}),
            Cmd.update(42, {"price_unit": 9.00}),
            Cmd.delete(42),
            Cmd.set([1, 2, 3]),
        ]
    })

Each method returns a plain :class:`tuple`, so it is fully backward-compatible
with any code that already accepts ORM command tuples.

Reference: https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html#odoo.fields.Command
"""

from __future__ import annotations

from typing import Any


class Cmd:
    """Readable wrappers for Odoo ORM command tuples (One2many / Many2many fields).

    Every method returns a plain ``tuple`` — no special types or magic.
    """

    @staticmethod
    def create(values: dict[str, Any]) -> tuple[int, int, dict[str, Any]]:
        """Create a new related record.

        ``(0, 0, values)`` — create a new record with the given field values
        and link it to the parent.

        Example::

            Cmd.create({"name": "New line", "price_unit": 10.0})
        """
        return (0, 0, values)

    @staticmethod
    def update(record_id: int, values: dict[str, Any]) -> tuple[int, int, dict[str, Any]]:
        """Update an existing related record in place.

        ``(1, id, values)`` — write *values* on the linked record.

        Example::

            Cmd.update(42, {"price_unit": 9.00})
        """
        return (1, record_id, values)

    @staticmethod
    def delete(record_id: int) -> tuple[int, int, int]:
        """Remove a related record from the set **and delete it**.

        ``(2, id, 0)`` — unlink from the parent and delete the record from
        the database.

        Example::

            Cmd.delete(42)
        """
        return (2, record_id, 0)

    @staticmethod
    def unlink(record_id: int) -> tuple[int, int, int]:
        """Remove a related record from the set **without deleting it**.

        ``(3, id, 0)`` — remove the link but keep the record in the database.
        Only meaningful for Many2many fields.

        Example::

            Cmd.unlink(42)
        """
        return (3, record_id, 0)

    @staticmethod
    def link(record_id: int) -> tuple[int, int, int]:
        """Add an existing record to the set.

        ``(4, id, 0)`` — link an existing record without creating or
        modifying it.

        Example::

            Cmd.link(42)
        """
        return (4, record_id, 0)

    @staticmethod
    def clear() -> tuple[int, int, int]:
        """Remove all records from the set **without deleting them**.

        ``(5, 0, 0)`` — unlink all records from the parent. The records
        themselves are not deleted.

        Example::

            Cmd.clear()
        """
        return (5, 0, 0)

    @staticmethod
    def set(ids: list[int]) -> tuple[int, int, list[int]]:
        """Replace all linked records with the given list.

        ``(6, 0, ids)`` — unlink all current records and link exactly the
        records in *ids*. Equivalent to ``clear()`` + ``link()`` for each id.

        Example::

            Cmd.set([1, 2, 3])
        """
        return (6, 0, ids)
