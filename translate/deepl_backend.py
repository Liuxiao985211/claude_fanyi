"""
DeepL 翻译后端（可选，需要API Key）

DeepL 翻译质量通常优于 Google Translate，
但需要注册免费账号获取 API Key（每月50万字符免费额度）。
"""

import logging

from translate.translator import BaseTranslator

logger = logging.getLogger(__name__)


class DeepLBackend(BaseTranslator):
    """
    DeepL 翻译后端。

    需要 API Key，免费版每月50万字符。
    注册地址：https://www.deepl.com/pro-api
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._translator = None

        if api_key:
            self._init_translator()

    def _init_translator(self):
        """初始化 DeepL 翻译器"""
        try:
            import deepl
            self._translator = deepl.Translator(self._api_key)
            # 检查使用情况
            usage = self._translator.get_usage()
            if usage.any_limit_reached:
                logger.warning("DeepL API额度已用尽")
                self._translator = None
            else:
                logger.info(
                    f"DeepL翻译后端就绪 "
                    f"(已用: {usage.character.count}/{usage.character.limit})"
                )
        except ImportError:
            logger.warning("deepl库未安装，请执行: pip install deepl")
            self._translator = None
        except Exception as e:
            logger.warning(f"DeepL初始化失败: {e}")
            self._translator = None

    @property
    def name(self) -> str:
        return "DeepL"

    def is_available(self) -> bool:
        return self._translator is not None

    def translate(
        self, text: str, source: str = "auto", target: str = "zh-CN"
    ) -> str | None:
        """
        使用 DeepL 翻译文本。

        注意：DeepL 的目标语言代码略有不同：
        - 中文: "ZH" (不是 "zh-CN")
        - 英文: "EN-US" 或 "EN-GB"
        """
        if not self._translator:
            return None
        if not text or len(text.strip()) < 2:
            return None

        try:
            # 转换语言代码为DeepL格式
            deepl_target = self._to_deepl_lang(target)
            deepl_source = None if source == "auto" else self._to_deepl_lang(source)

            import deepl
            result = self._translator.translate_text(
                text,
                source_lang=deepl_source,
                target_lang=deepl_target
            )
            return result.text

        except Exception as e:
            logger.error(f"DeepL翻译失败: {e}")
            return None

    @staticmethod
    def _to_deepl_lang(code: str) -> str:
        """将通用语言代码转换为 DeepL 格式"""
        mapping = {
            "zh-CN": "ZH",
            "zh": "ZH",
            "en": "EN-US",
            "auto": None,
            "ja": "JA",
            "ko": "KO",
            "fr": "FR",
            "de": "DE",
            "es": "ES",
            "pt": "PT",
            "it": "IT",
        }
        return mapping.get(code, code.upper())
