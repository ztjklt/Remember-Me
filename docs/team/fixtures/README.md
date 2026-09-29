# Phase 2 Core Twin acceptance fixture

[`phase2_core_twin.json`](phase2_core_twin.json) is a synthetic, non-binding
scenario for Issues #18–#20, #23, and #24. It is **not** a Backend or AI Core
payload, a frozen Contract, or evidence that Phase 2 has started or passed.
`packages/contracts` remains unchanged. The three module owners can use the
same facts while proposing their boundaries and later writing their own tests.

The scenario starts with two Subject Episodes whose breakfast preference
changes over time and by weekday/weekend context. A third-party Episode makes
a contrary observation that must stay attributed to its speaker. Checks cover
direct-source ORIGINAL routing, a future question that requires SIMULATION or
uncertainty, an unrelated Actor's denial, a correction to a deliberately wrong
derived Memory, and deletion of the source Episode. The raw Episode is not
silently rewritten by a Memory correction; deletion invalidates every result
that relied on the deleted source. The third-party contribution assumes a
separate authorized contribution path; it never grants that Actor authority to
rewrite the Subject model. A third-party Episode may appear as attributed
counter-evidence, but cannot support a claim that the Subject herself made.

When Phase 1 has passed and Product activates Phase 2, replace these synthetic
recordings with consented real Episodes for gate acceptance. In the #23
proposal, each Owner should identify which facts their module stores, which
IDs and versions cross module boundaries, how policy context is supplied, and
when invalidation becomes visible. Resolve those questions in an approved
versioned Contract before implementing the wire APIs. A fixture result alone
cannot close the Phase 2 gate.
