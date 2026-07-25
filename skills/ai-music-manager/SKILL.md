---
name: ai-music-manager
description: Download and manage AI music with this repository, including Bilibili high-quality staging, native MP4 artwork, metadata repair, validation, and local Apple Music import preparation. Use when a user asks to download AI music, repair tags or cover art, replace low-bitrate copies, validate media before importing, or organize tracks through an AI-music smart playlist.
---

# AI Music Manager

Operate from the repository root. Treat the media library and Music application as local user data; preserve them and keep all public-repository changes generic.

## Workflow

1. Inspect `git status`, the requested source URLs, and the ignored media directories. Never add media, metadata, task queues, logs, or the local library index to a public commit.
2. Install `mutagen` in an isolated Python environment before Bilibili artwork work. Native MP4 `covr` artwork is required for reliable Apple Music display; an attached-picture fallback is insufficient for this workflow.
3. Download a URL with `python scripts/manager.py download "<url>"`, or stage an existing uploader's library entries without overwriting the normal audio directory:

   ```bash
   python scripts/manager.py refresh-bilibili --uploader "<uploader>" ./audio-bilibili-192k
   ```

4. Repair prior staged media only when needed:

   ```bash
   python scripts/manager.py fix-bilibili-covers --uploader "<uploader>" ./audio-bilibili-192k
   ```

5. Validate every staged track before import. Stop and repair failures; do not silently upload low-quality or untagged files.

   ```bash
   python scripts/manager.py verify-bilibili --uploader "<uploader>" ./audio-bilibili-192k
   ```

   The command returns nonzero for missing files, audio bitrate at or below 96 kbps, missing native artwork, or title/artist mismatch.

6. For Apple Music, copy only the verified files to the user's configured automatic-import folder. Confirm that Music has displayed a real cover while playing a track, then let cloud-library status settle before promising availability on another device.
7. Keep the artist marker in the form `<uploader> · AI音乐` so an Apple Music smart playlist with “Artist contains `AI音乐`” includes the tracks.

## Public-repository boundaries

- Use only placeholders in tracked docs, examples, logs, commits, and skill text: `<url>`, `<uploader>`, `<source-dir>`, `<music-import-dir>`.
- Do not record personal names, account identifiers, BV/video IDs, media titles, playlist URLs, absolute paths, Apple Music screenshots, cloud states, or downloaded media.
- Do not add ignored local artifacts such as `audio/`, `downloads/`, `metadata/`, `library.json`, `tasks.txt`, or logs.
- Before committing, run `git diff --check` and inspect the staged file list for personal data or large binary files.
