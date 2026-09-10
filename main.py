from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from summit.ui import app_icon
from summit.database import Database
from summit.theme import build_stylesheet
from summit.ui import MainWindow, OnboardingWindow


class SummitApplication:
    def __init__(self) -> None:
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Summit")
        self.app.setOrganizationName("Summit")
        self.app.setWindowIcon(app_icon())
        self.app.setStyle("Fusion")
        self.database = Database()
        settings = self.database.settings()
        self.app.setStyleSheet(build_stylesheet(settings["theme_mode"], settings["accent_color"]))
        self.window: MainWindow | OnboardingWindow | None = None

    def show(self) -> None:
        if self.database.is_configured():
            self.show_dashboard()
        else:
            onboarding = OnboardingWindow(self.database)
            onboarding.completed.connect(self.show_dashboard)
            self.window = onboarding
            onboarding.show()

    def show_dashboard(self) -> None:
        dashboard = MainWindow(self.database)
        self.window = dashboard
        dashboard.show()

    def run(self) -> int:
        self.show()
        if os.environ.get("SUMMIT_SMOKE_TEST") == "1":
            QTimer.singleShot(500, self.app.quit)
        return self.app.exec()


if __name__ == "__main__":
    raise SystemExit(SummitApplication().run())
