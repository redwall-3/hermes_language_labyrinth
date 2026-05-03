#!/usr/bin/env bash
# install.sh — Deploy Hermes Language Labyrinth to ~/.hermes
#
# What this script does:
#   1. Creates ~/.hermes/plugins/labyrinth/ and symlinks tools.py from the repo
#   2. Writes plugin.yaml and __init__.py into the plugin directory
#   3. Installs SKILL.md to ~/.hermes/skills/gaming/language-labyrinth/
#   4. Installs SOUL.md to ~/.hermes/SOUL.md  (backs up any existing file)
#   5. Creates ~/.hermes/labyrinth/ data directory
#   6. Enables the labyrinth plugin in ~/.hermes/config.yaml (via hermes CLI)
#
# Usage:
#   bash install.sh          # normal install
#   bash install.sh --dry-run  # print actions without executing them

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { printf '\033[0;34m[install]\033[0m %s\n' "$*"; }
ok()    { printf '\033[0;32m[  ok  ]\033[0m %s\n' "$*"; }
warn()  { printf '\033[0;33m[ warn ]\033[0m %s\n' "$*"; }
err()   { printf '\033[0;31m[error ]\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if $DRY_RUN; then
    printf '\033[0;90m[dry-run] %s\033[0m\n' "$*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# 0. Sanity checks
# ---------------------------------------------------------------------------

info "Hermes Language Labyrinth — Installer"
echo

if [ ! -d "$HERMES_HOME" ]; then
  err "Hermes home not found at $HERMES_HOME. Is hermes-agent installed?"
fi

if ! command -v hermes &>/dev/null; then
  warn "hermes binary not found in PATH — plugin enable step will be skipped."
  HERMES_BIN=""
else
  HERMES_BIN=$(command -v hermes)
fi

# ---------------------------------------------------------------------------
# 1. Plugin directory
# ---------------------------------------------------------------------------

PLUGIN_DIR="$HERMES_HOME/plugins/labyrinth"
info "Installing plugin to $PLUGIN_DIR"

run mkdir -p "$PLUGIN_DIR"

# Symlink tools.py from the repo so edits are immediately live
TOOLS_SRC="$REPO_DIR/tools/labyrinth_tools.py"
TOOLS_DST="$PLUGIN_DIR/tools.py"
if $DRY_RUN; then
  printf '\033[0;90m[dry-run] ln -sf %s %s\033[0m\n' "$TOOLS_SRC" "$TOOLS_DST"
else
  ln -sf "$TOOLS_SRC" "$TOOLS_DST"
fi

# Copy plugin.yaml and __init__.py from repo
run cp "$REPO_DIR/plugins/labyrinth/plugin.yaml" "$PLUGIN_DIR/plugin.yaml"
run cp "$REPO_DIR/plugins/labyrinth/__init__.py" "$PLUGIN_DIR/__init__.py"

ok "Plugin files installed"

# ---------------------------------------------------------------------------
# 2. Skill
# ---------------------------------------------------------------------------

SKILL_DIR="$HERMES_HOME/skills/gaming/language-labyrinth"
info "Installing skill to $SKILL_DIR"

run mkdir -p "$SKILL_DIR"
run cp "$REPO_DIR/skills/language-labyrinth/SKILL.md" "$SKILL_DIR/SKILL.md"

ok "Skill installed"

# ---------------------------------------------------------------------------
# 3. SOUL.md
# ---------------------------------------------------------------------------

SOUL_DST="$HERMES_HOME/SOUL.md"
SOUL_SRC="$REPO_DIR/config/SOUL.md"

info "Installing SOUL.md to $SOUL_DST"

if [ -f "$SOUL_DST" ] && [ -s "$SOUL_DST" ]; then
  BACKUP="$SOUL_DST.backup.$(date +%Y%m%d_%H%M%S)"
  run cp "$SOUL_DST" "$BACKUP"
  warn "Existing SOUL.md backed up to $BACKUP"
fi

run cp "$SOUL_SRC" "$SOUL_DST"
ok "SOUL.md installed"

# ---------------------------------------------------------------------------
# 4. Data directory
# ---------------------------------------------------------------------------

DATA_DIR="$HERMES_HOME/labyrinth"
info "Creating data directory $DATA_DIR"
run mkdir -p "$DATA_DIR"
ok "Data directory ready"

# ---------------------------------------------------------------------------
# 5. Enable plugin via hermes CLI
# ---------------------------------------------------------------------------

if [ -n "$HERMES_BIN" ] && ! $DRY_RUN; then
  info "Enabling labyrinth plugin in config.yaml..."
  if "$HERMES_BIN" plugins enable labyrinth 2>/dev/null; then
    ok "Plugin enabled via 'hermes plugins enable labyrinth'"
  else
    warn "Could not auto-enable plugin. Add this to ~/.hermes/config.yaml manually:"
    echo ""
    echo "  plugins:"
    echo "    enabled:"
    echo "      - labyrinth"
    echo ""
  fi
elif $DRY_RUN; then
  printf '\033[0;90m[dry-run] hermes plugins enable labyrinth\033[0m\n'
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo
info "Installation complete!"
echo
echo "Next steps:"
echo "  1. Set your API key:  echo 'OPENROUTER_API_KEY=sk-...' >> $HERMES_HOME/.env"
echo "  2. Create a campaign: python $REPO_DIR/main.py create"
echo "  3. Start playing:     python $REPO_DIR/main.py play"
echo
echo "To restrict tools to labyrinth only during a session, launch with:"
echo "  hermes -t labyrinth,skills,memory -s language-labyrinth"
