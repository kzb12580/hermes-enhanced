#!/bin/bash
# Hermes Enhanced Skills Installer
# Usage: bash install-skills.sh [core|key|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${HOME}/.hermes/skills"
TARGET="${1:-all}"

install_category() {
    local category="$1"
    local src_dir="${SCRIPT_DIR}/${category}"
    local count=0

    if [ ! -d "$src_dir" ]; then
        echo "❌ Directory not found: $src_dir"
        return 1
    fi

    for f in "$src_dir"/*.md; do
        [ -f "$f" ] || continue
        local name=$(basename "$f" .md)
        mkdir -p "${SKILLS_DIR}/${name}"
        cp "$f" "${SKILLS_DIR}/${name}/SKILL.md"
        count=$((count + 1))
    done
    echo "✅ ${category}: ${count} skills installed"
}

case "$TARGET" in
    core)
        install_category "core"
        ;;
    key)
        install_category "key"
        ;;
    all)
        install_category "core"
        install_category "key"
        ;;
    *)
        echo "Usage: $0 [core|key|all]"
        exit 1
        ;;
esac

echo "🎉 Done! Skills installed to ${SKILLS_DIR}"
