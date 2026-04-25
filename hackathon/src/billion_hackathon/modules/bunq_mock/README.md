# Module: `bunq_mock`

## Responsibility

Serve a **local mock of the bunq Payments API** so the rest of the pipeline can be developed and tested without a live sandbox key or network connection.

The mock mirrors the **URL shape** of the real bunq sandbox, so switching to the real API later is a one-line host change.

---

## Endpoint

```
GET /api/mock/bunq/v1/user/{user_id}/monetary-account/{account_id}/payment
```

**Equivalent real sandbox URL:**
```
GET https://public-api.sandbox.bunq.com/v1/user/{user_id}/monetary-account/{account_id}/payment
```

### Example request

```bash
curl http://127.0.0.1:8080/api/mock/bunq/v1/user/3629697/monetary-account/3621895/payment
```

### Response shape (trimmed bunq `Payment` object)

```json
{
  "Response": [
    {
      "Payment": {
        "id": 847291,
        "created": "2026-03-03 21:31:42.000000",
        "updated": "2026-03-03 21:31:42.000000",
        "monetary_account_id": 3621895,
        "amount": {
          "value": "-9.99",
          "currency": "EUR"
        },
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
        "balance_after_mutation": {
          "value": "990.01",
          "currency": "EUR"
        }
      }
    }
  ]
}
```

**Amount sign convention** (matches real bunq): negative = outgoing, positive = incoming.

---

## Current fixture — Story 1

| Field | Value |
|-------|-------|
| Scenario | Bar night at De Kroeg, Amsterdam |
| Date | 2026-03-03 21:31 |
| Payer | Bart (`user 3629697`, account `3621895`) |
| Payee | De Kroeg |
| Amount | −€9.99 (3 beers, €3.33 each) |
| Participants present | Alex, Bart, Charlie (see selfie + receipt in `Story/1/`) |

---

## Files

| File | Purpose |
|------|---------|
| `fixtures.py` | Static payment data keyed by story |
| `router.py` | FastAPI `APIRouter` — registers the mock endpoint |
| `__init__.py` | Package marker |

---

## Adding more fixtures

To add Story 2 (or any other scenario), extend `fixtures.py`:

```python
STORY2_PAYMENTS = [
    {
        "Payment": {
            "id": 912345,
            "created": "2026-04-01 20:15:00.000000",
            ...
        }
    }
]
```

Then update `router.py` to select the right fixture based on `user_id` / `account_id`, or add a query parameter `?story=2`.

---

## Migrating to the real bunq sandbox

See [`../../../../../docs/architecture/bunq-integration.md`](../../../../../docs/architecture/bunq-integration.md) for the full implementation plan.

**Short version:** replace the mock host with the real sandbox host and add the required bunq headers (`X-Bunq-Client-Authentication`, etc.). The response shape is already compatible — no contract changes needed downstream.

---

## Contract

- Input: `user_id` (int), `account_id` (int) — path parameters, currently ignored (always returns Story 1 fixture)
- Output: `{"Response": [{"Payment": {...}}, ...]}` — list of trimmed bunq `Payment` objects
