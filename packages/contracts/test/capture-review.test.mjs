import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const schema = JSON.parse(fs.readFileSync(new URL('../schemas/capture-review-v1.schema.json', import.meta.url)));
const ajv = new Ajv({strict: false});
addFormats(ajv);
ajv.addSchema(schema);
const check = (name, value) => ajv.getSchema(`${schema.$id}#/$defs/${name}`)(value);
const policy = 'asr-proofread-v1:' + 'a'.repeat(24);
const edit = {before: '电击', after: '电机', start: 3, end: 5, category: 'word', action: 'auto', reason: '语境明确的近音词'};
const result = {draft: '以前修电机。', input_sha256: 'a'.repeat(64), model_version: 'fixture-model', prompt_version: 'asr-proofread-v1', edits: [edit]};
const completed = {status: 'completed', ...result, completed_at: '2026-10-16T12:00:00Z', elapsed_ms: 120};

test('capture review preserves legacy states and distinguishes original, correction and supplement', () => {
  assert(check('transcriptReview', {state: 'reviewing', transcript: '旧客户端核对稿。', stt_model_version: null}));
  assert(check('transcriptReview', {state: 'reviewing', transcript: result.draft, machine_transcript: '以前修电击。',
    supplement: '这是本人书面补充。', stt_model_version: 'fixture-stt', automatic_correction: completed}));
  for (const state of ['transcribing', 'submitted', 'not_required']) {
    assert(check('transcriptReview', {state, transcript: null, stt_model_version: null, supplement: '', machine_transcript: null, automatic_correction: null}));
  }
  assert(!check('transcriptReview', {state: 'ready'}));
  assert(!check('transcriptReview', {state: 'reviewing', machine_transcript: 42}));
  assert(!check('transcriptReview', {state: 'reviewing', reviewed: true}));
});

test('one-save request remains optional-consent compatible and bounds transcript and supplement', () => {
  assert(check('confirmTranscript', {transcript: '本人核对的原话。'}));
  assert(check('confirmTranscript', {transcript: '本人改稿。', supplement: '独立补充。', cloud_analysis_consent_id: 'consent-current'}));
  assert(check('confirmTranscript', {transcript: '本人改稿。', supplement: '', cloud_analysis_consent_id: null}));
  assert(check('confirmTranscript', {transcript: '字'.repeat(100000), supplement: '字'.repeat(3000)}));
  for (const value of ['', '   ', '\n\t', '字'.repeat(100001)]) assert(!check('confirmTranscript', {transcript: value}));
  assert(!check('confirmTranscript', {transcript: '原话', supplement: '字'.repeat(3001)}));
  assert(!check('confirmTranscript', {transcript: '原话', supplement: null}));
  assert(!check('confirmTranscript', {transcript: '原话', cloud_analysis_consent_id: ''}));
  assert(!check('confirmTranscript', {transcript: '原话', cloud_analysis_consent_id: 'a'.repeat(65)}));
  assert(!check('confirmTranscript', {transcript: '原话', automatic_profile: {status: 'complete'}}));
});

test('successful automatic correction carries exact source identity and all result fields', () => {
  assert(check('correctionResult', result));
  assert(check('automaticCorrection', completed));
  assert(!check('automaticCorrection', {status: 'completed'}));
  assert(!check('correctionResult', {...result, input_sha256: 'not-a-source-hash'}));
  assert(!check('correctionResult', {...result, prompt_version: 'unversioned'}));
  assert(!check('correctionResult', {...result, draft: '字'.repeat(20001)}));
  assert(!check('correctionResult', {...result, edits: Array(65).fill(edit)}));
  assert(!check('automaticCorrection', {...completed, completed_at: 'yesterday'}));
  assert(!check('automaticCorrection', {...completed, elapsed_ms: -1}));
  assert(!check('automaticCorrection', {...completed, provider_api_key: 'not-a-client-field'}));
});

test('uncertain names numbers and meaning require human review instead of automatic replacement', () => {
  for (const category of ['name', 'number', 'meaning']) {
    assert(check('correctionEdit', {...edit, category, action: 'review'}));
    assert(!check('correctionEdit', {...edit, category, action: 'auto'}));
  }
  assert(check('correctionEdit', {...edit, category: 'punctuation', after: ''}));
  assert(!check('correctionEdit', {...edit, start: 0.5}));
  assert(!check('correctionEdit', {...edit, start: -1}));
  assert(!check('correctionEdit', {...edit, end: 0}));
  assert(!check('correctionEdit', {...edit, before: ''}));
  assert(!check('correctionEdit', {...edit, action: 'apply-all'}));
  assert(!check('correctionEdit', {...edit, source_type: 'SUBJECT'}));
});

test('failed unavailable and too-long correction reports never introduce replacement text', () => {
  for (const status of ['failed', 'unavailable', 'too_long']) {
    assert(check('automaticCorrection', {status}));
    assert(check('automaticCorrection', {status, completed_at: '2026-10-16T12:00:00+00:00', elapsed_ms: 0}));
    assert(!check('automaticCorrection', {status, draft: '无依据替换'}));
    assert(!check('automaticCorrection', {status, edits: []}));
    assert(!check('automaticCorrection', {status, error: 'private upstream response'}));
  }
  assert(!check('automaticCorrection', {status: 'ready'}));
});

test('cumulative analysis status exposes progress or fixed error without private job authority', () => {
  assert(check('cumulativeAnalysis', null));
  for (const status of ['waiting_for_memories', 'authorization_required', 'queued', 'running', 'complete', 'failed']) {
    assert(check('cumulativeAnalysis', {status, error: null}));
  }
  assert(check('cumulativeAnalysis', {status: 'failed', error: '分析暂未完成，可稍后重试。'}));
  assert(!check('cumulativeAnalysis', {status: 'confirmed'}));
  assert(!check('cumulativeAnalysis', {status: 'complete', consent_id: 'private-grant'}));
  assert(!check('cumulativeAnalysis', {status: 'queued', job_id: 'internal-job'}));
  assert(!check('cumulativeAnalysis', {status: 'complete', candidate_confirmed: true}));
});

test('episode and story increments compose with existing lists while keeping nullable reader fields', () => {
  assert(check('episodeCaptureFields', {episode_id: 'ep', status: 'ready'}));
  assert(check('episodeCaptureFields', {episode_id: 'ep', cumulative_analysis: {status: 'running', error: null}}));
  assert(check('episodeCaptureFields', {episode_id: 'ep', status: 'transcribing', waiting_for_review: true}));
  assert(check('episodeCaptureFields', {episode_id: 'ep', status: 'transcribing', waiting_for_review: false}));
  assert(check('storyCaptureFields', {episode_id: 'ep', memories: [], machine_transcript: null, cumulative_analysis: null}));
  assert(check('storyCaptureFields', {episode_id: 'ep', machine_transcript: '机器原稿。', cumulative_analysis: {status: 'complete', error: null}}));
  assert(!check('episodeCaptureFields', {cumulative_analysis: {status: 'ready'}}));
  assert(!check('episodeCaptureFields', {waiting_for_review: 'true'}));
  assert(!check('episodeCaptureFields', {waiting_for_review: null}));
  assert(!check('storyCaptureFields', {machine_transcript: false}));
});

test('episode review readiness is additive and does not replace the processing status enum', () => {
  assert.equal(schema.$defs.episodeCaptureFields.required, undefined);
  assert.deepEqual(schema.$defs.episodeCaptureFields.properties.waiting_for_review, {type: 'boolean'});
  assert(check('episodeCaptureFields', {episode_id: 'legacy-episode', status: 'transcribing'}));
  assert(check('episodeCaptureFields', {episode_id: 'reviewable-episode', status: 'transcribing', waiting_for_review: true,
    cumulative_analysis: null}));
});

test('capture capability version and policy explicitly control opt-in', () => {
  assert(check('capabilities', {automatic_capture_version: 1, automatic_profile_analysis: true, transcript_correction_policy: policy, stt: 'existing-field'}));
  assert(check('capabilities', {automatic_capture_version: 1, automatic_profile_analysis: true, transcript_correction_policy: null}));
  assert(!check('capabilities', {automatic_capture_version: 2, automatic_profile_analysis: true, transcript_correction_policy: policy}));
  assert(!check('capabilities', {automatic_capture_version: 1, automatic_profile_analysis: 'true', transcript_correction_policy: policy}));
  assert(!check('capabilities', {automatic_capture_version: 1, automatic_profile_analysis: true}));
  assert(!check('capabilities', {automatic_capture_version: 1, automatic_profile_analysis: true, transcript_correction_policy: 'approved'}));
});

test('upload opt-in composes with capture metadata and cannot mint server receipts', () => {
  assert(check('uploadMetadataFields', {}));
  assert(check('uploadMetadataFields', {transcript_correction_policy: policy, cloud_asr_policy: 'independent-existing-policy'}));
  assert(!check('uploadMetadataFields', {transcript_correction_policy: null}));
  for (const field of ['transcript_correction_receipt', 'automatic_correction', 'automatic_profile']) {
    assert(!check('uploadMetadataFields', {transcript_correction_policy: policy, [field]: {status: 'completed'}}));
  }
});
