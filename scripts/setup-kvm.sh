#!/bin/bash
# Setup passwordless sudo for /dev/kvm chmod (one-time)
set -e
USER=$(whoami)
RULE="$USER ALL=(ALL) NOPASSWD: /bin/chmod 666 /dev/kvm"
SUDOERS_FILE="/etc/sudoers.d/bunkervm-kvm"

if [ -f "$SUDOERS_FILE" ]; then
    echo "/dev/kvm sudo rule already configured"
    exit 0
fi

echo "Setting up passwordless /dev/kvm access for user: $USER"
echo "Enter your WSL password if prompted:"
sudo bash -c "echo '$RULE' > $SUDOERS_FILE && chmod 440 $SUDOERS_FILE"
echo "Done. /dev/kvm will be auto-fixed on each engine start."
