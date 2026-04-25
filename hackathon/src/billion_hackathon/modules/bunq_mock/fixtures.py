"""Mock bunq payment data — Story 1 (De Kroeg bar, 3 friends).

Bart (user 3629697, account 3621895) paid €9.99 for 3 beers.
Alex and Charlie were present (see selfie + receipt).
"""

STORY1_USER_ID = 3629697
STORY1_ACCOUNT_ID = 3621895

# Trimmed bunq Payment shape:
# id, created, monetary_account_id, amount, description, type,
# alias (payer), counterparty_alias (payee), balance_after_mutation
STORY1_PAYMENTS = [
    {
        "Payment": {
            "id": 847291,
            "created": "2026-03-03 21:31:42.000000",
            "updated": "2026-03-03 21:31:42.000000",
            "monetary_account_id": STORY1_ACCOUNT_ID,
            "amount": {"value": "-9.99", "currency": "EUR"},
            "description": "De Kroeg",
            "type": "BUNQ",
            "alias": {
                "iban": "NL77BUNQ2063799744",
                "display_name": "Bart",
            },
            "counterparty_alias": {
                "iban": "NL42BUNQ9876543210",
                "display_name": "De Kroeg",
            },
            "balance_after_mutation": {"value": "990.01", "currency": "EUR"},
        }
    }
]
