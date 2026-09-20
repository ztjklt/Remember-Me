# 刘修贤 Android and Hardware Task Brief

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

## Goal

Turn the existing `apps/android` Mock Prototype into a usable Android client and add a capability-based hardware adapter without rewriting the working Compose project.

## Phase 1 tasks

1. Preserve and review the existing screens, navigation, design system, repository boundary, and tests.
2. Implement microphone permission, real recording, pause or stop, elapsed time, audio-file persistence, and required metadata.
3. Replace mock capture state with repository and service interfaces that accept backend status from the shared contract.
4. Upload an audio file, expose progress and retry, create an Episode, and connect real processing state to the Processing screen.
5. Handle permission denial, missing data, offline storage, upload failure, and processing failure.

## Hardware boundary

Define a degradable adapter for `startRecording`, `stopRecording`, device state, recording retrieval, recording availability, and a device capability profile. Add markers only if the device supports them. The app must remain fully usable without hardware.

## Acceptance

A real device can open the app, grant consent and permission, record an audio file, upload it, see processing state, and receive a backend result. Submit Android setup, permission and API notes, and tests for the critical path.

