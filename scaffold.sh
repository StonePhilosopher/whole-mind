#!/bin/bash
# scaffold.sh — Create a whole-mind workspace from scratch
#
# Usage: bash scaffold.sh [target_directory]
# Default: current directory
#
# This creates the directory structure and starter files for a whole-mind
# memory architecture. Every file is a template — edit them, make them yours.
# The scaffold is the seed, not the crystal.

set -e

TARGET="${1:-.}"

# Colors (if terminal supports them)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}🧠 The Whole Mind — Workspace Scaffold${NC}"
echo "Creating workspace in: $TARGET"
echo ""

# Create directory structure
mkdir -p "$TARGET/memory"
mkdir -p "$TARGET/memory/crystals"
mkdir -p "$TARGET/memory/tidal"
mkdir -p "$TARGET/memory/people"
mkdir -p "$TARGET/memory/shelf"

# Find the templates directory (relative to this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "Error: templates/ directory not found at $TEMPLATE_DIR"
    echo "Make sure scaffold.sh is in the whole-mind repo root."
    exit 1
fi

# Copy templates (don't overwrite existing files)
copy_if_missing() {
    local src="$1"
    local dst="$2"
    if [ -f "$dst" ]; then
        echo "  ⏭  $(basename "$dst") already exists — skipping"
    else
        cp "$src" "$dst"
        echo -e "  ${GREEN}✓${NC}  $(basename "$dst")"
    fi
}

echo "Core files:"
copy_if_missing "$TEMPLATE_DIR/SOUL.md" "$TARGET/SOUL.md"
copy_if_missing "$TEMPLATE_DIR/USER.md" "$TARGET/USER.md"
copy_if_missing "$TEMPLATE_DIR/AGENTS.md" "$TARGET/AGENTS.md"
copy_if_missing "$TEMPLATE_DIR/MEMORY.md" "$TARGET/MEMORY.md"
copy_if_missing "$TEMPLATE_DIR/TODO.md" "$TARGET/TODO.md"
copy_if_missing "$TEMPLATE_DIR/HEARTBEAT.md" "$TARGET/HEARTBEAT.md"

echo ""
echo "Memory directories:"
for dir in memory memory/crystals memory/tidal memory/people memory/shelf; do
    echo -e "  ${GREEN}✓${NC}  $dir/"
done

# Create a README in each memory subdirectory
cat > "$TARGET/memory/README.md" << 'EOF'
# memory/

Your daily notes live here: `YYYY-MM-DD.md`

Subdirectories:
- `crystals/` — deep-grown memory structures (rich, expensive to create, rarely loaded)
- `tidal/` — entries between states (too important to dissolve, not yet placed)
- `people/` — notes about people you interact with
- `shelf/` — organized theme files (topics that recur across many days)

Daily notes are short-term memory. They have a one-week consolidation window.
After a week, promote what matters to MEMORY.md or a shelf theme. Let the rest cool.
EOF
echo ""
echo -e "  ${GREEN}✓${NC}  memory/README.md"

cat > "$TARGET/memory/crystals/README.md" << 'EOF'
# crystals/

Deep-grown memories. Created when something is rich enough to deserve full structure.

A crystal has:
- A nucleus (the seed event or insight)
- Growth layers (how understanding developed)
- Faces (connections to other memories)
- A one-line entry in MEMORY.md (the map reference)

Most memories don't become crystals. That's fine. Crystals are rare by nature.
EOF
echo -e "  ${GREEN}✓${NC}  memory/crystals/README.md"

cat > "$TARGET/memory/tidal/README.md" << 'EOF'
# tidal/

The liminal zone. Entries that are too important to dissolve but haven't found
their permanent home yet.

Review this directory during consolidation. Some things need time to decide
what they are. This is the place they sit while deciding.

When an entry finds its home (MEMORY.md, a shelf theme, a crystal), move it
there and remove it from here.
EOF
echo -e "  ${GREEN}✓${NC}  memory/tidal/README.md"

# Copy the example daily note
if [ -f "$TEMPLATE_DIR/daily-note-example.md" ]; then
    copy_if_missing "$TEMPLATE_DIR/daily-note-example.md" "$TARGET/memory/daily-note-example.md"
fi

echo ""
echo -e "${BLUE}Workspace created.${NC}"
echo ""
echo "Next steps:"
echo "  1. Open SOUL.md and write your first honest sentence about who you are"
echo "  2. Open USER.md and fill in what you know about your human"
echo "  3. Open AGENTS.md and adjust the boot sequence to your framework"
echo "  4. Start a conversation. Write your first daily note. The rest follows."
echo ""
echo "Read the full architecture: https://github.com/StonePhilosopher/whole-mind"
echo ""
echo -e "${GREEN}The seed is planted. What grows is yours.${NC}"
echo ""
