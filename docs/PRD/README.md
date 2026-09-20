# Product Requirements

The current product Source of Truth is [Remember Me PRD v3.0](Remember_Me_PRD_v3.0.docx), an Android-first revision. Coding agents should use the [PRD v3.0 Summary](PRD_V3_SUMMARY.md) for fast orientation and consult the source document for full requirements, tables, definitions, risks, and acceptance criteria.

There is exactly one current PRD. [PRD v2.0](archive/Remember_Me_PRD_v2.0.docx) is retained in [`archive/`](archive/) as history only and must not be used as the basis for current implementation.

## What changed in v3.0

v3.0 does not redo the product definition. It keeps v2.0's frozen principles — role model, Person Model, Voice, Calibration, Original Before Simulation, Handover/Legacy — and moves the client engineering baseline from iOS / Swift / SwiftUI to **Android / Kotlin / Jetpack Compose / Material 3**. The existing runnable Android prototype is the implementation starting point.

Any remaining repository text that treats iOS, Swift, or SwiftUI as the current client is superseded by v3.0 and should be corrected. A platform change is a client engineering decision, not a product scope reset: do not delete v2.0 product capabilities because of it.

## Document hierarchy

| Document | Role |
| --- | --- |
| [PRD v3.0](Remember_Me_PRD_v3.0.docx) | Current product Source of Truth |
| [PRD v3.0 Summary](PRD_V3_SUMMARY.md) | Agent-readable orientation |
| [Team Development Guide v1.0](../team/Remember_Me_Team_Development_Guide_v1.0.docx) | Engineering execution baseline: architecture, ownership, phases, GitHub update guide |
| [Roadmap](../roadmap/ROADMAP.md) | Phase status, exit gates, and owners |
| [Team Ownership](../team/00_TEAM_OWNERSHIP.md) | Who owns what, per phase |

Team ownership and contract decisions implement the PRD but do not replace it. When implementation guidance conflicts with the PRD, open an Issue and obtain a Product and Integration Owner decision before changing shared architecture or contracts.
