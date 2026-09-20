# Contributing

## Branches

- `main` contains stable demonstrable releases and accepts changes only through reviewed Pull Requests.
- `develop` is the continuous integration branch.
- Android and hardware: `feature/android-*`, `feature/hardware-*`
- AI Core: `feature/ai-*`, `feature/person-model-*`, `feature/twin-*`
- Backend, voice, and infrastructure: `feature/backend-*`, `feature/voice-*`, `feature/infra-*`

Create feature branches from `develop` and open Pull Requests back to `develop`. Release Pull Requests go from `develop` to `main`.

## Pull Request contract

Every Pull Request must state what changed, how it was tested, whether `packages/contracts` changed, and any consent, privacy, migration, or rollback impact. Cross-module contract changes require an Issue or proposal before implementation.

## Definition of done

The responsible owner has run the affected path locally, automated checks pass, failure and empty states are handled where relevant, documentation matches behavior, and no secrets or local environment files are committed.

