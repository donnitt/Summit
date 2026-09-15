"""Helpers for locating bundled assets.

When Summit runs from source, assets live next to this package. When it
runs as a PyInstaller-frozen executable, bundled data files are unpacked
into a temporary folder exposed as ``sys._MEIPASS``. This helper resolves
the correct path in both cases so the same code works in development and
in the built ``.exe``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def asset_path(*parts: str) -> Path:
    """Return the absolute path to a bundled asset.

    - Running from source: resolved relative to the ``summit`` package.
    - Running from the frozen ``.exe``: resolved inside PyInstaller's
      extracted bundle directory (``sys._MEIPASS``), where ``Summit.spec``
      places the ``summit/assets`` folder via its ``datas`` entry.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).joinpath("summit", "assets", *parts)
    return Path(__file__).resolve().parent.joinpath("assets", *parts)


def app_icon_path() -> Path:
    """Path to the Summit brand icon (multi-resolution .ico)."""
    return asset_path("icon.ico")


def app_icon() -> QIcon:
    """The Summit brand icon (purple mark with the white peak symbol)."""
    return QIcon(str(app_icon_path()))
