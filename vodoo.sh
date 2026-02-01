#!/bin/bash
# Wrapper script for vodoo CLI
# Works both from host and sandbox (sandbox mounts ~/clawd as /agent)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect if we're in sandbox (path starts with /agent)
if [[ "$SCRIPT_DIR" == /agent/* ]]; then
    VODOO_BIN="$SCRIPT_DIR/.venv/bin/vodoo"
    CONFIG_PATH="/agent/private/vodoo.env"
else
    VODOO_BIN="$SCRIPT_DIR/.venv/bin/vodoo"
    CONFIG_PATH="$HOME/clawd/private/vodoo.env"
fi

# Load config if exists
if [[ -f "$CONFIG_PATH" ]]; then
    set -a
    source "$CONFIG_PATH"
    set +a
fi

exec "$VODOO_BIN" "$@"
