import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PRIVATE_MONEY_TESTING"] = "1"

from PySide6.QtWidgets import QApplication

from privatemoney.main import MainWindow
from privatemoney.pages import CategoryTagFilter


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_overview_net_worth_duration_control(self):
        window=MainWindow()
        try:
            dashboard=window.pages[0]
            self.assertEqual(dashboard.net_duration.currentText(),"6M")
            self.assertFalse(dashboard.net_chart.show_points)
            self.assertTrue(dashboard.net_chart.hover_tooltip)
            self.assertTrue(dashboard.net_chart.show_trend)
            self.assertTrue(hasattr(dashboard.net_chart,"trend_change_percent"))
        finally:
            window.close()

    def test_net_worth_tab_removed(self):
        window=MainWindow()
        try:
            labels=[button.text() for button in window.nav_buttons]
            self.assertEqual(len(labels),6)
            self.assertFalse(any("Net worth" in label for label in labels))
            self.assertFalse(any("Reports" in label for label in labels))
            self.assertTrue(any("Budgets & Goals" in label for label in labels))
            self.assertEqual(sum("Transactions" in label for label in labels),1)
            self.assertEqual(window.stack.count(),6)
        finally:
            window.close()

    def test_category_tag_scroll_is_preserved_on_remove(self):
        field=CategoryTagFilter()
        field.resize(300,42)
        field.set_options(["One","Two","Three","Four","Five","Six"])
        for value in ["One","Two","Three","Four","Five","Six"]:
            field._add(value)
        field._scroll=min(80,field._max_scroll())
        before=field._scroll
        field._remove("Three")
        self.assertEqual(field._scroll,min(before,field._max_scroll()))
        field.deleteLater()

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
