"""Qt 6 interface for the CubeMX KiCad net-label CLI."""
import os
import re
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

from PySide6.QtCore import QPointF, QProcess, QProcessEnvironment, QSettings, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFontDatabase,
    QIntValidator,
    QPainter,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QDoubleSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:  # SVG preview needs QtSvgWidgets (included with the normal PySide6 wheel)
    from PySide6.QtSvgWidgets import QGraphicsSvgItem
    HAVE_SVG = True
except ImportError:
    QGraphicsSvgItem = None
    HAVE_SVG = False


def build_cli_arguments(
    csv_path: str,
    schematic_path: str,
    output_path: str,
    reference: str,
    column: str,
    net_length_mils: float | str,
    grid_mils: float,
    font_size_mils: float,
    minimum_stub_mils: float = 300,
    font_face: str = "",
    font_thickness_mils: float | None = None,
    auto_thickness: bool = True,
    bold: bool = False,
    italic: bool = False,
    fallback_signal: bool = False,
    fallback_name: bool = False,
    dry_run: bool = False,
    in_place: bool = False,
    force: bool = False,
) -> list[str]:
    """Build command-line arguments using mils, as accepted by the CLI."""
    arguments = [csv_path, schematic_path]
    if output_path and not in_place:
        arguments.append(output_path)
    arguments.extend(
        [
            "--reference", reference,
            "--column", column,
            "--stub", f"{minimum_stub_mils:g}",
            "--net-length", (
                "auto" if isinstance(net_length_mils, str)
                else f"{net_length_mils:g}"
            ),
            "--grid", f"{grid_mils:g}",
            "--font-size", f"{font_size_mils:g}",
        ]
    )
    if font_face:
        arguments.extend(["--font-face", font_face])
    if auto_thickness:
        arguments.append("--auto-thickness")
    elif font_thickness_mils is not None:
        arguments.extend(["--font-thickness", f"{font_thickness_mils:g}"])
    else:
        raise ValueError("A font thickness is required when automatic thickness is off")
    if bold:
        arguments.append("--bold")
    if italic:
        arguments.append("--italic")
    if fallback_signal:
        arguments.append("--fallback-signal")
    if fallback_name:
        arguments.append("--fallback-name")
    if dry_run:
        arguments.append("--dry-run")
    if in_place:
        arguments.append("--in-place")
    if force:
        arguments.append("--force")
    return arguments


def cli_process_command(arguments: list[str]) -> tuple[str, list[str]]:
    """Run this package's CLI from the current Python environment."""
    return sys.executable, ["-u", "-m", "cubemx_kicad_netlabels", *arguments]


def find_kicad_cli() -> str | None:
    """Find kicad-cli on PATH or in the conventional Windows install tree."""
    on_path = shutil.which("kicad-cli")
    if on_path:
        return on_path
    if sys.platform == "win32":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(variable)
            if base:
                candidates = sorted(
                    (Path(base) / "KiCad").glob("*/bin/kicad-cli.exe"),
                    reverse=True,
                )
                if candidates:
                    return str(candidates[0])
    return None


class PreviewView(QGraphicsView):
    """Zoomable / pannable viewer: wheel = zoom, drag = pan, double-click = fit."""

    def __init__(self):
        super().__init__()
        self.preview_scene = QGraphicsScene(self)
        self.setScene(self.preview_scene)
        self._fitted = True
        self.setBackgroundBrush(QBrush(QColor("#FFFFFF")))   # paper, in every theme
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumHeight(380)
        self.setToolTip("Mouse wheel: zoom   |   drag: pan   |   double-click: fit")

    def fit(self):
        self._fitted = True
        rect = self.preview_scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._fitted = False
        self.scale(factor, factor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fitted:
            self.fit()


class NetLabelGui(QMainWindow):
    THEMES = {
        "Dark": {
            "background": "#2B2B2B", "surface": "#383838",
            "surface_alt": "#454545", "border": "#555555",
            "text": "#E6E6E6", "muted": "#B0B0B0",
            "accent": "#C89120", "accent_hover": "#DDAA3B",
            "input": "#303030",
        },
        "Light": {
            "background": "#F3F6FB", "surface": "#FFFFFF",
            "surface_alt": "#EAF0F8", "border": "#D2DBE8",
            "text": "#172033", "muted": "#5D6B82",
            "accent": "#2563EB", "accent_hover": "#1D4ED8",
            "input": "#FFFFFF",
        },
        "Blue": {
            "background": "#071B2E", "surface": "#0B2943",
            "surface_alt": "#103858", "border": "#1B4B6D",
            "text": "#E3F3FF", "muted": "#91B7D0",
            "accent": "#00A6D6", "accent_hover": "#29C1E8",
            "input": "#08233B",
        },
    }

    def __init__(self, project_directory=None):
        super().__init__()
        self.setWindowTitle("CubeMX Net Labels for KiCad")
        self.resize(900, 760)
        self.setMinimumSize(560, 460)
        self._project_directory = project_directory or ""
        self.process = None
        self.reference_process = None
        self._reference_path_loaded = None
        self._reference_path_pending = None
        self._auto_output = None          # last auto-suggested output name
        self._preview_dir = None
        self.preview_process = None
        self.theme_name = "Dark"
        self.COLORS = self.THEMES[self.theme_name]
        self._configure_style()
        self._build_ui()
        self._build_theme_menu()
        self._restore_settings()

    @staticmethod
    def _arrow_image(color):
        """Draw a small down-arrow PNG (Qt stylesheets can't draw triangles)."""
        path = Path(tempfile.gettempdir()) / f"cube_netlabels_arrow_{color.lstrip('#')}.png"
        pixmap = QPixmap(12, 8)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(QPolygonF([QPointF(1, 1.5), QPointF(11, 1.5), QPointF(6, 6.5)]))
        painter.end()
        pixmap.save(str(path), "PNG")
        return path.as_posix()          # forward slashes: required in url() on Windows

    def _configure_style(self):
        c = self.COLORS
        arrow = self._arrow_image(c['muted'])
        arrow_open = self._arrow_image(c['accent'])
        self.setStyleSheet(f"""
            QMenuBar {{ color: {c['text']}; background: {c['surface']}; }}
            QMenuBar::item {{ padding: 7px 12px; background: transparent; }}
            QMenuBar::item:selected {{ background: {c['surface_alt']}; }}
            QMenu {{
                color: {c['text']}; background: {c['surface']};
                border: 1px solid {c['border']}; padding: 5px;
            }}
            QMenu::item {{ padding: 7px 28px 7px 10px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {c['surface_alt']}; }}
            QMainWindow, QWidget#page {{ background: {c['background']}; color: {c['text']}; }}
            QScrollArea {{ border: 0; background: {c['background']}; }}
            QFrame#card {{
                background: {c['surface']}; border: 1px solid {c['border']};
                border-radius: 12px;
            }}
            QFrame#palette {{
                background: {c['surface_alt']}; border: 1px solid {c['border']};
                border-radius: 9px;
            }}
            QLabel {{ color: {c['text']}; background: transparent; border: 0; }}
            QLabel#eyebrow {{ color: {c['accent']}; font-size: 9pt; font-weight: 700; }}
            QLabel#title {{ font-size: 22pt; font-weight: 700; }}
            QLabel#subtitle, QLabel#muted {{ color: {c['muted']}; }}
            QLabel#section {{ font-size: 11pt; font-weight: 700; }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                color: {c['text']}; background: {c['input']};
                border: 1px solid {c['border']}; border-radius: 7px;
                padding: 8px 10px; selection-background-color: {c['accent']};
                min-height: 18px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid {c['accent']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 26px; border-left: 1px solid {c['border']};
            }}
            QComboBox::down-arrow {{
                image: url("{arrow}"); width: 12px; height: 8px;
            }}
            QComboBox::down-arrow:on {{ image: url("{arrow_open}"); }}
            QComboBox QAbstractItemView {{
                color: {c['text']}; background: {c['input']};
                selection-background-color: {c['accent']};
                border: 1px solid {c['border']};
            }}
            QPushButton {{
                color: {c['text']}; background: {c['surface_alt']};
                border: 1px solid {c['border']}; border-radius: 7px;
                padding: 8px 12px;
            }}
            QPushButton:hover {{ background: {c['border']}; }}
            QPushButton:pressed {{ background: {c['accent']}; }}
            QPushButton#primary {{
                color: white; background: {c['accent']}; border: 0;
                border-radius: 8px; padding: 12px;
                font-size: 11pt; font-weight: 700;
            }}
            QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
            QPushButton#primary:disabled {{
                color: {c['muted']}; background: {c['surface_alt']};
            }}
            QRadioButton, QCheckBox {{ color: {c['text']}; spacing: 8px; }}
            QRadioButton::indicator, QCheckBox::indicator {{
                width: 16px; height: 16px;
            }}
            QProgressBar {{
                background: {c['surface_alt']}; border: 0; border-radius: 4px;
                min-height: 7px; max-height: 7px; text-align: center;
            }}
            QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
            QTextEdit {{
                color: {c['text']}; background: {c['input']};
                border: 0; border-radius: 7px;
                selection-background-color: {c['accent']};
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 9pt; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {c['background']}; width: 10px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c['border']}; min-height: 30px; border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        self._style_font_buttons()

    def _build_theme_menu(self):
        theme_menu = self.menuBar().addMenu("Theme")
        self.theme_actions = {}
        for name in self.THEMES:
            action = theme_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == self.theme_name)
            action.triggered.connect(
                lambda checked=False, theme=name: self._apply_theme(theme))
            self.theme_actions[name] = action

    def _apply_theme(self, theme_name):
        if theme_name not in self.THEMES:
            raise ValueError(f"Unknown theme: {theme_name}")
        self.theme_name = theme_name
        self.COLORS = self.THEMES[theme_name]
        self._configure_style()
        for name, action in self.theme_actions.items():
            action.setChecked(name == theme_name)

    def _style_font_buttons(self):
        c = self.COLORS
        buttons = list(getattr(self, "font_style_buttons", {}).values())
        for index, button in enumerate(buttons):
            left_radius = "5px" if index == 0 else "0"
            right_radius = "5px" if index == len(buttons) - 1 else "0"
            button.setStyleSheet(f"""
                QPushButton {{
                    color: {c['muted']}; background: {c['input']};
                    border: 1px solid {c['border']};
                    border-top-left-radius: {left_radius};
                    border-bottom-left-radius: {left_radius};
                    border-top-right-radius: {right_radius};
                    border-bottom-right-radius: {right_radius};
                    padding: 4px 10px; font-weight: 600;
                }}
                QPushButton:hover {{
                    color: {c['text']}; border-color: {c['accent']};
                }}
                QPushButton:checked {{
                    color: #FFFFFF; background: {c['accent']};
                    border-color: {c['accent']};
                }}
            """)

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        page = QWidget()
        page.setObjectName("page")
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        header = QVBoxLayout()
        eyebrow = QLabel("KICAD  /  SCHEMATIC TOOL")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("CubeMX Net Labels")
        title.setObjectName("title")
        subtitle = QLabel("Turn pinout data into clean, connected schematic labels.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        header.addWidget(eyebrow)
        header.addWidget(title)
        header.addWidget(subtitle)
        header.setSpacing(3)
        layout.addLayout(header)
        layout.addSpacing(4)

        files = self._card(layout, "01   PROJECT FILES",
                           "Choose your source data and destination.")
        self.csv_path = self._file_row(files, 2, "CubeMX CSV", self._browse_csv)
        self.input_path = self._file_row(
            files, 3, "Input schematic", self._browse_input)
        self.input_path.editingFinished.connect(self._load_references)
        self.output_path = self._file_row(
            files, 4, "Output schematic", self._browse_output)

        target = self._card(
            layout, "02   TARGET",
            "Select the symbol reference and source column for net names.")
        target_grid = target.layout()
        self.reference = QComboBox()
        self.reference.setEditable(True)
        self.reference.addItem("U1")
        self.reference.setFixedWidth(180)
        self.reference.setToolTip("Choose a reference found in the input schematic.")
        self.column = QComboBox()
        self.column.addItems(("Label", "Signal", "Name"))
        self.column.setFixedWidth(180)
        target_fields = QGridLayout()
        target_fields.setHorizontalSpacing(12)
        target_fields.setVerticalSpacing(8)
        self._field(target_fields, 0, "Select reference", self.reference, 0)
        self._field(target_fields, 0, "Net-name column", self.column, 1)
        target_fields.setColumnStretch(0, 1)
        target_fields.setColumnStretch(1, 1)
        target_grid.addLayout(target_fields, 2, 0, 1, 2)

        routing = self._card(
            layout, "03   ROUTING", "Control grid alignment and wire length (mils).")
        routing_grid = routing.layout()
        self.grid_size = QDoubleSpinBox()
        self.grid_size.setRange(1, 100000)
        self.grid_size.setDecimals(0)
        self.grid_size.setValue(100)
        self.grid_size.setFixedWidth(180)
        self.length_mode = QComboBox()
        self.length_mode.addItems(("Auto fit", "Custom"))
        self.length_mode.setFixedWidth(180)
        self.net_length = QComboBox()
        self.net_length.setEditable(True)
        self.net_length.addItems(
            ("100", "200", "300", "400", "500", "600", "700", "800", "900", "1000")
        )
        self.net_length.setCurrentText("300")
        self.net_length.lineEdit().setValidator(QIntValidator(1, 100000, self))
        self.net_length.setToolTip("Custom net length in mils")
        self.net_length.setFixedWidth(180)
        routing_fields = QGridLayout()
        routing_fields.setHorizontalSpacing(12)
        routing_fields.setVerticalSpacing(8)
        self._field(routing_fields, 0, "Grid size (mils)", self.grid_size, 0)
        length_label = QLabel("Net length")
        length_label.setObjectName("muted")
        routing_fields.addWidget(length_label, 0, 1)
        routing_fields.addWidget(self.length_mode, 1, 1)
        length_value_label = QLabel("Length (mils)")
        length_value_label.setObjectName("muted")
        routing_fields.addWidget(length_value_label, 2, 1)
        routing_fields.addWidget(self.net_length, 3, 1)
        length_value_label.setVisible(False)
        self.net_length.setVisible(False)
        self.length_mode.currentTextChanged.connect(
            lambda mode: (
                length_value_label.setVisible(mode == "Custom"),
                self.net_length.setVisible(mode == "Custom"),
            ))
        routing_fields.setColumnStretch(0, 1)
        routing_fields.setColumnStretch(1, 1)
        routing_grid.addLayout(routing_fields, 2, 0, 1, 2)
        note = QLabel(
            "Auto fit sizes each stub to the label text (minimum 300 mils); "
            "custom endpoints snap to the grid.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        routing_grid.addWidget(note, 3, 0, 1, 2)

        appearance = self._card(
            layout, "04   APPEARANCE", "Choose the label font and text style.")
        appearance_grid = appearance.layout()
        families = self._installed_fonts()
        reserved_font_names = {"default font", "kicad font"}
        families = [
            family for family in families
            if family.casefold() not in reserved_font_names
        ]
        self.font_name = QComboBox()
        self.font_name.addItems(["Default Font", "KiCad Font", *families])
        self.font_name.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font_name.setMinimumContentsLength(20)
        self.font_name.setMaxVisibleItems(20)
        self.font_name.setCurrentIndex(0)
        self.font_name.setFixedWidth(180)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(0.1, 100000)
        self.font_size.setDecimals(1)
        self.font_size.setValue(50)
        self.font_size.setFixedWidth(180)
        self.auto_thickness = QCheckBox("Automatic font thickness")
        self.auto_thickness.setChecked(True)
        self.font_thickness = QDoubleSpinBox()
        self.font_thickness.setRange(0.1, 100000)
        self.font_thickness.setDecimals(1)
        self.font_thickness.setValue(6)
        self.font_thickness.setFixedWidth(180)
        self.font_thickness.setEnabled(False)
        self.auto_thickness.toggled.connect(
            lambda enabled: self.font_thickness.setEnabled(not enabled))
        appearance_fields = QGridLayout()
        appearance_fields.setHorizontalSpacing(12)
        appearance_fields.setVerticalSpacing(8)
        self._field(appearance_fields, 0, "Font", self.font_name, 0)
        self._field(appearance_fields, 0, "Font size (mils)", self.font_size, 1)
        self._field(appearance_fields, 2, "Thickness (mils)", self.font_thickness, 0)
        appearance_fields.addWidget(self.auto_thickness, 4, 0, 1, 2)
        appearance_fields.setColumnStretch(0, 1)
        appearance_fields.setColumnStretch(1, 1)
        appearance_grid.addLayout(appearance_fields, 2, 0, 1, 2)

        styles = QHBoxLayout()
        styles.setSpacing(1)
        styles.addStretch(1)
        self.font_style_buttons = {}
        for key, label in (
                ("bold", "Bold"),
                ("italic", "Italic")):
            button = QPushButton()
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(30)
            button.setToolTip(label)
            styles.addWidget(button)
            self.font_style_buttons[key] = button
        self._style_font_buttons()
        styles.addStretch(1)
        appearance_grid.addLayout(styles, 3, 0, 1, 2)

        checks = self._card(
            layout, "05   PIN CHECKS", "CSV fallback behavior.")
        self.fallback_signal = QCheckBox("Fall back to Signal when Label is empty")
        self.fallback_name = QCheckBox("Fall back to Name when selected value is empty")
        checks.layout().addWidget(self.fallback_signal, 2, 0, 1, 2)
        checks.layout().addWidget(self.fallback_name, 3, 0, 1, 2)

        actions = QHBoxLayout()
        self.run_button = QPushButton("Generate schematic   →")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self._run)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.open_folder_button = QPushButton("Open output folder")
        self.open_folder_button.setToolTip("Show the output schematic in your file manager")
        self.open_folder_button.clicked.connect(self._open_output_folder)
        actions.addWidget(self.run_button, 1)
        actions.addWidget(self.progress)
        actions.addWidget(self.open_folder_button)
        layout.addLayout(actions)
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        self.show_preview = QCheckBox("Show preview")
        self.show_preview.setChecked(True)
        if not HAVE_SVG:
            self.show_preview.setChecked(False)
            self.show_preview.setEnabled(False)
            self.show_preview.setToolTip("QtSvgWidgets is not available in this PySide6 install")
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.show_preview)
        layout.addLayout(status_row)

        activity = self._card(layout, "ACTIVITY", "Generation output and validation.")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        activity.layout().addWidget(self.log, 2, 0, 1, 2)

        self.preview_card = self._card(
            layout, "PREVIEW",
            "Rendered output. Mouse wheel zooms, drag pans, double-click fits the sheet.")
        self.preview_view = PreviewView()
        self.preview_card.layout().addWidget(self.preview_view, 2, 0, 1, 2)
        fit_button = QPushButton("Fit to window")
        fit_button.clicked.connect(lambda _checked=False: self.preview_view.fit())
        self.preview_card.layout().addWidget(fit_button, 3, 0, 1, 2)
        self.preview_card.hide()
        layout.addStretch(1)

    def _card(self, parent_layout, title, subtitle):
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 13, 16, 15)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        section = QLabel(title)
        section.setObjectName("section")
        description = QLabel(subtitle)
        description.setObjectName("muted")
        description.setWordWrap(True)
        grid.addWidget(section, 0, 0, 1, 2)
        grid.addWidget(description, 1, 0, 1, 2)
        if parent_layout is not None:
            parent_layout.addWidget(card)
        return card

    @staticmethod
    def _installed_fonts():
        families = set(QFontDatabase.families())
        if not families and sys.platform == "win32":
            import winreg

            registry_paths = (
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER,
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            )
            for hive, key_path in registry_paths:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        for index in range(winreg.QueryInfoKey(key)[1]):
                            name, _value, _kind = winreg.EnumValue(key, index)
                            family = re.sub(
                                r"\s+\((?:TrueType|OpenType|All Res)\)$",
                                "", name, flags=re.IGNORECASE).strip()
                            if family:
                                families.add(family)
                except OSError:
                    continue
        return sorted(families, key=str.casefold)

    @staticmethod
    def _field(grid, row, label, widget, column):
        caption = QLabel(label)
        caption.setObjectName("muted")
        grid.addWidget(caption, row, column)
        grid.addWidget(widget, row + 1, column)
        grid.setColumnStretch(column, 1)

    def _file_row(self, card, row, label, callback):
        grid = card.layout()
        caption = QLabel(label)
        caption.setObjectName("muted")
        entry = QLineEdit()
        entry.setClearButtonEnabled(True)
        button = QPushButton("Browse…")
        button.clicked.connect(callback)
        grid.addWidget(caption, row, 0)
        grid.addWidget(entry, row, 1)
        grid.addWidget(button, row, 2)
        grid.setColumnStretch(1, 1)
        return entry

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CubeMX CSV", self._project_directory,
            "CSV files (*.csv);;All files (*)")
        if path:
            self.csv_path.setText(path)

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select input schematic", self._project_directory,
            "KiCad schematic (*.kicad_sch);;All files (*)")
        if path:
            self.input_path.setText(path)
            source = Path(path)
            suggested = str(source.with_name(
                source.stem + "_labeled" + source.suffix))
            current = self.output_path.text().strip()
            # Fill/refresh the name unless the user typed their own output path
            if not current or current == self._auto_output:
                self.output_path.setText(suggested)
                self._auto_output = suggested
            self._load_references()

    def _load_references(self):
        schematic = self.input_path.text().strip()
        if not schematic or not Path(schematic).is_file():
            return
        resolved_path = str(Path(schematic).resolve())
        if self.reference_process is not None:
            if (self.reference_process.state()
                    != QProcess.ProcessState.NotRunning
                    and resolved_path == self._reference_path_pending):
                return
            previous_process = self.reference_process
            self.reference_process = None
            self._reference_path_pending = None
            previous_process.blockSignals(True)
            if previous_process.state() != QProcess.ProcessState.NotRunning:
                previous_process.kill()
                previous_process.waitForFinished(1000)
            previous_process.deleteLater()
        if resolved_path == self._reference_path_loaded:
            return

        self._append_log(f"\nReading symbol references from:\n{schematic}\n")
        self.status.setText("Reading symbol references…")
        process = QProcess(self)
        program, arguments = cli_process_command([
            "--list-references", schematic,
        ])
        process.setProgram(program)
        process.setArguments(arguments)
        process.setProcessEnvironment(self._child_environment())
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.finished.connect(
            lambda code, status, current=process, path=resolved_path:
            self._references_finished(current, path, code, status)
            if current is self.reference_process else None)
        process.errorOccurred.connect(
            lambda error, current=process:
            self._references_process_error(current, error))
        self.reference_process = process
        self._reference_path_pending = resolved_path
        process.start()

    def _references_finished(self, process, path, exit_code, _exit_status):
        if process is not self.reference_process:
            return
        stdout = bytes(process.readAllStandardOutput()).decode(
            "utf-8", errors="replace")
        stderr = bytes(process.readAllStandardError()).decode(
            "utf-8", errors="replace")
        process.deleteLater()
        self.reference_process = None
        self._reference_path_pending = None
        if stderr:
            self._append_log(stderr)
        if exit_code != 0:
            self.status.setText(
                f"Could not read references (exit code {exit_code})")
            self._append_log("Failed to read symbol references.\n")
            return

        references = [line.strip() for line in stdout.splitlines() if line.strip()]
        previous = self.reference.currentText().strip()
        self.reference.clear()
        self.reference.addItems(references)
        if previous in references:
            self.reference.setCurrentText(previous)
        elif references:
            self.reference.setCurrentIndex(0)
        else:
            self.reference.setCurrentText("")
        self._reference_path_loaded = path
        self.status.setText(f"Found {len(references)} reference(s)")
        self._append_log(
            "Found symbol references: "
            + (", ".join(references) if references else "(none)")
            + "\n")

    def _references_process_error(self, process, error):
        if (process is not self.reference_process
                or error != QProcess.ProcessError.FailedToStart):
            return
        self.reference_process = None
        self._reference_path_pending = None
        self.status.setText("Could not start schematic reader")
        self._append_log(
            "Could not start reference reader: "
            + process.errorString() + "\n")
        process.deleteLater()

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save output schematic", "", "KiCad schematic (*.kicad_sch)")
        if path:
            if not Path(path).suffix:
                path += ".kicad_sch"
            self.output_path.setText(path)

    def _append_log(self, text):
        if text:
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
            self.log.insertPlainText(text)
            self.log.ensureCursorVisible()

    def _run(self):
        csv_path = self.csv_path.text().strip()
        input_path = self.input_path.text().strip()
        output_path = self.output_path.text().strip()
        reference = self.reference.currentText().strip()
        if not all((csv_path, input_path, output_path, reference)):
            QMessageBox.critical(
                self, "Missing information",
                "Choose the CSV, input and output schematics, and symbol reference.")
            return
        if not Path(csv_path).is_file() or not Path(input_path).is_file():
            QMessageBox.critical(
                self, "File not found", "The selected CSV or input schematic does not exist.")
            return
        if Path(input_path).resolve() == Path(output_path).resolve():
            QMessageBox.critical(
                self, "Invalid output",
                "Choose an output path different from the input schematic.")
            return
        if Path(output_path).exists():
            answer = QMessageBox.question(
                self, "Overwrite output?",
                f"Replace the existing file?\n{output_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return

        if not self.auto_thickness.isChecked() and self.font_thickness.value() <= 0:
            QMessageBox.critical(
                self, "Invalid font thickness",
                "Font thickness must be greater than zero mils.")
            self.font_thickness.setFocus()
            return
        self._save_settings()

        net_length_text = self.net_length.currentText().strip()
        if self.length_mode.currentText() == "Custom" and (
            not net_length_text.isdecimal()
            or not 1 <= int(net_length_text) <= 100000
        ):
            QMessageBox.critical(
                self,
                "Invalid net length",
                "Enter a custom net length between 1 and 100000 mils.",
            )
            self.net_length.setFocus()
            return
        command = build_cli_arguments(
            csv_path=csv_path,
            schematic_path=input_path,
            output_path=output_path,
            reference=reference,
            column=self.column.currentText(),
            net_length_mils=(
                "auto"
                if self.length_mode.currentText() == "Auto fit"
                else int(net_length_text)
            ),
            grid_mils=self.grid_size.value(),
            font_size_mils=self.font_size.value(),
            font_face=(
                "" if self.font_name.currentText() == "Default Font"
                else self.font_name.currentText()
            ),
            font_thickness_mils=self.font_thickness.value(),
            auto_thickness=self.auto_thickness.isChecked(),
            bold=self.font_style_buttons["bold"].isChecked(),
            italic=self.font_style_buttons["italic"].isChecked(),
            fallback_signal=self.fallback_signal.isChecked(),
            fallback_name=self.fallback_name.isChecked(),
        )

        self.run_button.setEnabled(False)
        self.progress.show()
        self.status.setText("Generating schematic…")
        program, arguments = cli_process_command(command)
        self._append_log("\nRunning:\n" + subprocess.list2cmdline(
            [program, *arguments]) + "\n\n")

        self.process = QProcess(self)
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        self.process.setProcessEnvironment(self._child_environment())
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.process.start()

    @staticmethod
    def _child_environment():
        """Let the module CLI find this package when it is not pip-installed."""
        env = QProcessEnvironment.systemEnvironment()
        root = str(Path(__file__).resolve().parent.parent)
        existing = env.value("PYTHONPATH")
        env.insert("PYTHONPATH", root + (os.pathsep + existing if existing else ""))
        return env

    # ------------------------------------------------------------ settings
    @staticmethod
    def _settings():
        return QSettings("CubeNetLabels", "NetLabelGuiMils")

    def _save_settings(self):
        s = self._settings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("theme", self.theme_name)
        s.setValue("csv_path", self.csv_path.text().strip())
        s.setValue("input_path", self.input_path.text().strip())
        s.setValue("output_path", self.output_path.text().strip())
        s.setValue("reference", self.reference.currentText().strip())
        s.setValue("column", self.column.currentText())
        s.setValue("grid", self.grid_size.value())
        s.setValue("length_mode", self.length_mode.currentText())
        s.setValue("net_length", self.net_length.currentText().strip())
        s.setValue("font_name", self.font_name.currentText())
        s.setValue("font_size", self.font_size.value())
        s.setValue("font_thickness", self.font_thickness.value())
        s.setValue("auto_thickness", self.auto_thickness.isChecked())
        for key, button in self.font_style_buttons.items():
            s.setValue(f"font_{key}", button.isChecked())
        s.setValue("fallback_signal", self.fallback_signal.isChecked())
        s.setValue("fallback_name", self.fallback_name.isChecked())
        s.setValue("show_preview", self.show_preview.isChecked())

    @staticmethod
    def _set_combo(combo, text):
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _restore_settings(self):
        s = self._settings()
        geometry = s.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        theme = s.value("theme", self.theme_name, type=str)
        if theme in self.THEMES and theme != self.theme_name:
            self._apply_theme(theme)

        input_text = s.value("input_path", "", type=str)
        output_text = s.value("output_path", "", type=str)
        self.csv_path.setText(s.value("csv_path", "", type=str))
        self.input_path.setText(input_text)
        self.output_path.setText(output_text)
        if input_text:
            source = Path(input_text)
            auto = str(source.with_name(source.stem + "_labeled" + source.suffix))
            if output_text == auto:
                self._auto_output = auto

        reference = s.value("reference", "", type=str)
        if reference:
            self.reference.setCurrentText(reference)
        self._set_combo(self.column, s.value("column", "", type=str))
        self.grid_size.setValue(s.value("grid", 100, type=float))
        self._set_combo(self.length_mode, s.value("length_mode", "", type=str))
        net_length = s.value("net_length", "", type=str)
        if net_length:
            self.net_length.setCurrentText(net_length)
        self._set_combo(self.font_name, s.value("font_name", "", type=str))
        self.font_size.setValue(s.value("font_size", 50, type=float))
        self.font_thickness.setValue(s.value("font_thickness", 6, type=float))
        self.auto_thickness.setChecked(
            s.value("auto_thickness", True, type=bool))
        for key, button in self.font_style_buttons.items():
            button.setChecked(s.value(f"font_{key}", False, type=bool))
        self.fallback_signal.setChecked(
            s.value("fallback_signal", False, type=bool))
        self.fallback_name.setChecked(
            s.value("fallback_name", False, type=bool))
        if HAVE_SVG:
            self.show_preview.setChecked(s.value("show_preview", True, type=bool))

        if input_text and Path(input_text).is_file():
            self._load_references()

    # ------------------------------------------------------------ output folder
    def _open_output_folder(self):
        text = self.output_path.text().strip()
        if not text:
            QMessageBox.information(
                self, "No output", "Choose an output schematic first.")
            return
        path = Path(text)
        if not path.parent.is_dir():
            QMessageBox.warning(
                self, "Folder not found", f"The folder does not exist:\n{path.parent}")
            return
        try:
            if path.is_file():
                if sys.platform == "win32":          # open Explorer with the file selected
                    subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
                    return
                if sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", str(path)])
                    return
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    # ------------------------------------------------------------ svg preview
    def _load_preview(self):
        if self._preview_dir is None:
            self._append_log("Preview: no temporary export directory exists.\n")
            return
        files = sorted(self._preview_dir.glob("*.svg"))
        if not files:
            self._append_log("Preview: KiCad CLI did not produce an SVG file.\n")
            return
        item = QGraphicsSvgItem(str(files[0]))
        if not item.renderer().isValid():
            self._append_log(f"Preview: could not render {files[0]}\n")
            return
        scene = self.preview_view.preview_scene
        scene.clear()
        scene.addItem(item)
        scene.setSceneRect(item.boundingRect())
        self.preview_card.show()
        self.preview_view.fit()

    def _start_preview_export(self):
        if not (HAVE_SVG and self.show_preview.isChecked()):
            self._show_completion()
            return
        cli = find_kicad_cli()
        if cli is None:
            self.status.setText("Schematic generated; preview unavailable")
            self._append_log("Preview skipped: kicad-cli was not found.\n")
            self._show_completion()
            return
        if self._preview_dir is not None:
            shutil.rmtree(self._preview_dir, ignore_errors=True)
        self._preview_dir = Path(tempfile.mkdtemp(prefix="cubemx-kicad-preview-"))
        self.preview_view.preview_scene.clear()
        self.preview_card.hide()
        process = QProcess(self)
        process.setProgram(cli)
        process.setArguments([
            "sch", "export", "svg", "--output", str(self._preview_dir),
            self.output_path.text().strip(),
        ])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.finished.connect(self._preview_export_finished)
        process.errorOccurred.connect(self._preview_export_error)
        self.preview_process = process
        self.status.setText("Rendering schematic preview…")
        self._append_log("Exporting SVG preview with kicad-cli.\n")
        process.start()

    def _preview_export_finished(self, exit_code, _exit_status):
        process = self.preview_process
        if process is None:
            return
        stdout = bytes(process.readAllStandardOutput()).decode(
            "utf-8", errors="replace")
        stderr = bytes(process.readAllStandardError()).decode(
            "utf-8", errors="replace")
        if stdout:
            self._append_log(stdout)
        if stderr:
            self._append_log(stderr)
        process.deleteLater()
        self.preview_process = None
        if exit_code == 0:
            self._load_preview()
            self.status.setText("Schematic generated successfully")
        else:
            self.status.setText("Schematic generated; SVG preview failed")
            self._append_log(f"SVG export failed (exit code {exit_code}).\n")
        self._show_completion()

    def _preview_export_error(self, error):
        process = self.preview_process
        if process is None or error != QProcess.ProcessError.FailedToStart:
            return
        self._append_log(f"Could not start SVG export: {process.errorString()}\n")
        process.deleteLater()
        self.preview_process = None
        self.status.setText("Schematic generated; preview unavailable")
        self._show_completion()

    def _show_completion(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Complete")
        box.setText("Schematic generated successfully.")
        open_button = box.addButton(
            "Open output folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is open_button:
            self._open_output_folder()

    def _read_stdout(self):
        self._append_log(bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"))

    def _read_stderr(self):
        self._append_log(bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="replace"))

    def _process_finished(self, exit_code, _exit_status):
        if self.process is None:
            return
        self._read_stdout()
        self._read_stderr()
        self.run_button.setEnabled(True)
        self.progress.hide()
        if exit_code == 0:
            self.status.setText("Schematic generated successfully")
            self._start_preview_export()
        else:
            self.status.setText(f"Generation failed (exit code {exit_code})")
            QMessageBox.critical(
                self, "Generation failed",
                f"The script exited with code {exit_code}. See the activity log.")
        self.process = None

    def _process_error(self, error):
        if self.process and error == QProcess.ProcessError.FailedToStart:
            self.run_button.setEnabled(True)
            self.progress.hide()
            self.status.setText("Could not start the generator")
            QMessageBox.critical(
                self, "Could not start generator",
                self.process.errorString())
            self.process = None

    def closeEvent(self, event):
        self._save_settings()
        for attribute in ("process", "reference_process", "preview_process"):
            process = getattr(self, attribute)
            if process is None:
                continue
            process.blockSignals(True)
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
            process.deleteLater()
            setattr(self, attribute, None)
        if self._preview_dir is not None:
            shutil.rmtree(self._preview_dir, ignore_errors=True)
            self._preview_dir = None
        super().closeEvent(event)


def launch(project_directory=None):
    app = QApplication.instance() or QApplication(sys.argv)
    window = NetLabelGui(project_directory=project_directory)
    window.show()
    if QApplication.instance() is app:
        app.exec()


if __name__ == "__main__":
    launch()
