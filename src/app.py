"""Main application window with stacked page navigation.

v3.0.0: Landing page with 3 module cards (ANPR, Counter, Intersection)
plus Settings.  Each module page is a self-contained 3-step wizard.
"""

from PySide6.QtWidgets import QMainWindow, QStackedWidget
from PySide6.QtCore import Slot

from src.landing_page import LandingPage
from src.anpr.anpr_page import ANPRPage
from src.counter.counter_page import CounterPage
from src.intersection.intersection_page import IntersectionPage
from src.pedestrian.pedestrian_page import PedestrianPage
from src.settings_page import SettingsPage


class MainWindow(QMainWindow):
    """Main application window with landing page and module pages."""

    PAGE_LANDING = 0
    PAGE_ANPR = 1
    PAGE_COUNTER = 2
    PAGE_INTERSECTION = 3
    PAGE_SETTINGS = 4
    PAGE_PEDESTRIAN = 5

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Matrix Traffic Data Extraction")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Stacked widget for page navigation
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Create pages
        self.landing_page = LandingPage()
        self.landing_page.module_selected.connect(self._on_module_selected)

        self.anpr_page = ANPRPage(on_back=self._go_to_landing)
        self.counter_page = CounterPage(on_back=self._go_to_landing)
        self.intersection_page = IntersectionPage()
        self.intersection_page.back_to_menu.connect(self._go_to_landing)
        self.pedestrian_page = PedestrianPage(on_back=self._go_to_landing)

        self.settings_page = SettingsPage()
        self.settings_page.back_clicked.connect(self._go_to_landing)

        # Add pages to stack
        self.stack.addWidget(self.landing_page)        # index 0
        self.stack.addWidget(self.anpr_page)           # index 1
        self.stack.addWidget(self.counter_page)        # index 2
        self.stack.addWidget(self.intersection_page)   # index 3
        self.stack.addWidget(self.settings_page)       # index 4
        self.stack.addWidget(self.pedestrian_page)     # index 5

        # Start on landing page
        self.stack.setCurrentIndex(self.PAGE_LANDING)

    @Slot(str)
    def _on_module_selected(self, module: str):
        if module == "anpr":
            self.stack.setCurrentIndex(self.PAGE_ANPR)
        elif module == "counter":
            self.stack.setCurrentIndex(self.PAGE_COUNTER)
        elif module == "intersection":
            self.stack.setCurrentIndex(self.PAGE_INTERSECTION)
        elif module == "pedestrian":
            self.stack.setCurrentIndex(self.PAGE_PEDESTRIAN)
        elif module == "settings":
            self.stack.setCurrentIndex(self.PAGE_SETTINGS)

    def _go_to_landing(self):
        self.stack.setCurrentIndex(self.PAGE_LANDING)
