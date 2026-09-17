"""Drop zones: the Main page folder drop (OS folders) and the level-specific zones on the results pages."""
from __future__ import annotations

import os
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..model import Node, Session
from ..theme import Badge, DashedDropFrame, button, hbox, label, level_colors, vbox
from .folder_tree import MIME, mime_node


class FolderDropZone(DashedDropFrame):
    """Main page: accepts folders dropped from Finder / Explorer, or the Browse button."""

    dropped = Signal(list)  # list of folder paths

    def __init__(self, on_browse: Callable[[], None]):
        super().__init__()
        self.setMinimumSize(720, 380)
        lay = vbox(self, (32, 32, 32, 32), 16)
        lay.addStretch(1)
        lay.addWidget(_svg_label(), 0, Qt.AlignHCenter)
        t = label("Drop data folders here", h1=True)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        o = label("or", muted=True)
        o.setStyleSheet("font-size: 15px; color: #4a5566;")
        o.setAlignment(Qt.AlignCenter)
        lay.addWidget(o)
        b = button("Browse for folder…", "primary", on_browse)
        lay.addWidget(b, 0, Qt.AlignHCenter)
        hint = QLabel("You can add more than one folder. Each subfolder level becomes a label you name on the next screen.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setFixedWidth(480)
        hint.setMinimumHeight(48)
        hint.setStyleSheet("font-size: 14px; color: #4a5566;")
        lay.addWidget(hint, 0, Qt.AlignHCenter)
        lay.addStretch(1)

    def dragEnterEvent(self, ev: QDragEnterEvent) -> None:
        if ev.mimeData().hasUrls() and any(os.path.isdir(u.toLocalFile()) for u in ev.mimeData().urls()):
            self.set_active(True)
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev) -> None:
        self.set_active(False)

    def dropEvent(self, ev: QDropEvent) -> None:
        self.set_active(False)
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if os.path.isdir(u.toLocalFile())]
        if paths:
            ev.acceptProposedAction()
            self.dropped.emit(paths)


def _svg_label() -> QLabel:
    """Folder-with-upload-arrow icon drawn with QPainter (crisp at any scale)."""
    from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QPainterPath
    from PySide6.QtCore import QPointF, QRectF
    size, scale = 56, 2
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#2c64b0"), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    k = size / 24.0
    path = QPainterPath()
    path.moveTo(3 * k, 9 * k)
    path.arcTo(QRectF(3 * k, 5 * k, 4 * k, 4 * k), 180, -90)
    path.lineTo(9 * k, 5 * k)
    path.lineTo(11 * k, 7 * k)
    path.lineTo(19 * k, 7 * k)
    path.arcTo(QRectF(17 * k, 7 * k, 4 * k, 4 * k), 90, -90)
    path.lineTo(21 * k, 17 * k)
    path.arcTo(QRectF(17 * k, 15 * k, 4 * k, 4 * k), 0, -90)
    path.lineTo(5 * k, 19 * k)
    path.arcTo(QRectF(3 * k, 15 * k, 4 * k, 4 * k), 270, -90)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(12 * k, 10.5 * k), QPointF(12 * k, 16.5 * k))
    p.drawLine(QPointF(9 * k, 13.5 * k), QPointF(12 * k, 10.5 * k))
    p.drawLine(QPointF(15 * k, 13.5 * k), QPointF(12 * k, 10.5 * k))
    p.end()
    lab = QLabel()
    lab.setPixmap(pm)
    lab.setFixedSize(size, size)
    return lab


class LevelDropZone(DashedDropFrame):
    """Accepts folder nodes of one level from the FolderTree (and lists what was dropped when ``multi``)."""

    changed = Signal()

    def __init__(self, session: Session, level_getter: Callable[[], int], title_fmt: str, hint_fmt: str, multi: bool = False):
        super().__init__()
        self.session = session
        self.level_getter = level_getter
        self.title_fmt = title_fmt
        self.hint_fmt = hint_fmt
        self.multi = multi
        self.nodes: List[Node] = []
        self.setMinimumHeight(140)
        self.lay = vbox(self, (20, 16, 20, 16), 8)
        self.lay.addStretch(1)
        self.title_row = QWidget()
        self.title_lay = hbox(self.title_row, spacing=8)
        self.title_lay.addStretch(1)
        self.title_lay.addStretch(1)
        self.lay.addWidget(self.title_row)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet("font-size: 14px; color: #4a5566;")
        self.lay.addWidget(self.hint)
        self.chips = QWidget()
        self.chips_lay = QHBoxLayout(self.chips)
        self.chips_lay.setContentsMargins(0, 8, 0, 0)
        self.chips_lay.setSpacing(8)
        self.chips_lay.addStretch(1)
        self.lay.addWidget(self.chips)
        self.lay.addStretch(1)
        self.refresh_text()

    @property
    def level(self) -> int:
        return self.level_getter()

    def refresh_text(self) -> None:
        lvl = self.level
        s = self.session
        # title: "Drag a <Level N> folder here"
        while self.title_lay.count():
            it = self.title_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.title_lay.addStretch(1)
        parts = self.title_fmt.split("{level}")
        pre = QLabel(parts[0].strip())
        pre.setProperty("h2", True)
        pre.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.title_lay.addWidget(pre)
        if len(parts) > 1:
            self.title_lay.addWidget(Badge(s.level_name(lvl) if s.level_names else f"Level {lvl}", level=max(lvl, 1), size=16, weight=500))
        if len(parts) > 1 and parts[1].strip():
            post = QLabel(parts[1].strip())
            post.setStyleSheet("font-size: 20px; font-weight: 600;")
            self.title_lay.addWidget(post)
        self.title_lay.addStretch(1)
        below = s.level_name(lvl + 1) if lvl + 1 <= s.n_levels else "Replicate"
        bg, fg = level_colors(max(lvl + 1, 1))
        self.hint.setText(self.hint_fmt.format(level=f'<span style="font-weight:600; color:{fg};">{below}</span>') if "{level}" in self.hint_fmt else self.hint_fmt)
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        while self.chips_lay.count():
            it = self.chips_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for n in self.nodes:
            chip = QWidget()
            h = hbox(chip, spacing=4)
            h.addWidget(Badge(" › ".join(n.labels), level=n.level))
            x = button("×", "tiny", lambda _=False, node=n: self.remove(node))
            h.addWidget(x)
            self.chips_lay.addWidget(chip)
        self.chips_lay.addStretch(1)
        self.chips.setVisible(bool(self.nodes))

    def set_nodes(self, nodes: List[Node]) -> None:
        self.nodes = list(nodes)
        self._refresh_chips()
        self.changed.emit()

    def remove(self, node: Node) -> None:
        self.nodes = [n for n in self.nodes if n is not node]
        self._refresh_chips()
        self.changed.emit()

    def clear(self) -> None:
        self.nodes = []
        self._refresh_chips()

    # ---- drag & drop -------------------------------------------------------------
    def dragEnterEvent(self, ev: QDragEnterEvent) -> None:
        node = mime_node(ev.mimeData(), self.session)
        if node is not None and not node.is_file and node.level == self.level:
            self.set_active(True)
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev) -> None:
        self.set_active(False)

    def dropEvent(self, ev: QDropEvent) -> None:
        self.set_active(False)
        node = mime_node(ev.mimeData(), self.session)
        if node is None or node.level != self.level:
            ev.ignore()
            return
        ev.acceptProposedAction()
        if self.multi:
            if all(n is not node for n in self.nodes):
                self.nodes.append(node)
        else:
            self.nodes = [node]
        self._refresh_chips()
        self.changed.emit()
