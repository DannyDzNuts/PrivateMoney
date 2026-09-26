import stat
import tempfile
import unittest
from datetime import date
from pathlib import Path

from privatemoney.models import Account, Budget, RecurringCharge, Transaction
from privatemoney.plaid import PlaidBridge
from privatemoney.state import FinanceState
from privatemoney.storage import VaultError, VaultManager


class VaultTests(unittest.TestCase):
    def test_destroy_removes_vault_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=VaultManager(Path(tmp))
            vault.create("correct horse battery staple")
            self.assertTrue(vault.exists)
            vault.destroy()
            self.assertFalse(vault.unlocked)
            self.assertFalse(vault.exists)
            self.assertFalse(vault.db_path.exists())
            self.assertFalse(vault.salt_path.exists())

    def test_encrypted_round_trip_and_wrong_passphrase(self):
        passphrase = "correct horse battery staple"

        with tempfile.TemporaryDirectory() as tmp:
            vault = VaultManager(Path(tmp))
            vault.create(passphrase)

            self.assertTrue(vault.unlocked)
            self.assertTrue(vault.exists)
            self.assertNotEqual(vault.db_path.read_bytes()[:16], b"SQLite format 3\x00")
            self.assertEqual(stat.S_IMODE(vault.salt_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(vault.db_path.stat().st_mode), 0o600)

            state = FinanceState()
            state.restore_snapshot(
                {
                    "source": "local",
                    "accounts": [
                        Account(
                            "acct-1",
                            "Checking",
                            "checking",
                            "Test Institution",
                            1234.56,
                            1200.00,
                            "1234",
                        )
                    ],
                    "transactions": [
                        Transaction(
                            date(2026, 9, 25),
                            "Test Merchant",
                            "Dining",
                            "Checking",
                            -42.18,
                            False,
                            "tx-1",
                        )
                    ],
                    "budgets": [Budget("Dining", 42.18, 200.00)],
                    "recurring": [
                        RecurringCharge(
                            "Test Service",
                            12.99,
                            "Monthly",
                            date(2026, 10, 1),
                            "Subscriptions",
                        )
                    ],
                    "net_worth": [("Sep", 1234.56)],
                    "cashflow": [("Sep", 2000.00, 765.44)],
                }
            )

            plaid = PlaidBridge(state)
            plaid.configure("client-id", "secret-value")
            with plaid._lock:
                plaid._items["item-id"] = {
                    "access_token": "access-token",
                    "cursor": "cursor-value",
                    "accounts": [],
                    "transactions": {},
                    "institution_name": "Test Bank",
                }
                plaid._items["item-id-2"] = {
                    "access_token": "access-token-2",
                    "cursor": "cursor-value-2",
                    "accounts": [],
                    "transactions": {},
                    "institution_name": "Second Bank",
                }

            profile={"amount_mode":"split","debit_col":"Debit","credit_col":"Credit"}
            vault.save_import_profile("headersig", profile)
            self.assertEqual(vault.load_import_profile("headersig"), profile)

            vault.save_runtime(state, plaid)
            vault.lock()

            with self.assertRaises(VaultError):
                vault.unlock("this is the wrong passphrase")

            vault.unlock(passphrase)
            restored_state = FinanceState()
            restored_plaid = PlaidBridge(restored_state)
            self.assertTrue(vault.restore_runtime(restored_state, restored_plaid))

            self.assertEqual(restored_state.accounts()[0].name, "Checking")
            self.assertEqual(restored_state.transactions()[0].external_id, "tx-1")
            self.assertEqual(restored_state.budgets()[0].limit, 200.00)

            session = restored_plaid.session_snapshot()
            self.assertEqual(session["client_id"], "client-id")
            self.assertEqual(session["secret"], "secret-value")
            self.assertEqual(len(session["items"]), 2)
            restored_items={item["item_id"]:item for item in session["items"]}
            self.assertEqual(restored_items["item-id"]["access_token"], "access-token")
            self.assertEqual(restored_items["item-id"]["cursor"], "cursor-value")
            self.assertEqual(restored_items["item-id-2"]["access_token"], "access-token-2")
            self.assertEqual(restored_items["item-id-2"]["cursor"], "cursor-value-2")
            vault.lock()


if __name__ == "__main__":
    unittest.main()
