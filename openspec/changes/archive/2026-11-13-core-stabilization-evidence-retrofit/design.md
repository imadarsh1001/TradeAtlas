# Design

## Context

The four tool service functions in `tradeatlas/ingest.py` (plus `calculate_delivered_cost` in `tradeatlas/calculator.py`) return raw record dicts; `tradeatlas/cache.py` writes naive local-time timestamps; both HTTP clients pass `verify=False`; pytest is not a dependency; no provenance record exists for `data/raw/` or `config/`. See proposal.md — Why. The MCP server (`tradeatlas_mcp.py`) is a thin pass-over these services.

## Goals / Non-Goals

**Goals:**
- One standard, typed evidence envelope wrapping every tool output (see `specs/evidence-cards/spec.md`)
- An offline pytest suite as the M1 exit gate (`uv run pytest` green, no network)
- Enforced provenance for pinned files via a manifest check inside that suite
- TLS verification and UTC timestamps as tested properties

**Non-Goals:**
- No new data sources, no arrival volumes (Beyond M6)
- No normalization of the AGMARKNET spot-weekly upstream schema (wrapped as-is)
- No agent-layer work (M3), no UI, no evidence-card *verification gate* (that is M3's citation checker, not M1)
- No cache schema migration beyond timestamp handling (6 h TTL ages old rows out naturally)

## Decisions

1. **Typed Pydantic envelope, defined once in the package** (`tradeatlas/models.py`) — `EvidenceEnvelope` carrying payload + observation date(s) + `retrieved_at`/`cached_as_of` (UTC) + coverage + tier + caveats. *Why not plain dicts:* the envelope is a contract; Pydantic is already a dependency and gives validation for free. *Why not dataclasses:* MCP serialization favors Pydantic. Guardrail: the envelope stays one flat model with a loosely typed payload — per-tool payload submodels or discriminated unions are the over-engineering trap; do not introduce them.
2. **Wrapping happens in the service functions (`ingest.py`), not the MCP layer** — M3 agents will call the package, not the MCP server; wrapping at the service boundary means every consumer gets the same contract. The MCP server becomes pure pass-through.
3. **Timestamps:** new writes use `datetime.now(timezone.utc)`; reads treat legacy naive rows as UTC. No backfill — the 6 h TTL invalidates old rows within a day.
4. **TLS:** drop `verify=False` outright. docs/LEARNINGS.md records successful HTTP 200 probes, but those ran with verification disabled, so certificate validity is unconfirmed; the change is low-risk and trivially reversible, and the first live call with verification enabled (at apply time) is recorded in LEARNINGS.md as confirmation. No cert-bundle workaround is warranted.
5. **Test strategy: `httpx.MockTransport` + a monkeypatched clock, fixtures as recorded JSON under `tests/fixtures/`.** *Why not `respx` or `freezegun`:* avoids two new dependencies for capabilities httpx and monkeypatch already cover. Fetching services gain an optional `transport` parameter (default `None` → normal client) as the injection seam — one parameter, not an abstraction layer. Fixtures are real API responses captured once during scaffolding (the suite's only network use) and committed. Every scenario in `specs/deterministic-core/spec.md` maps to at least one test.
6. **Manifest as JSON (`data/manifest.json`) checked by a pytest test** — machine-checkable, diff-able, and the M1 gate already runs pytest, so the check cannot be skipped silently. *Alternative considered:* standalone script + pre-commit hook — rejected: no pre-commit infra exists and checks outside the test suite rot.
7. **pytest via uv dependency-group** (`[dependency-groups] dev = ["pytest"]`) — keeps the runtime install lean while `uv sync` picks it up for development.

## Risks / Trade-offs

- [data.gov.in intra-day reporting asymmetry means "no records" may mean "not yet posted," not "no trade"] → envelope wording states "not reported in this snapshot (retrieved_at …)" and never asserts absence of trade.
- [Envelope bloats every response] → acceptable: envelope fields are small and flat; agents and dashboards need exactly these fields; payload layout unchanged.
- [Manifest check friction when swapping extracts] → intended friction; the check message names the file and required fields, so updating the manifest is one edit.
- [Upstream spot-weekly schema may change] → out of scope to normalize; the envelope's caveats disclose that the payload is passed through from AGMARKNET 2.0.

## Migration Plan

Single change, no data migration. Breaking output-shape change lands with the README note (updated at apply time); the only current consumers are local MCP clients owned by this project. Rollback = revert the commit.

## Open Questions

None material — envelope field names are fixed in `specs/evidence-cards/spec.md`; anything narrower is a tasks-level detail.
