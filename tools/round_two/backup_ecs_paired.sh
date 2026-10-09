#!/usr/bin/env bash
# Root-only, remote-only secrets backup and isolated restore drill. No cutover.
set -euo pipefail
umask 077
test "$(id -u)" = 0
candidate=/opt/remember-me/releases/paired-20261009-candidate
stamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot=/var/lib/remember-me/backups/paired-$stamp
restore_db=remember_paired_restore_${stamp,,}_test
[[ "$restore_db" =~ ^remember_paired_restore_[0-9]{8}t[0-9]{6}z_test$ ]]
mkdir -p "$snapshot"
chmod 700 "$snapshot"
readlink -f /opt/remember-me/current > "$snapshot/previous-release.txt"
# postgres cannot enter the root-only directory; stream rather than loosen permissions.
runuser -u postgres -- pg_dump --format=custom --no-owner --no-acl remember_me > "$snapshot/database.dump"
tar -C /var/lib/remember-me -czf "$snapshot/audio.tar.gz" audio
tar -C /etc -czf "$snapshot/config.tar.gz" remember-me
sha256sum "$snapshot"/*.dump "$snapshot"/*.tar.gz > "$snapshot/SHA256SUMS"
pg_restore --list "$snapshot/database.dump" > "$snapshot/toc.txt"
runuser -u postgres -- createdb -O root "$restore_db"
pg_restore --exit-on-error --no-owner --no-acl --dbname="$restore_db" "$snapshot/database.dump"
mkdir "$snapshot/restored-audio"
tar -C "$snapshot/restored-audio" -xzf "$snapshot/audio.tar.gz"
cd "$candidate/services/backend"
REMEMBER_DATABASE_URL="postgresql+psycopg:///$restore_db" .venv/bin/python -m alembic upgrade head > "$snapshot/migration.log" 2>&1
REMEMBER_DATABASE_URL="postgresql+psycopg:///$restore_db" SNAPSHOT="$snapshot" .venv/bin/python - <<'PY'
import json, os
from pathlib import Path
from sqlalchemy import create_engine,text
from app.models import Base
root=Path(os.environ['SNAPSHOT'])
engine=create_engine(os.environ['REMEMBER_DATABASE_URL'])
with engine.connect() as c:
    counts={t.name:c.execute(text('SELECT count(*) FROM "'+t.name+'"')).scalar_one() for t in Base.metadata.sorted_tables}
    revision=c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
assert revision=='0016_share_invitations'
original=Path('/var/lib/remember-me/audio')
restored=root/'restored-audio/audio'
import hashlib
files=list(restored.rglob('*'))
checks=[(str(p.relative_to(restored)),hashlib.sha256(p.read_bytes()).hexdigest()) for p in files if p.is_file()]
assert checks and all((original/name).is_file() and hashlib.sha256((original/name).read_bytes()).hexdigest()==digest for name,digest in checks)
result={'database':engine.url.database,'migration':revision,'row_counts':counts,'restored_files':len(checks),'audio_hash_match':True,'config_archive_retained_on_server_only':True,'cutover':False}
(root/'restore-check.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'snapshot':str(root),'database':engine.url.database,'restored_files':len(checks),'migration':revision,'cutover':False}))
PY
