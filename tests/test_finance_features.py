import unittest
from datetime import date, timedelta

from privatemoney.models import Account, Goal, Transaction
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

    def test_recurring_income_detection(self):
        state=FinanceState()
        transactions=[
            Transaction(date(2026,7,3),"PAYROLL","Income","Checking",1200.0,False,"p1"),
            Transaction(date(2026,7,17),"PAYROLL","Income","Checking",1200.0,False,"p2"),
            Transaction(date(2026,7,31),"PAYROLL","Income","Checking",1200.0,False,"p3"),
            Transaction(date(2026,8,14),"PAYROLL","Income","Checking",1200.0,False,"p4"),
            Transaction(date(2026,8,28),"PAYROLL","Income","Checking",1200.0,False,"p5"),
            Transaction(date(2026,9,11),"PAYROLL","Income","Checking",1200.0,False,"p6"),
        ]
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":transactions,"budgets":[],"goals":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        income=[r for r in state.recurring() if r.direction=="income"]
        self.assertEqual(len(income),1)
        self.assertEqual(income[0].cadence,"Every 2 weeks")
        self.assertEqual(income[0].merchant,"PAYROLL")

    def test_set_budget_uses_current_month_spending(self):
        state=FinanceState()
        today=date.today()
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":[
                Transaction(today,"Store","Groceries","Checking",-40.0,False,"b1"),
                Transaction(today,"Store","Groceries","Checking",-15.0,False,"b2"),
            ],
            "budgets":[],"goals":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        budget=state.set_budget("Groceries",200.0)
        self.assertEqual(budget.spent,55.0)
        self.assertEqual(budget.limit,200.0)

    def test_budget_delete_and_goal_update(self):
        state=FinanceState()
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1")],
            "transactions":[],"budgets":[],"goals":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        state.set_budget("Groceries",250.0)
        self.assertEqual(len(state.budgets()),1)
        self.assertTrue(state.delete_budget("groceries"))
        self.assertEqual(state.budgets(),[])

        original=Goal("goal-1","spent","merchant","Store",1,"month","less than",100.0)
        state.add_goal(original)
        updated=Goal("other-id","received","bank","Checking",1,"month","greater than",500.0)
        self.assertTrue(state.update_goal("goal-1",updated))
        saved=state.goals()[0]
        self.assertEqual(saved.id,"goal-1")
        self.assertEqual(saved.direction,"received")
        self.assertEqual(saved.scope_type,"bank")
        self.assertEqual(saved.target,500.0)

    def test_goal_status_filters_direction_scope_and_period(self):
        state=FinanceState()
        today=date.today()
        state.restore_snapshot({
            "source":"local",
            "accounts":[Account("a","Checking","checking","Bank",100.0,100.0,"1","Daily")],
            "transactions":[
                Transaction(today,"Walmart","Shopping","Checking",-40.0,False,"g1"),
                Transaction(today,"Walmart","Shopping","Checking",-25.0,False,"g2"),
                Transaction(today,"Payroll","Income","Checking",1000.0,False,"g3"),
            ],
            "budgets":[],"goals":[],"recurring":[],"net_worth":[],"cashflow":[],
        })
        goal=Goal("g","spent","merchant","Walmart",1,"month","less than",100.0)
        status=state.goal_status(goal)
        self.assertEqual(status["actual"],65.0)
        self.assertTrue(status["met"])

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
