# Open Government Data (OGD) Platform India (`data.gov.in`) API Reference

**Document Version:** 1.0.0  
**Last Updated:** 2026-11-11  
**Project:** TradeAtlas (Indian Agricultural Commodity Intelligence)

---

## 1. Overview & Architecture

The **Open Government Data (OGD) Platform India** (`https://data.gov.in`) is the official public API portal managed by the National Informatics Centre (NIC) and Ministry of Electronics & Information Technology (MeitY). 

For agricultural market surveillance, `data.gov.in` hosts synchronized data feeds from **AGMARKNET** (Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers Welfare).

Unlike direct AGMARKNET 2.0 portal web routes (which require graphic CAPTCHA validation for bulk exports), the `data.gov.in` platform exposes clean, key-authenticated REST endpoints suitable for automated batch pipelines and scheduled ingestion jobs.

---

## 2. Authentication & Keys

### Authentication Scheme
* **Type:** Query Parameter Authentication.
* **Parameter Name:** `api-key`
* **Protocol:** HTTPS GET.

### Test Key & Authorization Behavior
The OGD platform validates API keys server-side against registered developer profiles. Generic placeholder strings like `test`, `demo`, or arbitrary hashes return:

```json
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "error": "Key not authorised"
}
```

If the parameter is completely omitted:
```json
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "Authorization field missing"
}
```

### How to Generate Your Developer Key
1. Register for an account on [data.gov.in](https://data.gov.in).
2. Verify your email and log in to the user dashboard.
3. Navigate to **My Account > API Key** (`https://data.gov.in/user/me/api-key`).
4. Copy your 64-character hexadecimal key (e.g., `579b464db66ecb387e3a7fae...`).
5. Store it securely in your local environment:
   ```powershell
   $env:DATA_GOV_IN_API_KEY = "your_actual_api_key_here"
   ```

---

## 3. Core Mandi & Agricultural Endpoints

### Endpoint 1: Current Daily Mandi Prices (Primary Dataset)
* **Dataset Title:** Current Daily Price of Various Commodities from Various Markets (Mandi)
* **Resource UUID:** `9ef84268-d588-465a-a308-a864a43d0070`
* **Base URL:**
  ```text
  https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
  ```
* **Method:** `GET`
* **Update Frequency:** Daily (overnight sync from national APMCs).

#### Standard Request Parameters

| Parameter | Type | Required | Description / Allowed Values | Default |
| :--- | :--- | :--- | :--- | :--- |
| `api-key` | string | **Yes** | Your 64-char OGD platform API key | — |
| `format` | string | No | Response serialization: `json`, `xml`, or `csv` | `json` |
| `limit` | integer | No | Number of records to return per page (max recommended: 10,000) | `10` |
| `offset` | integer | No | Zero-based index of the first record to return (pagination) | `0` |
| `filters[field]` | string | No | Exact match filter on schema fields (case-sensitive) | — |

#### Available Filter Keys for Daily Mandi Prices
* `filters[state]`: State name (e.g., `Gujarat`, `Rajasthan`, `Maharashtra`)
* `filters[district]`: District name (e.g., `Rajkot`, `Bikaner`, `Gondal`)
* `filters[market]`: APMC Mandi name (e.g., `Rajkot`, `Gondal`, `Jetpur`)
* `filters[commodity]`: Commodity name (e.g., `Groundnut`, `Wheat`, `Mustard`)
* `filters[variety]`: Commodity variety (e.g., `Bold`, `Java`, `Desi`)
* `filters[grade]`: Quality grade (e.g., `FAQ`, `Medium`, `Large`)
* `filters[arrival_date]`: Date string formatted as `DD/MM/YYYY` (e.g., `10/11/2026`)

#### Sample Response Payload (`format=json`)

```json
{
  "created": 1731328000,
  "updated": 1731331600,
  "title": "Current Daily Price of Various Commodities from Various Markets (Mandi)",
  "desc": "Wholesale prices of commodities reported across APMCs",
  "org_type": "Central",
  "org": [
    "Ministry of Agriculture and Farmers Welfare",
    "Department of Agriculture and Cooperation",
    "Directorate of Marketing and Inspection (DMI)"
  ],
  "sector": ["Agriculture"],
  "visualizable": "1",
  "index_name": "9ef84268-d588-465a-a308-a864a43d0070",
  "message": "Resource fetched successfully",
  "version": "2.2.0",
  "status": "ok",
  "total": 4521,
  "count": 2,
  "limit": "2",
  "offset": "0",
  "records": [
    {
      "state": "Gujarat",
      "district": "Rajkot",
      "market": "Rajkot",
      "commodity": "Groundnut",
      "variety": "Bold",
      "grade": "FAQ",
      "arrival_date": "10/11/2026",
      "min_price": "6800",
      "max_price": "8100",
      "modal_price": "7850"
    },
    {
      "state": "Rajasthan",
      "district": "Bikaner",
      "market": "Bikaner",
      "commodity": "Groundnut",
      "variety": "Desi",
      "grade": "FAQ",
      "arrival_date": "10/11/2026",
      "min_price": "6400",
      "max_price": "7500",
      "modal_price": "7150"
    }
  ]
}
```

---

### Endpoint 2: Agricultural Production & Economic Catalogs
The OGD platform provides several complementary resources across ministries:

1. **Wholesale Price Index (WPI) - Agricultural Commodities**
   * **Source:** Office of the Economic Adviser, Ministry of Commerce and Industry.
   * **Resource Base:** Search catalog under *Index Numbers of Wholesale Prices in India*.
   * **Purpose:** Macro inflation deflators for agricultural products.
2. **Crop Production Statistics (APY)**
   * **Source:** Directorate of Economics and Statistics (DES).
   * **Fields:** State, District, Crop, Year, Season, Area (Hectares), Production (Tonnes), Yield.
   * **Note:** Official UPAg authenticated API (`https://data.upag.gov.in/docs`) provides fresher advance estimates than static OGD uploads.

---

## 4. Comparison: `data.gov.in` vs. `AGMARKNET 2.0 Direct` vs. `CEDA API`

| Capability | **data.gov.in** | **AGMARKNET 2.0 Direct (`api.agmarknet.gov.in`)** | **CEDA API (`api.ceda.ashoka.edu.in`)** |
| :--- | :--- | :--- | :--- |
| **Authentication** | API Key query param (`api-key=...`) | Unauthenticated for 7-day spot; Bearer JWT for internal operations. | API Token / Bearer Key (`Authorization: Bearer <key>`) |
| **CAPTCHA Barrier** | **None** | **Yes** (`TOKEN_OR_CAPTCHA_REQUIRED` on bulk reports) | **None** |
| **Documentation** | Official catalog page on data.gov.in | None (Undocumented private React SPA backend) | Full OpenAPI 3.0 / Swagger UI |
| **Prices Data** | Min, Max, Modal prices (INR/quintal) | Min, Max, Modal, Weighted Average prices | Min, Max, Modal prices (`/agmarknet/prices`) |
| **Variety & Grade** | **Yes** (`variety`, `grade`) | **Yes** (stratified variety reporting) | **Yes** (`Variety`, `Grade`) |
| **Arrival Quantities** | **No** (volume omitted in daily price resource) | **Yes** (metric tonnes in dashboard and reports) | **Yes** (`/agmarknet/quantities`) |
| **License Terms** | National Data Sharing and Accessibility Policy (NDSAP) - Open Government Data | Government Public Portal | Non-commercial academic license (mandatory attribution) |

---

## 5. Implementation Example (Python Client)

The following script queries `data.gov.in` for Gujarat Groundnut prices using pagination:

```python
import os
import requests
import pandas as pd

API_KEY = os.getenv("DATA_GOV_IN_API_KEY", "YOUR_API_KEY_HERE")
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

def fetch_mandi_prices(state: str, commodity: str, limit: int = 1000):
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": 0,
        "filters[state]": state,
        "filters[commodity]": commodity,
    }
    
    records = []
    while True:
        response = requests.get(BASE_URL, params=params, timeout=15)
        if response.status_code == 403:
            raise PermissionError("data.gov.in API key is invalid or unauthorized.")
        response.raise_for_status()
        
        payload = response.json()
        batch = payload.get("records", [])
        if not batch:
            break
            
        records.extend(batch)
        total = int(payload.get("total", 0))
        
        params["offset"] += len(batch)
        if params["offset"] >= total or len(records) >= total:
            break
            
    df = pd.DataFrame(records)
    if not df.empty:
        df["min_price"] = pd.to_numeric(df["min_price"], errors="coerce")
        df["max_price"] = pd.to_numeric(df["max_price"], errors="coerce")
        df["modal_price"] = pd.to_numeric(df["modal_price"], errors="coerce")
        df["arrival_date"] = pd.to_datetime(df["arrival_date"], format="%d/%m/%Y", errors="coerce")
    return df

if __name__ == "__main__":
    try:
        df_gujarat = fetch_mandi_prices(state="Gujarat", commodity="Groundnut", limit=50)
        print(f"Fetched {len(df_gujarat)} records.")
        print(df_gujarat[["market", "variety", "arrival_date", "modal_price"]].head())
    except Exception as err:
        print(f"Error fetching data: {err}")
```

---

## 6. Maintenance & Updates Checklist

- [ ] Check if new resource UUIDs are issued upon annual portal refreshes on data.gov.in.
- [ ] Monitor rate limits (typical quota is 5,000–10,000 requests per key per 24-hour cycle).
- [ ] If arrival volumes (tonnes) are required for procurement order sizing, combine these prices with **CEDA API** (`/agmarknet/quantities`) or official **UPAg / e-NAM** feeds.
