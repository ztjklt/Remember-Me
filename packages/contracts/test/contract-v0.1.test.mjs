import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const schemaUrl = new URL(
  "../schemas/integration-contract-v0.1.schema.json",
  import.meta.url,
);

async function loadSchema() {
  return JSON.parse(await readFile(schemaUrl, "utf8"));
}

test("integration contract schema is valid JSON with the expected versioned title", async () => {
  const schema = await loadSchema();

  assert.equal(schema.title, "Remember Me Integration Contract v0.1");
  assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema");
});

test("processing status exposes trace_id as an optional non-empty string", async () => {
  const schema = await loadSchema();
  const processingStatus = schema.$defs.processingStatus;

  assert.deepEqual(processingStatus.properties.trace_id, {
    type: "string",
    minLength: 1,
  });
  assert.equal(processingStatus.required.includes("trace_id"), false);
  assert.deepEqual(processingStatus.required, ["episode_id", "status"]);
});

test("contract v0.1 does not expose job_id", async () => {
  const schema = await loadSchema();
  const serialized = JSON.stringify(schema);

  assert.equal(serialized.includes('"job_id"'), false);
});

test("evidence distinguishes objective material and supports transcript spans", async () => {
  const schema = await loadSchema();
  const evidence = schema.$defs.evidence;

  assert.equal(evidence.properties.source_type.enum.includes("OBJECTIVE"), true);
  assert.deepEqual(evidence.properties.span_start, {
    type: "integer",
    minimum: 0,
  });
  assert.deepEqual(evidence.properties.span_end, {
    type: "integer",
    minimum: 0,
  });
});

test("memory items require provenance confidence and version information", async () => {
  const schema = await loadSchema();
  const memoryItem = schema.$defs.memoryItem;

  assert.equal(memoryItem.additionalProperties, false);
  assert.deepEqual(memoryItem.required, [
    "memory_type",
    "content",
    "source_type",
    "evidence_ids",
    "confidence",
    "model_version",
    "prompt_version",
    "schema_version",
  ]);
  assert.deepEqual(schema.$defs.aiCoreOutput.properties.memory_items.items, {
    $ref: "#/$defs/memoryItem",
  });

  const ajv = new Ajv2020({ strict: false });
  addFormats(ajv);
  const validate = ajv.compile(memoryItem);
  const completeMemory = {
    memory_type: "EVENT",
    content: "The subject moved to Singapore.",
    source_type: "SUBJECT",
    evidence_ids: ["evidence-1"],
    confidence: 0.92,
    model_version: "fixture-model-1",
    prompt_version: "memory-extractor-1",
    schema_version: "0.1.2",
  };

  assert.equal(validate(completeMemory), true);
  assert.equal(validate({ ...completeMemory, evidence_ids: [] }), false);
  const { confidence: _confidence, ...missingConfidence } = completeMemory;
  assert.equal(validate(missingConfidence), false);
});

test("capture exposes actor consent and idempotency without breaking old fixtures", async () => {
  const schema = await loadSchema();
  const capture = schema.$defs.captureEpisode;

  for (const field of ["actor_id", "recording_consent_id", "idempotency_key"]) {
    assert.deepEqual(capture.properties[field], {
      type: "string",
      minLength: 1,
    });
    assert.equal(capture.required.includes(field), false);
  }
});

test("AI input propagates trace_id and Episode Result is a shared output shape", async () => {
  const schema = await loadSchema();

  assert.deepEqual(schema.$defs.aiCoreInput.properties.trace_id, {
    type: "string",
    minLength: 1,
  });
  assert.equal(schema.$defs.episodeResult.properties.status.const, "ready");
  assert.deepEqual(schema.$defs.episodeResult.properties.memory_items.items, {
    $ref: "#/$defs/memoryItem",
  });
  assert.equal(
    schema.oneOf.some((entry) => entry.$ref === "#/$defs/episodeResult"),
    true,
  );
});
