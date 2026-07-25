import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime

try:
    from mutagen.mp4 import MP4, MP4Cover
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# Use absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
METADATA_DIR = os.path.join(BASE_DIR, "metadata")
TASKS_FILE = os.path.join(BASE_DIR, "tasks.txt")
LOG_FILE = os.path.join(BASE_DIR, "download.log")

# Ensure directories exist
for d in [AUDIO_DIR, METADATA_DIR, DOWNLOADS_DIR]:
    os.makedirs(d, exist_ok=True)

# Environment without proxy for Bilibili (direct connection is faster/more stable)
NO_PROXY_ENV = {k: v for k, v in os.environ.items()
                if k.lower() not in ('http_proxy', 'https_proxy', 'all_proxy')}


def parse_title(raw_title):
    """
    Parse AI cover song title to extract structured info.

    Examples:
        "【SUNO V5】陶喆-流沙-黑人福音R&B版" -> {song_name: "流沙", original_artist: "陶喆", style: "黑人福音R&B"}
        "[SUNO V5] 黑人大妈热唱灵魂福音版《情歌》" -> {song_name: "情歌", style: "灵魂福音"}
    """
    title = raw_title.strip()

    # Remove common prefixes like 【SUNO V5】, [SUNO V5], [SUNO AI], etc.
    title = re.sub(r'^[\[【][^\]】]*[\]】]\s*', '', title)

    # Try pattern: Artist-Song-Style (e.g., "陶喆-流沙-黑人福音R&B版")
    match = re.match(r'^(.+?)[—\-－](.+?)[—\-－](.+)$', title)
    if match:
        artist, song, style = match.groups()
        # Clean up style (remove trailing 版/版本)
        style = re.sub(r'版本?$', '', style.strip())
        return {
            'song_name': song.strip(),
            'original_artist': artist.strip(),
            'style': style.strip(),
            'display_title': f"AI音乐 - {song.strip()} - {style.strip()}版"
        }

    # Try pattern with《》brackets (e.g., "黑人大妈热唱灵魂福音版《情歌》")
    match = re.search(r'《([^》]+)》', title)
    if match:
        song_name = match.group(1)
        # Try to extract style from before the song name
        before_song = title[:match.start()]
        # Common style patterns
        style_match = re.search(r'([\u4e00-\u9fa5A-Za-z&]+(?:版|风格|唱腔|翻唱))', before_song)
        if style_match:
            style = style_match.group(1)
            style = re.sub(r'(版|风格|唱腔|翻唱)$', '', style)
        else:
            # Try to find style keywords
            style_keywords = ['福音', '灵魂', 'R&B', 'Soul', '摇滚', '金属', '电音', 'City pop',
                            'Synthwave', '弗拉明戈', '雷鬼', 'Salsa', '朋克', '嘻哈', '说唱']
            style = ''
            for kw in style_keywords:
                if kw.lower() in before_song.lower():
                    style = kw
                    break
            if not style:
                style = '翻唱'

        # Try to extract artist from patterns like "翻唱陈奕迅《xxx》" or "热唱张杰《xxx》"
        artist_match = re.search(r'(?:翻唱|热唱|演绎|版)([^\s《]+?)《', before_song)
        artist = artist_match.group(1) if artist_match else ''

        return {
            'song_name': song_name,
            'original_artist': artist,
            'style': style,
            'display_title': f"AI音乐 - {song_name} - {style}版"
        }

    # Try simple pattern: "《Song》Style" (e.g., "《雨蝶》微醺版R&B")
    match = re.match(r'^《([^》]+)》(.+)$', title)
    if match:
        song_name, style = match.groups()
        style = re.sub(r'版本?$', '', style.strip())
        return {
            'song_name': song_name,
            'original_artist': '',
            'style': style,
            'display_title': f"AI音乐 - {song_name} - {style}版"
        }

    # Try pattern: "Song但是Style" (e.g., "心太软但是R&B")
    match = re.match(r'^(.+?)但是(.+)$', title)
    if match:
        song_name, style = match.groups()
        return {
            'song_name': song_name.strip(),
            'original_artist': '',
            'style': style.strip(),
            'display_title': f"AI音乐 - {song_name.strip()} - {style.strip()}版"
        }

    # Fallback: use the whole title as song name
    return {
        'song_name': title,
        'original_artist': '',
        'style': '翻唱',
        'display_title': f"AI音乐 - {title}"
    }


def fetch_lyrics(song_name, artist=""):
    """
    Fetch lyrics from NetEase Music API.
    Returns LRC format lyrics or empty string if not found.
    """
    try:
        # Search for the song
        search_query = f"{song_name} {artist}".strip()
        search_url = f"https://music.163.com/api/search/get?s={urllib.parse.quote(search_query)}&type=1&limit=5"

        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://music.163.com/'
        })

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        if data.get('code') != 200 or not data.get('result', {}).get('songs'):
            return ''

        # Get the first matching song's ID
        song_id = data['result']['songs'][0]['id']

        # Fetch lyrics
        lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1"
        req = urllib.request.Request(lyric_url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://music.163.com/'
        })

        with urllib.request.urlopen(req, timeout=10) as resp:
            lyric_data = json.loads(resp.read().decode('utf-8'))

        if lyric_data.get('code') != 200:
            return ''

        # Get the lyrics (lrc format)
        lrc = lyric_data.get('lrc', {}).get('lyric', '')
        return lrc

    except Exception as e:
        print(f"  ⚠ Failed to fetch lyrics for '{song_name}': {e}")
        return ''


def fetch_bilibili_cover(video_id, cover_url):
    """Download a Bilibili video's cover once and retain it beside its metadata."""
    if not cover_url:
        return None

    # Bilibili's API normally serves JPEG artwork.  Keep a stable extension so
    # Music and FFmpeg can infer the attached-picture format reliably.
    cover_path = os.path.join(METADATA_DIR, f"{video_id}.cover.jpg")
    if os.path.exists(cover_path) and os.path.getsize(cover_path) > 0:
        return cover_path

    temporary_path = f"{cover_path}.part"
    try:
        request = urllib.request.Request(cover_url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com/',
        })
        with urllib.request.urlopen(request, timeout=30) as response, open(temporary_path, 'wb') as output:
            shutil.copyfileobj(response, output)
        if os.path.getsize(temporary_path) == 0:
            raise RuntimeError("Bilibili returned an empty cover image")
        os.replace(temporary_path, cover_path)
        return cover_path
    except Exception as e:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        print(f"  ⚠ Failed to fetch Bilibili cover for {video_id}: {e}")
        return None


def cover_path_for_item(item):
    """Return an item's cached Bilibili cover, downloading it when necessary."""
    metadata_name = item.get("files", {}).get("metadata")
    if not metadata_name:
        return None
    metadata_path = os.path.join(METADATA_DIR, metadata_name)
    try:
        with open(metadata_path, encoding="utf-8") as f:
            cover_url = json.load(f).get("data", {}).get("pic")
    except (OSError, json.JSONDecodeError):
        return None
    return fetch_bilibili_cover(item["id"], cover_url)


def update_metadata(file_path, title, artist, lyrics="", cover_path=None):
    """
    Update m4a metadata without re-encoding the audio stream.

    Mutagen is preferred for iTunes-native lyric tags.  The command-line
    workflow must also work on a clean macOS Python installation, so FFmpeg is
    used as a stream-copy fallback when Mutagen is unavailable.
    """
    if not HAS_MUTAGEN:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("  ⚠ Neither mutagen nor ffmpeg is available for metadata tagging")
            return False

        temporary_path = f"{file_path}.metadata.m4a"
        try:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
            command = [ffmpeg, "-y", "-v", "error", "-i", file_path]
            if cover_path:
                command.extend(["-i", cover_path])
            command.extend([
                "-map", "0:a:0", "-map_metadata", "0",
                "-c:a", "copy",
                "-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
                "-metadata", f"album_artist={artist}",
            ])
            if cover_path:
                command.extend([
                    "-map", "1:v:0", "-c:v", "mjpeg",
                    "-disposition:v:0", "attached_pic",
                    "-metadata:s:v:0", "title=Cover",
                    "-metadata:s:v:0", "comment=Cover (front)",
                ])
            if lyrics:
                command.extend(["-metadata", f"lyrics={lyrics}"])
            command.append(temporary_path)
            subprocess.run(command, check=True)
            os.replace(temporary_path, file_path)
            return True
        except Exception as e:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
            print(f"  ✗ Failed to update metadata for {file_path}: {e}")
            return False

    try:
        audio = MP4(file_path)
        audio["\xa9nam"] = [title]       # Title
        audio["\xa9ART"] = [artist]      # Artist
        if lyrics:
            audio["\xa9lyr"] = [lyrics]  # Lyrics
        if cover_path:
            with open(cover_path, "rb") as cover_file:
                image_format = MP4Cover.FORMAT_PNG if cover_path.lower().endswith(".png") else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(cover_file.read(), imageformat=image_format)]
        audio.save()
        return True
    except Exception as e:
        print(f"  ✗ Failed to update metadata for {file_path}: {e}")
        return False


def fix_metadata():
    """
    Fix metadata for all downloaded files in the library.
    - Parse and clean titles
    - Fetch lyrics from NetEase Music
    - Update m4a file metadata
    - Update library.json
    """
    if not HAS_MUTAGEN:
        print("Error: mutagen is required. Install with: pip install mutagen")
        return

    library = load_library()

    if not library['items']:
        print("Library is empty. Nothing to fix.")
        return

    print(f"Processing {len(library['items'])} items...\n")

    success_count = 0
    lyrics_count = 0

    for item in library['items']:
        video_id = item['id']
        raw_title = item['title']
        audio_file = item.get('files', {}).get('audio', '')

        if not audio_file:
            print(f"  ⚠ No audio file for {video_id}, skipping")
            continue

        audio_path = os.path.join(AUDIO_DIR, audio_file)

        if not os.path.exists(audio_path):
            print(f"  ⚠ Audio file not found: {audio_file}, skipping")
            continue

        print(f"--- Processing: {video_id}")
        print(f"    Original: {raw_title}")

        # Parse title
        parsed = parse_title(raw_title)
        clean_title = parsed['display_title']
        song_name = parsed['song_name']
        original_artist = parsed['original_artist']
        style = parsed['style']

        print(f"    Clean: {clean_title}")
        print(f"    Song: {song_name}, Artist: {original_artist or 'N/A'}, Style: {style}")

        # Fetch lyrics
        lyrics = fetch_lyrics(song_name, original_artist)
        has_lyrics = bool(lyrics)
        if has_lyrics:
            lyrics_count += 1
            print(f"    ✓ Lyrics found ({len(lyrics)} chars)")
        else:
            print(f"    ○ No lyrics found")

        # Update m4a metadata
        if update_metadata(audio_path, clean_title, "AI音乐", lyrics):
            success_count += 1
            print(f"    ✓ Metadata updated")

        # Update library.json entry
        item['clean_title'] = clean_title
        item['song_name'] = song_name
        item['original_artist'] = original_artist
        item['style'] = style
        item['has_lyrics'] = has_lyrics

    # Save updated library
    save_library(library)

    print(f"\n=== Summary ===")
    print(f"Total items: {len(library['items'])}")
    print(f"Metadata updated: {success_count}")
    print(f"Lyrics found: {lyrics_count}")


def extract_bili_id(url):
    """Extract BV/av ID from a Bilibili URL (handles dirty URLs with query params)."""
    match = re.search(r'(BV[a-zA-Z0-9]+|av\d+)', url)
    return match.group(1) if match else None


def fetch_bilibili_metadata(video_id):
    """Fetch Bilibili video metadata without relying on yt-dlp's Bilibili extractor."""
    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={urllib.parse.quote(video_id)}"
    req = urllib.request.Request(api_url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': 'https://www.bilibili.com/'
    })

    with urllib.request.urlopen(req, timeout=20) as resp:
        info = json.loads(resp.read().decode('utf-8'))

    if info.get('code') != 0 or not info.get('data'):
        raise RuntimeError(f"Bilibili metadata request failed: {info.get('message', 'unknown error')}")

    return info


def _find_downloaded_audio(before_paths):
    """Return the audio file newly produced by bili-cli in DOWNLOADS_DIR."""
    candidates = []
    for root, _, filenames in os.walk(DOWNLOADS_DIR):
        for filename in filenames:
            if filename.lower().endswith(('.m4a', '.mp3', '.aac', '.opus')):
                path = os.path.join(root, filename)
                if path not in before_paths:
                    candidates.append(path)

    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one audio file from bili-cli, found {len(candidates)} new file(s): {candidates}"
        )
    return candidates[0]


def _bili_cli_python():
    """Return the Python runtime backing the installed ``bili`` command."""
    bili_path = shutil.which("bili")
    if not bili_path:
        return None

    try:
        with open(bili_path, encoding="utf-8") as f:
            shebang = f.readline().strip()
    except OSError:
        return None

    if shebang.startswith("#!"):
        return shebang[2:].split()[0]
    return None


def ai_music_artist(uploader):
    """Keep Bilibili downloads eligible for the user's AI Music smart playlist."""
    return f"{uploader} · AI音乐" if uploader else "AI音乐"


def require_mutagen_for_bilibili_artwork():
    """Require native MP4 artwork support for Apple Music-oriented Bilibili flows."""
    if HAS_MUTAGEN:
        return True
    print(
        "Error: mutagen is required for Bilibili artwork. "
        "Install it with: python -m pip install mutagen"
    )
    return False


HIGH_QUALITY_BILI_DOWNLOAD_SCRIPT = r'''
import asyncio
import os
import sys

from bilibili_api import video
from bilibili_api.video import AudioQuality, VideoDownloadURLDataDetecter
from bili_cli.client import download_audio
from bili_cli.commands.common import get_credential


async def main(bvid, output_path):
    credential = get_credential(mode="optional")
    source = video.Video(bvid=bvid, credential=credential)
    download_data = await source.get_download_url(page_index=0)
    detector = VideoDownloadURLDataDetecter(download_data)
    streams = detector.detect_best_streams(
        audio_max_quality=AudioQuality._192K,
        no_dolby_audio=True,
        no_hires=True,
    )

    audio_stream = None
    if detector.check_flv_mp4_stream():
        if streams and getattr(streams[0], "url", None):
            audio_stream = streams[0]
    elif len(streams) >= 2 and getattr(streams[1], "audio_quality", None):
        audio_stream = streams[1]

    if audio_stream is None:
        for stream in streams:
            if getattr(stream, "audio_quality", None) and getattr(stream, "url", None):
                audio_stream = stream
                break
    if audio_stream is None:
        raise RuntimeError("Bilibili did not provide an audio stream")

    partial_path = output_path + ".part"
    urls = [audio_stream.url, *getattr(audio_stream, "backup_url", [])]
    errors = []
    for stream_url in dict.fromkeys(urls):
        if os.path.exists(partial_path):
            os.unlink(partial_path)
        try:
            await download_audio(stream_url, partial_path)
            os.replace(partial_path, output_path)
            break
        except Exception as exc:
            errors.append(f"{stream_url.split('/')[2]}: {exc}")
    else:
        raise RuntimeError("All Bilibili audio CDN URLs failed: " + "; ".join(errors))
    quality = getattr(audio_stream.audio_quality, "value", audio_stream.audio_quality)
    print(f"Downloaded Bilibili audio quality: {quality}")


asyncio.run(main(sys.argv[1], sys.argv[2]))
'''


def download_bilibili_audio(video_id):
    """Download the highest non-Dolby Bilibili audio stream available."""
    before_paths = {
        os.path.join(root, filename)
        for root, _, filenames in os.walk(DOWNLOADS_DIR)
        for filename in filenames
        if filename.lower().endswith((".m4a", ".mp3", ".aac", ".opus"))
    }
    output_path = os.path.join(DOWNLOADS_DIR, f"{video_id}.m4a")
    bili_python = _bili_cli_python()

    if bili_python:
        print(f"Downloading highest available Bilibili audio for {video_id}...")
        subprocess.run(
            [bili_python, "-c", HIGH_QUALITY_BILI_DOWNLOAD_SCRIPT, video_id, output_path],
            check=True,
            env=NO_PROXY_ENV,
        )
    else:
        # Keep the existing CLI route usable on installations that do not expose
        # the bili-cli Python runtime. It may be limited to 64 kbps.
        print("Could not inspect bili-cli runtime; falling back to its default audio stream.")
        subprocess.run(
            ["bili", "audio", video_id, "--no-split", "--output", DOWNLOADS_DIR],
            check=True,
            env=NO_PROXY_ENV,
        )

    return _find_downloaded_audio(before_paths)


def download_bilibili(video_id):
    """Download a Bilibili video as m4a with bili-cli and add it to the local library."""
    if not require_mutagen_for_bilibili_artwork():
        raise RuntimeError("Native MP4 artwork support is unavailable")

    library = load_library()
    if any(item['id'] == video_id for item in library['items']):
        print("Item already in library.")
        return

    info = fetch_bilibili_metadata(video_id)
    video = info['data']
    title = video.get('title') or video_id
    uploader = video.get('owner', {}).get('name', '')
    source_url = f"https://www.bilibili.com/video/{video_id}"
    cover_path = fetch_bilibili_cover(video_id, video.get('pic'))

    meta_path = os.path.join(METADATA_DIR, f"{video_id}.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    downloaded_audio = download_bilibili_audio(video_id)
    audio_filename = f"{title} [{video_id}].m4a"
    audio_path = os.path.join(AUDIO_DIR, audio_filename)
    os.replace(downloaded_audio, audio_path)

    # The Bilibili audio endpoint does not provide useful Apple Music tags.
    # Include the smart-playlist marker while keeping the UP name visible.
    if not update_metadata(
        audio_path,
        title,
        ai_music_artist(uploader),
        cover_path=cover_path,
    ):
        raise RuntimeError(f"Could not write Bilibili metadata for {video_id}")

    library['items'].append({
        "id": video_id,
        "title": title,
        "uploader": uploader,
        "source_url": source_url,
        "downloaded_at": datetime.now().isoformat(),
        "files": {
            "audio": audio_filename,
            "metadata": f"{video_id}.json",
            **({"cover": os.path.basename(cover_path)} if cover_path else {}),
        }
    })
    save_library(library)
    print(f"Successfully added '{title}' to library.")


def audio_bitrate(file_path):
    """Return the first audio stream's bitrate in bits per second."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=bit_rate",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def has_embedded_cover(file_path):
    """Return whether an M4A has artwork that the current tagger can read."""
    if HAS_MUTAGEN:
        try:
            audio = MP4(file_path)
            return bool(audio.tags and audio.tags.get("covr"))
        except Exception:
            return False

    # The FFmpeg fallback cannot write the iTunes-native ``covr`` atom, but an
    # attached picture remains the best artwork representation it can produce.
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
            "-of", "json", file_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    return any(
        stream.get("codec_type") == "video"
        and stream.get("disposition", {}).get("attached_pic") == 1
        for stream in streams
    )


def fix_bilibili_covers(uploader, input_dir=None, limit=None):
    """Embed cached Bilibili cover art into already-downloaded audio files."""
    if not require_mutagen_for_bilibili_artwork():
        return 1

    source_dir = input_dir or os.path.join(BASE_DIR, "audio-bilibili-192k")
    library = load_library()
    items = [
        item for item in library["items"]
        if item.get("source_url", "").startswith("https://www.bilibili.com/video/")
        and item.get("uploader") == uploader
    ]

    processed = 0
    successes = 0
    failures = []
    for index, item in enumerate(items, 1):
        if limit is not None and processed >= limit:
            break
        audio_filename = item.get("files", {}).get("audio") or f"{item['id']}.m4a"
        audio_path = os.path.join(source_dir, audio_filename)
        if not os.path.isfile(audio_path):
            continue
        if has_embedded_cover(audio_path):
            successes += 1
            continue

        processed += 1
        try:
            cover_path = cover_path_for_item(item)
            if not cover_path:
                raise RuntimeError("cover URL is missing or could not be downloaded")
            if not update_metadata(
                audio_path,
                item.get("title") or item["id"],
                ai_music_artist(item.get("uploader", "")),
                cover_path=cover_path,
            ):
                raise RuntimeError("metadata update failed")
            if not has_embedded_cover(audio_path):
                raise RuntimeError("cover was not embedded")
            successes += 1
            print(f"COVER_PROGRESS {index}/{len(items)} {item['id']}", flush=True)
        except Exception as exc:
            failures.append((item["id"], str(exc)))
            print(f"COVER_ERROR {index}/{len(items)} {item['id']}: {exc}", flush=True)

    print(
        f"COVER_SUMMARY covered={successes} processed={processed} "
        f"failed={len(failures)} total={len(items)}",
        flush=True,
    )
    for video_id, error in failures:
        print(f"COVER_FAILURE {video_id}: {error}", flush=True)
    return len(failures)


def verify_bilibili_media(uploader, input_dir=None, min_bitrate=96000):
    """Verify bitrate, native artwork, and Music metadata for staged Bilibili audio."""
    if not require_mutagen_for_bilibili_artwork():
        return 1

    source_dir = input_dir or os.path.join(BASE_DIR, "audio-bilibili-192k")
    library = load_library()
    items = [
        item for item in library["items"]
        if item.get("source_url", "").startswith("https://www.bilibili.com/video/")
        and item.get("uploader") == uploader
    ]
    if not items:
        print(f"No Bilibili library items to verify for UP: {uploader}")
        return 1

    missing = []
    low_bitrate = []
    missing_cover = []
    tag_mismatch = []
    errors = []
    present = 0
    for item in items:
        video_id = item["id"]
        audio_filename = item.get("files", {}).get("audio") or f"{video_id}.m4a"
        audio_path = os.path.join(source_dir, audio_filename)
        if not os.path.isfile(audio_path):
            missing.append(video_id)
            continue
        present += 1
        try:
            if audio_bitrate(audio_path) <= min_bitrate:
                low_bitrate.append(video_id)
            if not has_embedded_cover(audio_path):
                missing_cover.append(video_id)
            tags = MP4(audio_path).tags or {}
            expected_title = item.get("title") or video_id
            expected_artist = ai_music_artist(item.get("uploader", ""))
            actual_title = str((tags.get("\xa9nam") or [""])[0])
            actual_artist = str((tags.get("\xa9ART") or [""])[0])
            if actual_title != expected_title or actual_artist != expected_artist:
                tag_mismatch.append(video_id)
        except Exception as exc:
            errors.append((video_id, str(exc)))

    print(
        f"VERIFY_SUMMARY total={len(items)} present={present} missing={len(missing)} "
        f"low_bitrate={len(low_bitrate)} missing_cover={len(missing_cover)} "
        f"tag_mismatch={len(tag_mismatch)} errors={len(errors)}",
        flush=True,
    )
    for video_id, error in errors:
        print(f"VERIFY_ERROR {video_id}: {error}", flush=True)
    return len(missing) + len(low_bitrate) + len(missing_cover) + len(tag_mismatch) + len(errors)


def refresh_bilibili(uploader, output_dir=None, limit=None):
    """Stage high-quality Bilibili source files for one UP's library items.

    The existing ``audio`` directory and Music.app library are not modified.
    The command is restartable: an already-verified staged file is retained,
    while missing items are retried through the primary and backup CDNs.
    """
    if not require_mutagen_for_bilibili_artwork():
        return 1

    destination = output_dir or os.path.join(BASE_DIR, "audio-bilibili-192k")
    os.makedirs(destination, exist_ok=True)
    library = load_library()
    items = [
        item for item in library["items"]
        if item.get("source_url", "").startswith("https://www.bilibili.com/video/")
        and item.get("uploader") == uploader
    ]

    if not items:
        print(f"No Bilibili library items to refresh for UP: {uploader}")
        return 0

    successes = 0
    downloads_started = 0
    failures = []
    for index, item in enumerate(items, 1):
        video_id = item["id"]
        title = item.get("title") or video_id
        uploader = item.get("uploader", "")
        audio_filename = item.get("files", {}).get("audio") or f"{video_id}.m4a"
        target = os.path.join(destination, audio_filename)
        cover_path = cover_path_for_item(item)

        if os.path.exists(target):
            try:
                if not update_metadata(
                    target,
                    title,
                    ai_music_artist(uploader),
                    cover_path=cover_path,
                ):
                    raise RuntimeError("metadata update failed")
                bitrate = audio_bitrate(target)
                if bitrate <= 96000:
                    raise RuntimeError(f"staged bitrate is too low: {bitrate}")
                successes += 1
                continue
            except Exception as exc:
                failures.append((video_id, str(exc)))
                print(f"REFRESH_ERROR {index}/{len(items)} {video_id}: {exc}", flush=True)
                continue

        if limit is not None and downloads_started >= limit:
            break
        downloads_started += 1
        downloaded_path = os.path.join(DOWNLOADS_DIR, f"{video_id}.m4a")
        partial_path = downloaded_path + ".part"
        last_error = None
        for attempt in range(1, 4):
            for path in (downloaded_path, partial_path):
                if os.path.exists(path):
                    os.unlink(path)
            try:
                downloaded = download_bilibili_audio(video_id)
                if not update_metadata(
                    downloaded,
                    title,
                    ai_music_artist(uploader),
                    cover_path=cover_path,
                ):
                    raise RuntimeError("metadata update failed")
                os.replace(downloaded, target)
                bitrate = audio_bitrate(target)
                if bitrate <= 96000:
                    os.unlink(target)
                    raise RuntimeError(f"downloaded bitrate is too low: {bitrate}")
                successes += 1
                print(
                    f"REFRESH_PROGRESS {index}/{len(items)} downloaded={video_id} "
                    f"attempt={attempt} bitrate={bitrate}",
                    flush=True,
                )
                break
            except Exception as exc:
                last_error = exc
                print(
                    f"REFRESH_RETRY {index}/{len(items)} {video_id} "
                    f"attempt={attempt}: {exc}",
                    flush=True,
                )
        else:
            failures.append((video_id, str(last_error)))
            print(f"REFRESH_ERROR {index}/{len(items)} {video_id}: {last_error}", flush=True)

    print(
        f"REFRESH_SUMMARY verified={successes} attempted={downloads_started} "
        f"failed={len(failures)} total={len(items)}",
        flush=True,
    )
    for video_id, error in failures:
        print(f"REFRESH_FAILURE {video_id}: {error}", flush=True)
    return len(failures)


def is_playlist_url(url):
    """Check if URL is a playlist/collection (合集) link."""
    # 合集格式: /lists/, favlist, or series
    return bool(re.search(r'(/lists/|/favlist|series_id=|season_id=)', url))


def expand_playlist(url):
    """Use yt-dlp to expand a playlist into individual video URLs."""
    print(f"Expanding playlist: {url}")
    cmd = ["yt-dlp", "--flat-playlist", "--dump-json", url]
    result = subprocess.run(cmd, capture_output=True, text=True, env=NO_PROXY_ENV)

    if result.returncode != 0:
        print(f"Error expanding playlist: {result.stderr}")
        return []

    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        try:
            info = json.loads(line)
            video_id = info.get('id')
            video_url = info.get('url') or info.get('webpage_url')
            if video_id:
                # Construct canonical URL if needed
                if not video_url or not video_url.startswith('http'):
                    video_url = f"https://www.bilibili.com/video/{video_id}"
                videos.append({'id': video_id, 'url': video_url, 'title': info.get('title', video_id)})
        except json.JSONDecodeError:
            continue

    print(f"Found {len(videos)} video(s) in playlist")
    return videos


def log_message(status, video_id, title="", error=""):
    """Append a log entry to download.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if error:
        line = f"[{timestamp}] [{status}] {video_id} - {error}\n"
    else:
        line = f"[{timestamp}] [{status}] {video_id} - {title}\n"
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line)


def is_in_library(video_id):
    """Check if a video ID already exists in the library."""
    library = load_library()
    for item in library['items']:
        if item['id'] == video_id:
            return True
    return False


def load_library():
    if os.path.exists(LIBRARY_FILE):
        with open(LIBRARY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"items": []}

def save_library(library):
    with open(LIBRARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

def download(url):
    print(f"Downloading {url}...")

    # Bilibili's yt-dlp extractor is currently blocked by Bilibili's 412
    # anti-bot response. Use the dedicated bili-cli audio command instead.
    video_id = extract_bili_id(url)
    if video_id:
        return download_bilibili(video_id)

    # Generate a unique ID (timestamp based for simplicity, or use yt-dlp id)
    # We let yt-dlp handle filename generation but capture the output ID

    # 1. Get Metadata first
    cmd_info = [
        "yt-dlp", "--dump-json", url
    ]
    result = subprocess.run(cmd_info, capture_output=True, text=True, env=NO_PROXY_ENV)
    if result.returncode != 0:
        print("Error fetching metadata")
        return

    info = json.loads(result.stdout)
    video_id = info.get('id')
    title = info.get('title')
    uploader = info.get('uploader')

    # Save metadata
    meta_path = os.path.join(METADATA_DIR, f"{video_id}.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    # 2. Download Audio (m4a for Apple Music)
    output_template = os.path.join(AUDIO_DIR, f"{title} [{video_id}].%(ext)s")

    cmd_dl = [
        "yt-dlp",
        "-x", "--audio-format", "m4a", "--audio-quality", "0",
        "--embed-thumbnail", "--add-metadata",
        "-o", output_template,
        url
    ]

    subprocess.run(cmd_dl, check=True, env=NO_PROXY_ENV)

    # 3. Update Library
    library = load_library()

    # Check if exists
    for item in library['items']:
        if item['id'] == video_id:
            print("Item already in library.")
            return

    new_item = {
        "id": video_id,
        "title": title,
        "uploader": uploader,
        "source_url": url,
        "downloaded_at": datetime.now().isoformat(),
        "files": {
            "audio": f"{title} [{video_id}].m4a",
            "metadata": f"{video_id}.json"
        }
    }

    library['items'].append(new_item)
    save_library(library)
    print(f"Successfully added '{title}' to library.")

def list_items():
    lib = load_library()
    print(f"{'ID':<15} | {'Uploader':<20} | {'Title'}")
    print("-" * 60)
    for item in lib['items']:
        print(f"{item['id']:<15} | {item.get('uploader', 'N/A')[:20]:<20} | {item['title']}")


def process_tasks():
    """Process all URLs in tasks.txt: download, dedupe, and clean up."""
    if not os.path.exists(TASKS_FILE):
        print(f"No tasks file found at {TASKS_FILE}")
        return

    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Filter out empty lines and whitespace
    tasks = [line.strip() for line in lines if line.strip()]

    if not tasks:
        print("No tasks to process.")
        return

    print(f"Found {len(tasks)} task(s) to process.\n")

    remaining_tasks = []
    total_downloaded = 0

    for url in tasks:
        print(f"--- Processing: {url}")

        # Check if it's a playlist/collection
        if is_playlist_url(url):
            print("  📂 Detected playlist/collection")
            videos = expand_playlist(url)
            if not videos:
                print("  ✗ Failed to expand playlist")
                log_message("ERROR", url[:50], error="Failed to expand playlist")
                remaining_tasks.append(url)
                continue

            playlist_success = True
            for video in videos:
                video_id = video['id']
                video_url = video['url']

                if is_in_library(video_id):
                    print(f"  ✓ Already in library: {video_id}")
                    continue

                try:
                    download(video_url)
                    if is_in_library(video_id):
                        log_message("SUCCESS", video_id, title=video.get('title', video_id))
                        total_downloaded += 1
                    else:
                        playlist_success = False
                except Exception as e:
                    print(f"  ✗ Failed: {video_id} - {e}")
                    log_message("ERROR", video_id, error=str(e))
                    playlist_success = False

            if not playlist_success:
                remaining_tasks.append(url)
            continue

        # Single video processing
        video_id = extract_bili_id(url)
        if not video_id:
            print(f"  ✗ Invalid URL, cannot extract ID")
            log_message("INVALID", url[:50], error="Cannot extract BV/av ID")
            remaining_tasks.append(url)
            continue

        if is_in_library(video_id):
            print(f"  ✓ Already in library, skipping: {video_id}")
            log_message("SKIPPED", video_id, error="Already in library")
            continue

        try:
            download(url)
            if is_in_library(video_id):
                library = load_library()
                title = next((item['title'] for item in library['items'] if item['id'] == video_id), video_id)
                log_message("SUCCESS", video_id, title=title)
                print(f"  ✓ Downloaded successfully: {video_id}")
                total_downloaded += 1
            else:
                log_message("ERROR", video_id, error="Download completed but not in library")
                remaining_tasks.append(url)
        except Exception as e:
            print(f"  ✗ Download failed: {e}")
            log_message("ERROR", video_id, error=str(e))
            remaining_tasks.append(url)

    # Rewrite tasks.txt with only failed/remaining tasks
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        for task in remaining_tasks:
            f.write(task + '\n')

    print(f"\n=== Summary ===")
    print(f"Tasks processed: {len(tasks)}")
    print(f"Videos downloaded: {total_downloaded}")
    if remaining_tasks:
        print(f"Remaining in tasks.txt: {len(remaining_tasks)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python manager.py [download <url> | list | process | fix | refresh-bilibili --uploader <name> [--limit <number>] [output-dir] | fix-bilibili-covers --uploader <name> [--limit <number>] [input-dir] | verify-bilibili --uploader <name> [--min-bitrate <bps>] [input-dir]]")
        sys.exit(1)

    action = sys.argv[1]

    if action == "download":
        if len(sys.argv) < 3:
            print("Usage: python manager.py download <url>")
        else:
            download(sys.argv[2])
    elif action == "list":
        list_items()
    elif action == "process":
        process_tasks()
    elif action == "fix":
        fix_metadata()
    elif action == "refresh-bilibili":
        if len(sys.argv) < 4 or sys.argv[2] != "--uploader":
            print("Usage: python manager.py refresh-bilibili --uploader <name> [--limit <number>] [output-dir]")
            sys.exit(1)
        uploader = sys.argv[3]
        remaining = sys.argv[4:]
        limit = None
        if remaining[:1] == ["--limit"]:
            if len(remaining) < 2:
                print("--limit requires a positive integer")
                sys.exit(1)
            limit = int(remaining[1])
            if limit <= 0:
                print("--limit requires a positive integer")
                sys.exit(1)
            remaining = remaining[2:]
        if len(remaining) > 1:
            print("Usage: python manager.py refresh-bilibili --uploader <name> [--limit <number>] [output-dir]")
            sys.exit(1)
        output_dir = remaining[0] if remaining else None
        sys.exit(1 if refresh_bilibili(uploader, output_dir, limit) else 0)
    elif action == "fix-bilibili-covers":
        if len(sys.argv) < 4 or sys.argv[2] != "--uploader":
            print("Usage: python manager.py fix-bilibili-covers --uploader <name> [--limit <number>] [input-dir]")
            sys.exit(1)
        uploader = sys.argv[3]
        remaining = sys.argv[4:]
        limit = None
        if remaining[:1] == ["--limit"]:
            if len(remaining) < 2:
                print("--limit requires a positive integer")
                sys.exit(1)
            limit = int(remaining[1])
            if limit <= 0:
                print("--limit requires a positive integer")
                sys.exit(1)
            remaining = remaining[2:]
        if len(remaining) > 1:
            print("Usage: python manager.py fix-bilibili-covers --uploader <name> [--limit <number>] [input-dir]")
            sys.exit(1)
        input_dir = remaining[0] if remaining else None
        sys.exit(1 if fix_bilibili_covers(uploader, input_dir, limit) else 0)
    elif action == "verify-bilibili":
        if len(sys.argv) < 4 or sys.argv[2] != "--uploader":
            print("Usage: python manager.py verify-bilibili --uploader <name> [--min-bitrate <bps>] [input-dir]")
            sys.exit(1)
        uploader = sys.argv[3]
        remaining = sys.argv[4:]
        min_bitrate = 96000
        if remaining[:1] == ["--min-bitrate"]:
            if len(remaining) < 2:
                print("--min-bitrate requires a positive integer")
                sys.exit(1)
            try:
                min_bitrate = int(remaining[1])
            except ValueError:
                print("--min-bitrate requires a positive integer")
                sys.exit(1)
            if min_bitrate <= 0:
                print("--min-bitrate requires a positive integer")
                sys.exit(1)
            remaining = remaining[2:]
        if len(remaining) > 1:
            print("Usage: python manager.py verify-bilibili --uploader <name> [--min-bitrate <bps>] [input-dir]")
            sys.exit(1)
        input_dir = remaining[0] if remaining else None
        sys.exit(1 if verify_bilibili_media(uploader, input_dir, min_bitrate) else 0)
    else:
        print("Unknown command")
