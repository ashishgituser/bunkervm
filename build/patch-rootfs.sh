#!/bin/bash
# Quick-patch: update init + agent files in rootfs without full rebuild
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$SCRIPT_DIR")"
ROOTFS="$PROJECT/build/rootfs.ext4"
MNT="/tmp/nervos-fix"

umount "$MNT" 2>/dev/null || true
mkdir -p "$MNT"
mount -o loop "$ROOTFS" "$MNT"

echo "Patching rootfs..."

# Update init
cp "$PROJECT/rootfs/init" "$MNT/init"
sed -i 's/\r$//' "$MNT/init"
chmod +x "$MNT/init"
echo "  ✓ /init"

# Ensure /nervos and /etc/nervos directories exist
mkdir -p "$MNT/nervos"
mkdir -p "$MNT/etc/nervos"

# Force sandbox mode (MCP server mode — no model needed)
echo "sandbox" > "$MNT/etc/nervos/mode"
echo "  ✓ /etc/nervos/mode = sandbox"

# Update agent files (standalone + sandbox)
for f in orchestrator.py tools.py system_prompt.txt exec_agent.py; do
    if [ -f "$PROJECT/rootfs/nervos/$f" ]; then
        cp "$PROJECT/rootfs/nervos/$f" "$MNT/nervos/$f"
        sed -i 's/\r$//' "$MNT/nervos/$f"
        chmod +x "$MNT/nervos/$f"
        echo "  ✓ /nervos/$f"
    fi
done

# Ensure wget is available (used by init health check)
chroot "$MNT" /bin/sh -c "which wget >/dev/null 2>&1 || apk add --no-cache wget" 2>/dev/null || true

umount "$MNT"
echo "Done. Rootfs patched."
