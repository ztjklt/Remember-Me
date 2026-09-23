# Voice Service

Owner: 王昊宇 (`qingtian-4`). Phase 3 — PLANNED. See the [task brief](../../docs/team/03_WANGHAOYU_BACKEND_VOICE.md).

**Status: this directory is a boundary definition, not an implementation.** Phase 1 (Issue #9) establishes the consent boundary and the exclusion rule below so that the voice pipeline cannot later be built on a consent that was never meant to cover it. Nothing here processes audio, and no provider is selected.

## Voice consent is a separate grant

Consent to record a conversation is not consent to build a voice profile from it. They are two grants, and the second is not implied by the first:

| Scope | Covers | Does not cover |
| --- | --- | --- |
| `RECORDING` | Capturing the subject's audio and text, and processing it into memories | Building or using a voice profile |
| `VOICE` | Building and using a voice profile from the subject's audio | Anything `RECORDING` covers |

The rule: **a voice operation must verify a `VOICE` grant, and a `RECORDING` grant never satisfies it.** Recording consent is a broader permission in the everyday sense and a strictly separate one here, because the consequences differ — a transcript is a record of what was said, a voice profile is a usable likeness of the person.

This is enforced in three places, none of which is documentation:

- **The database** refuses a scope this codebase does not register (`ck_consents_scope`, migration `0002_consent_scopes`), so a hand-written row or a typo cannot create a grant no rule would match.
- **The verification rule** matches scope exactly: same subject, same scope, still granted, not revoked. There is no "either scope" path to call by accident (`ConsentRepository.require_active`).
- **The API boundary** asks the question the same way for every caller — `POST /api/v1/consents/authorize` with an explicit `scope`. A recording operation and a voice operation differ only in the scope they name, and naming the wrong one is a `403 CONSENT_INVALID`, not a warning.

When the voice pipeline exists, it calls that same check with `VOICE` before touching audio. It does not get its own consent model, and it does not get a relaxed version of this one.

## Exclusion rule: third-party speech never enters a Subject Voice Dataset

A Subject Voice Dataset is the set of audio segments associated with one subject. **Third-party speech must never enter it.**

Third-party speech is any speech that is not the subject's own: another speaker in the room, a voice on a call or a recording being played back, a television or radio, and any segment where the speaker cannot be established as the subject. Overlapping speech counts as third-party on the overlapping portion, because the subject's own voice is not separable from it without guessing.

Why the rule is absolute rather than best-effort:

- A voice profile is a likeness. Building it from audio that contains another person does not merely lower its quality — it makes that person's voice part of an artifact they never agreed to, which no consent scope available today could authorize.
- The subject's consent covers the subject. It cannot cover a bystander, and a bystander has no way to be asked.
- A contaminated profile is not detectably contaminated later. The rule has to hold at ingestion, because there is no cleaning step that makes it safe afterwards.

What this implies for the pipeline, when it is built: the check belongs at the boundary where a segment would be admitted to a dataset, not at the end of processing; the default answer is refusal; and a segment whose speaker is uncertain is excluded rather than included with a low confidence. The rule is stated here in Phase 1 so that the dataset boundary is designed around it rather than retrofitted.

## Non-goals

- Voice clone, TTS, speaker verification, quality assessment, dataset building, clean segment selection — all Phase 3, none of it authorized in Phase 1.
- Selecting a voice provider. It stays behind an adapter with capability fallback, and the choice is captured in the integration contract before any code depends on it.
- Handling a real voice sample. No such material exists in this repository, and none should.
- Production hardening, and any provider credential in a client. Provider secrets stay server-side and never reach Android (ADR-0001 D10).

## Contract

Inputs and outputs conform to [`packages/contracts`](../../packages/contracts/README.md). The voice shapes in the contract are Phase 3 and are not implemented here; a change to them goes through the Issue/proposal route in [CONTRIBUTING.md](../../CONTRIBUTING.md) rather than being made unilaterally.