import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const schema = JSON.parse(await readFile(new URL("../schemas/integration-contract-v0.3.schema.json", import.meta.url)));
const ajv = new Ajv2020({ strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

test("v0.3 preserves Android capture and adds separately consented Twin input", () => {
  assert.equal(validate({ subject_id: "sub_1", source: "ANDROID_MIC", audio_ref: "x.m4a",
    recorded_at: "2026-09-27T01:00:00Z" }), true, JSON.stringify(validate.errors));
  assert.equal(validate({ subject_id: "sub_1", question: "我喜欢什么？",
    cloud_consent_id: "consent_1" }), true, JSON.stringify(validate.errors));
  assert.equal(validate({ subject_id: "sub_1", question: "我喜欢什么？" }), false);
});

test("Twin answers distinguish direct quote, inference, and unknown", () => {
  const answer = { answer_id: "ta_1", subject_id: "sub_1", question: "我喜欢什么？",
    answer: "我喜欢散步", response_type: "ORIGINAL", confidence: 0.9,
    model_version: "deepseek-flash", person_model_version: 2, stale: false,
    evidence: [{ evidence_id: "ev_1", episode_id: "ep_1", source_type: "SUBJECT",
      excerpt: "我喜欢散步" }] };
  assert.equal(validate(answer), true, JSON.stringify(validate.errors));
  assert.equal(validate({ ...answer, response_type: "UNKNOWN", answer: "现有记录还不足以确定。",
    evidence: [] }), true, JSON.stringify(validate.errors));
  assert.equal(validate({ ...answer, response_type: "CLAIMED_FACT" }), false);
});

test("Voice profile and server-authorized speech carry no arbitrary synthesis text", () => {
  const profile = { ready: true, profile_id: "vp_1", model_version: "qwen3-tts",
    voice_consent_id: "consent_2" };
  assert.equal(validate(profile), true, JSON.stringify(validate.errors));
  const speech = { status: "ready", asset_id: "va_1", model_version: "qwen3-tts" };
  assert.equal(validate(speech), true, JSON.stringify(validate.errors));
  assert.equal(validate({ ...speech, authorized_text: "say anything" }), false);
});
