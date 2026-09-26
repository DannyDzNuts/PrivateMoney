import unittest
from datetime import date, timedelta

from privatemoney.models import Account, Transaction
from privatemoney.state import FinanceState


class FinanceFeatureTests(unittest.TestCase):
    def test_net_worth_history_uses_transaction_dates(self):
        state=FinanceState()
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",1000.0,1000.0,"1")],
            "transactions":[
                Transaction(date(2026,9,24),"Income","Income","Checking",100.0,False,"t1"),
                Transaction(date(2026,9,25),"Purchase","Dining","Checking",-50.0,False,"t2"),
                Transaction(date(2026,9,25),"Purchase 2","Shopping","Checking",-25.0,False,"t3"),
            ],
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        self.assertEqual(
            state.net_worth(),
            [("2026-09-24",1075.0),("2026-09-25",1000.0)],
        )

    def test_category_edit_is_preserved_across_plaid_refresh(self):
        state=FinanceState()
        original=Transaction(date(2026,9,25),"Shop","Shopping","Checking",-10.0,False,"tx-1")
        state.restore_snapshot({
            "source":"plaid",
            "accounts":[Account("a","Checking","checking","Bank",100.0,90.0,"1")],
            "transactions":[original],
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        self.assertTrue(state.set_transaction_category(original,"Dining"))
        incoming=Transaction(date(2026,9,25),"Shop","Other","Checking",-10.0,False,"tx-1")
        state.replace_with_plaid(
            [Account("a","Checking","checking","Bank",100.0,90.0,"1")],
            [incoming],
        )
        self.assertEqual(state.transactions()[0].category,"Dining")

    def test_account_nickname_survives_plaid_refresh(self):
        state=FinanceState()
        account=Account("a","Checking","checking","Bank",100.0,90.0,"1")
        state.restore_snapshot({
            "source":"plaid","accounts":[account],"transactions":[],
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        self.assertTrue(state.set_account_nickname("a","Daily"))
        self.assertEqual(state.account_display_name("Checking"),"Daily")
        state.replace_with_plaid(
            [Account("a","Checking","checking","Bank",110.0,100.0,"1")],
            [],
        )
        self.assertEqual(state.accounts()[0].nickname,"Daily")
        self.assertEqual(state.account_display_name("Checking"),"Daily")

    def test_bulk_merchant_category_updates_all_matching_transactions(self):
        state=FinanceState()
        rows=[
            Transaction(date(2026,9,1),"YouTube Premium","Other","Checking",-13.99,False,"y1"),
            Transaction(date(2026,8,1),"youtube premium","Other","Checking",-13.99,False,"y2"),
            Transaction(date(2026,9,2),"Other Merchant","Other","Checking",-5.0,False,"o1"),
        ]
        state.restore_snapshot({
            "source":"local","accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":rows,"budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        self.assertEqual(state.bulk_set_merchant_category("YOUTUBE PREMIUM","Subscriptions"),2)
        youtube=[tx for tx in state.transactions() if tx.merchant.casefold()=="youtube premium"]
        self.assertTrue(all(tx.category=="Subscriptions" for tx in youtube))
        self.assertEqual(next(tx for tx in state.transactions() if tx.merchant=="Other Merchant").category,"Other")

    def test_recurring_monthly_pattern_detection(self):
        state=FinanceState()
        transactions=[
            Transaction(date(2026,4,5),"STREAMCO","Subscriptions","Checking",-14.99,False,"r1"),
            Transaction(date(2026,5,5),"STREAMCO","Subscriptions","Checking",-14.99,False,"r2"),
            Transaction(date(2026,6,4),"STREAMCO","Subscriptions","Checking",-14.99,False,"r3"),
            Transaction(date(2026,7,5),"STREAMCO","Subscriptions","Checking",-14.99,False,"r4"),
            Transaction(date(2026,8,5),"STREAMCO","Subscriptions","Checking",-15.49,False,"r5"),
            Transaction(date(2026,9,4),"STREAMCO","Subscriptions","Checking",-14.99,False,"r6"),
        ]
        state.restore_snapshot({
            "source":"plaid",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":transactions,
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        rows=state.recurring()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].cadence,"Monthly")
        self.assertAlmostEqual(rows[0].amount,14.99,places=2)
        self.assertEqual(state.summary()["recurring_count"],1)

    def test_recurring_details_include_history_metrics(self):
        state=FinanceState()
        transactions=[
            Transaction(date(2026,6,1),"STREAMCO","Subscriptions","Checking",-10.0,False,"d1"),
            Transaction(date(2026,7,1),"STREAMCO","Subscriptions","Checking",-10.0,False,"d2"),
            Transaction(date(2026,8,1),"STREAMCO","Subscriptions","Checking",-10.0,False,"d3"),
            Transaction(date(2026,9,1),"STREAMCO","Subscriptions","Checking",-10.0,False,"d4"),
        ]
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":transactions,
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        details=state.recurring_details()
        self.assertEqual(len(details),1)
        self.assertEqual(details[0]["first_seen"],date(2026,6,1))
        self.assertEqual(details[0]["total_spent"],40.0)
        self.assertEqual(details[0]["occurrences"],4)
        self.assertEqual(details[0]["frequency_days"],30)

    def test_recurring_does_not_flag_irregular_spending(self):
        state=FinanceState()
        transactions=[
            Transaction(date(2026,4,1),"COFFEE SHOP","Dining","Checking",-5.0,False,"c1"),
            Transaction(date(2026,4,10),"COFFEE SHOP","Dining","Checking",-9.0,False,"c2"),
            Transaction(date(2026,5,2),"COFFEE SHOP","Dining","Checking",-4.0,False,"c3"),
            Transaction(date(2026,6,20),"COFFEE SHOP","Dining","Checking",-12.0,False,"c4"),
            Transaction(date(2026,9,1),"COFFEE SHOP","Dining","Checking",-7.0,False,"c5"),
        ]
        state.restore_snapshot({
            "source":"plaid",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":transactions,
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        self.assertEqual(state.recurring(),[])

    def test_spending_variance_compares_previous_month(self):
        today=date.today()
        previous_month_last=today.replace(day=1)-timedelta(days=1)
        state=FinanceState()
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":[
                Transaction(today,"Current","Dining","Checking",-80.0,False,"cur"),
                Transaction(previous_month_last,"Previous","Dining","Checking",-50.0,False,"prev"),
            ],
            "budgets":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        summary=state.summary()
        self.assertEqual(summary["month_spending"],80.0)
        self.assertEqual(summary["previous_month_spending"],50.0)
        self.assertEqual(summary["spending_variance"],30.0)


if __name__ == "__main__":
    unittest.main()
