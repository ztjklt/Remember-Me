import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

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
