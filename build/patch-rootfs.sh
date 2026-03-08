#!/bin/bash
# Quick-patch: update init + agent files in rootfs without full rebuild
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$SCRIPT_DIR")"
ROOTFS="$PROJECT/build/rootfs.ext4"
MNT="/tmp/bunkervm-fix"

umount "$MNT" 2>/dev/null || true
mkdir -p "$MNT"
mount -o loop "$ROOTFS" "$MNT"

echo "Patching rootfs..."

# Update init
cp "$PROJECT/rootfs/init" "$MNT/init"
sed -i 's/\r$//' "$MNT/init"
chmod +x "$MNT/init"
echo "  ✓ /init"

# Ensure /bunkervm and /etc/bunkervm directories exist
mkdir -p "$MNT/bunkervm"
mkdir -p "$MNT/etc/bunkervm"

# Force sandbox mode (MCP server mode — no model needed)
echo "sandbox" > "$MNT/etc/bunkervm/mode"
echo "  ✓ /etc/bunkervm/mode = sandbox"

# Update agent files (standalone + sandbox)
for f in orchestrator.py tools.py system_prompt.txt exec_agent.py; do
    if [ -f "$PROJECT/rootfs/bunkervm/$f" ]; then
        cp "$PROJECT/rootfs/bunkervm/$f" "$MNT/bunkervm/$f"
        sed -i 's/\r$//' "$MNT/bunkervm/$f"
        chmod +x "$MNT/bunkervm/$f"
        echo "  ✓ /bunkervm/$f"
    fi
done

# Ensure wget is available (used by init health check)
chroot "$MNT" /bin/sh -c "which wget >/dev/null 2>&1 || apk add --no-cache wget" 2>/dev/null || true

umount "$MNT"
echo "Done. Rootfs patched."
