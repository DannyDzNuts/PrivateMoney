import json
import unittest
import urllib.error
import urllib.request
from privatemoney.api import DashboardApiServer
from privatemoney.plaid import PlaidBridge, PlaidError
from privatemoney.state import FinanceState


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.state=FinanceState(); self.plaid=PlaidBridge(self.state)
        self.api=DashboardApiServer(self.state,self.plaid,"test-token",port=18976); self.api.start()
    def tearDown(self): self.api.stop()

    def test_health(self):
        with urllib.request.urlopen(self.api.base_url+"/api/v1/health") as r:
            body=json.load(r)
        self.assertEqual(body["status"],"ok")
        self.assertEqual(body["version"],"0.5.2")

    def test_finance_requires_bearer(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.api.base_url+"/api/v1/summary")
        self.assertEqual(ctx.exception.code,401)

    def test_summary_authorized(self):
        req=urllib.request.Request(self.api.base_url+"/api/v1/summary",headers={"Authorization":"Bearer test-token"})
        with urllib.request.urlopen(req) as r:
            body=json.load(r)
        self.assertIn("net_worth",body); self.assertEqual(body["source"],"local")



    def test_plaid_refresh_then_sync(self):
        bridge=PlaidBridge(FinanceState())
        bridge._access_token="test-access-token"
        calls=[]
        bridge._request=lambda path,payload,timeout=45: calls.append((path,timeout)) or {}
        bridge.sync=lambda: calls.append(("sync",None)) or {"accounts":0,"transactions":0}
        result=bridge.refresh_and_sync()
        self.assertEqual(calls[0],("/transactions/refresh",75))
        self.assertEqual(calls[1],("sync",None))
        self.assertEqual(result["transactions"],0)

    def test_plaid_refresh_falls_back_when_product_unavailable(self):
        bridge=PlaidBridge(FinanceState())
        bridge._access_token="test-access-token"
        calls=[]
        def unavailable(path,payload,timeout=45):
            calls.append((path,timeout))
            raise PlaidError("PRODUCT_NOT_ENABLED: Transactions Refresh is not enabled")
        bridge._request=unavailable
        bridge.sync=lambda: calls.append(("sync",None)) or {"accounts":0,"transactions":0}
        result=bridge.refresh_and_sync()
        self.assertEqual(calls[-1],("sync",None))
        self.assertEqual(result["accounts"],0)

if __name__ == "__main__": unittest.main()
