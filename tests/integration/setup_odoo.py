#!/usr/bin/env python3
"""Initialize an Odoo database and create an API key for testing.

This script:
1. Waits for Odoo to be healthy
2. Creates the database via the JSON-RPC ``db`` service
3. Installs community modules (project, crm) and optionally enterprise ones
4. Creates an API key via ``odoo shell`` inside the Docker container

Usage:
    python setup_odoo.py --port 19069 --version 19 --project vodoo-test-19
    python setup_odoo.py --port 19169 --version 19 --project vodoo-test-19ee --enterprise
"""

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

MASTER_PASSWORD = "vodoo-test-master"
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin"


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def jsonrpc(url: str, service: str, method: str, args: list) -> object:
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"service": service, "method": method, "args": args},
        "id": 1,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{url}/jsonrpc",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode())
    if "error" in body:
        raise RuntimeError(f"JSON-RPC error: {json.dumps(body['error'], indent=2)}")
    return body.get("result")


def execute_kw(
    url: str,
    db: str,
    uid: int,
    pwd: str,
    model: str,
    method: str,
    args: list,
    kwargs: dict | None = None,
) -> object:
    return jsonrpc(url, "object", "execute_kw", [db, uid, pwd, model, method, args, kwargs or {}])


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


def wait_for_odoo(url: str, max_wait: int = 180) -> None:
    print(f"Waiting for Odoo at {url} …", end="", flush=True)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{url}/web/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    print(" ready!")
                    return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    raise TimeoutError(f"Odoo not ready after {max_wait}s")


def db_exists(url: str, db_name: str) -> bool:
    try:
        dbs = jsonrpc(url, "db", "list", [])
        return db_name in dbs
    except Exception:
        return False


def create_database(url: str, db_name: str) -> None:
    print(f"Creating database '{db_name}' …")
    jsonrpc(
        url,
        "db",
        "create_database",
        [MASTER_PASSWORD, db_name, False, "en_US", ADMIN_PASSWORD, ADMIN_LOGIN, None, None],
    )
    print(f"Database '{db_name}' created.")


def authenticate(url: str, db_name: str) -> int:
    uid = jsonrpc(url, "common", "authenticate", [db_name, ADMIN_LOGIN, ADMIN_PASSWORD, {}])
    if not isinstance(uid, int) or uid <= 0:
        raise RuntimeError("Admin authentication failed")
    return uid


def install_modules(url: str, db_name: str, uid: int, modules: list[str]) -> None:
    print(f"Installing modules: {', '.join(modules)} …")
    not_installed = execute_kw(
        url,
        db_name,
        uid,
        ADMIN_PASSWORD,
        "ir.module.module",
        "search",
        [[["name", "in", modules], ["state", "!=", "installed"]]],
    )
    if not not_installed:
        print("  All modules already installed.")
        return
    for mod_id in not_installed:
        execute_kw(
            url,
            db_name,
            uid,
            ADMIN_PASSWORD,
            "ir.module.module",
            "button_immediate_install",
            [[mod_id]],
        )
    print(f"  Installed {len(not_installed)} module(s).")


def enable_features(url: str, db_name: str, uid: int) -> None:
    """Enable project/CRM features via res.config.settings.

    This is equivalent to an admin toggling settings in the UI.
    Without this, fields like stage_id on projects are access-restricted.
    """
    print("Enabling project/CRM features …")
    settings_id = execute_kw(
        url,
        db_name,
        uid,
        ADMIN_PASSWORD,
        "res.config.settings",
        "create",
        [{"group_project_stages": True}],
    )
    execute_kw(
        url,
        db_name,
        uid,
        ADMIN_PASSWORD,
        "res.config.settings",
        "set_values",
        [[settings_id]],
    )
    print("  Features enabled.")


# ---------------------------------------------------------------------------
# API key via odoo shell inside the Docker container
# ---------------------------------------------------------------------------


def create_api_key_via_shell(docker_project: str, db_name: str, odoo_major: int) -> str:
    """Run ``odoo shell`` inside the container to call ``_generate`` on the
    ``res.users.apikeys`` model and capture the returned key.
    """
    # _generate uses self.env.user.id for the key's user_id.
    # The odoo shell runs as __system__ (uid=1) which is inactive, so
    # bearer auth would reject the key.  We switch to the admin user
    # via with_user() so the key is bound to an active user.
    #
    # _generate signature changed between 17 and 18:
    #   17: _generate(scope, name)
    #   18+: _generate(scope, name, expiration_date)
    admin_ref = "env.ref('base.user_admin')"
    apikeys = f"env['res.users.apikeys'].with_user({admin_ref}).sudo()"
    if odoo_major <= 17:
        generate_call = f"{apikeys}._generate('rpc', 'vodoo-integration-test')"
    else:
        generate_call = f"{apikeys}._generate('rpc', 'vodoo-integration-test', None)"

    # Python snippet executed inside odoo shell.
    # We print a sentinel so we can reliably extract the key from stdout.
    script = f"""\
k = {generate_call}
env.cr.commit()
print('VODOO_API_KEY=' + k)
"""

    container = _odoo_container_name(docker_project)
    print(f"  Creating API key via odoo shell in container {container} …")

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "odoo",
            "shell",
            "-d",
            db_name,
            "--no-http",
            "-c",
            "/etc/odoo/odoo.conf",
            "--stop-after-init",
        ],
        input=script,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[:500]}")
        raise RuntimeError(f"odoo shell failed (rc={result.returncode})")

    # Extract key from stdout
    for line in result.stdout.splitlines():
        if line.startswith("VODOO_API_KEY="):
            key = line.split("=", 1)[1].strip()
            print(f"  API key created: {key[:8]}…")
            return key

    print(f"  STDOUT: {result.stdout[:500]}")
    raise RuntimeError("Could not find API key in odoo shell output")


def _odoo_container_name(docker_project: str) -> str:
    """Discover the running odoo container name for a compose project."""
    result = subprocess.run(
        ["docker", "compose", "-p", docker_project, "ps", "-q", "odoo"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    container_id = result.stdout.strip()
    if not container_id:
        raise RuntimeError(f"No running odoo container found for project {docker_project}")
    return container_id


# ---------------------------------------------------------------------------
# Write env file
# ---------------------------------------------------------------------------


def write_env(
    path: str, url: str, db_name: str, password: str, odoo_major: int, enterprise: bool
) -> None:
    with Path(path).open("w") as fh:
        fh.write(f"ODOO_URL={url}\n")
        fh.write(f"ODOO_DATABASE={db_name}\n")
        fh.write(f"ODOO_USERNAME={ADMIN_LOGIN}\n")
        fh.write(f"ODOO_PASSWORD={password}\n")
        fh.write(f"ODOO_MAJOR_VERSION={odoo_major}\n")
        fh.write(f"ODOO_ENTERPRISE={'1' if enterprise else '0'}\n")
    print(f"Wrote {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Set up Odoo for vodoo integration tests")
    ap.add_argument("--host", default="http://localhost")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument(
        "--version", type=int, required=True, choices=[17, 18, 19], help="Odoo major version"
    )
    ap.add_argument(
        "--project", required=True, help="Docker compose project name (for exec into container)"
    )
    ap.add_argument("--db-name", default=None, help="Database name (default: vodoo_test_<ver>)")
    ap.add_argument("--env-file", default=None, help="Output .env path")
    ap.add_argument(
        "--enterprise",
        action="store_true",
        help="Enterprise edition — install helpdesk, knowledge, timesheet modules",
    )
    args = ap.parse_args()

    suffix = f"{args.version}ee" if args.enterprise else str(args.version)
    db_name = args.db_name or f"vodoo_test_{suffix}"
    env_file = args.env_file or f"tests/integration/.env.test.{suffix}"
    base_url = f"{args.host}:{args.port}"

    wait_for_odoo(base_url)

    if db_exists(base_url, db_name):
        print(f"Database '{db_name}' already exists — reusing.")
    else:
        create_database(base_url, db_name)

    uid = authenticate(base_url, db_name)

    # Community modules (always)
    install_modules(base_url, db_name, uid, ["project", "crm"])

    # Enable project/CRM features (stages, etc.)
    enable_features(base_url, db_name, uid)

    # Enterprise modules (optional)
    if args.enterprise:
        install_modules(base_url, db_name, uid, ["helpdesk", "knowledge", "timesheet_grid"])

    # Create API key via odoo shell inside the container
    print("Creating API key …")
    api_key = create_api_key_via_shell(args.project, db_name, args.version)

    write_env(env_file, base_url, db_name, api_key, args.version, args.enterprise)

    edition = "Enterprise" if args.enterprise else "Community"
    print(f"\n✅  Odoo {args.version} {edition} test environment ready!")
    print(f"    URL      : {base_url}")
    print(f"    Database : {db_name}")
    print(f"    Login    : {ADMIN_LOGIN}")
    print(f"    API Key  : {api_key[:8]}…")


if __name__ == "__main__":
    main()
