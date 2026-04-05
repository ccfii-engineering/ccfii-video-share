"""PySide6 desktop control panel for CCFII Display Share."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QGuiApplication, QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    QApplication = None
    QComboBox = None
    QFont = None
    QFrame = None
    QGridLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QGuiApplication = None
    QImage = None
    QLabel = None
    QLineEdit = None
    QMainWindow = object
    QMessageBox = None
    QPlainTextEdit = None
    QPushButton = None
    QPixmap = None
    QScrollArea = None
    QSizePolicy = None
    QSplitter = None
    Qt = None
    QTimer = None
    QVBoxLayout = None
    QWidget = None

from .capture import (
    CaptureTarget,
    build_capture_targets,
    capture_preview_image,
    list_monitors,
    list_windows,
    resolve_capture_backend,
)
from .config import APP_COLORS, APP_NAME
from .manager import BroadcastManager


def format_target_option(target: CaptureTarget) -> str:
    if target.kind == "desktop":
        return f"{target.label}"
    return f"{target.label} (Window)"


def parse_int_setting(raw_value: str, default: int,
                      minimum: int, maximum: int) -> int:
    value = raw_value.strip()
    if not value:
        return default
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"Value must be between {minimum} and {maximum}.")
    return parsed


def build_status_text(status: dict[str, object]) -> str:
    error_text = str(status.get("error") or "").strip()
    if error_text:
        return (
            "Broadcast stopped because capture failed.\n"
            "Review the diagnostics panel for FFmpeg details, then refresh the source or restart the broadcast."
        )

    if not status.get("is_running"):
        return "Ready to broadcast. Select a source and start sharing to the local network."

    viewer_count = int(status.get("viewer_count", 0))
    viewer_noun = "device" if viewer_count == 1 else "devices"
    target_label = str(status.get("target_label") or "Selected source")
    viewer_url = str(status.get("viewer_url") or "")
    return (
        f"Broadcasting live from {target_label}.\n"
        f"{viewer_count} {viewer_noun} connected.\n"
        f"Receivers can connect at {viewer_url}."
    )


def build_preview_caption(target: CaptureTarget | None) -> str:
    if target is None:
        return ""
    if target.kind == "desktop":
        return target.label
    return target.title or target.label


def build_capability_summary(capabilities) -> str:
    if capabilities is None:
        return "Capabilities unavailable."

    lines = []
    lines.append("Display capture: enabled" if capabilities.display_capture else "Display capture unavailable")
    lines.append("Window capture: enabled" if capabilities.window_capture else "Window capture unavailable")
    lines.append("Preview capture: enabled" if capabilities.preview_capture else "Preview capture unavailable")
    if capabilities.permissions_required:
        lines.append("Permissions required: " + ", ".join(capabilities.permissions_required))
    if capabilities.notes:
        lines.extend(capabilities.notes)
    return "\n".join(lines)


def build_diagnostics_copy_text(status: dict[str, object]) -> str:
    backend_name = str(status.get("backend_name") or "unknown")
    capabilities = status.get("capabilities")
    error = str(status.get("error") or "none")
    lines = [
        f"Backend: {backend_name}",
        f"Error: {error}",
    ]
    if capabilities is not None:
        lines.append(build_capability_summary(capabilities))
    return "\n".join(lines)


def build_preflight_capability_summary(backend_name: str, capabilities) -> str:
    preface = f"Backend: {backend_name}" if backend_name else "Backend: unknown"
    if capabilities is None:
        return f"{preface}\nCapabilities unavailable."
    return f"{preface}\n{build_capability_summary(capabilities)}"


def calculate_preview_size(
    source_width: int,
    source_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    safe_width = max(1, max_width)
    safe_height = max(1, max_height)
    if source_width <= 0 or source_height <= 0:
        return safe_width, safe_height
    scale = min(safe_width / source_width, safe_height / source_height)
    return max(1, int(source_width * scale)), max(1, int(source_height * scale))


def calculate_logo_size(
    source_width: int,
    source_height: int,
    window_width: int,
) -> tuple[int, int]:
    max_size = max(48, min(72, int(window_width * 0.06)))
    return calculate_preview_size(source_width, source_height, max_size, max_size)


def build_stylesheet() -> str:
    return f"""
        QMainWindow {{
            background: {APP_COLORS['background']};
        }}
        QScrollArea#appRoot {{ background: transparent; border: none; }}
        QScrollArea#appRoot QWidget#appRoot {{ background: transparent; }}
        QWidget#appRoot, QWidget#headerTextWrap, QWidget#rightPanel {{
            background: transparent;
            color: {APP_COLORS['foreground']};
            font-family: 'Segoe UI';
            font-size: 14px;
        }}
        QLabel {{
            background: transparent;
            color: {APP_COLORS['foreground']};
        }}
        QFrame#card {{
            background: {APP_COLORS['surface']};
            border: 1px solid {APP_COLORS['border']};
            border-radius: 18px;
        }}
        QFrame#subCard {{
            background: {APP_COLORS['surface_alt']};
            border: 1px solid {APP_COLORS['border']};
            border-radius: 16px;
        }}
        QLabel#eyebrow, QLabel#fieldLabel {{
            color: {APP_COLORS['accent']};
            font-weight: 700;
            font-size: 12px;
        }}
        QLabel#title {{
            font-size: 22px;
            font-weight: 800;
        }}
        QLabel#subtitle, QLabel#bodyMuted {{
            color: {APP_COLORS['muted']};
        }}
        QLabel#sectionTitle {{
            font-size: 18px;
            font-weight: 800;
        }}
        QLabel#bodyStrong, QLabel#metricValue {{
            font-weight: 600;
        }}
        QLabel#statusBadge {{
            background: {APP_COLORS['primary']};
            color: {APP_COLORS['foreground']};
            border-radius: 12px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 700;
        }}
        QLabel#previewImage {{
            background: {APP_COLORS['background']};
            border-radius: 14px;
            border: 1px solid {APP_COLORS['border']};
            padding: 12px;
        }}
        QLineEdit, QComboBox, QPlainTextEdit {{
            background: {APP_COLORS['background']};
            border: 1px solid {APP_COLORS['border']};
            border-radius: 12px;
            padding: 10px 12px;
            min-height: 22px;
        }}
        QPlainTextEdit#diagnosticsOutput {{
            font-family: 'Cascadia Mono';
            font-size: 12px;
        }}
        QPushButton {{
            background: {APP_COLORS['primary']};
            color: {APP_COLORS['foreground']};
            border: none;
            border-radius: 12px;
            padding: 12px 18px;
            font-weight: 700;
        }}
        QPushButton:hover {{
            background: {APP_COLORS['primary_hover']};
        }}
        QPushButton[secondary="true"] {{
            background: {APP_COLORS['surface_alt']};
            border: 1px solid {APP_COLORS['border']};
        }}
        QPushButton[secondary="true"]:hover {{
            background: {APP_COLORS['border']};
        }}
        QPushButton[accent="true"] {{
            background: {APP_COLORS['accent']};
            color: #2d1408;
        }}
        QPushButton[accent="true"]:hover {{
            background: {APP_COLORS['success']};
        }}
        QPushButton[compact="true"] {{
            padding: 8px 12px;
        }}
        QPushButton#primaryButton {{
            padding: 16px 20px;
            font-size: 16px;
        }}
        QGroupBox {{
            background: transparent;
            border: 1px solid {APP_COLORS['border']};
            border-radius: 14px;
            margin-top: 10px;
            padding: 16px 16px 10px 16px;
            font-weight: 600;
            font-size: 13px;
            color: {APP_COLORS['muted']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: {APP_COLORS['accent']};
        }}
        QGroupBox::indicator {{
            width: 12px;
            height: 12px;
        }}
        QGroupBox::indicator:unchecked {{
            border: 2px solid {APP_COLORS['muted']};
            border-radius: 3px;
            background: transparent;
        }}
        QGroupBox::indicator:checked {{
            border: 2px solid {APP_COLORS['accent']};
            border-radius: 3px;
            background: {APP_COLORS['accent']};
        }}
        QFrame#stripDivider {{
            background: {APP_COLORS['border']};
            border: none;
        }}
        QPushButton#collapseHeader {{
            background: transparent;
            border: none;
            border-bottom: 1px solid {APP_COLORS['border']};
            border-radius: 0;
            color: {APP_COLORS['muted']};
            font-size: 12px;
            font-weight: 600;
            padding: 8px 4px;
            text-align: left;
        }}
        QPushButton#collapseHeader:hover {{
            color: {APP_COLORS['foreground']};
            background: {APP_COLORS['surface_alt']};
        }}
        QWidget#collapseBody {{
            background: transparent;
        }}
        QSplitter::handle {{
            background: transparent;
        }}
        QSplitter::handle:horizontal {{
            width: 3px;
        }}
        QSplitter::handle:vertical {{
            height: 10px;
            image: none;
        }}
    """


class DisplayShareDesktopApp(QMainWindow):
    """Responsive Qt desktop operator console."""

    def __init__(self):
        if QApplication is None:
            raise RuntimeError("PySide6 is not available in this Python environment.")
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.setMinimumSize(640, 480)

        self.targets: list[CaptureTarget] = []
        self.target_lookup: dict[str, CaptureTarget] = {}
        self.manager: BroadcastManager | None = None
        self.preview_path = Path(tempfile.gettempdir()) / "ccfii-display-share-preview.png"
        self.preview_pixmap: QPixmap | None = None
        self.logo_pixmap: QPixmap | None = None
        self.diagnostic_lines: list[str] = []
        self._last_runtime_error = ""
        self.backend = resolve_capture_backend()

        self._build_ui()
        self.refresh_targets(initial=True)
        self._start_status_timer()
        self._apply_styles()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("appRoot")
        self.setCentralWidget(scroll)

        root = QWidget()
        root.setObjectName("appRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(10)
        scroll.setWidget(root)

        outer.addWidget(self._build_header())

        # Top area: left/right panels in a horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setOpaqueResize(True)
        self.main_splitter.setHandleWidth(14)
        self.main_splitter.addWidget(self._build_left_panel())
        self.main_splitter.addWidget(self._build_right_panel())
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([380, 600])

        # Paint a drag indicator on the horizontal splitter handle
        h_handle = self.main_splitter.handle(1)
        h_handle.setCursor(Qt.CursorShape.SizeHorCursor)
        h_handle_layout = QVBoxLayout(h_handle)
        h_handle_layout.setContentsMargins(0, 0, 0, 0)
        h_grip = QLabel("\u2022\n\u2022\n\u2022")
        h_grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_grip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        h_grip.setStyleSheet(f"color: {APP_COLORS['muted']}; font-size: 10px; background: transparent;")
        h_handle_layout.addWidget(h_grip)

        outer.addWidget(self._build_info_panel())

        # Vertical splitter: main content on top, diagnostics on bottom (draggable)
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.setHandleWidth(14)
        self.vertical_splitter.addWidget(self.main_splitter)
        self.vertical_splitter.addWidget(self._build_diagnostics_panel())
        self.vertical_splitter.setSizes([500, 200])
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 0)
        outer.addWidget(self.vertical_splitter, 1)

        # Paint a drag indicator on the vertical splitter handle
        handle = self.vertical_splitter.handle(1)
        handle.setCursor(Qt.CursorShape.SizeVerCursor)
        handle_layout = QHBoxLayout(handle)
        handle_layout.setContentsMargins(0, 0, 0, 0)
        grip_label = QLabel("\u2022 \u2022 \u2022")
        grip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grip_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        grip_label.setStyleSheet(f"color: {APP_COLORS['muted']}; font-size: 10px; background: transparent;")
        handle_layout.addWidget(grip_label)

        self._last_orientation = Qt.Orientation.Horizontal

    def _build_header(self):
        card = self._card_frame()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("logoLabel")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = Path(__file__).resolve().parents[1] / "assets" / "ccfii-logo.png"
        if logo_path.exists():
            self.logo_pixmap = QPixmap(str(logo_path))
            self._render_logo()
        layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        text_wrap = QWidget()
        text_wrap.setObjectName("headerTextWrap")
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        eyebrow = QLabel("Christ Charismatic Fellowship Int'l, Inc.")
        eyebrow.setObjectName("eyebrow")
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Local network display broadcast for sanctuary and event operations")
        subtitle.setObjectName("subtitle")

        text_layout.addWidget(eyebrow)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        layout.addWidget(text_wrap, 1)

        self.status_badge = QLabel("Status: Ready")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_left_panel(self):
        card = self._card_frame()
        card.setMinimumWidth(200)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        heading = QLabel("Broadcast Control")
        heading.setObjectName("sectionTitle")
        intro = QLabel("Choose what to share, then start the local broadcast.")
        intro.setWordWrap(True)
        intro.setObjectName("bodyMuted")
        layout.addWidget(heading)
        layout.addWidget(intro)

        source_label = QLabel("Source")
        source_label.setObjectName("fieldLabel")
        layout.addWidget(source_label)

        source_row = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self.refresh_preview)
        self.source_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        source_row.addWidget(self.source_combo, 1)

        refresh_sources_button = self._button("Refresh Sources", self.refresh_targets, secondary=True)
        source_row.addWidget(refresh_sources_button)
        layout.addLayout(source_row)

        self.primary_button = self._button("Start Broadcast", self.toggle_broadcast)
        self.primary_button.setObjectName("primaryButton")
        layout.addWidget(self.primary_button)

        link_card = self._sub_card()
        link_layout = QVBoxLayout(link_card)
        link_layout.setContentsMargins(16, 16, 16, 16)
        link_layout.setSpacing(10)
        link_title = QLabel("Receiver Link")
        link_title.setObjectName("fieldLabel")
        link_layout.addWidget(link_title)

        link_row = QHBoxLayout()
        self.viewer_url_input = QLineEdit("Not live yet")
        self.viewer_url_input.setReadOnly(True)
        link_row.addWidget(self.viewer_url_input, 1)
        link_row.addWidget(self._button("Copy Link", self.copy_viewer_link, accent=True, compact=True))
        link_layout.addLayout(link_row)
        layout.addWidget(link_card)

        av_card, av_body, _ = self._collapsible_card("AV Controls")

        av_grid = QGridLayout()
        av_grid.setHorizontalSpacing(12)
        av_grid.setVerticalSpacing(10)

        self.port_input = QLineEdit("8080")
        self.fps_input = QLineEdit("30")
        self.quality_input = QLineEdit("5")
        for row, (label_text, widget) in enumerate([
            ("Port", self.port_input),
            ("Frames Per Second", self.fps_input),
            ("JPEG Quality", self.quality_input),
        ]):
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            av_grid.addWidget(label, row, 0)
            av_grid.addWidget(widget, row, 1)
        av_body.addLayout(av_grid)
        layout.addWidget(av_card)
        layout.addStretch(1)
        return card

    def _build_right_panel(self):
        container = QWidget()
        container.setObjectName("rightPanel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- Source Preview (hero element) ---
        preview_card = self._card_frame()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 10, 12, 10)
        preview_layout.setSpacing(4)

        preview_header = QHBoxLayout()
        preview_header.setSpacing(8)
        preview_title = QLabel("Source Preview")
        preview_title.setObjectName("sectionTitle")
        preview_header.addWidget(preview_title)
        preview_header.addStretch(1)
        preview_header.addWidget(self._button("Refresh", self.refresh_preview, secondary=True, compact=True))
        preview_layout.addLayout(preview_header)

        self.preview_image_label = QLabel("No preview")
        self.preview_image_label.setObjectName("previewImage")
        self.preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image_label.setMinimumHeight(160)
        self.preview_image_label.setWordWrap(True)
        self.preview_image_label.setScaledContents(False)
        self.preview_image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        preview_layout.addWidget(self.preview_image_label, 1)

        self.preview_caption_label = QLabel(build_preview_caption(None))
        self.preview_caption_label.setObjectName("bodyMuted")
        self.preview_caption_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_caption_label)

        self.preview_status_label = QLabel("")
        self.preview_status_label.setObjectName("bodyMuted")
        self.preview_status_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_status_label)
        layout.addWidget(preview_card, 1)

        # --- Compact status strip ---
        status_strip = self._card_frame()
        strip_layout = QVBoxLayout(status_strip)
        strip_layout.setContentsMargins(12, 8, 12, 8)
        strip_layout.setSpacing(4)

        self.status_title = QLabel("Ready")
        self.status_title.setObjectName("bodyStrong")
        strip_layout.addWidget(self.status_title)

        self.status_text = QLabel("Select a source to begin.")
        self.status_text.setObjectName("bodyMuted")
        self.status_text.setWordWrap(True)
        strip_layout.addWidget(self.status_text)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)
        devices_label = QLabel("Devices:")
        devices_label.setObjectName("fieldLabel")
        self.viewer_count_label = QLabel("0")
        self.viewer_count_label.setObjectName("metricValue")
        link_label = QLabel("Link:")
        link_label.setObjectName("fieldLabel")
        self.current_link_label = QLabel("Not live yet")
        self.current_link_label.setObjectName("metricValue")
        metrics_row.addWidget(devices_label)
        metrics_row.addWidget(self.viewer_count_label)
        metrics_row.addWidget(link_label)
        metrics_row.addWidget(self.current_link_label, 1)
        strip_layout.addLayout(metrics_row)

        layout.addWidget(status_strip)

        return container

    def _build_info_panel(self):
        card, body_layout, _ = self._collapsible_card("Backend & Operator Info")

        self.capability_summary_label = QLabel("Capabilities unavailable.")
        self.capability_summary_label.setObjectName("bodyMuted")
        self.capability_summary_label.setWordWrap(True)
        body_layout.addWidget(self.capability_summary_label)

        notes_body = QLabel(
            "Receivers must be on the same local network. "
            "Stream link works in any browser. "
            "Receivers auto-reconnect if the feed drops."
        )
        notes_body.setObjectName("bodyMuted")
        notes_body.setWordWrap(True)
        body_layout.addWidget(notes_body)

        return card

    def _build_diagnostics_panel(self):
        card, body_layout, header_btn = self._collapsible_card("Diagnostics", expanded=True)
        self._diag_body = body_layout.parentWidget()
        self._diag_expanded_size = 200

        # Override the toggle to also adjust the vertical splitter
        original_toggle = header_btn.clicked
        header_btn.clicked.disconnect()

        def toggle_diagnostics():
            body = self._diag_body
            show = not body.isVisible()
            body.setVisible(show)
            header_btn.setText(f"  \u25bc  Diagnostics" if show else f"  \u25b6  Diagnostics")
            if show:
                self.vertical_splitter.setSizes([500, self._diag_expanded_size])
            else:
                self._diag_expanded_size = max(100, self.vertical_splitter.sizes()[1])
                self.vertical_splitter.setSizes([1, 0])

        header_btn.clicked.connect(toggle_diagnostics)

        header = QHBoxLayout()
        header.addStretch(1)
        header.addWidget(self._button("Copy", self.copy_diagnostics, secondary=True, compact=True))
        body_layout.addLayout(header)

        self.diagnostics_output = QPlainTextEdit()
        self.diagnostics_output.setObjectName("diagnosticsOutput")
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setPlaceholderText("Runtime logs will appear here.")
        body_layout.addWidget(self.diagnostics_output, 1)
        return card

    def _metric(self, layout: QVBoxLayout, label: str, value: str):
        title = QLabel(label)
        title.setObjectName("fieldLabel")
        body = QLabel(value)
        body.setObjectName("metricValue")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)
        return body

    def _collapsible_card(self, title: str, expanded: bool = False):
        """Build a card with a clickable header that toggles body visibility."""
        card = self._card_frame()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        arrow = "\u25bc" if expanded else "\u25b6"
        header_btn = QPushButton(f"  {arrow}  {title}")
        header_btn.setObjectName("collapseHeader")
        header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        outer.addWidget(header_btn)

        body = QWidget()
        body.setObjectName("collapseBody")
        body.setVisible(expanded)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 6, 14, 10)
        body_layout.setSpacing(6)
        outer.addWidget(body)

        def toggle():
            show = not body.isVisible()
            body.setVisible(show)
            header_btn.setText(f"  \u25bc  {title}" if show else f"  \u25b6  {title}")

        header_btn.clicked.connect(toggle)
        return card, body_layout, header_btn

    def _card_frame(self):
        frame = QFrame()
        frame.setObjectName("card")
        return frame

    def _sub_card(self):
        frame = QFrame()
        frame.setObjectName("subCard")
        return frame

    def _button(self, text: str, handler, secondary: bool = False, accent: bool = False, compact: bool = False):
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if compact:
            button.setProperty("compact", True)
        if secondary:
            button.setProperty("secondary", True)
        if accent:
            button.setProperty("accent", True)
        button.clicked.connect(handler)
        return button

    def _apply_styles(self):
        self.setStyleSheet(build_stylesheet())

    def _start_status_timer(self):
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status_ui)
        self.status_timer.start(1500)

    def refresh_targets(self, initial: bool = False):
        try:
            monitors = list_monitors()
            windows = list_windows()
        except Exception as exc:
            self._log(f"Source refresh failed: {exc}")
            if not initial and QMessageBox is not None:
                QMessageBox.critical(self, APP_NAME, f"Unable to refresh sources.\n\n{exc}")
            return

        self.targets = build_capture_targets(monitors, windows)
        labels = [format_target_option(target) for target in self.targets]
        self.target_lookup = dict(zip(labels, self.targets))

        current = self.source_combo.currentText()
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItems(labels)
        if labels:
            index = max(0, labels.index(current)) if current in labels else 0
            self.source_combo.setCurrentIndex(index)
        self.source_combo.blockSignals(False)
        self._log(f"Loaded {len(monitors)} displays and {len(windows)} windows.")
        self.refresh_preview()

    def _selected_target(self) -> CaptureTarget | None:
        return self.target_lookup.get(self.source_combo.currentText())

    def refresh_preview(self):
        target = self._selected_target()
        self.preview_caption_label.setText(build_preview_caption(target))
        if target is None:
            self.preview_pixmap = None
            self.preview_image_label.setText("Preview not loaded yet.")
            self.preview_image_label.setPixmap(QPixmap())
            self.preview_status_label.setText("Choose a source to see a snapshot preview.")
            return

        is_live = self.manager is not None and self.manager.is_healthy()
        if is_live:
            try:
                self.manager.switch_target(target)
                self._log(f"Switched live broadcast to {target.label}")
            except Exception as exc:
                self._log(f"Source switch failed: {exc}")

        try:
            self._log(f"Refreshing preview for {target.label}")
            preview_file = capture_preview_image(target, self.preview_path)
            self.preview_pixmap = QPixmap(str(preview_file))
            self._render_preview()
            if is_live:
                self.preview_status_label.setText("Source switched. Broadcast is now streaming this source.")
            else:
                self.preview_status_label.setText("Snapshot ready. Confirm the source, then switch or start the broadcast.")
            self._log(f"Preview ready for {target.label}")
        except Exception as exc:
            self.preview_pixmap = None
            self.preview_image_label.setPixmap(QPixmap())
            self.preview_image_label.setText("Preview unavailable")
            error_message = str(exc).strip()
            if hasattr(exc, "stderr") and exc.stderr:
                error_message = str(exc.stderr).strip()
            self.preview_status_label.setText(f"Unable to capture preview right now: {error_message}")
            self._log(f"Preview failed for {target.label}: {error_message}")

    def _render_preview(self):
        if self.preview_pixmap is None or self.preview_pixmap.isNull():
            return
        # Use the label's visible rect minus padding (12px each side)
        container = self.preview_image_label.contentsRect()
        available_width = max(200, container.width() - 24)
        available_height = max(120, container.height() - 24)
        width, height = calculate_preview_size(
            self.preview_pixmap.width(),
            self.preview_pixmap.height(),
            available_width,
            available_height,
        )
        pixmap = self.preview_pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_image_label.setPixmap(pixmap)
        self.preview_image_label.setText("")

    def _render_logo(self):
        if self.logo_pixmap is None or self.logo_pixmap.isNull():
            return
        width, height = calculate_logo_size(
            self.logo_pixmap.width(),
            self.logo_pixmap.height(),
            max(1, self.width()),
        )
        pixmap = self.logo_pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.logo_label.setPixmap(pixmap)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._render_logo()
        self._render_preview()
        self._update_responsive_layout()

    def _update_responsive_layout(self):
        width = self.width()
        BREAKPOINT = 900
        if width < BREAKPOINT and self._last_orientation != Qt.Orientation.Vertical:
            self.main_splitter.setOrientation(Qt.Orientation.Vertical)
            self._last_orientation = Qt.Orientation.Vertical
        elif width >= BREAKPOINT and self._last_orientation != Qt.Orientation.Horizontal:
            self.main_splitter.setOrientation(Qt.Orientation.Horizontal)
            self.main_splitter.setSizes([380, 600])
            self._last_orientation = Qt.Orientation.Horizontal

    def toggle_broadcast(self):
        if self.manager is not None:
            status = self.manager.get_status()
            if status["is_running"]:
                self.stop_broadcast()
                return
            self.stop_broadcast()
        self.start_broadcast()

    def start_broadcast(self):
        target = self._selected_target()
        if target is None:
            QMessageBox.warning(self, APP_NAME, "Choose a display or window before starting the broadcast.")
            return
        try:
            port = parse_int_setting(self.port_input.text(), 8080, 1024, 65535)
            fps = parse_int_setting(self.fps_input.text(), 30, 1, 60)
            quality = parse_int_setting(self.quality_input.text(), 5, 1, 31)
        except ValueError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        try:
            self.manager = BroadcastManager(
                targets=self.targets,
                port=port,
                fps=fps,
                quality=quality,
            )
            self.manager.start(target)
        except Exception as exc:
            self.manager = None
            self._log(f"Broadcast start failed: {exc}")
            self._last_runtime_error = str(exc)
            self.status_badge.setText("Status: Capture Error")
            self.status_title.setText("Broadcast interrupted")
            self.status_text.setText(
                build_status_text({
                    "is_running": False,
                    "error": str(exc),
                })
            )
            self.viewer_url_input.setText("Not live yet")
            self.current_link_label.setText("Not live yet")
            QMessageBox.critical(self, APP_NAME, f"Unable to start the broadcast.\n\n{exc}")
            return

        self._log(f"Broadcast started for {target.label} on http://{self.manager.lan_ip_fn()}:{port}")
        self.primary_button.setText("Stop Broadcast")
        self.primary_button.setProperty("accent", True)
        self.primary_button.style().unpolish(self.primary_button)
        self.primary_button.style().polish(self.primary_button)
        self.status_badge.setText("Status: Broadcasting")
        self.status_title.setText("Broadcast live on local network")
        self._refresh_status_ui()

    def stop_broadcast(self):
        if self.manager is None:
            return
        self._log("Broadcast stopped by operator.")
        self.manager.stop()
        self.manager = None
        self.primary_button.setText("Start Broadcast")
        self.primary_button.setProperty("accent", False)
        self.primary_button.style().unpolish(self.primary_button)
        self.primary_button.style().polish(self.primary_button)
        self.status_badge.setText("Status: Ready")
        self.status_title.setText("Ready for service")
        self.status_text.setText(build_status_text({"is_running": False}))
        self.viewer_url_input.setText("Not live yet")
        self.viewer_count_label.setText("0")
        self.current_link_label.setText("Not live yet")

    def copy_viewer_link(self):
        value = self.viewer_url_input.text()
        if not value.startswith("http"):
            return
        if QGuiApplication is not None:
            QGuiApplication.clipboard().setText(value)
        self.status_badge.setText("Status: Link Copied")
        self._log(f"Viewer link copied: {value}")

    def copy_diagnostics(self):
        if QGuiApplication is None:
            return
        value = self.diagnostics_output.toPlainText()
        if self.manager is not None:
            prefix = build_diagnostics_copy_text(self.manager.get_status())
            value = f"{prefix}\n\n{value}" if value else prefix
        else:
            prefix = build_preflight_capability_summary(
                getattr(self.backend, "name", "unknown"),
                self.backend.get_capabilities() if self.backend is not None else None,
            )
            value = f"{prefix}\n\n{value}" if value else prefix
        QGuiApplication.clipboard().setText(value)
        self._log("Diagnostics copied to clipboard.")

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.diagnostic_lines.append(line)
        self.diagnostic_lines = self.diagnostic_lines[-400:]
        if hasattr(self, "diagnostics_output"):
            self.diagnostics_output.setPlainText("\n".join(self.diagnostic_lines))
            scrollbar = self.diagnostics_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _refresh_status_ui(self):
        if self.manager is None:
            self.status_text.setText(build_status_text({"is_running": False}))
            self.capability_summary_label.setText(
                build_preflight_capability_summary(
                    getattr(self.backend, "name", "unknown"),
                    self.backend.get_capabilities() if self.backend is not None else None,
                )
            )
            return
        status = self.manager.get_status()
        self.capability_summary_label.setText(
            build_capability_summary(status.get("capabilities"))
        )
        if status["is_running"]:
            self.status_badge.setText("Status: Broadcasting")
            self.status_title.setText("Broadcast live on local network")
        elif status.get("error"):
            self.status_badge.setText("Status: Capture Error")
            self.status_title.setText("Broadcast interrupted")
            error_key = str(status["error"])
            if getattr(self, "_last_runtime_error", "") != error_key:
                self._log(f"Capture error: {status['error']}")
                self._last_runtime_error = error_key
            self.primary_button.setText("Start Broadcast")
            self.primary_button.setProperty("accent", False)
            self.primary_button.style().unpolish(self.primary_button)
            self.primary_button.style().polish(self.primary_button)
        else:
            self.status_badge.setText("Status: Ready")
            self.status_title.setText("Ready for service")
            self._last_runtime_error = ""
        self.status_text.setText(build_status_text(status))
        viewer_url = str(status["viewer_url"]) if status["is_running"] else "Not live yet"
        self.viewer_url_input.setText(viewer_url)
        self.viewer_count_label.setText(str(status["viewer_count"]))
        self.current_link_label.setText(viewer_url)

    def closeEvent(self, event):  # noqa: N802
        if self.manager is not None:
            self.manager.stop()
        super().closeEvent(event)


def launch_app():
    if QApplication is None:
        raise RuntimeError("PySide6 is not available in this Python environment.")
    app = QApplication.instance() or QApplication([])
    if QFont is not None:
        app.setFont(QFont("Segoe UI", 10))
    window = DisplayShareDesktopApp()
    window.show()
    app.exec()
