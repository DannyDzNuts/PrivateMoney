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
    def __init__(self, points, parent=None, *, show_points=True, hover_tooltip=False, show_trend=False):
        super().__init__(parent)
        self.points = list(points)
        self.show_points = show_points
        self.hover_tooltip = hover_tooltip
        self.show_trend = show_trend
        self._painted_points = []
        self._graph_rect = QRectF()
        self.setMouseTracking(bool(hover_tooltip))

    def set_points(self, points):
        self.points = list(points)
        self.update()

    @staticmethod
    def _trend_fit(points):
        if len(points) < 2:
            return None
        values=[float(value) for _,value in points]
        count=len(values)
        x_mean=(count-1)/2.0
        y_mean=sum(values)/count
        denominator=sum((index-x_mean)**2 for index in range(count))
        if denominator <= 0:
            return None
        slope=sum((index-x_mean)*(value-y_mean) for index,value in enumerate(values))/denominator
        intercept=y_mean-slope*x_mean
        return intercept, intercept+slope*(count-1), slope

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
        trend=self._trend_fit(self.points) if self.show_trend else None
        scale_values=list(values)
        if trend is not None:
            scale_values.extend((trend[0],trend[1]))
        low, high = min(scale_values), max(scale_values)
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

            if trend is not None:
                trend_start,trend_end,slope=trend
                start_y=graph.bottom()-(trend_start-low)/(high-low)*graph.height()
                end_y=graph.bottom()-(trend_end-low)/(high-low)*graph.height()
                trend_color=theme.POSITIVE if slope >= 0 else theme.NEGATIVE
                painter.setPen(QPen(QColor(trend_color), 2.0, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawLine(QPointF(graph.left(),start_y),QPointF(graph.right(),end_y))

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
        self.setMinimumWidth(360)
        self.setMinimumHeight(245)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_segments(self, segments):
        self.segments = list(segments)
        self.update()

    @staticmethod
    def _distribute_labels(rows, top, bottom, gap=19.0):
        rows.sort(key=lambda item: item["desired_y"])
        if not rows:
            return

        cursor = top
        for row in rows:
            row["label_y"] = max(float(row["desired_y"]), cursor)
            cursor = row["label_y"] + gap

        overflow = rows[-1]["label_y"] - bottom
        if overflow > 0:
            for row in rows:
                row["label_y"] -= overflow

        cursor = bottom
        for row in reversed(rows):
            row["label_y"] = min(row["label_y"], cursor)
            cursor = row["label_y"] - gap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.segments:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, "No spending data")
            return

        total = sum(max(0.0, float(value)) for _, value in self.segments) or 1.0
        side = max(
            110.0,
            min(float(self.height() - 42), float(self.width()) * .48, 220.0),
        )
        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        base = QRectF(
            center_x - side / 2.0,
            center_y - side / 2.0,
            side,
            side,
        )
        radius = side / 2.0

        start_deg = 90.0
        geometry = []
        percent_boxes = []
        for index, (label, value) in enumerate(self.segments):
            value = max(0.0, float(value))
            fraction = value / total
            span_deg = -(fraction * 360.0)
            mid_deg = start_deg + span_deg / 2.0
            angle = math.radians(mid_deg)

            # Larger slices sit visibly farther from the center.
            explode = 4.0 + 34.0 * (fraction ** .75)
            dx = explode * math.cos(angle)
            dy = -explode * math.sin(angle)
            pie_rect = base.translated(dx, dy)

            painter.setPen(QPen(QColor(theme.CARD), 2.0))
            painter.setBrush(QColor(PALETTE[index % len(PALETTE)]))
            painter.drawPie(pie_rect, int(start_deg * 16), int(span_deg * 16))

            percent_rect = None
            for radius_factor in (.56, .72, .40, .84):
                percent_radius = radius * radius_factor
                percent_x = center_x + dx + percent_radius * math.cos(angle)
                percent_y = center_y + dy - percent_radius * math.sin(angle)
                candidate = QRectF(percent_x - 24, percent_y - 9, 48, 18)
                if not any(candidate.adjusted(-2,-1,2,1).intersects(other) for other in percent_boxes):
                    percent_rect = candidate
                    break
            if percent_rect is None:
                percent_rect = candidate

            percent_boxes.append(percent_rect)
            percent_font = QFont(self.font())
            percent_font.setPointSize(9 if fraction >= .08 else 7)
            percent_font.setBold(True)
            painter.setFont(percent_font)
            painter.setPen(QColor(theme.IVORY))
            painter.drawText(percent_rect, Qt.AlignCenter, f"{fraction:.0%}")

            anchor_x = center_x + dx + radius * .94 * math.cos(angle)
            anchor_y = center_y + dy - radius * .94 * math.sin(angle)
            elbow_x = center_x + dx + (radius + 18.0) * math.cos(angle)
            desired_y = center_y + dy - (radius + 28.0) * math.sin(angle)
            geometry.append({
                "label": str(label),
                "right": math.cos(angle) >= 0,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
                "elbow_x": elbow_x,
                "desired_y": desired_y,
            })
            start_deg += span_deg

        left = [row for row in geometry if not row["right"]]
        right = [row for row in geometry if row["right"]]
        self._distribute_labels(left, 14.0, self.height() - 14.0)
        self._distribute_labels(right, 14.0, self.height() - 14.0)

        leader_pen = QPen(QColor(theme.MUTED), 1.2)
        label_font = QFont(self.font())
        label_font.setPointSize(9)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(leader_pen)

        for row in geometry:
            y = row["label_y"]
            painter.drawLine(
                QPointF(row["anchor_x"], row["anchor_y"]),
                QPointF(row["elbow_x"], y),
            )

            if row["right"]:
                line_end = min(self.width() - 86.0, max(row["elbow_x"] + 10.0, center_x + radius + 34.0))
                painter.drawLine(QPointF(row["elbow_x"], y), QPointF(line_end, y))
                text_rect = QRectF(line_end + 6.0, y - 10.0, self.width() - line_end - 12.0, 20.0)
                flags = Qt.AlignLeft | Qt.AlignVCenter
            else:
                line_end = max(86.0, min(row["elbow_x"] - 10.0, center_x - radius - 34.0))
                painter.drawLine(QPointF(row["elbow_x"], y), QPointF(line_end, y))
                text_rect = QRectF(6.0, y - 10.0, line_end - 12.0, 20.0)
                flags = Qt.AlignRight | Qt.AlignVCenter

            painter.setPen(QColor(theme.IVORY))
            painter.drawText(text_rect, flags, row["label"])
            painter.setPen(leader_pen)


class DonutChart(QWidget):
    """Exploded full-slice pie chart with in-slice percentages and leader labels."""

    def __init__(self, segments, parent=None):
        super().__init__(parent)
        self.segments = list(segments)
        self.setMinimumHeight(245)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = _PieCanvas(self.segments)
        layout.addWidget(self.canvas, 1)

    def set_segments(self, segments):
        self.segments = list(segments)
        self.canvas.set_segments(self.segments)


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
