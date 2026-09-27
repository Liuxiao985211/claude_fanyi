"""
LLM 翻译后端（默认，国内可用）

走本机 cnsai 回退代理（127.0.0.1:8642）：
- 代理已实现「cnsai 中转站优先，DeepSeek 官方兜底」策略
- 密钥只存在于代理的 config.json，应用不持有任何 API Key
- 协议：Anthropic Messages API 格式（POST /v1/messages）

gstack-shortcut(dec-self-use-repair-v1): 单句翻译，无上下文窗口。
upgrade when 出现第一个追着要新版的外部用户（届时升级为 LLM 上下文窗口翻译）。
"""

import json
import logging
import urllib.request

from translate.translator import BaseTranslator

logger = logging.getLogger(__name__)

# 目标语言代码 → 提示词用的语言名
LANG_NAMES = {
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
}

TRANSLATE_PROMPT = (
    "You are a subtitle translator. Translate the text after \"Text:\" "
    "into {target}. Output ONLY the translation, no explanations, no quotes."
)


class LLMBackend(BaseTranslator):
    """通过本机代理调用 LLM 的翻译后端。"""

    def __init__(
        self,
        model: str = "deepseek-v4-pro",
        base_url: str = "http://127.0.0.1:8642",
        timeout_s: float = 30.0,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._available = None  # None=未检测, True/False=检测结果

    # ==================== BaseTranslator 接口 ====================

    @property
    def name(self) -> str:
        return f"LLM ({self._model})"

    def is_available(self) -> bool:
        if self._available is None:
            self._available = self._ping()
        return self._available

    def translate(
        self, text: str, source: str = "auto", target: str = "zh-CN"
    ) -> str | None:
        if not text or len(text.strip()) < 2:
            return None

        target_name = LANG_NAMES.get(target, target)
        user_prompt = f"{TRANSLATE_PROMPT.format(target=target_name)}\n\nText: {text.strip()}"

        try:
            result = self._chat([{"role": "user", "content": user_prompt}])
        except Exception as e:
            logger.warning(f"LLM翻译失败: {e}")
            return None

        if not result:
            return None
        # 去掉模型偶尔附带的引号/空行
        result = result.strip().strip('"').strip()
        return result or None

    # ==================== 内部实现 ====================

    def _ping(self) -> bool:
        """发一个最小请求检测服务可用性（thinking 关闭，几乎零成本）"""
        try:
            self._chat([{"role": "user", "content": "ping"}], max_tokens=1)
            return True
        except Exception as e:
            logger.warning(f"LLM后端不可用: {e}")
            return False

    def _chat(self, messages: list, max_tokens: int = 200) -> str:
        """
        发送 Anthropic Messages 格式请求到本机代理。

        返回：助手文本（拼接所有 type=="text" 的内容块）。
        """
        payload = json.dumps({
            "model": self._model,
            "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},  # 推理模型也要关掉思考，字幕翻译要快
            "messages": messages,
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            self._base_url + "/v1/messages",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
        )

        # 显式禁用系统代理：urllib 默认读 Windows 注册表的代理设置，
        # 请求 localhost 会被发到系统代理（如 127.0.0.1:26561）并 404。
        # 本机代理必须直连。
        with _NO_PROXY_OPENER.open(req, timeout=self._timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts).strip()


# 无代理 opener（模块级单例，所有请求共用）
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
