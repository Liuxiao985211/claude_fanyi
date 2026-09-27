"""
字幕显示组件
在透明窗口中渲染白字黑边描边的译文文字。

本次重构：窗口只显示最新一行译文，
历史记录全部由 HistoryWriter 写入本地文件，不再上屏。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QPainter, QPainterPath, QPen, QColor, QFont,
    QPaintEvent,
)
from PyQt5.QtWidgets import QWidget

from utils.text_utils import truncate


class SubtitleDisplay(QWidget):
    """
    字幕显示区域。
    在 paintEvent 中用 QPainter 渲染文字，背景完全透明。

    - 翻译中：居中显示最新一行译文（亮黄色 + 黑边描边）
    - 待开始：居中显示一行较暗的提示文字
    """

    IDLE_HINT = "▶ 点击开始翻译"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_size = 16
        self._translated = ""
        self._idle_mode = False
        self._idle_hint = self.IDLE_HINT

        # 字体设置
        self._font_family = "Microsoft YaHei"
        self._setup_ui()

    def _setup_ui(self):
        """初始化UI属性"""
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumHeight(40)

    # ==================== 对外接口 ====================

    def set_font_size(self, size: int):
        """设置字号"""
        self._font_size = max(8, min(48, size))
        self.update()

    def set_translation(self, translated: str):
        """更新当前显示的译文（屏幕上只保留这一行）"""
        self._translated = translated
        self.update()

    def set_idle_mode(self, idle: bool):
        """进入/退出待开始状态（待开始且无译文时显示提示文字）"""
        self._idle_mode = idle
        self.update()

    def set_idle_hint(self, text: str):
        """自定义待开始状态的提示文字（如“翻译服务不可用”）"""
        self._idle_hint = text
        self.update()

    def clear(self):
        """清空当前译文"""
        self._translated = ""
        self.update()

    # ==================== 绘制 ====================

    def paintEvent(self, event: QPaintEvent):
        """
        绘制字幕文字。
        使用 QPainterPath 实现黑边描边效果：
        1. 先用粗黑笔画轮廓（描边）
        2. 再用颜色画刷填充（文字本体）
        这样无论背景电影画面是什么颜色，文字都清晰可读。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_y = self.height() // 2

        if self._idle_mode and not self._translated:
            # 待开始状态：显示一行较暗的提示文字
            font = QFont(self._font_family, self._font_size, QFont.Weight.Normal)
            self._draw_text_line(
                painter, font, self._idle_hint,
                self.width(), center_y,
                fill_color=QColor(220, 220, 220, 150),
                outline_alpha=150,
                outline_width=2,
            )
        elif self._translated:
            # 翻译中：最新一行译文，字号加大、加粗
            text = truncate(self._translated, 120)
            font = QFont(self._font_family, self._font_size + 4, QFont.Weight.Bold)
            self._draw_text_line(
                painter, font, text,
                self.width(), center_y,
                fill_color=QColor(255, 255, 100, 255),   # 亮黄色译文
                outline_alpha=255,
                outline_width=3,
            )

        painter.end()

    def _draw_text_line(
        self,
        painter: QPainter,
        font: QFont,
        text: str,
        max_width: int,
        center_y: int,
        fill_color: QColor,
        outline_alpha: int = 255,
        outline_width: int = 3,
    ):
        """
        绘制单行文字，带黑边描边效果，以 center_y 为垂直中心。

        参数：
            painter: QPainter 实例
            font: 字体
            text: 文字内容
            max_width: 最大宽度（用于水平居中计算）
            center_y: 行的垂直中心坐标
            fill_color: 文字填充颜色
            outline_alpha: 描边不透明度 0-255
            outline_width: 描边粗细
        """
        if not text:
            return

        painter.save()
        painter.setFont(font)

        # 水平居中
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        x = max(10, (max_width - text_width) // 2)

        # 垂直居中：以 center_y 为文字块的中心计算基线
        y = center_y + fm.ascent() - fm.height() / 2

        # 创建文字路径
        path = QPainterPath()
        path.addText(x, y, font, text)

        # 描边颜色：黑色
        outline_pen = QPen(QColor(0, 0, 0, outline_alpha), outline_width)
        outline_pen.setJoinStyle(Qt.RoundJoin)
        outline_pen.setCapStyle(Qt.RoundCap)

        # 先画描边（轮廓），再填充文字本体
        painter.setPen(outline_pen)
        painter.setBrush(fill_color)
        painter.drawPath(path)

        painter.restore()
