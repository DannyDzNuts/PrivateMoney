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
        self.assertEqual(body["version"],"0.6.0")

    def test_finance_requires_bearer(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.api.base_url+"/api/v1/summary")
        self.assertEqual(ctx.exception.code,401)

    def test_summary_authorized(self):
        req=urllib.request.Request(self.api.base_url+"/api/v1/summary",headers={"Authorization":"Bearer test-token"})
        with urllib.request.urlopen(req) as r:
            body=json.load(r)
        self.assertIn("net_worth",body); self.assertEqual(body["source"],"local")



    def test_plaid_request_builds_with_versioned_user_agent(self):
        bridge=PlaidBridge(FinanceState())
        bridge.configure("client-id","production-secret")

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return b'{"link_token":"link-production-test"}'

        captured={}
        original=urllib.request.urlopen
        def fake_urlopen(req,timeout=45):
            captured["url"]=req.full_url
            captured["user_agent"]=req.get_header("User-agent")
            captured["client_id"]=req.get_header("Plaid-client-id")
            captured["secret"]=req.get_header("Plaid-secret")
            return FakeResponse()
        urllib.request.urlopen=fake_urlopen
        try:
            result=bridge._request("/link/token/create",{"test":True})
        finally:
            urllib.request.urlopen=original

        self.assertEqual(result["link_token"],"link-production-test")
        self.assertEqual(captured["url"],"https://production.plaid.com/link/token/create")
        self.assertEqual(captured["user_agent"],"PrivateMoney/0.5.5")
        self.assertEqual(captured["client_id"],"client-id")
        self.assertEqual(captured["secret"],"production-secret")

    def test_plaid_configure_forces_production(self):
        bridge=PlaidBridge(FinanceState())
        bridge.configure("  client-id\n", " production-secret \n", "Sandbox")
        session=bridge.session_snapshot()
        self.assertEqual(session["client_id"],"client-id")
        self.assertEqual(session["secret"],"production-secret")
        self.assertEqual(session["environment"],"Production")

    def test_plaid_does_not_restore_old_sandbox_session(self):
        bridge=PlaidBridge(FinanceState())
        bridge.restore_session({
            "client_id":"client-id",
            "secret":"sandbox-secret",
            "environment":"Sandbox",
            "access_token":"access-sandbox-test",
            "item_id":"item",
            "cursor":None,
        })
        self.assertFalse(bridge.configured)
        self.assertFalse(bridge.connected)
        self.assertIn("Production",bridge.status)

    def test_plaid_refresh_then_sync(self):
        bridge=PlaidBridge(FinanceState())
        bridge._items["item-1"]={
            "access_token":"test-access-token","cursor":None,
            "accounts":[],"transactions":{},"institution_name":"Bank One"
        }
        calls=[]
        bridge._request=lambda path,payload,timeout=45: calls.append((path,timeout)) or {}
        bridge._sync_item=lambda item_id: calls.append(("sync-item",item_id))
        bridge._publish_merged_state=lambda: None
        bridge._merged_counts_locked=lambda: (0,0)
        result=bridge.refresh_and_sync()
        self.assertEqual(calls[0],("/transactions/refresh",75))
        self.assertEqual(calls[1],("sync-item","item-1"))
        self.assertEqual(result["synced_items"],1)

    def test_plaid_refresh_falls_back_when_product_unavailable(self):
        bridge=PlaidBridge(FinanceState())
        bridge._items["item-1"]={
            "access_token":"test-access-token","cursor":None,
            "accounts":[],"transactions":{},"institution_name":"Bank One"
        }
        calls=[]
        def unavailable(path,payload,timeout=45):
            calls.append((path,timeout))
            raise PlaidError("PRODUCT_NOT_ENABLED: Transactions Refresh is not enabled")
        bridge._request=unavailable
        bridge._sync_item=lambda item_id: calls.append(("sync-item",item_id))
        bridge._publish_merged_state=lambda: None
        bridge._merged_counts_locked=lambda: (0,0)
        result=bridge.refresh_and_sync()
        self.assertEqual(calls[-1],("sync-item","item-1"))
        self.assertEqual(result["synced_items"],1)

    def test_multiple_plaid_items_merge_without_wiping_each_other(self):
        state=FinanceState()
        bridge=PlaidBridge(state)
        bridge.configure("client-id","production-secret")
        bridge._items={
            "item-one":{
                "access_token":"token-one","cursor":None,
                "accounts":[],"transactions":{},"institution_name":"Bank One"
            },
            "item-two":{
                "access_token":"token-two","cursor":None,
                "accounts":[],"transactions":{},"institution_name":"Bank Two"
            },
        }

        def fake_request(path,payload,timeout=45):
            token=payload.get("access_token")
            suffix="1" if token=="token-one" else "2"
            if path=="/accounts/get":
                return {"accounts":[{
                    "account_id":"acct-"+suffix,
                    "name":"Checking "+suffix,
                    "type":"depository","subtype":"checking",
                    "balances":{"current":100*int(suffix),"available":90*int(suffix)},
                    "mask":"000"+suffix,
                }]}
            if path=="/transactions/sync":
                return {
                    "added":[{
                        "transaction_id":"tx-"+suffix,
                        "account_id":"acct-"+suffix,
                        "date":"2026-09-25",
                        "name":"Merchant "+suffix,
                        "amount":10*int(suffix),
                        "pending":False,
                    }],
                    "modified":[],"removed":[],
                    "next_cursor":"cursor-"+suffix,"has_more":False,
                }
            raise AssertionError(path)

        bridge._request=fake_request
        result=bridge.sync()
        self.assertEqual(result["items"],2)
        self.assertEqual(result["accounts"],2)
        self.assertEqual(len(state.accounts()),2)
        self.assertEqual({a.institution for a in state.accounts()},{"Bank One","Bank Two"})
        self.assertEqual(len(state.transactions()),2)

        # Updating only Bank Two's cache must leave Bank One visible.
        bridge._items["item-two"]["accounts"][0]["balances"]["current"]=250
        bridge._publish_merged_state()
        self.assertEqual(len(state.accounts()),2)
        self.assertIn("Checking 1",{a.name for a in state.accounts()})
        self.assertIn("Checking 2",{a.name for a in state.accounts()})

if __name__ == "__main__": unittest.main()
