# Kaja_Tridi_Obrazky_v5.py
# Kompletní verze programu "Petr třídí obrázky…" podle zadání
# Vytvořeno: 2025-11-17
import os
import sys
import json
import time
import shutil
import logging
import warnings
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
)
from PyQt6.QtGui import QIcon, QPixmap, QImage, QImageReader, QPalette, QColor, QMouseEvent, QBrush, QPainter, QDrag
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
)
from PIL import Image, ImageFile, UnidentifiedImageError
ImageFile.LOAD_TRUNCATED_IMAGES = True
try:
    from send2trash import send2trash
except ImportError:
    send2trash = None
# =====================
# KONSTANTY A BARVY UI
# =====================
PRIMARY_COLOR = "#004A99"   # firemní modrá
ACCENT_COLOR = "#FFD700"    # firemní zlatá
BG_COLOR = "#0E0F12"        # tmavé pozadí
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
BUTTON_BLUE_QSS = f"background-color:{PRIMARY_COLOR};color:white;padding:6px 10px;font-weight:bold;border-radius:4px;"
BUTTON_GOLD_QSS = f"background-color:{ACCENT_COLOR};color:black;padding:6px 10px;font-weight:bold;border-radius:4px;"
BUTTON_RED_QSS = "background-color:#CC3333;color:white;padding:6px 10px;font-weight:bold;border-radius:4px;"
BUTTON_GRAY_QSS = "background-color:#444444;color:white;padding:6px 10px;font-weight:bold;border-radius:4px;"
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "Kaja_Tridi_Obrazky.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("Kaja")
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
        self.setWindowTitle("Dagmar – průběh operace")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setStyleSheet(PROGRESS_QSS + DIALOG_FRAME_QSS)
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
class BucketDropGroupBox(QGroupBox):
    def __init__(self, code: str, main_window, parent=None):
        super().__init__(parent)
        self.code = code
        self.main_window = main_window
        self._base_stylesheet = ""
        self.setAcceptDrops(True)

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
        self.btn_keep = QPushButton("Označené zachovej")
        self.btn_skip = QPushButton("Přeskoč")
        self.btn_trash = QPushButton("Smaž všechny")
        self.btn_auto = QPushButton("Petře, udělej to za mě…")
        self.btn_cancel = QPushButton("STORNO")
        self.btn_keep.setStyleSheet(BUTTON_BLUE_QSS)
        self.btn_skip.setStyleSheet(BUTTON_RED_QSS)
        self.btn_trash.setStyleSheet(BUTTON_GOLD_QSS)
        self.btn_auto.setStyleSheet(BUTTON_BLUE_QSS)
        self.btn_cancel.setStyleSheet(BUTTON_RED_QSS)
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Petr třídí obrázky…")
        self.setMinimumSize(1200, 800)
        self.threadpool = QThreadPool()
        logger.info("Petr – threadpool velikost: %d", self.threadpool.maxThreadCount())
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
            "T1": Bucket("T1", "HROMÁDKA 1"),
            "T2": Bucket("T2", "HROMÁDKA 2"),
            "T3": Bucket("T3", "HROMÁDKA 3"),
            "T4": Bucket("T4", "HROMÁDKA 4"),
            "TRASH": Bucket("TRASH", "KOŠ"),
            "DUPLICITA": Bucket("DUPLICITA", "DUPLICITY"),
        }
        # bucket kód -> widgety
        self.bucket_widgets: Dict[str, Dict[str, QWidget]] = {}
        self._build_ui()
        self.showMaximized()
    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        # Horní menu
        top_bar = QHBoxLayout()
        self.btn_kajo_stopa = QPushButton("Petře, stopa...")
        self.btn_dupes = QPushButton("Petře, hledej duplicity...")
        self.btn_run = QPushButton("SPUSŤ Petra...")
        self.btn_save = QPushButton("SAVE")
        self.btn_load = QPushButton("LOAD")
        self.btn_new = QPushButton("Petře, začneme znovu...")
        self.btn_exit = QPushButton("PETR ŘÍKÁ KONEC")
        # Barvy
        self.btn_kajo_stopa.setStyleSheet(BUTTON_BLUE_QSS)
        self.btn_dupes.setStyleSheet(BUTTON_GOLD_QSS)
        self.btn_run.setStyleSheet(BUTTON_RED_QSS)
        self.btn_save.setStyleSheet(BUTTON_GRAY_QSS)
        self.btn_load.setStyleSheet(BUTTON_GRAY_QSS)
        self.btn_new.setStyleSheet(BUTTON_RED_QSS)
        self.btn_exit.setStyleSheet(BUTTON_BLUE_QSS)
        for b in [
            self.btn_kajo_stopa,
            self.btn_dupes,
            self.btn_run,
            self.btn_save,
            self.btn_load,
            self.btn_new,
            self.btn_exit,
        ]:
            top_bar.addWidget(b)
        main_layout.addLayout(top_bar)
        # Nad seznamem – informace o aktuálním pohledu
        header_layout = QHBoxLayout()
        self.btn_back_to_main = QPushButton("Zpet do HLAVNÍ SLOŽKY")
        self.btn_back_to_main.setStyleSheet(BUTTON_BLUE_QSS)
        self.btn_back_to_main.setVisible(False)
        header_layout.addWidget(self.btn_back_to_main)
        self.lbl_view_title = QLabel("Pohled: HLAVNÍ VIRTUÁLNÍ SLOŽKA")
        self.lbl_view_title.setStyleSheet(f"color:{ACCENT_COLOR};font-size:14pt;font-weight:bold;")
        header_layout.addWidget(self.lbl_view_title)
        header_layout.addStretch()
        self.lbl_view_stats = QLabel("Soubory: 0 (0 B), vybráno: 0 (0 B)")
        self.lbl_view_stats.setStyleSheet("color:white;")
        header_layout.addWidget(self.lbl_view_stats)
        main_layout.addLayout(header_layout)
        # Seznam miniatur
        self.list_widget = DraggableListWidget(self)
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(96, 72))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setSpacing(6)
        self.list_widget.setGridSize(QSize(120, 120))
        self.list_widget.setWordWrap(False)
        self.list_widget.setStyleSheet(
            """
            QListWidget::item {
                border: 2px solid transparent;
                padding: 4px;
            }
            QListWidget::item:selected {
                border: 2px solid %s;
                background-color: rgba(255,215,0,40);
            }
            """ % ACCENT_COLOR
        )
        main_layout.addWidget(self.list_widget, stretch=1)
        # Tlačítko pro návrat z hromádek do hlavní složky (spodní, celá šířka)
        self.btn_return_from_bucket = QPushButton("Vrátit označené do HLAVNÍ SLOŽKY")
        self.btn_return_from_bucket.setStyleSheet(BUTTON_RED_QSS)
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
            lbl_info = QLabel(f"0 souborů / 0 B")
            lbl_info.setStyleSheet(f"color:{ACCENT_COLOR};font-weight:bold;")
            btn_assign = QPushButton(f"Přesunout do {bucket.alias}")
            btn_assign.setStyleSheet(BUTTON_RED_QSS)
            lbl_path = QLabel("Cesta: (není namapováno)" if code not in ["TRASH"] else "Cesta: systémový Koš")
            lbl_path.setStyleSheet("color:white;")
            lbl_path.setWordWrap(True)
            if code in ["T1", "T2", "T3", "T4", "DUPLICITA"]:
                btn_select = QPushButton("Vybrat složku")
                btn_select.setStyleSheet(BUTTON_BLUE_QSS)
            else:
                btn_select = QLabel("Vybrat složku není potřeba")
            btn_show = QPushButton("Zobrazit obsah")
            btn_show.setStyleSheet(BUTTON_GRAY_QSS)
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
                    border: 2px solid {ACCENT_COLOR};
                    border-radius: 8px;
                    margin-top: 6px;
                    color: {ACCENT_COLOR};
                    font-weight: bold;
                    text-transform: uppercase;
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
        msg.setWindowTitle("Neuložené změny")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(
            "Máte rozpracované virtuální třídění, které není uložené.\n"
            "Chcete aktuální stav uložit?"
        )
        msg.setStyleSheet(DIALOG_FRAME_QSS)
        save_btn = msg.addButton("Uložit", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg.addButton("Zahodit", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("Zrušit", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        save_btn.setStyleSheet(BUTTON_GOLD_QSS)
        discard_btn.setStyleSheet(BUTTON_RED_QSS)
        cancel_btn.setStyleSheet(BUTTON_BLUE_QSS)
        clicked = msg.clickedButton()
        if clicked == save_btn:
            return "save"
        if clicked == discard_btn:
            return "discard"
        return "cancel"
    # ---------------- VIEW / HEADER ----------------
    def update_view_header(self):
        if self.current_view == "MAIN":
            self.lbl_view_title.setText("Pohled: HLAVNÍ VIRTUÁLNÍ SLOŽKA")
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
    def rename_bucket(self, code: str):
        if code not in ["T1", "T2", "T3", "T4"]:
            return
        bucket = self.buckets.get(code)
        if not bucket:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Přejmenovat hromádku",
            "Nový název hromádky:",
            QLineEdit.EchoMode.Normal,
            bucket.alias,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        bucket.alias = new_name
        w = self.bucket_widgets.get(code)
        if w:
            w["group_box"].setTitle(new_name.upper())
            w["btn_assign"].setText(f"Přesunout do {new_name}")
        if self.current_view == code:
            self.update_view_header()

    def assign_selected_to_bucket(self, code: str):
        if self.current_view != "MAIN":
            info = QMessageBox(self)
            info.setWindowTitle("Přesun")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Přesun do hromádek je možný pouze z HLAVNÍ VIRTUÁLNÍ SLOŽKY.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
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
        for rec in recs:
            self._set_record_bucket(rec, code)
        self.mark_dirty()
        self.rebuild_list()
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
        for it in items:
            rec_id = it.data(Qt.ItemDataRole.UserRole)
            if rec_id in self.image_by_id:
                rec = self.image_by_id[rec_id]
                self._set_record_bucket(rec, "MAIN")
        self.mark_dirty()
        self.rebuild_list()
        self.update_view_header()
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
        progress_scan.show()
        QApplication.processEvents()
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
            info = QMessageBox(self)
            info.setWindowTitle("Skenování")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Podle zadaných podmínek nebyly nalezeny žádné obrázky.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
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
            info = QMessageBox(self)
            info.setWindowTitle("Skenování")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Podle zadaných podmínek nebyly nalezeny žádné obrázky.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
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
            err = QMessageBox(self)
            err.setWindowTitle("Chyba")
            err.setIcon(QMessageBox.Icon.Critical)
            err.setText("Nepodařilo se uložit session.")
            err.setStyleSheet(DIALOG_FRAME_QSS)
            err.exec()
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
            err = QMessageBox(self)
            err.setWindowTitle("Chyba")
            err.setIcon(QMessageBox.Icon.Critical)
            err.setText("Nepodařilo se načíst session.")
            err.setStyleSheet(DIALOG_FRAME_QSS)
            err.exec()
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
        info = QMessageBox(self)
        info.setWindowTitle("Načteno")
        info.setIcon(QMessageBox.Icon.Information)
        info.setText("Session byla načtena. Soubory se znovu neprohledávaly na disku.")
        info.setStyleSheet(DIALOG_FRAME_QSS)
        info.exec()
    # ---------------- NOVÁ SESSION / KONEC ----------------
    def on_new_session(self):
        warn = QMessageBox(self)
        warn.setWindowTitle("Varování")
        warn.setIcon(QMessageBox.Icon.Warning)
        warn.setText("Opravdu chcete začít znovu? Dojde ke ztrátě všech neuložených dat.")
        warn.setStyleSheet(DIALOG_FRAME_QSS)
        yes_btn = warn.addButton("Pokračovat", QMessageBox.ButtonRole.AcceptRole)
        no_btn = warn.addButton("Zrušit", QMessageBox.ButtonRole.RejectRole)
        warn.exec()
        yes_btn.setStyleSheet(BUTTON_RED_QSS)
        no_btn.setStyleSheet(BUTTON_BLUE_QSS)
        if warn.clickedButton() is not yes_btn:
            return
        choice = self.prompt_unsaved()
        if choice == "cancel":
            return
        if choice == "save":
            if not self._do_save():
                return
        msg = QMessageBox(self)
        msg.setWindowTitle("Nová session")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("Opravdu chcete zahodit všechen aktuální virtuální stav a začít znovu?")
        msg.setStyleSheet(DIALOG_FRAME_QSS)
        yes = msg.addButton("Ano, začít znovu", QMessageBox.ButtonRole.AcceptRole)
        no = msg.addButton("Ne", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() == yes:
            self.reset_state()
    def on_exit(self):
        warn = QMessageBox(self)
        warn.setWindowTitle("Varování")
        warn.setIcon(QMessageBox.Icon.Warning)
        warn.setText("Opravdu chcete ukončit program? Neuložená data budou ztracena.")
        warn.setStyleSheet(DIALOG_FRAME_QSS)
        yes_btn = warn.addButton("Ukončit", QMessageBox.ButtonRole.AcceptRole)
        no_btn = warn.addButton("Zrušit", QMessageBox.ButtonRole.RejectRole)
        warn.exec()
        yes_btn.setStyleSheet(BUTTON_RED_QSS)
        no_btn.setStyleSheet(BUTTON_BLUE_QSS)
        if warn.clickedButton() is not yes_btn:
            return
        if self.session_dirty:
            choice = self.prompt_unsaved()
            if choice == "cancel":
                return
            if choice == "save":
                if not self._do_save():
                    return
        self.close()
    # ---------------- DUPLICITY ----------------
    def on_find_duplicates(self):
        # duplicity jen v HLAVNÍ složce
        main_records = [rec for rec in self.images if rec.bucket == "MAIN"]
        if len(main_records) < 2:
            info = QMessageBox(self)
            info.setWindowTitle("Duplicity")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Pro hledání duplicit musíte mít v hlavní složce alespoň 2 soubory.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
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
            info = QMessageBox(self)
            info.setWindowTitle("Duplicity")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Nenalezeny žádné duplicity v HLAVNÍ VIRTUÁLNÍ SLOŽCE.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
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
            info = QMessageBox(self)
            info.setWindowTitle("SPUSŤ Petra")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Není nic k provedení.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
            return
        # zkontrolovat, že všechny hromádky s obsahem (mimo MAIN a TRASH) mají namapovanou cestu
        missing_map = []
        for code, b in self.buckets.items():
            if code in ["TRASH"]:
                continue
            if b.count > 0 and not b.path:
                missing_map.append(b.alias)
        if missing_map:
            warn = QMessageBox(self)
            warn.setWindowTitle("Chybí mapování složek")
            warn.setIcon(QMessageBox.Icon.Warning)
            warn.setText(
                "Následující hromádky obsahují soubory, ale nemají vybranou cílovou složku:\n\n"
                + "\n".join(missing_map)
            )
            warn.setStyleSheet(DIALOG_FRAME_QSS)
            warn.exec()
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("SPUSŤ Petra...")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(
            "Chystáte se fyzicky přesunout / smazat soubory podle virtuálního třídění.\n"
            "Tento krok není vratný.\n\n"
            "Pokračovat?"
        )
        msg.setStyleSheet(DIALOG_FRAME_QSS)
        ok_btn = msg.addButton("SPUSŤ Petra – provést", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg.addButton("Zrušit", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        ok_btn.setStyleSheet(BUTTON_RED_QSS)
        cancel_btn.setStyleSheet(BUTTON_BLUE_QSS)
        if msg.clickedButton() is not ok_btn:
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
            info = QMessageBox(self)
            info.setWindowTitle("SPUSŤ Petra")
            info.setIcon(QMessageBox.Icon.Information)
            info.setText("Není žádná operace k provedení.")
            info.setStyleSheet(DIALOG_FRAME_QSS)
            info.exec()
            return
        progress = DagmarProgress("Provádím fyzické přesuny…", self, len(operations))
        moved = 0
        trashed = 0
        failed = 0
        for i, (rec, op_type, target) in enumerate(operations, start=1):
            if progress is not None and progress.wasCanceled():
                logger.info("SPUSŤ Petra zrušeno uživatelem po %d operacích.", i - 1)
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
                elif op_type == "MOVE":
                    safe_move_file(rec.path, target)
                    logger.info("PŘESUNUTO: %s -> %s", rec.path, target)
                    moved += 1
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
        info = QMessageBox(self)
        info.setWindowTitle("SPUSŤ Petra – hotovo")
        info.setIcon(QMessageBox.Icon.Information)
        info.setText(msg_txt)
        info.setStyleSheet(DIALOG_FRAME_QSS)
        info.exec()
        logger.info("SPUSŤ Petra dokončeno: %s", msg_txt.replace("\n", " | "))
        # Návrat do výchozího stavu
        self.reset_state()
        # pokus o přehrání reklamního videa, pokud existuje (např. reklama.mp4 v BASE_DIR)
        video_path = os.path.join(BASE_DIR, "reklama.mp4")
        if os.path.exists(video_path):
            try:
                os.startfile(video_path)
            except Exception as e:
                logger.warning("Nepodařilo se přehrát reklamní video: %s", e)
    # ---------------- CLOSE EVENT ----------------
    def closeEvent(self, event):
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
    app.setStyleSheet(
        """
        QMainWindow, QWidget { background-color: #151821; color: white; }
        QMessageBox {
            border: 2px solid %s;
            border-radius: 8px;
        }
        """ % ACCENT_COLOR
    )
    icon_path = os.path.join(BASE_DIR, "kajovo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()