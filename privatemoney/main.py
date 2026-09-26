from __future__ import annotations

import os
import secrets
import sys

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .api import DashboardApiServer
from .pages import (
    AccountsPage,
    BudgetsPage,
    DashboardPage,
    NetWorthPage,
    RecurringPage,
    ReportsPage,
    SettingsPage,
    TransactionsPage,
)
from .plaid import PlaidBridge
from .state import FinanceState
from .storage import VaultManager
from .theme import APP_QSS, MUTED


class PasswordDialog(QDialog):
    """Small product-facing password dialog using PrivateMoney's normal theme."""

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setModal(True)
        self.setObjectName("PasswordDialog")
        self.setMinimumWidth(420)
        self.setWindowTitle("Create password" if mode == "create" else "Enter password")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(12)

        title = QLabel("Create password" if mode == "create" else "Enter password")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        if mode == "create":
            detail = QLabel(
                "Choose a password for PrivateMoney on this computer. "
                "Use at least 10 characters."
            )
        else:
            detail = QLabel("Enter your PrivateMoney password to unlock your data.")
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color:{MUTED};")
        layout.addWidget(detail)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Password")
        self.password.returnPressed.connect(self._submit)
        layout.addWidget(self.password)

        self.confirm = None
        if mode == "create":
            self.confirm = QLineEdit()
            self.confirm.setEchoMode(QLineEdit.Password)
            self.confirm.setPlaceholderText("Confirm password")
            self.confirm.returnPressed.connect(self._submit)
            layout.addWidget(self.confirm)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#FF8E9A;")
        self.error.hide()
        layout.addWidget(self.error)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Exit" if mode == "create" else "Cancel")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        submit = QPushButton("Create password" if mode == "create" else "Unlock")
        submit.setObjectName("Primary")
        submit.clicked.connect(self._submit)
        buttons.addWidget(submit)
        layout.addLayout(buttons)

        QTimer.singleShot(0, self.password.setFocus)

    def _submit(self):
        value = self.password.text()
        if self.mode == "create":
            if len(value) < 10:
                self._show_error("Use at least 10 characters.")
                return
            if self.confirm is None or value != self.confirm.text():
                self._show_error("The passwords do not match.")
                return
        elif not value:
            self._show_error("Enter your password.")
            return
        self.accept()

    def _show_error(self, message: str):
        self.error.setText(message)
        self.error.show()
        self.password.selectAll()
        self.password.setFocus()

    @property
    def value(self) -> str:
        return self.password.text()


class NavigationPane(QFrame):
    """Sidebar that turns wheel gestures into deliberate page navigation."""

    def __init__(self, on_step, parent=None):
        super().__init__(parent)
        self._on_step = on_step
        self._wheel_accumulator = 0

    def watch_wheel(self, widget):
        widget.installEventFilter(self)

    def _consume_wheel(self, event) -> bool:
        delta = event.angleDelta().y()
        threshold = 120
        if not delta:
            delta = event.pixelDelta().y()
            threshold = 45
        if not delta:
            return False

        self._wheel_accumulator += delta
        if abs(self._wheel_accumulator) >= threshold:
            self._on_step(-1 if self._wheel_accumulator > 0 else 1)
            self._wheel_accumulator = 0

        event.accept()
        return True

    def wheelEvent(self, event):
        if not self._consume_wheel(event):
            super().wheelEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            return self._consume_wheel(event)
        return super().eventFilter(obj, event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PrivateMoney")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)

        self.state = FinanceState()
        self.vault = VaultManager()
        self.plaid = PlaidBridge(self.state)
        self.api_token = secrets.token_urlsafe(36)
        self.api = DashboardApiServer(self.state, self.plaid, self.api_token)
        self.api.start()

        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._topbar())

        self.stack = QStackedWidget()
        self.pages = [
            DashboardPage(self.state),
            AccountsPage(self.state),
            TransactionsPage(self.state, self.vault),
            BudgetsPage(self.state),
            RecurringPage(self.state),
            NetWorthPage(self.state),
            ReportsPage(self.state),
            SettingsPage(
                self.state,
                self.api,
                self.plaid,
                self.api_token,
                self.vault,
                on_logout=self.lock_vault,
            ),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, 1)
        outer.addWidget(content, 1)

        self._set_page(0)
        self._last_version = -1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1250)
        self._refresh()

        if not self.vault.exists and os.environ.get("PRIVATE_MONEY_TESTING") != "1":
            QTimer.singleShot(0, self._prompt_create_password)

    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(54)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.addStretch()

        self.lock_button = QPushButton()
        self.lock_button.setObjectName("VaultToggle")
        self.lock_button.setFixedSize(38, 38)
        self.lock_button.clicked.connect(self.toggle_vault)
        layout.addWidget(self.lock_button)
        return bar

    def _sidebar(self):
        bar = NavigationPane(self._move_page)
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(228)

        layout = QVBoxLayout(bar)
        layout.setContentsMargins(18, 24, 18, 20)
        layout.setSpacing(7)

        brand = QLabel("PrivateMoney")
        brand.setObjectName("Brand")
        sub = QLabel("LOCAL FINANCE")
        sub.setObjectName("Eyebrow")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(18)
        bar.watch_wheel(brand)
        bar.watch_wheel(sub)

        items = [
            ("Overview", "⌂"),
            ("Accounts", "▣"),
            ("Transactions", "↕"),
            ("Budgets", "◫"),
            ("Recurring", "↻"),
            ("Net worth", "⌁"),
            ("Reports", "⌗"),
            ("Settings", "⚙"),
        ]
        self.nav_buttons = []
        group = QButtonGroup(bar)
        group.setExclusive(True)

        for idx, (name, icon) in enumerate(items):
            button = QPushButton(f"{icon}   {name}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=idx: self._set_page(i))
            group.addButton(button)
            self.nav_buttons.append(button)
            layout.addWidget(button)
            bar.watch_wheel(button)

        layout.addStretch()

        self.mode_label = QLabel()
        self.mode_label.setWordWrap(True)
        self.mode_label.setStyleSheet(f"color:{MUTED};font-size:10px;")
        layout.addWidget(self.mode_label)
        bar.watch_wheel(self.mode_label)
        return bar

    def _set_page(self, index: int):
        if not hasattr(self, "stack"):
            return
        index = max(0, min(index, self.stack.count() - 1))
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    def _move_page(self, direction: int):
        if not hasattr(self, "stack"):
            return
        self._set_page(self.stack.currentIndex() + (1 if direction > 0 else -1))

    def _prompt_create_password(self):
        if self.vault.exists:
            return
        dialog = PasswordDialog("create", self)
        if dialog.exec() != QDialog.Accepted:
            self.close()
            return
        try:
            self.vault.create(dialog.value)
            self.vault.save_runtime(self.state, self.plaid)
            self._last_version = -1
        except Exception as exc:
            QMessageBox.warning(self, "Create password", str(exc))
            QTimer.singleShot(0, self._prompt_create_password)
            return
        self._refresh()

    def _prompt_unlock(self):
        if self.vault.unlocked:
            return True
        if not self.vault.exists:
            self._prompt_create_password()
            return self.vault.unlocked

        dialog = PasswordDialog("unlock", self)
        if dialog.exec() != QDialog.Accepted:
            return False

        try:
            self.vault.unlock(dialog.value)
            self.vault.restore_runtime(self.state, self.plaid)
            self._last_version = -1
            self._refresh()
            return True
        except Exception:
            QMessageBox.warning(self, "Enter password", "That password did not work.")
            return False

    def toggle_vault(self):
        if self.vault.unlocked:
            self.lock_vault()
        else:
            self._prompt_unlock()

    def lock_vault(self):
        if not self.vault.unlocked:
            return
        try:
            self.vault.save_runtime(self.state, self.plaid)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Log out",
                f"PrivateMoney could not save your latest changes: {exc}",
            )
            return

        self.vault.lock()
        self.plaid.clear_sensitive_session()
        self.state.clear_runtime()
        self._last_version = -1
        self._refresh()

    def _refresh(self):
        version = self.state.version
        if version != self._last_version:
            for page in self.pages:
                refresh = getattr(page, "refresh", None)
                if callable(refresh):
                    refresh()
            if self.vault.unlocked:
                try:
                    self.vault.save_runtime(self.state, self.plaid)
                except Exception as exc:
                    settings = self.pages[-1]
                    settings.set_vault_error(str(exc))
            self._last_version = version

        settings = self.pages[-1]
        settings.refresh()

        if self.vault.unlocked and self.plaid.connected:
            mode = "PLAID CONNECTED"
        elif self.vault.unlocked:
            mode = "SIGNED IN"
        else:
            mode = "LOCKED"
        self.mode_label.setText(mode)

        unlocked = self.vault.unlocked
        self.lock_button.setText("🔓" if unlocked else "🔒")
        self.lock_button.setToolTip(
            "Lock PrivateMoney" if unlocked else "Unlock PrivateMoney"
        )
        self.lock_button.setAccessibleName(
            "Lock PrivateMoney" if unlocked else "Unlock PrivateMoney"
        )

    def closeEvent(self, event):
        if self.vault.unlocked:
            try:
                self.vault.save_runtime(self.state, self.plaid)
            finally:
                self.vault.lock()
        self.api.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PrivateMoney")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
