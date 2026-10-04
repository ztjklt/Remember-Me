"""Regenerate the experimental JSON schema from the Python source of truth."""

import json
from pathlib import Path
from pydantic.json_schema import models_json_schema
from remember_contracts import agent

ROOT = Path(__file__).resolve().parents[1]
models = [
    obj
    for obj in vars(agent).values()
    if isinstance(obj, type)
    and issubclass(obj, agent.Contract)
    and obj is not agent.Contract
]
_, schema = models_json_schema(
    [(model, "validation") for model in models],
    title="Remember Me Agent Loop v0.2 experimental",
)
schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
schema["$id"] = "https://remember.me/contracts/agent-loop-v0.2-experimental.schema.json"
(
    ROOT / "packages/contracts/schemas/agent-loop-v0.2-experimental.schema.json"
).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
