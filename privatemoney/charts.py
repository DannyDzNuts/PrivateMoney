from __future__ import annotations

import math
from datetime import date

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolTip,
    QVBoxLayout, QWidget,
)

from . import theme

PALETTE = [
    theme.VIOLET, theme.CYAN, theme.BLUE, theme.POSITIVE,
    theme.WARNING, "#F97316", "#EC4899",
]


class ChartBase(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(175)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setStyleSheet("background: transparent;")

    def _text(self, painter, x, y, text, color=theme.MUTED, size=10, bold=False):
        painter.setPen(QColor(color))
        font = QFont(self.font())
        font.setPointSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.drawText(QPointF(x, y), str(text))


class LineChart(ChartBase):
    def __init__(self, points, parent=None, *, show_points=True, hover_tooltip=False):
        super().__init__(parent)
        self.points = list(points)
        self.show_points = show_points
        self.hover_tooltip = hover_tooltip
        self._painted_points = []
        self._graph_rect = QRectF()
        self.setMouseTracking(bool(hover_tooltip))

    def set_points(self, points):
        self.points = list(points)
        self.update()

    @staticmethod
    def _display_label(label):
        text = str(label)
        try:
            return date.fromisoformat(text).strftime("%b %d")
        except ValueError:
            return text

    def paintEvent(self, event):
        self._painted_points = []
        if not self.points:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(16, 18, -16, -26)
        values = [value for _, value in self.points]
        low, high = min(values), max(values)
        pad = max((high - low) * .18, abs(high) * .02, 1)
        low -= pad
        high += pad
        graph = QRectF(rect.left() + 12, rect.top() + 8, rect.width() - 24, rect.height() - 30)
        self._graph_rect = graph

        painter.setPen(QPen(QColor(theme.OUTLINE), 1))
        for i in range(4):
            y = graph.top() + graph.height() * i / 3
            painter.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))

        points = []
        if len(self.points) == 1:
            value = self.points[0][1]
            y = graph.bottom() - (value - low) / (high - low) * graph.height()
            points = [QPointF(graph.center().x(), y)]
            guide = QColor(theme.VIOLET)
            guide.setAlpha(90)
            painter.setPen(QPen(guide, 1.2, Qt.DashLine))
            painter.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))
        else:
            denominator = len(self.points) - 1
            for i, (_, value) in enumerate(self.points):
                x = graph.left() + graph.width() * i / denominator
                y = graph.bottom() - (value - low) / (high - low) * graph.height()
                points.append(QPointF(x, y))

            area = QPainterPath()
            area.moveTo(points[0].x(), graph.bottom())
            area.lineTo(points[0])
            for point in points[1:]:
                area.lineTo(point)
            area.lineTo(points[-1].x(), graph.bottom())
            area.closeSubpath()
            fill = QColor(theme.VIOLET)
            fill.setAlpha(28)
            painter.fillPath(area, fill)

            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.setPen(QPen(QColor(theme.VIOLET), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)

        if self.show_points:
            painter.setBrush(QColor(theme.VIOLET))
            painter.setPen(Qt.NoPen)
            for point in points:
                painter.drawEllipse(point, 4.2, 4.2)

        for point, (label, value) in zip(points, self.points):
            self._painted_points.append((point, str(label), float(value)))

        if len(self.points) == 1:
            self._text(painter, graph.center().x() - 20, rect.bottom() - 2,
                       self._display_label(self.points[0][0]), size=9)
            self._text(painter, graph.center().x() - 36, points[0].y() - 12,
                       "$" + f"{self.points[0][1]:,.0f}", theme.IVORY, 10, True)
        else:
            count = len(self.points)
            step = max(1, (count - 1) // 5)
            indexes = set(range(0, count, step))
            indexes.add(count - 1)
            denominator = count - 1
            for i, (label, _) in enumerate(self.points):
                if i not in indexes:
                    continue
                x = graph.left() + graph.width() * i / denominator
                self._text(painter, x - 18, rect.bottom() - 2,
                           self._display_label(label), size=9)

    def mouseMoveEvent(self, event):
        if not self.hover_tooltip or not self._painted_points:
            return super().mouseMoveEvent(event)
        pos = event.position()
        if not self._graph_rect.adjusted(-8, -8, 8, 8).contains(pos):
            QToolTip.hideText()
            return super().mouseMoveEvent(event)

        nearest = min(self._painted_points, key=lambda item: abs(item[0].x() - pos.x()))
        point, label, value = nearest
        if abs(point.x() - pos.x()) <= 42 or len(self._painted_points) == 1:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                self._display_label(label) + "\n$" + f"{value:,.2f}",
                self,
            )
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hover_tooltip:
            QToolTip.hideText()
        super().leaveEvent(event)


class _PieCanvas(ChartBase):
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        total = sum(value for _, value in self.segments) or 1.0
        side = max(90, min(self.height() - 42, self.width() - 42, 190))
        base = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)

        start_deg = 90.0
        explode = max(4.0, min(8.0, side * .035))
        for index, (_, value) in enumerate(self.segments):
            span_deg = -(float(value) / total * 360.0)
            mid_deg = start_deg + span_deg / 2.0
            angle = math.radians(mid_deg)
            dx = explode * math.cos(angle)
            dy = -explode * math.sin(angle)
            pie_rect = base.translated(dx, dy)

            painter.setPen(QPen(QColor(theme.CARD), 2.0))
            painter.setBrush(QColor(PALETTE[index % len(PALETTE)]))
            painter.drawPie(pie_rect, int(start_deg * 16), int(span_deg * 16))
            start_deg += span_deg


class _LegendScrollArea(QScrollArea):
    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class DonutChart(QWidget):
    """Exploded full-slice pie chart with an independently scrollable legend."""

    def __init__(self, segments, parent=None):
        super().__init__(parent)
        self.segments = list(segments)
        self.setMinimumHeight(175)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.canvas = _PieCanvas(self.segments)
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
        total = sum(value for _, value in self.segments) or 1
        if not self.segments:
            empty = QLabel("No spending data")
            empty.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
            self.legend_layout.addWidget(empty)
            self.legend_layout.addStretch()
            return

        for index, (label, value) in enumerate(self.segments):
            row = QFrame()
            row.setStyleSheet("background: transparent; border: 0;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(9)

            swatch = QLabel()
            swatch.setFixedSize(9, 9)
            swatch.setStyleSheet(
                f"background:{PALETTE[index % len(PALETTE)]}; border-radius:2px;"
            )
            row_layout.addWidget(swatch, 0, Qt.AlignTop)

            text = QWidget()
            text.setStyleSheet("background: transparent;")
            text_layout = QVBoxLayout(text)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)

            name = QLabel(str(label))
            name.setWordWrap(True)
            name.setStyleSheet(
                f"color:{theme.IVORY}; font-weight:650; background:transparent;"
            )
            detail = QLabel("$" + f"{value:,.0f}" + "  ·  " + f"{value / total:.0%}")
            detail.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
            text_layout.addWidget(name)
            text_layout.addWidget(detail)
            row_layout.addWidget(text, 1)
            self.legend_layout.addWidget(row)

        self.legend_layout.addStretch(1)


class CashFlowChart(ChartBase):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = list(rows)

    def set_rows(self, rows):
        self.rows = list(rows)
        self.update()

    @staticmethod
    def _bar_label(value):
        if abs(value) >= 1000:
            return "$" + f"{value / 1000:.1f}k"
        return "$" + f"{value:,.0f}"

    def _draw_bar_value(self, painter, rect, value):
        if value <= 0 or rect.height() < 20:
            return
        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            rect.adjusted(1, 2, -1, -2),
            Qt.AlignHCenter | Qt.AlignTop,
            self._bar_label(value),
        )

    def paintEvent(self, event):
        if not self.rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(16, 20, -16, -30)
        top = max(max(income, outflow) for _, income, outflow in self.rows) * 1.12
        count = len(self.rows)
        group = rect.width() / max(count, 1)
        bar_width = min(30, max(18, group * .28))

        painter.setPen(QPen(QColor(theme.OUTLINE), 1))
        for i in range(4):
            y = rect.top() + rect.height() * i / 3
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        for index, (label, income, outflow) in enumerate(self.rows):
            center_x = rect.left() + group * (index + .5)
            income_height = rect.height() * income / top if top else 0
            outflow_height = rect.height() * outflow / top if top else 0

            income_rect = QRectF(
                center_x - bar_width - 3,
                rect.bottom() - income_height,
                bar_width,
                income_height,
            )
            outflow_rect = QRectF(
                center_x + 3,
                rect.bottom() - outflow_height,
                bar_width,
                outflow_height,
            )

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.POSITIVE))
            painter.drawRoundedRect(income_rect, 4, 4)
            self._draw_bar_value(painter, income_rect, income)

            painter.setBrush(QColor(theme.NEGATIVE))
            painter.drawRoundedRect(outflow_rect, 4, 4)
            self._draw_bar_value(painter, outflow_rect, outflow)

            self._text(painter, center_x - 11, self.height() - 9, label, size=9)
