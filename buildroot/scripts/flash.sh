#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="$ROOT_DIR/buildroot/output/sdcard.img"

if [ ! -f "$IMAGE" ]; then
    echo "ERROR: No image found at $IMAGE"
    echo "Run ./buildroot/scripts/build.sh first."
    exit 1
fi

# List all external physical disks
DISKS=($(diskutil list external physical 2>/dev/null | grep "^/dev/" | awk '{print $1}'))

if [ ${#DISKS[@]} -eq 0 ]; then
    echo "ERROR: No external disks found. Insert SD card and try again."
    exit 1
fi

echo "External disks:"
echo ""
for i in "${!DISKS[@]}"; do
    INFO=$(diskutil info "${DISKS[$i]}")
    SIZE=$(echo "$INFO" | grep "Disk Size" | awk -F: '{print $2}' | xargs)
    NAME=$(echo "$INFO" | grep "Media Name" | awk -F: '{print $2}' | xargs)
    PROTO=$(echo "$INFO" | grep "Protocol" | awk -F: '{print $2}' | xargs)
    echo "  [$i] ${DISKS[$i]}  $NAME  $SIZE  ($PROTO)"
done
echo ""
read -p "Select disk to flash: " SEL
DISK="${DISKS[$SEL]}"

SIZE=$(diskutil info "$DISK" | grep "Disk Size" | awk -F: '{print $2}' | xargs)
echo ""
echo "WARNING: This will ERASE all data on $DISK ($SIZE)"
echo "Image: $IMAGE ($(du -h "$IMAGE" | cut -f1))"
echo ""
read -p "Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo "==> Unmounting $DISK..."
diskutil unmountDisk "$DISK" || true

RAW_DISK="${DISK/disk/rdisk}"
echo "==> Flashing to $RAW_DISK..."
sudo dd if="$IMAGE" of="$RAW_DISK" bs=1M status=progress
sync

echo "==> Ejecting..."
diskutil eject "$DISK"

echo "==> Done. Insert SD card into ROCK 2F and power on."
