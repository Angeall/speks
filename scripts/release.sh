#!/usr/bin/env bash
# Release pyspeks to PyPI.
#
# Usage:
#   scripts/release.sh <version> [--test] [--skip-tests] [--dry-run]
#
# Examples:
#   scripts/release.sh 0.2.0              # release to PyPI
#   scripts/release.sh 0.2.0 --test       # release to TestPyPI
#   scripts/release.sh 0.2.0 --dry-run    # everything except git tag/push and upload
#
# Credentials: configure ~/.pypirc or set TWINE_USERNAME / TWINE_PASSWORD
# (use __token__ as username and your PyPI API token as password).

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
c_yel()   { printf '\033[33m%s\033[0m\n' "$*"; }

step()   { c_blue ">>> $*"; }
die()    { c_red "ERROR: $*" >&2; exit 1; }

confirm() {
    local prompt="${1:-Continue?}"
    read -r -p "$prompt [y/N] " ans
    case "$ans" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

VERSION=""
USE_TEST=0
SKIP_TESTS=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --test)        USE_TEST=1 ;;
        --skip-tests)  SKIP_TESTS=1 ;;
        --dry-run)     DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,13p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        -*)            die "unknown flag: $1" ;;
        *)
            if [[ -n "$VERSION" ]]; then
                die "multiple versions given: $VERSION and $1"
            fi
            VERSION="$1"
            ;;
    esac
    shift
done

[[ -n "$VERSION" ]] || die "version is required. Usage: $0 <version> [--test] [--skip-tests] [--dry-run]"

# Validate semver-ish: X.Y.Z optionally followed by a pre-release tag.
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.+-]+)?$ ]]; then
    die "invalid version: '$VERSION' (expected MAJOR.MINOR.PATCH[-pre])"
fi

# ---------------------------------------------------------------------------
# Locate project root and key files
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PYPROJECT="$ROOT/pyproject.toml"
INIT_FILE="$ROOT/speks/__init__.py"

[[ -f "$PYPROJECT" ]] || die "pyproject.toml not found at $PYPROJECT"
[[ -f "$INIT_FILE" ]] || die "speks/__init__.py not found at $INIT_FILE"

# ---------------------------------------------------------------------------
# Preflight: clean tree, on main, latest pulled
# ---------------------------------------------------------------------------

step "Preflight checks"

if [[ -n "$(git status --porcelain)" ]]; then
    die "working tree is dirty. Commit or stash before releasing."
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    c_yel "WARNING: you are on branch '$CURRENT_BRANCH', not 'main'."
    confirm "Continue anyway?" || exit 1
fi

step "Fetching origin"
git fetch origin --tags

if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
    die "tag v$VERSION already exists locally."
fi
if git ls-remote --exit-code --tags origin "refs/tags/v$VERSION" >/dev/null 2>&1; then
    die "tag v$VERSION already exists on origin."
fi

# ---------------------------------------------------------------------------
# Tests + type checks
# ---------------------------------------------------------------------------

if [[ "$SKIP_TESTS" -eq 0 ]]; then
    step "Running mypy"
    python -m mypy speks/ || die "mypy failed"

    step "Running unit tests (excluding e2e)"
    python -m pytest tests/ -q || die "tests failed"
else
    c_yel "Skipping tests (--skip-tests)"
fi

# ---------------------------------------------------------------------------
# Bump version in pyproject.toml + __init__.py
# ---------------------------------------------------------------------------

step "Bumping version to $VERSION"

# Portable sed: write to a .bak then delete.
sed -i.bak -E "s/^version = \"[^\"]+\"/version = \"$VERSION\"/" "$PYPROJECT"
sed -i.bak -E "s/^__version__ = \"[^\"]+\"/__version__ = \"$VERSION\"/" "$INIT_FILE"
rm -f "$PYPROJECT.bak" "$INIT_FILE.bak"

# Verify the substitution actually happened.
grep -q "^version = \"$VERSION\"" "$PYPROJECT" \
    || die "version bump in pyproject.toml failed"
grep -q "^__version__ = \"$VERSION\"" "$INIT_FILE" \
    || die "version bump in speks/__init__.py failed"

c_green "Version bumped. Diff:"
git --no-pager diff -- "$PYPROJECT" "$INIT_FILE"

confirm "Commit and tag this change?" || die "aborted by user"

# ---------------------------------------------------------------------------
# Commit + tag
# ---------------------------------------------------------------------------

step "Committing"
git add "$PYPROJECT" "$INIT_FILE"
git commit -m "release: v$VERSION"

step "Tagging v$VERSION"
git tag -a "v$VERSION" -m "Release v$VERSION"

# ---------------------------------------------------------------------------
# Build sdist + wheel
# ---------------------------------------------------------------------------

step "Cleaning build artefacts"
rm -rf dist/ build/ *.egg-info

step "Ensuring build + twine are installed"
python -m pip install --upgrade build twine >/dev/null

step "Building sdist + wheel"
python -m build

step "Validating distributions"
python -m twine check dist/*

c_green "Distributions ready:"
ls -lh dist/

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" -eq 1 ]]; then
    c_yel "--dry-run: skipping upload and git push."
    c_yel "Tag v$VERSION was created locally. Drop it with:"
    c_yel "    git tag -d v$VERSION && git reset --hard HEAD^"
    exit 0
fi

if [[ "$USE_TEST" -eq 1 ]]; then
    REPO_NAME="TestPyPI"
    UPLOAD_ARGS=(--repository testpypi)
else
    REPO_NAME="PyPI"
    UPLOAD_ARGS=()
fi

c_yel "About to upload to $REPO_NAME."
confirm "Proceed with upload?" || die "aborted by user before upload"

step "Uploading to $REPO_NAME"
python -m twine upload "${UPLOAD_ARGS[@]}" dist/*

# ---------------------------------------------------------------------------
# Push commit + tag
# ---------------------------------------------------------------------------

confirm "Push commit and tag to origin?" || {
    c_yel "Upload succeeded but commit/tag not pushed. Run when ready:"
    c_yel "    git push origin $CURRENT_BRANCH --follow-tags"
    exit 0
}

step "Pushing"
git push origin "$CURRENT_BRANCH" --follow-tags

c_green "Done. v$VERSION released to $REPO_NAME."
