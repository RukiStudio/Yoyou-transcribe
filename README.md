# Ruki's Music Transcriber

面向编曲学习的 AI 辅助快速扒谱桌面软件。它把音频分析结果呈现在可编辑的钢琴卷帘中，学生可以边听边改，最后导出 MIDI 带入任意 DAW。

> 当前版本为可运行的 MVP：提供本地音频特征识别、主旋律/鼓点基线提取、MIDI 导出与实时预览。AI 分轨模型预留为下一阶段的可插拔能力；它不是“零误差自动出总谱”的承诺，结果应按听感复核。

## 项目计划与实现路线

### 第一阶段：可编辑的转录闭环（本仓库已实现）

1. **音频信息识别**：使用 `librosa` 计算 BPM、CQT 色度特征与主调性估计。
2. **基线转录**：以 `piptrack` 取得主导有调音高、以 onset 检测得到节奏事件；将结果量化到十六分音符网格。
3. **学生友好编辑器**：`PySide6` 提供简洁欢迎页、声部面板、BPM/调性/和弦信息、钢琴卷帘；双击可添加、选中后按 `Delete` 可删除音符。
4. **输出与校对**：使用 `mido` 导出标准 MIDI；内置简易合成器把当前钢琴卷帘生成 WAV，修改后可立即试听。

### 第二阶段：专业 AI 管线（建议按接口添加）

1. 建立 `app/separation/`，使用 **Demucs** 或 **MDX-Net** 把混音分为 vocals、drums、bass、other；模型文件首次使用时显式下载并提示磁盘占用。
2. 将每个 stem 输入对应转录器：主旋律/人声使用 **Basic Pitch、MT3 或 CREPE**，钢琴与吉他使用多音高转录模型，鼓使用 onset + timbre embedding 聚类到 kick/snare/hihat 等类别。
3. 在 `Track` 上保存每个事件的模型置信度、源分轨路径与可回滚的编辑操作；用置信度热图引导人工检查，而非替代人工判断。
4. 和弦识别可接入 Chordino/Transformer 模型，按小节显示候选和弦，并允许用户锁定调性与拍号后重新量化。
5. 加入项目保存（JSON + MIDI）、波形/频谱视图、快捷键、模型管理页与批量处理队列。

### 关键架构

```text
音频文件
  └─ Audio Analysis Worker（线程，避免界面卡顿）
       ├─ BPM / 调性 / 节拍 / 和弦提示
       ├─ 基线旋律与鼓点提取
       └─ [未来] 可选 AI 分轨与专用转录模型
                ↓
          SongProject / Track / NoteEvent（与 UI 解耦的数据模型）
                ↓
      钢琴卷帘编辑 ←→ WAV 实时试听 / MIDI 标准导出
```

## 快速开始

### 环境

- Windows 10/11
- Python 3.10–3.13（当前环境已检测到 3.13）
- 建议使用虚拟环境，避免污染全局 Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

若 PowerShell 阻止激活脚本，可直接使用 `.venv\Scripts\python.exe -m pip install -r requirements.txt` 与 `.venv\Scripts\python.exe main.py`。

## 使用方式

1. 点击 **导入音频**，选择 WAV、MP3、FLAC、M4A 或 OGG 文件。
2. 等待分析完成，在右侧查看 BPM、调性、拍号和相似旋律推荐。
3. 在钢琴卷帘中点击音符查看候选；双击空白网格添加音符；按 `Delete` 删除误识别音符。
4. 点击 **试听** 听到当前编辑状态；点击 **导出 MIDI** 保存到 DAW。
5. 未准备音频时，选择 **示例工程** 熟悉流程。

## 目录

```text
main.py                  应用入口
app/analysis.py          音频特征与基线转录（可替换为 AI 模型适配器）
app/models.py            项目、声部、音符数据模型
app/midi_service.py      MIDI 导出和本地试听合成
app/ui/                  PySide6 主界面、样式、钢琴卷帘
build.py / build.bat     一键 Windows 打包
```

## 打包为可执行文件

双击 `build.bat`，或在已安装依赖的终端运行：

```powershell
python build.py
```

完成后从 `dist/RukiMusicTranscriber/RukiMusicTranscriber.exe` 启动。首次打包通常需要数分钟；若导入 MP3 失败，建议先转换为 WAV，或安装系统支持的 FFmpeg。

## 已知范围

- 混音音乐的自动转录天然有误差；当前基线特别适合先抓取节奏、速度、主旋律走向，再人工修正。
- 当前“相似旋律替换”是基于音高邻近度的透明规则，而不是黑盒生成；第二阶段可改为使用 embedding 检索。
- 内置试听是无外部设备依赖的简易合成音色，旨在校对音高和节奏，不等同于专业音源。
