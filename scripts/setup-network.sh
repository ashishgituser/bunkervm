#!/bin/bash
# ============================================================
# BunkerVM — TAP Network Setup
# ============================================================
# Creates the TAP device for Firecracker VM networking.
# Run ONCE before starting the MCP server (requires sudo).
#
# Usage:
#   sudo bash scripts/setup-network.sh
#   # or with custom settings:
#   sudo TAP=tap0 HOST_IP=172.16.0.1 SUBNET=24 bash scripts/setup-network.sh
#
# The MCP server can also set this up automatically if
# it has passwordless sudo access.
# ============================================================
set -euo pipefail

TAP="${TAP:-tap0}"
HOST_IP="${HOST_IP:-172.16.0.1}"
SUBNET="${SUBNET:-24}"
ENABLE_NAT="${ENABLE_NAT:-true}"

echo "BunkerVM Network Setup"
echo "  TAP device: $TAP"
echo "  Host IP:    $HOST_IP/$SUBNET"
echo ""

# ── Remove existing TAP if present ──
if ip link show "$TAP" &>/dev/null; then
    echo "  Removing existing $TAP..."
    ip link del "$TAP" 2>/dev/null || true
fi

# ── Create TAP device ──
echo "  Creating TAP device..."
ip tuntap add "$TAP" mode tap
ip addr add "${HOST_IP}/${SUBNET}" dev "$TAP"
ip link set "$TAP" up

echo "  ✓ TAP device $TAP is up (${HOST_IP}/${SUBNET})"

# ── Enable IP forwarding ──
echo "  Enabling IP forwarding..."
sysctl -w net.ipv4.ip_forward=1 > /dev/null

# ── NAT masquerade (for internet access in VM) ──
if [ "$ENABLE_NAT" = "true" ]; then
    # Find the default route interface
    DEFAULT_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
    if [ -n "$DEFAULT_IFACE" ]; then
        echo "  Setting up NAT via $DEFAULT_IFACE..."
        iptables -t nat -C POSTROUTING -o "$DEFAULT_IFACE" -s "${HOST_IP}/${SUBNET}" -j MASQUERADE 2>/dev/null \
            || iptables -t nat -A POSTROUTING -o "$DEFAULT_IFACE" -s "${HOST_IP}/${SUBNET}" -j MASQUERADE
        echo "  ✓ NAT enabled (VM can reach the internet)"
    else
        echo "  ⚠ No default route found, skipping NAT"
    fi
fi

echo ""
echo "Network ready. The VM will use:"
echo "  IP:      172.16.0.2/$SUBNET"
echo "  Gateway: $HOST_IP"
echo ""
echo "Start the MCP server with:"
echo "  python -m bunkervm"
