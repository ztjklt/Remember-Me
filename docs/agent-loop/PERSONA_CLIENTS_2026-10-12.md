# Persona local clients, 2026-10-12

Local changes in `codex/twin-a01-local-20261012`. This slice changes Android and
the existing companion web page. It does not change backend/AI Python, create a
commit or PR, push, deploy, or touch ECS. The later integration instruction
authorized installing the local debug APK and reading the existing emulator.

## Available client flows

- Android keeps the garden and senior simple mode. `档案 → 人物` starts with
  one confirmed-understanding card with a three-line summary, horizontal paging
  and a page counter. Its detail view preserves the full statement, situation,
  support and exceptions, leaving the person views usable on the first screen. `档案 → 亲友` opens signed contributions and
  dedicated letters; simple mode offers the same entry below its story content.
- `对话` / web `聊一聊` offers evidence and persona modes. Persona follows the
  existing owner narrative/style preference. Answers show a concise AI 分身 label
  and expandable understanding, story evidence and attributed contributions.
- `听这条回答` sends the saved answer ID to the speech endpoint, then downloads its
  returned audio asset. No client-created text is sent to a speech provider.
- Owner voice settings explicitly create a VOICE consent before activating the
  configured fictional preset. Reader voice permission is changed separately for
  each already known recipient. The owner can separately stop the voice consent.
  Story sharing does not silently enable voice.
- Contributions support native microphone capture or audio file selection, durable
  local Android audio drafts, upload, separate cloud transcription permission,
  original ASR text, editable reviewed text, and optional story links. Submission
  keeps server-controlled authorship. Owner review, explicit recipients, model use
  and withdrawal are distinct actions. Model use requires author and owner opt-in.
- Letters can attach their own reviewed audio. Draft text remains editable while
  retaining the attached audio and fixed recipient. They save as private drafts and
  require an explicit send action naming the recipient. Published/revoked text
  and audio follow server authorization. The web retains draft editing and sealed
  snapshots; this native slice does not add native snapshot management.
- Android owner answers offer `和我的想法对照`: lock the saved answer, record or
  import a separate human audio file, upload it with `metadata.calibration_id`,
  review the real ASR transcript, then compare. Imported originals retain their
  format and use `source=IMPORT`; recording uses `ANDROID_MIC`. History loads real
  saved comparisons, showing the five dimensions, human excerpts and a suggested
  next question. The person-view link leaves candidate confirmation explicit.
  This calibration addition is native; the companion web page has no new
  calibration editor.
- Daily UI no longer displays technical review badges, source IDs, model hashes
  or version badges. The web keeps one fictional-space label. Source details
  remain available as readable text, situation and story links.

## API wiring

All paths below have `/api/v1` prefix:

| Action | Shared API |
| --- | --- |
| Discovery | Merge `/workbench/spaces` with `/companion/spaces`; preserve owner role |
| Dialogue | `POST /subjects/{s}/twin/answers` with `question,cloud_consent_id,mode` |
| Style | `PUT /workbench/subjects/{s}/narrative/style` with `enabled,revision` |
| Saved answer validity | `GET /subjects/{s}/twin/answers/{answer_id}` |
| Speech | `POST /subjects/{s}/twin/answers/{answer_id}/speech`, then `GET /subjects/{s}/voice/assets/{asset_id}/audio` |
| Preset | `GET /subjects/{s}/voice/profile`, then explicit consent and `POST /subjects/{s}/voice/profile/synthetic` with `preset:a01,voice_consent_id` |
| Reader voice | Owner `GET/PUT /subjects/{s}/voice/recipients/{actor}`; PUT `enabled` |
| Companion audio | Multipart `POST /workbench/subjects/{s}/companion/audio`: `purpose,file,idempotency_key` |
| ASR | GET audio policy, then `POST .../audio/{id}/transcribe` with `cloud_asr_policy` |
| Audio review/play | `PUT .../audio/{id}/review` with `revision,text`; `GET .../audio/{id}/content` |
| Contributions | Existing create/review/recipient/withdraw routes; create adds `audio_id,narrative_ids` |
| Model use | `PUT .../contributions/{id}/model-use` with `revision,allowed`; separate owner/author response flags |
| Letters | Existing draft/publish/revoke routes, with optional dedicated `audio_id` |
| Calibration | Owner `GET/POST /subjects/{s}/calibrations`, GET `/{id}`, POST `/{id}/complete`; explicit `cloud_consent_id` |
| Human calibration audio | Normal Episode multipart with `metadata.calibration_id`; original ASR/transcript review is unchanged |

Android treats absent companion endpoints as unavailable so existing services can
still load the established stories UI. It does not fabricate substitute answers.
Identity/space changes reject late network responses. Backgrounding stops private
playback. Permission refreshes recheck saved answers and clear changed content.

## Verification actually run

- `testDebugUnitTest assembleDebug assembleDebugAndroidTest`: **90 tests, 0 failures, 0 errors** across
  21 suites; successful after the calibration and horizontal-card additions. Includes dedicated multipart
  transport with stable retry keys, no Episode upload, confirmed audio attachment
  gate, both model-use permissions, companion-only discovery, understanding status
  filtering, local audio draft restoration, and calibration import metadata /
  original-audio retention across repeated multipart requests. Existing native tests also ran.
- `node services/backend/tests/test_companion_frontend.cjs`: **26 passed**.
- `node services/backend/tests/test_persona_companion_frontend.cjs`: **22 passed**.
  These use browser HTTP fixtures. They cover persona mode, ordering, technical
  badge removal, saved-answer speech, stale answer removal, separate voice grants,
  dedicated audio upload/transcribe/review, source link submission, distinct model
  use, private audio letter publication and a 412 × 915 viewport without overflow.
- `node --check services/backend/app/workbench/companion.js` and Android
  `git diff --check` passed.

APK: `apps/android/app/build/outputs/apk/debug/app-debug.apk`.
Generated debug BuildConfig was verified as `http://10.0.2.2:8891` for the Android
emulator's host loopback; no ADB reverse is needed. Existing `internal` distribution
still points at its established ECS HTTPS URL. The APK is a local debug artifact,
not a published upgrade.

## Boundaries still requiring integration evidence

The tests do not establish ASR/model/voice quality, a live microphone-to-provider
round trip, or accessibility at every text scale. The real emulator checks below
cover current API login, navigation and native playback only. Android audio drafts
are stored privately by server, actor and subject; web audio drafts remain within
the page session. Neither is a background recording/upload service.

### Native live attempt and local connectivity

The existing `emulator-5554` was already running with font scale 1.0. Its old
`me.remember.app` package was updated with `adb install -r`; no uninstall or data
wipe occurred. A new `PersonaReadOnlyLiveTest` logs into the actual local service
and reads pages only. Credentials are streamed from the ignored private account
file into app-private storage, consumed and deleted, never printed.

The first login timed out because the running emulator had inherited the host
HTTP proxy; host Xray was attempting to reach literal `10.0.2.2`. Clearing the
emulator console proxy was insufficient. The same AVD was closed, then cold
started with proxy variables removed only from its process environment. Userdata
was preserved, no duplicate emulator was started, the global proxy was unchanged,
and no ADB reverse was used.

Direct requests then exposed two separate local-backend checks: the Host allowlist
and the accounts HTTP loopback rule. Parent integration fixed and restarted the
local service; the final APK connects directly to `http://10.0.2.2:8891`.

Both real owner and reader logins passed at font scale 1.0. The initial readback
contained 10 owner stories, 9 reader stories, three confirmed understandings each,
style enabled, and an available voice profile. The tests submit no question, content,
grant or voice-setting mutation. These are actual 陈国梁 pages, not old 陈守义
cache, overlay or fixture screens. The final carousel screenshot set and logs live
under `services/backend/var/a01-20261012/persona-android/`.

After companion integration changed the source basis, the earlier P01/P04 speech
assets became stale. They were not reused as current speech. The existing dedicated
letter audio was instead fetched through the authorized companion-content GET and
played by the native MediaPlayer for both roles; instrumentation requires a positive
duration and active playing state. This proves the device playback path, not voice
similarity or subjective audio quality. Real saved-answer and completed-calibration
read-only checks are optional inputs to `PersonaReadOnlyLiveTest`; they never invoke
a model or synthesize new audio.

### Completed real calibration readback

The owner logged in again and read `cal_33d058e9471d455d` through the live API.
The final instrumentation passed in 28.2 seconds and asserted `complete` with
five dimensions. `owner-calibration/` contains the frozen old answer, comparison
summary, and five native screenshots with each dimension's note and human excerpt.
The test did not record audio, submit a comparison, or apply a profile update.
At this later source state, the real API returned 11 stories and zero currently
confirmed understandings; the earlier three-card screenshots remain explicitly
the baseline capture. Nothing was re-confirmed to preserve the earlier display.

### Real native contribution write acceptance

After explicit coordinator authorization, the existing immutable companion WAV
(SHA-256 `d7c9bf169a2d9e63decd5c1ab5faf889d70061fd8da30531150e78ed7d30527a`)
was imported through the production native model, then uploaded, transcribed by
Paraformer, confirmed, attached and submitted through real Compose controls.
The import uses the same callback as the picker; no Android picker or microphone
interaction is claimed. Account login and every response came from local 8891.

Two initial failures are preserved. ADB stdin truncated the binary WAV and failed
the device hash check before upload. A byte-preserving push/copy then passed.
After submission, the author permission checkbox was actionable while pending,
but the API correctly rejected it. Android and web now disable that control until
accepted or retained as a disagreement. The same note continued after owner review;
no duplicate audio, ASR, note, or provider question was created.

Real IDs: audio `ca_465998d293b74e7f955d`, note `cc_0a40163d1c3d4481b2d1`.
Owner acceptance and owner permission succeeded, then the author separately opted
in. The actual transcript was automatically confirmed unchanged for transport
acceptance, not human listening review: it contains `陈国良` and a problematic
`用没有，马上扔掉` sentence boundary. This run does not certify transcription quality.

The one specified persona question, “亲友这次署名补记的原话是什么？请区分这是谁的记录。”,
used the production model with explicit mode and consent. It returned “模型回答未通过
来源或格式校验，本次未保存答案。” and no saved answer; no speech was generated.
The screenshot shows the actual error state, but the question was a model action,
not a filled form click. The parent observed a semantic-review discrepancy in the
provider draft; neither the compound question nor this simpler case is claimed fixed.

The author then withdrew the same note via the native confirmation dialog. The
owner view returned withdrawn with no text or audio ID. Independent authenticated
GETs for both owner and author returned 404 for that audio content. Evidence is in
`persona-android/native-write-byte-preserved/`, alongside the original failure logs.
`PersonaCompanionWriteLiveTest` and `apps/android/scripts/PERSONA_COMPANION_LIVE.md`
document phase-by-phase execution and explicit recovery without repeat writes.

The final debug APK version is `0.9.3-internal-persona-local-20261012`, SHA-256
`1071f195973b5f3f46c21421b6e5e3defa676215102b05eaea58b34a88771062`.
After the pending-state fix, all 91 Android unit tests in 21 suites passed,
debug plus androidTest APK builds passed, and 23 persona companion browser fixture
checks passed. The internal release URL and version configuration are unchanged.

### Final saved-answer playback

After all source mutations finished, owner and reader each logged in and passed
the read-only native test at font scale 1.0. Both had two current confirmed
understandings; owner had 11 recordings and reader 10. The native MediaPlayer
fetched and played the actual saved assets (positive duration and playing state):

- Owner: answer `ta_c9a039fe7a8e46bc`, asset `va_d13a9eec5bff4799`, displayed 51 seconds.
- Reader: answer `ta_5e2f865823a845c2`, asset `va_794604bb8fd4442c`, displayed 27 seconds.

`persona-android/final-owner/` and `final-reader/` contain only this final run's
screenshots and results. `08-native-saved-persona-answer.png` shows actual answer
text; `09-native-saved-voice-playing.png` shows native playback. The owner full
answer includes the new electrical-safety qualification. The test used existing
answer/asset GETs only, with zero new questions, synthesis or content mutations.
This verifies the playback path, not a human voice-similarity judgement.

The owner test captured `13-final-owner-person.png` before instrumentation ended.
On a later app-reopen attempt, a separate interaction-gallery run owned the
foreground. Navigation stopped immediately; no confirmation was clicked. That
unrelated capture is excluded as `persona-android/excluded-interaction-gallery.png`
and is not final product evidence. The deliverable is an operable local APK with
completed two-role acceptance; no claim is made about the emulator's current page.
