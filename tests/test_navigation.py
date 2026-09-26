import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from privatemoney.main import MainWindow


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_navigation_clamps_and_updates_selection(self):
        window = MainWindow()
        try:
            self.assertEqual(window.stack.currentIndex(), 0)
            self.assertTrue(window.nav_buttons[0].isChecked())

            window._move_page(1)
            self.assertEqual(window.stack.currentIndex(), 1)
            self.assertTrue(window.nav_buttons[1].isChecked())

            window._move_page(-1)
            window._move_page(-1)
            self.assertEqual(window.stack.currentIndex(), 0)

            window._set_page(window.stack.count() - 1)
            window._move_page(1)
            self.assertEqual(window.stack.currentIndex(), window.stack.count() - 1)
            self.assertTrue(window.nav_buttons[-1].isChecked())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
