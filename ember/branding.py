"""Ember logo: a flame with a play button cut out of it, in an amber-to-ember gradient, plus wordmark."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap

# Flame outline in a unit square: round base, tip leaning slightly left.
FLAME = [("M", .50, .97), ("C", .25, .97, .12, .79, .14, .58), ("C", .16, .38, .33, .28, .41, .03),
         ("C", .58, .19, .86, .37, .86, .60), ("C", .86, .81, .73, .97, .50, .97)]


def _path(cmds, x, y, s):
    path = QPainterPath()
    for c, *v in cmds:
        pts = [QPointF(x + v[i] * s, y + v[i + 1] * s) for i in range(0, len(v), 2)]
        if c == "M":
            path.moveTo(pts[0])
        else:
            path.cubicTo(*pts)
    path.closeSubpath()
    return path


def _rounded_triangle(pts, r):
    path = QPainterPath()
    for i, p in enumerate(pts):
        prev, nxt = pts[i - 1], pts[(i + 1) % 3]
        a = p + (prev - p) * (r / _dist(prev, p))
        b = p + (nxt - p) * (r / _dist(nxt, p))
        path.moveTo(a) if i == 0 else path.lineTo(a)
        path.quadTo(p, b)
    path.closeSubpath()
    return path


def _dist(a, b):
    d = a - b
    return (d.x() ** 2 + d.y() ** 2) ** 0.5


def paint_mark(p, rect):
    s = min(rect.width(), rect.height())
    x, y = rect.center().x() - s / 2, rect.center().y() - s / 2
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    flame = _path(FLAME, x, y, s)
    cx, cy, t = x + .52 * s, y + .66 * s, .17 * s
    play = _rounded_triangle([QPointF(cx - t * .8, cy - t), QPointF(cx - t * .8, cy + t),
                              QPointF(cx + t * 1.05, cy)], t * .22)
    shape = flame.subtracted(play)
    g = QLinearGradient(0, y, 0, y + s)
    g.setColorAt(0.0, QColor("#ffc04a"))
    g.setColorAt(0.6, QColor("#f36b20"))
    g.setColorAt(1.0, QColor("#d0381b"))
    p.fillPath(shape, g)
    hl = QLinearGradient(x, 0, x + s * .6, 0)  # soft light on the left edge
    hl.setColorAt(0, QColor(255, 255, 255, 55))
    hl.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(shape, hl)
    p.restore()


def mark_pixmap(size, dpr=2.0):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_mark(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def wordmark_pixmap(height=30, family="DM Sans", dpr=2.0, with_mark=True):
    """Flame mark + 'ember' in white."""
    f = QFont(family)
    f.setPixelSize(int(height * 0.78 * dpr))
    f.setWeight(QFont.Weight.Bold)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 96)
    probe = QImage(1, 1, QImage.Format.Format_ARGB32)
    p = QPainter(probe)
    p.setFont(f)
    fm = p.fontMetrics()
    text_w, ascent = fm.horizontalAdvance("ember"), fm.ascent()
    p.end()
    h = int(height * dpr)
    mark = h if with_mark else 0
    gap = int(h * 0.2) if with_mark else 0
    pm = QPixmap(mark + gap + text_w + 4, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if with_mark:
        paint_mark(p, QRectF(0, 0, mark, mark))
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(QPointF(mark + gap, (h + ascent * 0.72) / 2 + h * 0.04), "ember")
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def app_icon_image(size=256):
    """Flame on a warm dark rounded tile (taskbar / exe icon)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(size * .03, size * .03, size * .94, size * .94), size * .22, size * .22)
    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0, QColor("#2b2824"))
    bg.setColorAt(1, QColor("#171513"))
    p.fillPath(tile, bg)
    paint_mark(p, QRectF(size * .16, size * .14, size * .68, size * .68))
    p.end()
    return img
