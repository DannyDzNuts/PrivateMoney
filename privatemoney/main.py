from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
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
    RecurringPage,
    SettingsPage,
    TransactionsPage,
)
from .plaid import PlaidBridge
from .state import FinanceState
from .storage import VaultManager
from .theme import APP_QSS, MUTED


def app_icon() -> QIcon:
    return QIcon(str(Path(__file__).resolve().parent / "assets" / "privatemoney.svg"))


class PasswordDialog(QDialog):
    """Small product-facing password dialog using PrivateMoney's normal theme."""

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.forgot_requested = False
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
        self.password.installEventFilter(self)
        layout.addWidget(self.password)

        self.confirm = None
        if mode == "create":
            self.confirm = QLineEdit()
            self.confirm.setEchoMode(QLineEdit.Password)
            self.confirm.setPlaceholderText("Confirm password")
            self.confirm.installEventFilter(self)
            layout.addWidget(self.confirm)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#FF8E9A;")
        self.error.hide()
        layout.addWidget(self.error)

        buttons = QHBoxLayout()
        if mode == "unlock":
            forgot = QPushButton("FORGOT PASSWORD")
            forgot.setObjectName("Danger")
            forgot.setMinimumWidth(170)
            forgot.setMinimumHeight(38)
            forgot.setAutoDefault(False)
            forgot.setDefault(False)
            forgot.clicked.connect(self._forgot_password)
            buttons.addWidget(forgot)
        buttons.addStretch()

        cancel = QPushButton("Exit" if mode == "create" else "Cancel")
        cancel.setObjectName("Secondary")
        cancel.setAutoDefault(False)
        cancel.setDefault(False)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        submit = QPushButton("Create password" if mode == "create" else "Unlock")
        submit.setObjectName("Primary")
        submit.setAutoDefault(False)
        submit.setDefault(False)
        submit.clicked.connect(self._submit)
        buttons.addWidget(submit)
        layout.addLayout(buttons)

        QTimer.singleShot(0, self.password.setFocus)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if obj is self.password and self.mode == "create":
                self._focus_confirmation()
            else:
                self._submit()
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.mode == "create" and self.focusWidget() is self.password:
                self._focus_confirmation()
            else:
                self._submit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _focus_confirmation(self):
        if self.confirm is not None:
            self.confirm.setFocus()
            self.confirm.selectAll()

    def _forgot_password(self):
        self.forgot_requested = True
        self.reject()

    def _submit(self):
        value = self.password.text()
        if self.mode == "create":
            if len(value) < 10:
                self._show_error("Use at least 10 characters.", self.password)
                return
            confirmation = self.confirm.text() if self.confirm is not None else ""
            if not confirmation:
                self._show_error("Enter the password again to confirm it.", self.confirm)
                return
            if value != confirmation:
                self._show_error("The passwords do not match.", self.confirm)
                return
        elif not value:
            self._show_error("Enter your password.", self.password)
            return
        self.error.hide()
        self.accept()

    def _show_error(self, message: str, field=None):
        self.error.setText(message)
        self.error.show()
        target = field or self.password
        if target is not None:
            target.selectAll()
            target.setFocus()

    @property
    def value(self) -> str:
        return self.password.text()


class DestructiveConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setObjectName("PasswordDialog")
        self.setMinimumWidth(540)
        self.setWindowTitle(title)

        layout=QVBoxLayout(self); layout.setContentsMargins(24,24,24,22); layout.setSpacing(12)
        heading=QLabel(title); heading.setObjectName("SectionTitle"); layout.addWidget(heading)
        body=QLabel(message); body.setWordWrap(True); body.setStyleSheet(f"color:{MUTED};"); layout.addWidget(body)
        warning=QLabel("This cannot be undone."); warning.setStyleSheet("color:#FF8E9A;font-weight:700;"); layout.addWidget(warning)

        buttons=QHBoxLayout(); buttons.addStretch()
        cancel=QPushButton("Cancel"); cancel.setObjectName("Secondary"); cancel.setMinimumWidth(100); cancel.setMinimumHeight(38); cancel.clicked.connect(self.reject); buttons.addWidget(cancel)
        delete=QPushButton("DELETE DATA"); delete.setObjectName("Danger"); delete.setMinimumWidth(145); delete.setMinimumHeight(38); delete.clicked.connect(self.accept); buttons.addWidget(delete)
        layout.addLayout(buttons)


class VaultToggleButton(QPushButton):
    """Minimal vector lock icon matching the Midnight Violet UI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._unlocked=False
        self.setObjectName("VaultToggle")
        self.setFixedSize(38,38)
        self.setText("")

    def set_unlocked(self, unlocked: bool):
        unlocked=bool(unlocked)
        if self._unlocked != unlocked:
            self._unlocked=unlocked
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen=QPen(QColor("#D8D3DF"),1.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Clean rectangular body; no keyhole or decorative details.
        painter.drawRoundedRect(QRectF(11.5,17.0,15.0,11.0),1.8,1.8)

        path=QPainterPath()
        if self._unlocked:
            # One side lifted, but still uses the same simple geometry.
            path.moveTo(14.5,17.0)
            path.lineTo(14.5,13.2)
            path.cubicTo(14.5,9.9,16.8,8.0,19.7,8.0)
            path.cubicTo(22.0,8.0,23.8,9.2,24.6,11.2)
        else:
            path.moveTo(14.5,17.0)
            path.lineTo(14.5,13.0)
            path.cubicTo(14.5,9.8,16.8,8.0,19.0,8.0)
            path.cubicTo(21.2,8.0,23.5,9.8,23.5,13.0)
            path.lineTo(23.5,17.0)
        painter.drawPath(path)


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
        self.setWindowIcon(app_icon())
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
            BudgetsPage(self.state),
            RecurringPage(self.state),
            TransactionsPage(self.state, self.vault),
            SettingsPage(
                self.state,
                self.api,
                self.plaid,
                self.api_token,
                self.vault,
                on_logout=self.lock_vault,
                on_login=self._prompt_unlock,
                on_delete_data=self.request_delete_data,
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

        if os.environ.get("PRIVATE_MONEY_TESTING") != "1":
            if self.vault.exists:
                QTimer.singleShot(0, self._prompt_unlock)
            else:
                QTimer.singleShot(0, self._prompt_create_password)

    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(54)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.addStretch()

        self.lock_button = VaultToggleButton()
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
            ("Budgets & Goals", "◫"),
            ("Recurring", "↻"),
            ("Transactions", "⌗"),
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
            if dialog.forgot_requested:
                self.request_delete_data(forgot_password=True)
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

    def request_delete_data(self, forgot_password: bool = False):
        if not self.vault.exists:
            return False

        if forgot_password:
            title="Forgot password?"
            message=(
                "PrivateMoney passwords cannot be recovered or reset. "
                "To use PrivateMoney again, all existing data on this computer must be deleted."
            )
        else:
            title="Delete all data?"
            message=(
                "This permanently deletes your accounts, transactions, saved import defaults, "
                "Plaid connection data, and password from this computer. PrivateMoney will start fresh."
            )

        confirm=DestructiveConfirmDialog(title,message,self)
        if confirm.exec() != QDialog.Accepted:
            return False

        try:
            self.vault.destroy()
        except Exception as exc:
            QMessageBox.warning(self,"Delete data",str(exc))
            return False

        self.plaid.clear_sensitive_session()
        self.state.clear_runtime()
        self._last_version=-1
        self._refresh()
        QTimer.singleShot(0,self._prompt_create_password)
        return True

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
        self.lock_button.set_unlocked(unlocked)
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
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
