"""
J.A.R.V.I.S. Floating UI Widget
A compact, always-on-top assistant widget with voice settings panel.
"""

import sys
import math
import random
import subprocess
import re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QComboBox, QSlider, QPushButton, QLineEdit, QScrollArea, QFrame
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, pyqtSlot, QPoint, QRectF
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QRadialGradient,
    QLinearGradient, QPainterPath, QMouseEvent
)

import config


# ─── Colors ──────────────────────────────────────────────────────────────────

class Colors:
    # Iron Man HUD palette — gold + cyan
    BG_DARK = QColor(8, 10, 18, 240)
    BG_PANEL = QColor(14, 18, 30, 230)
    HUD_GOLD = QColor(255, 190, 70)        # Stark gold
    HUD_AMBER = QColor(255, 150, 30)
    HUD_CYAN = QColor(80, 220, 255)        # Arc reactor cyan
    ARC_CYAN = QColor(80, 220, 255)
    ARC_BLUE = QColor(60, 120, 255)
    TEXT_PRIMARY = QColor(255, 210, 130)   # gold text
    TEXT_SECONDARY = QColor(180, 140, 80)
    ACCENT_GREEN = QColor(60, 255, 140)    # listening indicator
    ACCENT_ORANGE = QColor(255, 160, 40)
    ACCENT_RED = QColor(255, 60, 60)
    RING_IDLE = QColor(120, 90, 40, 180)   # dim gold ring


# ─── Stylesheet ──────────────────────────────────────────────────────────────

COMBO_STYLE = """
QComboBox {
    background: #1a2040;
    color: #b4c8f0;
    border: 1px solid #2a3a5a;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}
QComboBox::drop-down { border: none; }
QComboBox::down-arrow { image: none; border: none; }
QComboBox QAbstractItemView {
    background: #141828;
    color: #b4c8f0;
    selection-background-color: #1a3060;
    border: 1px solid #2a3a5a;
}
"""

SLIDER_STYLE = """
QSlider::groove:horizontal {
    height: 4px;
    background: #1a2040;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #00c8ff;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #00c8ff;
    border-radius: 2px;
}
"""

BUTTON_STYLE = """
QPushButton {
    background: #1a2848;
    color: #b4c8f0;
    border: 1px solid #2a3a5a;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 10px;
}
QPushButton:hover {
    background: #1a3060;
    border-color: #00c8ff;
}
"""

INPUT_STYLE = """
QLineEdit {
    background: #1a2040;
    color: #b4c8f0;
    border: 1px solid #2a3a5a;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}
QLineEdit:focus {
    border-color: #00c8ff;
}
"""


# ─── Arc Reactor Core ────────────────────────────────────────────────────────

class ArcReactor(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._angle = 0
        self._angle2 = 0
        self._pulse = 0.0
        self._state = "idle"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(50)  # 20fps — smoother feel, less CPU than 30ms

    def set_state(self, state):
        if state != self._state:
            self._state = state
            # Re-render once immediately on state change
            self.update()

    def _animate(self):
        # Slower when idle to save CPU
        speed = 2 if self._state == "idle" else 4
        self._angle = (self._angle + speed) % 360
        self._angle2 = (self._angle2 - speed * 0.7) % 360
        self._pulse = (self._pulse + 0.08) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        radius = 32
        pulse_factor = 0.5 + 0.5 * math.sin(self._pulse)

        if self._state == "listening":
            main_color = Colors.ACCENT_GREEN
            glow_alpha = int(180 + 60 * pulse_factor)
            ring_width = 3.5
        elif self._state == "processing":
            main_color = Colors.HUD_AMBER
            glow_alpha = int(120 + 80 * pulse_factor)
            ring_width = 3.0
        elif self._state == "speaking":
            main_color = Colors.HUD_CYAN
            glow_alpha = int(160 + 80 * pulse_factor)
            ring_width = 3.5
        else:
            main_color = Colors.HUD_GOLD
            glow_alpha = int(60 + 40 * pulse_factor)
            ring_width = 2.5

        # ── Outer glow ──
        glow_color = QColor(main_color.red(), main_color.green(), main_color.blue(), glow_alpha)
        gradient = QRadialGradient(cx, cy, radius + 14)
        gradient.setColorAt(0.55, glow_color)
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - radius - 14, cy - radius - 14, (radius + 14) * 2, (radius + 14) * 2))

        # ── Background disk ──
        painter.setBrush(QBrush(Colors.BG_DARK))
        painter.setPen(QPen(Colors.RING_IDLE, 1.2))
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        # ── Outer HUD tick marks (Iron Man reticle) ──
        tick_pen = QPen(Colors.HUD_GOLD, 1.2)
        painter.setPen(tick_pen)
        for i in range(12):
            ang = math.radians(i * 30)
            r1 = radius + 1
            r2 = radius + (6 if i % 3 == 0 else 3)
            x1 = cx + r1 * math.cos(ang)
            y1 = cy + r1 * math.sin(ang)
            x2 = cx + r2 * math.cos(ang)
            y2 = cy + r2 * math.sin(ang)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # ── Dual rotating arcs (counter-rotating) ──
        pen = QPen(main_color, ring_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        arc_rect = QRectF(cx - radius + 5, cy - radius + 5, (radius - 5) * 2, (radius - 5) * 2)
        painter.drawArc(arc_rect, self._angle * 16, 110 * 16)
        painter.drawArc(arc_rect, (self._angle + 180) * 16, 110 * 16)

        # ── Inner counter-rotating thin arc ──
        pen2 = QPen(Colors.HUD_CYAN if self._state == "idle" else main_color, 1.2)
        painter.setPen(pen2)
        arc_rect2 = QRectF(cx - radius + 12, cy - radius + 12, (radius - 12) * 2, (radius - 12) * 2)
        painter.drawArc(arc_rect2, self._angle2 * 16, 70 * 16)
        painter.drawArc(arc_rect2, (self._angle2 + 180) * 16, 70 * 16)

        # ── Arc reactor core (inner glow) ──
        inner_r = 11
        inner_gradient = QRadialGradient(cx, cy, inner_r)
        glow_center = Colors.HUD_CYAN if self._state == "idle" else main_color
        inner_gradient.setColorAt(0, QColor(255, 255, 255, 230))
        inner_gradient.setColorAt(0.4, QColor(glow_center.red(), glow_center.green(), glow_center.blue(), 220))
        inner_gradient.setColorAt(1, QColor(glow_center.red(), glow_center.green(), glow_center.blue(), 40))
        painter.setBrush(QBrush(inner_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))

        # ── Inner triangular segments (arc reactor signature) ──
        seg_pen = QPen(QColor(255, 255, 255, 200), 1.0)
        painter.setPen(seg_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(6):
            ang = math.radians(i * 60 + self._angle2 * 0.5)
            x = cx + (inner_r - 1) * math.cos(ang)
            y = cy + (inner_r - 1) * math.sin(ang)
            painter.drawLine(int(cx), int(cy), int(x), int(y))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ─── Status Label ────────────────────────────────────────────────────────────

class StatusLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Normal))
        self.setStyleSheet("color: #ffb862; background: transparent; letter-spacing: 1px;")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._full_text = ""
        self._current_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._type_next)

    def set_text_animated(self, text, instant=False):
        self._full_text = text
        if instant or len(text) < 2:
            self.setText(text)
            self._timer.stop()
        else:
            self._current_index = 0
            self.setText("")
            self._timer.start(20)

    def _type_next(self):
        self._current_index += 2  # 2 chars at a time for speed
        self.setText(self._full_text[:self._current_index])
        if self._current_index >= len(self._full_text):
            self._timer.stop()


# ─── Voice Settings Panel ───────────────────────────────────────────────────

class VoiceSettingsPanel(QWidget):
    """Collapsible voice settings panel."""

    voice_changed = pyqtSignal(str)  # voice name
    rate_changed = pyqtSignal(int)   # rate value
    api_key_changed = pyqtSignal(str)

    def __init__(self, speech_engine=None, parent=None):
        super().__init__(parent)
        self._speech_engine = speech_engine
        self._init_ui()
        self._load_voices()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)

        # --- Voice Profile selector ---
        profile_row = QHBoxLayout()
        profile_label = QLabel("Profile")
        profile_label.setFont(QFont("SF Pro Text", 9))
        profile_label.setStyleSheet("color: #556080; background: transparent;")
        profile_label.setFixedWidth(42)
        profile_row.addWidget(profile_label)

        self._profile_combo = QComboBox()
        self._profile_combo.setStyleSheet(COMBO_STYLE)
        self._profile_combo.setMaximumHeight(28)
        self._load_profiles()
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self._profile_combo)

        layout.addLayout(profile_row)

        # Profile description
        self._profile_desc = QLabel("")
        self._profile_desc.setFont(QFont("SF Pro Text", 9))
        self._profile_desc.setStyleSheet("color: #445070; background: transparent; padding-left: 44px;")
        self._profile_desc.setWordWrap(True)
        self._update_profile_desc()
        layout.addWidget(self._profile_desc)

        # --- Voice selector ---
        voice_row = QHBoxLayout()
        voice_label = QLabel("Voice")
        voice_label.setFont(QFont("SF Pro Text", 9))
        voice_label.setStyleSheet("color: #556080; background: transparent;")
        voice_label.setFixedWidth(42)
        voice_row.addWidget(voice_label)

        self._voice_combo = QComboBox()
        self._voice_combo.setStyleSheet(COMBO_STYLE)
        self._voice_combo.setMaximumHeight(28)
        self._voice_combo.currentTextChanged.connect(self._on_voice_changed)
        voice_row.addWidget(self._voice_combo)

        # Test button
        self._test_btn = QPushButton("Test")
        self._test_btn.setStyleSheet(BUTTON_STYLE)
        self._test_btn.setFixedSize(40, 28)
        self._test_btn.clicked.connect(self._test_voice)
        voice_row.addWidget(self._test_btn)

        layout.addLayout(voice_row)

        # --- Speed slider ---
        speed_row = QHBoxLayout()
        speed_label = QLabel("Speed")
        speed_label.setFont(QFont("SF Pro Text", 9))
        speed_label.setStyleSheet("color: #556080; background: transparent;")
        speed_label.setFixedWidth(42)
        speed_row.addWidget(speed_label)

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setStyleSheet(SLIDER_STYLE)
        self._speed_slider.setRange(100, 300)
        self._speed_slider.setValue(config.get("voice_rate"))
        self._speed_slider.valueChanged.connect(self._on_rate_changed)
        speed_row.addWidget(self._speed_slider)

        self._speed_value = QLabel(str(config.get("voice_rate")))
        self._speed_value.setFont(QFont("SF Pro Text", 9))
        self._speed_value.setStyleSheet("color: #78a0c8; background: transparent;")
        self._speed_value.setFixedWidth(28)
        speed_row.addWidget(self._speed_value)

        layout.addLayout(speed_row)

        # --- Claude API Key ---
        api_row = QHBoxLayout()
        api_label = QLabel("Claude")
        api_label.setFont(QFont("SF Pro Text", 9))
        api_label.setStyleSheet("color: #556080; background: transparent;")
        api_label.setFixedWidth(42)
        api_row.addWidget(api_label)

        self._api_input = QLineEdit()
        self._api_input.setStyleSheet(INPUT_STYLE)
        self._api_input.setMaximumHeight(28)
        self._api_input.setPlaceholderText("sk-ant-... (API key for smart replies)")
        self._api_input.setEchoMode(QLineEdit.EchoMode.Password)
        existing_key = config.get("claude_api_key")
        if existing_key:
            self._api_input.setText(existing_key)
        self._api_input.editingFinished.connect(self._on_api_key_changed)
        api_row.addWidget(self._api_input)

        # Status dot
        self._api_status = QLabel("●")
        self._api_status.setFont(QFont("SF Pro Text", 10))
        self._api_status.setFixedWidth(16)
        self._update_api_status()
        api_row.addWidget(self._api_status)

        layout.addLayout(api_row)

    def _load_voices(self):
        """Load available macOS voices into combo box."""
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        self._voice_combo.blockSignals(True)

        current_voice = config.get("voice_id")
        current_name = current_voice.split(".")[-1] if current_voice else "Daniel"

        english_voices = []
        other_voices = []
        for line in result.stdout.strip().split("\n"):
            match = re.match(r'^(.+?)\s{2,}(\S+)\s+#', line)
            if match:
                name = match.group(1).strip()
                lang = match.group(2).strip()
                if lang.startswith("en"):
                    english_voices.append(name)
                else:
                    other_voices.append(f"{name} [{lang}]")

        # Add English voices first, then others
        self._voice_combo.addItem("── English Voices ──")
        idx = 0
        self._voice_combo.model().item(idx).setEnabled(False)
        select_idx = 1

        for name in sorted(english_voices):
            idx += 1
            self._voice_combo.addItem(name)
            if name.lower() == current_name.lower():
                select_idx = idx

        if other_voices:
            idx += 1
            self._voice_combo.addItem("── Other Languages ──")
            self._voice_combo.model().item(idx).setEnabled(False)
            for name in sorted(other_voices):
                idx += 1
                self._voice_combo.addItem(name)

        self._voice_combo.setCurrentIndex(select_idx)
        self._voice_combo.blockSignals(False)

    def _on_voice_changed(self, name):
        # Strip language tag if present
        clean = re.sub(r'\s*\[.*?\]$', '', name).strip()
        if clean.startswith("──"):
            return
        config.set_key("voice_id", clean)
        self.voice_changed.emit(clean)
        if self._speech_engine:
            self._speech_engine.set_voice(clean)

    def _on_rate_changed(self, value):
        self._speed_value.setText(str(value))
        config.set_key("voice_rate", value)
        self.rate_changed.emit(value)
        if self._speech_engine:
            self._speech_engine.set_rate(value)

    def _on_api_key_changed(self):
        key = self._api_input.text().strip()
        config.set_key("claude_api_key", key)
        self._update_api_status()
        self.api_key_changed.emit(key)

    def _update_api_status(self):
        if config.get("claude_api_key"):
            self._api_status.setStyleSheet("color: #00ff8c; background: transparent;")
            self._api_status.setToolTip("Claude API connected")
        else:
            self._api_status.setStyleSheet("color: #556080; background: transparent;")
            self._api_status.setToolTip("No API key — add one for smart replies")

    def _load_profiles(self):
        """Load voice profiles into combo box."""
        from jarvis import SpeechEngine
        profiles = SpeechEngine.VOICE_PROFILES
        current = config.load_config().get("voice_profile", "zoro")

        self._profile_combo.blockSignals(True)
        select_idx = 0
        for i, (name, p) in enumerate(profiles.items()):
            display = name.replace("_", " ").title()
            self._profile_combo.addItem(display)
            if name == current:
                select_idx = i
        self._profile_combo.setCurrentIndex(select_idx)
        self._profile_combo.blockSignals(False)

    def _update_profile_desc(self):
        """Update the profile description label."""
        from jarvis import SpeechEngine
        current_text = self._profile_combo.currentText().lower().replace(" ", "_")
        profiles = SpeechEngine.VOICE_PROFILES
        if current_text in profiles:
            p = profiles[current_text]
            desc = p["description"]
            if p["pitch"] != 0:
                desc += f" | Pitch: {p['pitch']} | Bass: +{p['bass']} | Overdrive: {p['overdrive']}"
            self._profile_desc.setText(desc)

    def _on_profile_changed(self, display_name):
        profile_name = display_name.lower().replace(" ", "_")
        if self._speech_engine:
            self._speech_engine.set_profile(profile_name)
            self._speed_slider.blockSignals(True)
            self._speed_slider.setValue(self._speech_engine.get_rate())
            self._speed_value.setText(str(self._speech_engine.get_rate()))
            self._speed_slider.blockSignals(False)
        self._update_profile_desc()

    def _test_voice(self):
        """Test the current voice profile with sox pipeline."""
        if self._speech_engine:
            import threading
            threading.Thread(
                target=self._speech_engine.speak,
                args=("I'm going to be the world's greatest swordsman. Nothing happened.",),
                daemon=True
            ).start()
        else:
            name = re.sub(r'\s*\[.*?\]$', '', self._voice_combo.currentText()).strip()
            rate = self._speed_slider.value()
            subprocess.Popen(["say", "-v", name, "-r", str(rate), f"Hello, I am {name}. How do I sound?"])


# ─── Main Floating Widget ────────────────────────────────────────────────────

class JarvisWidget(QWidget):
    update_state_signal = pyqtSignal(str)
    update_status_signal = pyqtSignal(str)
    update_heard_signal = pyqtSignal(str)
    update_response_signal = pyqtSignal(str)
    activate_signal = pyqtSignal()

    def __init__(self, speech_engine=None):
        super().__init__()
        self._speech_engine = speech_engine
        self._dragging = False
        self._drag_offset = QPoint()
        self._settings_visible = False

        self._init_window()
        self._init_ui()
        self._connect_signals()
        self._position_top_right()

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(300)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(0)

        self._container = QWidget()
        self._container.setObjectName("container")
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(6)

        # --- Top row: Reactor + Title ---
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._reactor = ArcReactor()
        top_row.addWidget(self._reactor)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self._title = QLabel("J.A.R.V.I.S.")
        self._title.setFont(QFont("Helvetica Neue", 15, QFont.Weight.Bold))
        self._title.setStyleSheet("color: #ffbe46; background: transparent; letter-spacing: 4px;")
        title_col.addWidget(self._title)

        self._status_label = StatusLabel()
        self._status_label.setText("STANDBY — Say 'Jarvis'")
        title_col.addWidget(self._status_label)

        top_row.addLayout(title_col)
        top_row.addStretch()

        # Settings gear button
        self._gear_btn = QLabel("⚙")
        self._gear_btn.setFont(QFont("SF Pro Display", 14))
        self._gear_btn.setStyleSheet("color: #556080; background: transparent;")
        self._gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gear_btn.mousePressEvent = lambda e: self._toggle_settings()
        top_row.addWidget(self._gear_btn, alignment=Qt.AlignmentFlag.AlignTop)

        # Close button
        self._close_btn = QLabel("✕")
        self._close_btn.setFont(QFont("SF Pro Display", 12))
        self._close_btn.setStyleSheet("color: #556080; background: transparent;")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.mousePressEvent = lambda e: self.close()
        top_row.addWidget(self._close_btn, alignment=Qt.AlignmentFlag.AlignTop)

        container_layout.addLayout(top_row)

        # --- Separator ---
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.3 #2a3a5a, stop:0.7 #2a3a5a, stop:1 transparent);")
        container_layout.addWidget(sep)

        # --- BIG LISTENING banner ---
        self._listen_banner = QLabel("◉  LISTENING — SPEAK NOW")
        self._listen_banner.setFont(QFont("Helvetica Neue", 11, QFont.Weight.Bold))
        self._listen_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._listen_banner.setStyleSheet(
            "color: #3cff8c; background: rgba(60,255,140,0.12); "
            "border: 1px solid rgba(60,255,140,0.5); border-radius: 8px; "
            "padding: 6px; letter-spacing: 2px;"
        )
        self._listen_banner.setVisible(False)
        container_layout.addWidget(self._listen_banner)

        # Pulse timer for listening banner
        self._banner_pulse = 0
        self._banner_timer = QTimer(self)
        self._banner_timer.timeout.connect(self._pulse_banner)

        # --- "You said" area ---
        self._heard_label = QLabel("")
        self._heard_label.setFont(QFont("SF Mono", 10))
        self._heard_label.setStyleSheet("color: #5a7a5a; background: rgba(0,255,140,0.05); border-radius: 4px; padding: 3px 6px;")
        self._heard_label.setWordWrap(True)
        self._heard_label.setMaximumHeight(40)
        self._heard_label.setVisible(False)
        container_layout.addWidget(self._heard_label)

        # --- Response area ---
        self._response_label = QLabel("At your service, sir.")
        self._response_label.setFont(QFont("Helvetica Neue", 11))
        self._response_label.setStyleSheet("color: #ffd88a; background: transparent; padding: 4px 0px;")
        self._response_label.setWordWrap(True)
        self._response_label.setMaximumHeight(80)
        container_layout.addWidget(self._response_label)

        # --- Command hint ---
        self._hint_label = QLabel('Try: "What\'s the weather?" or "Open Chrome"')
        self._hint_label.setFont(QFont("SF Pro Text", 9))
        self._hint_label.setStyleSheet("color: #445070; background: transparent;")
        self._hint_label.setWordWrap(True)
        container_layout.addWidget(self._hint_label)

        # --- Voice Settings Panel (collapsible) ---
        self._settings_panel = VoiceSettingsPanel(speech_engine=self._speech_engine)
        self._settings_panel.setVisible(False)
        container_layout.addWidget(self._settings_panel)

        main_layout.addWidget(self._container)

    def _connect_signals(self):
        self.update_state_signal.connect(self._on_update_state)
        self.update_status_signal.connect(self._on_update_status)
        self.update_heard_signal.connect(self._on_update_heard)
        self.update_response_signal.connect(self._on_update_response)
        self._reactor.clicked.connect(self._on_reactor_clicked)

    def _position_top_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 12
        y = screen.top() + 12
        self.move(x, y)

    def _toggle_settings(self):
        self._settings_visible = not self._settings_visible
        self._settings_panel.setVisible(self._settings_visible)
        self._gear_btn.setStyleSheet(
            "color: #00c8ff; background: transparent;" if self._settings_visible
            else "color: #556080; background: transparent;"
        )
        self.adjustSize()

    # --- Paint rounded background ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._container.geometry().adjusted(-2, -2, 2, 2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 16, 16)

        gradient = QLinearGradient(rect.x(), rect.y(), rect.x(), rect.y() + rect.height())
        gradient.setColorAt(0, QColor(18, 22, 38, 235))
        gradient.setColorAt(1, QColor(10, 14, 28, 245))
        painter.fillPath(path, QBrush(gradient))

        border_gradient = QLinearGradient(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
        border_gradient.setColorAt(0, QColor(40, 60, 100, 120))
        border_gradient.setColorAt(0.5, QColor(0, 150, 200, 60))
        border_gradient.setColorAt(1, QColor(40, 60, 100, 120))
        painter.setPen(QPen(QBrush(border_gradient), 1.2))
        painter.drawPath(path)
        painter.end()

    # --- Dragging ---

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self.move(self.pos() + event.position().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False

    # --- Public API ---

    def set_state(self, state):
        self.update_state_signal.emit(state)

    def set_status(self, text):
        self.update_status_signal.emit(text)

    def set_heard(self, text):
        """Show what Jarvis heard from any thread."""
        self.update_heard_signal.emit(text)

    def set_response(self, text):
        self.update_response_signal.emit(text)

    @pyqtSlot(str)
    def _on_update_heard(self, text):
        if text:
            self._heard_label.setText(f'You: "{text}"')
            self._heard_label.setVisible(True)
            self._heard_label.setStyleSheet("color: #6aaa6a; background: rgba(0,255,140,0.06); border-radius: 4px; padding: 3px 6px;")
        else:
            self._heard_label.setVisible(False)
        self.adjustSize()

    @pyqtSlot(str)
    def _on_update_state(self, state):
        self._reactor.set_state(state)
        state_labels = {
            "idle": "STANDBY — Say 'Jarvis'",
            "listening": "◉ LISTENING — Speak now",
            "processing": "⟳ Processing...",
            "speaking": "▶ Speaking...",
        }
        self._status_label.set_text_animated(state_labels.get(state, state))

        # Show/hide big banner
        if state == "listening":
            self._listen_banner.setVisible(True)
            self._banner_timer.start(60)
        else:
            self._listen_banner.setVisible(False)
            self._banner_timer.stop()

        if state == "idle":
            # Fade the heard text after going idle
            if self._heard_label.isVisible():
                self._heard_label.setStyleSheet("color: #8a6a2a; background: rgba(255,190,70,0.04); border-radius: 4px; padding: 3px 6px;")

        if state == "listening":
            # Clear old heard text when starting to listen fresh
            self._heard_label.setText("")
            self._heard_label.setVisible(False)
            hints = [
                '"What\'s the weather?"', '"Set a timer for 5 minutes"',
                '"Open Spotify"', '"Tell me a joke"',
                '"List voices"', '"Change voice to Samantha"',
                '"Speak faster"', '"What is quantum computing?"',
            ]
            self._hint_label.setText(f"Try: {random.choice(hints)}")

    @pyqtSlot(str)
    def _on_update_status(self, text):
        self._status_label.set_text_animated(text)

    @pyqtSlot(str)
    def _on_update_response(self, text):
        display = text if len(text) <= 150 else text[:147] + "..."
        self._response_label.setText(display)

    def _on_reactor_clicked(self):
        self.activate_signal.emit()

    def _pulse_banner(self):
        """Pulse the LISTENING banner background for visual urgency."""
        try:
            if not self._listen_banner or not self._listen_banner.isVisible():
                return
            self._banner_pulse = (self._banner_pulse + 1) % 20
            t = abs(self._banner_pulse - 10) / 10.0  # 0..1..0 triangle
            # Use rgba with float syntax Qt accepts cleanly
            bg = 0.05 + 0.12 * t
            border = 0.45 + 0.50 * t
            self._listen_banner.setStyleSheet(
                f"color: #3cff8c; background: rgba(60,255,140,{bg:.2f}); "
                f"border: 1px solid rgba(60,255,140,{border:.2f}); "
                f"border-radius: 8px; padding: 6px; letter-spacing: 2px;"
            )
        except RuntimeError:
            # Widget was deleted
            self._banner_timer.stop()
