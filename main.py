from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from summit.database import Database
from summit.resources import app_icon
from summit.theme import build_stylesheet
from summit.security import LockWindow
from summit.ui import MainWindow, OnboardingWindow


class SummitApplication:
    def __init__(self) -> None:
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Summit")
        self.app.setOrganizationName("Summit")
        self.app.setStyle("Fusion")
        # Brand icon (purple mark + white peak) for the taskbar, window,
        # title bar and every modal/dialog spawned by this application.
        self.app.setWindowIcon(app_icon())
        self.database = Database()
        settings = self.database.settings()
        self.app.setStyleSheet(build_stylesheet(settings["theme_mode"], settings["accent_color"]))
        self.window: MainWindow | OnboardingWindow | LockWindow | None = None

    def show(self) -> None:
        if not self.database.is_configured():
            onboarding = OnboardingWindow(self.database)
            onboarding.completed.connect(self.show_dashboard)
            self.window = onboarding
            onboarding.show()
        elif self.database.is_pin_enabled():
            lock = LockWindow(self.database)
            lock.unlocked.connect(self.show_dashboard)
            self.window = lock
            lock.show()
        else:
            self.show_dashboard()

    def show_dashboard(self) -> None:
        dashboard = MainWindow(self.database)
        self.window = dashboard
        dashboard.show()

    def run(self) -> int:
        self.show()
        if os.environ.get("SUMMIT_SMOKE_TEST") == "1":
            QTimer.singleShot(500, self.app.quit)
        exit_code = self.app.exec()
        self.database.close()
        return exit_code


if __name__ == "__main__":
    raise SystemExit(SummitApplication().run())
