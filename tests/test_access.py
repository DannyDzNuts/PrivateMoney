import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PRIVATE_MONEY_TESTING"] = "1"

from PySide6.QtWidgets import QApplication

from privatemoney.main import MainWindow, PasswordDialog
from privatemoney.models import Account


class AccessFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_create_password_validation_stays_open(self):
        dialog=PasswordDialog("create")
        try:
            dialog.password.setText("correct horse battery staple")
            dialog.confirm.setText("")
            dialog._submit()
            self.assertEqual(dialog.result(),0)
            self.assertTrue(dialog.error.isVisible() or bool(dialog.error.text()))
            self.assertIn("confirm",dialog.error.text().lower())

            dialog.confirm.setText("different password")
            dialog._submit()
            self.assertEqual(dialog.result(),0)
            self.assertIn("do not match",dialog.error.text().lower())
        finally:
            dialog.close()

    def test_lock_clears_visible_state_and_unlock_restores_it(self):
        previous = os.environ.get("XDG_DATA_HOME")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["XDG_DATA_HOME"] = tmp
                window = MainWindow()
                try:
                    settings=window.pages[-1]
                    self.assertTrue(settings.api_card.isHidden())
                    self.assertFalse(settings.dev_gate.isHidden())
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
                    self.assertTrue(window.lock_button._unlocked)

                    window.lock_vault()

                    settings=window.pages[-1]
                    settings.refresh()
                    self.assertEqual(settings.login_logout_btn.text(),"Log in")

                    self.assertFalse(window.vault.unlocked)
                    self.assertEqual(window.state.accounts(), [])
                    self.assertFalse(window.plaid.configured)
                    self.assertFalse(window.lock_button._unlocked)

                    window.vault.unlock(password)
                    self.assertTrue(
                        window.vault.restore_runtime(window.state, window.plaid)
                    )
                    window._last_version = -1
                    window._refresh()
                    settings.refresh()
                    self.assertEqual(settings.login_logout_btn.text(),"Log out")

                    self.assertEqual(window.state.accounts()[0].name, "Checking")
                    self.assertTrue(window.lock_button._unlocked)
                finally:
                    window.close()
        finally:
            if previous is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
