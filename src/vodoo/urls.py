"""Odoo web-client URL construction."""

from typing import Literal


def build_record_url(
    base_url: str,
    model: str,
    record_id: int,
    dialect: Literal["jsonrpc", "json2"],
) -> str:
    """Build the canonical record URL for a selected transport dialect.

    JSON-2 identifies Odoo 19+, whose web client uses path-based record URLs.
    Legacy clients retain the hash URL accepted by Odoo 17 and 18.
    """
    base = base_url.rstrip("/")
    if dialect == "json2":
        model_path = model if "." in model else f"m-{model}"
        return f"{base}/odoo/{model_path}/{record_id}"
    return f"{base}/web#id={record_id}&model={model}&view_type=form"
