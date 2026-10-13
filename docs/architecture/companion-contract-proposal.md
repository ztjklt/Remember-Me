# A01 companion additive contract

Authorized locally by A01_NIGHT_SPEC_2026-10-12. Base path:
`/api/v1/workbench/subjects/{subject_id}/companion`. Authentication is the existing
server-resolved Actor; names never identify family or recipients. These side records
do not feed canonical Memory, ProfileCandidate, Twin, or voice learning.

`GET /api/v1/companion/spaces` is a separate discovery router. It returns
`{"items":[{"subject_id":"...","display_name":"...","role":"companion"}]}` for
active contribution permissions, explicitly shared accepted/disagreement notes,
published exact-recipient letters, or valid named snapshots with live source access.
Clients merge this with existing owner/story space discovery. It adds no permission
to any Episode, story, private profile, or canonical memory. Revoking the only side
access removes that space from this discovery response; private drafts never add it.

## Contribution permission and signed notes

- `GET /contribution-grants`: owner sees grants; others see only their own grant.
- `PUT /contribution-grants/{actor_id}`: owner body `{"revision":0,"enabled":true}`
  creates revision 1. Existing grants require current revision. Revocation uses
  `enabled:false`; it blocks new notes, independently of StoryGrant reading.
- `POST /contributions`: `{"idempotency_key":"note-1","classification":"firsthand",
  "text":"I was there."}`. Classification is firsthand/reported/opinion; the server
  fixes author_actor_id and source_type THIRD_PARTY. author_display_name is the
  current account label; immutable actor ID defines authorship. Active contribution
  permission is required. Pending text is visible only to owner and its author.
- `GET /contributions`, `GET /contributions/{id}`: owner, author, or explicitly named
  recipients of accepted/disagreement notes. No inherited subject-wide sharing.
- `POST /contributions/{id}/review`: owner `{"revision":1,"decision":"accepted"}`;
  accepted/rejected/disagreement preserves original author, classification and text.
- `PUT /contributions/{id}/recipients`: owner `{"revision":2,
  "recipient_actor_ids":["actor_existing"]}` explicitly shares accepted/disagreement
  text; an empty list revokes sharing. Review changes clear recipients.
- `POST /contributions/{id}/withdraw`: author or current owner `{"revision":3}`.
  Terminal withdrawal hides text on all reads, including old links; owner retains
  metadata. Grant revocation alone does not retract existing signed notes.

## Dedicated text letters

- `POST /letters`: owner `{"idempotency_key":"letter-1","recipient_actor_id":
  "actor_existing","title":"For you","text":"Private message"}` creates a draft.
- `PUT /letters/{id}`: owner same content fields plus `revision`, only while draft.
- `POST /letters/{id}/publish`: owner `{"revision":1,"confirmed":true}` explicitly
  publishes the fixed recipient and text. False confirmation is rejected.
- `POST /letters/{id}/revoke`: owner `{"revision":2}` is terminal.
- `GET /letters`, `GET /letters/{id}`: owner inspects own draft/published history;
  only exact recipient reads published letters. Revocation blocks old links.
  No audio attachments are accepted; text letters grant no Episode access.

## Explicit sealed snapshots

- `POST /snapshots/preview`: owner `{"narrative_ids":["nr_..."],
  "profile_candidate_ids":[],"recipient_actor_ids":["actor_existing"]}` returns
  `source_version` and selected confirmed, currently valid items. Recipients must
  already have live source StoryGrants for every evidence Episode.
- `POST /snapshots`: preview body plus `idempotency_key`, `source_version`,
  `confirmed:true`. A source change returns SOURCE_CHANGED (409). Stores immutable
  content, source IDs/fingerprints, narrative revision/profile basis, model/prompt
  version, author, selected recipients, and explicit readonly/sealed state.
- `GET /snapshots`, `GET /snapshots/{id}` rechecks current source state and source
  grants for each item. Narrative recipient fingerprints must match the complete
  contextual narrative evidence, including visibility of linked change Episodes.
  Profile items use profile_updates.valid_snapshot and its canonical raw-evidence
  fingerprint protocol for both owner validity and recipient authorization.
  Stale/deleted/unreviewed/revoked items have no text in the
  response. Owners can inspect historical metadata with `source_valid:false`;
  recipients get only valid authorized items, or 404 if none. Unrelated later chat
  does not rewrite stored snapshots. Existing profile validity rules still apply.
- `POST /snapshots/{id}/revoke`: owner `{"revision":1}` blocks recipient access.
  No endpoint edits sealed content or recipients; create a new version instead.

Responses include id, subject_id, author_actor_id, source_type, revision, status,
visibility, created/updated timestamps, and resource-specific source references.
Collections return `{"items":[...]}`. `GET` at the base path returns role,
contribution_grants/contributions/letters/snapshots, without exposing unrelated
subject source material. Creation retries with the same actor/key/body are safe;
different bodies return IDEMPOTENCY_CONFLICT (409). Mutations use a short publication
lock and compare revisions; exact immediate action retries are idempotent while
older/conflicting revisions return SOURCE_CHANGED (409). No external calls.

This is a user-selected read-only version, not subject-wide freeze, death detection,
automatic activation, legal inheritance or an authorization to answer medical
decisions. SQLite migration is tested locally; PostgreSQL runtime is reported
separately rather than inferred from portable schema definitions.

## Local verification, 2026-10-12

Task implementation is isolated to companion_models.py, api/companion.py,
0017_companion.py, test_companion.py and this proposal. Integration owns main.py
router registration and migration table expectations. Initial delivery had 13 deterministic
companion tests. Initial 7 permission/state tests were run red before implementation;
2 later discovery tests were likewise red then green. Four additional source/edit/
migration tests strengthen established behavior rather than claiming a new failing
regression. Final command from services/backend:

```text
D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe -X utf8 -m pytest tests/test_companion.py tests/test_narrative.py tests/test_sharing_invitations.py tests/test_migrations.py -o addopts='' -q
50 passed, 2 warnings in 57.30s
```

Logs are retained under ignored services/backend/var/a01-20261012/companion/:
red.log, green-2.log, discovery-red.log, discovery-green.log, final-regression.log.
Two existing Starlette/httpx dependency deprecation warnings remain. SQLite upgrade,
downgrade to 0016 and re-upgrade, column parity, and whole migration regression passed.
Only PostgreSQL DDL compilation ran; no live PostgreSQL test or external call occurred.
No commit, push, PR, publish or deployment was performed by this implementation task.

Ruling: contribution grant revocation prevents new submissions but does not retract
already accepted signed text; explicit withdrawal/share revocation controls that
separate content. Ruling: discovery includes explicitly shared signed notes, because
their named recipients otherwise could not discover authorized text; it confers no
story permission. Snapshot validity uses existing confirmed narrative/profile source
rules; later source changes can hide old content while immutable stored content remains
available only as historical metadata. No full-space freeze or Twin learning is claimed.

Independent review then found two defects, reproduced before fixes: real API-confirmed
profiles were rejected due to mixing raw and contextual fingerprints, and narrative
snapshot recipients could retain text whose contextual fingerprint depended on a
revoked private change Episode. Profile sealing now reuses the canonical profile
validation function; narrative preview/read now checks the recipient's full contextual
fingerprint. Tests exercise direct and ADD-update confirmation APIs, later source
changes, grant revocation, and public-old/private-change narrative visibility. The
earlier profile fixture was corrected to confirm through the real API rather than
fabricate saved fingerprints. Protocol/privacy red and green logs are retained beside
the initial evidence. The expanded companion suite contains 18 deterministic tests.

Review-fix final command added tests/test_profile_updates.py to the earlier focused
regression: **65 passed, 2 warnings in 72.62s**. Its complete output is retained in
services/backend/var/a01-20261012/companion/review-final-regression.log. PostgreSQL
runtime, external model/provider execution and device verification are still separate.
