# Persona implementation ledger

Baseline: a12354a with the preserved uncommitted A01 iteration, existing checkout
codex/twin-a01-local-20261012. User authorized implementation, no GitHub push.

Tasks: (1) shared valid person context and persona worker; (2) companion audio and
attributed model use; (3) synthetic voice delivery; (4) Android and web product UI;
(5) local migration, regression, real-model and emulator acceptance.

Pre-flight: public contracts are in persona-dialogue-contract-20261012.md. Parent
owns migration 0018/main/Twin; voice owns 0019. Independent agents have disjoint
files; no worker may deploy, push, restart shared services or spawn reviewers.

Ruling: keep the existing dirty checkout rather than creating a clean worktree,
because it contains the preceding accepted local iteration. Preserve those files
and compare new edits separately; cost if wrong is more difficult diff review.

Ruling: contribution model use requires explicit permission beyond accepting or
sharing text; old contributions default off. This prevents silently transmitting
third-party text under an unrelated story grant.

Status: local implementation and real integration performed. Main results are in
PERSONA_LOCAL_RESULTS_2026-10-12.md; do not infer ECS or released-APK state from
these records. Source snapshot remains a12354a plus preserved local changes.

- Shared person context, opt-in persona dialogue, both-party contribution model
  consent, dedicated audio review and letters, synthetic voice grants, and current
  answer/audio validation are implemented. Migrations 0018 through 0020 applied
  locally after SQLite backups; existing 0017 companion work retained.
- A real owner calibration was locked before a later fictional audio was generated.
  Actual Paraformer text and DeepSeek extraction were stored. The difference report
  did not change profiles. Explicit CHANGE then made same-question and paraphrase
  answers include the new condition. Sharing the new Episode was separately explicit.
- The full backend suite passed 552 tests, with six PostgreSQL probes skipped. AI
  v5 passed 376. Android unit/build and web fixture results are documented separately.
- The fixed initial 18-question real run remains unchanged: 13 delivered / five
  failed; developer textual review 10 met / three partial / five undelivered. Real
  companion compound-query failures v3-v5 also remain; cannot be called fixed.
- Final Android write/play evidence and audio/APK delivery are indexed in the result
  document. Native import is not claimed as a physical microphone test.

No secrets, databases, synthetic audio or temporary provider drafts were added to
tracked release files; artifacts remain under ignored var. No Git push or deployment.
