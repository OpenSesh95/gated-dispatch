# ADR-001: Standard library only

**Status:** Accepted · 2026-11-10

## Context

The slice must run anywhere Python 3.11+ runs, be auditable in one sitting, and keep working when framework APIs churn. It is a reference implementation of a control loop, not a product surface.

## Decision

Use only the Python standard library: `urllib` for HTTP, `argparse` for the CLI, `json`/`hashlib` for the ledger, `unittest` for tests. The provider call targets an OpenAI-compatible HTTP interface, which every major provider or gateway exposes.

## Alternatives rejected

- **Provider SDKs** — one dependency per provider, each with its own release cadence and breaking changes; the slice would age with the fastest-moving SDK.
- **Orchestration frameworks (LangChain et al.)** — they own the control flow this project exists to make explicit. Hiding dispatch, verification, and gating inside a framework defeats the purpose of the artifact.
- **`requests`/`httpx`** — nicer ergonomics, but a dependency the slice does not need; `urllib` is sufficient for one POST.

## Consequences

Zero install friction (`pip install -e .` pulls nothing), a small audit surface, and portability across machines — at the cost of hand-rolled HTTP error handling if the slice ever grows past one endpoint.
