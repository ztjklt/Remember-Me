#!/usr/bin/env bash
# Requires prepared host, root-owned 0600 environment files and reviewed domain.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
root=/opt/remember-me/current
for service in api worker profile ai proxy; do
  config=/etc/remember-me/$service.env
  [ -f "$config" ] || { echo "Missing $service configuration" >&2; exit 1; }
  [ "$(stat -c %U:%a "$config")" = root:600 ] || { echo "Require root:600 for $service configuration" >&2; exit 1; }
  if grep -qE 'REPLACE_|example\.invalid' "$config"; then
    echo "Unfilled $service configuration" >&2; exit 1
  fi
done
systemd-run --unit=remember-me-migrate --wait --collect --pipe \
  --property=User=rememberme --property=Group=rememberme \
  --property=EnvironmentFile=/etc/remember-me/api.env \
  --property=WorkingDirectory="$root/services/backend" \
  "$root/services/backend/.venv/bin/python" -m alembic upgrade head
# Warm the pinned CPU retrieval model before a user asks the first question.
systemd-run --unit=remember-me-prewarm --wait --collect --pipe \
  --property=User=rememberme --property=Group=rememberme \
  --property=EnvironmentFile=/etc/remember-me/api.env \
  --property=WorkingDirectory="$root/services/backend" \
  --setenv=HF_HOME=/var/lib/remember-me/model-cache \
  "$root/services/backend/.venv/bin/python" -c \
  'from app.retrieval import LocalEncoder,DEFAULT_EMBEDDING; assert LocalEncoder(DEFAULT_EMBEDDING).encode(["部署检查"])'
systemctl enable --now remember-me@ai remember-me@api remember-me@worker remember-me@profile
# Public ingress remains a separate cloud firewall operation.
systemctl enable --now remember-me-proxy
systemctl is-active remember-me@ai remember-me@api remember-me@worker remember-me@profile remember-me-proxy
