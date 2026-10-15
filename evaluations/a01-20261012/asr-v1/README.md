# Fresh audio / actual ASR follow-up

`results.json` and `comparison.html` contain the ten actual Paraformer machine
transcripts from the new A01 Xiaomi WAVs, beside the creative scripts. No script
or gold was supplied to ASR. Raw ASR is not corrected or overwritten; manual
audio listening remains pending. This is synthetic audio, not a real speaker.

The earlier text baseline `../results.json` is preserved unchanged, including
its original historical ASR-blocked status. Use this directory for the later
actual ASR stage. The subsequently approved fixed seven-task small comparison
is in `model-retest.json` / `model-retest.html`, separately from the raw-ASR
comparison. Six selected QA tasks passed, but four of eight profile candidates
need correction; every profile remains unconfirmed.

Runtime/state: `services/backend/var/a01-20261012/evaluation/asr-paraformer-v1/`.
Secrets remain separately ACL-protected in the ignored `private/` directory.

Existing backend Python commands, repository root:

```powershell
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.asr
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.asr --remaining
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.compare_asr
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.retest_asr
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m tools.a01_eval.export_retest
```

Saved transcript checkpoints are reused. Unknown provider submission status
uses the existing adapter's refusal/resume rules; never delete state just to
start a duplicate paid task. The diff ratio includes number formatting and does
not establish ASR accuracy, since synthetic audio was not manually transcribed.
