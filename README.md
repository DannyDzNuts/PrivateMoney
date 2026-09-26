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

## Added in 0.15

- Removed the redundant **Latest 5** subtitle from Overview Recent Transactions
- Recent Transactions now reserves exactly five rows and disables internal scrollbars
- Active tab title and tagline moved into the global top bar beside the vault login/logout control
- Page bodies no longer repeat their title/tagline, freeing vertical space for content
- Main window now grows to the active page's preferred size and maximizes when that size approaches the usable screen boundary

## Added in 0.14

- Centered standard table text and headers across PrivateMoney, including transaction/account/recurring/import tables
- Centered the editable transaction-category selector and account nickname editor inside their table cells
- Budgets now use a shorter fixed-width progress bar and compact dollar progress label
- Added an **Edit** button to every budget row on Budgets & Goals
- Budget edit dialog supports category/limit changes and includes a confirmed **Delete budget** action
- Added **Edit** controls for monetary goals while retaining quick delete
- Goal edit dialog preloads the current rule and saves changes back to the existing goal
- Overview now includes the five most recent transactions in a compact table
- Recent transaction account names respect account nicknames

## Added in 0.13

- Net-worth trajectory badge now shows only the percentage change because the selected range is already visible beside it
- Overview metric cards are taller so large primary values are not clipped
- Account nickname rows/editors are taller so input text is fully visible
- Recurring card titles are now simply **Spending** and **Income**
- Recurring Income no longer includes a Category column
- Recurring table cells, including monetary values, are centered consistently
- Bulk categorization moved to a compact header button and popup dialog, freeing vertical room for the transaction list
- Transactions pie and cash-flow charts are shorter
- Pie layout now reserves measured left/right label gutters so long external slice labels stay inside the chart
- Sidebar tab glyphs are rendered as larger icons independently of label text

## Added in 0.12

- Renamed **Budgets** to **Budgets & Goals**
- **New budget** now creates/updates a real monthly category budget instead of being disabled
- Added persisted monetary goals using rules such as amount spent/received at/from a merchant, bank/account, or category over a configurable period compared with a target amount
- Goal progress is evaluated against the current transaction history and stored inside the encrypted vault
- Net-worth best-fit trajectory now shows its percentage change for the selected 1M / 3M / 6M / 1Y / All range
- Recurring detection now includes positive transactions such as paychecks
- Recurring spending and recurring income are displayed in separate sortable tables
- Rebuilt the Transactions category selector as one custom in-field tag control with a fixed attached drop arrow and deterministic horizontal scrolling
- Removing a category tag preserves the current horizontal scroll position
- Advanced Transactions filters inherit the filter-card background and date/number controls use the normal app theme
- Expanded the Transactions category chart area so external leader labels are not clipped

## Added in 0.11

- Overview net worth adds a straight best-fit trajectory line: green for upward trend, red for downward trend
- Accounts gives the nickname editor substantially more width
- Category filtering is now a fixed-width in-field tag control with removable tags, persistent drop arrow, search, and horizontal wheel scrolling
- Transactions filters are a collapsible card: common filters remain visible and date/dollar filters expand on demand
- Bulk-categorization merchant/category controls ignore mouse-wheel changes
- Recurring adds sortable history metrics for first seen, age, price, total spent, cadence frequency, occurrence count, and next due date
- Recurring history metrics are derived from the underlying matched transactions rather than only the next predicted charge

## Added in 0.10

- Overview gives the category pie and Budgets more horizontal room while Net worth and Cash flow share the narrower width
- Pie percentages use adaptive radial placement to reduce overlap
- Removed the old standalone Transactions tab and renamed the former Reports workspace to **Transactions**
- Transaction category dropdowns now live in the consolidated Transactions workspace
- Transactions defaults to the oldest tracked transaction through today's date
- Multi-category filtering uses removable searchable category tags
- Merchant-wide bulk recategorization can update every matching transaction at once
- Accounts support encrypted, autosaved nicknames; nicknames replace account names elsewhere in the UI without changing bank/account identity
- Account nicknames survive Plaid refreshes and vault restarts
- Fixed recurring rows that could visually retain the empty-state table span and hide category/cadence/amount fields

## Added in 0.9

- Overview and Reports category pies use external leader-line labels instead of a separate legend
- Pie slices show percentage values inside each slice and explode farther as their share increases
- Removed the standalone **Net worth** navigation tab; net-worth history remains on Overview
- Transaction category dropdowns ignore mouse-wheel selection changes
- Reports support combinable category, history-window, date-range, dollar-range, account, and merchant filters
- Report charts, statistics, and transaction rows all use the same active filter set

## Added in 0.8

- Overview net-worth duration control: 1M, 3M, 6M, 1Y, or All
- Overview net-worth line hides point dots and shows nearest transaction-date value on hover
- Overview category card renamed to **Categories · Last month**
- Category spending visualization is now an exploded full-slice pie chart
- Cash-flow bars show dollar values directly inside the income/spending bars
- **This Month's Spending** variance tagline no longer includes a redundant "Variance:" prefix
- Local recurring-pattern detection for weekly, biweekly, monthly, quarterly, and annual outgoing charges
- Recurring detection recomputes after Plaid sync, imports, restore, and category changes
- Existing vaults prompt for login when PrivateMoney starts

## Added in 0.7

- Net-worth history is reconstructed immediately from current balances and transaction dates
- Multiple transactions on the same day become one end-of-day net-worth point
- This-month spending card shows dollar variance versus the previous month
- Cash-flow charts use green for income and red for spending
- Sharper, more saturated Midnight Violet accent palette
- Reports can filter by category and show matching transactions
- Transaction categories are editable from a dropdown in the Transactions table
- Manual category changes persist locally and survive later Plaid syncs

## Added in 0.6

- Multiple Plaid Items/banks are retained simultaneously instead of the newest bank replacing the previous one
- Each linked bank keeps its own encrypted access token, sync cursor, account cache, and transaction cache
- Sync merges all linked banks before publishing finance state
- Sync failure for one bank no longer erases healthy banks
- Legacy single-Item vaults migrate the last retained Item automatically and rebuild its cache on first sync
- Plaid Link institution names are retained for the Accounts view
- Plaid refreshes preserve statement-imported local accounts and transactions

## Added in 0.5.5

- Fixed Plaid request construction referencing an undefined application version at runtime
- Added a regression test for the real Plaid HTTP request path, including Production endpoint and User-Agent construction

## Added in 0.5.4

- Create-password Return/Enter handling now intercepts the actual Qt key event and cannot trigger an auto-default submit button
- Plaid is Production-only; the Sandbox/Production selector has been removed
- Pasted Plaid credentials are normalized for stray whitespace/newlines
- Older saved Sandbox Plaid sessions are not reused against Production
- Plaid API errors now preserve actionable error codes and request IDs
- Added a packaged PrivateMoney SVG application logo

## Added in 0.5.3

- Password creation stays open and warns inline when confirmation is missing or mismatched
- Enter in the first password field advances to confirmation instead of prematurely submitting
- Destructive confirmation and forgot-password buttons have stable readable sizing
- Simplified geometric lock/unlock icon and quieter top-bar button styling
- Import customization panel has stable field widths and transparent card-matched background
- Import customization scrolls internally instead of forcing the whole dialog off-screen
- Removed the Appearance description from Settings

## Added in 0.5.2

- Vector-drawn persistent lock/unlock icon that does not depend on emoji font support
- Settings Access button switches between **Log in** and **Log out**
- Red **DELETE DATA** action with destructive confirmation
- Red **FORGOT PASSWORD** action on the unlock dialog
- Passwords are never recoverable or resettable; forgotten-password recovery deletes the encrypted local data and starts fresh
- Dashboard API controls moved behind session-only **Enable Developer Settings** confirmation
- Plaid connection controls remain visible in normal Settings

## Added in 0.5.1

- Custom CSV mapping per import with explicit **Not set** defaults
- Support for both single Amount fields and separate Debit / Credit fields
- Optional Account and Balance mappings
- Optional per-row account routing using the mapped Account field
- Running Balance can update the imported account's latest balance
- **Save as default** remembers a mapping for matching CSV header layouts inside the encrypted local store
- Automatic Debit/Credit detection for common bank exports
- Prevents accidental fallback to the first CSV column when an Amount field cannot be identified

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
