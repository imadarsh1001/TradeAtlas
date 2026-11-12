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
