"""
音频捕获模块

使用 sounddevice 捕获系统音频输出（WASAPI loopback），
通过 SpeechRecognition 进行语音识别（STT）。

工作原理：
1. 查找 WASAPI loopback 设备（捕获"电脑正在播放的声音"）
2. 音频流回调中进行能量检测（VAD）
3. 检测到静音超过1秒时，将缓冲的语音段送STT
4. STT结果放入队列供 AudioWorker 消费
"""

import logging
import queue
import threading
import numpy as np

logger = logging.getLogger(__name__)


class AudioCapture:
    """
    系统音频捕获 + 语音识别器。

    使用 WASAPI loopback 捕获系统播放的音频（不需要麦克风），
    能量阈值检测语音活动，静音时触发语音识别。
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_duration_s: float = 2.0,
        vad_threshold: float = 0.02,
        silence_duration_s: float = 1.0,
        stt_engine: str = "google",
    ):
        """
        参数：
            sample_rate: 采样率（Hz）
            chunk_duration_s: 每个音频块的长度（秒）
            vad_threshold: 语音活动检测的能量阈值
            silence_duration_s: 静音多久后触发STT（秒）
            stt_engine: STT引擎 ("google" | "whisper" | "vosk")
        """
        self._sample_rate = sample_rate
        self._chunk_duration_s = chunk_duration_s
        self._vad_threshold = vad_threshold
        self._silence_duration_s = silence_duration_s
        self._stt_engine = stt_engine

        # 状态
        self._initialized = False
        self._stream = None
        self._device_id = None

        # 音频缓冲
        self._buffer = []
        self._is_speech = False
        self._silence_start = None
        self._buffer_lock = threading.Lock()

        # STT 引擎
        self._recognizer = None
        self._whisper_model = None
        self._vosk_model = None

        # 识别结果队列（线程安全）
        self._result_queue = queue.Queue()

        # 最后的语音段
        self._speech_segment = None
        self._speech_segments = []

    def initialize(self) -> bool:
        """
        初始化音频设备和STT引擎。

        返回：
            True = 初始化成功
        """
        try:
            import sounddevice as sd

            # 1. 查找 WASAPI loopback 设备
            self._device_id = self._find_loopback_device()
            if self._device_id is None:
                logger.warning("未找到WASAPI loopback设备")
                return False

            device_info = sd.query_devices(self._device_id)
            logger.info(
                f"音频设备: {device_info['name']} "
                f"(channels: {device_info['max_input_channels']})"
            )

            # 使用设备的默认采样率
            self._sample_rate = int(device_info['default_samplerate'])

            # 2. 初始化STT引擎
            if not self._init_stt_engine():
                return False

            self._initialized = True
            return True

        except ImportError:
            logger.warning("sounddevice库未安装")
            return False
        except Exception as e:
            logger.error(f"音频初始化失败: {e}")
            return False

    def _find_loopback_device(self) -> int | None:
        """查找 WASAPI loopback 设备"""
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            wasapi_hostapis = [
                h for h in sd.query_hostapis()
                if "WASAPI" in h.get("name", "")
            ]

            for hostapi in wasapi_hostapis:
                for dev_idx in range(
                    hostapi.get("default_input_device", 0),
                    min(
                        hostapi.get("default_input_device", 0)
                        + hostapi.get("device_count", 0),
                        len(devices)
                    )
                ):
                    try:
                        dev = devices[dev_idx]
                        if dev.get("max_input_channels", 0) > 0:
                            # 尝试用 loopback 模式打开
                            sd.check_input_settings(
                                device=dev_idx,
                                channels=2,
                                samplerate=48000,
                                extra_settings=None,
                            )
                            logger.info(f"找到loopback设备: {dev['name']}")
                            return dev_idx
                    except Exception:
                        continue

            # 备选：查找包含 "loopback" 关键词的设备
            for i, dev in enumerate(devices):
                name = dev.get("name", "").lower()
                if "loopback" in name and dev.get("max_input_channels", 0) > 0:
                    return i

            return None

        except Exception as e:
            logger.error(f"查找loopback设备失败: {e}")
            return None

    def _init_stt_engine(self) -> bool:
        """初始化语音识别引擎"""
        if self._stt_engine == "google":
            try:
                import speech_recognition as sr
                self._recognizer = sr.Recognizer()
                self._recognizer.energy_threshold = 300
                self._recognizer.dynamic_energy_threshold = True
                logger.info("Google STT引擎就绪")
                return True
            except ImportError:
                logger.warning("SpeechRecognition库未安装")
                return False

        elif self._stt_engine == "whisper":
            try:
                import whisper
                self._whisper_model = whisper.load_model("base")
                logger.info("Whisper STT引擎就绪 (base模型)")
                return True
            except ImportError:
                logger.warning("whisper库未安装")
                return False

        elif self._stt_engine == "vosk":
            try:
                import vosk
                self._vosk_model = vosk.Model(lang="en-us")
                logger.info("Vosk STT引擎就绪")
                return True
            except ImportError:
                logger.warning("vosk库未安装")
                return False

        return False

    def start_capture(self):
        """开始音频捕获"""
        if not self._initialized:
            logger.warning("音频捕获未初始化")
            return

        try:
            import sounddevice as sd

            chunk_samples = int(self._sample_rate * self._chunk_duration_s)
            self._stream = sd.InputStream(
                device=self._device_id,
                channels=2,
                samplerate=self._sample_rate,
                callback=self._audio_callback,
                blocksize=chunk_samples,
                latency="low",
            )
            self._stream.start()
            logger.info("音频流已启动")

        except Exception as e:
            logger.error(f"启动音频流失败: {e}")

    def _audio_callback(self, indata, frames, time_info, status):
        """
        音频流回调（在音频线程中执行）。

        进行能量检测，缓冲语音段用于STT。
        """
        if status:
            logger.debug(f"音频状态: {status}")

        # 计算能量（RMS）
        if indata.ndim == 2:
            mono = np.mean(indata, axis=1)
        else:
            mono = indata.flatten()

        energy = np.sqrt(np.mean(mono ** 2))

        with self._buffer_lock:
            if energy > self._vad_threshold:
                # 检测到语音
                if not self._is_speech:
                    self._is_speech = True
                    self._buffer = []
                self._buffer.append(indata.copy())
                self._silence_start = None
            else:
                # 静音
                if self._is_speech:
                    if self._silence_start is None:
                        self._silence_start = time_info.currentTime
                    else:
                        silence_dur = time_info.currentTime - self._silence_start
                        if silence_dur > self._silence_duration_s:
                            # 语音段结束，送去STT
                            self._is_speech = False
                            if self._buffer:
                                speech = np.concatenate(self._buffer)
                                self._speech_segments.append(speech)
                            self._buffer = []

    def get_result(self, timeout: float = 0.5) -> str | None:
        """
        获取识别结果（非阻塞）。

        参数：
            timeout: 队列等待超时时间（秒）

        返回：
            识别的文本，没有则返回 None
        """
        # 处理待识别的语音段（pop 也要加锁：
        # append 发生在音频回调线程，两个线程竞争同一个列表）
        while True:
            with self._buffer_lock:
                if not self._speech_segments:
                    break
                speech = self._speech_segments.pop(0)
            text = self._transcribe(speech)
            if text:
                return text

        # 检查识别结果队列
        try:
            return self._result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _transcribe(self, audio_data: np.ndarray) -> str | None:
        """
        对一段语音进行识别（STT）。

        参数：
            audio_data: numpy数组，音频数据

        返回：
            识别的文本
        """
        try:
            if self._stt_engine == "google":
                return self._transcribe_google(audio_data)
            elif self._stt_engine == "whisper":
                return self._transcribe_whisper(audio_data)
            elif self._stt_engine == "vosk":
                return self._transcribe_vosk(audio_data)
        except Exception as e:
            logger.error(f"STT失败: {e}")

        return None

    def _transcribe_google(self, audio_data: np.ndarray) -> str | None:
        """使用Google Speech Recognition"""
        import speech_recognition as sr

        # 确保是16位整数格式
        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32767).astype(np.int16)

        audio_bytes = audio_data.tobytes()
        audio = sr.AudioData(
            audio_bytes,
            self._sample_rate,
            2  # 16-bit 采样宽度
        )

        try:
            text = self._recognizer.recognize_google(audio, language="en-US")
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            logger.warning(f"Google STT请求错误: {e}")
            return None

    def _transcribe_whisper(self, audio_data: np.ndarray) -> str | None:
        """使用Whisper本地模型"""
        if not self._whisper_model:
            return None

        # Whisper期望float32
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        # 转单声道
        if audio_data.ndim == 2:
            audio_data = np.mean(audio_data, axis=1)

        result = self._whisper_model.transcribe(audio_data, language="en")
        return result.get("text", "").strip() or None

    def _transcribe_vosk(self, audio_data: np.ndarray) -> str | None:
        """使用Vosk本地模型"""
        if not self._vosk_model:
            return None
        import vosk
        import json

        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32767).astype(np.int16)

        rec = vosk.KaldiRecognizer(self._vosk_model, self._sample_rate)
        audio_bytes = audio_data.tobytes()
        rec.AcceptWaveform(audio_bytes)

        result = json.loads(rec.FinalResult())
        text = result.get("text", "").strip()
        return text if text else None

    def stop_capture(self):
        """停止音频捕获"""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.info("音频流已停止")

    def shutdown(self):
        """释放所有资源"""
        self.stop_capture()
        self._recognizer = None
        self._whisper_model = None
        self._vosk_model = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized
