from __future__ import annotations

import secrets
import sys

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
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
            # Wheel up = previous page; wheel down = next page.
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

        self.stack = QStackedWidget()
        self.pages = [
            DashboardPage(self.state),
            AccountsPage(self.state),
            TransactionsPage(self.state),
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
            ),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        outer.addWidget(self.stack, 1)

        self._set_page(0)
        self._last_version = -1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1250)
        self._refresh()

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

        # Plaid and vault status can change independently of finance-state updates.
        settings = self.pages[-1]
        settings.refresh()

        if self.vault.unlocked and self.plaid.connected:
            mode = "PLAID CONNECTED · ENCRYPTED VAULT"
        elif self.vault.unlocked:
            mode = "LOCAL VAULT · ENCRYPTED"
        elif self.plaid.connected:
            mode = "PLAID CONNECTED · SESSION ONLY"
        else:
            mode = "LOCAL MODE · SESSION ONLY"
        self.mode_label.setText(mode)

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
