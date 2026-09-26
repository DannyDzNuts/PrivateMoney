from __future__ import annotations
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
)
from . import theme

PALETTE = [theme.VIOLET, theme.CYAN, theme.BLUE, theme.POSITIVE, theme.WARNING, "#E49BFF"]


class ChartBase(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(175)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setStyleSheet("background: transparent;")

    def _text(self, painter, x, y, text, color=theme.MUTED, size=10, bold=False):
        painter.setPen(QColor(color))
        f = QFont(self.font())
        f.setPointSize(size)
        f.setBold(bold)
        painter.setFont(f)
        painter.drawText(QPointF(x, y), str(text))


class LineChart(ChartBase):
    def __init__(self, points, parent=None):
        super().__init__(parent)
        self.points = list(points)

    def set_points(self, points):
        self.points = list(points)
        self.update()

    def paintEvent(self, event):
        if not self.points:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(16, 18, -16, -26)
        values = [v for _, v in self.points]
        lo, hi = min(values), max(values)
        pad = max((hi - lo) * .18, abs(hi) * .02, 1)
        lo -= pad
        hi += pad
        graph = QRectF(r.left() + 12, r.top() + 8, r.width() - 24, r.height() - 30)
        p.setPen(QPen(QColor(theme.OUTLINE), 1))
        for i in range(4):
            y = graph.top() + graph.height() * i / 3
            p.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))
        pts = []
        n = max(len(self.points) - 1, 1)
        for i, (_, val) in enumerate(self.points):
            x = graph.left() + graph.width() * i / n
            y = graph.bottom() - (val - lo) / (hi - lo) * graph.height()
            pts.append(QPointF(x, y))
        area = QPainterPath()
        area.moveTo(pts[0].x(), graph.bottom())
        area.lineTo(pts[0])
        for pt in pts[1:]:
            area.lineTo(pt)
        area.lineTo(pts[-1].x(), graph.bottom())
        area.closeSubpath()
        fill = QColor(theme.VIOLET)
        fill.setAlpha(28)
        p.fillPath(area, fill)
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.setPen(QPen(QColor(theme.VIOLET), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setBrush(QColor(theme.VIOLET))
        p.setPen(Qt.NoPen)
        for pt in pts:
            p.drawEllipse(pt, 4, 4)
        for i, (label, _) in enumerate(self.points):
            x = graph.left() + graph.width() * i / n
            self._text(p, x - 10, r.bottom() - 2, label, size=9)


class _DonutCanvas(ChartBase):
    def __init__(self, segments, parent=None):
        super().__init__(parent)
        self.segments = list(segments)
        self.setMinimumWidth(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_segments(self, segments):
        self.segments = list(segments)
        self.update()

    def paintEvent(self, event):
        if not self.segments:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        total = sum(v for _, v in self.segments) or 1
        side = max(90, min(self.height() - 36, self.width() - 36, 190))
        circle = QRectF(
            (self.width() - side) / 2,
            (self.height() - side) / 2,
            side,
            side,
        )
        pen_width = max(16, int(side * 0.12))
        start = 90 * 16
        for idx, (_, value) in enumerate(self.segments):
            span = -int(value / total * 360 * 16)
            pen = QPen(QColor(PALETTE[idx % len(PALETTE)]), pen_width)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(
                circle.adjusted(
                    pen_width / 2,
                    pen_width / 2,
                    -pen_width / 2,
                    -pen_width / 2,
                ),
                start,
                span,
            )
            start += span
        cx, cy = circle.center().x(), circle.center().y()
        self._text(p, cx - 34, cy - 2, f"${total:,.0f}", theme.IVORY, 17, True)
        self._text(p, cx - 24, cy + 19, "spent", theme.MUTED, 9)


class _LegendScrollArea(QScrollArea):
    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class DonutChart(QWidget):
    """Donut visualization with an independently scrollable legend."""

    def __init__(self, segments, parent=None):
        super().__init__(parent)
        self.segments = list(segments)
        self.setMinimumHeight(175)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.canvas = _DonutCanvas(self.segments)
        layout.addWidget(self.canvas, 3)

        self.legend_scroll = _LegendScrollArea()
        self.legend_scroll.setObjectName("LegendScroll")
        self.legend_scroll.setFrameShape(QFrame.NoFrame)
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.legend_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.legend_scroll.setMinimumWidth(180)
        self.legend_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: 0; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.legend_scroll.viewport().setStyleSheet("background: transparent;")

        self.legend_host = QWidget()
        self.legend_host.setStyleSheet("background: transparent;")
        self.legend_layout = QVBoxLayout(self.legend_host)
        self.legend_layout.setContentsMargins(4, 4, 6, 4)
        self.legend_layout.setSpacing(10)
        self.legend_scroll.setWidget(self.legend_host)
        layout.addWidget(self.legend_scroll, 2)

        self._rebuild_legend()

    def set_segments(self, segments):
        self.segments = list(segments)
        self.canvas.set_segments(self.segments)
        self._rebuild_legend()

    def _clear_legend(self):
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_legend(self):
        self._clear_legend()
        total = sum(v for _, v in self.segments) or 1
        if not self.segments:
            empty = QLabel("No spending data")
            empty.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
            self.legend_layout.addWidget(empty)
            self.legend_layout.addStretch()
            return

        for idx, (label, value) in enumerate(self.segments):
            row = QFrame()
            row.setStyleSheet("background: transparent; border: 0;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(9)

            swatch = QLabel()
            swatch.setFixedSize(9, 9)
            swatch.setStyleSheet(
                f"background:{PALETTE[idx % len(PALETTE)]}; border-radius:4px;"
            )
            rl.addWidget(swatch, 0, Qt.AlignTop)

            text = QWidget()
            text.setStyleSheet("background: transparent;")
            tl = QVBoxLayout(text)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(2)

            name = QLabel(str(label))
            name.setWordWrap(True)
            name.setStyleSheet(
                f"color:{theme.IVORY}; font-weight:650; background:transparent;"
            )
            detail = QLabel(f"${value:,.0f}  ·  {value / total:.0%}")
            detail.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
            tl.addWidget(name)
            tl.addWidget(detail)
            rl.addWidget(text, 1)
            self.legend_layout.addWidget(row)

        self.legend_layout.addStretch(1)


class CashFlowChart(ChartBase):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = list(rows)

    def set_rows(self, rows):
        self.rows = list(rows)
        self.update()

    def paintEvent(self, event):
        if not self.rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(16, 20, -16, -30)
        top = max(max(inc, out) for _, inc, out in self.rows) * 1.12
        n = len(self.rows)
        group = r.width() / max(n, 1)
        bw = min(18, group * 0.25)
        p.setPen(QPen(QColor(theme.OUTLINE), 1))
        for i in range(4):
            y = r.top() + r.height() * i / 3
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        for i, (label, inc, out) in enumerate(self.rows):
            cx = r.left() + group * (i + .5)
            h1 = r.height() * inc / top if top else 0
            h2 = r.height() * out / top if top else 0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.POSITIVE))
            p.drawRoundedRect(QRectF(cx - bw - 2, r.bottom() - h1, bw, h1), 4, 4)
            p.setBrush(QColor(theme.VIOLET))
            p.drawRoundedRect(QRectF(cx + 2, r.bottom() - h2, bw, h2), 4, 4)
            self._text(p, cx - 11, self.height() - 9, label, size=9)
