# Infrastructure

Owner: 王昊宇 (`qingtian-4`). Phase 1 — COMMITTED. See the [task brief](../docs/team/03_WANGHAOYU_BACKEND_VOICE.md).

This directory holds the environment, deployment, migration, and observability notes for the services. It holds no application code and **no secrets**.

| Document | Covers |
| --- | --- |
| [deployment.md](deployment.md) | The environments, the configuration surface, the process model, health and readiness, the observability baseline, and how a secret reaches a process |
| [migrations.md](migrations.md) | How the schema changes, who is allowed to change it, and the local/deployment split |

## One template, not one per service

There is exactly one environment template: [`services/backend/.env.example`](../services/backend/.env.example). A second copy per environment or per service would drift, and a drifted template is how a staging process ends up pointed at a development database. An environment is brought up by copying that one template and overriding the settings that differ — see [deployment.md](deployment.md#bringing-up-a-second-environment).

## Secrets

- Only `*.example` templates are committed, and they carry no credential.
- `.env` is git-ignored; a real credential arrives from the environment the process runs in, not from the repository.
- The rule applies to provider credentials with no exception: no speech-to-text, language-model, or voice-provider key is ever committed, and none is ever shipped to Android (ADR-0001 D10).

Anything that needs a secret to be reproducible is not reproducible, which is why local development and the whole test suite run without one (ADR-0001 D14).

## CI

The service CI workflow ([`.github/workflows/services-ci.yml`](../.github/workflows/services-ci.yml)) runs the backend module's documented verification command on every change under `services/backend/`. A service's workflow is enabled when that service has real source code and a real test command — not before, so a green check always means something ran.