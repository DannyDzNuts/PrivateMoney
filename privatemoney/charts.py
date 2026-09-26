from __future__ import annotations
from math import ceil
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from . import theme

PALETTE = [theme.VIOLET, theme.CYAN, theme.BLUE, theme.POSITIVE, theme.WARNING, "#E49BFF"]

class ChartBase(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

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
        lo -= pad; hi += pad
        graph = QRectF(r.left()+12, r.top()+8, r.width()-24, r.height()-30)
        p.setPen(QPen(QColor(theme.OUTLINE), 1))
        for i in range(4):
            y = graph.top() + graph.height() * i / 3
            p.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))
        pts = []
        n = max(len(self.points)-1, 1)
        for i, (_, val) in enumerate(self.points):
            x = graph.left() + graph.width() * i / n
            y = graph.bottom() - (val-lo)/(hi-lo)*graph.height()
            pts.append(QPointF(x,y))
        area = QPainterPath()
        area.moveTo(pts[0].x(), graph.bottom())
        area.lineTo(pts[0])
        for pt in pts[1:]: area.lineTo(pt)
        area.lineTo(pts[-1].x(), graph.bottom())
        area.closeSubpath()
        fill = QColor(theme.VIOLET); fill.setAlpha(28)
        p.fillPath(area, fill)
        path = QPainterPath(pts[0])
        for pt in pts[1:]: path.lineTo(pt)
        p.setPen(QPen(QColor(theme.VIOLET), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setBrush(QColor(theme.VIOLET)); p.setPen(Qt.NoPen)
        for pt in pts: p.drawEllipse(pt, 4, 4)
        for i, (label, _) in enumerate(self.points):
            x = graph.left() + graph.width() * i / n
            self._text(p, x-10, r.bottom()-2, label, size=9)

class DonutChart(ChartBase):
    def __init__(self, segments, parent=None):
        super().__init__(parent)
        self.segments = list(segments)

    def set_segments(self, segments):
        self.segments = list(segments)
        self.update()

    def paintEvent(self, event):
        if not self.segments:
            return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        total = sum(v for _, v in self.segments) or 1
        side = min(self.height()-34, int(self.width()*0.46), 190)
        circle = QRectF(18, (self.height()-side)/2, side, side)
        pen_width = max(16, int(side*0.12))
        start = 90*16
        for idx, (_, value) in enumerate(self.segments):
            span = -int(value/total*360*16)
            pen = QPen(QColor(PALETTE[idx % len(PALETTE)]), pen_width)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawArc(circle.adjusted(pen_width/2, pen_width/2, -pen_width/2, -pen_width/2), start, span)
            start += span
        cx, cy = circle.center().x(), circle.center().y()
        self._text(p, cx-32, cy-2, f"${total:,.0f}", theme.IVORY, 17, True)
        self._text(p, cx-23, cy+19, "spent", theme.MUTED, 9)
        x = circle.right()+28; y = max(30, circle.top()+10)
        for idx, (label, value) in enumerate(self.segments):
            p.setPen(Qt.NoPen); p.setBrush(QColor(PALETTE[idx % len(PALETTE)]))
            p.drawEllipse(QPointF(x, y-4), 4, 4)
            self._text(p, x+12, y, label, theme.IVORY, 10, True)
            self._text(p, x+12, y+17, f"${value:,.0f}  ·  {value/total:.0%}", theme.MUTED, 9)
            y += 38

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
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r=self.rect().adjusted(16,20,-16,-30)
        top=max(max(inc,out) for _,inc,out in self.rows)*1.12
        n=len(self.rows); group=r.width()/max(n,1); bw=min(18, group*0.25)
        p.setPen(QPen(QColor(theme.OUTLINE),1))
        for i in range(4):
            y=r.top()+r.height()*i/3
            p.drawLine(QPointF(r.left(),y),QPointF(r.right(),y))
        for i,(label,inc,out) in enumerate(self.rows):
            cx=r.left()+group*(i+.5)
            h1=r.height()*inc/top; h2=r.height()*out/top
            p.setPen(Qt.NoPen); p.setBrush(QColor(theme.POSITIVE))
            p.drawRoundedRect(QRectF(cx-bw-2,r.bottom()-h1,bw,h1),4,4)
            p.setBrush(QColor(theme.VIOLET))
            p.drawRoundedRect(QRectF(cx+2,r.bottom()-h2,bw,h2),4,4)
            self._text(p,cx-11,self.height()-9,label,size=9)
