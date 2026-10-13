#!/bin/bash
# Only creates a candidate-local test runtime and a separately named test DB.
set -eu
candidate=/opt/remember-me/releases/paired-20261009-candidate
old=/opt/remember-me/releases/paraformer-20261009
test -f "$candidate/services/backend/app/api/sharing.py"
if ! test -x "$candidate/.test-venv/bin/python"; then
    "$old/services/backend/.venv/bin/python" -m venv "$candidate/.test-venv"
fi
site_dir=$("$candidate/.test-venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')
old_site=$("$old/services/backend/.venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')
printf '%s\n' "$old_site" > "$site_dir/remember-runtime.pth"
"$candidate/.test-venv/bin/python" -m pip install --index-url https://pypi.org/simple pytest pytest-asyncio jsonschema > /tmp/paired-test-install.log 2>&1
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='root'" | grep -q 1; then
    runuser -u postgres -- createuser root
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='remember_paired_test'" | grep -q 1; then
    runuser -u postgres -- createdb -O root remember_paired_test
fi
cd "$candidate/services/backend"
REMEMBER_TEST_POSTGRES_URL=postgresql+psycopg:///remember_paired_test "$candidate/.test-venv/bin/python" -m pytest tests/test_sharing_invitations.py tests/test_accounts.py tests/test_postgres_runtime.py tests/test_agent_workbench.py -q --disable-warnings --junitxml=/tmp/paired-postgres.xml > /tmp/paired-postgres.log 2>&1
