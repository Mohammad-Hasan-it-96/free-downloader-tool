================================================================
  VIDEO DOWNLOADER  (powered by yt-dlp)
================================================================

WHAT IT DOES
  Downloads videos from YouTube and 1000+ other sites, lets you
  choose the resolution/quality, and saves them to D:\Videos
  (so your C: drive stays free).

HOW TO RUN
  Double-click:  "Download Video.bat"
  (or run:  python video_downloader.py)

MENU OPTIONS
  1. Download a video / audio  -> paste URL, pick quality
  2. Change download folder    -> default is D:\Videos
  3. Set browser for cookies   -> fixes YouTube "not a bot" error
  4. Show available formats     -> see every resolution for a URL
  5. Update yt-dlp             -> keep the downloader current

QUALITY CHOICES
  Best / 1080p / 720p / 480p / 360p / Audio-only MP3, or pick an
  exact format code from the list.

------------------------------------------------------------
FIXING YOUTUBE "Sign in to confirm you're not a bot"
------------------------------------------------------------
YouTube sometimes blocks anonymous downloads. Fix it with cookies:

  1. In the app, choose menu option 3 and select the browser you
     use for YouTube (e.g. edge or chrome).
  2. IMPORTANT: fully CLOSE that browser before downloading,
     otherwise its cookie file is locked and cannot be read.
  3. Download again.

If your browser still won't share cookies (some Chrome/Edge
versions encrypt them), export a cookies.txt file instead using a
browser extension like "Get cookies.txt LOCALLY", then in a
terminal run:
    python -m yt_dlp --cookies cookies.txt -f best <URL>

------------------------------------------------------------
INSTALLED DEPENDENCIES (already set up)
------------------------------------------------------------
  - Python 3.14
  - yt-dlp        (the downloader)
  - ffmpeg        (merges HD video+audio) - via winget
  - deno          (JavaScript runtime yt-dlp needs for YouTube)

The app auto-finds ffmpeg and deno, so you don't configure paths.

TROUBLESHOOTING
  - "ffmpeg NOT FOUND" in the header: restart the app; if it
    persists, reinstall with:  winget install Gyan.FFmpeg
  - Slow/blocked YouTube: enable cookies (see above).
  - Update the downloader regularly with menu option 5.
================================================================
