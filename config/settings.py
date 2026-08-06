"""
应用配置管理
使用 QSettings 存储（Windows 上存储在注册表），支持默认值回退。
"""

from PyQt5.QtCore import QSettings, QRect


# 默认配置值
DEFAULTS = {
    # 通用
    "target_language": "zh-CN",
    "source_language": "auto",
    "translation_mode": "hybrid",       # "ocr" | "audio" | "hybrid"
    "show_original_text": True,         # 是否显示原文
    "font_size": 16,
    "max_history_lines": 50,

    # 窗口
    "window_x": -1,                     # -1 表示使用默认位置
    "window_y": -1,
    "window_width": 800,
    "window_height": 200,
    "always_on_top": True,

    # OCR
    "ocr_interval_ms": 800,             # OCR 截图间隔（毫秒）
    "ocr_region_ratio": 0.15,           # 截取屏幕底部比例
    "ocr_languages": "en",              # EasyOCR 语言代码

    # 音频
    "audio_sample_rate": 16000,
    "audio_chunk_duration_s": 2.0,
    "audio_vad_threshold": 0.02,        # 语音活动检测阈值
    "audio_stt_engine": "google",       # "google" | "whisper" | "vosk"

    # 翻译
    "translation_backend": "google",    # "google" | "deepl"
    "deepl_api_key": "",                # 空 = 未配置

    # 历史记录
    "history_dir": "./翻译记录",
    "auto_save": True,
}


class AppSettings:
    """应用配置管理器，封装 QSettings 并提供默认值回退。"""

    def __init__(self, org="CludeTranslator", app="CludeApp"):
        self._settings = QSettings(org, app)
        self._org = org
        self._app = app

    def get(self, key, default=None):
        """获取配置值，未设置时返回传入的 default 或全局默认值。"""
        if default is None:
            default = DEFAULTS.get(key)
        return self._settings.value(key, default)

    def set(self, key, value):
        """设置配置值并立即写入。"""
        self._settings.setValue(key, value)
        self._settings.sync()

    def sync(self):
        """强制同步到磁盘。"""
        self._settings.sync()

    def default_window_geometry(self) -> QRect:
        """
        计算窗口默认位置：屏幕底部居中。
        如果用户之前保存过位置，则使用保存的位置。
        """
        x = self.get("window_x", -1)
        y = self.get("window_y", -1)
        w = self.get("window_width", 800)
        h = self.get("window_height", 200)

        if x < 0 or y < 0:
            # 首次运行：放到主屏幕底部居中
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtGui import QScreen
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    geom = screen.availableGeometry()
                    x = (geom.width() - w) // 2
                    y = geom.height() - h - 60  # 底部留60px边距

        return QRect(x, y, w, h)

    def save_window_geometry(self, x, y, w, h):
        """保存窗口几何信息。"""
        self.set("window_x", x)
        self.set("window_y", y)
        self.set("window_width", w)
        self.set("window_height", h)

    @property
    def is_hybrid_mode(self):
        return self.get("translation_mode") == "hybrid"

    @property
    def is_ocr_enabled(self):
        mode = self.get("translation_mode")
        return mode in ("ocr", "hybrid")

    @property
    def is_audio_enabled(self):
        mode = self.get("translation_mode")
        return mode in ("audio", "hybrid")
