"""
翻译历史记录写入器

将每次翻译结果异步写入本地文本文件，
按日期命名，格式化为可读的台词记录。
"""

import os
import logging
import queue
import threading
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class HistoryWriter(QObject):
    """
    翻译历史记录管理器。

    使用队列 + QTimer 异步写入，不阻塞UI线程。
    每天自动创建一个新文件。

    文件格式：
    ============================================================
    Clude翻译App - 翻译记录
    日期：2026-08-05 20:30:15
    ============================================================

    [00:05:23]
    EN: We used to look up at the sky...
    ZH: 我们曾经仰望星空...

    ---
    """

    def __init__(self, history_dir: str = "./翻译记录"):
        super().__init__()
        self._history_dir = history_dir
        self._queue: queue.Queue = queue.Queue()
        self._session_start = datetime.now()
        self._current_file = None
        self._file_lock = threading.Lock()

        # 确保目录存在
        os.makedirs(self._history_dir, exist_ok=True)

        # 创建今天的文件
        self._open_today_file()
        self._write_header()

        # 使用 QTimer 定期刷新队列（在主线程中执行文件IO）
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._process_queue)
        self._flush_timer.start(1000)  # 每秒刷新一次

        logger.info(f"历史记录目录: {os.path.abspath(self._history_dir)}")

    def _get_today_filename(self) -> str:
        """获取今天的记录文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self._history_dir, f"{today}_翻译记录.txt")

    def _open_today_file(self):
        """打开（或创建）今天的记录文件"""
        self._current_file = self._get_today_filename()

        # 跨天后切换文件
        if not os.path.exists(self._current_file):
            self._session_start = datetime.now()

        logger.info(f"记录文件: {os.path.basename(self._current_file)}")

    def _write_header(self):
        """写入会话头部信息"""
        if not self._current_file:
            return

        # 只在新建文件或新会话时写头部
        if os.path.exists(self._current_file):
            return

        with self._file_lock:
            try:
                with open(self._current_file, "a", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write("Clude翻译App - 翻译记录\n")
                    f.write(
                        f"开始时间："
                        f"{self._session_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    )
                    f.write("=" * 60 + "\n\n")
            except Exception as e:
                logger.error(f"写入文件头失败: {e}")

    def enqueue(self, original: str, translated: str, mode: str = "ocr"):
        """
        将一条翻译记录加入写入队列（线程安全）。

        参数：
            original: 原文
            translated: 译文
            mode: 识别模式 ("ocr" 或 "audio")
        """
        if original and translated:
            self._queue.put({
                "original": original,
                "translated": translated,
                "mode": mode,
                "time": datetime.now(),
            })

    def _process_queue(self):
        """处理队列中的所有待写入记录（由QTimer触发）"""
        # 检查是否需要跨天切换文件
        today_file = self._get_today_filename()
        if today_file != self._current_file:
            self._current_file = today_file
            self._write_header()

        entries = []
        while not self._queue.empty():
            try:
                entries.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not entries:
            return

        with self._file_lock:
            try:
                with open(self._current_file, "a", encoding="utf-8") as f:
                    for entry in entries:
                        f.write(
                            f"[{entry['time'].strftime('%H:%M:%S')}] "
                            f"({entry['mode']})\n"
                        )
                        f.write(f"原文: {entry['original']}\n")
                        f.write(f"译文: {entry['translated']}\n")
                        f.write("---\n\n")
            except Exception as e:
                logger.error(f"写入记录失败: {e}")

    def flush(self):
        """强制写入所有待处理记录（退出前调用）"""
        self._process_queue()

    def get_history_dir(self) -> str:
        """获取历史记录目录路径"""
        return os.path.abspath(self._history_dir)
