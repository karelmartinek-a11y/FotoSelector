import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from KajovoPhotoSelector import MainWindow
from support import APP, DummyProgress, DummyScanDialog, DummySfx, write_test_image


class AutoDuplicateDialog:
    def __init__(self, *args, **kwargs):
        self.choice = "auto_all"
        self.selected_indices = []

    def exec(self):
        return 1


class E2ESmokeTests(unittest.TestCase):
    def setUp(self):
        self.win = MainWindow(sfx=DummySfx())
        self.win.show()
        QApplication.processEvents()

    def tearDown(self):
        self.win._exit_in_progress = True
        self.win.hide()
        self.win.deleteLater()
        QApplication.processEvents()

    def test_e2e_scan_save_load_and_apply_via_toolbar_buttons(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as target_root, tempfile.TemporaryDirectory() as work_root:
            image_path = os.path.join(source_root, "keep.png")
            session_path = os.path.join(work_root, "session.json")
            write_test_image(image_path)

            with patch("KajovoPhotoSelector.QFileDialog.getExistingDirectory", side_effect=[source_root, target_root]), \
                patch("KajovoPhotoSelector.QFileDialog.getSaveFileName", return_value=(session_path, "JSON")), \
                patch("KajovoPhotoSelector.QFileDialog.getOpenFileName", return_value=(session_path, "JSON")), \
                patch("KajovoPhotoSelector.QProgressDialog", DummyScanDialog), \
                patch("KajovoPhotoSelector.DagmarProgress", DummyProgress), \
                patch.object(self.win, "_ask_scan_options", return_value=(0, 0, False)), \
                patch.object(self.win, "confirm_session_roots", return_value=True), \
                patch.object(self.win, "_coin_per_file"), \
                patch.object(self.win, "toast"), \
                patch.object(self.win, "_play_reklama_if_exists"), \
                patch.object(self.win, "_kajo_box", side_effect=["Kájo, proveď to", None]):
                QTest.mouseClick(self.win.btn_kajo_stopa, Qt.MouseButton.LeftButton)
                QApplication.processEvents()

                self.assertEqual(len(self.win.images), 1)
                self.assertEqual(self.win.session_roots, [source_root])
                self.assertEqual(self.win.list_widget.count(), 1)

                QTest.mouseClick(self.win.bucket_widgets["T1"]["btn_select"], Qt.MouseButton.LeftButton)
                QApplication.processEvents()
                self.assertEqual(self.win.buckets["T1"].path, target_root)

                item = self.win.list_widget.item(0)
                item.setSelected(True)
                self.win.list_widget.setCurrentItem(item)
                QApplication.processEvents()

                QTest.mouseClick(self.win.bucket_widgets["T1"]["btn_assign"], Qt.MouseButton.LeftButton)
                QApplication.processEvents()
                self.assertEqual(self.win.images[0].bucket, "T1")
                self.assertTrue(self.win.session_dirty)

                QTest.mouseClick(self.win.btn_save, Qt.MouseButton.LeftButton)
                QApplication.processEvents()

                self.assertTrue(os.path.exists(session_path))
                with open(session_path, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                self.assertEqual(session_data["roots"], [source_root])
                self.assertEqual(session_data["images"][0]["bucket"], "T1")

                self.win.reset_state()
                QApplication.processEvents()

                QTest.mouseClick(self.win.btn_load, Qt.MouseButton.LeftButton)
                QApplication.processEvents()

                self.assertEqual(len(self.win.images), 1)
                self.assertEqual(self.win.images[0].bucket, "T1")
                self.assertEqual(self.win.buckets["T1"].path, "")
                self.assertEqual(self.win.bucket_widgets["T1"]["lbl_path"].text(), "Cesta: (není namapováno)")

                with patch("KajovoPhotoSelector.QFileDialog.getExistingDirectory", return_value=target_root):
                    QTest.mouseClick(self.win.bucket_widgets["T1"]["btn_select"], Qt.MouseButton.LeftButton)
                    QApplication.processEvents()

                QTest.mouseClick(self.win.btn_run, Qt.MouseButton.LeftButton)
                QApplication.processEvents()

            self.assertTrue(os.path.exists(os.path.join(target_root, "keep.png")))
            self.assertFalse(os.path.exists(image_path))
            self.assertEqual(self.win.images, [])
            self.assertEqual(self.win.session_roots, [])
            self.assertFalse(self.win.session_dirty)

    def test_e2e_duplicate_detection_marks_one_record_for_trash(self):
        with tempfile.TemporaryDirectory() as source_root:
            img1 = os.path.join(source_root, "dup1.png")
            img2 = os.path.join(source_root, "dup2.png")
            write_test_image(img1, color=(10, 20, 30))
            write_test_image(img2, color=(10, 20, 30))

            with patch("KajovoPhotoSelector.QFileDialog.getExistingDirectory", return_value=source_root), \
                patch("KajovoPhotoSelector.QProgressDialog", DummyScanDialog), \
                patch("KajovoPhotoSelector.DagmarProgress", DummyProgress), \
                patch("KajovoPhotoSelector.DuplicateGroupDialog", AutoDuplicateDialog), \
                patch.object(self.win, "_ask_scan_options", return_value=(0, 0, False)), \
                patch.object(self.win, "_coin_per_file"), \
                patch.object(self.win, "toast"):
                QTest.mouseClick(self.win.btn_kajo_stopa, Qt.MouseButton.LeftButton)
                QApplication.processEvents()
                QTest.mouseClick(self.win.btn_dupes, Qt.MouseButton.LeftButton)
                QApplication.processEvents()

            buckets = sorted(rec.bucket for rec in self.win.images)
            self.assertEqual(buckets, ["MAIN", "TRASH"])


if __name__ == "__main__":
    unittest.main()
