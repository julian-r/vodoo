#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Integration-test runner for vodoo against Odoo 17, 18, and 19.
#
# Usage:
#   ./tests/integration/run.sh                    # all community editions
#   ./tests/integration/run.sh 19                 # community 19 only
#   ./tests/integration/run.sh 17 18              # community 17 + 18
#   uv run python tests/integration/fetch_enterprise.py fetch 19
#   ENTERPRISE=1 ./tests/integration/run.sh 19    # also run enterprise 19
#   ENTERPRISE_BUILD_ONLY=1 ./tests/integration/run.sh 19  # build only
#   KEEP=1 ./tests/integration/run.sh 19          # don't tear down
#
# Environment:
#   ENTERPRISE             – set to 1 to also test enterprise edition
#   ENTERPRISE_ADDONS      – fallback path to an official odoo/enterprise checkout
#   ENTERPRISE_ADDONS_<N>  – version-specific official Git checkout
#   ENTERPRISE_ARCHIVE_DIR – official download directory (default: .odoo-enterprise)
#   ENTERPRISE_ARCHIVE_<N> – version-specific official source archive
#   ENTERPRISE_BUILD_ONLY  – validate source and build local image(s), then exit
#   KEEP                   – set to 1 to keep containers running after tests
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
ENTERPRISE_ADDONS="${ENTERPRISE_ADDONS:-}"
ENTERPRISE_ARCHIVE_DIR="${ENTERPRISE_ARCHIVE_DIR:-$PROJECT_ROOT/.odoo-enterprise}"
ENTERPRISE_BUILD_ONLY="${ENTERPRISE_BUILD_ONLY:-0}"

for v in "${VERSIONS[@]}"; do
  case "$v" in
    17|18|19) ;;
    *)
      echo "❌ Unsupported Odoo version: $v (expected 17, 18, or 19)" >&2
      exit 2
      ;;
  esac
done

# Port mapping: community and enterprise
declare -A CE_PORTS=( [17]=17069 [18]=18069 [19]=19069 )
declare -A EE_PORTS=( [17]=17169 [18]=18169 [19]=19169 )

COMPOSE="docker compose"
FAILED=0
# Track compose projects and temporary exports for cleanup.
PROJECTS=()
STAGING_DIRS=()

cleanup() {
  # Licensed source exports are removed even with KEEP=1 and on early failure.
  for staging in "${STAGING_DIRS[@]}"; do
    rm -rf "$staging"
  done
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
    echo "✅ Odoo ${ver} ${edition}: Python tests passed"
  else
    echo "❌ Odoo ${ver} ${edition}: Python tests FAILED"
    FAILED=1
  fi

  if (cd "$PROJECT_ROOT" && \
      set -a && source "$env_file" && set +a && \
      pnpm --dir packages/typescript test:integration); then
    echo "✅ Odoo ${ver} ${edition}: TypeScript tests passed"
  else
    echo "❌ Odoo ${ver} ${edition}: TypeScript tests FAILED"
    FAILED=1
  fi
}

# ── Build enterprise image if needed ──────────────────────────────────
resolve_enterprise_addons() {
  # Returns an explicitly configured official Git checkout, if any.
  local ver="$1"
  local varname="ENTERPRISE_ADDONS_${ver}"
  if [[ -n "${!varname:-}" ]]; then
    echo "${!varname}"
    return
  fi
  # Convention for worktrees created from one official clone.
  if [[ -d "/tmp/enterprise-${ver}" ]]; then
    echo "/tmp/enterprise-${ver}"
    return
  fi
  echo "$ENTERPRISE_ADDONS"
}

resolve_enterprise_archive() {
  # Returns a version-specific official odoo.com source distribution.
  local ver="$1"
  local varname="ENTERPRISE_ARCHIVE_${ver}"
  if [[ -n "${!varname:-}" ]]; then
    echo "${!varname}"
    return
  fi
  echo "$ENTERPRISE_ARCHIVE_DIR/odoo-${ver}e-source.tar.gz"
}

validate_enterprise_addons() {
  # Print the validated source commit. Diagnostics go to stderr so callers can
  # safely capture the commit hash.
  local ver="$1" addons_path="$2"
  local expected_branch="${ver}.0"

  if [[ -z "$addons_path" || ! -d "$addons_path" ]]; then
    echo "❌ Enterprise addons for Odoo ${ver} were not found." >&2
    echo "   Set ENTERPRISE_ADDONS_${ver}=/path/to/an/official/odoo-enterprise-checkout" >&2
    return 1
  fi
  local inside_work_tree
  if ! inside_work_tree="$(git -C "$addons_path" rev-parse --is-inside-work-tree 2>/dev/null)" \
    || [[ "$inside_work_tree" != "true" ]]; then
    echo "❌ $addons_path is not a Git work tree." >&2
    echo "   Clone the official private repository with: gh repo clone odoo/enterprise ..." >&2
    return 1
  fi

  local origin_url
  origin_url="$(git -C "$addons_path" remote get-url origin 2>/dev/null || true)"
  case "$origin_url" in
    https://github.com/odoo/enterprise|https://github.com/odoo/enterprise.git|git@github.com:odoo/enterprise.git|ssh://git@github.com/odoo/enterprise.git) ;;
    *)
      echo "❌ Refusing non-official Enterprise source remote: ${origin_url:-<missing>}" >&2
      echo "   Expected the private https://github.com/odoo/enterprise repository." >&2
      return 1
      ;;
  esac

  local status_output
  if ! status_output="$(git -C "$addons_path" status --porcelain --untracked-files=all)"; then
    echo "❌ Could not inspect Enterprise checkout state: $addons_path" >&2
    return 1
  fi
  if [[ -n "$status_output" ]]; then
    echo "❌ Enterprise checkout has local or untracked changes: $addons_path" >&2
    echo "   Use a clean official checkout so private or unrelated files cannot enter the image." >&2
    return 1
  fi

  # Resolve the branch from GitHub now rather than trusting the forgeable local
  # remote-tracking ref. This intentionally fails closed when access/auth is absent.
  local head_commit official_commit remote_line
  head_commit="$(git -C "$addons_path" rev-parse HEAD)"
  if ! remote_line="$(
    git -C "$addons_path" ls-remote --exit-code origin "refs/heads/${expected_branch}" 2>/dev/null
  )"; then
    echo "❌ Could not verify the private official origin/${expected_branch} branch." >&2
    echo "   Check GitHub authentication and your Odoo Enterprise entitlement." >&2
    return 1
  fi
  read -r official_commit _ <<< "$remote_line"
  if [[ -z "$official_commit" ]]; then
    echo "❌ Official origin/${expected_branch} returned no commit." >&2
    return 1
  fi
  if [[ "$head_commit" != "$official_commit" ]]; then
    echo "❌ Checkout HEAD does not match origin/${expected_branch}." >&2
    echo "   HEAD: $head_commit" >&2
    echo "   Official branch: $official_commit" >&2
    return 1
  fi

  printf '%s\n' "$head_commit"
}

build_enterprise_image() {
  local ver="$1"
  local tag="vodoo-odoo-ee:${ver}.0"
  local addons_path archive_path source_kind source_revision source_commit="" staging
  addons_path="$(resolve_enterprise_addons "$ver")"
  archive_path="$(resolve_enterprise_archive "$ver")"

  staging="$(mktemp -d "${TMPDIR:-/tmp}/vodoo-enterprise-${ver}.XXXXXX")"
  STAGING_DIRS+=("$staging")

  if [[ -n "$addons_path" ]]; then
    source_kind="odoo-enterprise-git"
    source_revision="$(validate_enterprise_addons "$ver" "$addons_path")"
    source_commit="$source_revision"
    # Export only tracked files from the validated commit. This deliberately
    # excludes .git, credentials, ignored files, and local/untracked content.
    git -C "$addons_path" archive --format=tar "$source_revision" | tar -xf - -C "$staging"
  elif [[ -f "$archive_path" ]]; then
    source_kind="odoo-download"
    source_revision="$(
      cd "$PROJECT_ROOT" && uv run python tests/integration/fetch_enterprise.py \
        validate "$ver" "$archive_path" --sha-only
    )"
    # A hard link avoids duplicating a large licensed archive before the Docker
    # context is sent. Fall back to a private copy across filesystems.
    if ! ln "$archive_path" "$staging/odoo-enterprise-source.tar.gz" 2>/dev/null; then
      cp "$archive_path" "$staging/odoo-enterprise-source.tar.gz"
    fi
  else
    echo "❌ No validated Odoo ${ver} Enterprise source is available." >&2
    echo "   Fetch it with:" >&2
    echo "   uv run python tests/integration/fetch_enterprise.py fetch ${ver}" >&2
    return 1
  fi

  # Always execute the build recipe. Docker can reuse verified layers, while
  # --pull refreshes the mutable official Community base image.
  echo "🏗️  Building local Enterprise image $tag from ${source_kind} ${source_revision:0:12} …"
  if docker build \
    --pull \
    -f "$SCRIPT_DIR/Dockerfile.enterprise" \
    --build-arg "ODOO_VERSION=${ver}.0" \
    --build-arg "ODOO_ENTERPRISE_SOURCE_KIND=${source_kind}" \
    --build-arg "ODOO_ENTERPRISE_REVISION=${source_revision}" \
    --build-arg "ODOO_ENTERPRISE_COMMIT=${source_commit}" \
    -t "$tag" \
    "$staging"; then
    rm -rf "$staging"
  else
    local status=$?
    rm -rf "$staging"
    return "$status"
  fi
}

# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

# Validate and build private local images without starting Odoo when requested.
if [[ "$ENTERPRISE_BUILD_ONLY" == "1" ]]; then
  for v in "${VERSIONS[@]}"; do
    build_enterprise_image "$v"
  done
  echo "✅ Local Enterprise image build complete. No image was pushed."
  exit 0
fi

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
