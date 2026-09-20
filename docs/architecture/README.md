# Architecture

The agreed end-to-end path is:

`Android and Hardware → Backend Ingestion → STT and AI Core → Memory and Person Model → Twin → Voice → Backend → Android`

Provider choices remain replaceable behind adapters. Architecture records added here must not silently override `packages/contracts`.

