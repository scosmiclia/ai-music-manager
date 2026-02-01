import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime

try:
    from mutagen.mp4 import MP4
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


def update_metadata(file_path, title, artist, lyrics=""):
    """
    Update m4a file metadata using mutagen.
    """
    if not HAS_MUTAGEN:
        print("  ⚠ mutagen not installed. Run: pip install mutagen")
        return False

    try:
        audio = MP4(file_path)
        audio["\xa9nam"] = [title]       # Title
        audio["\xa9ART"] = [artist]      # Artist
        if lyrics:
            audio["\xa9lyr"] = [lyrics]  # Lyrics
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
        print("Usage: python manager.py [download <url> | list | process | fix]")
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
    else:
        print("Unknown command")
