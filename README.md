# AI 音乐管理器

一个用于下载和管理 AI 翻唱音乐的命令行工具。支持从 Bilibili/YouTube 下载音频，自动整理元信息，并从网易云音乐获取歌词。

## 功能

- **下载音频**：从视频网站提取音频，转换为 m4a 格式（适配 Apple Music）
- **批量处理**：支持播放列表/合集批量下载
- **元信息整理**：自动解析标题，提取歌名、原唱、风格等信息
- **歌词获取**：从网易云音乐 API 自动匹配并嵌入歌词
- **库管理**：维护本地音乐库索引

## 开发检查

推送到 `main`、拉取请求和手动触发会运行 GitHub Hosted CI，检查已跟踪的
Python/JSON 语法和离线 CLI 使用提示。真实下载、媒体标签和 Apple Music 导入
仍需独立验收。仓库目前没有版本化产物发布入口。

## 依赖

```bash
# 必需
pip install yt-dlp

# 元信息、原生 MP4 封面和 Apple Music 工作流（必需）
python -m pip install mutagen
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

## Bilibili 高码率与封面

Bilibili 下载会写入标题、艺人和原生 MP4 `covr` 封面；艺人字段会追加 `AI音乐`，便于用 Apple Music 智能播放列表归类。此流程需要已安装的 `bili` 命令及 `mutagen`。

对已入库的一位上传者，可将可用的高码率音频暂存到独立目录，补齐封面后再校验：

```bash
# 不覆盖 audio/；可安全重复执行
python scripts/manager.py refresh-bilibili --uploader "<uploader>" ./audio-bilibili-192k

# 为已有暂存文件写入原生 MP4 封面
python scripts/manager.py fix-bilibili-covers --uploader "<uploader>" ./audio-bilibili-192k

# 导入 Music 前验证：缺文件、低码率、缺封面或标签不符都会返回非零状态
python scripts/manager.py verify-bilibili --uploader "<uploader>" ./audio-bilibili-192k
```

`verify-bilibili` 默认拒绝码率不高于 96 kbps 的文件；可通过 `--min-bitrate <bps>` 调整阈值。

### 导入 Apple Music

1. 在 Music 设置中确认“同步资料库”已开启，并定位“自动添加到 Music”文件夹。
2. 只将 `verify-bilibili` 通过的 m4a 文件复制到该文件夹，等待 Music 完成导入与云端资料库更新。
3. 用智能播放列表规则“艺人包含 `AI音乐`”自动收纳 Bilibili 下载。

不要将 Music 资料库、自动导入文件夹、Apple ID、上传状态截图或下载音频提交到仓库。

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
