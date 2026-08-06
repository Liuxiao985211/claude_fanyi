"""
音频捕获工作线程

在独立线程中持续捕获系统音频输出（WASAPI loopback），
进行语音活动检测和语音识别，
通过信号将识别文本发送到主线程。
"""

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from capture.audio_capture import AudioCapture
from capture.deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class AudioWorker(QThread):
    """
    音频捕获工作线程。

    持续监听系统音频输出，
    检测到语音后进行语音识别（STT），
    去重后通过 speech_detected 信号发出。
    """

    # 信号
    speech_detected = pyqtSignal(str)       # 识别到语音文本（已去重）
    audio_error = pyqtSignal(str)            # 错误消息
    audio_initialized = pyqtSignal(bool)     # 初始化完成

    def __init__(
        self,
        audio: AudioCapture,
        dedup: Deduplicator,
        parent=None
    ):
        super().__init__(parent)
        self._audio = audio
        self._dedup = dedup
        self._running = False
        self._paused = False

    def run(self):
        """主循环：初始化音频 → 持续捕获 → STT → 去重 → 发信号"""
        logger.info("音频工作线程启动")

        # 初始化音频捕获
        if not self._audio.initialize():
            self.audio_initialized.emit(False)
            self.audio_error.emit(
                "音频捕获初始化失败。\n"
                "可能原因：没有WASAPI loopback设备、麦克风权限未开启。\n"
                "将仅使用OCR模式。"
            )
            return

        self.audio_initialized.emit(True)
        self._running = True

        # 开始音频流
        self._audio.start_capture()

        # 持续处理识别结果
        while self._running:
            try:
                if not self._paused:
                    # 非阻塞获取识别结果
                    text = self._audio.get_result(timeout=0.5)
                    if text and not self._dedup.is_duplicate(text):
                        self.speech_detected.emit(text)

                self.msleep(100)  # 避免忙等待

            except Exception as e:
                logger.error(f"音频循环异常: {e}")
                self.audio_error.emit(str(e))

        # 清理
        self._audio.stop_capture()
        self._audio.shutdown()
        logger.info("音频工作线程退出")

    def pause(self):
        """暂停音频捕获"""
        self._paused = True
        logger.info("音频已暂停")

    def resume(self):
        """恢复音频捕获"""
        self._paused = False
        logger.info("音频已恢复")

    def stop(self):
        """停止线程"""
        self._running = False
        self._audio.stop_capture()
        self.wait(3000)
