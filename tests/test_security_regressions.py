import os
import tempfile
import unittest

from kps_security import (
    is_path_within_roots,
    normalize_session_roots,
    sanitize_session_roots,
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

    def test_sanitize_session_roots_rejects_filesystem_root(self):
        drive_root = os.path.abspath(os.sep)
        roots = sanitize_session_roots([drive_root])
        self.assertEqual(roots, [])

    def test_is_path_within_roots_uses_realpath_for_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "secret.jpg")
            with open(target, "wb") as f:
                f.write(b"secret")

            link = os.path.join(root, "linked")
            try:
                os.symlink(outside, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation is not available in this environment.")

            escaped = os.path.join(link, "secret.jpg")
            self.assertFalse(is_path_within_roots(escaped, [root]))


if __name__ == "__main__":
    unittest.main()
