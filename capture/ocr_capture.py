"""
OCR 屏幕字幕捕获模块

使用 dxcam（D3D11加速）或 Pillow 截取屏幕底部字幕区域，
通过 Windows 内置 OCR 引擎识别文字。
无需安装额外的大型依赖（如 easyocr/torch）。

支持的后端（按优先级）：
1. Windows OCR（winrt，Win10+内置，推荐）
2. EasyOCR（可选，需要 pip install easyocr）
3. pytesseract（可选，需要安装 Tesseract）
"""

import logging
import numpy as np

from utils.text_utils import clean_ocr_text

logger = logging.getLogger(__name__)


class OCRCapture:
    """
    屏幕字幕捕获器。

    工作流程：
    1. dxcam/Pillow 截取全屏
    2. 裁剪屏幕底部字幕区域
    3. OCR引擎识别文字
    4. 清洗文本并返回
    """

    def __init__(
        self,
        region_ratio: float = 0.15,
        languages: list = None,
        display_index: int = 0,
        backend: str = "auto",
    ):
        """
        参数：
            region_ratio: 从屏幕底部截取的比例（0.15 = 底部15%区域）
            languages: OCR语言代码列表，默认 ['en']
            display_index: 显示器索引，0 = 主显示器
            backend: OCR后端 ("auto" | "windows" | "easyocr" | "tesseract")
        """
        self._region_ratio = region_ratio
        self._languages = languages or ["en"]
        self._display_index = display_index
        self._backend_name = backend

        # 延迟初始化
        self._camera = None          # dxcam
        self._reader = None          # easyocr
        self._ocr_engine = None      # Windows OCR
        self._initialized = False
        self._backend = None         # 实际使用的后端

        # 屏幕分辨率
        self._screen_width = 1920
        self._screen_height = 1080

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> bool:
        """
        初始化屏幕捕获和OCR引擎。
        自动选择可用的后端。
        """
        # ---- 第1步：初始化屏幕捕获 ----
        if not self._init_capture():
            return False

        # ---- 第2步：初始化OCR引擎 ----
        if not self._init_ocr():
            return False

        self._initialized = True
        logger.info(f"OCRCapture就绪 (捕获: dxcam, OCR: {self._backend})")
        return True

    def _init_capture(self) -> bool:
        """初始化屏幕截图"""
        # 优先使用 dxcam（D3D11加速）
        try:
            import dxcam
            self._camera = dxcam.create(
                device_idx=self._display_index,
                output_color="BGR"
            )
            if self._camera is not None:
                self._screen_width = self._camera.width
                self._screen_height = self._camera.height
                logger.info(f"dxcam就绪: {self._screen_width}x{self._screen_height}")
                return True
        except Exception as e:
            logger.debug(f"dxcam不可用: {e}")

        # 降级到 Pillow
        try:
            from PIL import ImageGrab, Image
            self._use_pillow = True
            # Pillow 方式无法预先获取分辨率，捕获时再获取
            logger.info("使用Pillow截图（无GPU加速）")
            return True
        except Exception as e:
            logger.error(f"截图模块不可用: {e}")
            return False

    def _init_ocr(self) -> bool:
        """初始化OCR引擎，按优先级尝试"""
        # 如果没有指定后端，自动选择
        if self._backend_name == "auto":
            backends_to_try = ["windows", "easyocr", "tesseract"]
        else:
            backends_to_try = [self._backend_name]

        for backend in backends_to_try:
            if backend == "windows" and self._try_init_windows_ocr():
                return True
            elif backend == "easyocr" and self._try_init_easyocr():
                return True
            elif backend == "tesseract" and self._try_init_tesseract():
                return True

        logger.error("没有可用的OCR引擎！")
        return False

    def _try_init_windows_ocr(self) -> bool:
        """初始化 Windows 10/11 内置 OCR"""
        try:
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.globalization import Language

            # 映射语言代码到 Windows 语言标签
            lang_map = {
                "en": "en-US",
                "zh": "zh-Hans",
                "ja": "ja",
                "ko": "ko",
                "fr": "fr",
                "de": "de",
                "es": "es",
            }
            lang_tag = lang_map.get(self._languages[0], "en-US")

            # 尝试创建指定语言的引擎
            try:
                lang = Language(lang_tag)
                self._ocr_engine = OcrEngine.try_create_from_language(lang)
            except Exception:
                self._ocr_engine = None

            # 如果指定语言不可用，使用系统默认语言
            if self._ocr_engine is None:
                logger.warning(
                    f"语言 '{lang_tag}' 不可用，使用系统默认OCR语言"
                )
                self._ocr_engine = OcrEngine.try_create_from_user_profile_languages()

            if self._ocr_engine:
                self._backend = "windows"
                logger.info(
                    f"Windows OCR就绪 "
                    f"({self._ocr_engine.recognizer_language.display_name})"
                )
                return True

        except ImportError:
            logger.debug("winrt未安装")
        except Exception as e:
            logger.debug(f"Windows OCR不可用: {e}")

        return False

    def _try_init_easyocr(self) -> bool:
        """初始化 EasyOCR"""
        try:
            import easyocr
            lang_str = "".join(self._languages)
            logger.info(f"加载EasyOCR模型（语言: {lang_str}）...")
            self._reader = easyocr.Reader(self._languages, gpu=False)
            self._backend = "easyocr"
            logger.info("EasyOCR就绪")
            return True
        except ImportError:
            logger.debug("easyocr未安装")
        except Exception as e:
            logger.warning(f"EasyOCR初始化失败: {e}")
        return False

    def _try_init_tesseract(self) -> bool:
        """初始化 Tesseract OCR"""
        try:
            import pytesseract
            # 测试 tesseract 是否可用
            pytesseract.get_tesseract_version()
            self._pytesseract = pytesseract
            self._backend = "tesseract"
            logger.info("Tesseract OCR就绪")
            return True
        except ImportError:
            logger.debug("pytesseract未安装")
        except Exception as e:
            logger.debug(f"Tesseract不可用: {e}")
        return False

    def capture_and_ocr(self) -> str | None:
        """
        执行一次截图+OCR。

        返回：
            识别到的文本，如果没有文字则返回 None
        """
        if not self._initialized:
            return None

        try:
            # 1. 截图
            image = self._capture_screen()
            if image is None:
                return None

            # 2. OCR识别
            text = self._run_ocr(image)
            if not text:
                return None

            # 3. 清洗
            cleaned = clean_ocr_text(text)
            if len(cleaned) < 2:
                return None

            return cleaned

        except Exception as e:
            logger.error(f"OCR捕获失败: {e}")
            return None

    def _capture_screen(self):
        """截取屏幕底部字幕区域"""
        if self._camera is not None:
            # dxcam 路径
            try:
                frame = self._camera.grab()
                if frame is not None:
                    h, w = frame.shape[:2]
                    self._screen_width = w
                    self._screen_height = h
                    crop_top = int(h * (1.0 - self._region_ratio))
                    cropped = frame[crop_top:, :]
                    return cropped
            except Exception as e:
                logger.debug(f"dxcam截图失败: {e}")

        # Pillow 降级路径
        try:
            from PIL import ImageGrab
            import numpy as np
            img = ImageGrab.grab()
            w, h = img.size
            self._screen_width = w
            self._screen_height = h
            crop_top = int(h * (1.0 - self._region_ratio))
            cropped = img.crop((0, crop_top, w, h))
            return np.array(cropped)
        except Exception as e:
            logger.error(f"截图失败: {e}")

        return None

    def _run_ocr(self, image) -> str | None:
        """根据后端选择合适的OCR方法"""
        if self._backend == "windows":
            return self._ocr_windows(image)
        elif self._backend == "easyocr":
            return self._ocr_easyocr(image)
        elif self._backend == "tesseract":
            return self._ocr_tesseract(image)
        return None

    def _ocr_windows(self, image: np.ndarray) -> str | None:
        """使用 Windows 内置 OCR（通过 asyncio 调用异步API）"""
        try:
            from winrt.windows.graphics.imaging import (
                SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
            )
            import asyncio

            h, w = image.shape[:2]

            # 确保图像格式正确 -> BGRA8
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            if len(image.shape) == 2:
                # 灰度图 → 转BGRA
                rgba[:, :, 0] = image
                rgba[:, :, 1] = image
                rgba[:, :, 2] = image
            elif image.shape[2] == 3:
                rgba[:, :, :3] = image
            else:
                rgba = image
            rgba[:, :, 3] = 255

            # 创建 SoftwareBitmap 并填充数据
            bitmap = SoftwareBitmap(
                BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.STRAIGHT
            )
            bitmap.copy_from_buffer(rgba.tobytes())

            # 使用 asyncio 调用异步OCR API
            async def _recognize():
                result = await self._ocr_engine.recognize_async(bitmap)
                return result

            result = asyncio.run(_recognize())
            bitmap.close()

            if result and result.lines:
                lines = [line.text for line in result.lines]
                return " ".join(lines)

        except Exception as e:
            logger.debug(f"Windows OCR失败: {type(e).__name__}: {e}")

        return None

    def _ocr_easyocr(self, image: np.ndarray) -> str | None:
        """使用 EasyOCR"""
        if not self._reader:
            return None

        try:
            # 转灰度加速
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            results = self._reader.readtext(gray, detail=0)
            if results:
                return " ".join(results)
        except Exception as e:
            logger.debug(f"EasyOCR失败: {e}")

        return None

    def _ocr_tesseract(self, image: np.ndarray) -> str | None:
        """使用 Tesseract OCR"""
        try:
            from PIL import Image
            pil_img = Image.fromarray(image)
            lang = "+".join(self._languages)
            text = self._pytesseract.image_to_string(pil_img, lang=lang)
            return text.strip() or None
        except Exception as e:
            logger.debug(f"Tesseract失败: {e}")

        return None

    def update_region(self):
        """更新捕获区域（屏幕分辨率变化时调用）"""
        if self._camera:
            self._screen_width = self._camera.width
            self._screen_height = self._camera.height

    def shutdown(self):
        """释放资源"""
        self._reader = None
        self._ocr_engine = None
        self._camera = None
        self._initialized = False
