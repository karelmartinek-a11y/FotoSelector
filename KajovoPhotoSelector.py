# Kaja_Tridi_Obrazky_v5.py
# KájovoPhotoSelector – hravé třídění fotek (Kája svět)
# Vytvořeno: 2025-11-17
import os
import sys
import json
import time
import shutil
import logging
import warnings
import platform
import random
import subprocess
import tempfile
import weakref
from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Optional, Tuple
from PyQt6.QtCore import (
    Qt,
    QSize,
    QThreadPool,
    QRunnable,
    pyqtSlot,
    QObject,
    pyqtSignal,
    QMimeData,
    QTimer,
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QPoint,
    QPointF,
    QUrl,
)
from PyQt6.QtGui import (
    QIcon,
    QPixmap,
    QImage,
    QImageReader,
    QPalette,
    QColor,
    QMouseEvent,
    QBrush,
    QPainter,
    QDrag,
    QGuiApplication,
    QEnterEvent,
    QFont,
    QCursor,
    QFontMetrics,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QAbstractButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QProgressDialog,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QAbstractItemView,
    QScrollArea,
    QFrame,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
    QRubberBand,
)

try:
    from PyQt6.QtMultimedia import QSoundEffect
except Exception:
    QSoundEffect = None

# Windows taskbar icon / AppUserModelID (pomáhá, aby se ikona v taskbaru držela aplikace)
def _set_windows_appusermodel_id(app_id: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes  # noqa: PLC0415

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
from PIL import Image, ImageFile, UnidentifiedImageError
ImageFile.LOAD_TRUNCATED_IMAGES = True
try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR_NAME = "resources"


def resource_path(rel_path: str) -> str:
    """
    Cesty kompatibilní s PyInstallerem.
    - při běhu z .py: BASE_DIR
    - při běhu z .exe (PyInstaller): sys._MEIPASS
    """
    base = getattr(sys, "_MEIPASS", None)
    root = base if base else BASE_DIR
    candidate = os.path.join(root, RESOURCE_DIR_NAME, rel_path)
    if base or os.path.exists(candidate):
        return candidate
    return os.path.join(root, rel_path)


def wav_duration_ms(filename: str, default_ms: int = 1600) -> int:
    # Vrati delku WAV v ms; fallback na default pri chybe.
    path = resource_path(filename)
    try:
        import wave  # noqa: PLC0415

        with wave.open(path, "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
        if rate <= 0:
            return default_ms
        return max(1, int((frames / rate) * 1000))
    except Exception:
        return default_ms
# =====================
# KONSTANTY A BARVY UI
# =====================
APP_NAME = "KájovoPhotoSelector"

# “Kájův svět” – hravá, moderní, ale stále čitelná paleta
BG_COLOR = "#0B1020"            # hlubší “noční” modrá
SURFACE_COLOR = "#101A33"       # panely/karty
PRIMARY_COLOR = "#E53935"       # “Mario red” vibe
ACCENT_COLOR = "#FFD54F"        # “coin gold”
MINT_COLOR = "#4DD0E1"          # jemný neon pro zvýraznění
TEXT_COLOR = "#EAF0FF"
SUBTEXT_COLOR = "#B9C6FF"

# UI rozměry
TOPBAR_H = 64
RADIUS = 14

# Zvuky (volitelné soubory v BASE_DIR)
SFX_COIN = "sfx_coin.wav"
SFX_JUMP = "sfx_jump.wav"
SFX_POP = "sfx_pop.wav"
SFX_ERROR = "sfx_error.wav"
SFX_INTRO = "sfx_intro.wav"
SFX_OUTRO = "sfx_outro.wav"
MAIN_BG_IMAGE = "plocha.png"
# “rozumné” modály (ne mikro okénka)
DLG_BASE_W_CHARS = 64
DLG_BASE_H_LINES = 12


def apply_dialog_sizing(w: QWidget, extra_w: int = 0, extra_h: int = 0):
    """
    Nastaví rozumné minimum dle aktuálního fontu.
    Používej pro QMessageBox/QProgressDialog/QDialog apod.
    """
    try:
        fm = QFontMetrics(w.font())
        min_w = max(680, fm.averageCharWidth() * DLG_BASE_W_CHARS) + int(extra_w)
        min_h = max(340, fm.height() * DLG_BASE_H_LINES) + int(extra_h)
        w.setMinimumSize(int(min_w), int(min_h))
    except Exception:
        pass


def _qss_btn(bg: str, fg: str, border: str, hover_bg: str, pressed_bg: str) -> str:
    return f"""
    QPushButton {{
        background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: {RADIUS}px;
        padding: 10px 14px;
        font-weight: 800;
        letter-spacing: 0.2px;
    }}
    QPushButton:hover {{
        background-color: {hover_bg};
    }}
    QPushButton:pressed {{
        background-color: {pressed_bg};
        padding-top: 11px;
        padding-bottom: 9px;
    }}
    QPushButton:disabled {{
        background-color: #2A2F45;
        color: #7D86B0;
        border: 1px solid #2A2F45;
    }}
    """

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}  # TIF/TIFF záměrně vynecháno
MAX_THUMB_PIXELS = 40_000_000
MAX_HASH_PIXELS = 80_000_000
SYSTEM_PATH_KEYWORDS = [
    "\\windows\\",
    "\\program files\\",
    "\\program files (x86)\\",
    "\\programdata\\",
    "\\appdata\\",
    "\\$recycle.bin\\",
    "\\system volume information\\",
    "\\venv\\",
    "\\.venv\\",
    "\\site-packages\\",
    "\\comfyui\\",
]
PROGRESS_QSS = f"""
QProgressBar {{
    border: 1px solid {ACCENT_COLOR};
    background: {BG_COLOR};
    color: white;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {ACCENT_COLOR};
}}
"""
# Moderní tlačítka (sjednocený systém)
BUTTON_PRIMARY_QSS = _qss_btn(PRIMARY_COLOR, "white", "#00000000", "#F04745", "#C62828")
BUTTON_GOLD_QSS = _qss_btn(ACCENT_COLOR, "#1A1A1A", "#00000000", "#FFE082", "#FFCA28")
BUTTON_SURFACE_QSS = _qss_btn(SURFACE_COLOR, TEXT_COLOR, "#283152", "#18234A", "#0E1630")
BUTTON_DANGER_QSS = _qss_btn("#D32F2F", "white", "#00000000", "#E53935", "#B71C1C")
DIALOG_FRAME_QSS = f"""
QDialog {{
    border: 2px solid {ACCENT_COLOR};
    border-radius: 8px;
}}
QMessageBox {{
    border: 2px solid {ACCENT_COLOR};
    border-radius: 8px;
}}
QProgressDialog {{
    border: 2px solid {ACCENT_COLOR};
    border-radius: 8px;
}}
"""
# =====================
# LOGOVÁNÍ
# =====================
LOG_PATH = os.path.join(BASE_DIR, "KajovoPhotoSelector.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
# =====================
# ASSETY (logo + ikona)
# =====================
APP_ICON_PNG_CANDIDATES = ["KajovoPhotoSelector.png", "kajovo_photoselector_logo.png", "kaja.png"]
APP_ICON_ICO_CANDIDATES = ["kajovo_photoselector.ico", "kajovo.ico"]


def _first_existing(rel_names: List[str]) -> Optional[str]:
    for name in rel_names:
        p = resource_path(name)
        if os.path.exists(p):
            return p
    return None


def get_app_icon() -> QIcon:
    ico = _first_existing(APP_ICON_ICO_CANDIDATES)
    if ico:
        return QIcon(ico)
    png = _first_existing(APP_ICON_PNG_CANDIDATES)
    if png:
        return QIcon(png)
    return QIcon()


def load_app_icon() -> QIcon:
    """Alias kvůli stávajícím voláním."""
    return get_app_icon()


def load_logo_pixmap(max_w: int = 520) -> Optional[QPixmap]:
    png = _first_existing(APP_ICON_PNG_CANDIDATES)
    if not png:
        return None
    pm = QPixmap(png)
    if pm.isNull():
        return None
    if pm.width() > max_w:
        pm = pm.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
    return pm


# =====================
# HRAVÉ ANIMACE + TOASTY + ZVUKY
# =====================


class RubberAnimator:
    """
    “měkká guma” deformace pro libovolné tlačítko (krátká animace, layout ji nestihne přepsat).
    """

    def __init__(self):
        self._anims: "weakref.WeakKeyDictionary[QWidget, QPropertyAnimation]" = (
            weakref.WeakKeyDictionary()
        )

    def press(self, w: QWidget):
        try:
            geo = w.geometry()
            if geo.width() <= 2 or geo.height() <= 2:
                return
            inset = max(2, min(6, int(min(geo.width(), geo.height()) * 0.06)))
            squish = QRect(
                geo.x() + inset,
                geo.y() + inset + 1,
                max(1, geo.width() - 2 * inset),
                max(1, geo.height() - 2 * inset),
            )
            overshoot = QRect(
                geo.x() - 1,
                geo.y() - 1,
                geo.width() + 2,
                geo.height() + 2,
            )
            anim = self._anims.get(w)
            if anim is None:
                anim = QPropertyAnimation(w, b"geometry")
                self._anims[w] = anim
            anim.stop()
            anim.setDuration(180)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(geo)
            anim.setKeyValueAt(0.55, squish)
            anim.setKeyValueAt(0.85, overshoot)
            anim.setEndValue(geo)
            anim.start()
        except Exception:
            return


RUBBER = RubberAnimator()


class SoundBank:
    def __init__(self):
        self.enabled = True
        self._effects: Dict[str, "QSoundEffect"] = {}
        if QSoundEffect is None:
            self.enabled = False
        self._queue_delay_ms = 0
        self._queue_step_ms = 55

    def _get(self, filename: str):
        if QSoundEffect is None:
            return None
        if filename in self._effects:
            return self._effects[filename]
        path = resource_path(filename)
        if not os.path.exists(path):
            return None
        eff = QSoundEffect()
        eff.setSource(QUrl.fromLocalFile(path))
        eff.setVolume(0.85)
        self._effects[filename] = eff
        return eff

    def play(self, filename: str):
        if not self.enabled:
            return
        eff = self._get(filename)
        if eff is None:
            return
        try:
            eff.stop()
        except Exception:
            pass
        eff.play()

    def queue(self, filename: str, n: int = 1, step_ms: Optional[int] = None):
        if not self.enabled:
            return
        n = int(n)
        if n <= 0:
            return
        step = self._queue_step_ms if step_ms is None else int(step_ms)
        for _ in range(n):
            self._queue_delay_ms += step
            QTimer.singleShot(self._queue_delay_ms, lambda f=filename: self.play(f))
        if self._queue_delay_ms > 45_000:
            self._queue_delay_ms = 0

    def play_info(self):
        self.coin()

    def play_warn(self):
        self.pop()

    def play_error(self):
        self.err()

    def play_any_button(self):
        self.play(random.choice([SFX_COIN, SFX_JUMP, SFX_POP]))

    def play_intro(self):
        self.intro()

    def play_outro(self):
        self.outro()

    def intro(self):
        self.play(SFX_INTRO)

    def outro(self):
        self.play(SFX_OUTRO)

    def coin(self):
        self.play(SFX_COIN)

    def pop(self):
        self.play(SFX_POP)

    def err(self):
        self.play(SFX_ERROR)


GLOBAL_SFX: Optional[SoundBank] = None


class GlobalButtonFxFilter(QObject):
    def __init__(self, sfx_getter: Callable[[], Optional["SoundBank"]]):
        super().__init__()
        self._get_sfx = sfx_getter

    def eventFilter(self, obj, event):
        try:
            if isinstance(obj, QAbstractButton) and event.type() == event.Type.MouseButtonPress:
                if not isinstance(obj, AnimatedPushButton):
                    sfx = self._get_sfx()
                    if sfx is not None:
                        sfx.play_any_button()
                    RUBBER.press(obj)
        except Exception:
            pass
        return super().eventFilter(obj, event)


class AnimatedPushButton(QPushButton):
    """
    Jemné “platformer” micro-interakce:
    - hover: světelný halo,
    - press: krátký bounce.
    """

    def __init__(self, *args, sfx: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 140))
        self.setGraphicsEffect(self._shadow)
        self._halo_anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._halo_anim.setDuration(160)
        self._halo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sfx = sfx

    def enterEvent(self, event: QEnterEvent):
        self._halo_anim.stop()
        self._halo_anim.setStartValue(self._shadow.blurRadius())
        self._halo_anim.setEndValue(28)
        self._halo_anim.start()
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self._halo_anim.stop()
        self._halo_anim.setStartValue(self._shadow.blurRadius())
        self._halo_anim.setEndValue(18)
        self._halo_anim.start()
        return super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._sfx:
                self._sfx()
            RUBBER.press(self)
        return super().mousePressEvent(event)


class Toast(QWidget):
    def __init__(self, parent: QWidget, text: str, kind: str):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.ToolTip, True)
        self.setStyleSheet("background: transparent;")

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0.0)

        self.card = QFrame(self)
        self.card.setObjectName("ToastCard")
        bg = SURFACE_COLOR
        br = "#2B3563"
        accent = ACCENT_COLOR
        if kind == "ok":
            accent = MINT_COLOR
        elif kind == "warn":
            accent = ACCENT_COLOR
        elif kind == "err":
            accent = "#FF6B6B"
        self.card.setStyleSheet(
            f"""
            QFrame#ToastCard {{
                background-color: {bg};
                border: 1px solid {br};
                border-left: 6px solid {accent};
                border-radius: {RADIUS}px;
            }}
            """
        )
        sh = QGraphicsDropShadowEffect(self.card)
        sh.setBlurRadius(26)
        sh.setOffset(0, 10)
        sh.setColor(QColor(0, 0, 0, 160))
        self.card.setGraphicsEffect(sh)

        lay = QHBoxLayout(self.card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{TEXT_COLOR}; font-weight: 750;")
        lay.addWidget(lbl)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        self.anim_in = QPropertyAnimation(self._fx, b"opacity")
        self.anim_in.setDuration(160)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_out = QPropertyAnimation(self._fx, b"opacity")
        self.anim_out.setDuration(220)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim_out.finished.connect(self.close)

        self.slide = QPropertyAnimation(self, b"pos")
        self.slide.setDuration(220)
        self.slide.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_at(self, p: QPoint):
        self.adjustSize()
        self.move(p)
        start = QPoint(p.x() + 16, p.y())
        self.move(start)
        self.show()
        self.slide.stop()
        self.slide.setStartValue(start)
        self.slide.setEndValue(p)
        self.slide.start()
        self.anim_in.start()

    def dismiss_later(self, ms: int):
        QTimer.singleShot(ms, self._dismiss)

    def _dismiss(self):
        self.anim_out.start()


class ToastLayer(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self._toasts: List[Toast] = []
        self._pad = 16

    def resizeEvent(self, event):
        self._reflow()
        return super().resizeEvent(event)

    def push(self, text: str, kind: str = "ok", ttl_ms: int = 2400):
        t = Toast(self, text, kind)
        self._toasts.insert(0, t)
        self._reflow()
        t.dismiss_later(ttl_ms)
        return t

    def _reflow(self):
        x_right = max(0, self.width() - self._pad)
        y = self._pad + TOPBAR_H + 10
        alive: List[Toast] = []
        for t in self._toasts:
            if t.isVisible() or not t.isHidden():
                alive.append(t)
        self._toasts = alive

        for i, t in enumerate(self._toasts):
            t.adjustSize()
            w = t.width()
            pos = QPoint(x_right - w, y + i * (t.height() + 10))
            if not t.isVisible():
                t.show_at(pos)
            else:
                t.move(pos)
# =====================
# POMOCNÉ FUNKCE
# =====================
def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024.0
def format_seconds(sec: float) -> str:
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"
def safe_move_file(src: str, dst: str) -> None:
    """Bezpečný přesun (funguje i napříč disky)."""
    try:
        shutil.move(src, dst)
    except Exception:
        logger.warning("shutil.move selhal, zkouším copy+delete: %s -> %s", src, dst)
        try:
            shutil.copy2(src, dst)
            os.remove(src)
        except Exception as e:
            logger.error("Fallback copy+delete selhal pro %s -> %s: %s", src, dst, e)
            raise
def is_system_like_path(path: str) -> bool:
    low = os.path.abspath(path).lower()
    return any(k in low for k in SYSTEM_PATH_KEYWORDS)
def iter_image_paths(
    roots: List[str],
    ignore_system: bool,
    on_progress: Optional[Callable[[int, int], bool]] = None,
) -> List[str]:
    paths: List[str] = []
    stop_scan = False
    last_update = time.time()
    dir_count = 0
    for root in roots:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dir_count += 1
            # odfiltrovat zjevne systemove adresare
            dirnames[:] = [d for d in dirnames if d not in ["$RECYCLE.BIN", "System Volume Information"]]
            if ignore_system and is_system_like_path(dirpath):
                dirnames[:] = []
                continue
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTS:
                    full = os.path.join(dirpath, name)
                    paths.append(full)
                if on_progress and (time.time() - last_update) > 0.1:
                    if on_progress(len(paths), dir_count) is False:
                        stop_scan = True
                        break
                    last_update = time.time()
            if stop_scan:
                break
            if on_progress and (time.time() - last_update) > 0.1:
                if on_progress(len(paths), dir_count) is False:
                    stop_scan = True
                    break
                last_update = time.time()
        if stop_scan:
            break
    return paths
def perceptual_hash(path: str, hash_size: int = 8) -> Optional[int]:
    """Jednoduchy prumerny hash pomoci Pillow."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                if img.width * img.height > MAX_HASH_PIXELS:
                    return None
                img = img.convert("L")
                img = img.resize((hash_size, hash_size), Image.Resampling.LANCZOS)
                if hasattr(img, "get_flattened_data"):
                    pixels = list(img.get_flattened_data())
                else:
                    pixels = list(img.getdata())
                avg = sum(pixels) / len(pixels)
                bits = "".join("1" if p > avg else "0" for p in pixels)
                return int(bits, 2)
    except UnidentifiedImageError:
        logger.warning("Soubor není rozpoznán jako obrázek pro hash: %s", path)
    except Image.DecompressionBombWarning:
        logger.warning("Obrázek je při hashování přeskočen (příliš velký): %s", path)
    except Exception as e:
        logger.warning("Chyba při výpočtu hashe pro %s: %s", path, e)
    return None
# =====================
# DATOVÉ STRUKTURY
# =====================
@dataclass
class ImageRecord:
    id: int
    path: str
    size: int
    bucket: str = "MAIN"  # MAIN, T1..T4, TRASH, DUPLICITA
    width: Optional[int] = None
    height: Optional[int] = None
@dataclass
class Bucket:
    code: str
    alias: str
    path: str = ""
    count: int = 0
    size_total: int = 0
# =====================
# WORKER PRO NÁHLEDY
# =====================
class ThumbWorkerSignals(QObject):
    finished = pyqtSignal(int, QImage)
class ThumbWorker(QRunnable):
    def __init__(self, rec_id: int, path: str, max_size: Tuple[int, int] = (96, 72)):
        super().__init__()
        self.rec_id = rec_id
        self.path = path
        self.max_size = max_size
        self.signals = ThumbWorkerSignals()
    @pyqtSlot()
    def run(self):
        try:
            if not os.path.exists(self.path):
                return
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                pixels = int(size.width()) * int(size.height())
                if pixels > MAX_THUMB_PIXELS:
                    return
            if not reader.canRead():
                return
            reader.setScaledSize(QSize(self.max_size[0], self.max_size[1]))
            image = reader.read()
            if image.isNull():
                return
            self.signals.finished.emit(self.rec_id, image)
        except Exception as e:
            logger.warning("ThumbWorker chyba pro %s: %s", self.path, e)
# =====================
# PROGRESS DIALOG
# =====================
class DagmarProgress(QProgressDialog):
    def __init__(self, text: str, parent: QWidget, maximum: int):
        super().__init__("", "Zrušit", 0, maximum, parent)
        self.setWindowTitle("KájovoPhotoSelector – průběh")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setStyleSheet(PROGRESS_QSS + DIALOG_FRAME_QSS)
        apply_dialog_sizing(self, extra_h=140)
        self.base_text = text
        self.start_time = time.time()
        self.last_update = self.start_time
        self.setLabelText(text)
        self.setValue(0)
    def update(self, current: int):
        if self.maximum() <= 0:
            self.setMaximum(1)
        if current > self.maximum():
            current = self.maximum()
        now = time.time()
        elapsed = now - self.start_time
        if current > 0:
            total_est = (elapsed / current) * self.maximum()
            remaining = total_est - elapsed
        else:
            remaining = 0
        percent = (current / self.maximum()) * 100 if self.maximum() > 0 else 0.0
        self.setLabelText(
            f"{self.base_text}\n"
            f"Hotovo: {current}/{self.maximum()} ({percent:.1f} %)\n"
            f"Uteklo: {format_seconds(elapsed)}, zbývá ~{format_seconds(max(0, remaining))}"
        )
        self.setValue(current)
        QApplication.processEvents()
# =====================
# DIALOG PRO NASTAVENÍ SKENU
# =====================
class ScanOptionsDialog(QDialog):
    def __init__(self, parent: QWidget, last_min_kb: int, last_max_kb: int, last_ignore_system: bool):
        super().__init__(parent)
        self.setWindowTitle("Nastavení skenování")
        self.setModal(True)
        self.setStyleSheet(DIALOG_FRAME_QSS)
        apply_dialog_sizing(self, extra_h=120)
        layout = QVBoxLayout(self)
        row1 = QHBoxLayout()
        lbl_min = QLabel("Min. velikost (kB, 0 = bez limitu):")
        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 1024 * 1024)
        self.spin_min.setValue(last_min_kb)
        row1.addWidget(lbl_min)
        row1.addWidget(self.spin_min)
        row2 = QHBoxLayout()
        lbl_max = QLabel("Max. velikost (kB, 0 = bez limitu):")
        self.spin_max = QSpinBox()
        self.spin_max.setRange(0, 1024 * 1024)
        self.spin_max.setValue(last_max_kb)
        row2.addWidget(lbl_max)
        row2.addWidget(self.spin_max)
        self.chk_ignore_system = QCheckBox("Ignorovat systémové / instalační obrázky")
        self.chk_ignore_system.setChecked(last_ignore_system)
        self.chk_ignore_system.setStyleSheet("color:white;background-color:#151821;padding:4px;")
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.chk_ignore_system)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
    def get_values(self) -> Tuple[int, int, bool]:
        return self.spin_min.value(), self.spin_max.value(), self.chk_ignore_system.isChecked()
# =====================
# DIALOG PRO DUPLICITY
# =====================
class DraggableListWidget(QListWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._rubber_band: Optional[QRubberBand] = None
        self._rubber_origin: Optional[QPoint] = None
        self._rubber_selecting: bool = False
        self._bg_enabled = True
        self._bg_source = resource_path(MAIN_BG_IMAGE)
        self._bg_cache_key = None
    def startDrag(self, supportedActions):
        if self.main_window.current_view != "MAIN":
            return
        items = self.selectedItems()
        if not items:
            return
        ids = []
        for item in items:
            rec_id = item.data(Qt.ItemDataRole.UserRole)
            if rec_id is not None:
                ids.append(str(rec_id))
        if not ids:
            return
        mime = QMimeData()
        mime.setData("application/x-kaja-ids", ",".join(ids).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def mousePressEvent(self, event: QMouseEvent):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and (event.modifiers() & Qt.KeyboardModifier.ControlModifier or self.itemAt(event.pos()) is None)
        ):
            self._rubber_origin = event.position().toPoint()
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self._rubber_band.setGeometry(QRect(self._rubber_origin, QSize(1, 1)))
            self._rubber_band.show()
            self._rubber_selecting = True
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._rubber_selecting and self._rubber_band and (event.buttons() & Qt.MouseButton.LeftButton):
            current = event.position().toPoint()
            rect = QRect(self._rubber_origin, current).normalized()
            self._rubber_band.setGeometry(rect)
            # označit položky, jejichž rect se překrývá
            for i in range(self.count()):
                item = self.item(i)
                if item is None:
                    continue
                if self.visualItemRect(item).intersects(rect):
                    item.setSelected(True)
                else:
                    item.setSelected(False)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._rubber_selecting and self._rubber_band:
            self._rubber_band.hide()
            self._rubber_selecting = False
            return
        super().mouseReleaseEvent(event)

    def set_main_background_enabled(self, enabled: bool):
        self._bg_enabled = enabled
        self._update_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_background()

    def _clear_background(self):
        pal = self.viewport().palette()
        pal.setBrush(QPalette.ColorRole.Base, QBrush())
        self.viewport().setPalette(pal)
        self.viewport().setAutoFillBackground(False)
        self.viewport().update()

    def _update_background(self):
        if not self._bg_enabled:
            self._clear_background()
            return
        path = self._bg_source
        if not path or not os.path.exists(path):
            self._clear_background()
            return
        size = self.viewport().size()
        if size.width() <= 0 or size.height() <= 0:
            return
        key = (path, size.width(), size.height())
        if self._bg_cache_key == key:
            return
        pm = QPixmap(path)
        if pm.isNull():
            self._clear_background()
            return
        scaled = pm.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        result = QPixmap(size)
        result.fill(QColor(0, 0, 0))
        painter = QPainter(result)
        x = (size.width() - scaled.width()) // 2
        y = (size.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.fillRect(result.rect(), QColor(8, 12, 22, 160))
        painter.end()
        pal = self.viewport().palette()
        pal.setBrush(QPalette.ColorRole.Base, QBrush(result))
        self.viewport().setPalette(pal)
        self.viewport().setAutoFillBackground(True)
        self._bg_cache_key = key
class BucketDropGroupBox(QGroupBox):
    def __init__(self, code: str, main_window, parent=None):
        super().__init__(parent)
        self.code = code
        self.main_window = main_window
        self._base_stylesheet = ""
        self.setAcceptDrops(True)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 8)
        self._shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(self._shadow)
        self._halo_anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._halo_anim.setDuration(160)
        self._halo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event: QEnterEvent):
        self._halo_anim.stop()
        self._halo_anim.setStartValue(self._shadow.blurRadius())
        self._halo_anim.setEndValue(26)
        self._halo_anim.start()
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self._halo_anim.stop()
        self._halo_anim.setStartValue(self._shadow.blurRadius())
        self._halo_anim.setEndValue(18)
        self._halo_anim.start()
        return super().leaveEvent(event)

    def _apply_drop_style(self, active: bool):
        if not self._base_stylesheet:
            self._base_stylesheet = self.styleSheet()
        if active:
            self.setStyleSheet(
                self._base_stylesheet
                + f"\nQGroupBox {{ border: 2px solid {ACCENT_COLOR}; background-color: #1a2230; }}"
            )
        else:
            self.setStyleSheet(self._base_stylesheet)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-kaja-ids"):
            self._apply_drop_style(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._apply_drop_style(False)
        event.accept()

    def dropEvent(self, event):
        self._apply_drop_style(False)
        if not event.mimeData().hasFormat("application/x-kaja-ids"):
            event.ignore()
            return
        data = event.mimeData().data("application/x-kaja-ids").data()
        try:
            ids = [int(x) for x in data.decode("utf-8").split(",") if x.strip()]
        except Exception:
            ids = []
        if ids:
            self.main_window.assign_ids_to_bucket(self.code, ids)
        event.acceptProposedAction()


class ExitDissolveOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, pixmap: QPixmap, geo: QRect, duration_ms: int):
        super().__init__(None)
        if pixmap.isNull() or pixmap.width() <= 1 or pixmap.height() <= 1:
            self._pixmap = QPixmap(1, 1)
            self._pixmap.fill(QColor(0, 0, 0))
        else:
            img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            solid = QImage(img.size(), QImage.Format.Format_ARGB32)
            solid.fill(QColor(0, 0, 0))
            painter = QPainter(solid)
            painter.drawImage(0, 0, img)
            painter.end()
            self._pixmap = QPixmap.fromImage(solid)
        self._geo = geo
        self._duration_ms = max(400, int(duration_ms))
        self._interval_ms = 30
        self._tiles: List[QRect] = []
        self._tiles_per_tick = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(self._geo)

        self._build_tiles()

    def _build_tiles(self):
        w = max(1, self._pixmap.width())
        h = max(1, self._pixmap.height())
        tile = max(28, min(64, min(w, h) // 18))
        cols = max(1, (w + tile - 1) // tile)
        rows = max(1, (h + tile - 1) // tile)
        tiles: List[QRect] = []
        for y in range(rows):
            for x in range(cols):
                tiles.append(QRect(x * tile, y * tile, tile, tile))
        random.shuffle(tiles)
        self._tiles = tiles
        steps = max(1, self._duration_ms // self._interval_ms)
        self._tiles_per_tick = max(1, (len(self._tiles) + steps - 1) // steps)

    def start(self):
        self._timer.start(self._interval_ms)

    def _tick(self):
        if not self._tiles:
            self._timer.stop()
            self.close()
            self.finished.emit()
            return
        count = min(self._tiles_per_tick, len(self._tiles))
        painter = QPainter(self._pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        for _ in range(count):
            rect = self._tiles.pop()
            painter.fillRect(rect, Qt.GlobalColor.transparent)
        painter.end()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.code in ["T1", "T2", "T3", "T4"]:
                self.main_window.rename_bucket(self.code)
        super().mouseDoubleClickEvent(event)


class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
class DuplicateGroupDialog(QDialog):
    """
    Zobrazí jednu skupinu duplicit s možností:
    - označit položky k zachování,
    - přeskočit,
    - smazat všechny (do virtuálního Koše),
    - auto (Petře, udělej to za mě),
    - storno.
    """
    def __init__(self, parent: QWidget, group_index: int, total_groups: int, records: List[ImageRecord]):
        super().__init__(parent)
        self.setWindowTitle("Nalezené duplicity")
        self.setModal(True)
        self.setStyleSheet(DIALOG_FRAME_QSS)
        apply_dialog_sizing(self, extra_h=160)
        self.records = records
        self.selected_indices: List[int] = []
        layout = QVBoxLayout(self)
        header = QLabel(f"{group_index + 1}. redundance z {total_groups}")
        header.setStyleSheet(f"color:{ACCENT_COLOR};font-weight:bold;")
        layout.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        # Heuristika pro kvalitu: větší velikost souboru
        best_index = 0
        if records:
            best_index = max(range(len(records)), key=lambda i: records[i].size)
        self.lbls: List[ClickableLabel] = []
        self.selected: List[bool] = []
        # připravit šachovnicové pozadí pro miniatury
        checker = QPixmap(8, 8)
        checker.fill(QColor("#555555"))
        painter = QPainter(checker)
        painter.fillRect(0, 0, 4, 4, QColor("#777777"))
        painter.fillRect(4, 4, 4, 4, QColor("#777777"))
        painter.end()
        checker_brush = QBrush(checker)
        for i, rec in enumerate(records):
            vbox = QVBoxLayout()
            img_label = ClickableLabel()
            img_label.setFixedSize(96, 72)
            img_label.setFrameShape(QFrame.Shape.Box)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_label.setAutoFillBackground(True)
            pal = img_label.palette()
            pal.setBrush(QPalette.ColorRole.Window, checker_brush)
            img_label.setPalette(pal)
            img_label.setStyleSheet("border: 2px solid transparent;")
            base = os.path.basename(rec.path)
            d = os.path.dirname(rec.path)
            if len(base) > 20:
                base_disp = "…" + base[-19:]
            else:
                base_disp = base
            if len(d) > 24:
                d_disp = "…" + d[-23:]
            else:
                d_disp = d
            info = QLabel(
                f"{base_disp}\n"
                f"{d_disp}\n"
                f"{human_size(rec.size)}"
            )
            info.setWordWrap(True)
            self.lbls.append(img_label)
            self.selected.append(False)
            def make_handler(index: int):
                def handler():
                    self._toggle_selection(index)
                return handler
            img_label.clicked.connect(make_handler(i))
            vbox.addWidget(img_label)
            vbox.addWidget(info)
            grid.addLayout(vbox, i // 3, i % 3)
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        btns_layout = QHBoxLayout()
        self.btn_keep = AnimatedPushButton("Kájo, nech označenou")
        self.btn_skip = AnimatedPushButton("Kájo, přeskoč to")
        self.btn_trash = AnimatedPushButton("Kájo, vyhoď všechny")
        self.btn_auto = AnimatedPushButton("Kájo, vyřeš to za mě…")
        self.btn_cancel = AnimatedPushButton("Kájo, stop")
        self.btn_keep.setStyleSheet(BUTTON_PRIMARY_QSS)
        self.btn_skip.setStyleSheet(BUTTON_SURFACE_QSS)
        self.btn_trash.setStyleSheet(BUTTON_DANGER_QSS)
        self.btn_auto.setStyleSheet(BUTTON_GOLD_QSS)
        self.btn_cancel.setStyleSheet(BUTTON_SURFACE_QSS)
        for b in [self.btn_keep, self.btn_skip, self.btn_trash, self.btn_auto, self.btn_cancel]:
            btns_layout.addWidget(b)
        layout.addLayout(btns_layout)
        self.choice: str = "skip"  # keep_marked, skip, trash_all, auto_all, abort
        self.btn_keep.clicked.connect(self._on_keep)
        self.btn_skip.clicked.connect(self._on_skip)
        self.btn_trash.clicked.connect(self._on_trash)
        self.btn_auto.clicked.connect(self._on_auto)
        self.btn_cancel.clicked.connect(self._on_cancel)
        # miniatury v tomto dialogu – jednoduché, synchronní, jen pár souborů
        for i, rec in enumerate(records):
            if os.path.exists(rec.path):
                reader = QImageReader(rec.path)
                reader.setAutoTransform(True)
                reader.setScaledSize(QSize(96, 72))
                img = reader.read()
                if not img.isNull():
                    pm = QPixmap.fromImage(img)
                    self.lbls[i].setPixmap(pm.scaled(96, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    self.lbls[i].setToolTip(f"{rec.path}\n{human_size(rec.size)}")
                    self.lbls[i].setMouseTracking(True)
        if records:
            self._toggle_selection(best_index, force_state=True, state=True)
    def _toggle_selection(self, index: int, force_state: bool = False, state: bool = False):
        if index < 0 or index >= len(self.lbls):
            return
        if force_state:
            new_state = state
        else:
            new_state = not self.selected[index]
        if new_state:
            for i in range(len(self.selected)):
                self.selected[i] = (i == index)
        else:
            self.selected[index] = False
        for i, lbl in enumerate(self.lbls):
            if self.selected[i]:
                lbl.setStyleSheet(f"border:2px solid {ACCENT_COLOR};")
            else:
                lbl.setStyleSheet("border:2px solid transparent;")
    def _on_keep(self):
        self.choice = "keep_marked"
        self.selected_indices = [i for i, sel in enumerate(self.selected) if sel]
        self.accept()
    def _on_skip(self):
        self.choice = "skip"
        self.accept()
    def _on_trash(self):
        self.choice = "trash_all"
        self.accept()
    def _on_auto(self):
        self.choice = "auto_all"
        self.accept()
    def _on_cancel(self):
        self.choice = "abort"
        self.reject()
# =====================
# HLAVNÍ OKNO
# =====================
class MainWindow(QMainWindow):
    def __init__(self, sfx: Optional[SoundBank] = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 800)
        self.sfx = sfx if sfx is not None else SoundBank()
        self.toast_layer: Optional[ToastLayer] = None
        self._outro_done = False
        self._exit_in_progress = False
        self._exit_overlay: Optional[ExitDissolveOverlay] = None
        self._exit_sfx: Optional["QSoundEffect"] = None
        self.threadpool = QThreadPool()
        logger.info("KájovoPhotoSelector – threadpool velikost: %d", self.threadpool.maxThreadCount())
        self.images: List[ImageRecord] = []
        self.image_by_id: Dict[int, ImageRecord] = {}
        self.item_by_id: Dict[int, QListWidgetItem] = {}
        self.thumb_cache: Dict[int, QPixmap] = {}
        self.next_id: int = 1
        self.current_view: str = "MAIN"  # MAIN nebo kód bucketu
        self.session_roots: List[str] = []
        self.session_dirty: bool = False
        self.last_min_kb: int = 0
        self.last_max_kb: int = 0
        self.last_ignore_system: bool = True
        # bucket kód -> Bucket
        self.buckets: Dict[str, Bucket] = {
            "T1": Bucket("T1", "Kájova hromádka 1"),
            "T2": Bucket("T2", "Kájova hromádka 2"),
            "T3": Bucket("T3", "Kájova hromádka 3"),
            "T4": Bucket("T4", "Kájova hromádka 4"),
            "TRASH": Bucket("TRASH", "Kájův koš"),
            "DUPLICITA": Bucket("DUPLICITA", "Kájovi dvojníci"),
        }
        # bucket kód -> widgety
        self.bucket_widgets: Dict[str, Dict[str, QWidget]] = {}
        self._build_ui()
        self.toast_layer = ToastLayer(self.centralWidget())
        self.toast_layer.setGeometry(self.centralWidget().rect())
        self.toast_layer.raise_()
        # “Kiosk” vzhled bez okenních ovládacích prvků – maximalizace na primární monitor
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

    def _maximize_on_primary(self):
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            self.showMaximized()
            return
        geo = scr.availableGeometry()
        self.setGeometry(geo)
        self.showMaximized()
        if self.toast_layer is not None and self.centralWidget() is not None:
            self.toast_layer.setGeometry(self.centralWidget().rect())
            self.toast_layer.raise_()

    def resizeEvent(self, event):
        if self.toast_layer is not None and self.centralWidget() is not None:
            self.toast_layer.setGeometry(self.centralWidget().rect())
            self.toast_layer.raise_()
        return super().resizeEvent(event)

    def keyPressEvent(self, event):
        # rychlé ukončení (když není titlebar)
        if event.key() == Qt.Key.Key_Escape:
            self.on_exit()
            return
        if event.key() == Qt.Key.Key_M:
            self.sfx.enabled = not self.sfx.enabled
            state = "ON" if self.sfx.enabled else "OFF"
            self.toast(f"Zvuky: {state}", "warn", 1600)
            if hasattr(self, "btn_sfx"):
                self.btn_sfx.setText(f"Zvuky: {state}")
            return
        super().keyPressEvent(event)

    # Frameless: jednoduché tažení okna (klik v horní liště)
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._dragging = event.position().y() <= (TOPBAR_H + 20)
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if getattr(self, "_dragging", False) and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - getattr(self, "_drag_pos", event.globalPosition().toPoint())
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        return super().mouseReleaseEvent(event)

    def toast(self, text: str, kind: str = "ok", ttl_ms: int = 2400):
        if self.toast_layer is None:
            return
        self.toast_layer.push(text, kind=kind, ttl_ms=ttl_ms)

    def _coin_per_file(self, n: int):
        self.sfx.queue(SFX_COIN, n=n)

    # ---------------- “TICHÉ” MESSAGEBOXY (bez systémových zvuků) ----------------
    def _kajo_box(
        self,
        title: str,
        text: str,
        kind: str = "info",  # info | warn | err
        buttons: Optional[List[Tuple[str, QMessageBox.ButtonRole]]] = None,
        default_index: int = 0,
        style_buttons: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        QMessageBox na Windows typicky spouští systémový zvuk podle ikony.
        Aby byl program konzistentně “WAV only”, vždy používáme NoIcon a pouštíme vlastní SFX.
        Vrací text tlačítka, na které uživatel klikl (nebo None).
        """
        if kind == "err":
            self.sfx.play_error()
        elif kind == "warn":
            self.sfx.play_warn()
        else:
            self.sfx.play_info()

        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStyleSheet(DIALOG_FRAME_QSS)
        apply_dialog_sizing(msg)
        # klíč: NoIcon => žádný Windows “ding”
        msg.setIcon(QMessageBox.Icon.NoIcon)

        created: List[QPushButton] = []
        if buttons:
            for caption, role in buttons:
                b = msg.addButton(caption, role)
                created.append(b)
            if 0 <= default_index < len(created):
                msg.setDefaultButton(created[default_index])
        else:
            msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)

        # volitelné styly tlačítek (musí být PŘED exec, aby byly vidět)
        if style_buttons:
            # pokud jsme vytvořili vlastní tlačítka, nastylujeme je
            if created:
                for b in created:
                    cap = b.text()
                    if cap in style_buttons:
                        b.setStyleSheet(style_buttons[cap])
            else:
                # default "OK" tlačítko
                okb = msg.button(QMessageBox.StandardButton.Ok)
                if okb is not None and "OK" in style_buttons:
                    okb.setStyleSheet(style_buttons["OK"])

        msg.exec()

        clicked = msg.clickedButton()
        if clicked is None:
            return None
        try:
            return clicked.text()
        except Exception:
            return None

    def _toggle_sfx(self):
        self.sfx.enabled = not self.sfx.enabled
        state = "ON" if self.sfx.enabled else "OFF"
        if hasattr(self, "btn_sfx"):
            self.btn_sfx.setText(f"Zvuky: {state}")
        self.toast(f"Zvuky: {state} (M)", "warn", 1600)
    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        # ===== TOP BAR (brand + akce) =====
        top_frame = QFrame()
        top_frame.setObjectName("TopBar")
        top_frame.setFixedHeight(TOPBAR_H)
        top_frame.setStyleSheet(
            f"""
            QFrame#TopBar {{
                background-color: {SURFACE_COLOR};
                border: 1px solid #25305A;
                border-radius: {RADIUS}px;
            }}
            """
        )
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(14, 10, 14, 10)
        top_layout.setSpacing(10)

        # Logo + název
        self.lbl_brand_logo = QLabel()
        self.lbl_brand_logo.setFixedSize(44, 44)
        self.lbl_brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = load_logo_pixmap(max_w=200)
        if pm is not None:
            self.lbl_brand_logo.setPixmap(
                pm.scaled(
                    44,
                    44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.lbl_brand_logo.setText("K")
            self.lbl_brand_logo.setStyleSheet(
                f"color:{ACCENT_COLOR}; font-weight: 900; font-size: 20px;"
            )

        self.lbl_brand_title = QLabel(APP_NAME)
        self.lbl_brand_title.setStyleSheet(
            f"color:{TEXT_COLOR}; font-size: 18px; font-weight: 900;"
        )
        self.lbl_brand_sub = QLabel("Třídění fotek v Kájově světě")
        self.lbl_brand_sub.setStyleSheet(
            f"color:{SUBTEXT_COLOR}; font-size: 12px; font-weight: 600;"
        )
        brand_col = QVBoxLayout()
        brand_col.setContentsMargins(0, 0, 0, 0)
        brand_col.setSpacing(0)
        brand_col.addWidget(self.lbl_brand_title)
        brand_col.addWidget(self.lbl_brand_sub)

        top_layout.addWidget(self.lbl_brand_logo)
        top_layout.addLayout(brand_col)
        top_layout.addStretch(1)

        # Akční tlačítka (funkce stejné, jen “Kája” naming)
        self.btn_kajo_stopa = AnimatedPushButton("Kájo, ukaž mi fotky", sfx=lambda: self.sfx.play(SFX_JUMP))
        self.btn_dupes = AnimatedPushButton("Kájo, najdi dvojníky", sfx=lambda: self.sfx.play(SFX_COIN))
        self.btn_run = AnimatedPushButton("Kájo, proveď to", sfx=lambda: self.sfx.play(SFX_POP))
        self.btn_save = AnimatedPushButton("Kájo, zapamatuj si to", sfx=lambda: self.sfx.play(SFX_COIN))
        self.btn_load = AnimatedPushButton("Kájo, vzpomeň si", sfx=lambda: self.sfx.play(SFX_COIN))
        self.btn_new = AnimatedPushButton("Kájo, začneme nanovo", sfx=lambda: self.sfx.play(SFX_POP))
        self.btn_exit = AnimatedPushButton("Kájo, končíme", sfx=lambda: self.sfx.play(SFX_POP))

        self.btn_kajo_stopa.setStyleSheet(BUTTON_PRIMARY_QSS)
        self.btn_dupes.setStyleSheet(BUTTON_GOLD_QSS)
        self.btn_run.setStyleSheet(BUTTON_DANGER_QSS)
        self.btn_save.setStyleSheet(BUTTON_SURFACE_QSS)
        self.btn_load.setStyleSheet(BUTTON_SURFACE_QSS)
        self.btn_new.setStyleSheet(BUTTON_DANGER_QSS)
        self.btn_exit.setStyleSheet(BUTTON_PRIMARY_QSS)

        for b in [
            self.btn_kajo_stopa,
            self.btn_dupes,
            self.btn_run,
            self.btn_save,
            self.btn_load,
            self.btn_new,
            self.btn_exit,
        ]:
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            top_layout.addWidget(b)

        self.btn_sfx = AnimatedPushButton("Zvuky: ON", sfx=lambda: self.sfx.play(SFX_COIN))
        self.btn_sfx.setStyleSheet(BUTTON_SURFACE_QSS)
        self.btn_sfx.setFixedWidth(120)
        self.btn_sfx.clicked.connect(self._toggle_sfx)
        top_layout.addWidget(self.btn_sfx)

        main_layout.addWidget(top_frame)

        # ===== HEADER nad seznamem =====
        # Nad seznamem – informace o aktuálním pohledu
        header_layout = QHBoxLayout()
        self.btn_back_to_main = AnimatedPushButton(
            "Kájo, zpátky domů", sfx=lambda: self.sfx.play(SFX_JUMP)
        )
        self.btn_back_to_main.setStyleSheet(BUTTON_PRIMARY_QSS)
        self.btn_back_to_main.setVisible(False)
        header_layout.addWidget(self.btn_back_to_main)
        self.lbl_view_title = QLabel("Pohled: Kájův hlavní svět")
        self.lbl_view_title.setStyleSheet(
            f"color:{ACCENT_COLOR}; font-size: 14pt; font-weight: 900;"
        )
        header_layout.addWidget(self.lbl_view_title)
        header_layout.addStretch()
        self.lbl_view_stats = QLabel("Soubory: 0 (0 B), vybráno: 0 (0 B)")
        self.lbl_view_stats.setStyleSheet(f"color:{SUBTEXT_COLOR}; font-weight: 700;")
        header_layout.addWidget(self.lbl_view_stats)
        main_layout.addLayout(header_layout)
        # Seznam miniatur
        self.list_widget = DraggableListWidget(self)
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(96, 72))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setSpacing(6)
        self.list_widget.setGridSize(QSize(120, 120))
        self.list_widget.setWordWrap(False)
        self.list_widget.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {BG_COLOR};
            }}
            QListWidget::item {{
                border: 2px solid transparent;
                padding: 6px;
                border-radius: 10px;
            }}
            QListWidget::item:selected {{
                border: 2px solid {ACCENT_COLOR};
                background-color: rgba(255, 213, 79, 45);
            }}
            """
        )
        self.list_widget.set_main_background_enabled(True)
        main_layout.addWidget(self.list_widget, stretch=1)
        # Tlačítko pro návrat z hromádek do hlavní složky (spodní, celá šířka)
        self.btn_return_from_bucket = AnimatedPushButton(
            "Kájo, vrať označené domů", sfx=lambda: self.sfx.play(SFX_POP)
        )
        self.btn_return_from_bucket.setStyleSheet(BUTTON_DANGER_QSS)
        self.btn_return_from_bucket.setVisible(False)
        main_layout.addWidget(self.btn_return_from_bucket)
        # Spodní hromádky
        bottom_layout = QHBoxLayout()
        main_layout.addLayout(bottom_layout)
        # Vytvořit 6 sloupců
        order = ["T1", "T2", "T3", "T4", "TRASH", "DUPLICITA"]
        for code in order:
            bucket = self.buckets[code]
            column_box = QVBoxLayout()
            column_box.setSpacing(8)
            lbl_info = QLabel(f"0 souborů / 0 B")
            lbl_info.setStyleSheet(f"color:{ACCENT_COLOR}; font-weight: 900;")
            btn_assign = AnimatedPushButton(
                f"Kájo, hoď to do: {bucket.alias}",
                sfx=lambda c=code: self.sfx.play(SFX_COIN if c != "TRASH" else SFX_POP),
            )
            btn_assign.setStyleSheet(BUTTON_DANGER_QSS if code == "TRASH" else BUTTON_PRIMARY_QSS)
            lbl_path = QLabel("Cesta: (není namapováno)" if code not in ["TRASH"] else "Cesta: Kájův koš (systém)")
            lbl_path.setStyleSheet(f"color:{SUBTEXT_COLOR}; font-weight: 650;")
            lbl_path.setWordWrap(True)
            if code in ["T1", "T2", "T3", "T4", "DUPLICITA"]:
                btn_select = AnimatedPushButton("Kájo, kam to dáme?", sfx=lambda: self.sfx.play(SFX_JUMP))
                btn_select.setStyleSheet(BUTTON_SURFACE_QSS)
            else:
                btn_select = QLabel("Tady se cesta nevybírá")
                btn_select.setStyleSheet(f"color:{SUBTEXT_COLOR};")
            btn_show = AnimatedPushButton("Kájo, ukaž obsah", sfx=lambda: self.sfx.play(SFX_POP))
            btn_show.setStyleSheet(BUTTON_SURFACE_QSS)
            column_box.addWidget(lbl_info)
            column_box.addWidget(btn_assign)
            column_box.addWidget(lbl_path)
            column_box.addWidget(btn_select)
            column_box.addWidget(btn_show)
            frame = BucketDropGroupBox(code, self)
            frame.setTitle(bucket.alias.upper())
            frame.setLayout(column_box)
            frame.setStyleSheet(
                f"""
                QGroupBox {{
                    border: 1px solid #2B3563;
                    border-radius: {RADIUS}px;
                    margin-top: 6px;
                    color: {ACCENT_COLOR};
                    font-weight: 900;
                    text-transform: uppercase;
                    background-color: {SURFACE_COLOR};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }}
                """
            )
            frame._base_stylesheet = frame.styleSheet()
            bottom_layout.addWidget(frame)
            self.bucket_widgets[code] = {
                "lbl_info": lbl_info,
                "btn_assign": btn_assign,
                "lbl_path": lbl_path,
                "btn_select": btn_select,
                "btn_show": btn_show,
                "group_box": frame,
            }
            # signály
            btn_assign.clicked.connect(lambda _, c=code: self.assign_selected_to_bucket(c))
            if isinstance(btn_select, QPushButton):
                btn_select.clicked.connect(lambda _, c=code: self.select_bucket_path(c))
            btn_show.clicked.connect(lambda _, c=code: self.show_bucket_view(c))
        # Signály horního menu
        self.btn_kajo_stopa.clicked.connect(self.on_kajo_stopa)
        self.btn_dupes.clicked.connect(self.on_find_duplicates)
        self.btn_run.clicked.connect(self.on_run_apply)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_load.clicked.connect(self.on_load)
        self.btn_new.clicked.connect(self.on_new_session)
        self.btn_exit.clicked.connect(self.on_exit)
        self.btn_return_from_bucket.clicked.connect(self.on_return_selected_from_bucket)
        self.btn_back_to_main.clicked.connect(self.on_back_to_main_view)
        self.list_widget.itemSelectionChanged.connect(self.update_view_stats)
        self.update_view_header()
    # ---------------- STAV / POMOC ----------------
    def mark_dirty(self):
        self.session_dirty = True
        self.list_widget.set_main_background_enabled(self.current_view == "MAIN")
        self.update_view_stats()
    def clear_dirty(self):
        self.session_dirty = False
        self.update_view_stats()
    def reset_state(self):
        logger.info("Reset stavu aplikace.")
        self.images.clear()
        self.image_by_id.clear()
        self.item_by_id.clear()
        self.thumb_cache.clear()
        self.list_widget.clear()
        self.next_id = 1
        self.current_view = "MAIN"
        self.session_roots.clear()
        for b in self.buckets.values():
            b.count = 0
            b.size_total = 0
        for code, w in self.bucket_widgets.items():
            bucket = self.buckets[code]
            w["lbl_info"].setText(f"0 souborů / 0 B")
            if code != "TRASH":
                w["lbl_path"].setText("Cesta: (není namapováno)")
        self.clear_dirty()
        self.update_view_header()
    def prompt_unsaved(self) -> str:
        """Vrátí 'save', 'discard' nebo 'cancel'."""
        if not self.session_dirty:
            return "discard"
        msg = QMessageBox(self)
        msg.setWindowTitle("Kájo, máme neuloženo")
        self.sfx.pop()
        msg.setIcon(QMessageBox.Icon.NoIcon)
        msg.setText(
            "Máte rozpracované virtuální třídění, které není uložené.\n"
            "Chcete aktuální stav uložit?"
        )
        msg.setStyleSheet(DIALOG_FRAME_QSS)
        apply_dialog_sizing(msg, extra_h=140)
        save_btn = msg.addButton("Kájo, zapamatuj si to", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg.addButton("Kájo, zahodit", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("Kájo, stop", QMessageBox.ButtonRole.RejectRole)
        save_btn.setStyleSheet(BUTTON_GOLD_QSS)
        discard_btn.setStyleSheet(BUTTON_DANGER_QSS)
        cancel_btn.setStyleSheet(BUTTON_PRIMARY_QSS)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == save_btn:
            return "save"
        if clicked == discard_btn:
            return "discard"
        return "cancel"
    # ---------------- VIEW / HEADER ----------------
    def update_view_header(self):
        if self.current_view == "MAIN":
            self.lbl_view_title.setText("Pohled: Kájův hlavní svět")
            self.btn_return_from_bucket.setVisible(False)
            self.btn_back_to_main.setVisible(False)
        else:
            alias = self.buckets[self.current_view].alias
            self.lbl_view_title.setText(f"Pohled: {alias}")
            self.btn_return_from_bucket.setVisible(True)
            self.btn_back_to_main.setVisible(True)
        self.update_view_stats()
    def update_view_stats(self):
        if self.current_view == "MAIN":
            records = [rec for rec in self.images if rec.bucket == "MAIN"]
        else:
            records = [rec for rec in self.images if rec.bucket == self.current_view]
        total_count = len(records)
        total_size = sum(r.size for r in records)
        selected_items = self.list_widget.selectedItems()
        selected_ids = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        selected_records = [self.image_by_id[i] for i in selected_ids if i in self.image_by_id]
        sel_count = len(selected_records)
        sel_size = sum(r.size for r in selected_records)
        self.lbl_view_stats.setText(
            f"Soubory: {total_count} ({human_size(total_size)}), "
            f"vybráno: {sel_count} ({human_size(sel_size)})"
        )
    def rebuild_list(self):
        self.list_widget.clear()
        self.item_by_id.clear()
        if self.current_view == "MAIN":
            records = [rec for rec in self.images if rec.bucket == "MAIN"]
        else:
            records = [rec for rec in self.images if rec.bucket == self.current_view]
        for rec in records:
            self._add_record_to_list(rec)
    def _display_label_for_record(self, rec: ImageRecord) -> str:
        base = os.path.basename(rec.path)
        d = os.path.dirname(rec.path)
        if len(base) > 20:
            base_disp = "…" + base[-19:]
        else:
            base_disp = base
        if len(d) > 24:
            d_disp = "…" + d[-23:]
        else:
            d_disp = d
        return f"{base_disp}\n{d_disp}"
    def _add_record_to_list(self, rec: ImageRecord):
        text = self._display_label_for_record(rec)
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, rec.id)
        item.setToolTip(f"{rec.path}\n{human_size(rec.size)}")
        pm = self.thumb_cache.get(rec.id)
        if pm is None:
            # placeholder
            placeholder = QPixmap(96, 72)
            placeholder.fill(Qt.GlobalColor.darkGray)
            item.setIcon(QIcon(placeholder))
            self._start_thumb_worker(rec)
        else:
            item.setIcon(QIcon(pm))
        self.list_widget.addItem(item)
        self.item_by_id[rec.id] = item
    # ---------------- NÁHLEDY ----------------
    def _start_thumb_worker(self, rec: ImageRecord):
        if not os.path.exists(rec.path):
            return
        worker = ThumbWorker(rec.id, rec.path)
        worker.signals.finished.connect(self.on_thumb_ready)
        self.threadpool.start(worker)
    @pyqtSlot(int, QImage)
    def on_thumb_ready(self, rec_id: int, image: QImage):
        if rec_id not in self.image_by_id:
            return
        pm = QPixmap.fromImage(image)
        self.thumb_cache[rec_id] = pm
        item = self.item_by_id.get(rec_id)
        if item is not None:
            item.setIcon(QIcon(pm))
    # ---------------- BUCKETY ----------------
    def _update_bucket_stats(self, code: str):
        bucket = self.buckets[code]
        w = self.bucket_widgets[code]
        w["lbl_info"].setText(
            f"{bucket.count} souborů / {human_size(bucket.size_total)}"
        )
    def _set_record_bucket(self, rec: ImageRecord, new_bucket: str):
        old_bucket = rec.bucket
        if old_bucket == new_bucket:
            return
        # odpsat z původního bucketu
        if old_bucket != "MAIN":
            b_old = self.buckets.get(old_bucket)
            if b_old:
                b_old.count = max(0, b_old.count - 1)
                b_old.size_total = max(0, b_old.size_total - rec.size)
                self._update_bucket_stats(old_bucket)
        # připsat do nového
        rec.bucket = new_bucket
        if new_bucket != "MAIN":
            b_new = self.buckets.get(new_bucket)
            if b_new:
                b_new.count += 1
                b_new.size_total += rec.size
                self._update_bucket_stats(new_bucket)
    def assign_ids_to_bucket(self, code: str, ids: List[int]):
        if code not in self.buckets:
            return
        if self.current_view != "MAIN":
            return
        updated = 0
        for rec_id in ids:
            rec = self.image_by_id.get(rec_id)
            if not rec:
                continue
            if rec.bucket != "MAIN":
                continue
            self._set_record_bucket(rec, code)
            updated += 1
        if updated > 0:
            self.mark_dirty()
            self.rebuild_list()
            self.update_view_header()
            try:
                self._coin_per_file(updated)
            except Exception:
                pass
    def rename_bucket(self, code: str):
        if code not in ["T1", "T2", "T3", "T4"]:
            return
        bucket = self.buckets.get(code)
        if not bucket:
            return
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Kájo, jak se to bude jmenovat?")
        dlg.setLabelText("Nový název hromádky:")
        dlg.setTextEchoMode(QLineEdit.EchoMode.Normal)
        dlg.setTextValue(bucket.alias)
        dlg.setStyleSheet(DIALOG_FRAME_QSS)
        apply_dialog_sizing(dlg, extra_h=140)
        try:
            self.sfx.pop()
        except Exception:
            pass
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        if not ok:
            return
        new_name = dlg.textValue().strip()
        if not new_name:
            return
        bucket.alias = new_name
        w = self.bucket_widgets.get(code)
        if w:
            w["group_box"].setTitle(new_name.upper())
            w["btn_assign"].setText(f"Kájo, hoď to do: {new_name}")
        if self.current_view == code:
            self.update_view_header()

    def assign_selected_to_bucket(self, code: str):
        if self.current_view != "MAIN":
            self._kajo_box(
                "Kájo, přesun nejde",
                "Přesun do hromádek je možný pouze z HLAVNÍ VIRTUÁLNÍ SLOŽKY.",
                kind="warn",
            )
            return
        if code not in self.buckets:
            return
        items = self.list_widget.selectedItems()
        if not items:
            return
        recs: List[ImageRecord] = []
        for it in items:
            rec_id = it.data(Qt.ItemDataRole.UserRole)
            if rec_id in self.image_by_id:
                recs.append(self.image_by_id[rec_id])
        if not recs:
            return
        moved = 0
        for rec in recs:
            if rec.bucket == "MAIN":
                self._set_record_bucket(rec, code)
                moved += 1
        self.mark_dirty()
        self.rebuild_list()
        if moved > 0:
            try:
                self._coin_per_file(moved)
            except Exception:
                pass
    def select_bucket_path(self, code: str):
        if code not in self.buckets:
            return
        if code == "TRASH":
            return
        folder = QFileDialog.getExistingDirectory(self, f"Vyberte cílovou složku pro {self.buckets[code].alias}")
        if not folder:
            return
        self.buckets[code].path = folder
        self.bucket_widgets[code]["lbl_path"].setText(f"Cesta: {folder}")
        self.mark_dirty()
    def show_bucket_view(self, code: str):
        if code not in self.buckets:
            return
        self.current_view = code
        self.rebuild_list()
        self.update_view_header()
    def on_back_to_main_view(self):
        self.current_view = "MAIN"
        self.rebuild_list()
        self.update_view_header()
    def on_return_selected_from_bucket(self):
        if self.current_view == "MAIN":
            return
        items = self.list_widget.selectedItems()
        if not items:
            return
        moved_back = 0
        for it in items:
            rec_id = it.data(Qt.ItemDataRole.UserRole)
            if rec_id in self.image_by_id:
                rec = self.image_by_id[rec_id]
                if rec.bucket != "MAIN":
                    moved_back += 1
                self._set_record_bucket(rec, "MAIN")
        self.mark_dirty()
        self.rebuild_list()
        self.update_view_header()
        if moved_back > 0:
            try:
                self._coin_per_file(moved_back)
            except Exception:
                pass
    # ---------------- SCAN DIRS ----------------
    def _ask_scan_options(self) -> Optional[Tuple[int, int, bool]]:
        dlg = ScanOptionsDialog(self, self.last_min_kb, self.last_max_kb, self.last_ignore_system)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        mkb, xkb, ign = dlg.get_values()
        self.last_min_kb = mkb
        self.last_max_kb = xkb
        self.last_ignore_system = ign
        return mkb, xkb, ign
    def on_kajo_stopa(self):
        dir_ = QFileDialog.getExistingDirectory(self, "Vyberte adresář s fotkami")
        if not dir_:
            return
        self.sfx.play(SFX_JUMP)
        opts = self._ask_scan_options()
        if not opts:
            return
        mkb, xkb, ign = opts
        if dir_ not in self.session_roots:
            self.session_roots.append(dir_)
        self._scan_directories([dir_], append=True, min_kb=mkb, max_kb=xkb, ignore_system=ign)
    def _scan_directories(
        self,
        roots: List[str],
        append: bool,
        min_kb: int,
        max_kb: int,
        ignore_system: bool,
    ):
        logger.info("Začíná skenování: %s", roots)
        if not append:
            self.reset_state()
        scan_canceled = False
        progress_scan = QProgressDialog(
            "Prohledávám složky...\nProhledáno složek: 0\nNalezeno obrázků: 0",
            "Zrušit",
            0,
            0,
            self,
        )
        progress_scan.setWindowTitle("Skenování")
        progress_scan.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_scan.setMinimumDuration(0)
        progress_scan.setAutoClose(False)
        progress_scan.setAutoReset(False)
        progress_scan.setStyleSheet(PROGRESS_QSS + DIALOG_FRAME_QSS)
        apply_dialog_sizing(progress_scan, extra_h=160)
        progress_scan.show()
        QApplication.processEvents()
        self.toast("Kájo skenuje svět…", "warn", 1800)
        def on_progress(found_count: int, dir_count: int) -> bool:
            nonlocal scan_canceled
            progress_scan.setLabelText(
                f"Prohledávám složky...\nProhledáno složek: {dir_count}\nNalezeno obrázků: {found_count}"
            )
            QApplication.processEvents()
            if progress_scan.wasCanceled():
                scan_canceled = True
                return False
            return True
        all_paths = iter_image_paths(roots, ignore_system=ignore_system, on_progress=on_progress)
        progress_scan.close()
        if scan_canceled:
            logger.info("Skenování preruseno uzivatelem.")
            return
        logger.info("Nalezeno %d kandidátů před filtrem velikosti.", len(all_paths))
        if not all_paths:
            self.sfx.play(SFX_ERROR)
            self.toast("Kájo nic nenašel (0 obrázků).", "err", 2600)
            return
        progress_filter = DagmarProgress("Filtruji soubory podle velikosti…", self, len(all_paths))
        min_bytes = min_kb * 1024 if min_kb > 0 else 0
        max_bytes = max_kb * 1024 if max_kb > 0 else 0
        filtered: List[str] = []
        for i, p in enumerate(all_paths, start=1):
            if progress_filter.wasCanceled():
                logger.info("Filtrování přerušeno uživatelem.")
                break
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if min_bytes and sz < min_bytes:
                continue
            if max_bytes and sz > max_bytes:
                continue
            filtered.append(p)
            progress_filter.update(i)
        progress_filter.close()
        logger.info("Po filtru velikosti zůstává %d souborů.", len(filtered))
        if not filtered:
            self.sfx.play(SFX_ERROR)
            self.toast("Kájo vše vyfiltroval (0 prošlo).", "err", 2600)
            return
        progress = DagmarProgress("Načítám obrázky…", self, len(filtered))
        added = 0
        start_id_before = self.next_id
        existing_paths = {rec.path for rec in self.images}
        for i, path in enumerate(filtered, start=1):
            if progress is not None and progress.wasCanceled():
                logger.info("Skenování přerušeno uživatelem po %d souborech.", i - 1)
                break
            if path in existing_paths:
                if progress is not None:
                    progress.update(i)
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            rec = ImageRecord(id=self.next_id, path=path, size=size, bucket="MAIN")
            self.next_id += 1
            self.images.append(rec)
            self.image_by_id[rec.id] = rec
            existing_paths.add(path)
            added += 1
            # pokud aktuální pohled je MAIN, přidat do listu
            if self.current_view == "MAIN":
                self._add_record_to_list(rec)
                try:
                    self._coin_per_file(1)
                except Exception:
                    pass
            if progress is not None:
                progress.update(i)
        if progress is not None:
            progress.close()
        logger.info(
            "Skenování dokončeno, přidáno %d nových záznamů (ID od %d do %d).",
            added,
            start_id_before,
            self.next_id - 1,
        )
        if added > 0:
            self.mark_dirty()
        self.update_view_header()
    # ---------------- SAVE / LOAD ----------------
    def _do_save(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Uložit stav třídění",
            os.path.join(BASE_DIR, "Kaja_session.json"),
            "JSON (*.json)",
        )
        if not path:
            return False
        data = {
            "version": 1,
            "roots": self.session_roots,
            "current_view": self.current_view,
            "last_min_kb": self.last_min_kb,
            "last_max_kb": self.last_max_kb,
            "last_ignore_system": self.last_ignore_system,
            "images": [asdict(rec) for rec in self.images],
            "buckets": {
                code: {
                    "alias": b.alias,
                    "path": b.path,
                    "count": b.count,
                    "size_total": b.size_total,
                }
                for code, b in self.buckets.items()
            },
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Session uložena do: %s", path)
            self.clear_dirty()
            return True
        except Exception as e:
            logger.error("Chyba při ukládání session: %s", e)
            self._kajo_box("Kájo, chyba", "Nepodařilo se uložit session.", kind="err")
            return False
    def on_save(self):
        self._do_save()
    def on_load(self):
        choice = self.prompt_unsaved()
        if choice == "cancel":
            return
        if choice == "save":
            if not self._do_save():
                return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Načíst stav třídění",
            BASE_DIR,
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Chyba při načítání session: %s", e)
            self._kajo_box("Kájo, chyba", "Nepodařilo se načíst session.", kind="err")
            return
        logger.info("Načítám session z %s", path)
        self.reset_state()
        self.session_roots = data.get("roots", [])
        self.current_view = data.get("current_view", "MAIN")
        self.last_min_kb = data.get("last_min_kb", 0)
        self.last_max_kb = data.get("last_max_kb", 0)
        self.last_ignore_system = data.get("last_ignore_system", True)
        buckets_data = data.get("buckets", {})
        for code, cfg in self.buckets.items():
            bd = buckets_data.get(code, {})
            cfg.alias = bd.get("alias", cfg.alias)
            cfg.path = bd.get("path", cfg.path)
            cfg.count = 0
            cfg.size_total = 0
            w = self.bucket_widgets.get(code)
            if w:
                w["lbl_info"].setText(f"0 souborů / 0 B")
                if code != "TRASH":
                    if cfg.path:
                        w["lbl_path"].setText(f"Cesta: {cfg.path}")
                    else:
                        w["lbl_path"].setText("Cesta: (není namapováno)")
                w["group_box"].setTitle(cfg.alias.upper())
        images_data = data.get("images", [])
        progress = DagmarProgress("Obnovuji miniatury…", self, len(images_data))
        for i, rec_data in enumerate(images_data, start=1):
            try:
                rec = ImageRecord(
                    id=rec_data["id"],
                    path=rec_data["path"],
                    size=rec_data["size"],
                    bucket=rec_data.get("bucket", "MAIN"),
                    width=rec_data.get("width"),
                    height=rec_data.get("height"),
                )
            except Exception:
                continue
            self.images.append(rec)
            self.image_by_id[rec.id] = rec
            self.next_id = max(self.next_id, rec.id + 1)
            if rec.bucket != "MAIN":
                b = self.buckets.get(rec.bucket)
                if b:
                    b.count += 1
                    b.size_total += rec.size
            if progress is not None:
                progress.update(i)
        if progress is not None:
            progress.close()
        for code in self.buckets:
            self._update_bucket_stats(code)
        # znovu postavit seznam podle aktuálního pohledu
        if self.current_view not in self.buckets and self.current_view != "MAIN":
            self.current_view = "MAIN"
        self.rebuild_list()
        self.clear_dirty()
        self.update_view_header()
        self._coin_per_file(len(images_data))
        self.toast("Kájo si vzpomněl (session načtena).", "ok", 2400)
    # ---------------- NOVÁ SESSION / KONEC ----------------
    def on_new_session(self):
        clicked = self._kajo_box(
            "Kájo, pozor",
            "Opravdu chcete začít znovu? Dojde ke ztrátě všech neuložených dat.",
            kind="warn",
            buttons=[
                ("Pokračovat", QMessageBox.ButtonRole.AcceptRole),
                ("Zrušit", QMessageBox.ButtonRole.RejectRole),
            ],
            default_index=1,
            style_buttons={
                "Pokračovat": BUTTON_DANGER_QSS,
                "Zrušit": BUTTON_PRIMARY_QSS,
            },
        )
        if clicked != "Pokračovat":
            return
        choice = self.prompt_unsaved()
        if choice == "cancel":
            return
        if choice == "save":
            if not self._do_save():
                return
        clicked2 = self._kajo_box(
            "Kájo, potvrď restart",
            "Opravdu chcete zahodit všechen aktuální virtuální stav a začít znovu?",
            kind="warn",
            buttons=[
                ("Ano, začít znovu", QMessageBox.ButtonRole.AcceptRole),
                ("Ne", QMessageBox.ButtonRole.RejectRole),
            ],
            default_index=1,
            style_buttons={
                "Ano, začít znovu": BUTTON_DANGER_QSS,
                "Ne": BUTTON_PRIMARY_QSS,
            },
        )
        if clicked2 == "Ano, začít znovu":
            self.reset_state()
    def on_exit(self):
        warn = QMessageBox(self)
        warn.setWindowTitle("Kájo, pozor")
        warn.setIcon(QMessageBox.Icon.NoIcon)
        warn.setText("Opravdu chcete ukončit program? Neuložená data budou ztracena.")
        warn.setStyleSheet(DIALOG_FRAME_QSS)
        apply_dialog_sizing(warn, extra_h=140)
        try:
            self.sfx.pop()
        except Exception:
            pass
        yes_btn = warn.addButton("Kájo, ukončit", QMessageBox.ButtonRole.AcceptRole)
        no_btn = warn.addButton("Kájo, ne", QMessageBox.ButtonRole.RejectRole)
        warn.exec()
        if warn.clickedButton() != yes_btn:
            return
        if self.session_dirty:
            choice = self.prompt_unsaved()
            if choice == "cancel":
                return
            if choice == "save":
                if not self._do_save():
                    return
        self._start_exit_sequence()

    def _start_exit_sequence(self):
        if self._exit_in_progress:
            return
        self._exit_in_progress = True
        try:
            self.sfx.play_outro()
        except Exception:
            pass
        # pojistka: pustit outro i mimo SoundBank (napr. kdyz jsou zvuky vypnute)
        try:
            if QSoundEffect is not None:
                path = resource_path(SFX_OUTRO)
                if os.path.exists(path):
                    eff = QSoundEffect()
                    eff.setSource(QUrl.fromLocalFile(path))
                    eff.setVolume(0.9)
                    self._exit_sfx = eff
                    eff.play()
        except Exception:
            pass
        outro_ms = wav_duration_ms(SFX_OUTRO, default_ms=1600)
        screen = self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()
        geo = self.geometry()
        if geo.width() <= 1 or geo.height() <= 1:
            if screen is not None:
                geo = screen.availableGeometry()
        pixmap = QPixmap(geo.size())
        pixmap.fill(QColor(0, 0, 0))
        try:
            self.repaint()
            QApplication.processEvents()
            shot = self.grab()
            if not shot.isNull() and shot.width() > 1 and shot.height() > 1:
                pixmap = shot
            if (pixmap.isNull() or pixmap.width() <= 1 or pixmap.height() <= 1) and screen is not None:
                full = screen.grabWindow(0)
                screen_geo = screen.geometry()
                rel = QRect(geo)
                rel.translate(-screen_geo.x(), -screen_geo.y())
                if not full.isNull():
                    cut = full.copy(rel)
                    if not cut.isNull() and cut.width() > 1 and cut.height() > 1:
                        pixmap = cut
            if not pixmap.isNull() and (pixmap.width() != geo.width() or pixmap.height() != geo.height()):
                pixmap = pixmap.scaled(
                    geo.size(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        except Exception:
            pass
        if pixmap.isNull() or pixmap.width() <= 1 or pixmap.height() <= 1:
            pixmap = QPixmap(geo.size())
            pixmap.fill(QColor(0, 0, 0))
        overlay = ExitDissolveOverlay(pixmap, geo, outro_ms)
        self._exit_overlay = overlay
        overlay.finished.connect(lambda: QApplication.instance().quit())
        overlay.show()
        overlay.raise_()
        QApplication.processEvents()
        self.hide()
        overlay.start()
        QTimer.singleShot(outro_ms + 200, lambda: QApplication.instance().quit())
    # ---------------- DUPLICITY ----------------
    def on_find_duplicates(self):
        # duplicity jen v HLAVNÍ složce
        main_records = [rec for rec in self.images if rec.bucket == "MAIN"]
        if len(main_records) < 2:
            self.sfx.play(SFX_ERROR)
            self.toast("Kájo potřebuje aspoň 2 fotky v hlavním světě.", "err", 2600)
            return
        progress = DagmarProgress("Počítám hash pro hledání duplicit…", self, len(main_records))
        hash_map: Dict[int, List[ImageRecord]] = {}
        for i, rec in enumerate(main_records, start=1):
            if progress is not None and progress.wasCanceled():
                logger.info("Hledání duplicit přerušeno uživatelem.")
                progress.close()
                return
            h = perceptual_hash(rec.path)
            if h is not None:
                hash_map.setdefault(h, []).append(rec)
            if progress is not None:
                progress.update(i)
        if progress is not None:
            progress.close()
        groups: List[List[ImageRecord]] = [lst for lst in hash_map.values() if len(lst) > 1]
        if not groups:
            self.toast("Kájo nenašel žádné dvojníky.", "ok", 2200)
            return
        auto_mode = False
        for idx, group in enumerate(groups):
            if auto_mode:
                self._auto_handle_group(group)
                continue
            dlg = DuplicateGroupDialog(self, idx, len(groups), group)
            dlg_result = dlg.exec()
            choice = dlg.choice
            if choice == "abort":
                logger.info("Uživatel přerušil zpracování duplicit.")
                break
            if choice == "skip":
                continue
            if choice == "trash_all":
                for rec in group:
                    self._set_record_bucket(rec, "TRASH")
                self.mark_dirty()
            if choice == "keep_marked":
                keep_indices = dlg.selected_indices
                keep_ids = {group[i].id for i in keep_indices}
                for rec in group:
                    if rec.id in keep_ids:
                        self._set_record_bucket(rec, "MAIN")
                    else:
                        self._set_record_bucket(rec, "TRASH")
                self.mark_dirty()
            if choice == "auto_all":
                auto_mode = True
                self._auto_handle_group(group)
        self.rebuild_list()
        self.update_view_header()
    def _auto_handle_group(self, group: List[ImageRecord]):
        if not group:
            return
        best = max(group, key=lambda r: r.size)
        for rec in group:
            if rec is best:
                self._set_record_bucket(rec, "MAIN")
            else:
                self._set_record_bucket(rec, "TRASH")
        self.mark_dirty()
    # ---------------- SPUSŤ KÁJU (fyzický přesun) ----------------
    def on_run_apply(self):
        if not self.images:
            self._kajo_box("Kájo, není co provést", "Není nic k provedení.", kind="info")
            return
        # zkontrolovat, že všechny hromádky s obsahem (mimo MAIN a TRASH) mají namapovanou cestu
        missing_map = []
        for code, b in self.buckets.items():
            if code in ["TRASH"]:
                continue
            if b.count > 0 and not b.path:
                missing_map.append(b.alias)
        if missing_map:
            self._kajo_box(
                "Kájo, chybí cíle",
                "Následující hromádky obsahují soubory, ale nemají vybranou cílovou složku:\n\n"
                + "\n".join(missing_map),
                kind="warn",
            )
            return
        clicked = self._kajo_box(
            "Kájo, jdeme naostro",
            "Chystáte se fyzicky přesunout / smazat soubory podle virtuálního třídění.\n"
            "Tento krok není vratný.\n\n"
            "Pokračovat?",
            kind="warn",
            buttons=[
                ("Kájo, proveď to", QMessageBox.ButtonRole.AcceptRole),
                ("Kájo, stop", QMessageBox.ButtonRole.RejectRole),
            ],
            default_index=1,
            style_buttons={
                "Kájo, proveď to": BUTTON_DANGER_QSS,
                "Kájo, stop": BUTTON_PRIMARY_QSS,
            },
        )
        if clicked != "Kájo, proveď to":
            return
        # sestavit operace
        operations: List[Tuple[ImageRecord, str, str]] = []  # (rec, op_type, target_path_or_empty)
        missing_sources = 0
        for rec in self.images:
            if rec.bucket == "MAIN":
                continue
            if not os.path.exists(rec.path):
                missing_sources += 1
                logger.warning("Zdroj chybí, přeskočeno: %s", rec.path)
                continue
            if rec.bucket == "TRASH":
                operations.append((rec, "TRASH", ""))
            else:
                b = self.buckets.get(rec.bucket)
                if not b or not b.path:
                    logger.warning("Bucket %s nemá cestu, přeskočeno: %s", rec.bucket, rec.path)
                    continue
                target_dir = b.path
                os.makedirs(target_dir, exist_ok=True)
                dst = os.path.join(target_dir, os.path.basename(rec.path))
                operations.append((rec, "MOVE", dst))
        if not operations and missing_sources == 0:
            self._kajo_box("Kájo, není co provést", "Není žádná operace k provedení.", kind="info")
            return
        progress = DagmarProgress("Provádím fyzické přesuny…", self, len(operations))
        moved = 0
        trashed = 0
        failed = 0
        for i, (rec, op_type, target) in enumerate(operations, start=1):
            if progress is not None and progress.wasCanceled():
                logger.info("KájovoPhotoSelector zrušeno uživatelem po %d operacích.", i - 1)
                break
            try:
                if op_type == "TRASH":
                    if send2trash is not None:
                        send2trash(rec.path)
                        logger.info("KOŠ: %s", rec.path)
                    else:
                        os.remove(rec.path)
                        logger.info("SMAZÁNO (bez send2trash): %s", rec.path)
                    trashed += 1
                    self._coin_per_file(1)
                elif op_type == "MOVE":
                    safe_move_file(rec.path, target)
                    logger.info("PŘESUNUTO: %s -> %s", rec.path, target)
                    moved += 1
                    self._coin_per_file(1)
                else:
                    failed += 1
                    logger.error("Neznámý typ operace: %s", op_type)
            except Exception as e:
                failed += 1
                logger.error("Chyba při přesunu %s: %s", rec.path, e)
            if progress is not None:
                progress.update(i)
        if progress is not None:
            progress.close()
        # po provedení – vyprázdnit vše, jako při startu
        msg_txt = (
            f"Přesunuto: {moved} souborů\n"
            f"Do koše: {trashed} souborů\n"
            f"Chybné operace: {failed}\n"
            f"Chybějící zdroje: {missing_sources}"
        )
        self._kajo_box("Kájo, hotovo", msg_txt, kind="info")
        logger.info("Kájo, hotovo: %s", msg_txt.replace("\n", " | "))
        # Návrat do výchozího stavu
        self.reset_state()
        self._play_reklama_if_exists()

    def _play_reklama_if_exists(self):
        src = resource_path("reklama.mp4")
        if not os.path.exists(src):
            logger.info("reklama.mp4 nenalezena: %s", src)
            return
        try:
            play_path = src
            if getattr(sys, "_MEIPASS", None):
                tmp = tempfile.gettempdir()
                dst = os.path.join(tmp, "KajovoPhotoSelector_reklama.mp4")
                try:
                    shutil.copy2(src, dst)
                    play_path = dst
                except Exception:
                    play_path = src
            if os.name == "nt":
                try:
                    os.startfile(play_path)  # type: ignore[attr-defined]
                    return
                except Exception:
                    subprocess.Popen(["cmd", "/c", "start", "", play_path], shell=False)
                    return
            if sys.platform == "darwin":
                subprocess.Popen(["open", play_path])
            else:
                subprocess.Popen(["xdg-open", play_path])
        except Exception as e:
            logger.warning("Nepodařilo se přehrát reklamní video: %s", e)
    # ---------------- CLOSE EVENT ----------------
    def closeEvent(self, event):
        try:
            if not self._exit_in_progress:
                self._start_exit_sequence()
                event.ignore()
                return
        except Exception:
            pass
        try:
            self.threadpool.waitForDone(3000)
        except Exception:
            pass
        event.accept()
# =====================
# MAIN
# =====================
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Kájovo")
    _set_windows_appusermodel_id("Kajovo.PhotoSelector")

    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    except Exception:
        pass
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    app.setStyleSheet(
        """
        QMainWindow, QWidget { background-color: %s; color: %s; }
        QMessageBox {
            border: 2px solid %s;
            border-radius: 8px;
        }
        """ % (BG_COLOR, TEXT_COLOR, ACCENT_COLOR)
    )
    app.setWindowIcon(get_app_icon())

    sfx = SoundBank()
    app.installEventFilter(GlobalButtonFxFilter(lambda: sfx))

    splash = IntroSplash(sfx)
    splash.show()

    win = MainWindow(sfx)
    win.setWindowIcon(get_app_icon())
    win.hide()

    def show_main():
        try:
            win._maximize_on_primary()
        except Exception:
            win.showMaximized()
            return
        win.show()
        win.raise_()
        win.activateWindow()

    splash.about_to_finish.connect(show_main)

    sys.exit(app.exec())


class IntroSplash(QWidget):
    """
    Stabilní intro (bez videa): full-screen jednolité pozadí + logo + krátký fade.
    """

    finished = pyqtSignal()
    about_to_finish = pyqtSignal()

    def __init__(self, sfx: SoundBank):
        super().__init__(None)
        self._sfx = sfx
        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setWindowIcon(get_app_icon())
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#000000"))
        self.setPalette(pal)
        self.setStyleSheet("background-color: #000000;")

        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            self.setGeometry(scr.geometry())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        logo = QLabel(self)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = load_logo_pixmap()
        if pm is not None:
            logo.setPixmap(pm)
        else:
            logo.setText(APP_NAME)
            logo.setStyleSheet("color:#E9F0FF; font-size:48px; font-weight:900;")

        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        # Fade-in
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0.0)

        self._intro_ms = wav_duration_ms(SFX_INTRO, default_ms=1800)
        self._fade_in_ms = max(200, int(self._intro_ms * 0.35))
        self._fade_out_ms = max(200, int(self._intro_ms * 0.25))
        total_fade = self._fade_in_ms + self._fade_out_ms
        if total_fade > self._intro_ms:
            self._fade_in_ms = max(120, int(self._intro_ms * 0.55))
            self._fade_out_ms = max(120, self._intro_ms - self._fade_in_ms)
        self._hold_ms = max(0, self._intro_ms - self._fade_in_ms - self._fade_out_ms)

        self.anim_in = QPropertyAnimation(self._fx, b"opacity")
        self.anim_in.setDuration(self._fade_in_ms)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_out = QPropertyAnimation(self._fx, b"opacity")
        self.anim_out.setDuration(self._fade_out_ms)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim_out.finished.connect(self._emit_done)

        self.anim_in.finished.connect(lambda: QTimer.singleShot(self._hold_ms, self._finish))
        # Zobrazit až po vytvoření animací, aby showEvent měl připravený self.anim_in
        self.showFullScreen()

    def showEvent(self, event):
        try:
            self._sfx.intro()
        except Exception:
            pass
        self.anim_in.start()
        return super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        super().paintEvent(event)

    def _finish(self):
        self.about_to_finish.emit()
        self.anim_out.start()

    def _emit_done(self):
        self.close()
        self.finished.emit()


if __name__ == "__main__":
    main()
