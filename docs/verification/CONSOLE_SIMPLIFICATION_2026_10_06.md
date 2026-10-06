# Demo launcher and console verification — 2026-10-06

Scope: local demo launcher and browser console only. No shared contracts, Android,
provider configuration, or database schema changes.

## Findings and behavior

- The earlier demo still owned ports 8000/8100. A duplicate launcher received the
  old services' health responses while its children failed to bind, then silently
  exited. Both child logs confirmed `address already in use`.
- Preflight checks ports before migrations/log writes. Duplicate launches fail
  clearly; child exits report service, exit code and log path, including worker.
  Logs append. Port checks permit immediate restart after closed TCP connections.
- Main view shows recording text, active understanding, question/answer, correction
  and updated understanding. Technical JSON and session tools are collapsed.
- Asking generates and locks one answer via the existing calibration endpoint.
  The displayed answer equals the answer compared during correction. Changing
  the question disables correction until asking again. Prior answers are labelled
  after correction, while new understanding and the user's correction are shown.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts services/backend/.venv/bin/python -m pytest scripts/tests/test_agent_demo.py -q`: 7 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts services/backend/.venv/bin/python -m pytest scripts/agent_console/tests/test_server.py -q`: 4 passed.
- `node --check` on `capture.js`, `agent.js`, `render.js`: passed.
- Existing `browser_capture.py` then `browser_agent.py` against fixture ports
  8001/8101/8201: passed, including consent, capture/upload, isolation, readable
  views, same-answer calibration, edited-question guard, recovery, update and revoke.
- Real configured session: loaded actual transcript/current understanding, asked
  the identity question, verified the correct answer and enabled correction; no
  JS errors or horizontal overflow at 1100px/390px. No new real correction submitted.
- Configured launch remained running; duplicate invocation exited 2 without
  stopping the running services. Both health endpoints and console returned 200.
- Terminating the fixture worker made its launcher exit 1 with the worker exit
  code/log path and clean up its other children. Ctrl-C stopped configured services
  cleanly; immediate restart succeeded. Demo processes stopped after verification
  so the user's terminal can own the next run.

No new real recording/ASR validation or Android build was performed. No independent
lint/format/typecheck is configured for this tool. Browser acceptance uses the
existing Playwright environment and cached Chromium, without added dependencies.
