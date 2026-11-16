# TradeAtlas Project Learnings & Reverse-Engineering Findings

**Date**: 2026-11-11  
**Area**: Live Market Data Ingestion (AGMARKNET 2.0, data.gov.in, CEDA)

---

## 1. AGMARKNET 2.0 Production System Analysis

We inspected the production frontend bundle (`https://agmarknet.gov.in/static/js/main.8c489c92.js`) and performed live network probes against `https://api.agmarknet.gov.in/v1/`.

### Verified Endpoint Hierarchy & Access Tiers

```
api.agmarknet.gov.in/v1/
├── Tier 1: Public / Open (200 OK, No Auth, No CAPTCHA)
│   ├── GET  /daily-price-arrival/filters
│   │   └── Returns: 609 commodities, 37 states, 751 districts, 4,178 mandis, 2,154 varieties, 18 grades.
│   ├── POST /dashboard-data/
│   │   └── Payload: {"dashboard": "cumm_data_sp", "date": "YYYY-MM-DD", "page": 1, "itemsPerPage": 50}
│   │   └── Returns: Macro commodity table, MSP price, weighted average price, aggregate volume.
│   └── GET  /prices-and-arrivals/market-price/lastweek?marketId={m}&stateId={s}&commodityId={c}
│       └── Returns: 7-day rolling prices broken down by Variety (e.g. Rajkot APMC - Bold: ₹7,850/Qtl) and "NR" flags.
│
├── Tier 2: Semi-Protected Bulk Reports (HTTP 400 TOKEN_OR_CAPTCHA_REQUIRED)
│   ├── POST /daily-price-arrival/report
│   ├── GET  /prices-and-arrivals/commodity-market/daily-report-weighted
│   ├── GET  /prices-and-arrivals/commodity-market/daily-report-state
│   └── GET  /prices-and-arrivals/market-report/daily
│       └── Constraint: Server requires EITHER an authorized Bearer token OR a solved graphic CAPTCHA (captcha + captcha_key).
│
└── Tier 3: Privileged Mandi Operations (HTTP 403 Forbidden)
    ├── POST /data-entry/lot-wise/batch
    ├── POST /data-entry/cumm-wise/batch
    ├── GET  /user-login_report/filters
    └── POST /auth/refresh
        └── Constraint: Requires active JWT Bearer token issued to registered APMC mandi officials via /auth/login + OTP.
```

---

## 2. Open Government Data Platform (`data.gov.in`) Learnings

### Authentication & Key Mechanics
* **Resource UUID**: `9ef84268-d588-465a-a308-a864a43d0070` (*Current Daily Price of Various Commodities from Various Markets (Mandi)*).
* **Key Validation**: Keys are validated against registered NIC developer accounts. Generic strings (`test`, `demo`) return `HTTP 403: {"error": "Key not authorised"}`.
* **Tested Key**: Validated live with user key `579b46...571b` returning `HTTP 200 OK` across 13,119 active daily records.
* **Schema Highlights**:
  * Exposes `min_price`, `max_price`, and `modal_price` (in ₹/Quintal).
  * Exposes `variety` (e.g. `Bold`, `Other`, `Local`) and `grade` (e.g. `FAQ`, `Medium`).
  * Formatted date: `DD/MM/YYYY`.
* **Discovered Limitations**:
  1. **Volume Omission**: Does not contain `arrivals_t` (quantity in tonnes).
  2. **Intra-Day Sync Asymmetry**: APMCs upload records at different times during the day. For example, Rajasthan mandis (Lunkaransar, Sridungargarh) had groundnut records posted mid-day, whereas Gujarat mandis had not yet posted groundnut lots during the morning batch.

---

## 3. CEDA (Ashoka University) API Learnings

* **Base URL**: `https://api.ceda.ashoka.edu.in/v1`
* **Swagger Documentation**: OpenAPI 3.0 compliant.
* **Key Advantage**: Solves the AGMARKNET CAPTCHA barrier while providing **both** prices (`/agmarknet/prices`) and arrival volumes (`/agmarknet/quantities`).
* **License & Terms**: Strictly non-commercial with mandatory visual citation (`CEDA Agri Market Data`). Requires API token passed via headers.

---

## 4. Local Development & Secrets Best Practices

* **`.env` Management**:
  * Secrets are stored in `.env` using standard key-value format (`DATA_GOV_IN_API_KEY=...`).
  * `.gitignore` was updated to explicitly ignore `.env`, `.env.local`, and `.env.*.local`.
  * `.env.example` is committed to track required keys without leaking credentials.
* **Network & Sandbox Guardrails**:
  * Commands requiring external HTTPS calls to government or university endpoints (`api.data.gov.in`, `api.agmarknet.gov.in`, `github.com`) require standard external networking.
* **TLS Verification Confirmed (2026-11-13)**:
  * Both endpoints returned `HTTP 200` with certificate verification **enabled** (default httpx, no `verify=False`): `api.data.gov.in` (2 Gujarat groundnut records) and `api.agmarknet.gov.in` spot-weekly (Rajkot APMC).
  * Earlier probes had run with `verify=False`, so certificate validity was unconfirmed until this check; `verify=False` has since been removed from the codebase (enforced by `tests/test_ingest.py::test_no_verify_false_anywhere_in_package`).
* **Windows Application Control / uv quirks**:
  * The `pytest.exe` console-script trampoline in `.venv/Scripts/` is blocked by local Application Control policy (os error 4551). Run the suite as `uv run python -m pytest tests/ -q` instead; `uv run python` and the direct `.venv/Scripts/python.exe` both work.
  * `langsmith`'s pytest plugin (transitive via langchain) fails to import under the same policy (`xxhash` DLL blocked); it is blocked explicitly via `addopts = "-p no:langsmith"` in `pyproject.toml`.

## Agent benchmark live-run findings (2026-11-15)

First live campaign paused mid-run: provider tool-call/schema strictness varies (Groq validates tool args server-side and 400s the run; strict json_schema rejects the free-form selector — fixed via non-strict json_schema + client-side validation), langgraph executes multi-tool-call turns on parallel threads (DuckDB catalog DDL conflicts — fixed by once-per-DB schema init + serialized writes), and free-tier providers rate-limit hard under parallel suites (one provider per session; pacing + resume-by-case-ids in the runner). Full log: [BENCHMARK_FINDINGS.md](BENCHMARK_FINDINGS.md).

## 2026-11-17 — Cloudflare AI Gateway + model registry (`add-llm-gateway-model-registry`)

- **The gateway swap is a pure base_url change** (`https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/<route>` + `cf-aig-authorization: Bearer` header) — proven by the provider sandbox before productionizing. BYOK = send NO provider `Authorization` (per-model httpx request hook strips it; Cloudflare injects dashboard-stored keys). Sending a gateway token as a provider key (the sandbox's fallback chain) is a confusion hazard — the registry resolves non-BYOK keys strictly from the entry's named env var.
- **Gateway rate limiting is dashboard-level and returns a bare 429** (no documented Retry-After header) — client-side pacing from registry `rpm_limit` is the primary defense; the runner's 429 backoff is secondary.
- **`langchain-google-genai`'s default structured-output method is already `json_schema`** (native responseJsonSchema) — the Google port of the structured-output contract needed only the client-side `model_validate` wrapper, not a different method. Entries stay disabled until a live smoke passes.
- **Run-ledger format choice: append-only JSONL over whole-file JSON** — the 11-15 pause killed a mid-run suite and lost the results file; JSONL keeps every completed line readable after a torn write. Daily-cap projection uses ledger-derived avg touches per case (default 6) and corrects post-case from `RunRecord.model_touches`.
- **Transport vs behaviour failures**: classify by substring signatures in `failure_reason` (langchain exceptions don't reliably surface Retry-After); only transport-class triggers retries (3 attempts; backoff 5s then 10s before retries 2 and 3), behaviour failures are evidence and never retried.
