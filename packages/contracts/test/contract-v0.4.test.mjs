import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const schema = JSON.parse(await readFile(new URL("../schemas/integration-contract-v0.4.schema.json", import.meta.url)));
const ajv = new Ajv2020({ strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

test("v0.4 keeps old Android capture and locks Twin before a human answer", () => {
  assert.equal(validate({ subject_id: "sub_1", source: "ANDROID_MIC", audio_ref: "x.m4a",
    recorded_at: "2026-09-27T01:00:00Z" }), true, JSON.stringify(validate.errors));
  assert.equal(validate({ twin_answer_id: "ta_1", cloud_consent_id: "consent_1" }), true,
    JSON.stringify(validate.errors));
  assert.equal(validate({ twin_answer_id: "ta_1", human_answer: "提前泄露" }), false);
  assert.equal(validate({ cloud_consent_id: "consent_1" }), true, JSON.stringify(validate.errors));
});

test("calibration response states the immutable lock, linked Episode, and typed diffs", () => {
  const run = { calibration_id: "cal_1", subject_id: "sub_1", twin_answer_id: "ta_1",
    question: "我喜欢什么？", locked_answer: "我喜欢散步", locked_response_type: "ORIGINAL",
    locked_model_version: "deepseek-flash", locked_person_model_version: 2,
    locked_evidence_ids: ["ev_1"], status: "complete", human_episode_id: "ep_2",
    summary: "有变化", dimensions: [{ dimension: "VALUE_PRIORITY", alignment: "DIFFERENT",
      note: "真人现在强调自由", human_excerpt: "我觉得自由" }],
    suggested_question: "为什么？", comparison_model_version: "deepseek-flash",
    created_at: "2026-09-27T01:00:00Z", completed_at: "2026-09-27T01:10:00Z" };
  assert.equal(validate(run), true, JSON.stringify(validate.errors));
  assert.equal(validate({ ...run, locked_response_type: "UNKNOWN" }), false);
  assert.equal(validate({ ...run, unauthorized_text: "say anything" }), false);
});
