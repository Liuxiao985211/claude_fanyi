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

    MAX_QUEUE = 30  # 队列上限：字幕翻译要跟画面同步，旧文本没有价值

    def __init__(self, translator: BaseTranslator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._queue: queue.Queue = queue.Queue(maxsize=self.MAX_QUEUE)
        self._running = False
        self._dropped = 0  # 因队列满被丢弃的文本数（诊断用）

    def enqueue(self, text: str):
        """
        将文本加入翻译队列（线程安全，可从任意线程调用）。

        队列满时丢弃最旧的一条换入最新：网络慢时宁可少翻，
        也不让字幕延迟越积越大。
        """
        if not text or len(text.strip()) < 2:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            try:
                self._queue.get_nowait()  # 丢最旧
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(text)
            except queue.Full:
                pass  # 极端竞态下放弃本条，下一条还会来
            self._dropped += 1
            if self._dropped % 20 == 1:
                logger.warning(
                    f"翻译队列已满，累计丢弃 {self._dropped} 条（翻译速度跟不上捕获速度）"
                )

    def run(self):
        """主循环：取最新文本 → 翻译 → 发信号"""
        logger.info(f"翻译工作线程启动 (后端: {self._translator.name})")
        self._running = True

        while self._running:
            try:
                # 阻塞等待新文本，超时1秒以检查 _running
                text = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            # 只翻最新一条：把队列里积压的文本全部清掉，保留最后一条。
            # 字幕场景下中间状态的句子翻出来也已经过时。
            while True:
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:  # 停止哨兵
                    text = None
                    break
                text = nxt

            if text is None:
                break

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
        self._queue.put(None)
        self.wait(3000)
