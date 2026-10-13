# Voice Service

The iOS-first local Voice slice is authorized by the [Twin and Voice proposal](../../docs/architecture/twin-voice-contract-proposal.md). The original [task brief](../../docs/team/03_WANGHAOYU_BACKEND_VOICE.md) is historical.

`local_voice.py` is a Mac-only Qwen3-TTS Base / MLX adapter. Start it with `uv run uvicorn local_voice:app --host 127.0.0.1 --port 8300` after `uv sync`. Its model weights are downloaded to the local model cache on first synthesis; they are not committed. Backend accepts only a separate VOICE grant and a dedicated, user-confirmed own-voice sample. The sidecar checks format, level, and 5–15 second duration. The user must confirm that no other person's speech is present; automated speaker verification is not yet implemented and must not be claimed as such.

The sidecar must remain on loopback. The mobile client never calls it directly. The server sends only saved Twin answer text, and generated audio is stored in the local object store. Revoking VOICE removes the sample and generated files.

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

The local voice pipeline calls that same check with `VOICE` before enrollment, synthesis, and audio readback. It does not get its own consent model or a relaxed version of this rule.

## Exclusion rule: keep third-party speech out of a Subject Voice Dataset

A Subject Voice Dataset is the set of audio segments associated with one subject. **Third-party speech must not enter it.** This first local slice relies on a dedicated recording and the Subject's explicit confirmation. It cannot technically verify speaker identity, so that confirmation is a current limitation rather than proof that every sample satisfies the rule.

Third-party speech is any speech that is not the subject's own: another speaker in the room, a voice on a call or a recording being played back, a television or radio, and any segment where the speaker cannot be established as the subject. Overlapping speech counts as third-party on the overlapping portion, because the subject's own voice is not separable from it without guessing.

Why the rule is absolute rather than best-effort:

- A voice profile is a likeness. Building it from audio that contains another person does not merely lower its quality — it makes that person's voice part of an artifact they never agreed to, which no consent scope available today could authorize.
- The subject's consent covers the subject. It cannot cover a bystander, and a bystander has no way to be asked.
- A contaminated profile is not detectably contaminated later. The rule has to hold at ingestion, because there is no cleaning step that makes it safe afterwards.

For this local slice, enrollment refuses an absent confirmation, a recording outside the allowed duration, and near-silent or unreadable audio. The user must reject a sample with another speaker or an uncertain speaker. Automated speaker checks and clean segment selection remain necessary before accepting unattended or imported audio.

## Remaining boundaries

- Automatic speaker identity verification and noisy/multiple-speaker separation are not available in this local slice. Only a dedicated sample that the Subject confirms as their own is admissible.
- Real voice samples belong only in the private local object store, never in this repository.
- Production hardening, and any provider credential in a client. Provider secrets stay server-side and never reach Android (ADR-0001 D10).

## Contract

The implemented local Voice shapes are in [Contract v0.3](../../packages/contracts/README.md); the [proposal](../../docs/architecture/twin-voice-contract-proposal.md) records the Product Owner decision. The older planned v0.2 voice placeholder remains for compatibility.
