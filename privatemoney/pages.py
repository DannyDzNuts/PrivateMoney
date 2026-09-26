from __future__ import annotations
import threading
import uuid
from datetime import date, timedelta
from PySide6.QtCore import QEvent, Signal, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget
)
from .charts import CashFlowChart, DonutChart, LineChart
from .models import Goal
from .importers import (ACCOUNT_CANDIDATES, AMOUNT_CANDIDATES, BALANCE_CANDIDATES, CREDIT_CANDIDATES, DATE_CANDIDATES, DEBIT_CANDIDATES, DESCRIPTION_CANDIDATES, csv_header_signature, guess_column, parse_csv, parse_ofx, read_csv_headers)
from .widgets import BudgetRow, Card, MetricCard, money
from . import theme


def page_header(title: str, subtitle: str):
    w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(3)
    a=QLabel(title); a.setObjectName("PageTitle")
    b=QLabel(subtitle); b.setObjectName("PageSubtitle")
    l.addWidget(a); l.addWidget(b)
    return w


def card_with_title(
    title: str,
    child: QWidget,
    subtitle: str = "",
    action: QWidget | None = None,
) -> Card:
    card=Card(); l=QVBoxLayout(card); l.setContentsMargins(18,16,18,16); l.setSpacing(8)
    header=QHBoxLayout()
    t=QLabel(title); t.setObjectName("SectionTitle"); header.addWidget(t)
    header.addStretch()
    if action is not None:
        header.addWidget(action)
    l.addLayout(header)
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
        self.spend_card=MetricCard("This Month's Spending", "$0.00")
        self.recurring_card=MetricCard("Upcoming recurring", "$0.00")
        for i,w in enumerate([self.net_card,self.cash_card,self.spend_card,self.recurring_card]): metrics.addWidget(w,0,i)
        l.addLayout(metrics)
        grid=QGridLayout(); grid.setSpacing(14)
        self.net_duration=_NoWheelComboBox()
        self.net_duration.setObjectName("ChartDuration")
        self.net_duration.addItem("1M",30)
        self.net_duration.addItem("3M",90)
        self.net_duration.addItem("6M",180)
        self.net_duration.addItem("1Y",365)
        self.net_duration.addItem("All",None)
        self.net_duration.setCurrentIndex(2)
        self.net_duration.setMinimumWidth(76)

        self.net_trend=QLabel("—")
        self.net_trend.setStyleSheet(f"color:{theme.MUTED};font-weight:700")
        net_action=QWidget()
        net_action.setStyleSheet("background:transparent;")
        nal=QHBoxLayout(net_action); nal.setContentsMargins(0,0,0,0); nal.setSpacing(8)
        nal.addWidget(self.net_trend); nal.addWidget(self.net_duration)

        self.net_chart=LineChart([],show_points=False,hover_tooltip=True,show_trend=True)
        self.net_duration.currentIndexChanged.connect(self._update_net_chart)
        self.spend_chart=DonutChart(state.spending_last_month())
        self.cashflow_chart=CashFlowChart(state.cashflow())
        grid.addWidget(
            card_with_title("Net worth",self.net_chart,"Recent trend",action=net_action),
            0,0,1,2
        )
        grid.addWidget(card_with_title("Categories",self.spend_chart,"Last month"),0,2)
        grid.addWidget(card_with_title("Cash flow", self.cashflow_chart, "Income vs. spending"),1,0,1,2)
        budgets=QWidget(); budgets.setStyleSheet("background:transparent;"); bl=QVBoxLayout(budgets); bl.setContentsMargins(0,0,0,0); bl.setSpacing(2)
        for b in state.budgets(): bl.addWidget(BudgetRow(b.category,b.spent,b.limit))
        bl.addStretch(); grid.addWidget(card_with_title("Budgets",budgets,"Current plan"),1,2)
        grid.setColumnStretch(0,1); grid.setColumnStretch(1,1); grid.setColumnStretch(2,3)
        grid.setRowStretch(0,1); grid.setRowStretch(1,1)
        l.addLayout(grid,1)
        self.recent_table=transaction_table([],compact=True)
        l.addWidget(card_with_title("Recent transactions",self.recent_table,"Latest 5"))
        self.refresh()

    def _overview_net_points(self):
        points=self.state.net_worth()
        days=self.net_duration.currentData()
        if days is None or not points:
            return points
        parsed=[]
        for label,value in points:
            try:
                parsed.append((date.fromisoformat(str(label)),label,value))
            except ValueError:
                return points
        latest=max(row[0] for row in parsed)
        cutoff=latest-timedelta(days=int(days))
        filtered=[(label,value) for posted,label,value in parsed if posted >= cutoff]
        return filtered or [points[-1]]

    def _update_net_chart(self, *_):
        self.net_chart.set_points(self._overview_net_points())
        pct=self.net_chart.trend_change_percent()
        if pct is None:
            self.net_trend.setText("—")
            self.net_trend.setStyleSheet(f"color:{theme.MUTED};font-weight:700")
        else:
            sign="+" if pct >= 0 else ""
            self.net_trend.setText(f"{sign}{pct:.1f}%")
            color=theme.POSITIVE if pct >= 0 else theme.NEGATIVE
            self.net_trend.setStyleSheet(f"color:{color};font-weight:700")

    def refresh(self):
        s=self.state.summary()
        self.net_card.set_value(money(s["net_worth"])); self.net_card.set_delta("Across tracked accounts", True)
        self.cash_card.set_value(money(s["cash_available"])); self.cash_card.set_delta(f"{s['account_count']} accounts", True)
        self.spend_card.set_value(money(s["month_spending"]))
        variance=s["spending_variance"]
        sign="+" if variance > 0 else ("-" if variance < 0 else "")
        variance_text=sign + "$" + f"{abs(variance):,.2f}" + " vs last month"
        self.spend_card.set_delta(variance_text, variance <= 0)
        recurring_count=s["recurring_count"]
        self.recurring_card.set_value(money(-s["upcoming_recurring"]))
        pattern_text=(f"{recurring_count} detected pattern" + ("s" if recurring_count != 1 else "")) if recurring_count else "No recurring patterns detected"
        self.recurring_card.set_delta(pattern_text, True)
        self._update_net_chart()
        self.spend_chart.set_segments(self.state.spending_last_month())
        self.cashflow_chart.set_rows(self.state.cashflow())
        recent=sorted(self.state.transactions(),key=lambda tx:tx.posted,reverse=True)[:5]
        fill_transaction_table(
            self.recent_table,
            recent,
            account_labeler=self.state.account_display_name,
        )


class AccountsPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Accounts", "Balances across your accounts."))
        self.table=QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(["Nickname","Account","Type","Institution","Available","Current"])
        style_table(self.table); l.addWidget(self.table,1); self.refresh()

    def _save_nickname(self, account_id, editor):
        self.state.set_account_nickname(account_id, editor.text())

    def refresh(self):
        rows=self.state.accounts(); self.table.setRowCount(len(rows))
        for r,a in enumerate(rows):
            nickname=QLineEdit()
            nickname.setPlaceholderText("Optional nickname")
            nickname.setText(a.nickname or "")
            nickname.setAlignment(Qt.AlignCenter)
            nickname.setMinimumHeight(38)
            nickname.editingFinished.connect(
                lambda account_id=a.id, editor=nickname: self._save_nickname(account_id,editor)
            )
            self.table.setCellWidget(r,0,nickname)
            vals=[a.name,a.kind,a.institution,"—" if a.available_balance is None else money(a.available_balance),money(a.current_balance)]
            for offset,val in enumerate(vals,1):
                item=_CenteredTableItem(val)
                self.table.setItem(r,offset,item)
        self.table.verticalHeader().setDefaultSectionSize(44)
        header=self.table.horizontalHeader()
        header.setSectionResizeMode(0,QHeaderView.Interactive)
        header.setSectionResizeMode(1,QHeaderView.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3,QHeaderView.Stretch)
        header.setSectionResizeMode(4,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5,QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0,280)


class StatementImportDialog(QDialog):
    NOT_SET = "Not set"

    def __init__(self, state, vault, parent=None):
        super().__init__(parent)
        self.state=state
        self.vault=vault
        self.rows=[]
        self.skipped=0
        self.file_type=""
        self.headers=[]
        self.header_signature=None
        self.setWindowTitle("Import statement")
        self.setObjectName("PasswordDialog")
        screen=QApplication.primaryScreen()
        available=screen.availableGeometry() if screen is not None else None
        max_w=max(720, (available.width()-80) if available is not None else 900)
        max_h=max(560, (available.height()-80) if available is not None else 760)
        self.setMinimumSize(min(720,max_w), min(560,max_h))
        self.setMaximumSize(max_w,max_h)
        self.resize(min(820,max_w), min(700,max_h))

        l=QVBoxLayout(self); l.setContentsMargins(22,22,22,22); l.setSpacing(12)
        title=QLabel("Import statement"); title.setObjectName("SectionTitle"); l.addWidget(title)
        sub=QLabel("Choose a statement, tell PrivateMoney how this bank lays out its fields, and preview the result before importing.")
        sub.setWordWrap(True); sub.setStyleSheet(f"color:{theme.MUTED}"); l.addWidget(sub)

        file_row=QHBoxLayout()
        self.file=QLineEdit(); self.file.setReadOnly(True); self.file.setPlaceholderText("Choose a statement file…")
        browse=QPushButton("Choose file"); browse.setObjectName("Secondary"); browse.clicked.connect(self._browse)
        file_row.addWidget(self.file,1); file_row.addWidget(browse); l.addLayout(file_row)

        self.mapping_widget=QWidget()
        self.mapping_widget.setObjectName("ImportMappingPanel")
        self.mapping_widget.setStyleSheet("QWidget#ImportMappingPanel { background: transparent; }")
        self.mapping_widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        mapping=QVBoxLayout(self.mapping_widget); mapping.setContentsMargins(10,8,10,8); mapping.setSpacing(10)
        grid=QGridLayout(); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0,180)
        grid.setColumnStretch(1,1)

        self.date_col=QComboBox()
        self.desc_col=QComboBox()
        self.amount_mode=QComboBox()
        self.amount_mode.addItem("Single amount column","single")
        self.amount_mode.addItem("Separate debit / credit columns","split")
        self.amount_col=QComboBox()
        self.debit_col=QComboBox()
        self.credit_col=QComboBox()
        self.account_col=QComboBox()
        self.balance_col=QComboBox()
        for combo in (
            self.date_col,self.desc_col,self.amount_mode,self.amount_col,
            self.debit_col,self.credit_col,self.account_col,self.balance_col,
        ):
            combo.setMinimumWidth(330)
            combo.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

        grid.addWidget(QLabel("Date"),0,0); grid.addWidget(self.date_col,0,1)
        grid.addWidget(QLabel("Description"),1,0); grid.addWidget(self.desc_col,1,1)
        grid.addWidget(QLabel("Amount format"),2,0); grid.addWidget(self.amount_mode,2,1)

        self.amount_label=QLabel("Amount")
        self.debit_label=QLabel("Debit")
        self.credit_label=QLabel("Credit")
        grid.addWidget(self.amount_label,3,0); grid.addWidget(self.amount_col,3,1)
        grid.addWidget(self.debit_label,4,0); grid.addWidget(self.debit_col,4,1)
        grid.addWidget(self.credit_label,5,0); grid.addWidget(self.credit_col,5,1)

        grid.addWidget(QLabel("Account (optional)"),6,0); grid.addWidget(self.account_col,6,1)
        grid.addWidget(QLabel("Balance (optional)"),7,0); grid.addWidget(self.balance_col,7,1)
        mapping.addLayout(grid)

        self.invert=QCheckBox("Invert amount signs")
        self.invert.setToolTip("For single-amount CSVs where purchases are exported as positive values.")
        mapping.addWidget(self.invert)

        self.use_account_column=QCheckBox("Use the Account column to choose the destination account for each row")
        mapping.addWidget(self.use_account_column)

        profile_row=QHBoxLayout()
        self.profile_note=QLabel(); self.profile_note.setWordWrap(True); self.profile_note.setMinimumWidth(0); self.profile_note.setStyleSheet(f"color:{theme.MUTED}")
        self.save_default=QPushButton("Save as default"); self.save_default.setObjectName("Secondary"); self.save_default.clicked.connect(self._save_default)
        profile_row.addWidget(self.profile_note,1); profile_row.addWidget(self.save_default)
        mapping.addLayout(profile_row)

        self.mapping_scroll=QScrollArea()
        self.mapping_scroll.setObjectName("ImportMappingScroll")
        self.mapping_scroll.setFrameShape(QFrame.NoFrame)
        self.mapping_scroll.setWidgetResizable(True)
        self.mapping_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mapping_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mapping_scroll.setMaximumHeight(335)
        self.mapping_scroll.setMinimumHeight(250)
        self.mapping_scroll.setStyleSheet(
            "QScrollArea#ImportMappingScroll { background: transparent; border: 0; }"
            "QScrollArea#ImportMappingScroll > QWidget > QWidget { background: transparent; }"
        )
        self.mapping_scroll.viewport().setStyleSheet("background: transparent;")
        self.mapping_scroll.setWidget(self.mapping_widget)
        l.addWidget(self.mapping_scroll)
        self.mapping_scroll.hide()

        account_row=QHBoxLayout()
        self.account_label=QLabel("Import to account")
        account_row.addWidget(self.account_label)
        self.account=QComboBox(); self.account.setEditable(True); self.account.setPlaceholderText("Account name")
        for existing in state.accounts():
            self.account.addItem((existing.nickname or "").strip() or existing.name, existing.name)
        self.account.currentTextChanged.connect(self._refresh_preview)
        account_row.addWidget(self.account,1); l.addLayout(account_row)

        for box in (self.date_col,self.desc_col,self.amount_col,self.debit_col,self.credit_col,self.account_col,self.balance_col):
            box.currentTextChanged.connect(self._mapping_changed)
        self.amount_mode.currentIndexChanged.connect(self._mapping_changed)
        self.invert.toggled.connect(self._mapping_changed)
        self.use_account_column.toggled.connect(self._mapping_changed)

        self.preview=QTableWidget(0,4); self.preview.setHorizontalHeaderLabels(["Date","Description","Amount","Account"])
        style_table(self.preview)
        hh=self.preview.horizontalHeader()
        hh.setSectionResizeMode(0,QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1,QHeaderView.Stretch)
        hh.setSectionResizeMode(2,QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3,QHeaderView.ResizeToContents)
        self.preview.setMinimumHeight(230); l.addWidget(self.preview,1)

        self.summary=QLabel("Choose a statement file to begin."); self.summary.setStyleSheet(f"color:{theme.MUTED}"); l.addWidget(self.summary)
        buttons=QHBoxLayout(); buttons.addStretch()
        cancel=QPushButton("Cancel"); cancel.setObjectName("Secondary"); cancel.clicked.connect(self.reject)
        self.import_btn=QPushButton("Import"); self.import_btn.setObjectName("Primary"); self.import_btn.setEnabled(False); self.import_btn.clicked.connect(self._import)
        buttons.addWidget(cancel); buttons.addWidget(self.import_btn); l.addLayout(buttons)
        self._update_amount_controls()

    def _set_columns(self, box, headers, selected=None):
        box.blockSignals(True)
        box.clear()
        box.addItem(self.NOT_SET,"")
        for header in headers:
            box.addItem(header,header)
        if selected and selected in headers:
            box.setCurrentText(selected)
        else:
            box.setCurrentIndex(0)
        box.blockSignals(False)

    def _value(self, box):
        return box.currentData() or ""

    def _browse(self):
        path,_=QFileDialog.getOpenFileName(
            self,"Choose statement","",
            "Statements (*.csv *.qfx *.ofx);;CSV files (*.csv);;QFX / OFX files (*.qfx *.ofx);;All files (*)",
        )
        if not path: return
        from pathlib import Path
        suffix=Path(path).suffix.lower()
        if suffix not in {".csv",".qfx",".ofx"}:
            QMessageBox.warning(self,"Import statement","Choose a CSV, QFX, or OFX statement file."); return

        self.file.setText(path)
        if not self.account.currentText().strip():
            self.account.setEditText(Path(path).stem.replace("_"," ").replace("-"," ").title())

        if suffix != ".csv":
            self.file_type="ofx"; self.mapping_scroll.hide(); self.account_label.setText("Import to account")
            self._refresh_preview(); return

        self.file_type="csv"; self.mapping_scroll.show()
        try:
            headers=read_csv_headers(path)
            if not headers: raise ValueError("This CSV does not contain a header row.")
        except Exception as exc:
            QMessageBox.warning(self,"Import statement",str(exc)); return

        self.headers=headers
        self.header_signature=csv_header_signature(headers)
        saved=self.vault.load_import_profile(self.header_signature) or {}

        guessed_debit=guess_column(headers,DEBIT_CANDIDATES)
        guessed_credit=guess_column(headers,CREDIT_CANDIDATES)
        guessed_mode="split" if guessed_debit or guessed_credit else "single"

        defaults={
            "date_col":guess_column(headers,DATE_CANDIDATES),
            "description_col":guess_column(headers,DESCRIPTION_CANDIDATES),
            "amount_mode":guessed_mode,
            "amount_col":guess_column(headers,AMOUNT_CANDIDATES),
            "debit_col":guessed_debit,
            "credit_col":guessed_credit,
            "account_col":guess_column(headers,ACCOUNT_CANDIDATES),
            "balance_col":guess_column(headers,BALANCE_CANDIDATES),
            "invert_amounts":False,
            "use_account_column":False,
        }
        defaults.update({k:v for k,v in saved.items() if k in defaults})

        for box,key in (
            (self.date_col,"date_col"),(self.desc_col,"description_col"),
            (self.amount_col,"amount_col"),(self.debit_col,"debit_col"),
            (self.credit_col,"credit_col"),(self.account_col,"account_col"),
            (self.balance_col,"balance_col"),
        ):
            self._set_columns(box,headers,defaults.get(key))

        mode_index=self.amount_mode.findData(defaults.get("amount_mode","single"))
        self.amount_mode.setCurrentIndex(max(0,mode_index))
        self.invert.setChecked(bool(defaults.get("invert_amounts",False)))
        self.use_account_column.setChecked(bool(defaults.get("use_account_column",False)))
        self.profile_note.setText("Saved mapping loaded." if saved else "Review the mapping before importing.")
        self._mapping_changed()

    def _update_amount_controls(self):
        split=self.amount_mode.currentData()=="split"
        self.amount_label.setVisible(not split); self.amount_col.setVisible(not split); self.invert.setVisible(not split)
        self.debit_label.setVisible(split); self.debit_col.setVisible(split)
        self.credit_label.setVisible(split); self.credit_col.setVisible(split)
        has_account=bool(self._value(self.account_col))
        self.use_account_column.setEnabled(has_account)
        if not has_account:
            self.use_account_column.setChecked(False)
        use_rows=self.use_account_column.isChecked()
        self.account.setEnabled(not use_rows)
        self.account_label.setText("Fallback account" if use_rows else "Import to account")

    def _mapping_changed(self, *args):
        self._update_amount_controls()
        if self.file_type=="csv":
            self.profile_note.setText("Mapping changed. Save it as the default for this CSV format if it looks right.")
        self._refresh_preview()

    def _account_target(self):
        text=self.account.currentText().strip()
        index=self.account.findText(text)
        if index >= 0:
            return self.account.itemData(index) or text
        return text

    def _profile(self):
        return {
            "date_col":self._value(self.date_col),
            "description_col":self._value(self.desc_col),
            "amount_mode":self.amount_mode.currentData(),
            "amount_col":self._value(self.amount_col),
            "debit_col":self._value(self.debit_col),
            "credit_col":self._value(self.credit_col),
            "account_col":self._value(self.account_col),
            "balance_col":self._value(self.balance_col),
            "invert_amounts":self.invert.isChecked(),
            "use_account_column":self.use_account_column.isChecked(),
        }

    def _save_default(self):
        if not self.header_signature or not self._mapping_valid():
            QMessageBox.information(self,"Save as default","Finish a valid mapping first."); return
        try:
            self.vault.save_import_profile(self.header_signature,self._profile())
            self.profile_note.setText("Default saved for this CSV layout.")
        except Exception as exc:
            QMessageBox.warning(self,"Save as default",str(exc))

    def _mapping_valid(self):
        if self.file_type!="csv": return True
        p=self._profile()
        if not p["date_col"] or not p["description_col"]: return False
        if p["amount_mode"]=="single":
            return bool(p["amount_col"])
        return bool(p["debit_col"] or p["credit_col"])

    def _refresh_preview(self):
        path=self.file.text().strip()
        if not path or not self.file_type:
            self.import_btn.setEnabled(False); return
        try:
            if self.file_type=="csv":
                if not self._mapping_valid():
                    self.rows=[]; self.preview.setRowCount(0)
                    self.summary.setText("Map Date, Description, and the amount field(s) to continue.")
                    self.import_btn.setEnabled(False); return
                p=self._profile()
                rows,skipped=parse_csv(
                    path,date_col=p["date_col"],description_col=p["description_col"],
                    amount_mode=p["amount_mode"],amount_col=p["amount_col"] or None,
                    debit_col=p["debit_col"] or None,credit_col=p["credit_col"] or None,
                    account_col=p["account_col"] or None,balance_col=p["balance_col"] or None,
                    invert_amounts=p["invert_amounts"],
                )
            else:
                rows,skipped=parse_ofx(path)
        except Exception as exc:
            self.rows=[]; self.preview.setRowCount(0); self.summary.setText(str(exc)); self.import_btn.setEnabled(False); return

        self.rows=rows; self.skipped=skipped
        shown=rows[:12]; self.preview.setRowCount(len(shown))
        for r,row in enumerate(shown):
            target=(row.account_hint or self._account_target()) if self.use_account_column.isChecked() else self._account_target()
            display_target=self.state.account_display_name(target) if target else "—"
            vals=[row.posted.strftime("%b %d, %Y"),row.merchant,money(row.amount_cents/100),display_target]
            for c,val in enumerate(vals):
                item=_CenteredTableItem(val)
                self.preview.setItem(r,c,item)

        suffix=f" · {skipped} skipped" if skipped else ""
        kind="CSV" if self.file_type=="csv" else "QFX / OFX"
        self.summary.setText(f"{len(rows)} valid {kind} transactions{suffix}. Showing the first {len(shown)}.")
        has_target=bool(self._account_target()) or (
            self.use_account_column.isChecked() and any(r.account_hint for r in rows)
        )
        self.import_btn.setEnabled(bool(rows and has_target and self.vault.unlocked))

    def _import(self):
        if not self.vault.unlocked:
            QMessageBox.warning(self,"Import statement","Unlock PrivateMoney before importing."); return
        result=self.state.import_transactions(
            self._account_target(),
            self.rows,
            use_account_column=(self.file_type=="csv" and self.use_account_column.isChecked()),
        )
        QMessageBox.information(
            self,"Import complete",
            f"Imported {result['imported']} transactions.\nSkipped {result['duplicates']} duplicates."
        )
        self.accept()


class NewBudgetDialog(QDialog):
    def __init__(self, state, budget=None, parent=None):
        super().__init__(parent); self.state=state; self.budget=budget; self.deleted=False
        editing=budget is not None
        self.setWindowTitle("Edit budget" if editing else "New budget")
        self.setObjectName("PasswordDialog")
        l=QVBoxLayout(self); l.setContentsMargins(22,22,22,22); l.setSpacing(10)
        title=QLabel("Edit budget" if editing else "New budget"); title.setObjectName("SectionTitle"); l.addWidget(title)
        self.category=_NoWheelComboBox(); self.category.setEditable(True)
        self.category.addItems(state.categories())
        self.limit=QDoubleSpinBox(); self.limit.setRange(0,100000000); self.limit.setDecimals(2); self.limit.setPrefix("$"); self.limit.setValue(500)
        if editing:
            self.category.setCurrentText(budget.category)
            self.limit.setValue(float(budget.limit))
        form=QGridLayout()
        form.addWidget(QLabel("Category"),0,0); form.addWidget(self.category,0,1)
        form.addWidget(QLabel("Monthly limit"),1,0); form.addWidget(self.limit,1,1)
        l.addLayout(form)

        buttons=QHBoxLayout()
        if editing:
            delete=QPushButton("Delete budget"); delete.setObjectName("Danger"); delete.clicked.connect(self._delete)
            buttons.addWidget(delete)
        buttons.addStretch()
        cancel=QPushButton("Cancel"); cancel.setObjectName("Secondary"); cancel.clicked.connect(self.reject)
        save=QPushButton("Save changes" if editing else "Save budget"); save.setObjectName("Primary"); save.clicked.connect(self.accept)
        buttons.addWidget(cancel); buttons.addWidget(save); l.addLayout(buttons)

    def _delete(self):
        answer=QMessageBox.question(
            self,
            "Delete budget",
            f'Delete the "{self.budget.category}" budget?',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer==QMessageBox.Yes:
            self.deleted=True
            self.accept()

    def values(self):
        return self.category.currentText().strip(), float(self.limit.value())


class NewGoalDialog(QDialog):
    def __init__(self, state, goal=None, parent=None):
        super().__init__(parent); self.state=state; self.existing_goal=goal
        editing=goal is not None
        self.setWindowTitle("Edit monetary goal" if editing else "New monetary goal")
        self.setObjectName("PasswordDialog")
        l=QVBoxLayout(self); l.setContentsMargins(22,22,22,22); l.setSpacing(10)
        title=QLabel("Edit monetary goal" if editing else "New monetary goal"); title.setObjectName("SectionTitle"); l.addWidget(title)
        note=QLabel("Build a rule such as: amount spent at Walmart over 1 month is less than $300.")
        note.setWordWrap(True); note.setStyleSheet(f"color:{theme.MUTED}"); l.addWidget(note)

        self.direction=_NoWheelComboBox(); self.direction.addItem("spent","spent"); self.direction.addItem("received","received")
        self.scope_type=_NoWheelComboBox(); self.scope_type.addItem("merchant","merchant"); self.scope_type.addItem("bank / account","bank"); self.scope_type.addItem("category","category")
        self.scope_value=_NoWheelComboBox(); self.scope_value.setEditable(True)
        self.period_count=QSpinBox(); self.period_count.setRange(1,120); self.period_count.setValue(1)
        self.period_unit=_NoWheelComboBox()
        for label,data in (("day","day"),("week","week"),("month","month"),("months","months"),("year","year")):
            self.period_unit.addItem(label,data)
        self.operator=_NoWheelComboBox()
        for label in ("less than","greater than","equal to"): self.operator.addItem(label,label)
        self.target=QDoubleSpinBox(); self.target.setRange(0,1000000000); self.target.setDecimals(2); self.target.setPrefix("$"); self.target.setValue(100)

        form=QGridLayout(); form.setHorizontalSpacing(10); form.setVerticalSpacing(9)
        fields=[
            ("Amount",self.direction),("At / from",self.scope_type),("Merchant / bank / category",self.scope_value),
            ("Period count",self.period_count),("Period",self.period_unit),("Comparison",self.operator),("Target",self.target),
        ]
        for row,(label,widget) in enumerate(fields):
            form.addWidget(QLabel(label),row,0); form.addWidget(widget,row,1)
        l.addLayout(form)
        self.scope_type.currentIndexChanged.connect(self._refresh_scope_values)

        if editing:
            for combo,value in (
                (self.direction,goal.direction),
                (self.scope_type,goal.scope_type),
                (self.period_unit,goal.period_unit),
                (self.operator,goal.operator),
            ):
                idx=combo.findData(value)
                if idx>=0: combo.setCurrentIndex(idx)
            self._refresh_scope_values()
            self.scope_value.setEditText(goal.scope_value)
            self.period_count.setValue(int(goal.period_count))
            self.target.setValue(float(goal.target))
        else:
            self._refresh_scope_values()

        buttons=QHBoxLayout(); buttons.addStretch()
        cancel=QPushButton("Cancel"); cancel.setObjectName("Secondary"); cancel.clicked.connect(self.reject)
        save=QPushButton("Save changes" if editing else "Save goal"); save.setObjectName("Primary"); save.clicked.connect(self._accept_if_valid)
        buttons.addWidget(cancel); buttons.addWidget(save); l.addLayout(buttons)

    def _refresh_scope_values(self,*_):
        current=self.scope_value.currentText().strip()
        kind=self.scope_type.currentData()
        if kind=="merchant":
            values=sorted({tx.merchant for tx in self.state.transactions() if tx.merchant},key=str.casefold)
        elif kind=="category":
            values=self.state.categories()
        else:
            values=sorted({(a.nickname or "").strip() or a.name for a in self.state.accounts()},key=str.casefold)
        self.scope_value.clear(); self.scope_value.addItems(values)
        if current: self.scope_value.setEditText(current)

    def _accept_if_valid(self):
        if not self.scope_value.currentText().strip():
            QMessageBox.information(self,"Goal","Choose or enter a merchant, bank/account, or category.")
            return
        self.accept()

    def goal(self):
        return Goal(
            id=self.existing_goal.id if self.existing_goal is not None else f"goal-{uuid.uuid4()}",
            direction=self.direction.currentData(),
            scope_type=self.scope_type.currentData(),
            scope_value=self.scope_value.currentText().strip(),
            period_count=int(self.period_count.value()),
            period_unit=self.period_unit.currentData(),
            operator=self.operator.currentData(),
            target=float(self.target.value()),
        )


class BudgetsPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        top=QHBoxLayout()
        top.addWidget(page_header("Budgets & Goals","Monthly category budgets and flexible monetary goals."))
        top.addStretch()
        self.new_budget=QPushButton("New budget"); self.new_budget.setObjectName("Secondary"); self.new_budget.clicked.connect(self._new_budget)
        self.new_goal=QPushButton("New goal"); self.new_goal.setObjectName("Primary"); self.new_goal.clicked.connect(self._new_goal)
        top.addWidget(self.new_budget); top.addWidget(self.new_goal); l.addLayout(top)

        self.budget_card=Card(); self.budget_layout=QVBoxLayout(self.budget_card); self.budget_layout.setContentsMargins(22,18,22,18); self.budget_layout.setSpacing(5)
        bh=QLabel("Budgets"); bh.setObjectName("SectionTitle"); self.budget_layout.addWidget(bh)
        l.addWidget(self.budget_card)

        self.goal_card=Card(); self.goal_layout=QVBoxLayout(self.goal_card); self.goal_layout.setContentsMargins(22,18,22,18); self.goal_layout.setSpacing(8)
        gh=QLabel("Goals"); gh.setObjectName("SectionTitle"); self.goal_layout.addWidget(gh)
        l.addWidget(self.goal_card,1)
        self.refresh()

    @staticmethod
    def _clear_after_heading(layout):
        while layout.count()>1:
            item=layout.takeAt(1)
            widget=item.widget()
            if widget is not None: widget.deleteLater()

    def _new_budget(self):
        dialog=NewBudgetDialog(self.state,None,self)
        if dialog.exec()!=QDialog.Accepted: return
        category,limit=dialog.values()
        if category:
            self.state.set_budget(category,limit)
            self.refresh()

    def _edit_budget(self, budget):
        dialog=NewBudgetDialog(self.state,budget,self)
        if dialog.exec()!=QDialog.Accepted:
            return
        if dialog.deleted:
            self.state.delete_budget(budget.category)
            self.refresh()
            return
        category,limit=dialog.values()
        if not category:
            return
        if category.casefold()!=budget.category.casefold():
            self.state.delete_budget(budget.category)
        self.state.set_budget(category,limit)
        self.refresh()

    def _new_goal(self):
        dialog=NewGoalDialog(self.state,None,self)
        if dialog.exec()!=QDialog.Accepted: return
        self.state.add_goal(dialog.goal())
        self.refresh()

    def _edit_goal(self, goal):
        dialog=NewGoalDialog(self.state,goal,self)
        if dialog.exec()!=QDialog.Accepted:
            return
        if self.state.update_goal(goal.id,dialog.goal()):
            self.refresh()

    def _delete_goal(self, goal_id):
        if self.state.delete_goal(goal_id): self.refresh()

    def refresh(self):
        self._clear_after_heading(self.budget_layout)
        budgets=self.state.budgets()
        if budgets:
            for row in budgets:
                self.budget_layout.addWidget(
                    BudgetRow(
                        row.category,row.spent,row.limit,
                        edit_callback=lambda budget=row:self._edit_budget(budget),
                    )
                )
        else:
            note=QLabel("No budgets yet."); note.setStyleSheet(f"color:{theme.MUTED}"); self.budget_layout.addWidget(note)
        self.budget_layout.addStretch()

        self._clear_after_heading(self.goal_layout)
        goals=self.state.goals()
        if not goals:
            note=QLabel("No monetary goals yet."); note.setStyleSheet(f"color:{theme.MUTED}"); self.goal_layout.addWidget(note)
        for goal in goals:
            status=self.state.goal_status(goal)
            row=QFrame(); row.setStyleSheet("background:transparent;border:0;")
            rl=QHBoxLayout(row); rl.setContentsMargins(0,6,0,6); rl.setSpacing(10)
            period=(f"{goal.period_count} {goal.period_unit}" + ("s" if goal.period_count != 1 and not goal.period_unit.endswith("s") else ""))
            rule=QLabel(f"Amount {goal.direction} at/from {goal.scope_value} over {period} is {goal.operator} {money(goal.target)}")
            rule.setWordWrap(True)
            actual=QLabel(f"Current: {money(status['actual'])}")
            actual.setStyleSheet(f"color:{theme.POSITIVE if status['met'] else theme.NEGATIVE};font-weight:700")
            edit=QPushButton("Edit"); edit.setObjectName("Secondary"); edit.setFixedWidth(72)
            edit.clicked.connect(lambda checked=False,g=goal:self._edit_goal(g))
            delete=QToolButton(); delete.setText("×"); delete.setToolTip("Delete goal")
            delete.clicked.connect(lambda checked=False,gid=goal.id:self._delete_goal(gid))
            rl.addWidget(rule,1); rl.addWidget(actual); rl.addWidget(edit); rl.addWidget(delete)
            self.goal_layout.addWidget(row)
        self.goal_layout.addStretch()


class RecurringPage(QWidget):
    SORTS=(
        ("Next due: soonest","next_asc"),("Next due: latest","next_desc"),
        ("Oldest","oldest"),("Newest","newest"),
        ("Price: highest","price_desc"),("Price: lowest","price_asc"),
        ("Age: oldest","age_desc"),("Age: newest","age_asc"),
        ("Total: highest","total_desc"),("Frequency: most often","frequency_asc"),
        ("Occurrences: most","occurrences_desc"),
    )

    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(14)
        top=QHBoxLayout()
        top.addWidget(page_header("Recurring","Detected repeating spending and income."))
        top.addStretch(); top.addWidget(QLabel("Sort"))
        self.sort=_NoWheelComboBox()
        for label,key in self.SORTS: self.sort.addItem(label,key)
        self.sort.currentIndexChanged.connect(self.refresh); top.addWidget(self.sort); l.addLayout(top)

        self.spending_table=self._make_table(True)
        self.income_table=self._make_table(False)
        l.addWidget(card_with_title("Spending",self.spending_table),1)
        l.addWidget(card_with_title("Income",self.income_table),1)
        self.refresh()

    def _make_table(self,include_category):
        headers=["Merchant"]
        if include_category: headers.append("Category")
        headers += ["Cadence / next","Amount","First seen","Total","Occurrences"]
        table=QTableWidget(0,len(headers))
        table.setHorizontalHeaderLabels(headers)
        style_table(table)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setDefaultSectionSize(34)
        return table

    def _sorted(self,rows):
        key=self.sort.currentData() if hasattr(self,"sort") else "next_asc"
        reverse=key in {"next_desc","price_desc","age_desc","total_desc","occurrences_desc"}
        accessors={
            "next_asc":lambda x:x["charge"].next_date,"next_desc":lambda x:x["charge"].next_date,
            "oldest":lambda x:x["first_seen"],"newest":lambda x:x["first_seen"],
            "price_desc":lambda x:x["charge"].amount,"price_asc":lambda x:x["charge"].amount,
            "age_desc":lambda x:x["age_days"],"age_asc":lambda x:x["age_days"],
            "total_desc":lambda x:x["total_amount"],"frequency_asc":lambda x:x["frequency_days"],
            "occurrences_desc":lambda x:x["occurrences"],
        }
        if key=="newest": reverse=True
        return sorted(rows,key=accessors.get(key,accessors["next_asc"]),reverse=reverse)

    def _fill(self,table,rows,empty_text,include_category):
        table.clearSpans(); rows=self._sorted(rows); table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            x=row["charge"]
            vals=[x.merchant]
            if include_category: vals.append(x.category)
            vals += [f"{x.cadence} · {x.next_date:%b %d}",money(x.amount),
                     row["first_seen"].strftime("%b %d, %Y"),money(row["total_amount"]),str(row["occurrences"])]
            for col,val in enumerate(vals):
                item=_CenteredTableItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(r,col,item)
        if not rows:
            table.setRowCount(1)
            item=_CenteredTableItem(empty_text); item.setTextAlignment(Qt.AlignCenter)
            table.setItem(0,0,item); table.setSpan(0,0,1,table.columnCount())

    def refresh(self,*_):
        details=self.state.recurring_details()
        self._fill(self.spending_table,[x for x in details if x["charge"].direction=="spending"],"No spending patterns detected.",True)
        self._fill(self.income_table,[x for x in details if x["charge"].direction=="income"],"No income patterns detected.",False)


class NetWorthPage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent); self.state=state
        l=QVBoxLayout(self); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Net worth","Assets minus liabilities, tracked over time."))
        self.chart=LineChart(state.net_worth()); l.addWidget(card_with_title("Net worth history",self.chart,"Reconstructed from transaction dates"),1)
    def refresh(self): self.chart.set_points(self.state.net_worth())


class CategoryTagFilter(QFrame):
    changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self._selected=[]; self._options=[]; self._chips=[]; self._scroll=0
        self.setObjectName("TagField")
        self.setStyleSheet(
            f"QFrame#TagField {{ background:{theme.CHARCOAL}; border:1px solid {theme.OUTLINE}; border-radius:10px; }}"
            f"QToolButton#TagChip {{ background:{theme.DEEP_VIOLET}; border:1px solid {theme.VIOLET}; border-radius:8px; padding:4px 7px; color:{theme.IVORY}; }}"
            f"QToolButton#TagDrop {{ background:transparent; border:0; color:{theme.MUTED}; font-weight:700; }}"
            f"QToolButton#TagDrop:hover {{ color:{theme.IVORY}; }}"
        )
        self.setFixedHeight(42); self.setMinimumWidth(280); self.setMaximumWidth(430)

        self.viewport=QWidget(self); self.viewport.setStyleSheet("background:transparent;")
        self.input=QLineEdit(self.viewport); self.input.setFrame(False)
        self.input.setFixedWidth(140); self.input.setPlaceholderText("Search categories…")
        self.input.setStyleSheet("QLineEdit { background:transparent; border:0; padding:4px; }")

        self.drop=QToolButton(self); self.drop.setObjectName("TagDrop"); self.drop.setText("▾")
        self.drop.setFixedWidth(30); self.drop.clicked.connect(self._show_menu)
        self.menu=QMenu(self)
        self._layout_contents()

    def set_options(self,options):
        self._options=list(options)

    def selected(self):
        return list(self._selected)

    def clear(self):
        if not self._selected: return
        self._selected=[]; self._rebuild(); self.changed.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event); self._layout_contents()

    def wheelEvent(self,event):
        delta=event.angleDelta().y() or event.angleDelta().x() or event.pixelDelta().y() or event.pixelDelta().x()
        if delta:
            self._scroll=max(0,min(self._max_scroll(),self._scroll-delta))
            self._layout_contents(); event.accept(); return
        super().wheelEvent(event)

    def _content_width(self):
        gap=5
        return sum(chip.sizeHint().width()+gap for chip in self._chips)+self.input.width()

    def _max_scroll(self):
        return max(0,self._content_width()-max(1,self.viewport.width()))

    def _layout_contents(self):
        arrow_w=30
        self.viewport.setGeometry(7,4,max(1,self.width()-arrow_w-12),34)
        self.drop.setGeometry(self.width()-arrow_w-3,4,arrow_w,34)
        self._scroll=max(0,min(self._max_scroll(),self._scroll))
        x=-self._scroll
        for chip in self._chips:
            w=chip.sizeHint().width()
            chip.setGeometry(x,2,w,30); x+=w+5
        self.input.setGeometry(x,2,140,30)

    def _show_menu(self):
        self.menu.clear()
        query=self.input.text().strip().casefold()
        for option in self._options:
            if option in self._selected or (query and query not in option.casefold()): continue
            action=self.menu.addAction(option)
            action.triggered.connect(lambda checked=False,value=option:self._add(value))
        if not self.menu.actions():
            empty=self.menu.addAction("No matching categories"); empty.setEnabled(False)
        self.menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def _add(self,value):
        if value in self._selected: return
        saved=self._scroll
        self._selected.append(value); self.input.clear()
        self._rebuild(saved); self.changed.emit()

    def _remove(self,value):
        if value not in self._selected: return
        saved=self._scroll
        self._selected.remove(value)
        self._rebuild(saved); self.changed.emit()

    def _rebuild(self,saved_scroll=None):
        if saved_scroll is None: saved_scroll=self._scroll
        for chip in self._chips: chip.deleteLater()
        self._chips=[]
        for value in self._selected:
            chip=QToolButton(self.viewport); chip.setObjectName("TagChip")
            chip.setText(value+"  ×"); chip.setToolTip("Remove "+value); chip.setFocusPolicy(Qt.NoFocus)
            chip.clicked.connect(lambda checked=False,v=value:self._remove(v))
            chip.show(); self._chips.append(chip)
        self._scroll=saved_scroll
        self._layout_contents()


class BulkCategorizeDialog(QDialog):
    def __init__(self,state,parent=None):
        super().__init__(parent); self.state=state
        self.setWindowTitle("Bulk categorize")
        self.setObjectName("PasswordDialog")
        l=QVBoxLayout(self); l.setContentsMargins(22,22,22,22); l.setSpacing(12)
        title=QLabel("Bulk categorize"); title.setObjectName("SectionTitle"); l.addWidget(title)
        note=QLabel("Apply one category to every transaction from the selected merchant.")
        note.setWordWrap(True); note.setStyleSheet(f"color:{theme.MUTED}"); l.addWidget(note)
        self.merchant=_NoWheelComboBox(); self.merchant.setEditable(True)
        self.merchant.addItems(sorted({t.merchant for t in state.transactions() if t.merchant},key=str.casefold))
        self.category=_NoWheelComboBox(); self.category.addItems(state.categories())
        form=QGridLayout(); form.setHorizontalSpacing(10); form.setVerticalSpacing(9)
        form.addWidget(QLabel("Merchant"),0,0); form.addWidget(self.merchant,0,1)
        form.addWidget(QLabel("Category"),1,0); form.addWidget(self.category,1,1)
        l.addLayout(form)
        buttons=QHBoxLayout(); buttons.addStretch()
        cancel=QPushButton("Cancel"); cancel.setObjectName("Secondary"); cancel.clicked.connect(self.reject)
        apply=QPushButton("Apply to all"); apply.setObjectName("Primary"); apply.clicked.connect(self.accept)
        buttons.addWidget(cancel); buttons.addWidget(apply); l.addLayout(buttons)

    def values(self):
        return self.merchant.currentText().strip(),self.category.currentText().strip()


class TransactionsPage(QWidget):
    def __init__(self, state, vault=None, parent=None):
        super().__init__(parent); self.state=state; self.vault=vault; self._dates_initialized=False
        l=QVBoxLayout(self); l.setContentsMargins(28,20,28,24); l.setSpacing(12)

        top=QHBoxLayout()
        top.addWidget(page_header("Transactions","Filter, review, categorize, and analyze tracked activity."))
        top.addStretch()
        self.bulk_btn=QPushButton("Bulk categorize")
        self.bulk_btn.setObjectName("Secondary")
        self.bulk_btn.clicked.connect(self._open_bulk_categorize)
        top.addWidget(self.bulk_btn)
        self.import_btn=QPushButton("Import statement")
        self.import_btn.setObjectName("Primary")
        self.import_btn.clicked.connect(self._import_statement)
        top.addWidget(self.import_btn)
        l.addLayout(top)

        grid=QGridLayout(); grid.setSpacing(12)
        self.spend=DonutChart([])
        self.cash=CashFlowChart([])
        self.spend.setFixedHeight(225)
        self.cash.setFixedHeight(205)
        grid.addWidget(card_with_title("Spending by category",self.spend),0,0)
        grid.addWidget(card_with_title("Income vs. spending",self.cash),0,1)
        l.addLayout(grid)

        filter_card=Card()
        filter_outer=QVBoxLayout(filter_card)
        filter_outer.setContentsMargins(16,12,16,12)
        filter_outer.setSpacing(8)

        filter_head=QHBoxLayout()
        filter_head.addWidget(QLabel("Filters"))
        filter_head.addStretch()
        self.filter_toggle=QToolButton()
        self.filter_toggle.setText("More filters ▾")
        self.filter_toggle.setCheckable(True)
        self.filter_toggle.toggled.connect(self._toggle_filters)
        filter_head.addWidget(self.filter_toggle)
        filter_outer.addLayout(filter_head)

        basic=QGridLayout()
        basic.setHorizontalSpacing(10); basic.setVerticalSpacing(7)
        self.category_filter=CategoryTagFilter()
        self.history_filter=_NoWheelComboBox()
        self.history_filter.addItem("All history",None)
        self.history_filter.addItem("1 month",1)
        self.history_filter.addItem("3 months",3)
        self.history_filter.addItem("6 months",6)
        self.history_filter.addItem("12 months",12)
        self.account_filter=_NoWheelComboBox()
        self.merchant_filter=QLineEdit(); self.merchant_filter.setPlaceholderText("Merchant contains…")

        for col,(label,widget) in enumerate((
            ("Categories",self.category_filter),
            ("History",self.history_filter),
            ("Account",self.account_filter),
            ("Merchant",self.merchant_filter),
        )):
            basic.addWidget(QLabel(label),0,col)
            basic.addWidget(widget,1,col)
        filter_outer.addLayout(basic)

        self.advanced_filters=QWidget()
        self.advanced_filters.setObjectName("AdvancedFilters")
        self.advanced_filters.setStyleSheet("QWidget#AdvancedFilters { background:transparent; }")
        advanced=QGridLayout(self.advanced_filters)
        advanced.setContentsMargins(0,0,0,0)
        advanced.setHorizontalSpacing(10); advanced.setVerticalSpacing(7)
        self.start_date=QDateEdit(); self.start_date.setCalendarPopup(True)
        self.end_date=QDateEdit(); self.end_date.setCalendarPopup(True)
        self.start_date.setMinimumDate(date(1900,1,1)); self.end_date.setMinimumDate(date(1900,1,1))
        self.min_amount=QLineEdit(); self.min_amount.setPlaceholderText("Min $")
        self.max_amount=QLineEdit(); self.max_amount.setPlaceholderText("Max $")
        for col,(label,widget) in enumerate((
            ("Start date",self.start_date),
            ("End date",self.end_date),
            ("Dollar min",self.min_amount),
            ("Dollar max",self.max_amount),
        )):
            advanced.addWidget(QLabel(label),0,col)
            advanced.addWidget(widget,1,col)
        self.advanced_filters.hide()
        filter_outer.addWidget(self.advanced_filters)

        footer=QHBoxLayout()
        self.clear_filters=QPushButton("Reset filters"); self.clear_filters.setObjectName("Secondary")
        footer.addWidget(self.clear_filters)
        self.summary=QLabel(); self.summary.setWordWrap(True); self.summary.setStyleSheet(f"color:{theme.MUTED}")
        footer.addWidget(self.summary,1)
        filter_outer.addLayout(footer)
        l.addWidget(filter_card)

        self.transactions=transaction_table([])
        l.addWidget(self.transactions,1)

        self.category_filter.changed.connect(self._apply_filters)
        for combo in (self.history_filter,self.account_filter):
            combo.currentIndexChanged.connect(self._apply_filters)
        self.start_date.dateChanged.connect(self._apply_filters)
        self.end_date.dateChanged.connect(self._apply_filters)
        self.min_amount.textChanged.connect(self._apply_filters)
        self.max_amount.textChanged.connect(self._apply_filters)
        self.merchant_filter.textChanged.connect(self._apply_filters)
        self.clear_filters.clicked.connect(self._reset_filters)
        self.refresh()

    def _toggle_filters(self, expanded):
        self.advanced_filters.setVisible(bool(expanded))
        self.filter_toggle.setText("Fewer filters ▴" if expanded else "More filters ▾")

    def _import_statement(self):
        if self.vault is None or not self.vault.unlocked:
            QMessageBox.information(self,"Import statement","Unlock PrivateMoney before importing a statement.")
            return
        dialog=StatementImportDialog(self.state,self.vault,self)
        dialog.exec()
        self.refresh()

    def _category_changed(self, transaction, category):
        self.state.set_transaction_category(transaction,category)
        self._apply_filters()

    def _open_bulk_categorize(self):
        dialog=BulkCategorizeDialog(self.state,self)
        if dialog.exec()!=QDialog.Accepted:
            return
        merchant,category=dialog.values()
        if not merchant or not category:
            return
        changed=self.state.bulk_set_merchant_category(merchant,category)
        if changed:
            self.refresh()
        else:
            self.summary.setText(f"No transactions from {merchant} needed a category change.")

    @staticmethod
    def _parse_amount(text):
        text=text.strip().replace("$","").replace(",","")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _subtract_months(day, months):
        month=day.month-1-int(months)
        year=day.year+month//12
        month=month%12+1
        month_lengths=(31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31)
        return date(year,month,min(day.day,month_lengths[month-1]))

    def _filtered_rows(self):
        rows=self.state.transactions()
        categories=set(self.category_filter.selected())
        account=self.account_filter.currentData()
        merchant=self.merchant_filter.text().strip().casefold()
        months=self.history_filter.currentData()
        min_amount=self._parse_amount(self.min_amount.text())
        max_amount=self._parse_amount(self.max_amount.text())

        if categories:
            rows=[t for t in rows if t.category in categories]
        if account:
            rows=[t for t in rows if t.account==account]
        if merchant:
            rows=[t for t in rows if merchant in t.merchant.casefold()]
        if months:
            cutoff=self._subtract_months(date.today(),months)
            rows=[t for t in rows if t.posted>=cutoff]

        start=self.start_date.date().toPython()
        end=self.end_date.date().toPython()
        rows=[t for t in rows if start<=t.posted<=end]

        if min_amount is not None:
            rows=[t for t in rows if abs(t.amount)>=min_amount]
        if max_amount is not None:
            rows=[t for t in rows if abs(t.amount)<=max_amount]
        return rows

    @staticmethod
    def _spending_segments(rows):
        totals={}
        for tx in rows:
            if tx.amount<0:
                category=tx.category or "Other"
                totals[category]=totals.get(category,0.0)-tx.amount
        return sorted(((k,round(v,2)) for k,v in totals.items()),key=lambda x:x[1],reverse=True)[:8]

    @staticmethod
    def _cashflow_rows(rows):
        monthly={}
        for tx in rows:
            key=(tx.posted.year,tx.posted.month)
            bucket=monthly.setdefault(key,[0.0,0.0])
            if tx.amount>=0:
                bucket[0]+=tx.amount
            else:
                bucket[1]+=-tx.amount
        keys=sorted(monthly)[-6:]
        return [(date(y,m,1).strftime("%b"),round(monthly[(y,m)][0],2),round(monthly[(y,m)][1],2)) for y,m in keys]

    def _apply_filters(self, *_):
        rows=self._filtered_rows()
        fill_transaction_table(
            self.transactions,
            rows,
            category_callback=self._category_changed,
            categories=self.state.categories(),
            account_labeler=self.state.account_display_name,
        )
        self.spend.set_segments(self._spending_segments(rows))
        self.cash.set_rows(self._cashflow_rows(rows))
        spending=sum(-t.amount for t in rows if t.amount<0)
        income=sum(t.amount for t in rows if t.amount>0)
        net=sum(t.amount for t in rows)
        self.summary.setText(
            f"{len(rows)} transactions · spending {money(spending)} · income {money(income)} · net {money(net)}"
            if rows else "No matching transactions"
        )

    def _reset_filters(self):
        self.category_filter.clear()
        self.history_filter.setCurrentIndex(0)
        self.account_filter.setCurrentIndex(0)
        self.min_amount.clear(); self.max_amount.clear(); self.merchant_filter.clear()
        rows=self.state.transactions()
        oldest=min((t.posted for t in rows),default=date.today())
        self.start_date.setDate(oldest)
        self.end_date.setDate(date.today())
        self._apply_filters()

    def refresh(self):
        rows=self.state.transactions()
        categories=self.state.categories()
        self.category_filter.set_options(categories)

        previous_account=self.account_filter.currentData()
        self.account_filter.blockSignals(True)
        self.account_filter.clear()
        self.account_filter.addItem("All accounts",None)
        for account in self.state.accounts():
            self.account_filter.addItem((account.nickname or "").strip() or account.name,account.name)
        index=self.account_filter.findData(previous_account)
        self.account_filter.setCurrentIndex(index if index>=0 else 0)
        self.account_filter.blockSignals(False)

        if not self._dates_initialized:
            oldest=min((t.posted for t in rows),default=date.today())
            self.start_date.blockSignals(True); self.end_date.blockSignals(True)
            self.start_date.setDate(oldest)
            self.end_date.setDate(date.today())
            self.start_date.blockSignals(False); self.end_date.blockSignals(False)
            self._dates_initialized=True

        self.import_btn.setEnabled(bool(self.vault and self.vault.unlocked))
        self.import_btn.setToolTip("" if self.import_btn.isEnabled() else "Unlock PrivateMoney to import statements.")
        self._apply_filters()


class SettingsPage(QScrollArea):
    def __init__(self, state, api_server, plaid, api_token, vault, on_logout=None, on_login=None, on_delete_data=None, parent=None):
        super().__init__(parent); self.state=state; self.api_server=api_server; self.plaid=plaid; self.api_token=api_token; self.vault=vault; self.on_logout=on_logout; self.on_login=on_login; self.on_delete_data=on_delete_data; self._vault_error=''
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        host=QWidget(); self.setWidget(host); l=QVBoxLayout(host); l.setContentsMargins(28,24,28,28); l.setSpacing(16)
        l.addWidget(page_header("Settings","Private by default; external access must be explicitly configured."))

        access=Card(); alog=QVBoxLayout(access); alog.setContentsMargins(20,18,20,18); alog.setSpacing(9)
        ah=QLabel("Access"); ah.setObjectName("SectionTitle"); alog.addWidget(ah)
        self.access_status=QLabel(); self.access_status.setWordWrap(True); self.access_status.setStyleSheet(f"color:{theme.MUTED}"); alog.addWidget(self.access_status)
        access_buttons=QHBoxLayout()
        self.login_logout_btn=QPushButton("Log out"); self.login_logout_btn.setObjectName("Secondary"); self.login_logout_btn.clicked.connect(self._access_action)
        self.delete_data_btn=QPushButton("DELETE DATA"); self.delete_data_btn.setObjectName("Danger"); self.delete_data_btn.clicked.connect(self._delete_data)
        access_buttons.addWidget(self.login_logout_btn); access_buttons.addWidget(self.delete_data_btn); access_buttons.addStretch()
        alog.addLayout(access_buttons)
        danger_note=QLabel("Delete data permanently removes all PrivateMoney data on this computer and starts fresh.")
        danger_note.setWordWrap(True); danger_note.setStyleSheet(f"color:{theme.MUTED}"); alog.addWidget(danger_note)
        l.addWidget(access)

        pc=Card(); p=QVBoxLayout(pc); p.setContentsMargins(20,18,20,18); p.setSpacing(9)
        h=QLabel("Plaid bank connection"); h.setObjectName("SectionTitle"); p.addWidget(h)
        steps=QLabel("1. Set Plaid API credentials  →  2. Connect bank in Plaid Link  →  3. Refresh & sync")
        steps.setWordWrap(True); steps.setStyleSheet(f"color:{theme.MUTED}; background:transparent;"); p.addWidget(steps)
        self.plaid_status=QLabel(); self.plaid_status.setWordWrap(True); self.plaid_status.setStyleSheet(f"color:{theme.MUTED}"); p.addWidget(self.plaid_status)
        environment_note=QLabel("Production · real bank data")
        environment_note.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
        p.addWidget(environment_note)
        self.client_id=QLineEdit(); self.client_id.setPlaceholderText("Plaid client_id")
        self.secret=QLineEdit(); self.secret.setPlaceholderText("Plaid Production secret"); self.secret.setEchoMode(QLineEdit.Password)
        p.addWidget(self.client_id); p.addWidget(self.secret)
        buttons=QHBoxLayout(); self.configure_btn=QPushButton("Set API credentials"); self.configure_btn.setObjectName("Secondary"); self.configure_btn.clicked.connect(self._configure_plaid)
        self.connect_btn=QPushButton("Connect bank"); self.connect_btn.setObjectName("Primary"); self.connect_btn.clicked.connect(self._connect_bank)
        self.sync_btn=QPushButton("Refresh & sync"); self.sync_btn.setObjectName("Secondary"); self.sync_btn.setToolTip("Requests a fresh Plaid transaction update when Transactions Refresh is available, then syncs available changes."); self.sync_btn.clicked.connect(self._sync_now)
        buttons.addWidget(self.configure_btn); buttons.addWidget(self.connect_btn); buttons.addWidget(self.sync_btn); buttons.addStretch(); p.addLayout(buttons)
        self.plaid_privacy=QLabel(); privacy=self.plaid_privacy
        privacy.setWordWrap(True); privacy.setStyleSheet(f"color:{theme.MUTED}"); p.addWidget(privacy); l.addWidget(pc)

        self.dev_gate=Card(); dg=QVBoxLayout(self.dev_gate); dg.setContentsMargins(20,18,20,18); dg.setSpacing(9)
        dgh=QLabel("Developer settings"); dgh.setObjectName("SectionTitle"); dg.addWidget(dgh)
        dgn=QLabel("Advanced local integration controls are hidden by default.")
        dgn.setWordWrap(True); dgn.setStyleSheet(f"color:{theme.MUTED}"); dg.addWidget(dgn)
        enable_dev=QPushButton("Enable Developer Settings"); enable_dev.setObjectName("Secondary"); enable_dev.clicked.connect(self._enable_developer_settings)
        dg.addWidget(enable_dev,0,Qt.AlignLeft); l.addWidget(self.dev_gate)

        self.api_card=Card(); a=QVBoxLayout(self.api_card); a.setContentsMargins(20,18,20,18); a.setSpacing(9)
        title=QLabel("Dashboard API"); title.setObjectName("SectionTitle"); a.addWidget(title)
        self.api_status=QLabel(); self.api_status.setStyleSheet(f"color:{theme.MUTED}"); a.addWidget(self.api_status)
        token_row=QHBoxLayout(); self.token_preview=QLineEdit(); self.token_preview.setReadOnly(True); self.token_preview.setEchoMode(QLineEdit.Password); self.token_preview.setText(api_token)
        copy=QPushButton("Copy token"); copy.setObjectName("Secondary"); copy.clicked.connect(lambda: QApplication.clipboard().setText(api_token))
        token_row.addWidget(self.token_preview,1); token_row.addWidget(copy); a.addLayout(token_row)
        curl=QPushButton("Copy curl example"); curl.setObjectName("Secondary"); curl.clicked.connect(self._copy_curl); a.addWidget(curl,0,Qt.AlignLeft)
        note=QLabel("Read-only API · bearer-token protected · bound to 127.0.0.1 only. No Plaid secret or access token is ever exposed through it.")
        note.setWordWrap(True); note.setStyleSheet(f"color:{theme.MUTED}"); a.addWidget(note)
        disable_dev=QPushButton("Disable Developer Settings"); disable_dev.setObjectName("Secondary"); disable_dev.clicked.connect(self._disable_developer_settings)
        a.addWidget(disable_dev,0,Qt.AlignLeft); self.api_card.hide(); l.addWidget(self.api_card)

        l.addStretch(); self.refresh()

    def _copy_curl(self):
        QApplication.clipboard().setText(f'curl -H "Authorization: Bearer {self.api_token}" {self.api_server.base_url}/api/v1/summary')

    def set_vault_error(self, message: str):
        self._vault_error = message
        self.refresh()

    def _access_action(self):
        if self.vault.unlocked:
            if callable(self.on_logout):
                self.on_logout()
        else:
            if callable(self.on_login):
                self.on_login()

    def _delete_data(self):
        if callable(self.on_delete_data):
            self.on_delete_data()

    def _enable_developer_settings(self):
        answer=QMessageBox.question(
            self,
            "Enable Developer Settings",
            "Developer settings expose advanced local integration controls, including the local Dashboard API token. Enable them for this session?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.dev_gate.hide()
            self.api_card.show()

    def _disable_developer_settings(self):
        self.api_card.hide()
        self.dev_gate.show()

    def _configure_plaid(self):
        try:
            self.plaid.configure(self.client_id.text(),self.secret.text())
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
        unlocked=self.vault.unlocked
        self.configure_btn.setEnabled(unlocked)
        self.client_id.setEnabled(unlocked)
        self.secret.setEnabled(unlocked)
        self.connect_btn.setEnabled(unlocked and self.plaid.configured)
        self.sync_btn.setEnabled(unlocked and self.plaid.connected)

        if self.vault.unlocked:
            access_text = "PrivateMoney is unlocked on this computer."
            self.login_logout_btn.setText("Log out")
            self.login_logout_btn.setEnabled(True)
            self.plaid_privacy.setText("Your Plaid connection can be saved securely on this computer. Bank credentials are still entered only inside Plaid Link.")
        else:
            access_text = "PrivateMoney is locked."
            self.login_logout_btn.setText("Log in")
            self.login_logout_btn.setEnabled(True)
            self.plaid_privacy.setText("Unlock PrivateMoney to save your Plaid connection and financial data.")
        self.delete_data_btn.setEnabled(self.vault.exists)
        if self._vault_error:
            access_text += f"  Last error: {self._vault_error}"
        self.access_status.setText(access_text)


class _CenteredItemDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option,index)
        option.displayAlignment=Qt.AlignCenter


class _CenteredTableItem(QTableWidgetItem):
    def __init__(self, text=""):
        super().__init__(str(text))
        self.setTextAlignment(Qt.AlignCenter)


def style_table(table):
    table.verticalHeader().setVisible(False); table.setShowGrid(False); table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
    table.setItemDelegate(_CenteredItemDelegate(table))


class _NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


def transaction_table(items, compact=False, category_callback=None, categories=None):
    table=QTableWidget(0,5)
    table.setHorizontalHeaderLabels(["Date","Merchant","Category","Account","Amount"])
    style_table(table)
    fill_transaction_table(
        table,
        items,
        category_callback=category_callback,
        categories=categories,
    )
    if compact:
        table.verticalHeader().setDefaultSectionSize(24)
        table.setMinimumHeight(155); table.setMaximumHeight(175)
    return table


def fill_transaction_table(
    table: QTableWidget,
    items,
    category_callback=None,
    categories=None,
    account_labeler=None,
):
    table.clearSpans()
    table.setRowCount(len(items))
    options=list(categories or [])

    for r,t in enumerate(items):
        account_text=account_labeler(t.account) if callable(account_labeler) else t.account
        values=[t.posted.strftime("%b %d"),t.merchant,t.category,account_text,money(t.amount)]
        for c,value in enumerate(values):
            if c == 2 and category_callback is not None:
                combo=_NoWheelComboBox()
                combo.setEditable(True)
                combo.lineEdit().setReadOnly(True)
                combo.lineEdit().setAlignment(Qt.AlignCenter)
                choices=list(options)
                if t.category and t.category not in choices:
                    choices.append(t.category)
                    choices.sort(key=str.casefold)
                combo.addItems(choices)
                combo.setCurrentText(t.category or "Other")
                combo.currentTextChanged.connect(
                    lambda category, tx=t: category_callback(tx,category)
                )
                table.setCellWidget(r,c,combo)
                continue

            item=_CenteredTableItem(value)
            if c==4:
                item.setForeground(
                    QColor(theme.POSITIVE if t.amount>=0 else theme.NEGATIVE)
                )
            if t.pending:
                item.setToolTip("Pending")
            table.setItem(r,c,item)

    hh=table.horizontalHeader()
    for c in range(5):
        hh.setSectionResizeMode(
            c,
            QHeaderView.Stretch if c in (1,2,3) else QHeaderView.ResizeToContents,
        )


def filter_table(table: QTableWidget, query: str):
    q=query.strip().lower()
    for row in range(table.rowCount()):
        parts=[]
        for c in range(table.columnCount()):
            widget=table.cellWidget(row,c)
            if isinstance(widget,QComboBox):
                parts.append(widget.currentText())
            else:
                item=table.item(row,c)
                if item:
                    parts.append(item.text())
        text=" ".join(parts).lower()
        table.setRowHidden(row, q not in text)
