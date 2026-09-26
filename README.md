# PrivateMoney

A local-first personal finance desktop application focused on private budgeting, transaction analysis, recurring-charge visibility, net-worth tracking, and an opt-in Plaid connection. PrivateMoney is designed so financial data can stay under the user's control rather than requiring a cloud-first account.


## Project status

PrivateMoney is under active development. The current build is a desktop prototype for Linux/Nobara with a polished Midnight Violet interface, local dashboard API, demo financial data, and a working Plaid Link integration scaffold.

Real financial data is not persisted yet. The encrypted SQLCipher vault is the next major milestone.

## Principles

- Local-first and single-user by default
- No telemetry, advertising, or cloud account requirement
- No plaintext fallback for sensitive persisted financial data
- Plaid is optional
- Dashboard API is read-only and localhost-only by default
- Secrets and bank credentials never belong in the repository

## Added in 0.2

- Versioned read-only Dashboard API on `127.0.0.1` only
- Per-launch bearer token; the API rejects unauthenticated finance-data requests
- API endpoints for summary, accounts, transactions, budgets, recurring charges, net worth, spending, and cash flow
- Plaid Link integration using the current `link_token -> public_token -> access_token` flow
- Plaid Transactions ingestion using `/transactions/sync` with cursor pagination
- Accounts screen and live UI refresh after Plaid sync
- Sandbox and Production environment support
- Plaid client secret, Item access token, and sync cursor are intentionally memory-only in this demo build
- Plaid bank credentials are entered only inside Plaid Link; PrivateMoney never receives them

## Privacy boundary

This build intentionally does **not** persist Plaid secrets, access tokens, or live transaction data. Closing the app clears the live Plaid session. This lets us demo the integration before the encrypted SQLCipher vault is completed.

The Dashboard API is bound to `127.0.0.1`, is read-only, and uses a random bearer token generated at every launch. It never returns Plaid credentials or access tokens.

## API

Open **Settings -> Dashboard API** to copy the current bearer token and a curl example.

Available endpoints:

- `GET /api/v1/health` (no financial data; no token required)
- `GET /api/v1`
- `GET /api/v1/summary`
- `GET /api/v1/accounts`
- `GET /api/v1/transactions?limit=100`
- `GET /api/v1/budgets`
- `GET /api/v1/recurring`
- `GET /api/v1/net-worth`
- `GET /api/v1/spending`
- `GET /api/v1/cash-flow`

All finance-data endpoints require `Authorization: Bearer <token>`.

## Plaid

Open **Settings -> Plaid bank connection**, choose Sandbox or Production, and enter your Plaid `client_id` and environment secret. Configuration is session-only.

Use **Connect bank** to open Plaid Link in the default browser. The local callback exchanges the temporary public token server-side, pulls accounts, and performs a paginated transaction sync. Live data replaces the demo snapshot in memory.

PrivateMoney requests 180 days of transaction history to support future recurring-charge analysis.

## Run

```bash
./install-user.sh
private-money
```

## Next persistence milestone

1. First-run encrypted vault creation.
2. Argon2id key derivation / local key handling.
3. SQLCipher persistence with no plaintext fallback.
4. Persist Plaid Item access tokens only inside the encrypted vault.
5. Persist `/transactions/sync` cursors and incremental transaction updates.
6. Add QFX/OFX and CSV import wizard.
7. Add local recurring detection and merchant/category rules.
8. Add explicit remote API binding only if needed for the future dashboard system.
