# Agent real loop v0.5 — 2026-10-07

Authorization: the user approved the full first-loop implementation in this task,
including distinct owner/reader identities and story grants. This is a local
feature branch, not a deployment, merge, or claim of mobile acceptance.

Baseline: develop 4dc3d5a. Implement in D:/codex_work/remember-me-agent-loop;
the diet application and historical UI worktrees are out of scope.

## Contract

Keep v0.1–v0.4 payloads. Add backend OpenAPI resources for spaces, story grants,
revision proposals and question requests under /api/v1/workbench. Shared Twin
routes gain authorization-filtered retrieval. Existing owner routes stay owner
only. IMPORT and IOS_MIC both wait for transcript confirmation; Android's legacy
path is retained pending mobile integration. Workbench never spoofs IOS_MIC.

Subject ownership is explicit. Migration leaves old ownership unmapped; an
operator supplies an explicit subject/actor mapping. No first-reader ownership.
Grants include the entire recording and reviewed text, not just memory summaries.
New recordings and revisions are private. A grant is not permission to synthesize
the subject's voice. Reader cloud processing is separately acknowledged by owner
when granting and by reader when issuing the query.

Memory relations: supplement, correction, change; proposals require owner
confirmation. Original recordings remain. Pending revision memories are excluded
from current retrieval. Corrections supersede old memories; time changes keep
history with explicitly supplied temporal text, never inferred exact timestamps.

Source consistency uses a digest of actual source/model/permission state before
and after provider calls, and a short publication transaction. SQLite acceptance
is required; PostgreSQL behavior is not certified by SQLite tests.

## Acceptance

Deterministic tests and real-model tests are different evidence. Verify owner and
reader isolation, grant revocation, in-flight source edits, no pre-review cloud
extraction, import/retry, correction/change, question requests and calibration.
Live test data must be purpose-made, not the user's private Mubu journal.
Missing credentials/models block live acceptance, never trigger fake fallback.

## Execution ledger

- Setup: fresh external Git worktree because the app worktree tool targets the
  current diet project, not this repository. No remote mutation.
- Plan: permissions/concurrency; capture/revisions; reader/questions; workbench;
  local model setup; deterministic and live verification; independent review.
- Implemented: explicit ownership, whole-story grants, reviewed imports,
  pending/confirmed memory relations, reader requests, filtered portraits,
  generation/search publication checks and the local workbench.
- Ruling: reuse existing IMPORT rather than invent WEB_MIC; capture metadata
  identifies the local workbench. Cost: clients needing a new capture enum must
  propose it separately. Existing legacy Android review policy is not silently changed.
- Ruling: local identities are provisioned by an operator, not public signup;
  credentials live in ignored var/. Cost: no account recovery or production auth.
- Ruling: reader views derive directly from visible memories, not owner profiles.
  Cost: conservative first-release views rather than a richer personality model.
- Ruling: a story containing superseded memory is hidden from readers as a whole;
  cost: coarse sharing until a later segment-level policy is designed.
- Baseline 39 relevant tests passed before implementation. New tests first
  reproduced self-authorization, absent sharing and stale in-flight answers.
- Independent review reproduced legacy ownership bypass, search/revoke race,
  late frontend responses, pending legacy revisions and temporal contradictions;
  all addressed, with 16 regression cases plus browser identity checks passing.
- Backend full suite: 260 passed; AI Core: 133 passed. POSIX-only permission bit
  assertions are conditional on POSIX; Windows file I/O still runs.
- Real adapters: Whisper v1.9.2 + multilingual base and pinned BGE encoder ran.
  Real browser imported synthetic speech, corrected transcription and played
  original audio. This is not a human microphone or mobile acceptance result.
- BLOCKED: no DeepSeek API key; cloud extraction, Twin quality and calibration
  live acceptance remain open. No fake fallback. See docs/agent-loop/ACCEPTANCE.md.
