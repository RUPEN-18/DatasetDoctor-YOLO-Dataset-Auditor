from __future__ import annotations
import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QSizePolicy
from .theme import COLORS


class DistributionChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = []
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_values(self, values):
        self.values = list(values)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            p.setPen(QColor('#91a0b1'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Run a scan to see the distribution')
            return
        shown = self.values[:8]
        peak = max((v for _, v in shown), default=1) or 1
        spacing = min(54, (self.height() - 20) / max(1, len(shown)))
        for n, (label, value) in enumerate(shown):
            y = n * spacing + 5
            p.setFont(QFont(self.font().family(), 9))
            p.setPen(QColor('#51657f'))
            shortened = p.fontMetrics().elidedText(str(label), Qt.TextElideMode.ElideRight, max(50, self.width() - 80))
            p.drawText(QRectF(0, y, self.width() - 60, 18), shortened)
            p.setPen(QColor('#243c56'))
            p.drawText(QRectF(self.width() - 65, y, 65, 18), Qt.AlignmentFlag.AlignRight, f'{value:,}')
            width = self.width()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#eef3f7'))
            p.drawRoundedRect(QRectF(0, y + 24, width, 8), 4, 4)
            p.setBrush(QColor(COLORS[n % len(COLORS)]))
            if value:
                p.drawRoundedRect(QRectF(0, y + 24, max(4, width * value / peak), 8), 4, 4)
        if len(self.values) > 8:
            p.setPen(QColor('#77869a'))
            p.drawText(0, self.height() - 2, f'+ {len(self.values) - 8} classes in the full report')


class SplitChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = []
        self.setMinimumHeight(210)

    def set_values(self, values):
        self.values = list(values)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v in self.values)
        size = min(self.height() - 30, self.width() * .48, 185)
        rect = QRectF(8, (self.height() - size) / 2, size, size)
        pen = QPen(QColor('#edf2f6'), 22)
        p.setPen(pen)
        p.drawEllipse(rect.adjusted(14, 14, -14, -14))
        angle = 90 * 16
        for n, (_, value) in enumerate(self.values):
            span = -round(value / total * 360 * 16) if total else 0
            p.setPen(QPen(QColor(COLORS[n % len(COLORS)]), 22))
            p.drawArc(rect.adjusted(14, 14, -14, -14), angle, span)
            angle += span
        p.setPen(QColor('#233a54'))
        p.setFont(QFont(self.font().family(), 23, QFont.Weight.Bold))
        p.drawText(rect.adjusted(0, -5, 0, 0), Qt.AlignmentFlag.AlignCenter, f'{total:,}')
        p.setFont(QFont(self.font().family(), 9))
        p.setPen(QColor('#8694a6'))
        p.drawText(rect.adjusted(0, 49, 0, 0), Qt.AlignmentFlag.AlignCenter, 'IMAGES')
        x = size + 35
        start = max(15, (self.height() - len(self.values) * 36) / 2)
        for n, (label, value) in enumerate(self.values):
            y = start + n * 36
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(COLORS[n % len(COLORS)]))
            p.drawEllipse(QRectF(x, y + 3, 8, 8))
            p.setPen(QColor('#526980'))
            p.drawText(QRectF(x + 19, y - 2, max(60, self.width() - x - 75), 22), str(label).title())
            p.setPen(QColor('#263e58'))
            p.drawText(QRectF(self.width() - 65, y - 2, 65, 22), Qt.AlignmentFlag.AlignRight, f'{value:,}')


class ImageCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.record = None
        self.classes = []
        self.show_boxes = True
        self.error = 'Select an image to inspect its annotations'
        self.setMinimumSize(350, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, path, record, classes):
        from PIL import Image
        from PIL.ImageQt import ImageQt
        from .scanner import MAX_PIXELS
        import warnings
        self.record, self.classes = record, classes
        self.pixmap = QPixmap()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if image.width * image.height > MAX_PIXELS:
                        raise ValueError('Image exceeds the 40 megapixel safety limit.')
                    image.thumbnail((2200, 1600))
                    self.pixmap = QPixmap.fromImage(ImageQt(image.convert('RGBA')))
            self.error = ''
        except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            self.error = 'Unable to preview this image.\n' + str(exc)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#172438'))
        if self.pixmap.isNull():
            p.setPen(QColor('#9cb0c4'))
            p.drawText(self.rect().adjusted(25, 25, -25, -25), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.error)
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        available = self.rect().adjusted(22, 22, -22, -22)
        ratio = min(available.width() / self.pixmap.width(), available.height() / self.pixmap.height())
        w, h = self.pixmap.width() * ratio, self.pixmap.height() * ratio
        left, top = (self.width() - w) / 2, (self.height() - h) / 2
        p.drawPixmap(QRectF(left, top, w, h), self.pixmap, QRectF(self.pixmap.rect()))
        if not self.show_boxes or self.record is None:
            return
        p.setFont(QFont(self.font().family(), 9, QFont.Weight.Bold))
        for a in self.record.annotations:
            x, y, bw, bh = a.box
            rect = QRectF(left + (x - bw / 2) * w, top + (y - bh / 2) * h, bw * w, bh * h)
            color = QColor(COLORS[a.class_id % len(COLORS)])
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 2))
            p.drawRect(rect)
            title = f'{a.class_id}  {self.classes[a.class_id]}'
            textw = min(p.fontMetrics().horizontalAdvance(title) + 12, w)
            tag = QRectF(min(rect.x(), left + w - textw), max(top, rect.y() - 22), textw, 22)
            p.fillRect(tag, color)
            p.setPen(QColor('white'))
            p.drawText(tag.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(textw - 10)))
