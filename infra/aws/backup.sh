#!/usr/bin/env bash
# Run as rememberme. REMEMBER_BACKUP_BUCKET must be the private project bucket.
set -euo pipefail
umask 077
: "${REMEMBER_BACKUP_BUCKET:?Configure the private backup bucket}"
directory=/var/lib/remember-me/backups
mkdir -p "$directory"
snapshot="$directory/remember-me-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
pg_dump --format=custom --no-owner --no-acl --dbname=remember_me --file="$snapshot"
pg_restore --list "$snapshot" >/dev/null
/opt/remember-me/current/services/backend/.venv/bin/python - "$snapshot" <<'PY'
import hashlib, os, sys
from pathlib import Path
import boto3
path=Path(sys.argv[1])
body=path.read_bytes()
checksum=hashlib.sha256(body).hexdigest()
boto3.client('s3').put_object(Bucket=os.environ['REMEMBER_BACKUP_BUCKET'],
    Key='backups/'+path.name,Body=body,ServerSideEncryption='AES256',
    Metadata={'sha256':checksum})
print('Database backup uploaded; sha256='+checksum)
PY
# Keep the local dump too. Retention/deletion is an explicit operator decision.
