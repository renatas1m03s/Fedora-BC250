# bc250-gfxclk-fix

Corrects GPU frequency reporting on the AMD BC-250 (Cyan Skillfish /
gfx1013) board when all 8 physical CPU cores are enabled, on Bazzite /
SteamOS-style image-based (immutable) distros where rebuilding
`amdgpu.ko` isn't practical.

This is a small, standalone, userspace-only fix. It does **not** require
a kernel module, a kernel rebuild, or root-owned writes anywhere under
`/usr`. It fixes GPU clock reporting only -- nothing else.

## The bug

BC-250's SMU firmware reports GPU (and CPU) telemetry through one shared
metrics table. The table has two layouts, chosen by the firmware itself
based on how many physical CPU cores it detects:

- **6-core (stock) layout**: `GfxclkFrequency` sits at a fixed byte
  offset (`0x44`) in the table.
- **8-core ("hybrid") layout**: that same offset (`0x44`) now holds
  `C0Residency[6]` instead -- a 0-100 residency percentage, a completely
  different number. `GfxclkFrequency` is no longer at any fixed table
  offset; it must be queried from the SMU firmware with a dedicated
  mailbox message instead.

The upstream (unpatched) `cyan_skillfish_ppt.c` amdgpu driver was written
before the hybrid layout existed, so on an 8-core BC-250 it keeps reading
the old fixed offset and reports the residency percentage as if it were a
clock frequency. This is why GPU frequency shows up as a small, noisy,
wrong number (bouncing around 1-100) in `gpu_metrics`, `amdgpu_pm_info`,
and the standard `hwmon` `freq1_input` file that GPU-monitoring tools
(MangoHud, radeontop, btop, etc.) already read -- the GPU itself runs at
the correct clock the entire time, only the *reporting* is wrong.

Fixing this properly requires a kernel patch to `cyan_skillfish_ppt.c`
and a rebuilt `amdgpu.ko`. This package reaches the same visible result
without touching `amdgpu.ko` or requiring a kernel/image rebuild --
useful specifically for image-based distros where a patched module can't
be made to persist without rebuilding the whole OS image.

## How it works

1. Reads the real GPU clock straight from SMU firmware via mailbox
   message `GetGfxFrequency` (`PPSMC_MSG_GetGfxFrequency` = `0x37`),
   which is unaffected by the offset bug.
2. Bind-mounts a corrected, writable copy over the standard `hwmon`
   `freq1_input` file that GPU-monitoring tools already read.
3. Runs continuously (not a one-shot fix): every `--interval` seconds
   (default 1.0s) it re-reads the real clock and rewrites the overlay
   file with the fresh value. Stopping the service tears the bind mount
   down immediately and the original (uncorrected) file reappears --
   there is no lingering/stale state, and nothing is left half-patched.

`GetGfxFrequency` only exists on SMU mailbox **queue 0** -- confirmed
against [filippor/cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor)'s
own `queue0.rs`. This script only ever *reads* on that queue -- it never
sends a SET/FORCE message. On `REJECTED_BUSY` or a timeout it retries a
few times with a short backoff instead of treating one failed read as
fatal, and the result is sanity-clamped to a plausible clock range before
being trusted. If the mailbox stays uncooperative, it falls back to
`gpu_metrics`'s `average_gfxclk_frequency` field, which stays in the
uncorrupted 6-wide table layout even in hybrid mode and needs no mailbox
access at all.

## Overhead

Each cycle is one small MMIO mailbox transaction (a handful of 32-bit
reads/writes over BAR5, polled until the firmware responds) plus a write
to a tmpfs file -- no disk I/O, no polling loop faster than
`--interval`. Measured on real hardware after 52 minutes of continuous
run (`systemctl show bc250-gfxclk-fix.service`):

```
CPU time:  787ms total over 52 minutes  (~0.025% average CPU)
Memory:    9.7 MB RSS (peak 10.6 MB)
```

At the default 1-second interval this is not something you'll notice
against any workload. If you want it even lighter, `--interval` accepts
any value (e.g. `--interval 2.0`); the tradeoff is just a coarser update
rate for monitoring tools.

## Installation

```bash
sudo ./install.sh
```

Installs `/usr/local/bin/bc250_gfxclk_fix.py` and
`bc250-gfxclk-fix.service`, then enables and starts it. Nothing here
needs rebuilding after a kernel update -- it's plain Python, no kernel
module involved.

## Verifying it worked

```bash
systemctl status bc250-gfxclk-fix.service

for d in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$d/name")" = "amdgpu" ] && cat "$d/freq1_input"
done
```

The printed value is in Hz; it should track real GPU load (rising under
load, dropping at idle) instead of bouncing around a small 0-100-ish
number.

## Uninstalling

```bash
sudo ./uninstall.sh
```

## Tested against

Linux `7.1.3-ogc5.1.fc44.x86_64` (Bazzite 44, stock unpatched amdgpu
driver).
