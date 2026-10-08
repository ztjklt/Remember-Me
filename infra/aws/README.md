# AWS pilot runbook

Status: deployment files prepared; **no AWS resources created by this change**.
Use the existing Remember Me backend and AI Core. Windows `.env` files, local
databases, actor credentials, and benchmark audio are excluded from the release.

## Resources and boundary

`pilot.yaml`: one Ubuntu 24.04 amd64 `t3.medium` (2 vCPU/4 GiB), 40 GiB encrypted
gp3 root disk, one Elastic IP, one private encrypted S3 bucket, EC2 instance role
and SSM. No SSH or database ingress. `PublicWeb=false` creates no inbound rules;
only switch it to true when the reviewed HTTPS entry is ready (80/443 only).
CPU credits use standard mode, so sustained CPU load may throttle rather than
generate surplus-credit charges. This is a small pilot, not a capacity SLA.

Use a public subnet with an Internet Gateway, not a new NAT Gateway. Verify the
subnet belongs to the selected VPC. In Singapore on 2026-10-08, the console lists
Canonical Ubuntu 24.04 amd64 `ami-03acbba64aef9bf5c`; verify owner Canonical and
image availability before deployment. Do not substitute Ubuntu 26.04 silently.

CloudFormation creation requires IAM capability acknowledgement and explicit
resource/network approval. Preview/dry validation does not grant permissions or
prove account quotas. The service role can read/write/delete only this bucket's
`audio/` objects and the exact readiness key `healthcheck/probe`, read `releases/`,
and write `backups/`; it has SSM's managed
instance policy. The bucket never serves public audio URLs. Application routes
perform identity, grant and source-version checks before returning audio.

Instance, disk and S3 data are retained on removal of the stack. Stack deletion
is **not** full cost cleanup. Stopped instances still incur disk/IP/storage costs;
retained resources need a separately reviewed export/removal decision. No automatic
destructive expiry is installed. Activity credit currently expires 2026-10-31.

## Build and install

1. From the repository root, run `python tools/package_cloud.py`. Review the
   source manifest and SHA256 in `output/aws/`; package creation aborts if it
   encounters configured credentials, unsafe paths, or symlinks. It contains
   source/config templates only, not an already provisioned service.
2. After cloud resource approval, upload only the resulting package to this
   project's private `releases/` prefix. Use temporary operator credentials;
   EC2 retrieves it using its role. No long-lived AWS key is required by the app.
3. Verify SHA256, extract into `/opt/remember-me/current`, retain root ownership,
   and run `sudo bash infra/aws/prepare-host.sh`. This is for a fresh Ubuntu host;
   it refuses an already-active default Caddy. It prepares but does not start the app.
4. Create `/etc/remember-me/{api,worker,profile,ai,proxy}.env`, root-owned mode
   0600. The first three use `backend.env.example`; AI and proxy use their own
   templates. Only backend processes receive the Groq key; only AI Core receives
   the Weixin key. Keep model keys out of EC2 UserData, SSM command text, history,
   frontend, APK and release archives. Configure them over an approved secure
   transfer/session rather than pasting into a logged command.
5. Set the real domain, host allowlist and private bucket. Start with registration
   disabled; create approved tester accounts through the normal registration API
   during a controlled test window, then disable new registration again. Existing
   logins continue to work. Domain ownership, DNS and a valid certificate must
   be established before sharing the URL or building a connected APK.
6. `sudo bash infra/aws/activate.sh` migrates PostgreSQL, warms the pinned Chinese
   CPU embedding model, and starts five systemd services. The migration runs as
   database owner `rememberme`, via peer-authenticated Unix socket. Do not expose
   port 5432. `uv.lock` pins Linux CPU torch; no CUDA installation is needed.
7. Inspect systemd status and health routes. Open reviewed public ingress and
   obtain/verify Caddy's public certificate. Run fictional material through Groq,
   review, Weixin, memory, candidates, source playback and two-account revocation.
   A health endpoint alone is not end-to-end acceptance.

If Hugging Face cannot be reached, preload **the same pinned**
`BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620`
from a verified cache into `/var/lib/remember-me/model-cache/hub/`, owned by
rememberme. Copy only that model's files, never the user's entire Hugging Face
configuration or tokens. Record hashes and set `HF_HUB_OFFLINE=1` in the relevant
backend environment files. This is a retrieval dependency; ASR remains Groq.

## Verification and recovery

The following test commands are for a **disposable local Ubuntu rehearsal**,
not the source-only release or production host. They require the complete test
checkout (including `tools/`, backend tests and development dependencies),
PostgreSQL 16 client/server, Caddy and Python 3.12. In a new disposable Linux
environment, start PostgreSQL and prepare a non-superuser peer-authenticated root
role and a dedicated test database (skip creation only if already present):

```bash
sudo systemctl start postgresql
sudo -u postgres createuser --no-superuser --no-createdb --no-createrole root
sudo -u postgres createdb --owner=root remember_deploy_test
# As root, in the complete test checkout, not the live release:
cd services/backend
uv sync --locked --extra deployment --extra retrieval
REMEMBER_TEST_POSTGRES_URL=postgresql+psycopg:///remember_deploy_test .venv/bin/pytest
cd ../..
services/backend/.venv/bin/python tools/aws_linux_smoke.py
```

The smoke script runs as root because it uses `runuser -u postgres` to create and
drop a separately named temporary restore database. It uses PostgreSQL's `root`
role for the test database; `prepare-host.sh` intentionally creates only the
application's `rememberme` role, not these testing prerequisites. Do not create
test roles/databases on the production host. The existing checkout's `.env` must
not be copied into this test environment.

- `REMEMBER_TEST_POSTGRES_URL=postgresql+psycopg:///remember_deploy_test pytest`
  inside backend: shared fixtures use random PostgreSQL schemas in a database
  whose name ends `_test`; explicit SQLite tests remain SQLite. Never point this
  at the application database. Three PG transaction/migration/error probes added.
- `python tools/aws_linux_smoke.py` inside the prepared Linux source copy checks
  real local TLS, staging account security, restart and independent pg_dump
  restore. It uses loopback 18443/18877 and a client-only CA. It sends no model
  requests and does not install a system CA or touch the existing PC app.
- PostgreSQL's short publication transaction conservatively locks all mapped
  tables against DML. This covers existing workers that don't take advisory locks.
  Ordinary reads remain available, but concurrent writes serialize globally.
  Lock conflicts return `409 STATE_CONFLICT`; no model invocation is replayed.
  This tradeoff is for the pilot; throughput at larger scale is unverified.
- Run `infra/aws/backup.sh` as rememberme with `REMEMBER_BACKUP_BUCKET` configured.
  It creates a private local pg_dump and uploads it under private `backups/`.
  It does not delete old backups. A scheduler/retention decision must be installed
  and verified before persistent user data is accepted.
- Restore into an **independent empty database** first with `pg_restore`; verify
  account ownership, source IDs, grants, corrections and audio hashes. Never test
  restoration over the live database. The local Linux rehearsal verified accounts
  and owner spaces; AWS backup upload and complete remote disaster recovery remain
  to be tested after resource creation.
- For rollback stop workers/API, preserve database+audio backups, restore a
  compatible release and schema; do not automatically downgrade live data.

Android's public APK requires the final HTTPS `SERVICE_URL`, a deliberate build
type/signing choice, and mobile-network device verification. The existing local
debug APK and Android emulator are not that deliverable. iOS requires macOS.
