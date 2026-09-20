# Remember Me

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. This repository contains the Android prototype and the shared baseline for backend, AI Core, voice, infrastructure, and team integration.

## Current status

Phase 0 is in progress. The Android UI prototype is runnable and tested; real capture, backend ingestion, STT, AI extraction, person modeling, Twin, voice cloning, cloud sync, accounts, and Work 3200 integration are not yet implemented. The formal product baseline is [Remember Me PRD v2.0](docs/PRD/Remember_Me_PRD_v2.0.docx), with a concise [agent-readable summary](docs/PRD/PRD_V2_SUMMARY.md).

## Repository map

- `apps/android` — existing Android prototype and its original build documentation
- `services/backend` — API, persistence, auth, jobs, and storage
- `services/ai-core` — memory extraction, person model, Twin, calibration, and capture planning
- `services/voice` — consent-gated voice dataset, clone, and TTS adapters
- `packages/contracts` — versioned cross-module schemas; the integration source of truth
- `infra` — environments, deployment, migrations, logging, and monitoring
- `docs/team` — ownership and individual task briefs
- `docs/api` — contract field and integration guidance

## Start here

All contributors and coding agents must read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), the [PRD summary](docs/PRD/PRD_V2_SUMMARY.md), [team ownership](docs/team/00_TEAM_OWNERSHIP.md), and [contract v0.1](packages/contracts/README.md) before changing code.

Android setup and build commands are in [apps/android/README.md](apps/android/README.md). The local verification command is:

```bash
cd apps/android
./gradlew test
```
