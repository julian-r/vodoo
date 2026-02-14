#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Integration-test runner for vodoo against Odoo 17, 18, and 19.
#
# Usage:
#   ./tests/integration/run.sh                    # all community editions
#   ./tests/integration/run.sh 19                 # community 19 only
#   ./tests/integration/run.sh 17 18              # community 17 + 18
#   ENTERPRISE=1 ./tests/integration/run.sh 19    # also run enterprise 19
#   KEEP=1 ./tests/integration/run.sh 19          # don't tear down
#
# Environment:
#   ENTERPRISE           – set to 1 to also test enterprise edition
#   ENTERPRISE_ADDONS    – path to enterprise addons dir
#                          (default: ~/src/Julian Rath/odoo/enterprise-addons)
#   KEEP                 – set to 1 to keep containers running after tests
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

# Versions to test
if [[ $# -gt 0 ]]; then
  VERSIONS=("$@")
else
  VERSIONS=(17 18 19)
fi

ENTERPRISE="${ENTERPRISE:-0}"
ENTERPRISE_ADDONS="${ENTERPRISE_ADDONS:-$HOME/src/Julian Rath/odoo/enterprise-addons}"

# Port mapping: community and enterprise
declare -A CE_PORTS=( [17]=17069 [18]=18069 [19]=19069 )
declare -A EE_PORTS=( [17]=17169 [18]=18169 [19]=19169 )

COMPOSE="docker compose"
FAILED=0
# Track all compose projects for cleanup
PROJECTS=()

cleanup() {
  if [[ "${KEEP:-}" == "1" ]]; then
    echo "ℹ️  KEEP=1 — leaving containers running."
    echo "   To tear down:  for p in ${PROJECTS[*]:-}; do docker compose -p \$p down -v; done"
    return
  fi
  for proj in "${PROJECTS[@]}"; do
    echo "🧹 Tearing down $proj …"
    $COMPOSE -p "$proj" -f docker-compose.yml down -v --remove-orphans 2>/dev/null || true
  done
}
trap cleanup EXIT

# ── Helper: start + provision one instance ────────────────────────────
start_instance() {
  local ver="$1" port="$2" proj="$3" image="$4" db="$5" ee_flag="$6"
  local edition="community"
  [[ "$ee_flag" == "1" ]] && edition="enterprise"

  PROJECTS+=("$proj")

  # Use enterprise config (with addons_path) when needed
  local conf="odoo.conf"
  [[ "$ee_flag" == "1" ]] && conf="odoo-enterprise.conf"

  echo ""
  echo "🚀 Starting Odoo ${ver} ${edition} on port ${port} (project: ${proj}) …"
  ODOO_IMAGE="$image" ODOO_PORT="$port" ODOO_CONF="$conf" \
    $COMPOSE -p "$proj" -f docker-compose.yml up -d --wait --wait-timeout 180

  echo "⚙️  Provisioning ${proj} …"
  local ee_arg=""
  [[ "$ee_flag" == "1" ]] && ee_arg="--enterprise"
  (cd "$PROJECT_ROOT" && \
    uv run python tests/integration/setup_odoo.py \
      --port "$port" --version "$ver" --project "$proj" \
      --db-name "$db" $ee_arg)
}

# ── Helper: run tests for one instance ────────────────────────────────
run_tests() {
  local ver="$1" suffix="$2" edition="$3"

  local env_file="$SCRIPT_DIR/.env.test.${suffix}"

  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "  🧪 Running tests — Odoo ${ver} ${edition}"
  echo "════════════════════════════════════════════════════════════════"

  if (cd "$PROJECT_ROOT" && \
      VODOO_TEST_ENV="$env_file" \
      uv run python -m pytest \
        tests/integration/test_suite.py \
        tests/integration/test_async_suite.py \
        -v --tb=short -x \
        --odoo-version "$ver"); then
    echo "✅ Odoo ${ver} ${edition}: all tests passed"
  else
    echo "❌ Odoo ${ver} ${edition}: some tests FAILED"
    FAILED=1
  fi
}

# ── Build enterprise image if needed ──────────────────────────────────
resolve_enterprise_addons() {
  # Returns the addons path for a given version.
  # Checks version-specific overrides first, then the default.
  local ver="$1"
  local varname="ENTERPRISE_ADDONS_${ver}"
  if [[ -n "${!varname:-}" && -d "${!varname}" ]]; then
    echo "${!varname}"
    return
  fi
  # Convention: /tmp/enterprise-<ver> (git worktree checkouts)
  if [[ -d "/tmp/enterprise-${ver}" ]]; then
    echo "/tmp/enterprise-${ver}"
    return
  fi
  # Fall back to default (assumed to match the latest version)
  echo "$ENTERPRISE_ADDONS"
}

build_enterprise_image() {
  local ver="$1"
  local tag="vodoo-odoo-ee:${ver}.0"

  if docker image inspect "$tag" &>/dev/null; then
    echo "ℹ️  Enterprise image $tag already exists, skipping build."
    return
  fi

  local addons_path
  addons_path="$(resolve_enterprise_addons "$ver")"

  if [[ ! -d "$addons_path" ]]; then
    echo "❌ Enterprise addons for Odoo ${ver} not found at $addons_path"
    echo "   Set ENTERPRISE_ADDONS_${ver}=/path/to/enterprise-addons"
    exit 1
  fi

  echo "🏗️  Building enterprise image $tag from $addons_path …"
  docker build \
    -f "$SCRIPT_DIR/Dockerfile.enterprise" \
    --build-arg "ODOO_VERSION=${ver}.0" \
    -t "$tag" \
    "$addons_path"
}

# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

# 1. Start community instances
for v in "${VERSIONS[@]}"; do
  start_instance "$v" "${CE_PORTS[$v]}" "vodoo-test-${v}" "odoo:${v}.0" "vodoo_test_${v}" "0"
done

# 2. Optionally start enterprise instances
if [[ "$ENTERPRISE" == "1" ]]; then
  for v in "${VERSIONS[@]}"; do
    build_enterprise_image "$v"
    start_instance "$v" "${EE_PORTS[$v]}" "vodoo-test-${v}ee" "vodoo-odoo-ee:${v}.0" "vodoo_test_${v}ee" "1"
  done
fi

# 3. Run community tests
for v in "${VERSIONS[@]}"; do
  run_tests "$v" "$v" "community"
done

# 4. Run enterprise tests
if [[ "$ENTERPRISE" == "1" ]]; then
  for v in "${VERSIONS[@]}"; do
    run_tests "$v" "${v}ee" "enterprise"
  done
fi

# 5. Summary
echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "🎉 All integration tests passed!"
else
  echo "💥 Some integration tests failed."
  exit 1
fi
