"""
文本处理工具函数
"""

import re
import hashlib


def normalize_text(text: str) -> str:
    """
    标准化文本：去除多余空白、转小写、去重复标点。
    用于去重比较前的预处理。
    """
    text = text.lower().strip()
    # 合并连续空格
    text = re.sub(r'\s+', ' ', text)
    # 去掉重复的标点符号（如 "..." → "."）
    text = re.sub(r'[.!?]{2,}', '.', text)
    # 去掉重复逗号
    text = re.sub(r',{2,}', ',', text)
    return text


def fast_hash(text: str) -> str:
    """快速哈希（用于去重缓存键）"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def levenshtein_ratio(s1: str, s2: str) -> float:
    """
    计算两个字符串的 Levenshtein 相似度。
    返回 0.0 ~ 1.0 之间的值，1.0 表示完全相同。
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len1, len2 = len(s1), len(s2)
    # 使用两行优化的 Levenshtein 距离
    prev = list(range(len2 + 1))
    curr = [0] * (len2 + 1)

    for i in range(1, len1 + 1):
        curr[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # 删除
                curr[j - 1] + 1,    # 插入
                prev[j - 1] + cost  # 替换
            )
        prev, curr = curr, prev

    distance = prev[len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len)


def truncate(text: str, max_len: int = 200) -> str:
    """截断文本到指定长度"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def clean_ocr_text(text: str) -> str:
    """
    清洗 OCR 输出的文本。
    - 去除常见 OCR 噪声字符
    - 合并断行
    - 去除前后空白
    """
    # 去除一些常见的 OCR 噪声
    text = text.replace('\r', ' ')
    text = text.replace('\n', ' ')
    # 合并空格
    text = re.sub(r'\s+', ' ', text)
    # 去除首尾空白
    text = text.strip()
    return text
