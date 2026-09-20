#!/usr/bin/env python3
"""
YTMax Downloader
=================
A Termux command-line tool for downloading YouTube videos in any
available quality (up to 8K) using yt-dlp.

SETUP (run once in Termux):
    pkg update && pkg upgrade -y
    pkg install python ffmpeg -y
    pip install --upgrade yt-dlp

RUN:
    python ytmax_downloader.py

Notes:
- ffmpeg is required to merge separate video+audio streams (needed for
  anything above 1080p, since YouTube serves high-res video and audio
  as separate tracks).
- 8K/4320p footage only exists for videos the uploader actually
  published in that resolution. YTMax Downloader will show you every
  quality that's really available for the video you paste in — it
  never fakes a resolution that isn't there.
- Only download videos you have the right to download (your own
  content, content licensed for reuse, or for personal/offline use
  where permitted). Respect YouTube's Terms of Service and copyright
  law in your country.
"""

import os
import sys
import re

try:
    import yt_dlp
except ImportError:
    print("\n[!] yt-dlp is not installed.")
    print("    Install it with:  pip install --upgrade yt-dlp\n")
    sys.exit(1)


# ---- Terminal colors (ANSI escape codes — work fine in Termux) ----
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
BOLD_RED = "\033[1;91m"
MAGENTA = "\033[95m"
BOLD_MAGENTA = "\033[1;95m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BLUE = "\033[94m"
GRAY = "\033[90m"

# Color for each resolution tier, best -> worst.
QUALITY_COLORS = {
    4320: BOLD_MAGENTA,  # 8K — top tier, stands out most
    2160: BOLD_RED,      # 4K
    1440: YELLOW,        # 2K / QHD
    1080: GREEN,         # Full HD
    720: CYAN,           # HD
    480: BLUE,           # SD
    360: GRAY,           # Low
    240: GRAY,           # Very Low
    144: GRAY,           # Lowest
}

APP_NAME = "YTMax Downloader"
DOWNLOAD_DIR = os.path.expanduser("~/storage/downloads/YTMax")
FALLBACK_DIR = os.path.join(os.getcwd(), "YTMax_Downloads")

YOUTUBE_URL_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/\S+"
)

# Standard resolution ladder we try to detect in the video's formats.
RESOLUTION_LADDER = [
    (4320, "8K"),
    (2160, "4K"),
    (1440, "2K / QHD"),
    (1080, "Full HD"),
    (720, "HD"),
    (480, "SD"),
    (360, "Low"),
    (240, "Very Low"),
    (144, "Lowest"),
]


def banner():
    logo = r"""
__   _______ __  __              ____                        _                 _
\ \ / /_   _|  \/  | __ ___  __ |  _ \  _____      ___ __   | | ___   __ _  __| | ___ _ __
 \ V /  | | | |\/| |/ _` \ \/ / | | | |/ _ \ \ /\ / / '_ \  | |/ _ \ / _` |/ _` |/ _ \ '__|
  | |   | | | |  | | (_| |>  <  | |_| | (_) \ V  V /| | | | | | (_) | (_| | (_| |  __/ |
  |_|   |_| |_|  |_|\__,_/_/\_\ |____/ \___/ \_/\_/ |_| |_| |_|\___/ \__,_|\__,_|\___|_|
"""
    print(f"{BOLD_RED}{logo}{RESET}")
    print(f"        {BOLD_RED}{APP_NAME}{RESET} — download YouTube videos in any quality, up to 8K")
    print(f"{RED}{'-' * 90}{RESET}")


def ensure_download_dir():
    """Pick a writable downloads folder, preferring Termux's shared storage."""
    for candidate in (DOWNLOAD_DIR, FALLBACK_DIR):
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except OSError:
            continue
    return os.getcwd()


def get_url():
    while True:
        url = input("\nPaste the YouTube video URL: ").strip()
        if YOUTUBE_URL_RE.match(url):
            return url
        print("[!] That doesn't look like a YouTube URL. Try again.")


def probe_video(url):
    """Fetch metadata + available formats without downloading anything."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def available_qualities(info):
    """
    Look at the real formats returned for this video and figure out
    which entries in RESOLUTION_LADDER are actually available.
    Returns a list of (height, label) tuples, highest first.
    """
    formats = info.get("formats", [])
    heights_present = {f.get("height") for f in formats if f.get("height")}

    found = []
    for height, label in RESOLUTION_LADDER:
        if height in heights_present:
            found.append((height, label))

    # In case the exact standard heights aren't hit (some videos use
    # odd values like 2158), fall back to whatever heights exist.
    if not found and heights_present:
        for height in sorted(heights_present, reverse=True):
            found.append((height, f"{height}p"))

    return found


def build_format_string(height):
    """
    yt-dlp format selector: best video up to `height`, merged with
    best audio. Falls back gracefully if that exact combo is missing.
    """
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"


def choose_quality(qualities):
    print(f"\n{BOLD}Available qualities for this video:{RESET}")
    print(f"  {BOLD}{GREEN}0. Best available{RESET} (auto — highest quality found)")
    for i, (height, label) in enumerate(qualities, start=1):
        color = QUALITY_COLORS.get(height, GRAY)
        tag = f" {BOLD}★ 8K{RESET}{color}" if height == 4320 else ""
        print(f"  {color}{i}. {height}p — {label}{tag}{RESET}")
    audio_index = len(qualities) + 1
    print(f"  {CYAN}{audio_index}. Audio only (MP3){RESET}")

    while True:
        choice = input(f"\nChoose an option [0-{audio_index}]: ").strip()
        if not choice.isdigit():
            print("[!] Enter a number.")
            continue
        choice = int(choice)
        if choice == 0:
            return ("video", None)
        if 1 <= choice <= len(qualities):
            return ("video", qualities[choice - 1][0])
        if choice == audio_index:
            return ("audio", None)
        print("[!] Invalid option.")


def progress_hook(d):
    if d["status"] == "downloading":
        pct = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        sys.stdout.write(f"\r    Downloading... {pct}  speed: {speed}  eta: {eta}   ")
        sys.stdout.flush()
    elif d["status"] == "finished":
        print("\n    Download finished, processing (merging/converting)...")


def download(url, mode, height, out_dir):
    outtmpl = os.path.join(out_dir, "%(title)s [%(resolution)s].%(ext)s")

    if mode == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }
    else:
        fmt = build_format_string(height) if height else "bestvideo+bestaudio/best"
        ydl_opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main():
    banner()
    out_dir = ensure_download_dir()
    print(f"Saving downloads to: {out_dir}")

    while True:
        url = get_url()

        print("\nFetching video info...")
        try:
            info = probe_video(url)
        except yt_dlp.utils.DownloadError as e:
            print(f"[!] Couldn't fetch video info: {e}")
            continue

        title = info.get("title", "Unknown title")
        duration = info.get("duration")
        duration_str = f"{duration // 60}m {duration % 60}s" if duration else "N/A"
        print(f"\n{BOLD}Title:{RESET} {title}")
        print(f"{BOLD}Duration:{RESET} {duration_str}")

        qualities = available_qualities(info)
        if not qualities:
            print("[!] No downloadable video formats found for this video.")
            continue

        mode, height = choose_quality(qualities)

        print()
        try:
            download(url, mode, height, out_dir)
            print(f"\n{GREEN}[✔] Done! Saved in: {out_dir}{RESET}")
        except yt_dlp.utils.DownloadError as e:
            print(f"\n{RED}[!] Download failed: {e}{RESET}")

        again = input("\nDownload another video? (y/n): ").strip().lower()
        if again != "y":
            print("\nThanks for using YTMax Downloader. Bye!")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Cancelled by user. Bye!")
        sys.exit(0)
