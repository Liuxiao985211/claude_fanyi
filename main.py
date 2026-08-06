"""
Clude翻译App — 入口文件

一个悬浮在电影画面之上的实时翻译字幕窗口。
背景完全透明，文字清晰可见，窗口始终置顶。

用法：
    python main.py

快捷键：
    Ctrl+O      — 切换原文显示/隐藏
    Ctrl+滚轮   — 调节字号
    Ctrl+P      — 暂停/恢复翻译
"""

import sys
import signal
import logging

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from config.settings import AppSettings
from ui.translucent_window import TranslucentWindow
from ui.tray_manager import TrayManager

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
logger = logging.getLogger("CludeApp")


class CludeApp:
    """
    Clude翻译App 主控制器。

    架构：
    ┌─────────────┐  ┌──────────────┐
    │ OCRWorker   │  │ AudioWorker  │  ← 两个捕获线程
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

        # 创建翻译器
        self._translator = create_translator(self._settings)
        logger.info(f"翻译后端: {self._translator.name}")

        # 检查翻译是否可用
        self._translation_available = self._translator.is_available()
        if not self._translation_available:
            logger.warning("翻译服务不可用！将使用演示模式展示窗口功能。")
            logger.warning("请检查网络连接，或在设置中配置其他翻译后端。")

        # 创建翻译工作线程（仅在可用时启动）
        self._translation_worker = None
        if self._translation_available:
            self._translation_worker = TranslationWorker(self._translator)
            self._translation_worker.start()

        # 创建历史记录写入器
        self._history_writer = HistoryWriter(
            history_dir=self._settings.get("history_dir", "./翻译记录")
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
        self._paused = False
        self._ocr_available = False
        self._audio_available = False
        self._demo_mode = False

        # 连接信号
        self._connect_signals()

        # 启动捕获线程（翻译可用时才启动）
        if self._translation_available:
            QTimer.singleShot(1000, self._start_capture_workers)
        else:
            QTimer.singleShot(1000, self._start_demo_mode)

        # 欢迎通知
        QTimer.singleShot(1500, self._show_welcome)

    # ==================== 信号连接 ====================

    def _connect_signals(self):
        """连接所有信号"""
        # 托盘信号
        self._tray.show_window_requested.connect(self._toggle_window)
        self._tray.pause_requested.connect(self._pause)
        self._tray.resume_requested.connect(self._resume)
        self._tray.exit_requested.connect(self._exit_app)

        # 翻译结果 → 显示 + 记录（仅在翻译可用时连接）
        if self._translation_worker:
            self._translation_worker.translation_ready.connect(
                self._on_translation_ready
            )
            self._translation_worker.translation_error.connect(
                self._on_translation_error
            )

    def _start_capture_workers(self):
        """启动OCR和音频捕获线程"""
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

    def _start_demo_mode(self):
        """演示模式：翻译不可用时，展示窗口功能"""
        self._demo_mode = True
        logger.info("🎬 进入演示模式")

        demo_texts = [
            ("Hello, how are you?", "你好，你好吗？"),
            ("I've been waiting for this moment.", "我一直在等待这一刻。"),
            ("The weather is beautiful today.", "今天天气真好。"),
            ("Could you please pass me the salt?", "你能把盐递给我吗？"),
            ("I can't believe you did that!", "我不敢相信你做了那件事！"),
            ("Let's meet at the usual place.", "我们在老地方见。"),
            ("This is the best day of my life.", "这是我人生中最美好的一天。"),
            ("Don't worry, everything will be fine.", "别担心，一切都会好起来的。"),
        ]
        self._demo_index = 0

        def show_next():
            if not self._paused and self._window.isVisible():
                original, translated = demo_texts[self._demo_index % len(demo_texts)]
                self._window.update_translation(original, translated, mode="demo")
                self._history_writer.enqueue(original, translated, "demo")
                self._demo_index += 1

        self._demo_timer = QTimer()
        self._demo_timer.timeout.connect(show_next)
        self._demo_timer.start(3000)  # 每3秒一条

    # ==================== 回调：捕获就绪 ====================

    def _on_ocr_ready(self, success: bool):
        """OCR初始化完成"""
        self._ocr_available = success
        if success:
            logger.info("✅ OCR引擎就绪")
        else:
            logger.warning("❌ OCR引擎不可用")

    def _on_ocr_error(self, error: str):
        """OCR错误"""
        logger.error(f"OCR错误: {error}")

    def _on_audio_ready(self, success: bool):
        """音频初始化完成"""
        self._audio_available = success
        if success:
            logger.info("✅ 音频捕获就绪")
        else:
            logger.warning("❌ 音频捕获不可用，仅使用OCR模式")

    def _on_audio_error(self, error: str):
        """音频错误"""
        logger.error(f"音频错误: {error}")

    # ==================== 回调：翻译 ====================

    def _on_translation_ready(self, original: str, translated: str):
        """翻译完成：显示到窗口 + 写入记录"""
        if self._window.isVisible() and not self._paused:
            self._window.update_translation(original, translated)
        # 无论窗口是否可见，都写入记录
        self._history_writer.enqueue(original, translated)

    def _on_translation_error(self, original: str, error: str):
        """翻译失败"""
        logger.warning(f"翻译失败: {original[:30]}... → {error}")

    # ==================== 显示欢迎 ====================

    def _show_welcome(self):
        """显示欢迎信息"""
        tips = [
            "Ctrl+O — 切换原文显示",
            "Ctrl+滚轮 — 调节字号",
            "右键托盘图标 — 更多选项",
        ]
        self._tray.show_notification(
            "Clude翻译App 已就绪",
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

    def _pause(self):
        """暂停翻译"""
        self._paused = True
        if self._ocr_worker:
            self._ocr_worker.pause()
        if self._audio_worker:
            self._audio_worker.pause()

    def _resume(self):
        """恢复翻译"""
        self._paused = False
        if self._ocr_worker:
            self._ocr_worker.resume()
        if self._audio_worker:
            self._audio_worker.resume()

    def _exit_app(self):
        """优雅退出"""
        logger.info("正在退出...")

        # 停止演示定时器
        if hasattr(self, '_demo_timer') and self._demo_timer:
            self._demo_timer.stop()

        # 停止工作线程
        for worker in [self._ocr_worker, self._audio_worker, self._translation_worker]:
            if worker is not None and worker.isRunning():
                worker.stop()

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
