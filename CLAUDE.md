# CLAUDE.md

This file provides guidance to Claude Code when operating in the `/Volumes/ext/env/media` directory.

## 📂 Directory Structure

This directory acts as a **Media Library** for downloaded content (Bilibili/YouTube), managing source mapping, metadata, and file organization.

```
/Volumes/ext/env/media/
├── audio/          # Converted audio files (m4a/aac) ready for Apple Music
├── downloads/      # Raw video downloads (if kept)
├── metadata/       # Raw JSON metadata from yt-dlp
├── scripts/        # Management scripts
│   └── manager.py  # Main logic script
├── library.json    # Central registry mapping URLs to local files
└── CLAUDE.md       # This file
```

## 🤖 Agent Responsibilities

When asked to "download", "save", or "add" a video in this context, you MUST:

1.  **Use the Manager Script**: Prefer using `python3 scripts/manager.py download <url>` over raw `yt-dlp` commands. This ensures `library.json` is updated.
2.  **Maintain `library.json`**: This file is the source of truth. It maps `source_url` -> `local_path` + `metadata`.
3.  **Ensure Metadata**:
    *   Always embed thumbnails (`--embed-thumbnail`).
    *   Always add metadata (`--add-metadata`).
    *   Ensure Artist (Uploader) and Title are correct.
4.  **Format for Apple Music**: Default output should be `.m4a` (AAC) which is native to Apple ecosystem.

## 🛠 Common Commands

### Download & Register
```bash
cd /Volumes/ext/env/media
python3 scripts/manager.py download "https://www.bilibili.com/video/BVxxx"
```

### List Library
```bash
python3 scripts/manager.py list
```

### Manual Metadata Editing (if script fails)
If you need to manually fix tags using `ffmpeg`:
```bash
ffmpeg -i input.m4a -metadata title="New Title" -metadata artist="Artist Name" -c copy output.m4a
```

## 📊 Library Schema (`library.json`)

```json
{
  "items": [
    {
      "id": "BV1xx411c7x",
      "title": "Video Title",
      "uploader": "Uploader Name",
      "source_url": "https://www.bilibili.com/video/BV...",
      "downloaded_at": "2025-02-01T12:00:00",
      "files": {
        "audio": "Video Title [BV1xx].m4a",
        "metadata": "BV1xx.json"
      }
    }
  ]
}
```
