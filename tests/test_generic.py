"""Tests for generic model operations."""

from vodoo.client import OdooClient
from vodoo.generic import (
    create_record,
    delete_record,
    search_records,
    update_record,
)


def test_create_read_update_delete(client: OdooClient) -> None:
    """Test full CRUD cycle."""
    # Create
    record_id = create_record(
        client,
        "res.partner",
        {"name": "Test Partner", "email": "test@example.com"},
    )
    assert record_id > 0

    # Read
    records = search_records(
        client,
        "res.partner",
        domain=[["id", "=", record_id]],
    )
    assert len(records) == 1
    assert records[0]["name"] == "Test Partner"

    # Update
    success = update_record(
        client,
        "res.partner",
        record_id,
        {"phone": "+1234567890"},
    )
    assert success is True

    # Verify update
    records = search_records(
        client,
        "res.partner",
        domain=[["id", "=", record_id]],
    )
    assert records[0]["phone"] == "+1234567890"

    # Delete
    success = delete_record(client, "res.partner", record_id)
    assert success is True

    # Verify deletion
    records = search_records(
        client,
        "res.partner",
        domain=[["id", "=", record_id]],
    )
    assert len(records) == 0
