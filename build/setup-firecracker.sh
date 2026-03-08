#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUNKERVM_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$BUNKERVM_DIR/build"
mkdir -p "$BUILD_DIR"

# ===== Step 1: Install Firecracker =====
echo "===== STEP 1: Firecracker ====="
if command -v firecracker >/dev/null 2>&1; then
    echo "Already installed: $(firecracker --version 2>&1 | head -1)"
else
    cd /tmp
    ARCH="x86_64"
    # Try multiple versions
    for FC_VER in v1.11.0 v1.10.1 v1.9.1; do
        URL="https://github.com/firecracker-microvm/firecracker/releases/download/${FC_VER}/firecracker-${FC_VER}-${ARCH}.tgz"
        echo "Trying $URL ..."
        if curl -sL -o fc.tgz "$URL" && [ -s fc.tgz ]; then
            echo "Downloaded Firecracker $FC_VER"
            tar xzf fc.tgz
            FC_BIN=$(find /tmp -name "firecracker-*" -type f -not -name "*.tgz" | head -1)
            if [ -n "$FC_BIN" ]; then
                sudo cp "$FC_BIN" /usr/local/bin/firecracker
                sudo chmod +x /usr/local/bin/firecracker
                echo "Installed: $(firecracker --version 2>&1 | head -1)"
                break
            fi
        fi
    done
fi

# ===== Step 2: Download Firecracker kernel =====
echo ""
echo "===== STEP 2: Kernel ====="
KERNEL_PATH="$BUILD_DIR/vmlinux"
if [ -f "$KERNEL_PATH" ]; then
    echo "Kernel already exists: $(ls -lh $KERNEL_PATH)"
else
    # Firecracker provides pre-built kernels
    KERNEL_URL="https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux-6.1.102"
    echo "Downloading kernel from $KERNEL_URL ..."
    curl -sL -o "$KERNEL_PATH" "$KERNEL_URL"
    if [ -s "$KERNEL_PATH" ]; then
        echo "Kernel downloaded: $(ls -lh $KERNEL_PATH)"
    else
        echo "S3 download failed, trying alternative..."
        # Build a kernel or use the WSL2 one as fallback
        KERNEL_URL2="https://s3.amazonaws.com/spec.ccfc.min/ci-artifacts/kernels/x86_64/vmlinux-6.1"
        curl -sL -o "$KERNEL_PATH" "$KERNEL_URL2"
        if [ -s "$KERNEL_PATH" ]; then
            echo "Kernel downloaded (alt): $(ls -lh $KERNEL_PATH)"
        else
            echo "WARN: Could not download kernel. Will try to extract from system."
            # Fallback: extract WSL2 kernel
            sudo cp /boot/vmlinuz-$(uname -r) "$KERNEL_PATH" 2>/dev/null || true
        fi
    fi
fi

# ===== Step 3: Set up KVM permissions =====
echo ""
echo "===== STEP 3: KVM ====="
sudo chmod 666 /dev/kvm 2>/dev/null || true
ls -la /dev/kvm

echo ""
echo "===== SETUP COMPLETE ====="
echo "Firecracker: $(which firecracker 2>/dev/null || echo 'NOT FOUND')"
echo "Kernel: $(ls -lh $KERNEL_PATH 2>/dev/null || echo 'NOT FOUND')"
