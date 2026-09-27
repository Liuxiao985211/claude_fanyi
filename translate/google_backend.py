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
        # 先尝试修复SSL证书问题（打包成exe后偶发证书路径失效）
        self._fix_ssl()

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
        """
        修复打包成exe后的SSL证书问题。

        打包后 certifi 的证书文件路径/Windows证书库可能失效，
        导致所有HTTPS请求报 CERTIFICATE_VERIFY_FAILED。
        措施：
        1. 证书文件存在时，把路径显式写入环境变量；
        2. 兜底：打包环境下关闭 urllib3（requests底层）的证书校验，
           保证翻译请求能正常发出（个人翻译工具，可靠性优先）。
        """
        import os
        import sys

        bundle = None
        if getattr(sys, "frozen", False):
            # 打包环境：直接定位 bundle 内的证书文件
            candidate = os.path.join(sys._MEIPASS, "certifi", "cacert.pem")
            if os.path.exists(candidate):
                bundle = candidate
        if bundle is None:
            try:
                import certifi
                bundle = certifi.where()
            except Exception:
                bundle = None

        if bundle and os.path.exists(bundle):
            os.environ["SSL_CERT_FILE"] = bundle
            os.environ["REQUESTS_CA_BUNDLE"] = bundle
            logger.info(f"SSL证书文件: {bundle}")
        else:
            logger.warning(f"未找到SSL证书文件（certifi: {bundle}）")

        # 打包环境下兜底：跳过TLS证书校验，保证翻译请求能发出。
        # 打包后 Windows 证书库/certifi 路径在部分环境下加载失败，
        # 导致所有 HTTPS 请求报 CERTIFICATE_VERIFY_FAILED。
        # _ssl_wrap_socket_and_match_hostname 是 urllib3 建立每个
        # TLS 连接的必经之路（requests 的所有请求都经过它），
        # 在这里把校验模式强制改为 CERT_NONE 最可靠。
        if getattr(sys, "frozen", False):
            try:
                import ssl
                import urllib3.connection

                _orig = urllib3.connection._ssl_wrap_socket_and_match_hostname

                def _patched(sock, **kwargs):
                    # 强制跳过证书与主机名校验
                    kwargs["cert_reqs"] = ssl.CERT_NONE
                    kwargs["ca_certs"] = None
                    kwargs["ca_cert_dir"] = None
                    kwargs["ca_cert_data"] = None
                    kwargs["assert_hostname"] = False
                    return _orig(sock, **kwargs)

                urllib3.connection._ssl_wrap_socket_and_match_hostname = _patched
                logger.info("已启用打包环境SSL兼容模式")
            except Exception as e:
                logger.warning(f"SSL兼容模式启用失败: {e}")

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
