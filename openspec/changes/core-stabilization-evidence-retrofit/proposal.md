# Proposal

## Why

The five live MCP tools return raw record dictionaries with no observation age, scope caveats, or tier labels, and the deterministic core (`tradeatlas/calculator.py`, `cache.py`, `ingest.py`) has zero tests — both contradict the project thesis ([ADR 0002](../../../docs/adr/0002-deterministic-evidence-and-citation-verification.md): deterministic evidence, strict verification) and block ROADMAP M1, which gates every later milestone (the M3 agents consume evidence-card outputs).

## What Changes

- All 5 MCP tool outputs are wrapped in an evidence-card envelope: observation date vs. retrieval date (UTC), coverage counts and denominator where known, deep/thin tier labels, and explicit caveats. **BREAKING**: tool output shape changes from raw record lists to self-describing envelopes for every MCP consumer.
- Pytest coverage lands for the deterministic core — calculator arithmetic (incl. pod→kernel), cache TTL/upsert/fallback, hub matching, supply balance — using recorded fixtures, never live network calls.
- Hygiene: `verify=False` removed from both HTTP clients (TLS verification enforced); cache timestamps become timezone-aware UTC.
- A source manifest pins every file in `data/raw/` and `config/`: SHA-256 hash, source revision, retrieval date, and terms.

## Capabilities

### New Capabilities

- `evidence-cards`: the self-describing output contract for every TradeAtlas tool — each result discloses data age, coverage, scope tier (deep/thin), and caveats, so no consumer can mistake thin-tier or stale data for verified intelligence.
- `deterministic-core`: the verified correctness contract of `tradeatlas/` — cost arithmetic (incl. the 70% shelling-outturn benchmark), cache freshness/upsert/fallback, hub matching, supply-balance computation, TLS-verified HTTP, and UTC timestamps.
- `source-manifest`: provenance governance for pinned data — every file under `data/raw/` and `config/` carries a manifest record (hash, revision, retrieval date, terms) so any figure is traceable to a pinned source.

### Modified Capabilities

(none — this is the first OpenSpec change; no specs exist yet)

## Impact

- **Code**: `tradeatlas/ingest.py`, `tradeatlas/cache.py`, `tradeatlas/calculator.py` (envelopes, UTC, TLS), `tradeatlas_mcp.py` (pass-through/docstrings).
- **New**: `tests/` (pytest suite + fixtures), `data/manifest.json` (or equivalent) + a maintenance note in `docs/`.
- **Dependencies**: `pytest` added as a dev dependency ([ADR 0006](../../../docs/adr/0006-persona-expansion-and-reconciled-roadmap.md) M1 mandates the suite; `uv.lock` regenerated).
- **Consumers**: MCP clients (Claude Code, Cursor, agents) see changed output shapes — the breaking change is the point of M1; agents (M3) are built against the new contract.
- **No change**: data files, API endpoints used, `.env` handling; docs/ROADMAP.md gets a status-line update only (no milestone restructuring).
