import os
import tempfile
import unittest

from kps_security import (
    normalize_session_roots,
    sanitize_loaded_images,
    resolve_non_conflicting_path,
)


class SecurityRegressionTests(unittest.TestCase):
    def test_sanitize_loaded_images_drops_outside_root_and_missing(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            in_root = os.path.join(root, "ok.jpg")
            outside = os.path.join(other, "evil.jpg")
            with open(in_root, "wb") as f:
                f.write(b"ok")
            with open(outside, "wb") as f:
                f.write(b"evil")

            images = [
                {"id": 1, "path": in_root, "size": 2, "bucket": "MAIN"},
                {"id": 2, "path": outside, "size": 4, "bucket": "TRASH"},
                {"id": 3, "path": os.path.join(root, "missing.jpg"), "size": 0},
                {"id": 4, "path": "relative.jpg", "size": 1},
            ]
            out = sanitize_loaded_images(images, [root])
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["id"], 1)

    def test_resolve_non_conflicting_path_adds_suffix(self):
        with tempfile.TemporaryDirectory() as root:
            dst = os.path.join(root, "photo.jpg")
            with open(dst, "wb") as f:
                f.write(b"first")
            candidate = resolve_non_conflicting_path(dst)
            self.assertTrue(candidate.endswith("photo (1).jpg"))

    def test_normalize_session_roots_deduplicates_and_absolutizes(self):
        with tempfile.TemporaryDirectory() as root:
            rel = os.path.relpath(root)
            roots = normalize_session_roots([root, rel, "", 123])
            self.assertEqual(len(roots), 1)
            self.assertTrue(os.path.isabs(roots[0]))


if __name__ == "__main__":
    unittest.main()
