import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication


APP = QApplication.instance() or QApplication([])


class DummySfx:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class DummyProgress:
    def __init__(self, *args, **kwargs):
        self.updated = []
        self.closed = False

    def wasCanceled(self):
        return False

    def update(self, value):
        self.updated.append(value)

    def close(self):
        self.closed = True


class CancelAfterFirstProgress(DummyProgress):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checks = 0

    def wasCanceled(self):
        self._checks += 1
        return self._checks > 1


class AlwaysCanceledProgress(DummyProgress):
    def wasCanceled(self):
        return True


class DummyScanDialog:
    def __init__(self, *args, **kwargs):
        self._canceled = False

    def setWindowTitle(self, *_args, **_kwargs):
        return None

    def setWindowModality(self, *_args, **_kwargs):
        return None

    def setMinimumDuration(self, *_args, **_kwargs):
        return None

    def setAutoClose(self, *_args, **_kwargs):
        return None

    def setAutoReset(self, *_args, **_kwargs):
        return None

    def setStyleSheet(self, *_args, **_kwargs):
        return None

    def show(self):
        return None

    def close(self):
        return None

    def setLabelText(self, *_args, **_kwargs):
        return None

    def wasCanceled(self):
        return self._canceled


def write_test_image(path: str, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    Image.new("RGB", (16, 16), color).save(path, format="PNG")
