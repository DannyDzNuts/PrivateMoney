from __future__ import annotations
import secrets
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from .api import DashboardApiServer
from .pages import AccountsPage, BudgetsPage, DashboardPage, NetWorthPage, RecurringPage, ReportsPage, SettingsPage, TransactionsPage
from .plaid import PlaidBridge
from .state import FinanceState
from .theme import APP_QSS, MUTED


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PrivateMoney")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)
        self.state=FinanceState()
        self.plaid=PlaidBridge(self.state)
        self.api_token=secrets.token_urlsafe(36)
        self.api=DashboardApiServer(self.state,self.plaid,self.api_token)
        self.api.start()

        root=QWidget(); self.setCentralWidget(root)
        outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        outer.addWidget(self._sidebar())
        self.stack=QStackedWidget()
        self.pages=[
            DashboardPage(self.state), AccountsPage(self.state), TransactionsPage(self.state), BudgetsPage(self.state),
            RecurringPage(self.state), NetWorthPage(self.state), ReportsPage(self.state),
            SettingsPage(self.state,self.api,self.plaid,self.api_token),
        ]
        for p in self.pages: self.stack.addWidget(p)
        outer.addWidget(self.stack,1)
        self.nav_buttons[0].setChecked(True)
        self._last_version=-1
        self._timer=QTimer(self); self._timer.timeout.connect(self._refresh); self._timer.start(1250)
        self._refresh()

    def _sidebar(self):
        bar=QFrame(); bar.setObjectName("Sidebar"); bar.setFixedWidth(228)
        l=QVBoxLayout(bar); l.setContentsMargins(18,24,18,20); l.setSpacing(7)
        brand=QLabel("PrivateMoney"); brand.setObjectName("Brand")
        sub=QLabel("LOCAL FINANCE"); sub.setObjectName("Eyebrow")
        l.addWidget(brand); l.addWidget(sub); l.addSpacing(18)
        items=[("Overview","⌂"),("Accounts","▣"),("Transactions","↕"),("Budgets","◫"),("Recurring","↻"),("Net worth","⌁"),("Reports","⌗"),("Settings","⚙")]
        self.nav_buttons=[]; group=QButtonGroup(bar); group.setExclusive(True)
        for idx,(name,icon) in enumerate(items):
            b=QPushButton(f"{icon}   {name}"); b.setObjectName("NavButton"); b.setCheckable(True)
            b.clicked.connect(lambda checked, i=idx: self.stack.setCurrentIndex(i))
            group.addButton(b); self.nav_buttons.append(b); l.addWidget(b)
        l.addStretch()
        self.mode_label=QLabel(); self.mode_label.setWordWrap(True); self.mode_label.setStyleSheet(f"color:{MUTED};font-size:10px;")
        l.addWidget(self.mode_label)
        return bar

    def _refresh(self):
        version=self.state.version
        if version != self._last_version:
            for page in self.pages:
                refresh=getattr(page,"refresh",None)
                if callable(refresh): refresh()
            self._last_version=version
        # Plaid status changes independently of finance-state updates while Link is open.
        settings=self.pages[-1]
        settings.refresh()
        self.mode_label.setText("PLAID SESSION · IN-MEMORY" if self.state.source=="plaid" else "DEMO DATA · NOTHING PERSISTED")

    def closeEvent(self,event):
        self.api.stop()
        super().closeEvent(event)


def main():
    app=QApplication(sys.argv)
    app.setApplicationName("PrivateMoney")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    w=MainWindow(); w.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
