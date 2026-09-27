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
        # hash → (归一化文本, 时间戳)。归一化文本用于模糊匹配，
        # 只存 hash 的话 OCR 微差（一个标点/字母）就无法识别为重复。
        self._seen: OrderedDict[str, tuple] = OrderedDict()
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
                self._seen[text_hash] = (normalized, now)
                self._seen.move_to_end(text_hash)
                return True

            # 2. 清理过期条目 + 模糊匹配（Levenshtein 相似度，
            #    处理 OCR 逐帧识别的微小差异：标点、空格、个别字符）
            expired_keys = []
            for seen_hash, (seen_text, timestamp) in list(self._seen.items()):
                if now - timestamp > self._expiry_seconds:
                    expired_keys.append(seen_hash)
                    continue
                if levenshtein_ratio(normalized, seen_text) >= self._similarity_threshold:
                    # 视为同一条字幕：更新时间戳，不重复翻译
                    self._seen[seen_hash] = (seen_text, now)
                    self._seen.move_to_end(seen_hash)
                    return True

            for key in expired_keys:
                del self._seen[key]

            # 3. 添加当前条目
            self._seen[text_hash] = (normalized, now)

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
                1 for _text, t in self._seen.values()
                if now - t <= self._expiry_seconds
            )
            return {
                "total_cached": len(self._seen),
                "active": active,
                "expiry_seconds": self._expiry_seconds,
            }
