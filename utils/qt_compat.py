"""
PyQt5 / PyQt5 兼容层
优先使用 PyQt5，如果未安装则回退到 PyQt5。

用法：
    from utils.qt_compat import QtWidgets, QtCore, QtGui, Qt
"""

try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtCore import Qt, QEvent, pyqtSignal, pyqtSlot, QTimer
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QSystemTrayIcon, QMenu,
        QAction, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QCheckBox, QComboBox, QSlider,
    )
    from PyQt5.QtGui import (
        QPainter, QPainterPath, QPen, QBrush, QColor, QFont,
        QIcon, QPixmap, QMouseEvent, QWheelEvent, QPaintEvent,
        QAction as QActionGui,
    )
    _QT_VERSION = 6
except ImportError:
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtCore import Qt, QEvent, pyqtSignal, pyqtSlot, QTimer
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QSystemTrayIcon, QMenu,
        QAction, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QCheckBox, QComboBox, QSlider,
    )
    from PyQt5.QtGui import (
        QPainter, QPainterPath, QPen, QBrush, QColor, QFont,
        QIcon, QPixmap, QMouseEvent, QWheelEvent, QPaintEvent,
    )
    _QT_VERSION = 5

# ---- 版本适配的工具函数 ----

def get_global_pos(event):
    """获取鼠标事件的全局坐标（PyQt5/PyQt5 API不同）"""
    if _QT_VERSION >= 6:
        return event.globalPos()
    else:
        return event.globalPos()

def get_wheel_delta(event):
    """获取滚轮事件的滚动量"""
    if _QT_VERSION >= 6:
        return event.angleDelta().y()
    else:
        return event.angleDelta().y()

def get_ctrl_modifier():
    """获取Ctrl键的修饰符常量"""
    if _QT_VERSION >= 6:
        return Qt.ControlModifier
    else:
        return Qt.ControlModifier
