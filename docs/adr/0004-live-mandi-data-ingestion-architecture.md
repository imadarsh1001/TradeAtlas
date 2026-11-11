# Live Mandi Data Ingestion Architecture: data.gov.in and AGMARKNET 2.0

## Status
Accepted

## Context
Commercial groundnut procurement intelligence requires transitioning from static, pinned historical extracts (`data/raw/`) to live market observations. We conducted reverse-engineering and empirical HTTP probes against the upgraded AGMARKNET 2.0 portal (`https://api.agmarknet.gov.in/v1/`), the official Open Government Data Platform (`https://api.data.gov.in`), and the academic CEDA API.

Our investigation uncovered three critical technical constraints:
1. **AGMARKNET 2.0 Bulk Scraping Blocked by CAPTCHA**: While master filters (`/daily-price-arrival/filters`) and 7-day rolling spot queries (`/prices-and-arrivals/market-price/lastweek`) are unauthenticated and public, all bulk tabular reporting endpoints (`/daily-price-arrival/report`, `/prices-and-arrivals/market-report/daily`) strictly return HTTP 400 `TOKEN_OR_CAPTCHA_REQUIRED`. Headless automated scraping of these endpoints is blocked without solving graphic CAPTCHAs.
2. **Internal Operations Gated by Bearer JWT**: Mandi data-entry and administrative routes require official APMC staff JWT tokens via `/auth/login` and `/auth/verify-otp`, returning HTTP 403 `Authorization header missing` or `Session expired` for unauthorized requests.
3. **data.gov.in Provides Official, CAPTCHA-Free REST Access**: Resource ID `9ef84268-d588-465a-a308-a864a43d0070` exposes daily wholesale prices (min, max, modal) with variety and grade breakdown via authenticated GET requests (`api-key=...`). However, it omits daily arrival quantities in tonnes.

## Decision
1. **Automated Price Pipeline via data.gov.in**:
   TradeAtlas will use the official `data.gov.in` REST API (Resource `9ef84268-d588-465a-a308-a864a43d0070`) as the primary ingest for live daily mandi prices. Keys must be provisioned via user environment variables (`DATA_GOV_IN_API_KEY`) and loaded from `.env` (strictly ignored by Git).
2. **Direct Spot Checks via Unauthenticated AGMARKNET 2.0**:
   For on-demand 7-day spot verification of specific mandis (e.g. Rajkot, Gondal, Bikaner), TradeAtlas can query `GET /prices-and-arrivals/market-price/lastweek?marketId={id}&stateId={id}&commodityId={id}`, which requires neither token nor CAPTCHA.
3. **No Automated CAPTCHA Bypassing**:
   TradeAtlas strictly prohibits attempting to bypass or solve graphic CAPTCHAs on `POST /daily-price-arrival/report`.
4. **Arrival Volume Supplementation**:
   Because `data.gov.in` omits arrival volume (`arrivals_t`), TradeAtlas will ingest arrival volumes through either macro UPAg production estimates, authenticated CEDA API (`/agmarknet/quantities`) for non-commercial research, or official e-NAM feeds in future milestones.

## Consequences
- **Positive**: Ingestion is compliant, legal, robust, and free from fragile DOM scraping or CAPTCHA-breaking hacks.
- **Negative**: Daily mandi-level arrival volumes cannot be retrieved from `data.gov.in` alone; procurement sizing must rely on UPAg macro production and rolling spot indicators until a formal volume feed is connected.
