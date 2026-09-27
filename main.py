"""
Clude翻译App — 入口文件

一个悬浮在电影画面之上的实时翻译字幕窗口。
背景完全透明，文字清晰可见，窗口始终置顶。

用法：
    python main.py

交互：
    打开后处于“待开始”状态 → 点击窗口 ▶ 按钮或托盘菜单开始翻译
    Ctrl+滚轮   — 调节字号
    右键托盘图标 — 更多选项
"""

import os
import sys
import signal
import logging
from logging.handlers import RotatingFileHandler

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from config.settings import AppSettings
from ui.translucent_window import TranslucentWindow
from ui.tray_manager import TrayManager
from ui.settings_dialog import SettingsDialog

# 捕获模块
from capture.deduplicator import Deduplicator
from capture.ocr_capture import OCRCapture
from capture.audio_capture import AudioCapture

# 翻译模块
from translate.translator import create_translator

# 工作线程
from workers.ocr_worker import OCRWorker
from workers.audio_worker import AudioWorker
from workers.translation_worker import TranslationWorker

# 存储模块
from storage.history_writer import HistoryWriter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# 同时把日志写入文件（打包后的 exe 没有控制台，靠它排查问题）
_app_dir = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
try:
    _fh = RotatingFileHandler(
        os.path.join(_app_dir, "app.log"),
        maxBytes=1_000_000, backupCount=2, encoding="utf-8",
    )
    _fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger().addHandler(_fh)
except Exception:
    pass  # 日志文件写不了也不影响软件运行

logger = logging.getLogger("CludeApp")

# 待开始状态的窗口提示文字
IDLE_HINT_NORMAL = "▶ 点击开始翻译"
IDLE_HINT_UNAVAILABLE = "翻译服务不可用，请检查网络或 ⚙ 设置"


class CludeApp:
    """
    Clude翻译App 主控制器。

    翻译状态机：
        idle（待开始）  --▶ 开始翻译-->  running（翻译中）
        running        --⏸ 暂停-->      paused（已暂停）
        paused         --▶ 恢复-->      running
        running/paused --⏹ 停止-->      idle

    架构：
    ┌─────────────┐  ┌──────────────┐
    │ OCRWorker   │  │ AudioWorker  │  ← 两个捕获线程（点击开始后创建）
    └──────┬──────┘  └──────┬───────┘
           │                │
           └───────┬────────┘
                   ▼
    ┌─────────────────────────┐
    │ TranslationWorker       │  ← 翻译线程（队列）
    └───────────┬─────────────┘
                │
         ┌──────┴──────┐
         ▼              ▼
    ┌─────────┐  ┌──────────────┐
    │ 窗口显示 │  │ HistoryWriter │  ← 主线程
    └─────────┘  └──────────────┘
    """

    # 翻译状态
    STATE_IDLE = "idle"        # 待开始：打开后的初始状态
    STATE_RUNNING = "running"  # 翻译中
    STATE_PAUSED = "paused"    # 已暂停

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # 加载配置
        self._settings = AppSettings()

        # 创建共享的去重器（OCR和Audio共用）
        self._deduplicator = Deduplicator(
            max_history=50,
            similarity_threshold=0.85,
            expiry_seconds=30.0,
        )

        # 创建翻译线程
        self._translation_worker = None
        self._translation_available = False
        self._setup_translation_worker()

        # 创建历史记录写入器
        self._history_writer = HistoryWriter(
            history_dir=self._resolve_history_dir()
        )

        # 创建窗口
        self._window = TranslucentWindow(self._settings)
        self._window.show()

        # 创建托盘
        self._tray = TrayManager(self._window)

        # 工作线程引用
        self._ocr_worker: OCRWorker = None
        self._audio_worker: AudioWorker = None

        # 状态
        self._state = self.STATE_IDLE
        self._last_error_notify = 0.0  # 上次翻译失败提示时间（限流用）

        # 连接信号
        self._connect_signals()

        # 初始状态：待开始，不启动任何捕获
        self._set_state(self.STATE_IDLE)

        # 翻译服务不可用时，把窗口提示换成原因说明
        if not self._translation_available:
            self._window.set_idle_hint(IDLE_HINT_UNAVAILABLE)

        # 欢迎通知
        QTimer.singleShot(1500, self._show_welcome)

    # ==================== 翻译线程 ====================

    def _resolve_history_dir(self) -> str:
        """
        把历史记录目录解析为绝对路径并回写配置。

        相对路径（旧默认 "./翻译记录"）依赖启动时的工作目录：
        用快捷方式/开机自启启动时 cwd 不确定，记录会写到别处去。
        统一解析为应用所在目录（exe 同目录或源码目录）下的绝对路径。
        """
        raw = self._settings.get("history_dir", "./翻译记录")
        if not os.path.isabs(raw):
            raw = os.path.join(_app_dir, raw)
        self._settings.set("history_dir", raw)
        return raw

    def _setup_translation_worker(self):
        """创建翻译器与翻译线程（设置变更后可重复调用重建）"""
        self._translator = create_translator(self._settings)
        self._translation_available = self._translator.is_available()
        logger.info(
            f"翻译后端: {self._translator.name}，可用: {self._translation_available}"
        )

        old = self._translation_worker
        if old is not None and old.isRunning():
            old.stop()

        self._translation_worker = None
        if not self._translation_available:
            logger.warning("翻译服务不可用！")
            logger.warning("请检查网络连接，或点击 ⚙ 翻译API设置 查看配置。")
            return

        self._translation_worker = TranslationWorker(self._translator)
        self._translation_worker.translation_ready.connect(
            self._on_translation_ready
        )
        self._translation_worker.translation_error.connect(
            self._on_translation_error
        )
        self._translation_worker.start()

    # ==================== 信号连接 ====================

    def _connect_signals(self):
        """连接所有信号"""
        # 托盘信号
        self._tray.show_window_requested.connect(self._toggle_window)
        self._tray.start_requested.connect(self._start_translation)
        self._tray.stop_requested.connect(self._stop_translation)
        self._tray.pause_requested.connect(self._pause)
        self._tray.resume_requested.connect(self._resume)
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.mode_change_requested.connect(self._on_mode_changed)
        self._tray.exit_requested.connect(self._exit_app)

        # 窗口控制条信号
        self._window.start_pause_clicked.connect(self._on_start_pause_clicked)
        self._window.settings_clicked.connect(self._open_settings)

    # ==================== 状态机 ====================

    def _set_state(self, state: str):
        """切换翻译状态，并同步窗口/托盘界面"""
        self._state = state
        self._tray.update_state(state)
        self._window.set_translation_state(state)
        self._window.set_idle_mode(state == self.STATE_IDLE)

    def _start_translation(self):
        """待开始 → 翻译中：启动捕获线程"""
        if self._state != self.STATE_IDLE:
            return
        if not self._translation_available:
            # 翻译服务不可用：只提示，不启动、不播放任何示例
            self._tray.show_notification(
                "翻译服务不可用",
                "无法连接翻译服务。请检查网络连接，或点击 ⚙ 翻译API设置 查看配置。",
            )
            logger.warning("点击开始翻译，但翻译服务不可用，保持待开始状态")
            return
        self._start_capture_workers()
        self._set_state(self.STATE_RUNNING)
        logger.info("▶ 开始翻译")

    def _pause(self):
        """翻译中 → 已暂停"""
        if self._state != self.STATE_RUNNING:
            return
        self._set_state(self.STATE_PAUSED)
        if self._ocr_worker:
            self._ocr_worker.pause()
        if self._audio_worker:
            self._audio_worker.pause()
        logger.info("⏸ 暂停翻译")

    def _resume(self):
        """已暂停 → 翻译中"""
        if self._state != self.STATE_PAUSED:
            return
        self._set_state(self.STATE_RUNNING)
        if self._ocr_worker:
            self._ocr_worker.resume()
        if self._audio_worker:
            self._audio_worker.resume()
        logger.info("▶ 恢复翻译")

    def _stop_translation(self):
        """翻译中/已暂停 → 待开始：停止一切捕获"""
        if self._state == self.STATE_IDLE:
            return
        self._stop_capture_workers()
        self._window.clear_translation()
        self._set_state(self.STATE_IDLE)
        logger.info("⏹ 停止翻译")

    def _on_start_pause_clicked(self):
        """窗口控制条按钮：按当前状态执行 开始/暂停/恢复"""
        if self._state == self.STATE_IDLE:
            self._start_translation()
        elif self._state == self.STATE_RUNNING:
            self._pause()
        else:
            self._resume()

    # ==================== 捕获线程 ====================

    def _start_capture_workers(self):
        """启动OCR和音频捕获线程（先停掉旧线程）"""
        self._stop_capture_workers()

        # 翻译线程不存在（翻译不可用）时无法启动捕获
        if self._translation_worker is None:
            return

        mode = self._settings.get("translation_mode", "hybrid")

        # ---- OCR 线程 ----
        if mode in ("ocr", "hybrid"):
            ocr = OCRCapture(
                region_ratio=self._settings.get("ocr_region_ratio", 0.15),
                languages=[self._settings.get("ocr_languages", "en")],
            )
            self._ocr_worker = OCRWorker(
                ocr=ocr,
                dedup=self._deduplicator,
                interval_ms=self._settings.get("ocr_interval_ms", 800),
            )
            self._ocr_worker.text_captured.connect(self._translation_worker.enqueue)
            self._ocr_worker.ocr_initialized.connect(self._on_ocr_ready)
            self._ocr_worker.ocr_error.connect(self._on_ocr_error)
            self._ocr_worker.start()
            logger.info("OCR工作线程已启动")

        # ---- 音频线程 ----
        if mode in ("audio", "hybrid"):
            audio = AudioCapture(
                sample_rate=self._settings.get("audio_sample_rate", 16000),
                chunk_duration_s=self._settings.get("audio_chunk_duration_s", 2.0),
                vad_threshold=self._settings.get("audio_vad_threshold", 0.02),
                stt_engine=self._settings.get("audio_stt_engine", "google"),
            )
            self._audio_worker = AudioWorker(
                audio=audio,
                dedup=self._deduplicator,
            )
            self._audio_worker.speech_detected.connect(
                self._translation_worker.enqueue
            )
            self._audio_worker.audio_initialized.connect(self._on_audio_ready)
            self._audio_worker.audio_error.connect(self._on_audio_error)
            self._audio_worker.start()
            logger.info("音频工作线程已启动")

    def _stop_capture_workers(self):
        """停止并销毁OCR/音频捕获线程"""
        for worker in (self._ocr_worker, self._audio_worker):
            if worker is not None and worker.isRunning():
                worker.stop()
        self._ocr_worker = None
        self._audio_worker = None

    # ==================== 回调：捕获就绪 ====================

    def _on_ocr_ready(self, success: bool):
        """OCR初始化完成"""
        if success:
            logger.info("✅ OCR引擎就绪")
        else:
            logger.warning("❌ OCR引擎不可用")

    def _on_ocr_error(self, error: str):
        """OCR错误"""
        logger.error(f"OCR错误: {error}")

    def _on_audio_ready(self, success: bool):
        """音频初始化完成"""
        if success:
            logger.info("✅ 音频捕获就绪")
        else:
            logger.warning("❌ 音频捕获不可用，仅使用OCR模式")

    def _on_audio_error(self, error: str):
        """音频错误"""
        logger.error(f"音频错误: {error}")

    # ==================== 回调：翻译 ====================

    def _on_translation_ready(self, original: str, translated: str):
        """翻译完成：窗口显示最新一行译文 + 写入记录文件"""
        if self._window.isVisible():
            self._window.update_translation(translated)
        # 无论窗口是否可见，都写入记录
        self._history_writer.enqueue(original, translated)

    def _on_translation_error(self, original: str, error: str):
        """翻译失败"""
        logger.warning(f"翻译失败: {original[:30]}... → {error}")
        # 用户提示（60 秒限流：翻译失败通常是持续性的，别刷屏）
        import time as _time
        now = _time.time()
        if now - self._last_error_notify >= 60:
            self._last_error_notify = now
            self._tray.show_notification(
                "翻译失败",
                "连续翻译失败，请检查网络或 ⚙ 翻译API设置。"
                f"\n（{error[:60]}）",
            )

    # ==================== 设置 ====================

    def _open_settings(self):
        """打开翻译设置窗口"""
        dlg = SettingsDialog(
            self._settings,
            self._history_writer.get_history_dir(),
            self._window,
        )
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec_()

    def _on_settings_changed(self):
        """设置已保存：重建翻译器；若在翻译中则重启捕获线程"""
        restart = self._state in (self.STATE_RUNNING, self.STATE_PAUSED)
        if restart:
            self._stop_capture_workers()
        self._setup_translation_worker()
        # 窗口提示跟随服务可用性变化
        self._window.set_idle_hint(
            IDLE_HINT_UNAVAILABLE if not self._translation_available
            else IDLE_HINT_NORMAL
        )
        if restart:
            if self._translation_available:
                self._start_capture_workers()
                if self._state == self.STATE_PAUSED:
                    self._pause()
            else:
                # 新设置下翻译不可用 → 回到待开始状态
                self._window.clear_translation()
                self._set_state(self.STATE_IDLE)
                self._tray.show_notification(
                    "翻译服务不可用",
                    "当前配置无法连接翻译服务，已停止翻译。",
                )
        logger.info("设置已更新")

    def _on_mode_changed(self, mode: str):
        """翻译模式（OCR/音频/混合）变更：保存并在翻译中时重启"""
        self._settings.set("translation_mode", mode)
        if not self._translation_available:
            return
        if self._state == self.STATE_RUNNING:
            self._stop_capture_workers()
            self._start_capture_workers()
        elif self._state == self.STATE_PAUSED:
            self._stop_capture_workers()
            self._start_capture_workers()
            self._pause()

    # ==================== 显示欢迎 ====================

    def _show_welcome(self):
        """显示欢迎信息"""
        tips = [
            "点击 ▶ 按钮或托盘菜单开始翻译",
            "Ctrl+滚轮 — 调节字号",
            "右键托盘图标 — 更多选项",
        ]
        self._tray.show_notification(
            "Clude翻译App 已就绪（待开始）",
            "\n".join(tips)
        )

    # ==================== 窗口控制 ====================

    def _toggle_window(self):
        """切换窗口显示/隐藏"""
        if self._window.isVisible():
            self._window.hide()
        else:
            self._window.show()
            # 确保置顶属性生效
            self._window.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.Tool
            )
            self._window.show()

    # ==================== 退出 ====================

    def _exit_app(self):
        """优雅退出"""
        logger.info("正在退出...")

        # 停止工作线程
        self._stop_capture_workers()
        if self._translation_worker is not None and self._translation_worker.isRunning():
            self._translation_worker.stop()

        # 写入所有待处理的记录
        self._history_writer.flush()

        # 保存配置
        self._settings.sync()

        logger.info(f"翻译记录已保存至: {self._history_writer.get_history_dir()}")
        self._window.close()
        self._app.quit()

    def run(self):
        """启动应用"""
        return self._app.exec()


# ==================== 入口 ====================

if __name__ == "__main__":
    # 让 Ctrl+C 能正常退出
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = CludeApp()
    sys.exit(app.run())
