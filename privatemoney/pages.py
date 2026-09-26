from __future__ import annotations
import threading
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget
)
from .charts import CashFlowChart, DonutChart, LineChart
from .widgets import BudgetRow, Card, MetricCard, money
from . import theme


def page_header(title: str, subtitle: str):
    w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(3)
    a=QLabel(title); a.setObjectName("PageTitle")
    b=QLabel(subtitle); b.setObjectName("PageSubtitle")
    l.addWidget(a); l.addWidget(b)
    return w


def card_with_title(title: str, child: QWidget, subtitle: str = "") -> Card:
    card=Card(); l=QVBoxLayout(card); l.setContentsMargins(18,16,18,16); l.setSpacing(8)
    t=QLabel(title); t.setObjectName("SectionTitle"); l.addWidget(t)
    if subtitle:
        s=QLabel(subtitle); s.setStyleSheet(f"color:{theme.MUTED}"); l.addWidget(s)
    l.addWidget(child,1)
    return card


class DashboardPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,20,28,22); l.setSpacing(14)
        l.addWidget(page_header("Overview", "A private snapshot of your money."))
        metrics=QGridLayout(); metrics.setSpacing(14)
        self.net_card=MetricCard("Net worth", "$0.00")
        self.cash_card=MetricCard("Cash available", "$0.00")
        self.spend_card=MetricCard("This month spending", "$0.00")
        self.recurring_card=MetricCard("Upcoming recurring", "$0.00")
        for i,w in enumerate([self.net_card,self.cash_card,self.spend_card,self.recurring_card]): metrics.addWidget(w,0,i)
        l.addLayout(metrics)
        grid=QGridLayout(); grid.setSpacing(14)
        self.net_chart=LineChart(state.net_worth())
        self.spend_chart=DonutChart(state.spending())
        self.cashflow_chart=CashFlowChart(state.cashflow())
        grid.addWidget(card_with_title("Net worth", self.net_chart, "Recent trend"),0,0,1,2)
        grid.addWidget(card_with_title("Spending mix", self.spend_chart, "Latest month"),0,2)
        grid.addWidget(card_with_title("Cash flow", self.cashflow_chart, "Income vs. outflow"),1,0,1,2)
        budgets=QWidget(); budgets.setStyleSheet("background:transparent;"); bl=QVBoxLayout(budgets); bl.setContentsMargins(0,0,0,0); bl.setSpacing(2)
        for b in state.budgets(): bl.addWidget(BudgetRow(b.category,b.spent,b.limit))
        bl.addStretch(); grid.addWidget(card_with_title("Budgets",budgets,"Current plan"),1,2)
        grid.setColumnStretch(0,2); grid.setColumnStretch(1,2); grid.setColumnStretch(2,2)
        grid.setRowStretch(0,1); grid.setRowStretch(1,1)
        l.addLayout(grid,1)
        self.refresh()

    def refresh(self):
        s=self.state.summary()
        live=s["source"]=="plaid"
        self.net_card.set_value(money(s["net_worth"])); self.net_card.set_delta("Across tracked accounts", True)
        self.cash_card.set_value(money(s["cash_available"])); self.cash_card.set_delta(f"{s['account_count']} accounts", True)
        self.spend_card.set_value(money(-s["month_spending"])); self.spend_card.set_delta(f"Income {money(s['month_income'])}", s["month_income"] >= s["month_spending"])
        self.recurring_card.set_value(money(-s["upcoming_recurring"])); self.recurring_card.set_delta("Pattern detection pending" if live else "Upcoming scheduled charges", True)
        self.net_chart.set_points(self.state.net_worth())
        self.spend_chart.set_segments(self.state.spending())
        self.cashflow_chart.set_rows(self.state.cashflow())


class AccountsPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Accounts", "Balances across your accounts."))
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["Account","Type","Institution","Available","Current"])
        style_table(self.table); l.addWidget(self.table,1); self.refresh()

    def refresh(self):
        rows=self.state.accounts(); self.table.setRowCount(len(rows))
        for r,a in enumerate(rows):
            vals=[a.name,a.kind,a.institution,"—" if a.available_balance is None else money(a.available_balance),money(a.current_balance)]
            for c,val in enumerate(vals):
                item=QTableWidgetItem(val)
                if c in (3,4): item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                self.table.setItem(r,c,item)
        header=self.table.horizontalHeader()
        for c in range(5): header.setSectionResizeMode(c,QHeaderView.Stretch if c<3 else QHeaderView.ResizeToContents)


class TransactionsPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        top=QHBoxLayout(); top.addWidget(page_header("Transactions","Search and review local or Plaid-synced activity.")); top.addStretch()
        btn=QPushButton("Import statement"); btn.setObjectName("Primary"); btn.setEnabled(False); btn.setToolTip("Statement import wizard is next on the roadmap")
        top.addWidget(btn); l.addLayout(top)
        self.search=QLineEdit(); self.search.setPlaceholderText("Search merchant, category, or account…"); l.addWidget(self.search)
        self.table=transaction_table([]); l.addWidget(self.table,1)
        self.search.textChanged.connect(lambda q: filter_table(self.table,q)); self.refresh()

    def refresh(self):
        fill_transaction_table(self.table,self.state.transactions()); filter_table(self.table,self.search.text())


class BudgetsPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        top=QHBoxLayout(); top.addWidget(page_header("Budgets","Simple category limits without noisy gamification.")); top.addStretch()
        b=QPushButton("New budget"); b.setObjectName("Primary"); b.setEnabled(False); top.addWidget(b); l.addLayout(top)
        card=Card(); cl=QVBoxLayout(card); cl.setContentsMargins(22,18,22,18); cl.setSpacing(5)
        for row in state.budgets(): cl.addWidget(BudgetRow(row.category,row.spent,row.limit))
        cl.addStretch(); l.addWidget(card); l.addStretch()

    def refresh(self): pass


class RecurringPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Recurring","Bills and subscriptions detected from transaction patterns."))
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(["Merchant","Category","Cadence / next","Amount"])
        style_table(self.table); l.addWidget(self.table,1); self.refresh()

    def refresh(self):
        rows=self.state.recurring(); self.table.setRowCount(len(rows))
        for r,x in enumerate(rows):
            vals=[x.merchant,x.category,f"{x.cadence} · {x.next_date:%b %d}",money(-x.amount)]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(val))
        if not rows:
            self.table.setRowCount(1); self.table.setItem(0,0,QTableWidgetItem("Recurring detection will run after enough live transaction history is available.")); self.table.setSpan(0,0,1,4)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


class NetWorthPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Net worth","Assets minus liabilities, tracked over time."))
        self.chart=LineChart(state.net_worth()); l.addWidget(card_with_title("Net worth history",self.chart,"History will build over time"),1)
    def refresh(self): self.chart.set_points(self.state.net_worth())


class ReportsPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Reports","Understand patterns without sending dashboard data anywhere."))
        grid=QGridLayout(); grid.setSpacing(14)
        self.spend=DonutChart(state.spending()); self.cash=CashFlowChart(state.cashflow())
        grid.addWidget(card_with_title("Spending by category",self.spend),0,0); grid.addWidget(card_with_title("Income vs. outflow",self.cash),0,1)
        l.addLayout(grid,1)
    def refresh(self): self.spend.set_segments(self.state.spending()); self.cash.set_rows(self.state.cashflow())


class SettingsPage(QScrollArea):
    def __init__(self, state, api_server, plaid, api_token, vault, on_logout=None, parent=None):
        super().__init__(parent); self.state=state; self.api_server=api_server; self.plaid=plaid; self.api_token=api_token; self.vault=vault; self.on_logout=on_logout; self._vault_error=''
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        host=QWidget(); self.setWidget(host); l=QVBoxLayout(host); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Settings","Private by default; external access must be explicitly configured."))

        access=Card(); alog=QVBoxLayout(access); alog.setContentsMargins(20,18,20,18); alog.setSpacing(9)
        ah=QLabel("Access"); ah.setObjectName("SectionTitle"); alog.addWidget(ah)
        self.access_status=QLabel(); self.access_status.setWordWrap(True); self.access_status.setStyleSheet(f"color:{theme.MUTED}"); alog.addWidget(self.access_status)
        self.logout_btn=QPushButton("Log out"); self.logout_btn.setObjectName("Secondary"); self.logout_btn.clicked.connect(self._logout)
        alog.addWidget(self.logout_btn,0,Qt.AlignLeft)
        l.addWidget(access)

        api=Card(); a=QVBoxLayout(api); a.setContentsMargins(20,18,20,18); a.setSpacing(9)
        title=QLabel("Dashboard API"); title.setObjectName("SectionTitle"); a.addWidget(title)
        self.api_status=QLabel(); self.api_status.setStyleSheet(f"color:{theme.MUTED}"); a.addWidget(self.api_status)
        token_row=QHBoxLayout(); self.token_preview=QLineEdit(); self.token_preview.setReadOnly(True); self.token_preview.setEchoMode(QLineEdit.Password); self.token_preview.setText(api_token)
        copy=QPushButton("Copy token"); copy.setObjectName("Secondary"); copy.clicked.connect(lambda: QApplication.clipboard().setText(api_token))
        token_row.addWidget(self.token_preview,1); token_row.addWidget(copy); a.addLayout(token_row)
        curl=QPushButton("Copy curl example"); curl.setObjectName("Secondary"); curl.clicked.connect(self._copy_curl); a.addWidget(curl,0,Qt.AlignLeft)
        note=QLabel("Read-only API · bearer-token protected · bound to 127.0.0.1 only. No Plaid secret or access token is ever exposed through it.")
        note.setWordWrap(True); note.setStyleSheet(f"color:{theme.MUTED}"); a.addWidget(note); l.addWidget(api)

        pc=Card(); p=QVBoxLayout(pc); p.setContentsMargins(20,18,20,18); p.setSpacing(9)
        h=QLabel("Plaid bank connection"); h.setObjectName("SectionTitle"); p.addWidget(h)
        steps=QLabel("1. Set Plaid API credentials  →  2. Connect bank in Plaid Link  →  3. Refresh & sync")
        steps.setWordWrap(True); steps.setStyleSheet(f"color:{theme.MUTED}; background:transparent;"); p.addWidget(steps)
        self.plaid_status=QLabel(); self.plaid_status.setWordWrap(True); self.plaid_status.setStyleSheet(f"color:{theme.MUTED}"); p.addWidget(self.plaid_status)
        envrow=QHBoxLayout(); envlbl=QLabel("Environment"); self.env=QComboBox(); self.env.addItems(["Sandbox","Production"]); envrow.addWidget(envlbl); envrow.addStretch(); envrow.addWidget(self.env); p.addLayout(envrow)
        self.client_id=QLineEdit(); self.client_id.setPlaceholderText("Plaid client_id")
        self.secret=QLineEdit(); self.secret.setPlaceholderText("Plaid secret"); self.secret.setEchoMode(QLineEdit.Password)
        p.addWidget(self.client_id); p.addWidget(self.secret)
        buttons=QHBoxLayout(); configure=QPushButton("Set API credentials"); configure.setObjectName("Secondary"); configure.clicked.connect(self._configure_plaid)
        self.connect_btn=QPushButton("Connect bank"); self.connect_btn.setObjectName("Primary"); self.connect_btn.clicked.connect(self._connect_bank)
        self.sync_btn=QPushButton("Refresh & sync"); self.sync_btn.setObjectName("Secondary"); self.sync_btn.setToolTip("Requests a fresh Plaid transaction update when Transactions Refresh is available, then syncs available changes."); self.sync_btn.clicked.connect(self._sync_now)
        buttons.addWidget(configure); buttons.addWidget(self.connect_btn); buttons.addWidget(self.sync_btn); buttons.addStretch(); p.addLayout(buttons)
        self.plaid_privacy=QLabel(); privacy=self.plaid_privacy
        privacy.setWordWrap(True); privacy.setStyleSheet(f"color:{theme.MUTED}"); p.addWidget(privacy); l.addWidget(pc)

        ap=Card(); al=QVBoxLayout(ap); al.setContentsMargins(20,18,20,18); al.setSpacing(7)
        x=QLabel("Appearance"); x.setObjectName("SectionTitle"); al.addWidget(x)
        al.addWidget(QLabel("Midnight Violet")); detail=QLabel("OLED black · charcoal cards · deep violet surfaces · violet accent · ivory text"); detail.setStyleSheet(f"color:{theme.MUTED}"); al.addWidget(detail)
        l.addWidget(ap); l.addStretch(); self.refresh()

    def _copy_curl(self):
        QApplication.clipboard().setText(f'curl -H "Authorization: Bearer {self.api_token}" {self.api_server.base_url}/api/v1/summary')

    def set_vault_error(self, message: str):
        self._vault_error = message
        self.refresh()

    def _logout(self):
        if callable(self.on_logout):
            self.on_logout()

    def _configure_plaid(self):
        try:
            self.plaid.configure(self.client_id.text(),self.secret.text(),self.env.currentText())
            if self.vault.unlocked:
                self.vault.save_runtime(self.state, self.plaid)
            self.secret.clear(); self.refresh()
        except Exception as exc:
            QMessageBox.warning(self,"Plaid configuration",str(exc))

    def _connect_bank(self):
        try:
            nonce=self.plaid.create_link_session(); url=f"{self.api_server.base_url}/plaid/link/{nonce}"
            if not QDesktopServices.openUrl(QUrl(url)): raise RuntimeError("Could not open the Plaid Link page in your browser.")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self,"Plaid connection",str(exc))

    def _sync_now(self):
        with self.plaid._lock:
            self.plaid._status = "Refreshing bank data…"
        self.refresh()
        def worker():
            try:
                self.plaid.refresh_and_sync()
            except Exception as exc:
                with self.plaid._lock:
                    self.plaid._status=f"Sync failed: {exc}"
        threading.Thread(target=worker,daemon=True,name="private-money-plaid-sync").start()

    def refresh(self):
        self.api_status.setText(f"Running at {self.api_server.base_url}/api/v1")
        self.plaid_status.setText(self.plaid.status)
        self.connect_btn.setEnabled(self.plaid.configured)
        self.sync_btn.setEnabled(self.plaid.connected)
        self.env.setCurrentText(self.plaid.environment)

        if self.vault.unlocked:
            access_text = "PrivateMoney is unlocked on this computer."
            self.logout_btn.setEnabled(True)
            self.plaid_privacy.setText("Your Plaid connection can be saved securely on this computer. Bank credentials are still entered only inside Plaid Link.")
        else:
            access_text = "PrivateMoney is locked."
            self.logout_btn.setEnabled(False)
            self.plaid_privacy.setText("Unlock PrivateMoney to save your Plaid connection and financial data.")
        if self._vault_error:
            access_text += f"  Last error: {self._vault_error}"
        self.access_status.setText(access_text)


def style_table(table):
    table.verticalHeader().setVisible(False); table.setShowGrid(False); table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setEditTriggers(QAbstractItemView.NoEditTriggers)


def transaction_table(items, compact=False):
    table=QTableWidget(0,5); table.setHorizontalHeaderLabels(["Date","Merchant","Category","Account","Amount"]); style_table(table)
    fill_transaction_table(table,items)
    if compact: table.setMinimumHeight(230); table.setMaximumHeight(260)
    return table


def fill_transaction_table(table: QTableWidget, items):
    table.clearSpans(); table.setRowCount(len(items))
    for r,t in enumerate(items):
        vals=[t.posted.strftime("%b %d"),t.merchant,t.category,t.account,money(t.amount)]
        for c,val in enumerate(vals):
            item=QTableWidgetItem(val)
            if c==4:
                item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter); item.setForeground(QColor(theme.POSITIVE if t.amount>=0 else theme.NEGATIVE))
            if t.pending: item.setToolTip("Pending")
            table.setItem(r,c,item)
    hh=table.horizontalHeader()
    for c in range(5): hh.setSectionResizeMode(c,QHeaderView.Stretch if c in (1,2,3) else QHeaderView.ResizeToContents)


def filter_table(table: QTableWidget, query: str):
    q=query.strip().lower()
    for row in range(table.rowCount()):
        text=" ".join((table.item(row,c).text() if table.item(row,c) else "") for c in range(table.columnCount())).lower()
        table.setRowHidden(row, q not in text)
