"""
翻译工作线程

从队列中取出文本，调用翻译API，通过信号返回结果。
"""

import logging
import queue

from PyQt5.QtCore import QThread, pyqtSignal

from translate.translator import BaseTranslator

logger = logging.getLogger(__name__)


class TranslationWorker(QThread):
    """
    翻译工作线程。

    使用线程安全的 queue.Queue 接收待翻译文本，
    调用翻译API后将结果通过 pyqtSignal 发送回主线程。
    """

    # 信号
    translation_ready = pyqtSignal(str, str)  # (原文, 译文)
    translation_error = pyqtSignal(str, str)  # (原文, 错误信息)

    def __init__(self, translator: BaseTranslator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._queue: queue.Queue = queue.Queue()
        self._running = False

    def enqueue(self, text: str):
        """
        将文本加入翻译队列（线程安全，可从任意线程调用）。

        参数：
            text: 待翻译的文本
        """
        if text and len(text.strip()) >= 2:
            self._queue.put(text)

    def run(self):
        """主循环：从队列取文本 → 翻译 → 发信号"""
        logger.info(f"翻译工作线程启动 (后端: {self._translator.name})")
        self._running = True

        while self._running:
            try:
                # 阻塞等待新文本，超时1秒以检查 _running
                text = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                result = self._translator.translate(text)
                if result:
                    self.translation_ready.emit(text, result)
                else:
                    self.translation_error.emit(text, "翻译返回空结果")
            except Exception as e:
                logger.error(f"翻译异常: {e}")
                self.translation_error.emit(text, str(e))

        logger.info("翻译工作线程退出")

    def stop(self):
        """停止线程"""
        self._running = False
        # 放入哨兵值确保线程能从阻塞中醒来
        self._queue.put("__STOP__")
        self.wait(3000)
