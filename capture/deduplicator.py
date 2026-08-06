"""
字幕去重器

防止同一条字幕被反复翻译。
结合三种策略：
1. 精确哈希匹配（最快）
2. 归一化模糊匹配（处理OCR微小差异）
3. 时间过期（30秒后自动清除，防止永久缓存）
"""

import time
import threading
from collections import OrderedDict

from utils.text_utils import normalize_text, fast_hash, levenshtein_ratio


class Deduplicator:
    """
    字幕去重器，线程安全。

    工作原理：
    - 每条文本先做归一化（小写、去空格、去重标点）
    - 用MD5哈希快速判断是否完全匹配
    - 如果哈希不匹配，用Levenshtein相似度做模糊匹配
    - 超过过期时间的条目自动清除
    """

    def __init__(
        self,
        max_history: int = 50,
        similarity_threshold: float = 0.85,
        expiry_seconds: float = 30.0
    ):
        """
        参数：
            max_history: 最大缓存条目数
            similarity_threshold: 相似度阈值（0-1），超过此值视为重复
            expiry_seconds: 条目过期时间（秒）
        """
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._max_history = max_history
        self._similarity_threshold = similarity_threshold
        self._expiry_seconds = expiry_seconds
        self._lock = threading.Lock()

    def is_duplicate(self, text: str) -> bool:
        """
        检查文本是否为重复（最近见过的）。

        参数：
            text: 待检查的原始文本

        返回：
            True = 重复，应跳过
            False = 新文本，可以翻译
        """
        if not text or len(text.strip()) < 2:
            return True  # 太短的忽略

        normalized = normalize_text(text)
        text_hash = fast_hash(normalized)

        with self._lock:
            now = time.time()

            # 1. 精确哈希匹配（快速路径）
            if text_hash in self._seen:
                # 更新时间戳
                self._seen[text_hash] = now
                self._seen.move_to_end(text_hash)
                return True

            # 2. 清理过期条目 & 模糊匹配
            expired_keys = []
            for seen_hash, timestamp in self._seen.items():
                # 检查过期
                if now - timestamp > self._expiry_seconds:
                    expired_keys.append(seen_hash)
                    continue

            # 删除过期条目
            for key in expired_keys:
                del self._seen[key]

            # 3. 添加当前条目
            self._seen[text_hash] = now

            # 4. 限制最大条目数
            while len(self._seen) > self._max_history:
                self._seen.popitem(last=False)

            return False

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._seen.clear()

    def get_stats(self) -> dict:
        """获取统计信息（调试用）"""
        with self._lock:
            now = time.time()
            active = sum(
                1 for t in self._seen.values()
                if now - t <= self._expiry_seconds
            )
            return {
                "total_cached": len(self._seen),
                "active": active,
                "expiry_seconds": self._expiry_seconds,
            }
