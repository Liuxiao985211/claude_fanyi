"""
系统托盘管理器
提供任务栏托盘图标、右键菜单（暂停/恢复、设置、退出）。
"""

from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtGui import QIcon, QFont, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction


class TrayManager(QObject):
    """
    系统托盘管理器。
    创建托盘图标，提供右键上下文菜单。
    """

    # 信号
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    show_window_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self._tray_icon: QSystemTrayIcon = None
        self._paused = False

        # 菜单项引用
        self._pause_action: QAction = None
        self._show_original_action: QAction = None
        self._mode_action_ocr: QAction = None
        self._mode_action_audio: QAction = None
        self._mode_action_hybrid: QAction = None

        self._setup_tray_icon()

    def _setup_tray_icon(self):
        """创建系统托盘图标和菜单"""
        self._tray_icon = QSystemTrayIcon(self)

        # 创建图标（先用空白图标，后续可替换为自定义图标）
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(0, 180, 100))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.setBrush(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "译")
        painter.end()

        self._tray_icon.setIcon(QIcon(pixmap))
        self._tray_icon.setToolTip("Clude翻译App - 运行中")
        self._tray_icon.setVisible(True)

        # 创建菜单
        self._setup_context_menu()

        # 双击托盘图标显示/隐藏窗口
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _setup_context_menu(self):
        """创建右键菜单"""
        menu = QMenu()

        # 显示/隐藏窗口
        show_action = menu.addAction("显示/隐藏翻译窗口")
        show_action.triggered.connect(self.show_window_requested.emit)

        menu.addSeparator()

        # 暂停/恢复
        self._pause_action = menu.addAction("⏸ 暂停翻译")
        self._pause_action.triggered.connect(self._on_pause_toggle)

        menu.addSeparator()

        # 原文显示切换
        self._show_original_action = menu.addAction("✅ 显示原文")
        self._show_original_action.setCheckable(True)
        self._show_original_action.setChecked(True)
        self._show_original_action.triggered.connect(self._on_toggle_original)

        menu.addSeparator()

        # 翻译模式子菜单
        mode_menu = menu.addMenu("翻译模式")
        self._mode_action_hybrid = mode_menu.addAction("混合模式 (推荐)")
        self._mode_action_hybrid.setCheckable(True)
        self._mode_action_hybrid.setChecked(True)
        self._mode_action_ocr = mode_menu.addAction("仅OCR字幕")
        self._mode_action_ocr.setCheckable(True)
        self._mode_action_audio = mode_menu.addAction("仅音频识别")
        self._mode_action_audio.setCheckable(True)

        self._mode_action_hybrid.triggered.connect(
            lambda: self._on_mode_change("hybrid")
        )
        self._mode_action_ocr.triggered.connect(
            lambda: self._on_mode_change("ocr")
        )
        self._mode_action_audio.triggered.connect(
            lambda: self._on_mode_change("audio")
        )

        menu.addSeparator()

        # 退出
        exit_action = menu.addAction("退出")
        exit_action.triggered.connect(self.exit_requested.emit)

        self._tray_icon.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()

    def _on_pause_toggle(self):
        """切换暂停/恢复状态"""
        self._paused = not self._paused
        if self._paused:
            self._pause_action.setText("▶ 恢复翻译")
            self._tray_icon.setToolTip("Clude翻译App - 已暂停")
            self.pause_requested.emit()
        else:
            self._pause_action.setText("⏸ 暂停翻译")
            self._tray_icon.setToolTip("Clude翻译App - 运行中")
            self.resume_requested.emit()

    def _on_toggle_original(self, checked):
        """切换原文显示"""
        if checked:
            self._show_original_action.setText("✅ 显示原文")
        else:
            self._show_original_action.setText("☐ 隐藏原文")

    def _on_mode_change(self, mode: str):
        """切换翻译模式"""
        self._mode_action_ocr.setChecked(mode == "ocr")
        self._mode_action_audio.setChecked(mode == "audio")
        self._mode_action_hybrid.setChecked(mode == "hybrid")

    def update_pause_state(self, paused: bool):
        """更新暂停状态（由外部调用）"""
        self._paused = paused
        if paused:
            self._pause_action.setText("▶ 恢复翻译")
            self._tray_icon.setToolTip("Clude翻译App - 已暂停")
        else:
            self._pause_action.setText("⏸ 暂停翻译")
            self._tray_icon.setToolTip("Clude翻译App - 运行中")

    def show_notification(self, title: str, message: str):
        """显示系统通知"""
        if self._tray_icon and self._tray_icon.supportsMessages():
            self._tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    @property
    def is_paused(self):
        return self._paused

    @property
    def tray_icon(self):
        return self._tray_icon

