#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
case "${1:-}" in
  api)
    cd "$root/services/backend"
    exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${REMEMBER_API_PORT:-8877}" --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log ;;
  worker|profile)
    cd "$root/services/backend"
    module=app.worker
    [ "$1" != profile ] || module=app.profile_worker
    exec .venv/bin/python -m "$module" ;;
  ai)
    cd "$root/services/ai-core"
    exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${REMEMBER_AI_PORT:-8879}" --no-proxy-headers --no-access-log ;;
  *) echo 'Expected api, worker, profile or ai' >&2; exit 2 ;;
esac
