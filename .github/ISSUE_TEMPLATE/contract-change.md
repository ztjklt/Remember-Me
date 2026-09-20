---
name: Contract Change
about: Propose a change to packages/contracts. Required before any cross-module payload change.
title: "[Contract] "
labels: "contract"
assignees: ""
---

<!--
The contract in packages/contracts is the integration source of truth and outranks architecture notes.
Contract v0.1 is FROZEN. Do not edit the schema before this proposal is approved by the Product and Integration Owner.

Breaking changes (removal, rename, type change, required-field change, enum change, semantic change)
always require this Issue. Additive optional fields also need approval, because the schema sets additionalProperties: false.
-->

## Proposed change

Exact field-level change, with the current and proposed shape.

```json
// current
// proposed
```

## Classification

- [ ] Additive optional field
- [ ] Breaking (removal / rename / type / required / enum / semantics)

## Rationale

Why the current contract is insufficient, and what breaks without this change.

## Modules affected

Which of Android, Backend, AI Core, Voice, Hardware must change, and who owns each.

| Module | Owner | Impact |
| --- | --- | --- |
|  |  |  |

## Principle check

Confirm the change does not violate the frozen product principles.

- [ ] Raw Episode remains persisted before any AI or Voice work
- [ ] Downstream failure cannot destroy the original life record
- [ ] Subject / Actor separation preserved
- [ ] Consent scope is not weakened or implicitly expanded
- [ ] Provenance, evidence, confidence, and model version preserved
- [ ] No provider-specific field is hard-coded into the domain model

## Minimum-change justification

Explain why this is the smallest change that solves the problem, and what was deliberately left out.

## Migration and compatibility

How existing payloads, stored data, and in-flight Episodes are handled during the transition.

## Approval

- [ ] Product and Integration Owner approved
- [ ] Schema updated in a Pull Request referencing this Issue
