"""
透明悬浮翻译窗口（核心UI组件）

特性：
- 无边框、始终置顶
- 背景完全透明，文字不透明（白字黑边描边）
- 鼠标拖动窗口任意位置
- 鼠标拖动边缘/角落调整大小
- Ctrl+滚轮调节字号
"""

import ctypes
from ctypes import wintypes

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import (
    QMouseEvent, QWheelEvent, QPaintEvent,
)
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from ui.subtitle_display import SubtitleDisplay
from config.settings import AppSettings

# ---- Windows API 常量（用于 WM_NCHITTEST 边缘缩放） ----

WM_NCHITTEST = 0x0084

# Hit test 返回值
HTCAPTION = 2
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
    3. nativeEvent 处理 WM_NCHITTEST → 边缘缩放（Windows原生体验）
    4. mousePressEvent / mouseMoveEvent → 窗口拖动
    5. wheelEvent + Ctrl → 字号调节
    """

    def __init__(self, settings: AppSettings):
        super().__init__()
        self._settings = settings
        self._dragging = False
        self._drag_offset = QPoint()
        self._resize_margin = 8  # 边缘缩放热区像素

        # 从配置加载
        self._font_size = settings.get("font_size", 16)
        self._show_original = settings.get("show_original_text", True)

        self._init_ui()
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
        self.subtitle_display.set_show_original(self._show_original)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.subtitle_display)

        self.setLayout(layout)

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

    # ==================== 公共接口 ====================

    def update_translation(self, original: str, translated: str, mode: str = "ocr"):
        """更新翻译显示（由翻译线程回调）"""
        self.subtitle_display.add_entry(original, translated, mode)

    def set_show_original(self, show: bool):
        """切换是否显示原文"""
        self._show_original = show
        self.subtitle_display.set_show_original(show)
        self._settings.set("show_original_text", show)

    def toggle_original(self):
        """切换原文显示状态"""
        self.set_show_original(not self._show_original)

    def set_font_size(self, size: int):
        """设置字号"""
        self._font_size = max(8, min(48, size))
        self.subtitle_display.set_font_size(self._font_size)
        self._settings.set("font_size", self._font_size)

    def get_font_size(self) -> int:
        return self._font_size

    def get_show_original(self) -> bool:
        return self._show_original

    def clear_history(self):
        """清空翻译历史"""
        self.subtitle_display.clear_history()

    # ==================== 鼠标事件：窗口拖动 ====================

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下：开始拖动"""
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
            # 非Ctrl时传递给父类（可用于滚动历史）
            super().wheelEvent(event)

    # ==================== 键盘事件：快捷键 ====================

    def keyPressEvent(self, event):
        """快捷键处理"""
        # Ctrl+O: 切换原文显示
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_O:
                self.toggle_original()
                event.accept()
                return
        super().keyPressEvent(event)

    # ==================== Windows原生事件：边缘缩放 ====================

    def nativeEvent(self, eventType, message):
        """
        处理 Windows 原生消息。
        WM_NCHITTEST: 让无边框窗口仍然支持边缘拖拽缩放。
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
