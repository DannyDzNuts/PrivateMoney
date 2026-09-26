from __future__ import annotations
import json
import secrets
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from . import __version__


def _money_rows(rows):
    return [{"label": x[0], "value": x[1]} for x in rows]


class DashboardApiServer:
    def __init__(self, state, plaid, bearer_token: str, host: str = "127.0.0.1", port: int = 8765):
        self.state = state
        self.plaid = plaid
        self.bearer_token = bearer_token
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None

    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    def start(self):
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"PrivateMoneyAPI/{__version__}"

            def log_message(self, fmt, *args):
                return

            def _json(self, status, payload):
                raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

            def _html(self, status, html):
                raw = html.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'self' https://cdn.plaid.com; script-src 'self' 'unsafe-inline' https://cdn.plaid.com; style-src 'self' 'unsafe-inline'; frame-src https://*.plaid.com; connect-src 'self' https://*.plaid.com")
                self.end_headers()
                self.wfile.write(raw)

            def _authorized(self):
                expected = f"Bearer {server_ref.bearer_token}"
                supplied = self.headers.get("Authorization", "")
                return secrets.compare_digest(supplied, expected)

            def _finance_payload(self, path):
                st = server_ref.state
                if path == "/api/v1/summary":
                    return st.summary()
                if path == "/api/v1/accounts":
                    return {"source": st.source, "accounts": [asdict(x) for x in st.accounts()]}
                if path == "/api/v1/budgets":
                    return {"budgets": [asdict(x) for x in st.budgets()]}
                if path == "/api/v1/recurring":
                    return {"recurring": [asdict(x) for x in st.recurring()]}
                if path == "/api/v1/net-worth":
                    return {"source": st.source, "series": _money_rows(st.net_worth())}
                if path == "/api/v1/spending":
                    return {"source": st.source, "series": _money_rows(st.spending())}
                if path == "/api/v1/cash-flow":
                    return {"source": st.source, "series": [{"label": x[0], "income": x[1], "outflow": x[2]} for x in st.cashflow()]}
                return None

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                if path == "/api/v1/health":
                    return self._json(200, {"status": "ok", "version": __version__, "source": server_ref.state.source})
                if path.startswith("/plaid/link/"):
                    nonce = path.rsplit("/", 1)[-1]
                    link_token = server_ref.plaid.link_token_for(nonce)
                    if not link_token:
                        return self._html(404, "<h1>Link session expired</h1><p>Return to PrivateMoney and start again.</p>")
                    return self._html(200, plaid_link_page(nonce, link_token))
                if not path.startswith("/api/v1"):
                    return self._json(404, {"error": "not_found"})
                if not self._authorized():
                    return self._json(401, {"error": "unauthorized"})
                if path == "/api/v1":
                    return self._json(200, {
                        "name": "PrivateMoney Dashboard API",
                        "version": "v1",
                        "read_only": True,
                        "endpoints": ["summary", "accounts", "transactions", "budgets", "recurring", "net-worth", "spending", "cash-flow"],
                    })
                if path == "/api/v1/transactions":
                    q = parse_qs(parsed.query)
                    try:
                        limit = min(max(int(q.get("limit", [100])[0]), 1), 1000)
                    except ValueError:
                        limit = 100
                    rows = [asdict(x) for x in server_ref.state.transactions()[:limit]]
                    return self._json(200, {"source": server_ref.state.source, "transactions": rows, "count": len(rows)})
                payload = self._finance_payload(path)
                if payload is None:
                    return self._json(404, {"error": "not_found"})
                return self._json(200, payload)

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/")
                if not path.startswith("/plaid/exchange/"):
                    return self._json(405, {"error": "read_only_api"})
                nonce = path.rsplit("/", 1)[-1]
                length = min(int(self.headers.get("Content-Length", "0") or 0), 65536)
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                    public_token = body["public_token"]
                    result = server_ref.plaid.exchange_and_sync(nonce, public_token)
                    return self._json(200, result)
                except Exception as exc:
                    return self._json(400, {"ok": False, "error": str(exc)})

        last_error = None
        for candidate in range(self.port, self.port + 20):
            try:
                self._httpd = ThreadingHTTPServer((self.host, candidate), Handler)
                self.port = candidate
                break
            except OSError as exc:
                last_error = exc
        if not self._httpd:
            raise RuntimeError(f"Could not bind local dashboard API: {last_error}")
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="private-money-api", daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def plaid_link_page(nonce: str, link_token: str) -> str:
    token_js = json.dumps(link_token)
    nonce_js = json.dumps(nonce)
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Connect bank · PrivateMoney</title><script src=\"https://cdn.plaid.com/link/v2/stable/link-initialize.js\"></script>
<style>body{{margin:0;background:#000;color:#f5f2fa;font:16px system-ui;display:grid;place-items:center;min-height:100vh}}.c{{max-width:520px;background:#151519;border:1px solid #2d2d35;border-radius:18px;padding:28px}}button{{background:#bda0ff;color:#17121f;border:0;border-radius:10px;padding:12px 16px;font-weight:700}}p{{color:#a7a2ad;line-height:1.5}}</style></head>
<body><div class=\"c\"><h1>PrivateMoney</h1><p id=\"status\">Plaid Link is ready. Your bank sign-in happens inside Plaid's secure flow; PrivateMoney never receives your bank password.</p><button id=\"open\">Connect bank</button></div>
<script>
const token={token_js}, nonce={nonce_js};
const status=document.getElementById('status');
const handler=Plaid.create({{token,
 onSuccess: async (public_token)=>{{status.textContent='Connecting and syncing…'; document.getElementById('open').disabled=true;
   const r=await fetch('/plaid/exchange/'+encodeURIComponent(nonce),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{public_token}})}});
   const j=await r.json(); if(r.ok){{status.textContent='Connected. You can close this tab and return to PrivateMoney.';}} else {{status.textContent='Connection failed: '+(j.error||'Unknown error'); document.getElementById('open').disabled=false;}}
 }},
 onExit:(err)=>{{if(err) status.textContent='Plaid Link closed with an error. Return to PrivateMoney to retry.';}}
}});
document.getElementById('open').onclick=()=>handler.open();
</script></body></html>"""
