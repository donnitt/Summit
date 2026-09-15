"""Custom frameless window chrome shared by every top-level window.

Summit hides the native OS title bar and draws its own (TitleBar), plus a
thin resizable margin around the window content (FramelessRoot). Split out
of summit/ui.py so windows defined in other modules (e.g. summit/security.py)
can use apply_frameless_chrome() without importing summit/ui.py itself.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QPushButton, QVBoxLayout, QWidget


# ---------------------------------------------------------------------------
# Frameless window chrome
#
# Summit hides the native OS title bar and draws its own, so every platform
# shows the same custom minimize / maximize / close controls that match the
# app's theme. Dragging the custom bar moves the window and dragging within
# a thin margin around the window edges resizes it — both implemented by
# hand (rather than the native QWindow.startSystemMove/Resize helpers) so
# behaviour is identical and testable across Windows, macOS and Linux.
# ---------------------------------------------------------------------------

RESIZE_MARGIN = 6
TITLE_BAR_HEIGHT = 38

_EDGE_CURSORS = {
    Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.TopEdge | Qt.Edge.LeftEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.BottomEdge | Qt.Edge.RightEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.TopEdge | Qt.Edge.RightEdge: Qt.CursorShape.SizeBDiagCursor,
    Qt.Edge.BottomEdge | Qt.Edge.LeftEdge: Qt.CursorShape.SizeBDiagCursor,
}


class TitleBar(QWidget):
    """Custom replacement for the native window title bar."""

    def __init__(self, window: QMainWindow, show_maximize: bool = True) -> None:
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 10, 6)
        layout.setSpacing(6)
        layout.addStretch()

        self.minimize_button = self._make_button("–")
        self.minimize_button.setToolTip("Minimizar")
        self.minimize_button.clicked.connect(window.showMinimized)
        layout.addWidget(self.minimize_button)

        self.maximize_button = None
        if show_maximize:
            self.maximize_button = self._make_button("▢")
            self.maximize_button.setToolTip("Maximizar")
            self.maximize_button.clicked.connect(self._toggle_maximized)
            layout.addWidget(self.maximize_button)

        self.close_button = self._make_button("✕", close=True)
        self.close_button.setToolTip("Fechar")
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.close_button)

    def _make_button(self, glyph: str, close: bool = False) -> QPushButton:
        button = QPushButton(glyph)
        button.setObjectName("TitleBarButtonClose" if close else "TitleBarButton")
        button.setFixedSize(28, 26)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    # -- dragging -----------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            global_pos = event.globalPosition().toPoint()
            if self._window.isMaximized():
                # Restore first so the window doesn't stay pinned to the
                # screen edges, then re-anchor the drag so it tracks the
                # cursor smoothly instead of jumping.
                ratio = event.position().x() / max(self.width(), 1)
                self._window.showNormal()
                self._drag_offset = QPoint(int(self._window.width() * ratio), self._drag_offset.y())
            self._window.move(global_pos - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.maximize_button is not None:
            self._toggle_maximized()
        super().mouseDoubleClickEvent(event)


class FramelessRoot(QWidget):
    """Outer container that owns the resize-by-edge hit area.

    A thin margin is left around the inner content; that margin belongs to
    this widget (nothing is drawn there), so mouse presses landing in it are
    delivered here rather than to a child, which is what makes edge-resize
    detection possible without native window-manager support.
    """

    def __init__(self, window: QMainWindow) -> None:
        super().__init__()
        self._window = window
        self._resize_edge = Qt.Edge(0)
        self._resize_start_geometry: QRect | None = None
        self._resize_start_pos: QPoint | None = None
        self.setObjectName("Root")
        self.setMouseTracking(True)

    def _edge_at(self, pos: QPoint) -> Qt.Edge:
        margin = RESIZE_MARGIN
        edge = Qt.Edge(0)
        if pos.x() <= margin:
            edge |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - margin:
            edge |= Qt.Edge.RightEdge
        if pos.y() <= margin:
            edge |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - margin:
            edge |= Qt.Edge.BottomEdge
        return edge

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and not self._window.isMaximized():
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start_geometry = self._window.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._resize_edge and (event.buttons() & Qt.MouseButton.LeftButton) and self._resize_start_geometry:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QRect(self._resize_start_geometry)
            min_size = self._window.minimumSize()
            if self._resize_edge & Qt.Edge.LeftEdge:
                geo.setLeft(min(geo.left() + delta.x(), geo.right() - min_size.width()))
            if self._resize_edge & Qt.Edge.RightEdge:
                geo.setRight(max(geo.right() + delta.x(), geo.left() + min_size.width()))
            if self._resize_edge & Qt.Edge.TopEdge:
                geo.setTop(min(geo.top() + delta.y(), geo.bottom() - min_size.height()))
            if self._resize_edge & Qt.Edge.BottomEdge:
                geo.setBottom(max(geo.bottom() + delta.y(), geo.top() + min_size.height()))
            self._window.setGeometry(geo)
            event.accept()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton) and not self._window.isMaximized():
            cursor = _EDGE_CURSORS.get(self._edge_at(event.position().toPoint()))
            self.setCursor(cursor if cursor is not None else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._resize_edge = Qt.Edge(0)
        self._resize_start_geometry = None
        self._resize_start_pos = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)


def apply_frameless_chrome(window: QMainWindow, content: QWidget, show_maximize: bool = True) -> TitleBar:
    """Strip the native title bar and install Summit's own in its place.

    ``content`` is whatever the window would otherwise have passed to
    ``setCentralWidget`` — it's re-parented under a new outer widget that
    adds the custom title bar above it and a thin resizable margin around
    it, then that outer widget becomes the actual central widget.

    The title bar and resize margin take up space that the original
    ``setMinimumSize``/``resize`` calls (made before this runs) didn't
    account for, so both are grown by that same amount here — otherwise
    every page loses that many pixels of height and the sidebar/content
    end up visually cramped, as if a phantom OS title bar were still being
    reserved.
    """
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    outer = FramelessRoot(window)
    outer_layout = QVBoxLayout(outer)
    outer_layout.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)
    outer_layout.setSpacing(0)
    title_bar = TitleBar(window, show_maximize=show_maximize)
    outer_layout.addWidget(title_bar)
    content.setObjectName("Shell")
    outer_layout.addWidget(content, 1)
    window.setCentralWidget(outer)

    chrome_width = RESIZE_MARGIN * 2
    chrome_height = RESIZE_MARGIN * 2 + TITLE_BAR_HEIGHT
    min_size = window.minimumSize()
    if min_size.width() > 0 or min_size.height() > 0:
        window.setMinimumSize(min_size.width() + chrome_width, min_size.height() + chrome_height)
    if window.width() > 0 and window.height() > 0:
        window.resize(window.width() + chrome_width, window.height() + chrome_height)
    return title_bar
