#!/usr/bin/env bash
set -euo pipefail

VM_NAME="equip1-builder"
VM_IMAGE="ghcr.io/cirruslabs/ubuntu:latest"
DISK_SIZE=50  # GB — Buildroot needs ~30GB for sources + build artifacts

# Check if VM already exists
if tart list | grep -q "$VM_NAME"; then
    echo "VM '$VM_NAME' already exists."
    echo "To recreate: tart delete $VM_NAME && ./buildroot/scripts/vm-setup.sh"
    exit 0
fi

echo "==> Cloning base image..."
tart clone "$VM_IMAGE" "$VM_NAME"

echo "==> Resizing disk to ${DISK_SIZE}GB..."
tart set "$VM_NAME" --disk-size "$DISK_SIZE"

echo "==> Setting RAM to 8GB..."
tart set "$VM_NAME" --memory 8192

echo "==> Starting VM (headless)..."
tart run --no-graphics "$VM_NAME" &
VM_PID=$!

echo "==> Waiting for VM to boot..."
sleep 15

# Wait for SSH to become available
VM_IP=""
SSH_OK=false
for i in $(seq 1 60); do
    VM_IP=$(tart ip "$VM_NAME" 2>/dev/null || true)
    if [ -n "$VM_IP" ]; then
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 admin@"$VM_IP" true 2>/dev/null; then
            SSH_OK=true
            break
        fi
    fi
    echo "  waiting for SSH... ($i/60)"
    sleep 5
done

if [ "$SSH_OK" != "true" ]; then
    echo "ERROR: Could not establish SSH to VM (IP: ${VM_IP:-none})."
    kill $VM_PID 2>/dev/null || true
    exit 1
fi

echo "==> VM IP: $VM_IP"
echo "==> Provisioning build dependencies..."

ssh -o StrictHostKeyChecking=no admin@"$VM_IP" bash <<'PROVISION'
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
    build-essential \
    git \
    wget \
    cpio \
    unzip \
    rsync \
    bc \
    libncurses-dev \
    file \
    python3 \
    python3-setuptools \
    python3-dev \
    python3-pip \
    python3-venv \
    which \
    libssl-dev \
    device-tree-compiler \
    bison \
    flex \
    swig \
    dosfstools \
    mtools \
    e2fsprogs \
    u-boot-tools \
    libelf-dev \
    libgnutls28-dev \
    libfdt-dev \
    python3-libfdt

echo "==> Cloning Buildroot..."
if [ -d "$HOME/buildroot" ] && ! git -C "$HOME/buildroot" log --oneline -1 &>/dev/null; then
    echo "  Buildroot checkout is broken, removing..."
    rm -rf "$HOME/buildroot"
fi
if [ ! -d "$HOME/buildroot" ]; then
    git clone --branch 2024.11.x https://gitlab.com/buildroot.org/buildroot.git "$HOME/buildroot"
else
    echo "Buildroot already cloned."
fi

echo "==> Cloning rkbin (Rockchip firmware blobs)..."
if [ ! -d "$HOME/rkbin" ]; then
    git clone --depth 1 https://github.com/rockchip-linux/rkbin.git "$HOME/rkbin"
else
    echo "rkbin already cloned."
fi

echo "==> Provisioning complete."
PROVISION

echo ""
echo "==> VM '$VM_NAME' is ready."
echo "    IP: $VM_IP"
echo "    SSH: ssh admin@$VM_IP"
echo ""
echo "==> Stopping VM. Use './buildroot/scripts/build.sh' to build images."
tart stop "$VM_NAME" 2>/dev/null || true
wait $VM_PID 2>/dev/null || true
