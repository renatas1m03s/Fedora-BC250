#!/usr/bin/env python3
"""
bc250-gfxclk-fix — makes third-party monitoring tools (MangoHud, radeontop,
btop, anything reading amdgpu_gpu_metrics/hwmon) display the *correct* GPU
frequency on BC-250, without patching or recompiling the kernel driver.

The problem this fixes
-----------------------
The stock driver's "Current" SMU metrics table has a fixed 116-byte layout.
In the 6-core (stock) layout, byte offset 0x44 holds GfxclkFrequency. When
the firmware detects all 8 physical CPU cores present, it switches to an
8-core layout of that *same* table, and that same offset 0x44 now holds
C0Residency[6] instead -- a completely different number (a 0-100 residency
percentage, not a clock). Any code that blindly reads GfxclkFrequency at the
old offset (including the stock kernel driver's own gpu_metrics/debugfs/hwmon
exposure) ends up displaying that unrelated value as if it were the GPU
clock. The GPU itself runs at the correct frequency the whole time -- only
the *reporting* is wrong. Confirmed live on this exact board: current_gfxclk
via gpu_metrics/debugfs bounces around 1-100 (matches a residency counter),
while metrics.Average.GfxclkFrequency (which stays 6-wide/uncorrupted even
in hybrid mode) reads a plausible ~200-300 MHz idle clock.

How this fixes it, without a kernel patch
------------------------------------------
1. Read the real gfxclk directly from the SMU firmware via mailbox message
   GetGfxFrequency (PPSMC_MSG_GetGfxFrequency = 0x37) -- this bypasses the
   broken table offset entirely, so it is correct regardless of 6- vs
   8-core layout.
2. Take the standard hwmon file every monitoring tool already reads for
   GPU frequency (/sys/class/hwmon/hwmonN/freq1_input, where hwmonN is
   the "amdgpu" instance) and bind-mount a corrected copy over it,
   writing the value from step 1 (converted to Hz, the hwmon convention)
   on every update cycle. This is a plain text integer file, not a
   struct, so there's no offset math involved.

This is the same technique cyan-skillfish-governor-smu already uses in
production to fix its "655% GPU usage" bug (see gpu_usage_fix.rs, which
does the equivalent for debugfs gpu_metrics) -- same bind-mount idea,
applied to whichever specific file the reading tool actually consumes.
(On the BC-250 board this was developed against, debugfs gpu_metrics
doesn't exist at all in this kernel build -- only the older text-based
amdgpu_pm_info debugfs entry and the standard hwmon files are present,
which is why this version targets hwmon instead.)

The queue-0 mailbox message (and why an earlier version of this script
got it wrong)
---------------------------------------------------------------------------
PPSMC_MSG_GetGfxFrequency (0x37) is only defined on SMU mailbox queue 0 --
confirmed against filippor/cyan-skillfish-governor's own queue0.rs
(`get_gfx_frequency` -> `send_message(0, 0x37, ...)`). An earlier version
of this script deliberately avoided queue 0 (to not collide with
cyan-skillfish-governor-smu's own use of it) and sent message 0x37 on
queue 4 instead -- but queue 4's message-ID space is unrelated and mostly
undocumented (see that project's queue4.rs: messages 0x04-0x11 only), so
0x37 there returned meaningless data. That was the actual bug behind
"apu_telemetry doesn't show the real GPU frequency": not the offset
theory being wrong, but querying the wrong physical mailbox for that
particular message.

Queue 0 *is* shared with cyan-skillfish-governor-smu (which uses it for
force_gfx_freq/unforce_gfx_freq when set-method="smu", plus a handful of
other control messages) -- so this script is a second, unsynchronized
writer on that mailbox's 3 registers. There's no cross-process lock
available (the governor only guards its *own* concurrent access via an
in-process Mutex). To keep the risk low:
  - Only ever *read* GetGfxFrequency (0x37) -- never send a SET/FORCE
    message on queue 0 from this script.
  - Retry a few times with a short backoff on REJECTED_BUSY/timeout
    rather than treating the first failure as fatal.
  - Sanity-clamp the result to a plausible clock range (BC-250 configs
    on this board run 500-2400 MHz); anything outside that range is
    treated as a bad read.
  - On repeated mailbox failure, fall back to
    metrics.Average.GfxclkFrequency (gpu_metrics offset 0x40,
    `average_gfxclk_frequency`) -- confirmed uncorrupted even in hybrid
    mode, read-only sysfs, zero collision risk, just less instantaneous.
  - Poll at a modest interval (default 1s) -- the governor's own queue-0
    traffic is bursty and brief, so collisions are rare at this cadence.

Access path: BAR5 MMIO (not PCI config space) -- config-space access to
the indirect index/data registers timed out on at least one real BC-250
board tested (Bazzite, VBIOS 113-AMDRBN-003 build 584828), while BAR5 MMIO
access to the same registers worked correctly. See bc250_mailbox_bar5_probe.py
for how this was diagnosed.

Requires root (BAR5 mmap, mount --bind).
"""

import argparse
import glob
import logging
import mmap
import os
import signal
import struct
import subprocess
import sys
import time

AMD_VENDOR_ID = 0x1002
BC250_DEVICE_ID = 0x13FE

# BAR5 MMIO offsets for the NBIO indirect index/data register pair.
# Verified against drivers/gpu/drm/amd/amdgpu/{amdgpu_reg_access.c,nbio_v2_3.c}
# for NBIO_HWIP version 2.1.1 (Cyan Skillfish).
INDEX2_OFFSET = 0x38
DATA2_OFFSET = 0x3C

# SMU mailbox queue addresses, taken from cyan-skillfish-governor-smu
# (github.com/filippor/cyan-skillfish-governor, branch smu, src/smu/mod.rs
# DEFAULT_QUEUE_ADDRS) -- the same tool the wider BC-250 community already
# runs in production. Kept here for reference/diagnostics even though this
# script only ever talks to queue 0.
QUEUE_ADDRS = {
    0: (0x03B10A08, 0x03B10A68, 0x03B10A48),
    1: (0x03B10A00, 0x03B10A60, 0x03B10A40),
    2: (0x03B10528, 0x03B10564, 0x03B10998),
    3: (0x03B10A20, 0x03B10A80, 0x03B10A88),
    4: (0x03B10A24, 0x03B10A84, 0x03B10A8C),
}

# PPSMC_MSG_GetGfxFrequency only exists in queue 0's message set (see
# queue0.rs in the governor project). It is NOT portable to other queues.
GFXCLK_QUEUE = 0
MSG_TEST = 0x01
MSG_GET_GFXCLK_FREQUENCY = 0x37
SMU_STATUS_NAMES = {0x01: "OK", 0xFF: "FAILED", 0xFE: "UNKNOWN_CMD",
                    0xFD: "REJECTED_PREREQ", 0xFC: "REJECTED_BUSY"}

# Plausible BC-250 gfxclk range on this board (governor config allows up to
# 2400 MHz safe-points); anything outside this is treated as a bad read
# rather than trusting it blindly.
GFXCLK_MIN_PLAUSIBLE_MHZ = 50
GFXCLK_MAX_PLAUSIBLE_MHZ = 2600

GPU_METRICS_AVERAGE_GFXCLK_OFFSET = 0x40  # gpu_metrics_v2_2.average_gfxclk_frequency

PATCHED_METRICS_PATH = "/dev/shm/bc250_gfxclk_fix_patched_freq1_input"

log = logging.getLogger("bc250-gfxclk-fix")


def find_bc250_device_path():
    for dev in sorted(glob.glob("/sys/bus/pci/devices/*")):
        try:
            vendor = int(open(os.path.join(dev, "vendor")).read().strip(), 16)
            device = int(open(os.path.join(dev, "device")).read().strip(), 16)
        except (OSError, ValueError):
            continue
        if vendor == AMD_VENDOR_ID and device == BC250_DEVICE_ID:
            return dev
    return None


def find_hwmon_freq1_path():
    """Find /sys/class/hwmon/hwmonN/freq1_input for the amdgpu hwmon
    instance. Matches the exact discovery logic in bc250_telemetry.cpp's
    get_hwmon_dir("amdgpu") -- read each hwmon*/name file, take the one
    whose content is exactly "amdgpu"."""
    for name_file in sorted(glob.glob("/sys/class/hwmon/hwmon*/name")):
        try:
            name = open(name_file).read().strip()
        except OSError:
            continue
        if name == "amdgpu":
            freq_path = os.path.join(os.path.dirname(name_file), "freq1_input")
            if os.path.exists(freq_path):
                return freq_path
    return None


def find_gpu_metrics_path():
    matches = glob.glob("/sys/devices/pci*/*/*/gpu_metrics") + \
        glob.glob("/sys/devices/pci*/*/*/*/gpu_metrics")
    return matches[0] if matches else None


def read_average_gfxclk_mhz(gpu_metrics_path):
    """Read gpu_metrics_v2_2.average_gfxclk_frequency -- the Average table
    stays 6-wide even when the Current table switches to the 8-core hybrid
    layout, so this field is never affected by the offset bug. Read-only
    sysfs, no mailbox, no collision risk with the governor -- used as the
    fallback when the queue-0 mailbox read fails."""
    with open(gpu_metrics_path, "rb") as f:
        data = f.read()
    if len(data) < GPU_METRICS_AVERAGE_GFXCLK_OFFSET + 2:
        return None
    return struct.unpack_from("<H", data, GPU_METRICS_AVERAGE_GFXCLK_OFFSET)[0]


def bar5_length(devpath):
    with open(os.path.join(devpath, "resource")) as f:
        lines = f.readlines()
    start_s, end_s, _ = lines[5].split()
    start, end = int(start_s, 16), int(end_s, 16)
    return end - start + 1


class Bar5Mailbox:
    """SMU mailbox over BAR5 MMIO. Confirmed working on real BC-250
    hardware where the PCI-config-space path (0xB8/0xBC) timed out."""

    def __init__(self, devpath, queue, timeout=20000):
        self.length = bar5_length(devpath)
        self.fd = os.open(os.path.join(devpath, "resource5"), os.O_RDWR)
        self.mm = mmap.mmap(self.fd, self.length, mmap.MAP_SHARED,
                             mmap.PROT_READ | mmap.PROT_WRITE)
        self.cmd_addr, self.rsp_addr, self.arg_addr = QUEUE_ADDRS[queue]
        self.timeout = timeout

    def close(self):
        self.mm.close()
        os.close(self.fd)

    def _write32(self, off, val):
        self.mm[off:off + 4] = struct.pack("<I", val & 0xFFFFFFFF)

    def _read32(self, off):
        return struct.unpack("<I", self.mm[off:off + 4])[0]

    def _read_indirect(self, reg):
        self._write32(INDEX2_OFFSET, reg)
        return self._read32(DATA2_OFFSET)

    def _write_indirect(self, reg, value):
        self._write32(INDEX2_OFFSET, reg)
        self._write32(DATA2_OFFSET, value)

    def send(self, msg_id, arg=0, arg_high=0):
        self._write_indirect(self.rsp_addr, 0)
        self._write_indirect(self.arg_addr, arg)
        self._write_indirect(self.arg_addr + 4, arg_high)
        self._write_indirect(self.cmd_addr, msg_id)
        remaining = self.timeout
        while remaining > 0:
            remaining -= 1
            status = self._read_indirect(self.rsp_addr) & 0xFF
            if status in SMU_STATUS_NAMES:
                return status
        raise TimeoutError("SMU mailbox timed out")

    def read_arg(self):
        return self._read_indirect(self.arg_addr)

    def get_gfxclk_mhz(self):
        status = self.send(MSG_GET_GFXCLK_FREQUENCY)
        if status != 0x01:
            raise RuntimeError(f"GetGfxFrequency failed: {SMU_STATUS_NAMES.get(status, hex(status))}")
        return self.read_arg()

    def self_test(self):
        """MSG_TEST (0x01) is only defined on queue 3 in the governor's own
        message set (Bc250Smu::test_message hardcodes queue 3) -- it is NOT
        a valid message on queue 0, so this deliberately does not reuse
        self.queue/self.cmd_addr and instead talks to queue 3 directly."""
        cmd_addr, rsp_addr, arg_addr = QUEUE_ADDRS[3]
        self._write_indirect(rsp_addr, 0)
        self._write_indirect(arg_addr, 123)
        self._write_indirect(arg_addr + 4, 0)
        self._write_indirect(cmd_addr, MSG_TEST)
        remaining = self.timeout
        status = None
        while remaining > 0:
            remaining -= 1
            s = self._read_indirect(rsp_addr) & 0xFF
            if s in SMU_STATUS_NAMES:
                status = s
                break
        if status is None:
            raise TimeoutError("self-test (queue 3) mailbox timed out")
        if status != 0x01:
            raise RuntimeError(f"self-test failed: {SMU_STATUS_NAMES.get(status, hex(status))}")
        echoed = self._read_indirect(arg_addr)
        if echoed != 124:
            raise RuntimeError(f"self-test echo mismatch: expected 124, got {echoed}")


def get_gfxclk_mhz_with_fallback(mailbox, gpu_metrics_path, retries, retry_delay):
    """Try the authoritative queue-0 mailbox read a few times (tolerating
    REJECTED_BUSY/timeouts from colliding with the governor's own queue-0
    traffic), sanity-check the result, and fall back to the Average-table
    sysfs value if the mailbox is uncooperative or returns nonsense."""
    last_err = None
    for attempt in range(retries):
        try:
            mhz = mailbox.get_gfxclk_mhz()
        except (TimeoutError, RuntimeError) as e:
            last_err = e
            time.sleep(retry_delay)
            continue
        if GFXCLK_MIN_PLAUSIBLE_MHZ <= mhz <= GFXCLK_MAX_PLAUSIBLE_MHZ:
            return mhz, "mailbox"
        last_err = RuntimeError(f"implausible mailbox value: {mhz} MHz")
        time.sleep(retry_delay)

    if gpu_metrics_path is not None:
        avg = read_average_gfxclk_mhz(gpu_metrics_path)
        if avg is not None and GFXCLK_MIN_PLAUSIBLE_MHZ <= avg <= GFXCLK_MAX_PLAUSIBLE_MHZ:
            log.debug("mailbox read failed (%s), using Average.GfxclkFrequency fallback = %d MHz",
                      last_err, avg)
            return avg, "average_fallback"

    raise RuntimeError(f"no usable gfxclk source (mailbox: {last_err}, no valid fallback)")


class GfxclkHwmonOverlay:
    """Bind-mounts a correctable copy of hwmon's freq1_input over the real
    file. Same technique as cyan-skillfish-governor-smu's gpu_usage_fix.rs,
    just simpler: freq1_input is a plain text integer (Hz), not a binary
    struct, so there's no offset math -- just write the corrected number."""

    def __init__(self, real_path):
        self.real_path = real_path
        self._umount_bind(real_path)  # clean up a stale mount from a previous crashed run, if any
        self.real_file = open(real_path, "r")

        if os.path.exists(PATCHED_METRICS_PATH):
            os.remove(PATCHED_METRICS_PATH)
        self.patched_file = open(PATCHED_METRICS_PATH, "w+")
        self.patched_file.write(self._read_real())
        self.patched_file.flush()
        os.chmod(PATCHED_METRICS_PATH, 0o644)

        self._mount_bind(PATCHED_METRICS_PATH, real_path)
        os.remove(PATCHED_METRICS_PATH)  # bind mount keeps the inode alive
        log.info("Bind-mounted corrected freq1_input over %s", real_path)

    def _read_real(self):
        self.real_file.seek(0)
        return self.real_file.read()

    def apply_gfxclk(self, gfxclk_mhz):
        hz = gfxclk_mhz * 1_000_000
        self.patched_file.seek(0)
        self.patched_file.truncate()
        self.patched_file.write(f"{hz}\n")
        self.patched_file.flush()

    def shutdown(self):
        self._umount_bind(self.real_path)
        self.real_file.close()
        self.patched_file.close()

    def _mount_bind(self, src, dst):
        result = subprocess.run(["mount", "--bind", src, dst], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"mount --bind {src} {dst} failed: {result.stderr.strip()}")

    def _umount_bind(self, dst):
        subprocess.run(["umount", dst], capture_output=True)



def main():
    ap = argparse.ArgumentParser(
        description="Overlay the correct GPU frequency onto hwmon freq1_input so monitoring tools display it right"
    )
    ap.add_argument("--interval", type=float, default=1.0, help="update interval in seconds (default: 1.0)")
    ap.add_argument("--retries", type=int, default=3, help="mailbox read attempts before falling back (default: 3)")
    ap.add_argument("--retry-delay", type=float, default=0.02,
                     help="delay between mailbox retries in seconds (default: 0.02)")
    ap.add_argument("--self-test", action="store_true", help="run a mailbox self-test before starting")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
    )

    if os.geteuid() != 0:
        sys.exit("This needs root (BAR5 mmap, mount --bind). Run with sudo.")

    devpath = find_bc250_device_path()
    if devpath is None:
        sys.exit(f"BC-250 ({AMD_VENDOR_ID:04x}:{BC250_DEVICE_ID:04x}) not found.")
    bdf = os.path.basename(devpath)
    log.info("Found BC-250 at %s", bdf)

    freq1_path = find_hwmon_freq1_path()
    if freq1_path is None:
        sys.exit("Could not find hwmon freq1_input for amdgpu (is the driver loaded?)")
    log.info("Real hwmon freq1_input path: %s", freq1_path)

    gpu_metrics_path = find_gpu_metrics_path()
    if gpu_metrics_path is None:
        log.warning("gpu_metrics sysfs not found -- no fallback source if the mailbox is unavailable")
    else:
        log.info("gpu_metrics fallback path: %s", gpu_metrics_path)

    mailbox = Bar5Mailbox(devpath, GFXCLK_QUEUE)
    overlay = None
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        log.info("Received signal %s, shutting down", signum)
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        if args.self_test:
            mailbox.self_test()
            log.info("Mailbox self-test OK")

        overlay = GfxclkHwmonOverlay(freq1_path)

        while running:
            try:
                gfxclk, source = get_gfxclk_mhz_with_fallback(
                    mailbox, gpu_metrics_path, args.retries, args.retry_delay)
                overlay.apply_gfxclk(gfxclk)
                log.debug("gfxclk = %d MHz (source: %s)", gfxclk, source)
            except RuntimeError as e:
                log.warning("Failed to update gfxclk this cycle: %s", e)
            time.sleep(args.interval)
    finally:
        if overlay is not None:
            overlay.shutdown()
        mailbox.close()
        log.info("Unmounted overlay, exiting cleanly")


if __name__ == "__main__":
    main()
