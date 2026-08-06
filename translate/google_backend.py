"""
多后端翻译模块

按优先级自动选择可用的翻译后端：
1. MyMemory — 免费，无需API Key，通常全球可访问
2. Google Translate — 免费，某些地区可能被屏蔽
3. DeepL — 需要API Key，翻译质量最高

用法：
    from translate.translator import create_translator
    translator = create_translator(settings)
    result = translator.translate("hello world")
"""

import logging
import time
import traceback

from translate.translator import BaseTranslator

logger = logging.getLogger(__name__)


class MultiBackend(BaseTranslator):
    """
    多后端翻译器。
    自动选择第一个可用的免费后端。
    """

    def __init__(self, source: str = "auto", target: str = "zh-CN"):
        self._source = source
        self._target = target
        self._backend = None
        self._backend_name = ""
        self._max_retries = 2
        self._base_delay = 1.0

        # 语言代码映射（标准代码 → MyMemory代码）
        self._lang_map = {
            "en": "en-GB",
            "zh-CN": "zh-CN",
            "zh": "zh-CN",
            "ja": "ja-JP",
            "ko": "ko-KR",
            "fr": "fr-FR",
            "de": "de-DE",
            "es": "es-ES",
            "auto": "auto",
        }

        self._init_backend()

    def _map_lang(self, code: str) -> str:
        """映射标准语言代码到后端需要的格式"""
        return self._lang_map.get(code, code)

    def _init_backend(self):
        """自动选择可用的翻译后端"""
        # 后端1: MyMemory（免费，无API Key）
        try:
            from deep_translator import MyMemoryTranslator
            # MyMemory不支持 'auto'，默认使用英文
            src = self._map_lang(self._source)
            if src == "auto":
                src = "en-GB"
            tgt = self._map_lang(self._target)
            translator = MyMemoryTranslator(source=src, target=tgt)
            result = translator.translate("test")
            if result and "INVALID" not in result.upper():
                self._backend = translator
                self._backend_name = "MyMemory"
                self._source_mapped = src
                self._target_mapped = tgt
                logger.info("翻译后端就绪: MyMemory (免费)")
                return
        except Exception as e:
            logger.warning(f"MyMemory不可用: {e}")
            logger.debug(traceback.format_exc())

        # 后端2: Google Translate（免费，某些地区可能被屏蔽）
        try:
            # 尝试修复SSL
            self._fix_ssl()
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(
                source=self._source, target=self._target
            )
            result = translator.translate("test")
            if result:
                self._backend = translator
                self._backend_name = "Google Translate"
                logger.info("翻译后端就绪: Google Translate (免费)")
                return
        except Exception as e:
            logger.warning(f"Google不可用: {e}")
            logger.debug(traceback.format_exc())

        logger.warning("所有免费翻译后端均不可用！")

    @staticmethod
    def _fix_ssl():
        """尝试修复SSL证书问题"""
        try:
            import certifi
            import os
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
            os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
        except ImportError:
            pass
        try:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
        except Exception:
            pass

    @property
    def name(self) -> str:
        return self._backend_name or "None"

    def is_available(self) -> bool:
        return self._backend is not None

    def translate(
        self, text: str, source: str = "auto", target: str = "zh-CN"
    ) -> str | None:
        """
        翻译文本，带重试逻辑。
        """
        if not self._backend:
            return None

        if not text or len(text.strip()) < 2:
            return None

        for attempt in range(self._max_retries):
            try:
                result = self._backend.translate(text)
                if result and result != text:
                    return str(result)

            except Exception as e:
                delay = self._base_delay * (2 ** attempt)
                logger.warning(
                    f"翻译失败 (尝试 {attempt + 1}/{self._max_retries}): {e}"
                )
                if attempt < self._max_retries - 1:
                    time.sleep(delay)

        return None
