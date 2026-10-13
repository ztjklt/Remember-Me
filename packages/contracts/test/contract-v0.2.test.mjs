import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const schema = JSON.parse(await readFile(new URL("../schemas/integration-contract-v0.2.schema.json", import.meta.url)));
const ajv = new Ajv2020({ strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

test("iOS capture is additive, while the Android source remains valid", () => {
  const capture = { subject_id: "sub_1", source: "IOS_MIC", audio_ref: "clip.m4a", recorded_at: "2026-09-26T09:00:00Z" };
  assert.equal(validate(capture), true, JSON.stringify(validate.errors));
  assert.equal(validate({ ...capture, source: "ANDROID_MIC" }), true);
  assert.equal(validate({ ...capture, source: "UNKNOWN_MIC" }), false);
});

test("the seven-domain snapshot and question have typed envelopes", () => {
  const domains = schema.$defs.personTrait.properties.domain.enum.map(domain => ({ domain, traits: [] }));
  assert.equal(validate({ subject_id: "sub_1", version: 2, domains }), true, JSON.stringify(validate.errors));
  assert.equal(validate({ subject_id: "sub_1", version: 2, domains: domains.slice(1) }), false);
  assert.equal(validate({ question_id: "q_1", subject_id: "sub_1", text: "你最看重什么？",
    target_domain: "VALUES_BELIEFS", reason: "missing_domain", status: "pending" }), true);
});

test("person traits and graph facts require evidence and a model version", () => {
  const evidence = { evidence_id: "ev_1", source_type: "SUBJECT", source_ref: "episode:ep_1#span:0-2",
    excerpt: "我喜欢", span_start: 0, span_end: 3 };
  const trait = { trait_id: "trait_1", domain: "PREFERENCES", statement: "喜欢茶",
    confidence: 0.9, source_type: "AI_INFERENCE", evidence_ids: ["ev_1"],
    counter_evidence_ids: [], status: "active", model_version: "qwen-1" };
  const output = { memory_items: [], graph_updates: [], persona_updates: [trait], evidence: [evidence], model_version: "qwen-1" };
  assert.equal(validate(output), true, JSON.stringify(validate.errors));
  assert.equal(validate({ ...output, persona_updates: [{ ...trait, evidence_ids: undefined }] }), false);
});
