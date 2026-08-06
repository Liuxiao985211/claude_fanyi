# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 for Clude翻译App
构建命令: pyinstaller clude_fanyi.spec
"""

import sys
from pathlib import Path

# ---- 项目路径 ----
PROJECT_DIR = Path(SPECPATH).resolve()

# ---- 需要强制导入的隐藏模块 ----
# 这些包PyInstaller可能检测不到，需要手动指定
hidden_imports = [
    # Windows OCR (winrt)
    'winrt._winrt_windows_media_ocr',
    'winrt._winrt_windows_graphics_imaging',
    'winrt._winrt_windows_globalization',
    'winrt._winrt_windows_foundation',
    'winrt._winrt_windows_foundation_collections',
    'winrt._winrt_windows_storage_streams',
    'winrt.windows.media.ocr',
    'winrt.windows.graphics.imaging',
    'winrt.windows.globalization',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.storage.streams',

    # 翻译
    'deep_translator',
    'deep_translator.google',
    'deep_translator.mymemory',

    # 屏幕捕获
    'dxcam',

    # PyQt5
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.sip',

    # 音频（可选）
    'sounddevice',
    'speech_recognition',

    # 工具
    'numpy',
    'numpy.core',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'certifi',
    'asyncio',
    'ctypes',
    'queue',
    'logging',
    'json',
    'threading',
]

# ---- Qt5 平台插件 ----
# 确保在其他电脑上也能正常渲染透明窗口
import PyQt5
qt_plugin_path = Path(PyQt5.__file__).parent / 'Qt5' / 'plugins'

# ---- 分析阶段 ----
a = Analysis(
    [str(PROJECT_DIR / 'main.py')],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=[
        # 图标文件
        (str(PROJECT_DIR / 'resources' / 'app.ico'), 'resources'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大包（避免PyInstaller分析它们时崩溃）
        'torch',
        'torchvision',
        'torchaudio',
        'numba',
        'scipy',
        'scikit-learn',
        'sklearn',
        'matplotlib',
        'pandas',
        'easyocr',
        'whisper',
        'openai_whisper',
        'tensorflow',
        'keras',
        'onnx',
        'transformers',
        'tokenizers',
        'sentencepiece',
        'tiktoken',
        # 排除不需要的Qt组件以减小体积
        'PyQt5.QtBluetooth',
        'PyQt5.QtDBus',
        'PyQt5.QtDesigner',
        'PyQt5.QtHelp',
        'PyQt5.QtLocation',
        'PyQt5.QtMultimedia',
        'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtNfc',
        'PyQt5.QtNetwork',
        'PyQt5.QtOpenGL',
        'PyQt5.QtPositioning',
        'PyQt5.QtQml',
        'PyQt5.QtQuick',
        'PyQt5.QtQuick3D',
        'PyQt5.QtQuickWidgets',
        'PyQt5.QtRemoteObjects',
        'PyQt5.QtSensors',
        'PyQt5.QtSerialPort',
        'PyQt5.QtSql',
        'PyQt5.QtTest',
        'PyQt5.QtTextToSpeech',
        'PyQt5.QtWebChannel',
        'PyQt5.QtWebSockets',
        'PyQt5.QtWinExtras',
        'PyQt5.QtXml',
        'PyQt5.QtXmlPatterns',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ---- 过滤特定DLL ----
# 排除系统DLL（避免冲突）
import re
a.binaries = [b for b in a.binaries if not re.search(
    r'api-ms-win-|MSVCP|VCRUNTIME|msvcr|ucrtbase',
    b[0],
    re.IGNORECASE
)]

# ---- 构建 EXE ----
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Clude翻译App',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # 压缩以减小体积
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,     # 不显示命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_DIR / 'resources' / 'app.ico'),  # 程序图标
)
