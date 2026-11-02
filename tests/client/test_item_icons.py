"""Vignettes des objets : toujours carrées, proportions de l'image conservées."""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage, QPixmap

from syncron_client.ui.item_icons import fit_square


def test_wide_and_tall_images_are_centered_in_a_square(qapp):
    for width, height in ((96, 32), (24, 64)):
        source = QImage(width, height, QImage.Format.Format_ARGB32)
        source.fill(QColor("#c0392b"))
        square = fit_square(QPixmap.fromImage(source), 32).toImage()
        assert square.width() == square.height()
        side = square.width()
        middle = square.pixelColor(side // 2, side // 2)
        corner = square.pixelColor(0, 0)
        assert middle.name() == "#c0392b" and corner.alpha() == 0
