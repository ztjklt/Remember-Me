#!/usr/bin/env bash
# Run on a fresh Ubuntu 24.04 host after reviewing the resource plan.
# Does not configure public access, copy secrets or start Remember Me.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
[ "$root" = /opt/remember-me/current ] || { echo 'Extract release to /opt/remember-me/current first' >&2; exit 1; }
apt-get update -qq
caddy_present=false
dpkg-query -W caddy >/dev/null 2>&1 && caddy_present=true
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv postgresql postgresql-client ffmpeg caddy
# Ubuntu packages auto-start their default site. Stop only the newly installed
# service; never replace another project's already-running reverse proxy.
if [ "$caddy_present" = false ]; then systemctl disable --now caddy; fi
if systemctl is-active --quiet caddy; then
  echo 'An existing Caddy service owns this host; review before deploying.' >&2
  exit 1
fi
id rememberme >/dev/null 2>&1 || useradd --system --home-dir /var/lib/remember-me --create-home rememberme
install -d -m 700 -o rememberme -g rememberme /var/lib/remember-me
install -d -m 700 /etc/remember-me
python3 -m venv /opt/remember-me/installer
/opt/remember-me/installer/bin/pip install 'uv==0.12.23'
uv=/opt/remember-me/installer/bin/uv
cd "$root/services/backend"
# Linux CPU wheels and every transitive version are pinned in uv.lock.
"$uv" sync --locked --no-dev --extra deployment --extra retrieval --python /usr/bin/python3
cd "$root/services/ai-core"
"$uv" sync --locked --no-dev --python /usr/bin/python3
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rememberme'" | grep -q 1 || runuser -u postgres -- createuser rememberme
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='remember_me'" | grep -q 1 || runuser -u postgres -- createdb -O rememberme remember_me
install -m 644 "$root/infra/aws/remember-me@.service" /etc/systemd/system/
install -m 644 "$root/infra/aws/remember-me-proxy.service" /etc/systemd/system/
systemctl daemon-reload
echo 'Runtime prepared. Configure root-only environment files; run migrations and checks before starting services.'
