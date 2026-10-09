#!/usr/bin/env bash
# Smoke-check candidate API against an explicit restored TEST database only.
set -euo pipefail
test "$(id -u)" = 0
candidate=/opt/remember-me/releases/paired-20261009-candidate
snapshot=/var/lib/remember-me/backups/paired-20261009T112642Z
db=remember_paired_restore_20261009t112642z_test
test -f "$snapshot/restore-check.json"
unit=remember-me-paired-check
if systemctl is-active --quiet "$unit"; then echo 'Candidate check already running; inspect it first'; exit 1; fi
trap 'systemctl stop "$unit" >/dev/null 2>&1 || true' EXIT
systemd-run --unit="$unit" --collect --quiet \
    --property=EnvironmentFile=/etc/remember-me/api.env \
    --property=WorkingDirectory="$candidate/services/backend" \
    /usr/bin/env "REMEMBER_DATABASE_URL=postgresql+psycopg:///$db" \
    "REMEMBER_OBJECT_STORE_ROOT=$snapshot/restored-audio/audio" \
    REMEMBER_RELEASE_ID=paired-20261009-candidate \
    "$candidate/services/backend/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8880 --no-access-log
for ((attempt=0;attempt<30;attempt++)); do
    if curl --fail --silent http://127.0.0.1:8880/ready > /tmp/paired-candidate-ready.json; then break; fi
    sleep 1
done
curl --fail --silent http://127.0.0.1:8880/api/v1/service-info > /tmp/paired-candidate-info.json
python3 - <<'PY'
import json
ready=json.load(open('/tmp/paired-candidate-ready.json'))
info=json.load(open('/tmp/paired-candidate-info.json'))
assert info['sharing_invitations'] is True and info['registration_allowed'] is False
print(json.dumps({'ready':ready,'service_info':info,'environment':'restored test DB','production_cutover':False}))
PY
