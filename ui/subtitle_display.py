"""
字幕显示组件
在透明窗口中渲染白字黑边描边文字，支持滚动历史。
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QPainter, QPainterPath, QPen, QBrush, QColor, QFont,
    QPaintEvent,
)
from PyQt5.QtWidgets import QWidget

from utils.text_utils import truncate


@dataclass
class SubtitleEntry:
    """一条字幕记录"""
    timestamp: str      # "HH:MM:SS"
    original: str       # 原文
    translated: str     # 译文
    mode: str           # "ocr" | "audio"


class SubtitleDisplay(QWidget):
    """
    字幕显示区域。
    在 paintEvent 中用 QPainter 渲染白字黑边描边文字。
    背景完全透明，让电影画面穿透。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: deque[SubtitleEntry] = deque(maxlen=50)
        self._max_entries = 50
        self._font_size = 16
        self._show_original = True
        self._current_original = ""
        self._current_translated = ""

        # 字体设置
        self._font_family = "Microsoft YaHei"
        self._setup_ui()

    def _setup_ui(self):
        """初始化UI属性"""
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumHeight(60)

    def set_font_size(self, size: int):
        """设置字号"""
        self._font_size = max(8, min(48, size))
        self.update()

    def set_show_original(self, show: bool):
        """设置是否显示原文"""
        self._show_original = show
        self.update()

    def set_max_entries(self, n: int):
        """设置最大历史条目数"""
        self._max_entries = n
        self._entries = deque(self._entries, maxlen=n)

    def add_entry(self, original: str, translated: str, mode: str = "ocr"):
        """添加一条翻译记录"""
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")

        entry = SubtitleEntry(
            timestamp=timestamp,
            original=original,
            translated=translated,
            mode=mode
        )
        self._entries.append(entry)

        # 更新当前显示
        self._current_original = original
        self._current_translated = translated

        # 限制历史条目数量
        while len(self._entries) > self._max_entries:
            self._entries.popleft()

        self.update()

    def update_current(self, original: str, translated: str):
        """更新当前显示的翻译（不新增历史记录，用于实时刷新）"""
        self._current_original = original
        self._current_translated = translated
        self.update()

    def clear_history(self):
        """清空历史记录"""
        self._entries.clear()
        self._current_original = ""
        self._current_translated = ""
        self.update()

    def paintEvent(self, event: QPaintEvent):
        """
        绘制字幕文字。
        使用 QPainterPath 实现白字黑边描边效果：
        1. 先用粗黑笔画轮廓（描边）
        2. 再用白色画刷填充（文字本体）
        这样无论背景电影画面是什么颜色，文字都清晰可读。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 窗口的实际宽度
        w = self.width()
        y_offset = 10

        # ---- 绘制当前译文（最大、最醒目） ----
        if self._current_translated:
            # 译文使用较大字号
            font_size = self._font_size + 4
            font = QFont(self._font_family, font_size, QFont.Weight.Bold)
            self._draw_text_line(
                painter, font,
                self._current_translated,
                w, y_offset, is_translation=True
            )
            y_offset += font_size + 12

        # ---- 绘制当前原文（较小，可选） ----
        if self._show_original and self._current_original:
            font_size = self._font_size - 2
            font = QFont(self._font_family, font_size, QFont.Weight.Normal)
            self._draw_text_line(
                painter, font,
                self._current_original,
                w, y_offset, is_translation=False
            )
            y_offset += font_size + 8

        # ---- 历史记录分隔线 ----
        if len(self._entries) > 1 and y_offset < self.height() - 40:
            # 画一条半透明的分隔线
            painter.save()
            pen = QPen(QColor(255, 255, 255, 60), 1)
            painter.setPen(pen)
            painter.drawLine(20, y_offset + 5, w - 20, y_offset + 5)
            painter.restore()
            y_offset += 15

        # ---- 绘制历史记录（更小、半透明） ----
        history_font_size = max(10, self._font_size - 4)
        font = QFont(self._font_family, history_font_size, QFont.Weight.Normal)
        opacity = 180  # 历史文字略透明

        # 从最新到最旧显示（最新的在下，旧的在上）
        history_entries = list(self._entries)[-6:-1]  # 最近5条（排除当前）
        for entry in reversed(history_entries):
            if y_offset > self.height() - 30:
                break

            # 显示译文（缩短版）
            text = entry.translated
            if self._show_original and entry.original:
                text = f"{entry.translated}  |  {entry.original}"
            text = truncate(text, 100)

            self._draw_text_line(
                painter, font, text,
                w, y_offset, is_translation=False, opacity=opacity
            )
            y_offset += history_font_size + 6

        painter.end()

    def _draw_text_line(
        self,
        painter: QPainter,
        font: QFont,
        text: str,
        max_width: int,
        y: int,
        is_translation: bool = False,
        opacity: int = 255
    ):
        """
        绘制单行文字，带黑边描边效果。

        参数：
            painter: QPainter 实例
            font: 字体
            text: 文字内容
            max_width: 最大宽度（用于居中计算）
            y: Y 坐标
            is_translation: 是否为译文（译文颜色略不同）
            opacity: 不透明度 0-255
        """
        if not text:
            return

        painter.save()
        painter.setFont(font)

        # 计算文字宽度以居中
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        x = max(10, (max_width - text_width) // 2)

        # 创建文字路径
        path = QPainterPath()
        path.addText(x, y + fm.ascent(), font, text)

        # 描边颜色：深色（黑色或深灰）
        outline_color = QColor(0, 0, 0, opacity)
        outline_pen = QPen(outline_color, 3)
        outline_pen.setJoinStyle(Qt.RoundJoin)
        outline_pen.setCapStyle(Qt.RoundCap)

        # 填充颜色：译文用亮黄，原文用白色
        if is_translation:
            fill_color = QColor(255, 255, 100, opacity)  # 亮黄色译文
        else:
            fill_color = QColor(255, 255, 255, opacity)  # 白色原文

        # 先画描边（轮廓）
        painter.setPen(outline_pen)
        painter.setBrush(fill_color)
        painter.drawPath(path)

        painter.restore()
