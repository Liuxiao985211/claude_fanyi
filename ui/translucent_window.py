"""
透明悬浮翻译窗口（核心UI组件）

特性：
- 无边框、始终置顶
- 背景完全透明，文字不透明（黄字黑边描边）
- 鼠标悬停：白色边框线 + 淡黑底条渐显；移开后渐隐
- 悬停时右上角显示控制条（▶ 开始/暂停 + ⚙ 设置）
- 鼠标拖动窗口任意位置
- 鼠标拖动边缘/角落调整大小
- Ctrl+滚轮调节字号
"""

import ctypes
from ctypes import wintypes

from PyQt5.QtCore import Qt, QPoint, QTimer, QVariantAnimation, pyqtSignal
from PyQt5.QtGui import (
    QMouseEvent, QWheelEvent, QPaintEvent,
    QPainter, QPen, QColor, QCursor,
)
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton

from ui.subtitle_display import SubtitleDisplay
from config.settings import AppSettings

# ---- Windows API 常量（用于 WM_NCHITTEST 边缘缩放） ----

WM_NCHITTEST = 0x0084

# Hit test 返回值
HTCAPTION = 2
HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# Windows API 结构体
class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class TranslucentWindow(QWidget):
    """
    透明悬浮翻译窗口。

    核心实现：
    1. FramelessWindowHint + WindowStaysOnTopHint + Tool → 无边框、置顶
    2. WA_TranslucentBackground → 背景透明
    3. paintEvent → 悬停时绘制白色边框线 + 淡黑底条
    4. QTimer 轮询鼠标位置 → 驱动边框/底条渐显渐隐
    5. nativeEvent 处理 WM_NCHITTEST → 边缘缩放 + 按钮点击穿透
    6. wheelEvent + Ctrl → 字号调节
    """

    # 信号：主控制器据此切换翻译状态 / 打开设置窗口
    start_pause_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()

    def __init__(self, settings: AppSettings):
        super().__init__()
        self._settings = settings
        self._dragging = False
        self._drag_offset = QPoint()
        self._resize_margin = 8  # 边缘缩放热区像素

        # 悬停渐显状态
        self._hover_opacity = 0.0   # 当前不透明度 0.0~1.0
        self._hover_target = 0.0    # 目标不透明度

        # 从配置加载
        self._font_size = settings.get("font_size", 16)

        self._init_ui()
        self._init_hover_effect()
        self._apply_window_settings()

    def _init_ui(self):
        """初始化UI组件"""
        # 设置透明背景
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 防止窗口抢焦点（看电影时不打断全屏）
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # 创建字幕显示组件
        self.subtitle_display = SubtitleDisplay(self)
        self.subtitle_display.set_font_size(self._font_size)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.subtitle_display)

        self.setLayout(layout)

        # ---- 悬停控制条按钮（右上角，平时隐藏） ----
        btn_style = """
            QPushButton {
                background-color: rgba(30, 30, 30, 160);
                color: white;
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(70, 70, 70, 200);
            }
        """
        self._btn_start = QPushButton("▶ 开始翻译", self)
        self._btn_start.setStyleSheet(btn_style)
        self._btn_start.setCursor(Qt.PointingHandCursor)
        self._btn_start.clicked.connect(self.start_pause_clicked.emit)

        self._btn_settings = QPushButton("⚙", self)
        self._btn_settings.setStyleSheet(btn_style)
        self._btn_settings.setCursor(Qt.PointingHandCursor)
        self._btn_settings.setToolTip("翻译API设置")
        self._btn_settings.clicked.connect(self.settings_clicked.emit)

        self._btn_start.hide()
        self._btn_settings.hide()

    def _init_hover_effect(self):
        """初始化悬停检测与渐显渐隐动画"""
        # 每 100ms 检查一次鼠标是否在窗口内。
        # 用轮询而不是 enter/leave 事件：窗口内部被注册为
        # Windows“标题栏区”（用于整窗拖动），Qt 的鼠标进出事件
        # 在此类窗口上不可靠，轮询鼠标坐标不依赖事件系统。
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._update_hover)
        self._hover_timer.start(100)

        # 透明度渐变动画（约 200ms 淡入/淡出）
        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setDuration(200)
        self._fade_anim.valueChanged.connect(self._on_fade_value)

    def _apply_window_settings(self):
        """应用窗口设置：置顶、无边框、初始位置"""
        # 设置窗口标志：无边框 + 置顶 + 工具窗口（不在任务栏显示）
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        # 窗口默认大小和位置
        geom = self._settings.default_window_geometry()
        self.setGeometry(geom)

        # 允许鼠标追踪（用于边缘光标切换）
        self.setMouseTracking(True)

    # ==================== 悬停效果 ====================

    def _update_hover(self):
        """轮询鼠标位置，更新悬停目标透明度"""
        if not self.isVisible():
            return
        inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self._set_hover_target(1.0 if inside else 0.0)

    def _set_hover_target(self, target: float):
        """切换悬停目标，并启动渐变动画"""
        if abs(target - self._hover_target) < 0.01:
            return
        self._hover_target = target
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._hover_opacity)
        self._fade_anim.setEndValue(target)
        self._fade_anim.start()

    def _on_fade_value(self, value):
        """动画进行中：更新不透明度并重绘"""
        self._hover_opacity = float(value)
        visible = self._hover_opacity > 0.05
        if visible != self._btn_start.isVisible():
            self._btn_start.setVisible(visible)
            self._btn_settings.setVisible(visible)
        self.update()

    def paintEvent(self, event: QPaintEvent):
        """
        绘制悬停效果：
        - 淡黑色半透明底条（辅助阅读，电影画面依然穿透）
        - 白色边框线（1像素）
        两者透明度随 _hover_opacity 变化。
        字幕文字由子组件在本方法之后绘制，永远压在底条上面。
        """
        if self._hover_opacity <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        op = self._hover_opacity

        # 淡黑底条（最淡约 60/255 ≈ 23%，保证电影画面穿透）
        painter.fillRect(self.rect(), QColor(0, 0, 0, int(60 * op)))

        # 白色边框线（最亮约 170/255）
        pen = QPen(QColor(255, 255, 255, int(170 * op)), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        painter.end()

    def resizeEvent(self, event):
        """窗口尺寸变化时，把控制条按钮保持在右上角"""
        super().resizeEvent(event)
        if not hasattr(self, "_btn_start"):
            return
        bw = self._btn_settings.sizeHint().width()
        sw = self._btn_start.sizeHint().width()
        self._btn_settings.move(self.width() - bw - 8, 6)
        self._btn_start.move(self.width() - bw - sw - 14, 6)

    # ==================== 公共接口 ====================

    def update_translation(self, translated: str):
        """更新最新一行译文（由翻译线程回调）"""
        self.subtitle_display.set_translation(translated)

    def clear_translation(self):
        """清空窗口上的译文（停止翻译时调用）"""
        self.subtitle_display.clear()

    def set_idle_mode(self, idle: bool):
        """待开始状态：显示/隐藏提示文字"""
        self.subtitle_display.set_idle_mode(idle)

    def set_idle_hint(self, text: str):
        """自定义待开始状态的提示文字（如“翻译服务不可用”）"""
        self.subtitle_display.set_idle_hint(text)

    def set_translation_state(self, state: str):
        """同步翻译状态（idle/running/paused），更新按钮文字"""
        labels = {
            "idle": "▶ 开始翻译",
            "running": "⏸ 暂停翻译",
            "paused": "▶ 恢复翻译",
        }
        self._btn_start.setText(labels.get(state, "▶ 开始翻译"))

    def set_font_size(self, size: int):
        """设置字号"""
        self._font_size = max(8, min(48, size))
        self.subtitle_display.set_font_size(self._font_size)
        self._settings.set("font_size", self._font_size)

    def get_font_size(self) -> int:
        return self._font_size

    # ==================== 鼠标事件：窗口拖动 ====================

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下：开始拖动（Qt 层面的兜底实现）"""
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动：拖动窗口或更新光标"""
        if self._dragging:
            # 拖动窗口
            new_pos = event.globalPos() - self._drag_offset
            self.move(new_pos)
            event.accept()
        else:
            # 更新光标（边缘缩放提示）
            self._update_cursor(event.pos())
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放：结束拖动"""
        if event.button() == Qt.LeftButton:
            self._dragging = False
            # 保存窗口位置
            g = self.geometry()
            self._settings.save_window_geometry(g.x(), g.y(), g.width(), g.height())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ==================== 滚轮事件：字号调节 ====================

    def wheelEvent(self, event: QWheelEvent):
        """Ctrl+滚轮调节字号"""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.set_font_size(self._font_size + 1)
            else:
                self.set_font_size(self._font_size - 1)
            event.accept()
        else:
            super().wheelEvent(event)

    # ==================== Windows原生事件：边缘缩放 + 按钮点击 ====================

    def nativeEvent(self, eventType, message):
        """
        处理 Windows 原生消息。
        WM_NCHITTEST: 让无边框窗口仍然支持边缘拖拽缩放，
        同时让鼠标落在控制条按钮上时点击能正常到达按钮。
        """
        if eventType == "windows_generic_MSG":
            msg = ctypes.cast(
                ctypes.c_void_p(int(message)),
                ctypes.POINTER(MSG)
            ).contents

            if msg.message == WM_NCHITTEST:
                # 获取鼠标屏幕坐标
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF

                # 转换为窗口本地坐标
                local_pos = self.mapFromGlobal(QPoint(x, y))
                local_x = local_pos.x()
                local_y = local_pos.y()

                # 鼠标位于控制条按钮上 → 当作普通客户区，
                # 点击才会被分发到按钮（否则会被当作窗口拖动）
                child = self.childAt(local_pos)
                if child is not None and isinstance(child, QPushButton):
                    return True, HTCLIENT

                w = self.width()
                h = self.height()
                m = self._resize_margin

                # 检查是否在边缘热区内
                on_left = local_x < m
                on_right = local_x > w - m
                on_top = local_y < m
                on_bottom = local_y > h - m

                # 角落优先
                if on_top and on_left:
                    return True, HTTOPLEFT
                if on_top and on_right:
                    return True, HTTOPRIGHT
                if on_bottom and on_left:
                    return True, HTBOTTOMLEFT
                if on_bottom and on_right:
                    return True, HTBOTTOMRIGHT

                # 边缘
                if on_left:
                    return True, HTLEFT
                if on_right:
                    return True, HTRIGHT
                if on_top:
                    return True, HTTOP
                if on_bottom:
                    return True, HTBOTTOM

                # 窗口内部 → 当作标题栏（允许拖动）
                return True, HTCAPTION

        return False, 0

    # ==================== 辅助方法 ====================

    def _update_cursor(self, pos: QPoint):
        """根据鼠标位置更新光标样式（边缘缩放提示）"""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = self._resize_margin

        on_left = x < m
        on_right = x > w - m
        on_top = y < m
        on_bottom = y > h - m

        if (on_top and on_left) or (on_bottom and on_right):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (on_top and on_right) or (on_bottom and on_left):
            self.setCursor(Qt.SizeBDiagCursor)
        elif on_left or on_right:
            self.setCursor(Qt.SizeHorCursor)
        elif on_top or on_bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # ==================== 窗口关闭 ====================

    def closeEvent(self, event):
        """窗口关闭时保存状态"""
        g = self.geometry()
        self._settings.save_window_geometry(g.x(), g.y(), g.width(), g.height())
        self._settings.sync()
        event.accept()
