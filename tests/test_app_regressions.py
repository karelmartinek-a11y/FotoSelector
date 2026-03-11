import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from KajovoPhotoSelector import DEFAULT_BUCKET_ALIASES, DuplicateGroupDialog, ImageRecord, MainWindow
from test_support import (
    APP,
    AlwaysCanceledProgress,
    CancelAfterFirstProgress,
    DummyProgress,
    DummyScanDialog,
    DummySfx,
)


class AppRegressionTests(unittest.TestCase):
    def setUp(self):
        self.win = MainWindow(sfx=DummySfx())

    def tearDown(self):
        self.win.deleteLater()
        QApplication.processEvents()

    def test_reset_state_clears_bucket_aliases_and_paths(self):
        bucket = self.win.buckets["T1"]
        bucket.alias = "Moje hromada"
        bucket.path = os.path.abspath(".")
        self.win.bucket_widgets["T1"]["group_box"].setTitle("MOJE HROMADA")
        self.win.bucket_widgets["T1"]["btn_assign"].setText("stare")

        self.win.reset_state()

        self.assertEqual(bucket.alias, DEFAULT_BUCKET_ALIASES["T1"])
        self.assertEqual(bucket.path, "")
        self.assertEqual(self.win.bucket_widgets["T1"]["group_box"].title(), DEFAULT_BUCKET_ALIASES["T1"].upper())
        self.assertEqual(
            self.win.bucket_widgets["T1"]["btn_assign"].text(),
            f"Kájo, hoď to do: {DEFAULT_BUCKET_ALIASES['T1']}",
        )

    def test_on_thumb_ready_ignores_stale_worker_results(self):
        rec = ImageRecord(id=1, path=r"C:\photos\new.jpg", size=10)
        self.win.image_by_id[1] = rec
        image = QImage(8, 8, QImage.Format.Format_RGB32)

        self.win.on_thumb_ready(1, r"C:\photos\old.jpg", image)

        self.assertNotIn(1, self.win.thumb_cache)

    def test_on_load_sanitizes_bucket_code_and_requires_confirmation_of_session_roots(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as target:
            image_path = os.path.join(root, "ok.jpg")
            with open(image_path, "wb") as f:
                f.write(b"ok")

            session_path = os.path.join(root, "session.json")
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "roots": [root],
                        "images": [{"id": 1, "path": image_path, "size": 2, "bucket": "NEZNAMY"}],
                        "buckets": {"T1": {"alias": "Muj cil", "path": target}},
                    },
                    f,
                )

            with patch("KajovoPhotoSelector.QFileDialog.getOpenFileName", return_value=(session_path, "JSON")), \
                patch("KajovoPhotoSelector.DagmarProgress", DummyProgress), \
                patch.object(self.win, "prompt_unsaved", return_value="discard"), \
                patch.object(self.win, "confirm_session_roots", return_value=True) as confirm_mock, \
                patch.object(self.win, "_coin_per_file"), \
                patch.object(self.win, "toast"):
                self.win.on_load()

            confirm_mock.assert_called_once_with([root], 1)
            self.assertEqual(len(self.win.images), 1)
            self.assertEqual(self.win.images[0].bucket, "MAIN")
            self.assertEqual(self.win.buckets["T1"].alias, "Muj cil")
            self.assertEqual(self.win.buckets["T1"].path, "")
            self.assertEqual(self.win.bucket_widgets["T1"]["lbl_path"].text(), "Cesta: (není namapováno)")

    def test_on_load_aborts_when_session_roots_are_not_confirmed(self):
        with tempfile.TemporaryDirectory() as root:
            image_path = os.path.join(root, "ok.jpg")
            with open(image_path, "wb") as f:
                f.write(b"ok")

            session_path = os.path.join(root, "session.json")
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "roots": [root],
                        "images": [{"id": 1, "path": image_path, "size": 2, "bucket": "MAIN"}],
                    },
                    f,
                )

            self.win.images = [ImageRecord(id=99, path=image_path, size=2, bucket="MAIN")]
            self.win.image_by_id = {99: self.win.images[0]}

            with patch("KajovoPhotoSelector.QFileDialog.getOpenFileName", return_value=(session_path, "JSON")), \
                patch.object(self.win, "prompt_unsaved", return_value="discard"), \
                patch.object(self.win, "confirm_session_roots", return_value=False):
                self.win.on_load()

            self.assertEqual([rec.id for rec in self.win.images], [99])
            self.assertIn(99, self.win.image_by_id)

    def test_on_run_apply_keeps_unfinished_records_after_cancel(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as target1, tempfile.TemporaryDirectory() as target2:
            src1 = os.path.join(root, "one.jpg")
            src2 = os.path.join(root, "two.jpg")
            for path in [src1, src2]:
                with open(path, "wb") as f:
                    f.write(b"img")

            rec1 = ImageRecord(id=1, path=src1, size=3, bucket="T1")
            rec2 = ImageRecord(id=2, path=src2, size=3, bucket="T2")
            self.win.images = [rec1, rec2]
            self.win.image_by_id = {1: rec1, 2: rec2}
            self.win.buckets["T1"].path = target1
            self.win.buckets["T2"].path = target2
            self.win._recalculate_bucket_totals()

            prompts = iter(["Kájo, proveď to", None])
            moved_targets = []

            with patch("KajovoPhotoSelector.DagmarProgress", CancelAfterFirstProgress), \
                patch("KajovoPhotoSelector.safe_move_file", side_effect=lambda src, dst: moved_targets.append((src, dst))), \
                patch.object(self.win, "_kajo_box", side_effect=lambda *args, **kwargs: next(prompts)), \
                patch.object(self.win, "_coin_per_file"), \
                patch.object(self.win, "_play_reklama_if_exists"):
                self.win.on_run_apply()

            self.assertEqual(len(moved_targets), 1)
            self.assertEqual([rec.id for rec in self.win.images], [2])
            self.assertEqual(self.win.buckets["T1"].count, 0)
            self.assertEqual(self.win.buckets["T2"].count, 1)
            self.assertTrue(self.win.session_dirty)

    def test_scan_filter_cancel_does_not_import_partial_results(self):
        with tempfile.TemporaryDirectory() as root:
            paths = []
            for name in ["a.jpg", "b.jpg"]:
                path = os.path.join(root, name)
                with open(path, "wb") as f:
                    f.write(b"img")
                paths.append(path)

            with patch("KajovoPhotoSelector.iter_image_paths", return_value=paths), \
                patch("KajovoPhotoSelector.DagmarProgress", AlwaysCanceledProgress), \
                patch("KajovoPhotoSelector.QProgressDialog", DummyScanDialog), \
                patch.object(self.win, "toast"):
                self.win._scan_directories([root], append=True, min_kb=0, max_kb=0, ignore_system=False)

            self.assertEqual(self.win.images, [])

    def test_duplicate_dialog_requires_selection_before_keep(self):
        with tempfile.TemporaryDirectory() as root:
            image_path = os.path.join(root, "dup.jpg")
            with open(image_path, "wb") as f:
                f.write(b"dup")

            dialog = DuplicateGroupDialog(self.win, 0, 1, [ImageRecord(id=1, path=image_path, size=1)])
            dialog._toggle_selection(0)
            dialog._on_keep()

            self.assertEqual(dialog.choice, "skip")
            self.assertEqual(dialog.result(), 0)
            dialog.close()


if __name__ == "__main__":
    unittest.main()
