"""
OCR 捕获工作线程

在独立线程中定期执行屏幕截图+OCR识别，
通过信号将识别的文本发送到主线程。
"""

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from capture.ocr_capture import OCRCapture
from capture.deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class OCRWorker(QThread):
    """
    OCR 工作线程。

    以固定间隔（默认800ms）截取屏幕底部区域，
    通过 EasyOCR 识别字幕文字，
    去重后通过 text_captured 信号发出。
    """

    # 信号
    text_captured = pyqtSignal(str)      # 识别到新文本（已去重）
    ocr_error = pyqtSignal(str)           # 错误消息
    ocr_initialized = pyqtSignal(bool)    # 初始化完成

    def __init__(
        self,
        ocr: OCRCapture,
        dedup: Deduplicator,
        interval_ms: int = 800,
        parent=None
    ):
        super().__init__(parent)
        self._ocr = ocr
        self._dedup = dedup
        self._interval_ms = interval_ms
        self._running = False
        self._paused = False

    def run(self):
        """主循环：定期截图 → OCR → 去重 → 发信号"""
        logger.info("OCR工作线程启动")

        # 初始化 OCR 引擎
        if not self._ocr.initialize():
            self.ocr_initialized.emit(False)
            self.ocr_error.emit("OCR引擎初始化失败，请检查依赖")
            return

        self.ocr_initialized.emit(True)
        self._running = True

        while self._running:
            try:
                if not self._paused:
                    text = self._ocr.capture_and_ocr()
                    if text and not self._dedup.is_duplicate(text):
                        self.text_captured.emit(text)

                # 等待下一个间隔
                self.msleep(self._interval_ms)

            except Exception as e:
                logger.error(f"OCR循环异常: {e}")
                self.ocr_error.emit(str(e))
                self.msleep(self._interval_ms)

        # 清理
        self._ocr.shutdown()
        logger.info("OCR工作线程退出")

    def pause(self):
        """暂停OCR捕获"""
        self._paused = True
        logger.info("OCR已暂停")

    def resume(self):
        """恢复OCR捕获"""
        self._paused = False
        logger.info("OCR已恢复")

    def stop(self):
        """停止线程"""
        self._running = False
        self.wait(3000)  # 等待最多3秒
