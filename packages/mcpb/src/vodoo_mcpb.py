"""Claude Desktop extension (MCPB) launcher for the Vodoo MCP server.

Claude Desktop passes the extension settings as environment variables and
arguments. Settings the user left empty arrive as empty strings or as the
literal placeholder (``${user_config.name}``); both mean "not set", so Vodoo's
normal configuration (``~/.config/vodoo``) applies for them.

Arguments: zero or more upload folders.
"""

import os
import sys
from pathlib import Path

_PREFIXES = ("ODOO_", "VODOO_MCP_")


def _is_set(value: str | None) -> bool:
    return bool(value and value.strip()) and not str(value).startswith("${")


def main() -> None:
    for key in [k for k in os.environ if k.startswith(_PREFIXES)]:
        if not _is_set(os.environ[key]):
            del os.environ[key]

    def flag(name: str) -> bool:
        return os.environ.pop(name, "").strip().lower() == "true"

    allow_write = flag("VODOO_MCP_ALLOW_WRITE")
    allow_delete = flag("VODOO_MCP_ALLOW_DELETE")
    instance = os.environ.pop("VODOO_MCP_INSTANCE", None)
    download_dir = os.environ.pop("VODOO_MCP_DOWNLOAD_DIR", None)
    upload_dirs = [Path(arg).expanduser() for arg in sys.argv[1:] if _is_set(arg)]

    from vodoo.exceptions import VodooError
    from vodoo.mcp_server import run

    try:
        run(
            instance=instance,
            allow_write=allow_write,
            allow_delete=allow_delete,
            download_dir=Path(download_dir).expanduser() if download_dir else None,
            upload_dirs=upload_dirs or None,
        )
    except VodooError as exc:
        print(f"vodoo mcp: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
