"""
翻译器抽象接口 + 工厂函数

提供统一的翻译接口，方便切换不同的翻译后端。
"""

from abc import ABC, abstractmethod

from config.settings import AppSettings


class BaseTranslator(ABC):
    """翻译器抽象基类"""

    @abstractmethod
    def translate(
        self, text: str, source: str = "auto", target: str = "zh-CN"
    ) -> str | None:
        """
        翻译文本。

        参数：
            text: 待翻译的文本
            source: 源语言代码（"auto" = 自动检测）
            target: 目标语言代码

        返回：
            翻译后的文本，失败返回 None
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查翻译服务是否可用"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """后端名称"""
        ...


def create_translator(settings: AppSettings) -> BaseTranslator:
    """
    根据配置创建翻译器实例。

    优先使用用户配置的后端，
    如果指定的后端不可用，自动降级到可用后端。
    """
    backend = settings.get("translation_backend", "auto")

    if backend == "deepl":
        api_key = settings.get("deepl_api_key", "")
        if api_key:
            from translate.deepl_backend import DeepLBackend
            translator = DeepLBackend(api_key)
            if translator.is_available():
                return translator

    # 默认使用多后端（自动选择 MyMemory → Google）
    from translate.google_backend import MultiBackend
    return MultiBackend(
        source=settings.get("source_language", "auto"),
        target=settings.get("target_language", "zh-CN"),
    )
