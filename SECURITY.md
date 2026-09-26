# Security

PrivateMoney handles sensitive financial information. Please do not commit, post, or include in issues:

- Plaid client secrets
- Plaid access tokens, public tokens, or Link tokens
- bank credentials
- exported statements or transaction files
- dashboard API bearer tokens
- encryption keys or vault files

The current development build keeps Plaid secrets, access tokens, sync cursors, and live financial data in process memory only. Persistent live data is intentionally deferred until the encrypted vault is complete.

If you discover a security issue, avoid publishing sensitive reproduction data in a public issue.
