"""Ember logo: a rounded play triangle in an amber-to-ember gradient on a dark tile, plus wordmark."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap,
                           QRadialGradient)

AMBER = QColor("#ffc24b")
EMBER = QColor("#ee5a24")


def _flame_gradient(top, bottom):
    g = QLinearGradient(0, top, 0, bottom)
    g.setColorAt(0.0, AMBER)
    g.setColorAt(1.0, EMBER)
    return g


def _play_path(cx, cy, size):
    """Equilateral-ish play triangle with rounded corners, optically centred."""
    r = size * 0.11  # corner radius
    pts = [QPointF(cx - size * 0.36, cy - size * 0.46), QPointF(cx - size * 0.36, cy + size * 0.46),
           QPointF(cx + size * 0.46, cy)]
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


def paint_mark(p, rect, tile=True):
    """Draw the logo mark inside rect."""
    s = min(rect.width(), rect.height())
    x, y = rect.center().x() - s / 2, rect.center().y() - s / 2
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if tile:
        tile_path = QPainterPath()
        tile_path.addRoundedRect(QRectF(x, y, s, s), s * 0.24, s * 0.24)
        bg = QLinearGradient(0, y, 0, y + s)
        bg.setColorAt(0, QColor("#24262b"))
        bg.setColorAt(1, QColor("#121316"))
        p.fillPath(tile_path, bg)
        glow = QRadialGradient(QPointF(x + s * 0.5, y + s * 0.62), s * 0.55)
        glow.setColorAt(0, QColor(238, 90, 36, 90))
        glow.setColorAt(1, QColor(238, 90, 36, 0))
        p.fillPath(tile_path, glow)
        inner = s * 0.54
    else:
        inner = s * 0.92
    path = _play_path(x + s * 0.53, y + s * 0.5, inner)
    p.fillPath(path, _flame_gradient(y + s * 0.5 - inner * 0.46, y + s * 0.5 + inner * 0.46))
    # small highlight along the top edge, like light catching a coal
    hl = QLinearGradient(0, y + s * 0.5 - inner * 0.46, 0, y + s * 0.5)
    hl.setColorAt(0, QColor(255, 255, 255, 70))
    hl.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(path, hl)
    p.restore()


def mark_pixmap(size, tile=True, dpr=2.0):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_mark(p, QRectF(0, 0, size * dpr, size * dpr), tile)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def wordmark_pixmap(height=30, family="Figtree", dpr=2.0, with_mark=True):
    """Mark + 'ember' set in a heavy weight with the same gradient."""
    f = QFont(family)
    f.setPixelSize(int(height * 0.86 * dpr))
    f.setWeight(QFont.Weight.ExtraBold)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
    probe = QImage(1, 1, QImage.Format.Format_ARGB32)
    p = QPainter(probe)
    p.setFont(f)
    text_w = p.fontMetrics().horizontalAdvance("ember")
    ascent = p.fontMetrics().ascent()
    p.end()
    mark = int(height * dpr) if with_mark else 0
    gap = int(height * 0.3 * dpr) if with_mark else 0
    w, h = mark + gap + text_w + 4, int(height * dpr)
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if with_mark:
        paint_mark(p, QRectF(0, 0, mark, mark))
    path = QPainterPath()
    path.addText(QPointF(mark + gap, (h + ascent * 0.72) / 2), f, "ember")
    p.fillPath(path, _flame_gradient(h * 0.15, h * 0.9))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm
