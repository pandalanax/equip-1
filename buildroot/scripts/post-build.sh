#!/usr/bin/env bash
# Post-build script run by buildroot after target filesystem is assembled
# but before post-image scripts (genimage). Runs inside the VM.
set -euo pipefail

IMAGES_DIR="${BINARIES_DIR}"
TARGET_DIR="${TARGET_DIR:?}"
BUILD_DIR="${BUILD_DIR:?}"
HOST_DIR="${HOST_DIR:?}"
AIC8800_REPO="${HOME}/aic8800"

apply_patch_once() {
    local repo="$1"
    local patchfile="$2"

    if patch -d "$repo" -p1 -N --dry-run < "$patchfile" >/dev/null 2>&1; then
        patch -d "$repo" -p1 -N < "$patchfile"
    elif patch -d "$repo" -p1 -R --dry-run < "$patchfile" >/dev/null 2>&1; then
        echo "==> AIC patch already applied: $(basename "$patchfile")"
    else
        echo "ERROR: Could not apply AIC patch $(basename "$patchfile")"
        return 1
    fi
}

ensure_aic8800_repo() {
    if [ ! -d "${AIC8800_REPO}/.git" ]; then
        echo "==> Cloning Radxa AIC8800 driver..."
        git clone --depth 1 https://github.com/radxa-pkg/aic8800.git "${AIC8800_REPO}"
    else
        echo "==> Reusing cached AIC8800 driver repo."
    fi

    apply_patch_once "${AIC8800_REPO}" "${AIC8800_REPO}/debian/patches/fix-linux-6.1-build.patch"
    apply_patch_once "${AIC8800_REPO}" "${AIC8800_REPO}/debian/patches/fix-usb-build.patch"
}

build_and_stage_aic8800() {
    local kernel_dir
    local kernel_release
    local driver_dir
    local mod_dest
    local firmware_dest
    local cross_compile

    kernel_dir="$(find "${BUILD_DIR}" -maxdepth 1 -type d -name 'linux-*' ! -name 'linux-headers-*' | head -1)"
    if [ -z "${kernel_dir}" ]; then
        echo "ERROR: Could not find built kernel tree under ${BUILD_DIR}"
        return 1
    fi
    if [ ! -f "${kernel_dir}/include/config/auto.conf" ]; then
        echo "ERROR: Kernel tree ${kernel_dir} is missing include/config/auto.conf"
        return 1
    fi

    driver_dir="${AIC8800_REPO}/src/USB/driver_fw/drivers/aic8800"
    cross_compile="${HOST_DIR}/bin/aarch64-buildroot-linux-gnu-"

    echo "==> Building AIC8800 USB WiFi modules..."
    make -C "${driver_dir}" \
        KDIR="${kernel_dir}" \
        ARCH=arm64 \
        CROSS_COMPILE="${cross_compile}" \
        CONFIG_PLATFORM_UBUNTU=y \
        CONFIG_PLATFORM_ROCKCHIP=n \
        modules

    kernel_release="$(make -s -C "${kernel_dir}" kernelrelease)"
    mod_dest="${TARGET_DIR}/lib/modules/${kernel_release}/kernel/drivers/net/wireless/aic8800"
    firmware_dest="${TARGET_DIR}/lib/firmware/aic8800_fw/USB"

    mkdir -p "${mod_dest}" "${firmware_dest}"
    install -m 0644 \
        "${driver_dir}/aic_load_fw/aic_load_fw.ko" \
        "${driver_dir}/aic8800_fdrv/aic8800_fdrv.ko" \
        "${mod_dest}/"
    cp -a "${AIC8800_REPO}/src/USB/driver_fw/fw/aic8800/." "${firmware_dest}/"
    cp -a "${AIC8800_REPO}/src/USB/driver_fw/fw/aic8800D80/." "${firmware_dest}/"

    echo "==> Staged AIC8800 modules into ${mod_dest}"
    echo "==> Staged AIC8800 firmware into ${firmware_dest}"
}

# Copy u-boot-rockchip.bin to images/ (buildroot only installs u-boot.bin by default)
UBOOT_ROCKCHIP=$(find "${BUILD_DIR}" -maxdepth 2 -name "u-boot-rockchip.bin" -path "*/uboot-*" 2>/dev/null | head -1)
if [ -n "$UBOOT_ROCKCHIP" ] && [ -s "$UBOOT_ROCKCHIP" ]; then
    cp "$UBOOT_ROCKCHIP" "$IMAGES_DIR/u-boot-rockchip.bin"
    echo "==> Copied u-boot-rockchip.bin to images/"
else
    echo "WARNING: u-boot-rockchip.bin not found or empty in build dir"
fi

ensure_aic8800_repo
build_and_stage_aic8800
