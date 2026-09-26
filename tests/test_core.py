import json
import unittest
import urllib.error
import urllib.request
from privatemoney.api import DashboardApiServer
from privatemoney.plaid import PlaidBridge
from privatemoney.state import FinanceState


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.state=FinanceState(); self.plaid=PlaidBridge(self.state)
        self.api=DashboardApiServer(self.state,self.plaid,"test-token",port=18976); self.api.start()
    def tearDown(self): self.api.stop()

    def test_health(self):
        with urllib.request.urlopen(self.api.base_url+"/api/v1/health") as r:
            self.assertEqual(json.load(r)["status"],"ok")

    def test_finance_requires_bearer(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.api.base_url+"/api/v1/summary")
        self.assertEqual(ctx.exception.code,401)

    def test_summary_authorized(self):
        req=urllib.request.Request(self.api.base_url+"/api/v1/summary",headers={"Authorization":"Bearer test-token"})
        with urllib.request.urlopen(req) as r:
            body=json.load(r)
        self.assertIn("net_worth",body); self.assertEqual(body["source"],"demo")


if __name__ == "__main__": unittest.main()
