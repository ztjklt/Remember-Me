import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const schema = JSON.parse(fs.readFileSync(new URL('../schemas/guest-access-v1.schema.json', import.meta.url)));
const ajv = new Ajv({strict: false});
addFormats(ajv);
ajv.addSchema(schema);
const check = (name, payload) => ajv.getSchema(`${schema.$id}#/$defs/${name}`)(payload);
const source = {episode_id: 'ep-open', recorded_at: '2026-10-16T08:00:00Z', duration_ms: 12000,
  transcript: '同一段原音中的两件事。', supplement: '', memories: ['故事一', '故事二'], has_audio: true};
const session = {session_id: 'gs-example', subject_id: 'subject-example', subject_label: '家人',
  expires_at: '2026-10-16T09:00:00Z', revision: 1, personal_voice_available: false,
  cloud_asr_policy: null, speech_notice: '语音仅用于本次交流。', default_voice_available: true,
  spoken_question_available: true};

test('whole-source preview carries the transcript and all related memories', () => {
  const preview = {source_version: 'snapshot', episode_ids: ['ep-open'], includes_full_audio: true,
    notice: '确认将开放完整原音、全文和相关记忆。', items: [source]};
  assert(check('preview', preview));
  assert(!check('preview', {...preview, includes_full_audio: false}));
  assert(!check('source', {...source, owner_profile: 'private'}));
  assert(!check('preview', {...preview, items: [{episode_id: 'ep-open', memories: ['只显示标题']}]}));
});

test('publication requires an explicit preview version and separate voice choice', () => {
  assert(check('publicationRequest', {episode_ids: ['ep-open'], source_version: 'snapshot', enabled: true,
    personal_voice_enabled: false}));
  assert(!check('publicationRequest', {episode_ids: ['ep-open'], enabled: true, personal_voice_enabled: false}));
  assert(!check('publicationRequest', {episode_ids: [], source_version: 'snapshot', enabled: 'yes',
    personal_voice_enabled: false}));
  assert(check('publicationRequest', {episode_ids: [], source_version: 'snapshot', enabled: false,
    personal_voice_enabled: false}));
  assert(!check('previewRequest', {episode_ids: ['ep-open', 'ep-open']}));
  assert(!check('previewRequest', {episode_ids: Array.from({length: 31}, (_, i) => `ep-${i}`)}));
});

test('guest session creation and status do not expose an owner credential or provider ID', () => {
  assert(check('session', session));
  assert(!check('createdSession', session));
  assert(check('createdSession', {...session, session_token: 's'.repeat(48)}));
  assert(!check('session', {...session, actor_token: 'owner-secret'}));
  assert(!check('session', {...session, provider_voice_id: 'vendor-voice'}));
  assert(!check('sessionRequest', {entry_token: 'e'.repeat(48), subject_id: 'another-person'}));
  assert(!check('sessionRequest', {entry_token: 'short'}));
});

test('guest questions cannot request capture, training, owner history or another scope', () => {
  const question = {question: '然后呢？', request_id: 'turn-two', previous_answer_id: 'guest-answer-one'};
  assert(check('question', question));
  for (const field of ['remember', 'training', 'actor_id', 'subject_id', 'allowed_episode_ids', 'voice_consent_id']) {
    assert(!check('question', {...question, [field]: true}), field);
  }
  assert(!check('question', {question: 'x'.repeat(1001)}));
  assert(!check('question', {question: ''}));
  assert(!check('question', {question: '   '}));
});

test('ending a visit and password verification have narrow dedicated shapes', () => {
  assert(check('ended', {ended: true}));
  assert(!check('ended', {ended: false}));
  assert(check('reauthRequest', {password: 'owner-password'}));
  assert(!check('reauthRequest', {password: 'owner-password', actor_id: 'another-owner'}));
  assert(!check('reauthRequest', {password: 'short'}));
  assert(check('garden', {subject_id: 'subject-example', subject_label: '家人', revision: 1, items: [source]}));
});
