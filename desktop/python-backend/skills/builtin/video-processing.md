---
name: video-processing
description: "视频处理 — 剪辑、转码、提取音频/帧、合并、加速、加水印"
category: office
version: "1.0"
tags: [video, ffmpeg, processing, edit, transcode]
---

# 视频处理技能

## 工具依赖
- FFmpeg（系统级工具，功能最全）
- Python: moviepy, opencv-python（可选）

## 安装
```bash
# Ubuntu/Debian
sudo apt install ffmpeg
# macOS
brew install ffmpeg
# Windows: 下载 https://ffmpeg.org/download.html

# Python 库（可选）
pip install moviepy opencv-python
```

## FFmpeg 常用命令

### 1. 格式转换
```bash
# MP4 转 AVI
ffmpeg -i input.mp4 output.avi
# 转 GIF（前10秒）
ffmpeg -i input.mp4 -t 10 -vf "fps=10,scale=320:-1" output.gif
# 转 WebM
ffmpeg -i input.mp4 -c:v libvpx -crf 10 -b:v 1M output.webm
```

### 2. 剪辑视频
```bash
# 截取片段（从00:01:30开始，截取30秒）
ffmpeg -i input.mp4 -ss 00:01:30 -t 00:00:30 -c copy output.mp4
# 截取到指定时间点
ffmpeg -i input.mp4 -ss 00:01:30 -to 00:02:00 -c copy output.mp4
```

### 3. 提取音频
```bash
# 提取为 MP3
ffmpeg -i input.mp4 -vn -acodec libmp3lame -q:a 2 output.mp3
# 提取为 WAV
ffmpeg -i input.mp4 -vn -acodec pcm_s16le output.wav
# 提取为 AAC
ffmpeg -i input.mp4 -vn -acodec copy output.aac
```

### 4. 提取视频帧
```bash
# 每秒提取一帧
ffmpeg -i input.mp4 -vf fps=1 frame_%04d.png
# 提取第10秒的帧
ffmpeg -i input.mp4 -ss 00:00:10 -frames:v 1 frame.png
# 每10秒提取一帧
ffmpeg -i input.mp4 -vf "select=not(mod(n\,300))" -vsync vfn frames/%04d.png
```

### 5. 调整分辨率
```bash
# 缩放到 720p
ffmpeg -i input.mp4 -vf scale=-1:720 output_720p.mp4
# 缩放到 1080p
ffmpeg -i input.mp4 -vf scale=-1:1080 output_1080p.mp4
# 自定义尺寸
ffmpeg -i input.mp4 -vf scale=1280:720 output.mp4
```

### 6. 调整速度
```bash
# 2倍速（视频+音频）
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=0.5*PTS[v];[0:a]atempo=2.0[a]" -map "[v]" -map "[a]" output.mp4
# 0.5倍速（慢放）
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=2.0*PTS[v];[0:a]atempo=0.5[a]" -map "[v]" -map "[a]" output.mp4
# 仅视频加速（无声）
ffmpeg -i input.mp4 -vf "setpts=0.5*PTS" output.mp4
```

### 7. 合并视频
```bash
# 方法1: concat 协议（同格式）
cat filelist.txt
# file 'part1.mp4'
# file 'part2.mp4'
# file 'part3.mp4'
ffmpeg -f concat -safe 0 -i filelist.txt -c copy merged.mp4

# 方法2: 不同格式先统一再合并
ffmpeg -i part1.mp4 -c:v libx264 -c:a aac part1_conv.mp4
ffmpeg -i part2.avi -c:v libx264 -c:a aac part2_conv.mp4
ffmpeg -f concat -safe 0 -i filelist.txt -c copy merged.mp4
```

### 8. 添加水印
```bash
# 图片水印
ffmpeg -i input.mp4 -i watermark.png -filter_complex "overlay=W-w-10:H-h-10" output.mp4
# 文字水印
ffmpeg -i input.mp4 -vf "drawtext=text='水印':fontsize=24:fontcolor=white:x=10:y=10" output.mp4
```

### 9. 裁剪画面
```bash
# 裁剪中心区域 (宽:高)
ffmpeg -i input.mp4 -vf "crop=640:480" output.mp4
# 裁剪指定区域 (宽:高:x:y)
ffmpeg -i input.mp4 -vf "crop=640:480:100:50" output.mp4
```

### 10. 压缩视频
```bash
# 降低码率压缩
ffmpeg -i input.mp4 -c:v libx264 -crf 28 -preset fast output.mp4
# CRF 值: 0=无损, 23=默认, 28=较小, 51=最差
```

## Python MoviePy 用法

### 基本剪辑
```python
from moviepy.editor import VideoFileClip

clip = VideoFileClip('input.mp4')
# 截取片段
subclip = clip.subclip(60, 120)  # 1-2分钟
# 缩放
resized = clip.resize(width=640)
# 导出
subclip.write_videofile('output.mp4')
# 导出音频
clip.audio.write_audiofile('audio.mp3')
```

### 添加字幕
```python
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

clip = VideoFileClip('input.mp4')
txt = TextClip('字幕文字', fontsize=24, color='white', font='SimHei')
txt = txt.set_position(('center', 'bottom')).set_duration(5)
final = CompositeVideoClip([clip, txt])
final.write_videofile('output.mp4')
```

## 注意事项
- `-c copy` 最快（不重新编码），但格式必须兼容
- `-c:v libx264` 通用性最好
- 处理大文件用 `-preset fast` 加快速度
- `-crf` 值越小质量越高，文件越大
