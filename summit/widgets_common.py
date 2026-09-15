"""Tiny, dependency-free widget helpers shared across the UI modules.

Kept separate (rather than living in summit/ui.py) so that other modules —
like summit/security.py or summit/chrome.py — can use them without
importing summit/ui.py itself, which would create a circular import since
ui.py in turn imports classes from those modules.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QLineEdit


def label(text: str, object_name: str = "", word_wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(word_wrap)
    return widget


def text_field(placeholder: str, value: str = "") -> QLineEdit:
    field = QLineEdit(value)
    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    return field
