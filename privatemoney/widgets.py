from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout
from . import theme


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")


class MetricCard(Card):
    def __init__(self, title: str, value: str, delta: str = "", positive: bool = True, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)
        t = QLabel(title); t.setObjectName("CardTitle")
        self.value_label = QLabel(value); self.value_label.setObjectName("BigNumber")
        layout.addWidget(t); layout.addWidget(self.value_label)
        self.delta_label = QLabel(delta)
        layout.addWidget(self.delta_label)
        self.set_delta(delta, positive)
        layout.addStretch(1)
        self.setMinimumHeight(112)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_delta(self, delta: str, positive: bool = True):
        self.delta_label.setText(delta)
        self.delta_label.setObjectName("DeltaPositive" if positive else "DeltaNegative")
        self.delta_label.style().unpolish(self.delta_label)
        self.delta_label.style().polish(self.delta_label)
        self.delta_label.setVisible(bool(delta))


class BudgetRow(QFrame):
    def __init__(self, category: str, spent: float, limit: float, parent=None):
        super().__init__(parent)
        self.setObjectName("BudgetRow")
        self.setStyleSheet("QFrame#BudgetRow { background: transparent; border: 0; }")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 7, 0, 7); outer.setSpacing(7)
        row = QHBoxLayout(); row.setSpacing(8)
        name = QLabel(category); name.setStyleSheet("font-weight:650")
        amount = QLabel(f"{money(spent)} / {money(limit)}"); amount.setStyleSheet(f"color:{theme.MUTED}")
        row.addWidget(name); row.addStretch(); row.addWidget(amount)
        bar = QProgressBar(); bar.setTextVisible(False); bar.setRange(0, 100)
        pct = 0 if limit <= 0 else min(100, round(spent / limit * 100))
        bar.setValue(pct)
        if spent > limit:
            bar.setStyleSheet(f"QProgressBar::chunk {{ background:{theme.NEGATIVE}; border-radius:5px; }}")
        outer.addLayout(row); outer.addWidget(bar)


class EmptyState(Card):
    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        l=QVBoxLayout(self); l.setContentsMargins(24,24,24,24); l.setSpacing(7)
        a=QLabel(title); a.setObjectName("SectionTitle")
        b=QLabel(detail); b.setWordWrap(True); b.setStyleSheet(f"color:{theme.MUTED}")
        l.addWidget(a); l.addWidget(b); l.addStretch()
