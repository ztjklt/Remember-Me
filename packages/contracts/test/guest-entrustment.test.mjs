import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const schema = JSON.parse(fs.readFileSync(new URL('../schemas/guest-entrustment-v1.schema.json', import.meta.url)));
const guest = JSON.parse(fs.readFileSync(new URL('../schemas/guest-access-v1.schema.json', import.meta.url)));
const ajv = new Ajv({strict: false});
addFormats(ajv);
ajv.addSchema(schema); ajv.addSchema(guest);
const check = (name, payload) => ajv.getSchema(`${schema.$id}#/$defs/${name}`)(payload);
const checkGuest = (name, payload) => ajv.getSchema(`${guest.$id}#/$defs/${name}`)(payload);
const draft = {recipient_label: '儿子小明', secret: '那年旧车站的雨伞里藏着两颗青杏',
  private_detail_confirmed: true, episode_ids: ['ep-father-son'], source_version: 'confirmed-source-version',
  handover_consent_id: 'consent-handover', voice_consent_id: null, condition: 'immediate'};
const plan = {plan_id: 'ge-plan', subject_id: 'subject', recipient_label: '儿子小明', condition: 'immediate',
  status: 'confirmed', episode_count: 1, voice_allowed: false, revision: 1};

test('guest entrustment needs private-detail confirmation and a complete reviewed source version', () => {
  assert(check('create', draft));
  assert(!check('create', {...draft, private_detail_confirmed: false}));
  assert(!check('create', {...draft, secret: '爱吃香蕉'}));
  assert(!check('create', {...draft, episode_ids: []}));
  assert(!check('create', {...draft, episode_ids: ['ep-one', 'ep-one']}));
  const {source_version, ...unreviewed} = draft;
  assert(!check('create', unreviewed));
});

test('guest entrustment has no recipient account, arbitrary state or caller-provided scope', () => {
  for (const field of ['recipient_username', 'recipient_actor_id', 'owner_actor_id', 'active']) {
    assert(!check('create', {...draft, [field]: 'forged'}), field);
  }
  assert(!check('create', {...draft, condition: 'automatically_dead'}));
  assert(check('create', {...draft, condition: 'after_verified_transition'}));
});

test('plan metadata never returns the secret or password hash', () => {
  assert(check('plan', plan));
  assert(check('plans', {items: [plan]}));
  assert(check('plan', {...plan, secret_confirmation_required: true}));
  assert(!check('plan', {...plan, secret_confirmation_required: 'true'}));
  for (const field of ['secret', 'secret_hash', 'secret_fingerprint', 'secret_key_id', 'secret_length', 'recipient_actor_id', 'voice_consent_id']) {
    assert(!check('plan', {...plan, [field]: 'private'}), field);
  }
  assert(check('locked', {locked: true}));
  assert(!check('locked', {locked: false}));
});

test('owner can re-confirm an existing secret without sending changed authority', () => {
  assert(check('secretIndex', {secret: draft.secret}));
  assert(!check('secretIndex', {secret: '香蕉'}));
  for (const field of ['episode_ids', 'condition', 'revision', 'status', 'secret_hash']) {
    assert(!check('secretIndex', {secret: draft.secret, [field]: 'forged'}), field);
  }
});

test('guest session can carry a scoped unlock without introducing recipient login credentials', () => {
  const session = {session_id: 'guest-1', subject_id: 'subject', subject_label: '父亲',
    expires_at: '2026-10-16T12:00:00Z', revision: 1, personal_voice_available: false,
    cloud_asr_policy: null, speech_notice: '本次提问用途', default_voice_available: false,
    spoken_question_available: true, scope_version: 'opaque-scope-2',
    entrustment: {recipient_label: '儿子小明', expires_at: '2026-10-16T10:10:00Z'}};
  assert(checkGuest('session', session));
  assert(checkGuest('session', {...session, entrustment: null}));
  assert(!checkGuest('session', {...session, entrustment: {...session.entrustment, secret: draft.secret}}));
  assert(!checkGuest('session', {...session, entrustment: {...session.entrustment, expires_at: 'tomorrow'}}));
  assert(checkGuest('question', {question: draft.secret, entrustment_attempt: true}));
  assert(!checkGuest('question', {question: draft.secret, entrustment_attempt: 'true'}));
});
