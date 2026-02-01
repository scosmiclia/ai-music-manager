# AI 音乐管理器

一个用于下载和管理 AI 翻唱音乐的命令行工具。支持从 Bilibili/YouTube 下载音频，自动整理元信息，并从网易云音乐获取歌词。

## 功能

- **下载音频**：从视频网站提取音频，转换为 m4a 格式（适配 Apple Music）
- **批量处理**：支持播放列表/合集批量下载
- **元信息整理**：自动解析标题，提取歌名、原唱、风格等信息
- **歌词获取**：从网易云音乐 API 自动匹配并嵌入歌词
- **库管理**：维护本地音乐库索引

## 依赖

```bash
# 必需
pip install yt-dlp

# 元信息编辑（fix 命令需要）
pip install mutagen
```

## 使用方法

```bash
# 下载单个视频
python scripts/manager.py download "https://www.bilibili.com/video/BVxxx"

# 批量处理 tasks.txt 中的链接
python scripts/manager.py process

# 查看库中所有内容
python scripts/manager.py list

# 整理元信息 + 获取歌词
python scripts/manager.py fix
```

## 目录结构

```
./
├── audio/          # 转换后的音频文件 (m4a)
├── metadata/       # 原始元数据 (JSON)
├── scripts/
│   └── manager.py  # 主脚本
├── library.json    # 本地库索引
└── tasks.txt       # 待下载链接列表
```

## 元信息整理

`fix` 命令会自动解析各种常见的 AI 翻唱标题格式：

| 原标题 | 整理后 |
|--------|--------|
| `【SUNO V5】陶喆-流沙-黑人福音R&B版` | `AI音乐 - 流沙 - 黑人福音R&B版` |
| `[SUNO V5] 黑人大妈热唱《情歌》` | `AI音乐 - 情歌 - 灵魂福音版` |
| `心太软但是R&B` | `AI音乐 - 心太软 - R&B版` |

## License

MIT
