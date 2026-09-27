"""
翻译API设置窗口

让用户配置：
- 翻译平台（LLM 中转站 / DeepL / Google 免费）
- LLM 模型名与代理地址
- 翻译目标语言、OCR 识别语言
- 查看/打开翻译记录文件夹
"""

import os
import subprocess

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QComboBox, QLabel, QLineEdit, QPushButton, QDialogButtonBox,
)

from config.settings import AppSettings


class SettingsDialog(QDialog):
    """
    翻译API设置弹窗（普通窗口，带标题栏，不复用透明悬浮样式）。

    保存后发出 settings_changed 信号，由主控制器重建翻译器。
    """

    settings_changed = pyqtSignal()

    # 平台标识（与 config.settings 的 translation_backend 对应）
    BACKEND_LLM = "llm"
    BACKEND_DEEPL = "deepl"
    BACKEND_GOOGLE = "google"

    # OCR 语言选项（代码与 Windows OCR 语言标签对应）
    OCR_LANGS = [
        ("英语 (English)", "en"),
        ("简体中文 (中文)", "zh"),
        ("日本語 (Japanese)", "ja"),
        ("한국어 (Korean)", "ko"),
        ("Français (French)", "fr"),
        ("Deutsch (German)", "de"),
        ("Español (Spanish)", "es"),
    ]

    def __init__(self, settings: AppSettings, history_dir: str, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._history_dir = history_dir

        self.setWindowTitle("翻译设置")
        self.setMinimumWidth(460)
        self._init_ui()

    def _init_ui(self):
        """构建设置窗口布局"""
        layout = QVBoxLayout(self)

        # ---- 翻译平台 ----
        backend_group = QGroupBox("翻译平台")
        backend_layout = QVBoxLayout(backend_group)

        current_backend = self._settings.get("translation_backend", "llm")

        self._radio_llm = QRadioButton("LLM 翻译（推荐，走本机代理，国内可用）")
        self._radio_llm.setChecked(current_backend == self.BACKEND_LLM)
        backend_layout.addWidget(self._radio_llm)

        llm_row = QHBoxLayout()
        llm_row.addWidget(QLabel("模型名"))
        self._model_edit = QLineEdit(
            self._settings.get("llm_model", "deepseek-v4-pro")
        )
        llm_row.addWidget(self._model_edit, 1)
        backend_layout.addLayout(llm_row)

        proxy_row = QHBoxLayout()
        proxy_row.addWidget(QLabel("代理地址"))
        self._proxy_edit = QLineEdit(
            self._settings.get("llm_base_url", "http://127.0.0.1:8642")
        )
        proxy_row.addWidget(self._proxy_edit, 1)
        backend_layout.addLayout(proxy_row)

        llm_note = QLabel(
            "默认连本机 cnsai 回退代理（cnsai 中转站优先，DeepSeek 兜底），"
            "密钥保存在代理配置里，应用本身不持有密钥。"
        )
        llm_note.setStyleSheet("color: gray; font-size: 11px;")
        llm_note.setWordWrap(True)
        backend_layout.addWidget(llm_note)

        self._radio_deepl = QRadioButton("DeepL（需 API Key，翻译质量高）")
        self._radio_deepl.setChecked(current_backend == self.BACKEND_DEEPL)
        backend_layout.addWidget(self._radio_deepl)

        deepl_row = QHBoxLayout()
        deepl_row.addWidget(QLabel("API Key"))
        self._deepl_key_edit = QLineEdit(
            self._settings.get("deepl_api_key", "")
        )
        self._deepl_key_edit.setEchoMode(QLineEdit.Password)
        self._deepl_key_edit.setPlaceholderText("DeepL Free/Pro API Key")
        deepl_row.addWidget(self._deepl_key_edit, 1)
        backend_layout.addLayout(deepl_row)

        self._radio_google = QRadioButton(
            "Google 免费自动（MyMemory + Google，国内网络不可用）"
        )
        self._radio_google.setChecked(current_backend == self.BACKEND_GOOGLE)
        backend_layout.addWidget(self._radio_google)

        google_note = QLabel("无需注册、无需密钥，但国内网络下基本连不上。")
        google_note.setStyleSheet("color: gray; font-size: 11px;")
        backend_layout.addWidget(google_note)

        layout.addWidget(backend_group)

        # ---- 目标语言 ----
        lang_group = QGroupBox("翻译目标语言")
        lang_layout = QVBoxLayout(lang_group)
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("简体中文", "zh-CN")
        self._lang_combo.addItem("繁體中文", "zh-TW")
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("日本語", "ja")
        current = self._settings.get("target_language", "zh-CN")
        idx = self._lang_combo.findData(current)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        lang_layout.addWidget(self._lang_combo)
        layout.addWidget(lang_group)

        # ---- OCR 识别语言 ----
        ocr_group = QGroupBox("OCR 字幕识别语言")
        ocr_layout = QVBoxLayout(ocr_group)
        self._ocr_lang_combo = QComboBox()
        for label, code in self.OCR_LANGS:
            self._ocr_lang_combo.addItem(label, code)
        current_ocr = self._settings.get("ocr_languages", "en")
        idx = self._ocr_lang_combo.findData(current_ocr)
        if idx >= 0:
            self._ocr_lang_combo.setCurrentIndex(idx)
        ocr_layout.addWidget(self._ocr_lang_combo)
        ocr_note = QLabel("看什么语言的视频就选什么（默认英语）。")
        ocr_note.setStyleSheet("color: gray; font-size: 11px;")
        ocr_layout.addWidget(ocr_note)
        layout.addWidget(ocr_group)

        # ---- 翻译记录 ----
        record_group = QGroupBox("翻译记录")
        record_layout = QVBoxLayout(record_group)
        self._record_label = QLabel(os.path.abspath(self._history_dir))
        self._record_label.setWordWrap(True)
        self._record_label.setStyleSheet("color: gray;")
        record_layout.addWidget(self._record_label)
        open_btn = QPushButton("打开记录文件夹")
        open_btn.clicked.connect(self._open_history_dir)
        record_row = QHBoxLayout()
        record_row.addWidget(open_btn)
        record_row.addStretch()
        record_layout.addLayout(record_row)
        layout.addWidget(record_group)

        # ---- 确定 / 取消 ----
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ==================== 事件处理 ====================

    def _on_accept(self):
        """保存设置并关闭窗口"""
        if self._radio_llm.isChecked():
            backend = self.BACKEND_LLM
        elif self._radio_deepl.isChecked():
            backend = self.BACKEND_DEEPL
        else:
            backend = self.BACKEND_GOOGLE

        self._settings.set("translation_backend", backend)
        self._settings.set("llm_model", self._model_edit.text().strip())
        self._settings.set("llm_base_url", self._proxy_edit.text().strip())
        self._settings.set("deepl_api_key", self._deepl_key_edit.text().strip())
        self._settings.set("target_language", self._lang_combo.currentData())
        self._settings.set("ocr_languages", self._ocr_lang_combo.currentData())
        self.settings_changed.emit()
        self.accept()

    def _open_history_dir(self):
        """用系统资源管理器打开翻译记录文件夹"""
        path = os.path.abspath(self._history_dir)
        os.makedirs(path, exist_ok=True)
        try:
            os.startfile(path)  # Windows 专用：直接打开文件夹
        except Exception:
            subprocess.Popen(["explorer", path])
