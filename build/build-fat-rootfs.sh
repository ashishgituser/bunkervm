#!/bin/bash
# ============================================================
# BunkerVM — Build FAT rootfs for Firecracker MicroVM
# ============================================================
# Extends the base sandbox rootfs with common data-science
# and web packages pre-installed so agents can use them
# immediately without pip install delays inside the VM.
#
# Included extras:
#   numpy, pandas, matplotlib, scikit-learn,
#   requests, flask, httpx, beautifulsoup4, lxml,
#   pyyaml, pillow, sympy, scipy
#
# Output: build/rootfs-fat.ext4  (~900MB)
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

WIN_PROJECT_DIR="$PROJECT_DIR"

ROOTFS_IMG="$WIN_PROJECT_DIR/build/rootfs-fat.ext4"
ROOTFS_SIZE_MB=1024
MOUNT_DIR="/tmp/bunkervm-rootfs-mount"
ALPINE_MIRROR="http://dl-cdn.alpinelinux.org/alpine/v3.21"
ALPINE_MINIROOTFS="$ALPINE_MIRROR/releases/x86_64/alpine-minirootfs-3.21.3-x86_64.tar.gz"

echo "============================================"
echo " BunkerVM Fat Rootfs Builder"
echo "============================================"
echo " Mode: Sandbox (MCP server backend)"
echo " Size: ${ROOTFS_SIZE_MB}MB (with data-science packages)"
echo ""

# ── Verify prerequisites ──
echo "[1/7] Checking prerequisites..."

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
echo "[2/7] Creating ext4 image (${ROOTFS_SIZE_MB}MB)..."
rm -f "$ROOTFS_IMG"
dd if=/dev/zero of="$ROOTFS_IMG" bs=1M count=$ROOTFS_SIZE_MB status=progress
mkfs.ext4 -F -L bunkervm-root "$ROOTFS_IMG"

# ── Mount image ──
echo ""
echo "[3/7] Mounting image..."
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
echo "[4/7] Installing Alpine Linux base..."
cd /tmp
if [ ! -f /tmp/alpine-minirootfs.tar.gz ]; then
    wget -q --show-progress -O /tmp/alpine-minirootfs.tar.gz "$ALPINE_MINIROOTFS"
fi
sudo tar xzf /tmp/alpine-minirootfs.tar.gz -C "$MOUNT_DIR"

# Configure Alpine
sudo cp /etc/resolv.conf "$MOUNT_DIR/etc/resolv.conf" 2>/dev/null || \
    echo "nameserver 8.8.8.8" | sudo tee "$MOUNT_DIR/etc/resolv.conf" > /dev/null

# ── Install system packages ──
echo ""
echo "[5/7] Installing system packages..."

echo "$ALPINE_MIRROR/main" | sudo tee "$MOUNT_DIR/etc/apk/repositories" > /dev/null
echo "$ALPINE_MIRROR/community" | sudo tee -a "$MOUNT_DIR/etc/apk/repositories" > /dev/null

sudo chroot "$MOUNT_DIR" /bin/sh -c "
    apk update --quiet
    apk add --quiet --no-cache \
        python3 \
        python3-dev \
        py3-pip \
        py3-numpy \
        py3-pandas \
        py3-matplotlib \
        py3-scipy \
        py3-scikit-learn \
        py3-pillow \
        py3-lxml \
        py3-yaml \
        py3-requests \
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
        bash \
        gcc \
        musl-dev
"
echo "  ✓ System packages installed"

# ── Install pip packages not available via apk ──
echo ""
echo "[6/7] Installing Python packages via pip..."

sudo chroot "$MOUNT_DIR" /bin/sh -c "
    pip3 install --break-system-packages --no-cache-dir \
        httpx \
        beautifulsoup4 \
        flask \
        sympy \
        pyyaml
"
echo "  ✓ Python packages installed"

# ── Install BunkerVM agent ──
echo ""
echo "[7/7] Installing BunkerVM sandbox agent..."

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
echo "bunkervm-fat" | sudo tee "$MOUNT_DIR/etc/hostname" > /dev/null

echo "  ✓ Agent installed"

# ── Summary ──
echo ""
echo "============================================"
echo " Fat rootfs built successfully!"
echo "============================================"
echo ""
echo "  Image:  $ROOTFS_IMG"
ls -lh "$ROOTFS_IMG"
echo ""
echo "  Pre-installed Python packages:"
echo "    numpy, pandas, matplotlib, scipy, scikit-learn"
echo "    requests, httpx, flask, beautifulsoup4, lxml"
echo "    pillow, pyyaml, sympy"
echo ""
echo "  Contents:"
sudo du -sh "$MOUNT_DIR"/* 2>/dev/null | head -20 || true
echo ""
echo "  Usage:"
echo "    # Use fat rootfs instead of default:"
echo "    BUNKERVM_ROOTFS=build/rootfs-fat.ext4 python -m bunkervm"
echo "    # Or in bunkervm.toml:"
echo "    # rootfs = \"build/rootfs-fat.ext4\""
