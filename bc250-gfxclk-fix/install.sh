#!/usr/bin/env bash
# Installs bc250-gfxclk-fix: corrects GPU frequency reporting on BC-250
# boards where all 8 physical CPU cores are enabled.
#
# Safe to re-run: copies files, reloads systemd, (re)enables the service.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run this with sudo"

log "Installing bc250-gfxclk-fix"
install -m 0755 "${SCRIPT_DIR}/userspace/bc250_gfxclk_fix.py" /usr/local/bin/bc250_gfxclk_fix.py
install -m 0644 "${SCRIPT_DIR}/systemd/bc250-gfxclk-fix.service" /etc/systemd/system/bc250-gfxclk-fix.service

log "Reloading systemd and enabling the service"
systemctl daemon-reload
systemctl enable --now bc250-gfxclk-fix.service

log "Done. Check status with:"
echo "    systemctl status bc250-gfxclk-fix.service"
echo "    journalctl -u bc250-gfxclk-fix.service -f"
echo "    # find the amdgpu hwmon instance and read its corrected freq1_input:"
echo '    for d in /sys/class/hwmon/hwmon*; do [ "$(cat "$d/name")" = amdgpu ] && cat "$d/freq1_input"; done'
