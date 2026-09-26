# PrivateMoney

A local-first personal finance desktop application focused on private budgeting, transaction analysis, recurring-charge visibility, net-worth tracking, and an opt-in Plaid connection. PrivateMoney is designed so financial data can stay under the user's control rather than requiring a cloud-first account.


## Project status

PrivateMoney is under active development. The current build is a desktop prototype for Linux/Nobara with a polished Midnight Violet interface, local dashboard API, local sample data, and a working Plaid Link integration scaffold.

PrivateMoney now includes an encrypted SQLCipher vault for local persistence. The next persistence work is startup unlock UX, migrations, and explicit encrypted backup/export.

## Principles

- Local-first and single-user by default
- No telemetry, advertising, or cloud account requirement
- No plaintext fallback for sensitive persisted financial data
- Plaid is optional
- Dashboard API is read-only and localhost-only by default
- Secrets and bank credentials never belong in the repository

## Added in 0.5

- Guided statement import from CSV, QFX, and OFX files
- CSV column mapping for date, description, and amount
- Automatic column guesses for common bank CSV exports
- Optional CSV amount-sign inversion
- Statement preview before import
- Import into an existing account or create a local account by typing a new name
- Duplicate prevention using stable source/account transaction IDs
- Statement importing requires PrivateMoney to be unlocked

## Added in 0.4.1

- First-run **Create password** prompt when no local vault exists
- Persistent lock/unlock button at the top-right of every screen
- Locking saves current state, closes the vault, clears Plaid secrets, and removes financial data from the visible session
- Unlocking prompts for the password and restores saved state
- Settings now uses a simple **Log out** action instead of developer-facing vault controls

## Added in 0.4

- Mouse-wheel navigation over the left navigation pane switches pages one step at a time
- Navigation clamps at Overview and Settings rather than wrapping unexpectedly
- SQLCipher encrypted vault with Argon2id passphrase key derivation
- Vault create, unlock, and lock controls in Settings
- Encrypted persistence for finance state and Plaid developer credentials/session tokens
- No plaintext SQLite fallback
- Normal launches start with an empty local state; sample data is developer-only via PRIVATE_MONEY_SAMPLE_DATA=1

## Added in 0.3

- Scrollable spending-mix legend so long category lists stay inside their card
- Transparent budget-row/card-body treatment for consistent Midnight Violet cards
- Clear three-stage Plaid setup flow: API credentials, Link, then refresh/sync
- On-demand `/transactions/refresh` before `/transactions/sync` when the optional Plaid product is available
- Graceful fallback to Plaid's latest cached transaction data when on-demand refresh is unavailable
- More explicit Plaid connection and sync status messaging

## Added in 0.2

- Versioned read-only Dashboard API on `127.0.0.1` only
- Per-launch bearer token; the API rejects unauthenticated finance-data requests
- API endpoints for summary, accounts, transactions, budgets, recurring charges, net worth, spending, and cash flow
- Plaid Link integration using the current `link_token -> public_token -> access_token` flow
- Plaid Transactions ingestion using `/transactions/sync` with cursor pagination
- Accounts screen and live UI refresh after Plaid sync
- Sandbox and Production environment support
- Plaid client secret, Item access token, and sync cursor are intentionally memory-only in the current development build
- Plaid bank credentials are entered only inside Plaid Link; PrivateMoney never receives them

## Privacy boundary

This build intentionally does **not** persist Plaid secrets, access tokens, or live transaction data. Closing the app clears the live Plaid session. This keeps the integration safe while the encrypted SQLCipher vault is being completed.

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

Use **Connect bank** to open Plaid Link in the default browser. The local callback exchanges the temporary public token server-side, pulls accounts, and performs a paginated transaction sync. Live data replaces the local sample snapshot in memory.

PrivateMoney requests 180 days of transaction history to support future recurring-charge analysis.

## Run

```bash
./install-user.sh
private-money
```

## Next milestones

1. Startup vault-unlock UX and schema migrations.
2. QFX/OFX and CSV import wizard.
3. Local recurring detection and merchant/category rules.
4. Budget creation/editing and category management.
5. Explicit encrypted backup/export.
6. Optional remote API transport only when the future dashboard system needs it.
