"""Versioned prompt and schema identifiers for the Phase 1 extractor."""

PROMPT_VERSION = "memory-extractor-v1"
SCHEMA_VERSION = "integration-contract-v0.1.2"


def build_system_prompt() -> str:
    return (
        "Extract only evidence-backed memories from the supplied transcript. "
        "Return JSON matching the supplied schema and no prose. Preserve uncertainty; "
        "do not invent facts. Use only the allowed memory and source enums. "
        "Keep graph_updates and persona_updates as empty arrays for Phase 1. "
        "Every memory must include evidence_ids, confidence, model_version, "
        "prompt_version, and schema_version."
    )


__all__ = ["PROMPT_VERSION", "SCHEMA_VERSION", "build_system_prompt"]
