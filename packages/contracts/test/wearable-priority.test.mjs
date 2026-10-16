import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
const schema = JSON.parse(fs.readFileSync(new URL('../schemas/wearable-priority-v1.schema.json', import.meta.url)));
const ajv = new Ajv({strict: false});
ajv.addSchema(schema);
const check = (name, value) => ajv.getSchema(schema.$id + '#/$defs/' + name)(value);

test('priority upload metadata is versioned and distinguishes an unavailable timeline', () => {
  const value = {wearable_policy_version: 'wearable-priority-v1', priority_ranges_ms: '[[0,20000]]',
    priority_timeline_complete: 'false', transcript_retention: 'derived_only', source_start_ms: '300000', source_end_ms: '360000'};
  assert(check('metadata', value));
  assert(!check('metadata', {...value, priority_timeline_complete: true}));
  assert(!check('metadata', {...value, wearable_policy_version: 'future'}));
  assert(!check('metadata', {...value, source_start_ms: '-10'}));
  assert(!check('ranges', [[0, 20.5]]));
  assert(!check('ranges', [[0, 20, 30]]));
});

test('AI priority context cannot carry client-made speaker identity or raw audio', () => {
  const value = {policy_version: 'wearable-priority-v1', protected_spans: [{start: 0, end: 12}], priority_timeline_complete: true};
  assert(check('aiContext', value));
  assert(check('aiContext', {...value, protected_spans: [], priority_timeline_complete: false}));
  assert(!check('aiContext', {...value, speaker_verification: 'matched'}));
  assert(!check('aiContext', {...value, protected_spans: [{start: -1, end: 12}]}));
  assert(!check('aiContext', {...value, protected_spans: [{start: 0, end: 12, text: 'unverified'}]}));
});
