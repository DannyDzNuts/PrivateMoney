import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PRIVATE_MONEY_TESTING"] = "1"

from PySide6.QtWidgets import QApplication

from privatemoney.main import MainWindow
from privatemoney.models import Account


class AccessFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_lock_clears_visible_state_and_unlock_restores_it(self):
        previous = os.environ.get("XDG_DATA_HOME")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["XDG_DATA_HOME"] = tmp
                window = MainWindow()
                try:
                    password = "correct horse battery staple"
                    window.vault.create(password)
                    window.state.restore_snapshot(
                        {
                            "source": "local",
                            "accounts": [
                                Account(
                                    "acct-1",
                                    "Checking",
                                    "checking",
                                    "Test Institution",
                                    321.45,
                                    300.00,
                                    "1234",
                                )
                            ],
                            "transactions": [],
                            "budgets": [],
                            "recurring": [],
                            "net_worth": [("Now", 321.45)],
                            "cashflow": [],
                        }
                    )
                    window.vault.save_runtime(window.state, window.plaid)
                    window._refresh()

                    self.assertTrue(window.vault.unlocked)
                    self.assertEqual(len(window.state.accounts()), 1)
                    self.assertEqual(window.lock_button.text(), "🔓")

                    window.lock_vault()

                    self.assertFalse(window.vault.unlocked)
                    self.assertEqual(window.state.accounts(), [])
                    self.assertFalse(window.plaid.configured)
                    self.assertEqual(window.lock_button.text(), "🔒")

                    window.vault.unlock(password)
                    self.assertTrue(
                        window.vault.restore_runtime(window.state, window.plaid)
                    )
                    window._last_version = -1
                    window._refresh()

                    self.assertEqual(window.state.accounts()[0].name, "Checking")
                    self.assertEqual(window.lock_button.text(), "🔓")
                finally:
                    window.close()
        finally:
            if previous is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
