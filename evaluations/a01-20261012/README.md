# A01 local evaluation

This is explicitly fictional test material. `input/episodes.json` contains only
the ten permitted spoken paragraphs. `input/questions.json` contains questions
without reference answers. The model runner does not open `reference-only/`.
This separation is a code/data boundary, not a claim of an OS security sandbox.

`results.json` and `results.html` display actual extracted memories, original
evidence, three cumulative profile snapshots, accepted/rejected answers, model
review, separate evaluator findings, call metadata and fresh synthetic audio.
Every profile remains pending technical review. Text baseline is not ASR.

Private runtime artifacts and immutable WAVs are kept under ignored
`services/backend/var/a01-20261012/evaluation/`. No provider key is in this corpus.
Reference gold is only for offline evaluation and is never copied into requests.

Run from the repository root with the existing backend Python:

```powershell
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m unittest tools.a01_eval.test_isolation tools.a01_eval.test_run_safety
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.prepare
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.run_baseline --stage all
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.run_baseline --stage qa-early
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.speech
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.export_results
```

Completed and failed checkpoints are reused; a started checkpoint blocks silent
duplicate calls. Do not delete checkpoints to disguise retries. Model transport
is serial, 45 seconds per request, at most three transient attempts; schema and
semantic failures are not retried. This baseline directly reuses strict
extraction/profile validators and the quote selection/render/review primitives;
it intentionally disables the production Twin's draft repair/replacement pass.
That makes the two first-pass failures visible instead of correcting them away.
