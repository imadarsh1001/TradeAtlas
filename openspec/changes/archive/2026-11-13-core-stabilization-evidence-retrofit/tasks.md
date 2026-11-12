# Tasks

## 1. Core hygiene

- [x] 1.1 Remove `verify=False` from both httpx clients in `tradeatlas/ingest.py` so TLS is verified — verify: `grep -n "verify=False" tradeatlas/` returns nothing, and a client-construction test in group 3 asserts verification is enabled
- [x] 1.2 Make cache timestamps UTC in `tradeatlas/cache.py` (writes store UTC — naive per the DuckDB TIMESTAMP convention — via `datetime.now(timezone.utc)`; reads normalize to timezone-aware UTC) — verify: a `test_cache.py` timestamp test passes after group 3

## 2. Evidence envelope

- [x] 2.1 Add `tradeatlas/models.py` with a Pydantic `EvidenceEnvelope` (payload, observation date(s), `retrieved_at` UTC, `cached_as_of`, coverage, tier `deep|thin`, caveats) — verify: model instantiates and rejects a missing `retrieved_at` in a unit test
- [x] 2.2 Wrap the four service functions in `tradeatlas/ingest.py` plus `calculate_delivered_cost` in `tradeatlas/calculator.py` to return envelopes with tier labels (groundnut Gujarat/Rajasthan = deep; state-less ID selectors = thin; input-only arithmetic = deep with coverage "user-supplied inputs"), basis caveats on derived figures, and explicit no-data statements instead of empty lists; add an optional `transport` parameter (default `None`) to the fetching services as the test seam; update `tradeatlas_mcp.py` docstrings for the new output shape — verify: unit smoke test asserting envelope fields on each of the five tools' responses, including a hub "Not Reported Today" entry and an explicit empty-result message

## 3. Test scaffolding + deterministic-core suite

- [x] 3.1 Add `[dependency-groups] dev = ["pytest"]` to `pyproject.toml`, run `uv lock && uv sync`, create `tests/` with `conftest.py` and recorded JSON fixtures under `tests/fixtures/` (data.gov.in response sample, AGMARKNET spot-weekly sample), captured once from live calls during this task (the suite's only network use) and committed — verify: `uv run pytest` runs the (initially minimal) suite green with no network
- [x] 3.2 `tests/test_calculator.py`: whole-seed arithmetic, pod→kernel 70% conversion, rounding, basis labels — verify: `uv run pytest tests/test_calculator.py` green
- [x] 3.3 `tests/test_cache.py`: TTL lifecycle via `httpx.MockTransport` + patched clock (fresh→no call, stale→refetch, failure→fallback), upsert isolation, UTC timestamps — verify: `uv run pytest tests/test_cache.py` green offline
- [x] 3.4 `tests/test_ingest.py`: case-insensitive hub matching, unmatched-hub status, supply-balance surplus/deficit/short-baseline and explicit error, API-key fallback path, TLS client-construction assertions — verify: `uv run pytest tests/test_ingest.py` green
- [x] 3.5 `tests/test_evidence_cards.py`: tier labelling per commodity/state and for state-less/input-only tools, caveats on derived numbers, cache-age disclosure, explicit no-data statements — envelope-only assertions against the shared conftest wrapped responses, no duplicate mocking — verify: `uv run pytest tests/test_evidence_cards.py` green

## 4. Source manifest

- [x] 4.1 Create `data/manifest.json` with entries for every file in `data/raw/` and `config/` (path, SHA-256, source URL/revision, retrieval date, terms) — verify: manifest parses and every tracked file has all fields
- [x] 4.2 `tests/test_manifest.py`: coverage check, hash-integrity check, unmanifested-file failure naming the file — verify: `uv run pytest tests/test_manifest.py` green; copying a modified file into `data/raw/` makes it fail with that file named

## 5. Integration gate + docs

- [x] 5.1 Full offline gate: `uv run pytest` green with network disabled; `uv lock --check` consistent — verify: both commands exit 0
- [x] 5.2 Update README (evidence-envelope note in "What works today", breaking-change mention for MCP consumers) and ROADMAP current status; record the TLS-verification probe result in `docs/LEARNINGS.md` and add the manifest maintenance note to `docs/` — verify: all relative links resolve, status matches completed state
