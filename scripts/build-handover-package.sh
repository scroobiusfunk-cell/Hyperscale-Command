#!/usr/bin/env bash
#
# Build the handover package: one archive an engineer can be handed instead of
# access to this repository.
#
#   scripts/build-handover-package.sh [output-dir]
#
# It contains the documents worth reading loose, so they can be circulated
# without cloning anything, and a git bundle carrying the branch with its full
# history, because the commit messages are where the reasoning behind the
# invariants lives.
#
# The bundle is built with HEAD as well as the branch. Without HEAD a clone
# succeeds, warns "remote HEAD refers to nonexistent ref", and leaves an empty
# working tree, which looks to whoever opens it like an empty project. The
# clone check below exists so that failure can never ship again.
#
# Nothing here is committed: the archive is a build artefact, and it holds a
# copy of the repository, so committing it would nest the repo inside itself.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

OUT_DIR="${1:-${TMPDIR:-/tmp}/understudy-handover}"
NAME="inspection-understudy-handover"
PKG="$OUT_DIR/$NAME"
BUNDLE="$PKG/inspection-understudy.bundle"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
HEAD_SHA="$(git rev-parse HEAD)"
BASE="$(git rev-parse --verify --quiet origin/main || true)"
BRANCH_COMMITS="$( [ -n "$BASE" ] && git rev-list --count "$BASE..HEAD" || git rev-list --count HEAD )"
TOTAL_COMMITS="$(git rev-list --count HEAD)"

if [ -n "$(git status --porcelain)" ]; then
  echo "refusing to build from a dirty tree: the package would not match any commit" >&2
  git status --short >&2
  exit 1
fi

rm -rf "$PKG"
mkdir -p "$PKG/docs"

git bundle create "$BUNDLE" HEAD "$BRANCH" >/dev/null 2>&1

# Prove the bundle before packaging it. A bundle that verifies can still fail to
# check out, so this clones it for real and looks for files that must be there.
CHECK="$(mktemp -d)"
trap 'rm -rf "$CHECK"' EXIT
git clone --quiet "$BUNDLE" "$CHECK/clone"
for required in \
  CLAUDE.md docs/HANDOVER.md docs/ARCHITECTURE.md \
  apps/api/pyproject.toml apps/field/package.json apps/reviewer/package.json \
  packages/schemas/schemas/common/definitions.schema.json \
  infra/docker-compose.yml .github/workflows/ci.yml
do
  if [ ! -f "$CHECK/clone/$required" ]; then
    echo "bundle clones but is missing $required; not packaging" >&2
    exit 1
  fi
done
if [ "$(git -C "$CHECK/clone" rev-parse HEAD)" != "$HEAD_SHA" ]; then
  echo "bundle clones to the wrong commit; not packaging" >&2
  exit 1
fi
if [ -f "$CHECK/clone/.env" ] || [ -n "$(git -C "$CHECK/clone" log --all --format=%H -- .env)" ]; then
  echo "a .env is in the history; not packaging" >&2
  exit 1
fi

cp docs/HANDOVER.md docs/ARCHITECTURE.md docs/OPEN_QUESTIONS.md docs/DEMO.md "$PKG/docs/"
cp docs/rule-registry-review-2026-09-20.md "$PKG/docs/" 2>/dev/null || true
cp -r docs/adr "$PKG/docs/"
cp CLAUDE.md "$PKG/docs/WORKING-RULES.md"
cp docs/handover-package-README.md "$PKG/README.md"

{
  echo "# Manifest"
  echo
  echo "Built:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Branch:   $BRANCH"
  echo "Head:     $HEAD_SHA"
  echo "Commits:  $BRANCH_COMMITS on the branch, $TOTAL_COMMITS including the repository's initial commit"
  echo
  echo "Verified before packaging: the bundle was cloned into an empty directory,"
  echo "landed on the head above, and carries every file the build script checks"
  echo "for. No .env is in the archive and none appears anywhere in the history."
  echo
  echo "## Bundle"
  echo
  ( cd "$PKG" && git bundle verify inspection-understudy.bundle 2>&1 ) | sed 's/^/  /'
  echo
  echo "## Checksums (sha256)"
  echo
  ( cd "$PKG" && find . -type f -not -name MANIFEST -print0 | sort -z | xargs -0 sha256sum | sed 's/^/  /' )
} > "$PKG/MANIFEST"

( cd "$OUT_DIR" && rm -f "$NAME.zip" && zip -qr "$NAME.zip" "$NAME" )

echo "$OUT_DIR/$NAME.zip"
echo "  head    $HEAD_SHA ($BRANCH_COMMITS commits on $BRANCH)"
echo "  size    $(du -h "$OUT_DIR/$NAME.zip" | cut -f1)"
