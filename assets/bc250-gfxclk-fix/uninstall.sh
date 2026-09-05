#!/usr/bin/env bash
# Removes bc250-gfxclk-fix installed by install.sh.
set -euo pipefail

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run this with sudo"

log "Stopping and disabling the service"
systemctl disable --now bc250-gfxclk-fix.service 2>/dev/null || true

log "Removing installed files"
rm -f /etc/systemd/system/bc250-gfxclk-fix.service
rm -f /usr/local/bin/bc250_gfxclk_fix.py

systemctl daemon-reload

log "Done. The stock (uncorrected) GPU frequency reporting is back immediately -- the bind-mount overlay is torn down as soon as the service stops."
