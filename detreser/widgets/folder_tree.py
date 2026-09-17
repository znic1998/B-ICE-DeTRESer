"""Shared "Loaded data" panel: colour-coded folder tree, drag source for the drop zones, Add folder button."""
from __future__ import annotations

import json
import os
from typing import Callable, List, Optional

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap, QFont
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..model import Node, Session
from ..theme import (BLOCKED_COLORS, BORDER_SOFT, MONO, REPLICATE_COLORS, TEXT_SOFT, Badge, button, hbox, level_colors, section_label, vbox)

MIME = "application/x-detreser-node"


def node_mime(node: Node) -> QMimeData:
    md = QMimeData()
    md.setData(MIME, QByteArray(json.dumps({"path": node.path, "level": node.level, "is_file": node.is_file}).encode("utf-8")))
    md.setText(node.name)
    return md


def mime_node(md: QMimeData, session: Session) -> Optional[Node]:
    if not md.hasFormat(MIME):
        return None
    try:
        d = json.loads(bytes(md.data(MIME)).decode("utf-8"))
    except Exception:
        return None
    return find_node(session, d.get("path", ""))


def find_node(session: Session, path: str) -> Optional[Node]:
    def walk(n: Node):
        if n.path == path:
            return n
        for c in n.children:
            r = walk(c)
            if r is not None:
                return r
        return None

    for r in session.roots:
        f = walk(r)
        if f is not None:
            return f
    return None


class _Tree(QTreeWidget):
    """QTreeWidget whose rows are drag sources carrying the node path."""

    def __init__(self, panel: "FolderTree"):
        super().__init__()
        self.panel = panel
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setRootIsDecorated(True)
        self.setExpandsOnDoubleClick(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def startDrag(self, actions):
        item = self.currentItem()
        if item is None:
            return
        node: Node = item.data(0, Qt.UserRole)
        if node is None or node.is_file:
            return
        drag = QDrag(self)
        drag.setMimeData(node_mime(node))
        # drag pixmap: the badge
        bg, fg = level_colors(node.level) if node.status != "blocked" else BLOCKED_COLORS
        font = QFont(self.font())
        font.setPointSize(11)
        pm = QPixmap(max(60, len(node.name) * 8 + 24), 26)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(bg))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(pm.rect(), 4, 4)
        p.setPen(QColor(fg))
        p.setFont(font)
        p.drawText(pm.rect(), Qt.AlignCenter, node.name)
        p.end()
        drag.setPixmap(pm)
        drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.CopyAction)

    def _menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        node: Node = item.data(0, Qt.UserRole)
        if node is None or node.level != 1 or node.is_file:
            return
        m = QMenu(self)
        act = m.addAction(f"Remove {node.name} from the loaded data")
        if m.exec(self.viewport().mapToGlobal(pos)) == act:
            self.panel.remove_root(node)


class FolderTree(QFrame):
    """The 280 px panel on the left of most pages."""

    changed = Signal()  # roots added or removed

    def __init__(self, session: Session, allow_add: bool = True):
        super().__init__()
        self.session = session
        self.setProperty("panel", True)
        self.setFixedWidth(280)
        lay = vbox(self, (16, 16, 16, 16), 12)
        lay.addWidget(section_label("Loaded data"))
        self.legend = QWidget()
        from PySide6.QtWidgets import QGridLayout
        self.legend_lay = QGridLayout(self.legend)
        self.legend_lay.setContentsMargins(0, 0, 0, 0)
        self.legend_lay.setHorizontalSpacing(6)
        self.legend_lay.setVerticalSpacing(6)
        lay.addWidget(self.legend)
        sep = QFrame()
        sep.setProperty("hline", True)
        lay.addWidget(sep)
        tools = QWidget()
        th = hbox(tools, spacing=6)
        self.expand_btn = button("Expand all", "small", lambda: self.set_expanded(True))
        self.collapse_btn = button("Collapse", "small", lambda: self.set_expanded(False))
        for b in (self.expand_btn, self.collapse_btn):
            b.setStyleSheet("QPushButton { padding: 0 10px; font-size: 12px; min-height: 28px; max-height: 28px; border-radius: 6px; }")
            th.addWidget(b)
        th.addStretch(1)
        lay.addWidget(tools)
        self.tree = _Tree(self)
        lay.addWidget(self.tree, 1)
        self.hint = QLabel("Drag a folder onto a drop zone to use it.")
        self.hint.setProperty("muted13", True)
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.add_btn = button("Add folder…", "small", self.add_folder)
        self.add_btn.setFixedHeight(40)
        lay.addWidget(self.add_btn)
        if not allow_add:
            self.add_btn.hide()
        self.refresh()

    # ---- building --------------------------------------------------------------
    def refresh(self) -> None:
        s = self.session
        # legend
        while self.legend_lay.count():
            w = self.legend_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        n = max(s.n_levels, 3 if not s.roots else s.n_levels)
        badges = [Badge(s.level_name(k) if s.level_names and s.level_name(k) != f"Level {k}" else f"Level {k}", level=k, size=11, weight=600) for k in range(1, n + 1)]
        badges.append(Badge("Replicate", REPLICATE_COLORS, size=11, weight=600))
        # flow the badges into rows of at most 248 px
        row, col, width, max_col = 0, 0, 0, 0
        for b in badges:
            bw = b.sizeHint().width() + 6
            if col and width + bw > 248:
                row, col, width = row + 1, 0, 0
            self.legend_lay.addWidget(b, row, col, Qt.AlignLeft)
            col += 1
            width += bw
            max_col = max(max_col, col)
        for c in range(max_col + 1):
            self.legend_lay.setColumnStretch(c, 0)
        self.legend_lay.setColumnStretch(max_col, 1)
        # tree: folders open, replicate files folded away (click the arrow to open a folder)
        self.tree.clear()
        for r in s.roots:
            self._add_item(None, r)
        self.set_expanded(True)
        self.hint.setVisible(bool(s.roots))

    def set_expanded(self, expanded: bool) -> None:
        """Expand every folder (files stay folded) or collapse to the root folders."""
        def walk(item):
            node = item.data(0, Qt.UserRole)
            if node is None or node.is_file:
                return
            has_files = any(c.is_file for c in node.children)
            item.setExpanded(bool(expanded and not has_files))  # folders holding the replicate files start folded
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _add_item(self, parent, node: Node) -> None:
        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, node)
        item.setFlags((item.flags() | Qt.ItemIsDragEnabled) if not node.is_file else (item.flags() & ~Qt.ItemIsDragEnabled))
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        w = QWidget()
        h = hbox(w, (0, 2, 0, 2), 6)
        if node.is_file:
            lab = QLabel(node.name)
            lab.setStyleSheet(f"font-family: '{MONO}', monospace; font-size: 12px; color: {TEXT_SOFT};")
            h.addWidget(lab)
        else:
            blocked = node.status == "blocked"
            text = f"✕ {node.name}" if blocked else node.name
            b = Badge(text, level=node.level, blocked=blocked)
            if blocked:
                b.setToolTip(f"Blocked: {node.block_reason}")
            elif node.status == "ok":
                b.setToolTip("Analysed")
            h.addWidget(b)
            if node.level == 1 and not self.add_btn.isHidden():
                x = button("×", "tiny", lambda _=False, n=node: self.remove_root(n))
                x.setToolTip(f"Remove {node.name} from the loaded data")
                h.addWidget(x)
        h.addStretch(1)
        self.tree.setItemWidget(item, 0, w)
        item.setSizeHint(0, QSize(0, 30))
        for c in node.children:
            self._add_item(item, c)

    # ---- roots -----------------------------------------------------------------
    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add data folder", os.path.expanduser("~"))
        if d:
            self.add_paths([d])

    def add_paths(self, paths: List[str]) -> List[str]:
        errors = []
        for p in paths:
            if not os.path.isdir(p):
                errors.append(f"{os.path.basename(p)} is not a folder.")
                continue
            e = self.session.add_root(p)
            if e:
                errors.append(e)
        self.refresh()
        self.changed.emit()
        return errors

    def remove_root(self, node: Node) -> None:
        self.session.remove_root(node.path)
        self.refresh()
        self.changed.emit()
