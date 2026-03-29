## Buildroot Setup

This project builds a bootable image for the Radxa ROCK 2F using Buildroot.

### Local dependencies

You need a few tools on the macOS host:

- `tart`
- `ssh`
- `rsync`
- `scp`
- `dtc`
- `minicom` or another serial terminal

The VM created by Tart also needs:

- a Linux userspace with common build tools
- Buildroot checked out in `~/buildroot`
- `rkbin` checked out in `~/rkbin`

The helper scripts in [`buildroot/scripts/`](/Users/pandalanax/Documents/projects/equip-1/buildroot/scripts) assume that layout.

### What Tart is for

[`Tart`](https://tart.run/) is used to run a Linux VM on macOS for the actual Buildroot build.

That solves two problems:

- it keeps the Buildroot toolchain and generated artifacts out of the macOS host
- it gives the build a stable Linux environment, which is what Buildroot expects

In practice the flow is:

1. the host copies overlay files and configs into the VM
2. the VM runs Buildroot and produces `sdcard.img`
3. the finished image is copied back to `buildroot/output/` on the host

### Main scripts

- [`buildroot/scripts/build.sh`](/Users/pandalanax/Documents/projects/equip-1/buildroot/scripts/build.sh): sync files to the VM, run the build, copy the image back
- [`buildroot/scripts/flash.sh`](/Users/pandalanax/Documents/projects/equip-1/buildroot/scripts/flash.sh): flash the generated image to removable media
- [`buildroot/scripts/vm-setup.sh`](/Users/pandalanax/Documents/projects/equip-1/buildroot/scripts/vm-setup.sh): prepare the Tart VM
- [`buildroot/scripts/vm-ssh.sh`](/Users/pandalanax/Documents/projects/equip-1/buildroot/scripts/vm-ssh.sh): open an SSH shell into the builder VM

### Logs and outputs

- build log: `buildroot/build.log`
- serial logs: `buildroot/logs/`
- generated image: `buildroot/output/sdcard.img`

### Serial console

To watch the board over serial with `minicom`:

```bash
minicom -D /dev/cu.usbserial-A5069RR4 -b 1500000
```

To log the serial session to a file on macOS:

```bash
mkdir -p buildroot/logs
script -q buildroot/logs/minicom-$(date +%Y%m%d-%H%M%S).log \
  minicom -D /dev/cu.usbserial-A5069RR4 -b 1500000
```

Inside `minicom`, `Ctrl-A` then `N` toggles timestamp modes, which is useful for boot timing.
