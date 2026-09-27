# Claude翻译App

透明悬浮窗实时翻译工具：看电影/视频时，在屏幕底部实时显示中文译文。

背景完全透明、文字带黑边描边、窗口始终置顶，不打断观影。

## 功能

- **两种捕获方式**（可单独或混合使用）：
  - OCR 字幕：定时截取屏幕底部区域，Windows 内置 OCR 识别字幕文字（零额外依赖）
  - 音频识别：捕获系统正在播放的声音（WASAPI loopback），语音识别后翻译
- **三种翻译后端**（设置里切换）：
  - **LLM 翻译（默认，推荐）**：走本机 cnsai 回退代理（cnsai 中转站优先、DeepSeek 官方兜底），国内可用，质量高。密钥保存在代理配置里，应用本身不持有密钥
  - DeepL：需自备 API Key，翻译质量最高（需能访问 DeepL）
  - Google 免费自动（MyMemory + Google）：无需密钥，但国内网络基本不可用
- 透明悬浮窗：悬停渐显底条和控制按钮，可拖动、可边缘缩放
- Ctrl+滚轮调节字号；右键托盘图标控制开始/暂停/停止/模式切换
- 翻译记录按天自动写入 `翻译记录/` 文件夹
- 去重：同一字幕不会反复翻译（精确匹配 + 相似度模糊匹配 + 30 秒过期）

## 安装

要求：Windows 10/11，Python 3.10+（3.13/3.14 亦可）

```bash
pip install -r requirements.txt
```

可选依赖（按需安装）：

```bash
# 音频识别模式（混合模式需要）
pip install sounddevice SpeechRecognition

# DeepL 翻译后端（需 API Key）
pip install deepl
```

## 运行

```bash
python main.py
```

打开后处于「待开始」状态 → 点击窗口上 ▶ 按钮或托盘菜单开始翻译。

### 首次使用前

1. 确保本机 cnsai 回退代理在运行（`127.0.0.1:8642`，默认翻译后端依赖它）
2. 右键托盘图标 → ⚙ 翻译API设置 → 确认翻译平台为「LLM 翻译」，模型名按你的代理配置填（默认 `deepseek-v4-pro`）
3. 确认 OCR 字幕识别语言与视频语言一致（默认英语）

### 交互

| 操作 | 效果 |
|------|------|
| 拖动窗口任意位置 | 移动悬浮窗 |
| 拖动窗口边缘/角落 | 调整大小 |
| Ctrl+滚轮 | 调节字号（8-48） |
| 悬停在窗口上 | 显示控制条（▶ 开始/暂停 + ⚙ 设置） |
| 双击托盘图标 | 显示/隐藏窗口 |
| 右键托盘图标 | 开始/暂停/停止、翻译模式、设置、退出 |

## 打包为 exe

```bash
pip install pyinstaller
pyinstaller clude_fanyi.spec        # 正式版（无控制台）
pyinstaller clude_fanyi_console.spec  # 带控制台的调试版
```

输出在 `dist/` 目录。三个 spec 文件：

- `clude_fanyi.spec` — 正式版，无控制台窗口
- `clude_fanyi_console.spec` — 调试版，带控制台查看日志
- `clude_fanyi_debug.spec` — 调试配置

打包后 exe 的日志在 exe 同目录 `app.log`（滚动保留 2 个备份），排查问题先看它。

## 配置

配置保存在 Windows 注册表（`QSettings`），设置界面可改的项：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| translation_backend | `llm` | 翻译平台：`llm` / `deepl` / `google` |
| llm_model | `deepseek-v4-pro` | LLM 模型名（按代理支持的模型填） |
| llm_base_url | `http://127.0.0.1:8642` | 本机 cnsai 回退代理地址 |
| target_language | `zh-CN` | 译文语言 |
| ocr_languages | `en` | OCR 字幕识别语言 |
| translation_mode | `hybrid` | `ocr` / `audio` / `hybrid` |
| ocr_region_ratio | `0.15` | 截屏区域（屏幕底部比例） |
| history_dir | 应用目录/翻译记录 | 翻译记录文件夹 |

## 常见问题

**点开始提示「翻译服务不可用」**：LLM 代理没在运行，或模型名不对。检查 `127.0.0.1:8642` 是否可访问，查看 `app.log`。

**OCR 识别不到字幕**：确认视频语言与 OCR 语言一致；调整 `ocr_region_ratio`（字幕位置不在屏幕底部 15% 时）；窗口显示缩放比例会影响识别效果。

**音频模式没反应**：音频识别依赖 sounddevice（WASAPI loopback），先确认 `pip install sounddevice SpeechRecognition` 已装；Google STT 国内不可用，音频模式目前实用性有限。

**译文延迟越来越大**：翻译速度跟不上时，程序会自动丢弃过期文本、只翻最新一句（队列上限 30）。

## 开发

架构：`main.py`（主控制器，状态机 idle/running/paused）→ `capture/`（OCR + 音频捕获）→ `workers/`（三个工作线程）→ `translate/`（可插拔翻译后端）→ `ui/`（透明悬浮窗 + 托盘 + 设置）。

```bash
python main.py   # 直接运行
```

工作进程与设计文档见 `工作进程.md` 与 `docs/designs/`。
