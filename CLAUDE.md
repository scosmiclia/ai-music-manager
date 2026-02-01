# CLAUDE.md

为 Claude Code 提供本项目的操作指引。

## 项目说明

这是一个 AI 翻唱音乐的下载和管理工具，用于从 Bilibili/YouTube 下载音频，整理元信息，并获取歌词。

## 目录结构

```
./
├── audio/          # 转换后的音频文件 (m4a)
├── downloads/      # 原始下载文件
├── metadata/       # 视频元数据 (JSON)
├── scripts/
│   └── manager.py  # 主脚本
├── library.json    # 本地库索引
└── tasks.txt       # 待下载链接列表
```

## 常用命令

```bash
# 下载视频音频
python scripts/manager.py download "<url>"

# 批量处理 tasks.txt
python scripts/manager.py process

# 查看库内容
python scripts/manager.py list

# 整理元信息 + 获取歌词
python scripts/manager.py fix
```

## 脱敏约束

**重要**：这是一个开源仓库，任何修改都必须遵守以下规则：

1. **禁止提交个人信息**：
   - 不要提交包含本地绝对路径的文件（如 `/Users/xxx/`、`/home/xxx/`）
   - 不要提交 `.claude/settings.local.json`（包含本地权限配置）
   - 不要提交 `library.json`（包含下载历史）

2. **禁止提交下载内容**：
   - `audio/`、`downloads/`、`metadata/` 目录已在 .gitignore 中排除
   - 不要手动添加这些目录中的文件

3. **代码保持通用**：
   - 使用相对路径或基于脚本位置的动态路径
   - 不要硬编码任何用户特定的配置

## Library Schema

```json
{
  "items": [
    {
      "id": "BVxxxxx",
      "title": "原始标题",
      "clean_title": "AI音乐 - 歌名 - 风格版",
      "song_name": "歌名",
      "original_artist": "原唱",
      "style": "风格",
      "has_lyrics": true,
      "source_url": "https://...",
      "downloaded_at": "2025-01-01T00:00:00",
      "files": {
        "audio": "xxx.m4a",
        "metadata": "xxx.json"
      }
    }
  ]
}
```
