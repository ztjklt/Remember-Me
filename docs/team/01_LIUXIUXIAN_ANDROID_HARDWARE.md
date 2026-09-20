# 刘修贤 Android and Hardware Task Brief

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, the Team Development Guide, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

## Goal

Turn the existing `apps/android` Mock Prototype into a usable Android client and add a capability-based hardware adapter without rewriting the working Compose project.

## Phase 1 — COMMITTED

1. Preserve and review the existing screens, navigation, design system, repository boundary, and tests. Do not tear down the Compose project without a stated reason.
2. Implement microphone permission, real recording, pause or stop, elapsed time, audio-file persistence, and required metadata.
3. Replace mock capture state with repository and service interfaces that accept backend status from the shared contract.
4. Upload an audio file, expose progress and retry, create an Episode, and connect real processing state to the Processing screen.
5. Handle permission denial, missing data, offline storage, upload failure, and processing failure.

**Definition of done:** a real device can Consent → Permission → Record → File → Upload → Processing → Backend result.

## Phase 2 — PLANNED

Connect the Memories screen to real data — people, events, relationships, themes, and evidence. Visualize Person Model and Coverage so the user can see what the system knows and what it is based on. Build the Twin client: question input, answering state, evidence display, and a clear visual and textual distinction between Original and Simulation. Add memory correction and deletion UI wired to the backend, and make the UI reflect model updates.

## Phase 3 — PLANNED

Calibration UI showing the question, the locked Twin answer, the human answer, the five-dimension diff, and follow-up questions. Voice Seed and Voice Confirmation UI with playback, confirmation, and a "not enough like me / re-record" path. Twin Voice player keeping text and voice answering states consistent.

## Phase 4 — BACKLOG / CONDITIONAL

Integrate the Work 3200 / recording device SDK: connection, capability, recording sync, device state. Implement markers only if the official capability supports them. Guarantee the Hardware Adapter fallback so phone Capture stays fully usable with no device. Complete the Handover/Legacy client pages and Recipient-mode permission behaviour.

## Hardware boundary

Define a degradable adapter for `startRecording`, `stopRecording`, device state, recording retrieval, recording availability, and a device capability profile. Add markers only if the device supports them. The app must remain fully usable without hardware.

## Acceptance

A real device can open the app, grant consent and permission, record an audio file, upload it, see processing state, and receive a backend result. Submit Android setup, permission and API notes, and tests for the critical path.
