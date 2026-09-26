from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
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
        self.value_label = QLabel(value); self.value_label.setObjectName("BigNumber"); self.value_label.setMinimumHeight(36)
        layout.addWidget(t); layout.addWidget(self.value_label)
        self.delta_label = QLabel(delta)
        layout.addWidget(self.delta_label)
        self.set_delta(delta, positive)
        layout.addStretch(1)
        self.setMinimumHeight(116)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_delta(self, delta: str, positive: bool = True):
        self.delta_label.setText(delta)
        self.delta_label.setObjectName("DeltaPositive" if positive else "DeltaNegative")
        self.delta_label.style().unpolish(self.delta_label)
        self.delta_label.style().polish(self.delta_label)
        self.delta_label.setVisible(bool(delta))


class BudgetRow(QFrame):
    def __init__(self, category: str, spent: float, limit: float, edit_callback=None, parent=None):
        super().__init__(parent)
        self.setObjectName("BudgetRow")
        self.setStyleSheet("QFrame#BudgetRow { background: transparent; border: 0; }")
        row=QHBoxLayout(self)
        row.setContentsMargins(0,7,0,7)
        row.setSpacing(12)

        name=QLabel(category)
        name.setStyleSheet("font-weight:650")
        name.setMinimumWidth(130)

        bar=QProgressBar()
        bar.setTextVisible(False)
        bar.setRange(0,100)
        bar.setFixedWidth(280)
        bar.setFixedHeight(12)
        pct=0 if limit <= 0 else min(100,round(spent/limit*100))
        bar.setValue(pct)
        if spent > limit:
            bar.setStyleSheet(f"QProgressBar::chunk {{ background:{theme.NEGATIVE}; border-radius:5px; }}")

        amount=QLabel(f"{money(spent)} / {money(limit)}")
        amount.setStyleSheet(f"color:{theme.MUTED}")
        amount.setAlignment(Qt.AlignCenter)
        amount.setFixedWidth(165)

        row.addWidget(name,1)
        row.addWidget(bar)
        row.addWidget(amount)
        if callable(edit_callback):
            edit=QPushButton("Edit")
            edit.setObjectName("Secondary")
            edit.setFixedWidth(72)
            edit.clicked.connect(lambda checked=False:edit_callback())
            row.addWidget(edit)


class EmptyState(Card):
    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        l=QVBoxLayout(self); l.setContentsMargins(24,24,24,24); l.setSpacing(7)
        a=QLabel(title); a.setObjectName("SectionTitle")
        b=QLabel(detail); b.setWordWrap(True); b.setStyleSheet(f"color:{theme.MUTED}")
        l.addWidget(a); l.addWidget(b); l.addStretch()
