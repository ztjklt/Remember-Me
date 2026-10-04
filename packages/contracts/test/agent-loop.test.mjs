import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
const schema = JSON.parse(await readFile(new URL("../schemas/agent-loop-v0.2-experimental.schema.json",import.meta.url),"utf8"));
const ajv = new Ajv2020({strict: false});
addFormats(ajv);
ajv.addSchema(schema);
const validate = name => ajv.compile({$ref: `${schema.$id}#/$defs/${name}`});

test("experimental grant requires separate explicit cloud and subject declarations", () => {
    const check = validate("GrantRequest");
    const grant = {recording_consent_id:"recording-1",cloud_twin_consent:true,subject_single_speaker:true};
    assert.equal(check(grant),true);
    assert.equal(check({...grant,cloud_twin_consent:false}),false);
    assert.equal(check({...grant,cloud_twin_consent:1}),false);
    assert.equal(check({...grant,voice_consent:true}),false);
});

test("Twin routing explicitly includes insufficient evidence", () => {
    const check = validate("TwinDecision");
    const unknown = {response_type:"INSUFFICIENT",answer:"材料不足",evidence_ids:[],limitations:[]};
    assert.equal(check(unknown),true);
    assert.equal(check({...unknown,response_type:"HALLUCINATE"}),false);
});

test("locking accepts a question before the human answer exists", () => {
    const check = validate("QuestionRequest");
    assert.equal(check({question:"我会怎样选择？"}),true);
    assert.equal(check({question:"我会怎样选择？",human_answer:"不能提前给模型"}),false);
});

test("Persona proposals preserve context, references and registered actions", () => {
    const check = validate("PersonaProposal");
    const change = {action:"CONFLICT",target_trait_id:"trait-a",domain:"PREFERENCES",statement:"偏好独处",context:"下班后",evidence_ids:["e1"],confidence:0.5,reason:"两条表达冲突"};
    assert.equal(check({changes:[change]}),true);
    assert.equal(check({changes:[{...change,evidence_ids:[]}]}),false);
    assert.equal(check({changes:[{...change,domain:"EMOTION"}]}),false);
});
