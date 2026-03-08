#!/bin/bash
# ============================================================
# BunkerVM — Build SANDBOX rootfs for Firecracker MicroVM
# ============================================================
# Creates a lightweight Alpine Linux rootfs for MCP sandbox mode.
# NO model, NO llama-server — just Python + exec_agent.py.
#
# This is ~80% smaller than the full rootfs:
#   Full:    1200MB (includes 469MB model + 13MB llama-server)
#   Sandbox:  512MB (just Alpine + Python + tools)
#
# Output: build/rootfs.ext4
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Use project dir directly (works in WSL and native Linux)
WIN_PROJECT_DIR="$PROJECT_DIR"

ROOTFS_IMG="$WIN_PROJECT_DIR/build/rootfs.ext4"
ROOTFS_SIZE_MB=512
MOUNT_DIR="/tmp/bunkervm-rootfs-mount"
ALPINE_MIRROR="http://dl-cdn.alpinelinux.org/alpine/v3.21"
ALPINE_MINIROOTFS="$ALPINE_MIRROR/releases/x86_64/alpine-minirootfs-3.21.3-x86_64.tar.gz"

echo "============================================"
echo " BunkerVM Sandbox Rootfs Builder"
echo "============================================"
echo " Mode: Sandbox (MCP server backend)"
echo " Size: ${ROOTFS_SIZE_MB}MB (no model, no LLM)"
echo ""

# ── Verify prerequisites ──
echo "[1/6] Checking prerequisites..."

EXEC_AGENT="$WIN_PROJECT_DIR/rootfs/bunkervm/exec_agent.py"
INIT_SCRIPT="$WIN_PROJECT_DIR/rootfs/init"

for f in "$EXEC_AGENT" "$INIT_SCRIPT"; do
    if [ ! -f "$f" ]; then
        echo "  ERROR: Missing $f"
        exit 1
    fi
    echo "  ✓ $(basename $f)"
done

# ── Create ext4 image ──
echo ""
echo "[2/6] Creating ext4 image (${ROOTFS_SIZE_MB}MB)..."
rm -f "$ROOTFS_IMG"
dd if=/dev/zero of="$ROOTFS_IMG" bs=1M count=$ROOTFS_SIZE_MB status=progress
mkfs.ext4 -F -L bunkervm-root "$ROOTFS_IMG"

# ── Mount image ──
echo ""
echo "[3/6] Mounting image..."
sudo mkdir -p "$MOUNT_DIR"
sudo mount -o loop "$ROOTFS_IMG" "$MOUNT_DIR"

cleanup() {
    echo ""
    echo "[CLEANUP] Unmounting..."
    sudo umount "$MOUNT_DIR" 2>/dev/null || true
    sudo rmdir "$MOUNT_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# ── Install Alpine minirootfs ──
echo ""
echo "[4/6] Installing Alpine Linux base..."
cd /tmp
if [ ! -f /tmp/alpine-minirootfs.tar.gz ]; then
    wget -q --show-progress -O /tmp/alpine-minirootfs.tar.gz "$ALPINE_MINIROOTFS"
fi
sudo tar xzf /tmp/alpine-minirootfs.tar.gz -C "$MOUNT_DIR"

# Configure Alpine
sudo cp /etc/resolv.conf "$MOUNT_DIR/etc/resolv.conf" 2>/dev/null || \
    echo "nameserver 8.8.8.8" | sudo tee "$MOUNT_DIR/etc/resolv.conf" > /dev/null

# ── Install packages ──
echo ""
echo "[5/6] Installing packages..."

echo "$ALPINE_MIRROR/main" | sudo tee "$MOUNT_DIR/etc/apk/repositories" > /dev/null
echo "$ALPINE_MIRROR/community" | sudo tee -a "$MOUNT_DIR/etc/apk/repositories" > /dev/null

sudo chroot "$MOUNT_DIR" /bin/sh -c "
    apk update --quiet
    apk add --quiet --no-cache \
        python3 \
        py3-pip \
        iproute2 \
        procps \
        coreutils \
        util-linux \
        ca-certificates \
        curl \
        wget \
        git \
        jq \
        tar \
        gzip \
        openssh-client \
        bash
"
echo "  ✓ Packages installed"

# ── Install BunkerVM agent ──
echo ""
echo "[6/6] Installing BunkerVM sandbox agent..."

# Create directories
sudo mkdir -p "$MOUNT_DIR/bunkervm"
sudo mkdir -p "$MOUNT_DIR/var/log"
sudo mkdir -p "$MOUNT_DIR/root"
sudo mkdir -p "$MOUNT_DIR/etc/bunkervm"

# Copy exec agent
sudo cp "$WIN_PROJECT_DIR/rootfs/bunkervm/exec_agent.py" "$MOUNT_DIR/bunkervm/"
sudo sed -i 's/\r$//' "$MOUNT_DIR/bunkervm/exec_agent.py"
sudo chmod +x "$MOUNT_DIR/bunkervm/exec_agent.py"

# Copy init
sudo cp "$WIN_PROJECT_DIR/rootfs/init" "$MOUNT_DIR/init"
sudo sed -i 's/\r$//' "$MOUNT_DIR/init"
sudo chmod +x "$MOUNT_DIR/init"

# Also copy standalone mode files (init auto-detects)
for f in orchestrator.py tools.py system_prompt.txt; do
    if [ -f "$WIN_PROJECT_DIR/rootfs/bunkervm/$f" ]; then
        sudo cp "$WIN_PROJECT_DIR/rootfs/bunkervm/$f" "$MOUNT_DIR/bunkervm/"
        sudo sed -i 's/\r$//' "$MOUNT_DIR/bunkervm/$f"
    fi
done

# Set sandbox mode
echo "sandbox" | sudo tee "$MOUNT_DIR/etc/bunkervm/mode" > /dev/null

# Set hostname
echo "bunkervm-sandbox" | sudo tee "$MOUNT_DIR/etc/hostname" > /dev/null

echo "  ✓ Agent installed"

# ── Summary ──
echo ""
echo "============================================"
echo " Sandbox rootfs built successfully!"
echo "============================================"
echo ""
echo "  Image:  $ROOTFS_IMG"
ls -lh "$ROOTFS_IMG"
echo ""
echo "  Contents:"
sudo du -sh "$MOUNT_DIR"/* 2>/dev/null | head -15 || true
echo ""
echo "  This rootfs is for MCP sandbox mode only."
echo "  Boot time: ~2-3 seconds (no model to load)"
echo ""
echo "  Next steps:"
echo "    1. sudo bash scripts/setup-network.sh"
echo "    2. pip install -e ."
echo "    3. python -m bunkervm"
