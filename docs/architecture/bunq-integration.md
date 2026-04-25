# bunq Integration — Implementation Guide

This document covers everything needed to replace the local mock (`bunq_mock` module) with real bunq sandbox / production calls. Read alongside the module README at [`../../hackathon/src/billion_hackathon/modules/bunq_mock/README.md`](../../hackathon/src/billion_hackathon/modules/bunq_mock/README.md).

---

## Current state (mock)

The app ships a **local mock endpoint** that returns hardcoded Story 1 payment data:

```
GET /api/mock/bunq/v1/user/{user_id}/monetary-account/{account_id}/payment
```

All pipeline modules downstream (ingestion → aggregation → graph → compute) are already wired to this shape. Switching to real bunq changes **only** how the payment list is fetched — nothing else.

---

## bunq sandbox credentials (already created)

| Field | Value |
|-------|-------|
| Sandbox base URL | `https://public-api.sandbox.bunq.com/v1` |
| User ID | `3629697` |
| Monetary Account ID | `3621895` |
| API key | stored in `.env` as `BUNQ_API_KEY` (never commit) |
| Environment | `BUNQ_ENV=sandbox` |

---

## Real API endpoint

```
GET https://public-api.sandbox.bunq.com/v1/user/{user_id}/monetary-account/{account_id}/payment
```

### Required headers

| Header | Value / Notes |
|--------|---------------|
| `Content-Type` | `application/json` |
| `Cache-Control` | `no-cache` |
| `User-Agent` | any string identifying the app |
| `X-Bunq-Language` | `en_US` |
| `X-Bunq-Region` | `nl_NL` |
| `X-Bunq-Client-Request-Id` | unique UUID per request (generate with `uuid.uuid4().hex`) |
| `X-Bunq-Geolocation` | `0 0 0 0 000` (acceptable placeholder) |
| `X-Bunq-Client-Authentication` | session token from `.env` as `BUNQ_API_KEY` |
| `X-Bunq-Client-Signature` | RSA signature of the request (see §Authentication below) |

### Optional query parameters

| Parameter | Description |
|-----------|-------------|
| `count` | Number of payments to return (default 10, max 200) |
| `newer_id` | Return only payments with id > this value (pagination) |
| `older_id` | Return only payments with id < this value (pagination) |

---

## Response shape

The real API returns the same structure as the mock:

```json
{
  "Response": [
    {
      "Payment": {
        "id": 847291,
        "created": "2026-03-03 21:31:42.000000",
        "updated": "2026-03-03 21:31:42.000000",
        "monetary_account_id": 3621895,
        "amount": { "value": "-9.99", "currency": "EUR" },
        "description": "De Kroeg",
        "type": "BUNQ",
        "alias": {
          "iban": "NL77BUNQ2063799744",
          "display_name": "Bart"
        },
        "counterparty_alias": {
          "iban": "NL42BUNQ9876543210",
          "display_name": "De Kroeg"
        },
        "balance_after_mutation": { "value": "990.01", "currency": "EUR" }
      }
    }
  ]
}
```

**Amount sign convention:** negative = outgoing (Bart paid), positive = incoming (someone paid Bart).

---

## Authentication

bunq uses a **two-layer auth** model:

### Layer 1 — Installation (one time)
1. Generate an RSA key pair (2048-bit minimum).
2. `POST /v1/installation` with your public key → receive an **installation token**.
3. Store the installation token; it doesn't expire.

### Layer 2 — Session (per session or daily)
1. `POST /v1/device-server` with the installation token and your API key → register the device.
2. `POST /v1/session-server` with the installation token and API key → receive a **session token**.
3. Use the session token as `X-Bunq-Client-Authentication` in all subsequent requests.
4. Sessions expire after **1 hour** of inactivity (sandbox) — re-create on 401.

### Request signing (`X-Bunq-Client-Signature`)
Every non-GET request (and optionally GETs) must be signed with your RSA private key:
1. Build the signing payload: `METHOD\nPATH\n\nHEADER1: value\nHEADER2: value\n\nBODY`.
2. Sign with RSA-SHA256.
3. Base64-encode the signature.
4. Set as `X-Bunq-Client-Signature`.

For the hackathon prototype, **GET requests without a body** can often be made without a signature in sandbox mode — but implement signing before going to production.

---

## Implementation plan

### Step 1 — `BunqClient` service

Create `hackathon/src/billion_hackathon/modules/bunq_mock/bunq_client.py`:

```python
import os, uuid, requests

BUNQ_BASE = "https://public-api.sandbox.bunq.com/v1"

class BunqClient:
    def __init__(self) -> None:
        self._token = os.environ["BUNQ_API_KEY"]
        self._base  = os.getenv("BUNQ_BASE_URL", BUNQ_BASE)

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "dutchie/0.1",
            "X-Bunq-Language": "en_US",
            "X-Bunq-Region": "nl_NL",
            "X-Bunq-Client-Request-Id": uuid.uuid4().hex,
            "X-Bunq-Geolocation": "0 0 0 0 000",
            "X-Bunq-Client-Authentication": self._token,
        }

    def list_payments(self, user_id: int, account_id: int, count: int = 50) -> list[dict]:
        url = f"{self._base}/user/{user_id}/monetary-account/{account_id}/payment"
        resp = requests.get(url, headers=self._headers(), params={"count": count}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("Response", [])
```

### Step 2 — Add `BUNQ_BASE_URL` to `.env.example`

```
# BUNQ_BASE_URL=https://public-api.sandbox.bunq.com/v1
```

This lets you point at sandbox or a local WireMock/Prism mirror without code changes.

### Step 3 — Update `router.py`

Switch the endpoint from static fixture to `BunqClient`:

```python
import os
from .bunq_client import BunqClient
from .fixtures import STORY1_PAYMENTS  # keep as fallback

@router.get("/user/{user_id}/monetary-account/{account_id}/payment")
async def list_payments(user_id: int, account_id: int) -> JSONResponse:
    if os.getenv("BUNQ_API_KEY"):
        payments = BunqClient().list_payments(user_id, account_id)
        return JSONResponse({"Response": payments})
    return JSONResponse({"Response": STORY1_PAYMENTS})  # mock fallback
```

### Step 4 — Feed payments into the pipeline

Map each bunq `Payment` to a `CollectedItem` with `kind="note"` using the `EXPENSE:` format that `DataIngestionService` already understands:

```python
def payment_to_note(p: dict) -> str:
    pay = p["Payment"]
    cents = abs(int(float(pay["amount"]["value"]) * 100))
    label = pay.get("description", "payment")
    payer = pay["alias"]["display_name"].lower()
    return f"EXPENSE: {cents} cents for {label} payer={payer}"
```

Or create a dedicated `CollectedItem` kind `bunq_payment` and handle it in `DataIngestionService._process_item`.

### Step 5 — Session refresh (production hardening)
- Wrap `BunqClient` calls in a retry that re-authenticates on `401 Unauthorized`.
- Cache the session token in memory (or `SCENARIO_CACHE_FILE`) with a TTL.

---

## Filtering payments to the event window

The pipeline is scoped to an **Event** (time window + participants). When fetching real payments, filter by:

```python
# Only fetch payments within the event date range
params = {
    "count": 200,
    # bunq does not support date filtering directly —
    # fetch by count and filter client-side by `created`:
}
payments = [
    p for p in raw
    if event.start <= parse_datetime(p["Payment"]["created"]) <= event.end
]
```

---

## Environment variables (full set)

Add to `.env` (never commit):

```
# bunq
BUNQ_API_KEY=<session-token-from-sandbox>
BUNQ_ENV=sandbox
BUNQ_BASE_URL=https://public-api.sandbox.bunq.com/v1
```

---

## Testing without a live key

The mock endpoint (`/api/mock/bunq/v1/...`) remains available when `BUNQ_API_KEY` is not set. All existing Story 1 / Story 2 tests continue to pass unchanged — the real client is only activated when the key is present.

---

## References

- bunq API docs: https://doc.bunq.com/
- Sandbox payment request example: `POST /v1/user/3629697/monetary-account/3621895/request-inquiry`
- Mock module: [`../../hackathon/src/billion_hackathon/modules/bunq_mock/`](../../hackathon/src/billion_hackathon/modules/bunq_mock/)
- Pipeline contracts: [`../../hackathon/src/billion_hackathon/contracts/`](../../hackathon/src/billion_hackathon/contracts/)
- LLM module (for ingestion after fetch): [`../../hackathon/src/billion_hackathon/modules/llm/README.md`](../../hackathon/src/billion_hackathon/modules/llm/README.md)
