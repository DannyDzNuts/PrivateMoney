# Security

PrivateMoney handles sensitive financial information. Please do not commit, post, or include in issues:

- Plaid client secrets
- Plaid access tokens, public tokens, or Link tokens
- bank credentials
- exported statements or transaction files
- dashboard API bearer tokens
- encryption keys or vault files

When the encrypted vault is unlocked, Plaid developer credentials, Item access tokens, sync cursors, and financial data are persisted inside SQLCipher. Without an unlocked vault, sensitive session data remains memory-only. Plaintext SQLite fallback is intentionally disabled.

If you discover a security issue, avoid publishing sensitive reproduction data in a public issue.
