#!/usr/bin/env python3
"""
YTMax Downloader (Desktop Edition)
===================================
A cross-platform command-line tool for downloading YouTube videos in
any available quality (up to 8K) using yt-dlp. Works on Windows,
macOS, and Linux.

SETUP (run once):

    1. Install Python 3.9+  ->  https://python.org/downloads

    2. Install ffmpeg (required to merge separate video+audio streams
       for anything above 1080p):
         Windows : winget install ffmpeg        (or choco install ffmpeg)
         macOS   : brew install ffmpeg
         Linux   : sudo apt install ffmpeg      (Debian/Ubuntu)
                   sudo dnf install ffmpeg      (Fedora)
                   sudo pacman -S ffmpeg        (Arch)

    3. Install yt-dlp:
         pip install --upgrade yt-dlp

RUN:
    python ytmax_downloader_pc.py

Notes:
- 8K/4320p footage only exists for videos the uploader actually
  published in that resolution. YTMax Downloader shows you every
  quality that's really available for the video you paste in — it
  never fakes a resolution that isn't there.
- Only download videos you have the right to download (your own
  content, content licensed for reuse, or personal/offline use where
  permitted). Respect YouTube's Terms of Service and copyright law in
  your country.
"""

import os
import sys
import platform
import shutil
import re
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("\n[!] yt-dlp is not installed.")
    print("    Install it with:  pip install --upgrade yt-dlp\n")
    sys.exit(1)


APP_NAME = "YTMax Downloader"
YOUTUBE_URL_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/\S+"
)

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


# ---------------------------------------------------------------------
# Cross-platform ANSI color support
# ---------------------------------------------------------------------

def _enable_windows_ansi() -> bool:
    """Turn on virtual-terminal (ANSI) processing in Windows consoles."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        mode.value |= ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode))
    except Exception:
        return False


def _color_supported() -> bool:
    if not sys.stdout.isatty():
        return False
    if platform.system() == "Windows":
        return _enable_windows_ansi()
    return True


USE_COLOR = _color_supported()


def c(code: str) -> str:
    """Return the ANSI code only if this terminal can display it."""
    return code if USE_COLOR else ""


RESET = c("\033[0m")
BOLD = c("\033[1m")
RED = c("\033[91m")
BOLD_RED = c("\033[1;91m")
MAGENTA = c("\033[95m")
BOLD_MAGENTA = c("\033[1;95m")
YELLOW = c("\033[93m")
GREEN = c("\033[92m")
CYAN = c("\033[96m")
BLUE = c("\033[94m")
GRAY = c("\033[90m")

QUALITY_COLORS = {
    4320: BOLD_MAGENTA,
    2160: BOLD_RED,
    1440: YELLOW,
    1080: GREEN,
    720: CYAN,
    480: BLUE,
    360: GRAY,
    240: GRAY,
    144: GRAY,
}


# ---------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------

def banner():
    logo = r"""
__   _______ __  __              ____                        _                 _
\ \ / /_   _|  \/  | __ ___  __ |  _ \  _____      ___ __   | | ___   __ _  __| | ___ _ __
 \ V /  | | | |\/| |/ _` \ \/ / | | | |/ _ \ \ /\ / / '_ \  | |/ _ \ / _` |/ _` |/ _ \ '__|
  | |   | | | |  | | (_| |>  <  | |_| | (_) \ V  V /| | | | | | (_) | (_| | (_| |  __/ |
  |_|   |_| |_|  |_|\__,_/_/\_\ |____/ \___/ \_/\_/ |_| |_| |_|\___/ \__,_|\__,_|\___|_|
"""
    print(f"{BOLD_RED}{logo}{RESET}")
    print(f"        {BOLD_RED}{APP_NAME}{RESET} — Desktop Edition (Windows / macOS / Linux)")
    print(f"{RED}{'-' * 90}{RESET}")


def check_ffmpeg():
    if shutil.which("ffmpeg"):
        return
    print(f"{YELLOW}[!] ffmpeg was not found on your PATH.{RESET}")
    print("    High-resolution downloads (above 1080p) and audio extraction need it.")
    system = platform.system()
    if system == "Windows":
        print("    Install it with:  winget install ffmpeg   (or: choco install ffmpeg)")
    elif system == "Darwin":
        print("    Install it with:  brew install ffmpeg")
    else:
        print("    Install it with:  sudo apt install ffmpeg   (or your distro's package manager)")
    print()


def ensure_download_dir() -> str:
    """Pick a writable downloads folder: ~/Downloads/YTMax, with a fallback."""
    candidates = [
        Path.home() / "Downloads" / "YTMax",
        Path.cwd() / "YTMax_Downloads",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return str(candidate)
        except OSError:
            continue
    return str(Path.cwd())


def get_url():
    while True:
        url = input("\nPaste the YouTube video URL: ").strip()
        if YOUTUBE_URL_RE.match(url):
            return url
        print("[!] That doesn't look like a YouTube URL. Try again.")


def probe_video(url):
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def available_qualities(info):
    formats = info.get("formats", [])
    heights_present = {f.get("height") for f in formats if f.get("height")}

    found = [(h, label) for h, label in RESOLUTION_LADDER if h in heights_present]

    if not found and heights_present:
        for height in sorted(heights_present, reverse=True):
            found.append((height, f"{height}p"))

    return found


def build_format_string(height):
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
    check_ffmpeg()
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