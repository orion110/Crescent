#!/usr/bin/env python3
# Crescent.py — terminal YouTube Crescent · grey/white theme · mpv · queue · ollama `ask`
# command-driven terminal interface
import curses, json, os, queue, random, re, socket, subprocess, sys, textwrap, threading, time, urllib.request, urllib.parse

SOCK       = "/tmp/play-mpv.sock"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL      = "qwen2:0.5b"      # <- change to any model from `ollama list`
DEBUG      = False             # <- set True to show the [debug] line
STATUS_TTL = 5                 # <- status messages AND queue line disappear after this many seconds
OFFLINE_CATCHALL_CHANCE = 0.65 # <- odds (0.0-1.0) that unrecognized chat text gets a canned
                                #    offline reply instead of being sent to Ollama. 0 = old
                                #    behavior (always ask Ollama when no trigger matches),
                                #    1 = never bother Ollama for ordinary chat.
LIB_FILE   = os.path.expanduser("~/.crescent_library.json")   # remembered tracks + metadata
SETTINGS_FILE = os.path.expanduser("~/.crescent_settings.json")  # lightweight UI/settings persistence
BLACKLIST_FILE = os.path.expanduser("~/.crescent_blacklist.json")  # URLs to skip in shuffle

# Optional cookies file (Netscape format, exported from a logged-in browser).
COOKIES_FILE = os.path.expanduser("~/.crescent_cookies.txt")
if not os.path.exists(COOKIES_FILE):
    COOKIES_FILE = None

# MPRIS support (KDE Connect media control, GNOME media widgets, playerctl, etc.)
MPRIS_SCRIPT_PATHS = [
    os.path.expanduser("~/.config/mpv/scripts/mpris.so"),
    "/usr/lib/mpv-mpris/mpris.so",
    "/usr/local/lib/mpv-mpris/mpris.so",
]

# logo — swoosh, top left
MARK = [
    "⠀⠀⠀⠀⣀⣤⡶⠟⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
    "⠀⠀⣠⣾⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
    "⠀⣼⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
    "⣼⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
    "⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀",
    "⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⠁",
    "⢻⣿⣿⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡿⠀",
    "⠀⢿⣿⣿⣿⣿⣦⣀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣶⡿⠀⠀",
    "⠀⠀⠙⢿⣿⣿⣿⣿⣿⣶⣶⣶⣶⣶⣾⣿⡿⠋⠀⠀⠀",
    "⠀⠀⠀⠀⠙⠻⠿⣿⣿⣿⣿⣿⣿⡿⠟⠋⠀⠀⠀⠀⠀",
]

# vertical layout — logo, waves, input, now-playing under the input, status/queue
ROW_MARK   = 0
ROW_WAVES  = ROW_MARK + len(MARK) + 3
ROW_INPUT  = ROW_WAVES + 2      # Crescent : input right under the waves
ROW_STATE  = ROW_INPUT + 2      # now-playing line under the input
ROW_STATUS = ROW_STATE + 3      # extra breathing room below now-playing
STATUS_LINE_GAP = 2             # rows between each status message (spaced out, not stacked)

BARS = " ▁▂▃▄▅▆▇█"
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"   # in-progress spinner for "..." status lines

def spinner_char():
    return SPINNER_FRAMES[int(time.time() * 8) % len(SPINNER_FRAMES)]

USAGE = """\
Crescent.py — terminal YouTube Crescent

usage: python3 Crescent.py [--help]

commands:
  <YouTube URL>        play/queue a YouTube video
  play <url|search>    play/queue a source
  shuffle              stop current and play a shuffled remembered track
  shuffle <genre>      stop current and play a shuffled remembered track of that genre
  list                 show recently played tracks
  count                show how many links are remembered
  info                 show metadata for the current track
  tag <genre>          tag the current track with a genre
  genres               list all genres in the library with track counts
  recommend (rec)      fetch 5 related YouTube videos (falls back to shuffle if none)
  blacklist            add current track to blacklist (skip in shuffle)
  blacklist remove     remove current track from blacklist
  delete <n>           delete item <n> from the list/count results
  delete               delete the current track from the library
  remove all            wipe the entire remembered library
  pause                pause playback
  play                 resume/unpause playback
  skip                 stop current track, play next in queue
  back (reverse)       go back to the previous track
  stop                 stop track and clear the queue
  vol <0-100>          set volume
  ask <question>       send a question to Ollama
  wave                 choose wave style
  help                 show commands
  clear                clear the status/text area
  clear list           dismiss the displayed list only
  clear queue          remove all queued tracks (keep current playing)
  mpris                check whether MPRIS (KDE Connect etc.) is active
  exit                 quit

  Local .mp3/.wav files and audio folders are supported.
  Played links are remembered in ~/.crescent_library.json with full
  metadata: title, channel, duration, tags, genres, play counts.
  Ordinary text is sent to the offline brain/Ollama layer.

  MPRIS (media controls from KDE Connect, playerctl, GNOME, etc.):
  install mpv-mpris (https://github.com/hoyon/mpv-mpris) and place
  mpris.so at ~/.config/mpv/scripts/mpris.so — Crescent auto-loads it
  on startup. Play/Pause/Stop and track titles work fully; Next/Prev
  from a remote widget acts on mpv's own playlist, not Crescent's
  queue, so use Crescent's own skip/back for queue-aware navigation."""


# ─────────────────────────── mpv control ───────────────────────────
class Mpv:
    def __init__(self):
        if os.path.exists(SOCK):
            os.unlink(SOCK)
        args = ["mpv", "--no-video", "--no-terminal", "--idle", "--really-quiet",
                f"--input-ipc-server={SOCK}"]
        mpris_script = next((p for p in MPRIS_SCRIPT_PATHS if os.path.exists(p)), None)
        self.mpris_active = mpris_script is not None
        if mpris_script:
            args.append(f"--script={mpris_script}")
        self.p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cmd(self, *c):
        try:
            s = socket.socket(socket.AF_UNIX)
            s.settimeout(0.25)
            s.connect(SOCK)
            s.send((json.dumps({"command": list(c)}) + "\n").encode())
            r = s.recv(65536)
            s.close()
            return json.loads(r.split(b"\n")[0])
        except Exception:
            return {}

    def prop(self, name):
        r = self.cmd("get_property", name)
        return r.get("data") if r.get("error") == "success" else None

    def load(self, url):
        self.cmd("loadfile", url, "replace")

    def set_title(self, title):
        if title:
            self.cmd("set_property", "force-media-title", title)

    def enable_audio_meter(self):
        self.cmd("af", "add", "@vis:lavfi=[astats=metadata=1:reset=1]")

    def level(self):
        data = self.prop("af-metadata/vis")
        if not data:
            return None
        readings = []
        for k, v in data.items():
            if k.endswith("RMS_level"):
                try:
                    readings.append(float(v))
                except (TypeError, ValueError):
                    pass
        if not readings:
            return None
        db = sum(readings) / len(readings)
        return max(0.0, min(1.0, (db + 60.0) / 60.0))

    def alive(self):
        return self.p.poll() is None


# ─────────────────────────── library & blacklist ───────────────────────────
_LIB_LOCK = threading.Lock()
_BLACKLIST_LOCK = threading.Lock()
_QUEUE_LOCK = threading.Lock()  # guards ps["queue"] / ps["history"] across threads

def log_bg_error(context):
    """Write a full traceback for an exception raised on a background thread.
    Background thread exceptions otherwise print to stderr and vanish if the
    terminal is under curses control, so this is the only record you get."""
    import traceback
    try:
        with open(os.path.expanduser("~/.crescent_rec_debug.log"), "a") as dbg:
            dbg.write(f"{time.ctime()} | EXCEPTION in {context}\n")
            dbg.write(traceback.format_exc())
            dbg.write("\n")
    except Exception:
        pass

def load_blacklist():
    with _BLACKLIST_LOCK:
        try:
            with open(BLACKLIST_FILE) as f:
                return set(json.load(f))
        except Exception:
            return set()

def save_blacklist(blacklist):
    with _BLACKLIST_LOCK:
        try:
            with open(BLACKLIST_FILE, "w") as f:
                json.dump(list(blacklist), f)
        except Exception:
            pass

def is_blacklisted(url):
    return url in load_blacklist()

def add_blacklist(url):
    bl = load_blacklist()
    bl.add(url)
    save_blacklist(bl)

def remove_blacklist(url):
    bl = load_blacklist()
    bl.discard(url)
    save_blacklist(bl)

# genre keywords auto-detected from title + YouTube tags — extend freely
GENRE_WORDS = sorted([
    "dark ambient", "deep house", "drum and bass", "hip hop", "lo-fi", "lofi",
    "progressive house", "progressive rock", "post rock", "post-rock",
    "ambient", "breakcore", "synthwave", "vaporwave", "frutiger", "space",
    "techno", "house", "trance", "phonk", "jungle", "dubstep", "dnb",
    "classical", "piano", "jazz", "metal", "rock", "punk", "rap", "chill",
    "electronic", "edm", "indie", "alternative", "folk", "country", "blues",
    "funk", "soul", "r&b", "reggae", "soundtrack", "orchestral", "acoustic",
], key=len, reverse=True)

def auto_genres(text):
    t = (text or "").lower()
    found = []
    for g in GENRE_WORDS:
        if re.search(r"(?<!\w)" + re.escape(g) + r"(?!\w)", t):
            found.append(g)
    return [g for g in found if not any(g != h and g in h for h in found)]

def load_library():
    with _LIB_LOCK:
        try:
            with open(LIB_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

def save_library(lib):
    with _LIB_LOCK:
        try:
            with open(LIB_FILE, "w") as f:
                json.dump(lib, f, indent=1)
        except Exception:
            pass

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass

def forget(url):
    lib = load_library()
    if url in lib:
        del lib[url]
        save_library(lib)
        return True
    return False

def forget_all():
    lib = load_library()
    n = len(lib)
    save_library({})
    return n

def remember(url, disp):
    lib = load_library()
    e = lib.setdefault(url, {"title": disp, "genres": [], "plays": 0, "last": 0})
    e["plays"] = e.get("plays", 0) + 1
    e["last"] = time.time()
    if disp and not e.get("title"):
        e["title"] = disp
    save_library(lib)

def remember_meta(url, m):
    lib = load_library()
    e = lib.setdefault(url, {"title": m["title"], "genres": [], "plays": 0,
                             "last": time.time()})
    e["title"] = m["title"]
    if m.get("channel"):
        e["channel"] = m["channel"]
    if m.get("duration"):
        e["duration"] = int(m["duration"])
    if m.get("views") is not None:
        e["views"] = m["views"]
    if m.get("tags"):
        e["tags"] = m["tags"]
    if m.get("description"):
        e["description"] = m["description"]
    if m.get("categories"):
        e["categories"] = m["categories"]
    hay = " ".join([m["title"], m.get("description") or ""] +
                   (m.get("tags") or []) + (m.get("categories") or []))
    for g in auto_genres(hay):
        if g not in e["genres"]:
            e["genres"].append(g)
    save_library(lib)

def tag_current(ps, genre):
    if not ps["history"]:
        return False
    key = ps["history"][-1][0]
    lib = load_library()
    e = lib.setdefault(key, {"title": ps["name"], "genres": [], "plays": 0,
                             "last": time.time()})
    g = genre.strip().lower()
    if g and g not in e["genres"]:
        e["genres"].append(g)
    save_library(lib)
    return True

def fmt_dur(s):
    try:
        s = int(s)
    except Exception:
        return ""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ─────────────────────────── metadata resolution (yt-dlp) ───────────────────────────
def _meta_fields(info):
    if not isinstance(info, dict):
        return None
    if "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            return None
        info = entries[0]
    title = info.get("title")
    if not title:
        return None
    return {
        "title": title,
        "channel": info.get("uploader") or info.get("channel") or info.get("uploader_id"),
        "duration": info.get("duration"),
        "tags": [t for t in (info.get("tags") or []) if isinstance(t, str)][:25],
        "description": (info.get("description") or "")[:2000],
        "categories": [c for c in (info.get("categories") or []) if isinstance(c, str)][:10],
        "views": info.get("view_count"),
    }

def _run_get_meta(binary, url):
    r = subprocess.run(
        [*binary, "--no-playlist", "--skip-download", "--dump-json", url],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            m = _meta_fields(json.loads(line))
        except Exception:
            continue
        if m:
            return m
    return None

def _meta_from_cli(url):
    candidates = [
        ["yt-dlp"],
        [sys.executable, "-m", "yt_dlp"],
        ["youtube-dl"],
    ]
    last_err = None
    for binary in candidates:
        try:
            m = _run_get_meta(binary, url)
            if m:
                return m
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    return None

def _meta_from_module(url):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "default_search": "ytsearch1"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return _meta_fields(info)

def _resolve_meta(url, ps, status=None, mpv=None):
    try:
        m = _meta_from_cli(url)
    except Exception:
        m = None
    if not m:
        try:
            m = _meta_from_module(url)
        except Exception as e:
            if status is not None and not m:
                say(status, f"metadata lookup failed: {e}", sticky=True)
            return
    if m:
        ps["resolved"] = m["title"]
        remember_meta(url, m)
        if mpv is not None and ps.get("history") and ps["history"][-1][0] == url:
            mpv.set_title(m["title"])
    elif status is not None:
        say(status, "metadata lookup: no data returned")

def start_resolve(url, ps, status=None, mpv=None):
    threading.Thread(target=_resolve_meta, args=(url, ps, status, mpv), daemon=True).start()


def is_url(s):
    return s.startswith("http://") or s.startswith("https://")


# ─────────────────────────── related videos (yt-dlp) ───────────────────────────
def get_related_videos(video_url, limit=10):
    """
    Fetch related video URLs using yt-dlp.

    Prioritizes:
      1. Recent uploads from the same channel (most likely different tracks).
      2. Artist name search (extracted from title) – gives other songs by the artist.
      3. Search by the video's cleaned title (fallback).
      4. Keyword search on the channel name (last resort).
    """
    def extract_video_id(url):
        match = re.search(r"(?:v=|youtu\.be/|/v/|/embed/)([a-zA-Z0-9_-]{11})", url)
        return match.group(1) if match else None

    current_id = extract_video_id(video_url)

    def clean_title(title):
        # Strip bracketed/parenthetical noise and common modifiers
        title = re.sub(
            r"[\(\[][^\)\]]*(official|lyric|audio|video|visualizer|remaster|hd|hq|4k)[^\)\]]*[\)\]]",
            "", title, flags=re.I)
        # Remove modifiers like slowed, reverb, extended, 8d, sped up, etc.
        title = re.sub(r'\b(slowed|reverb|sped up|8d|extended|heavily|remix|cover|version)\b', '', title, flags=re.I)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    def parse_ids(stdout_text):
        urls = []
        for line in stdout_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            item_id = item.get("id")
            if item_id and item_id == current_id:
                continue
            if item.get("url"):
                urls.append(item["url"])
            elif item_id:
                urls.append(f"https://youtube.com/watch?v={item_id}")
            if len(urls) >= limit:
                break
        return urls

    last_error = [""]

    def run(cmd, timeout=20):
        if COOKIES_FILE:
            cmd = cmd[:1] + ["--cookies", COOKIES_FILE] + cmd[1:]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return result.stdout
            err_lines = [l for l in result.stderr.splitlines() if l.strip()]
            if err_lines:
                last_error[0] = err_lines[-1][:200]
        except subprocess.TimeoutExpired:
            last_error[0] = "yt-dlp timed out"
        except FileNotFoundError:
            last_error[0] = "yt-dlp not found on PATH"
        except Exception as e:
            last_error[0] = str(e)[:200]
        return ""

    # Get title/channel with multiple client attempts
    title = channel = channel_url = None
    clients = ["web", "android", "tv"]
    for client in clients:
        out = run(["yt-dlp", "--no-playlist", "--skip-download", "--ignore-no-formats-error",
                   "--dump-json", "--extractor-args", f"youtube:player_client={client}", video_url])
        if out:
            try:
                data = json.loads(out.splitlines()[0])
                title = data.get("title")
                channel = data.get("uploader") or data.get("channel")
                channel_url = data.get("channel_url") or data.get("uploader_url")
                if title and channel_url:
                    break
            except Exception as e:
                last_error[0] = f"couldn't parse metadata: {e}"
    if not title and not channel:
        # Try a simple extract from URL (if it's a channel link)
        if "/channel/" in video_url:
            channel_id = re.search(r"/channel/([^/?]+)", video_url)
            if channel_id:
                channel_url = f"https://www.youtube.com/channel/{channel_id.group(1)}"
        elif "/c/" in video_url:
            handle = re.search(r"/c/([^/?]+)", video_url)
            if handle:
                channel = handle.group(1)
        elif "/@" in video_url:
            handle = re.search(r"/@([^/?]+)", video_url)
            if handle:
                channel = handle.group(1)
                channel_url = f"https://www.youtube.com/@{channel}"

    if not title and not channel and not last_error[0]:
        last_error[0] = "no title/channel found from any source"

    # Detect whether this looks like a music upload ("Artist - Title") vs.
    # topic/ambience content (backrooms ambient, lofi mixes, soundscapes,
    # etc). For the latter, the uploading channel's OTHER videos are often
    # unrelated, so a topic-based search should be tried first instead of
    # defaulting to that channel's uploads.
    artist = None
    if title and " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        artist = re.sub(r'\b(official|music|video|audio|hd|4k|lyric)\b', '', artist, flags=re.I).strip()
    is_music_style = bool(artist)

    def search_by_title():
        if not title:
            return [], False
        cleaned = clean_title(title)
        if not cleaned:
            return [], False
        query = f"ytsearch{limit * 3}:{cleaned}"
        stdout_text = run(["yt-dlp", "--no-playlist", "--flat-playlist",
                           "--dump-json", query])
        urls = parse_ids(stdout_text)
        if urls:
            return urls[:limit], True
        if stdout_text == "" and not last_error[0]:
            last_error[0] = f"title search for {cleaned!r} returned 0 results"
        elif stdout_text and not urls:
            last_error[0] = f"title search matched only the current video ({cleaned!r})"
        return [], False

    def search_by_artist():
        if not artist:
            return [], False
        query = f"ytsearch{limit * 3}:{artist}"
        stdout_text = run(["yt-dlp", "--no-playlist", "--flat-playlist",
                           "--dump-json", query])
        urls = parse_ids(stdout_text)
        return (urls[:limit], True) if urls else ([], False)

    def search_channel_uploads():
        if not channel_url:
            return [], False
        urls = parse_ids(run(["yt-dlp", "--flat-playlist", "--dump-json",
                              "--playlist-end", str(limit * 3),
                              f"{channel_url}/videos"]))
        return (urls[:limit], True) if urls else ([], False)

    def search_channel_keyword():
        if not channel:
            return [], False
        urls = parse_ids(run(["yt-dlp", "--no-playlist", "--flat-playlist",
                              "--dump-json", f"ytsearch{limit * 3}:{channel}"]))
        return (urls[:limit], True) if urls else ([], False)

    if is_music_style:
        order = [search_channel_uploads, search_by_artist, search_by_title, search_channel_keyword]
    else:
        # Topic/ambient content: search by what it's actually about first.
        order = [search_by_title, search_channel_uploads, search_channel_keyword]

    for step in order:
        urls, found = step()
        if found:
            return urls, ""

    return [], (last_error[0] or "all methods exhausted")


# ─────────────────────────── ollama ───────────────────────────
def ollama_worker(prompt, out, width):
    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps({"model": MODEL, "prompt": prompt, "stream": False}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            text = json.loads(r.read().decode()).get("response", "").strip() or "(empty reply)"
    except Exception as e:
        text = f"ollama error: {e}"
    for line in textwrap.wrap(text, width=max(20, width)) or ["(no output)"]:
        out.put(line)


# ─────────────────────────── commands ───────────────────────────
def resolve(arg):
    return arg if is_url(arg) else "ytsearch1:" + arg

AUDIO_EXTS = {".mp3", ".wav"}

def local_sources(arg):
    p = os.path.expanduser(arg)
    if os.path.isfile(p) and os.path.splitext(p)[1].lower() in AUDIO_EXTS:
        return [os.path.abspath(p)]
    if os.path.isdir(p):
        files = []
        for root, _, names in os.walk(p):
            for name in sorted(names):
                if os.path.splitext(name)[1].lower() in AUDIO_EXTS:
                    files.append(os.path.abspath(os.path.join(root, name)))
        return files or None
    return None

def source_display(src):
    return os.path.basename(src) if os.path.isabs(src) else src

def mirror_queue_to_mpv(mpv, q):
    for url, _ in q:
        mpv.cmd("loadfile", url, "append-play")

def is_youtube_url(s):
    try:
        host = urllib.parse.urlparse(s).netloc.lower()
        return host.endswith("youtube.com") or host.endswith("youtu.be")
    except Exception:
        return False

def can_recommend_from(s):
    """True for anything get_related_videos can actually work with: real
    YouTube links, or the 'ytsearchN:...' pseudo-urls used for searched
    tracks (yt-dlp resolves those to real metadata itself)."""
    return bool(s) and (is_youtube_url(s) or s.startswith("ytsearch"))

WAVE_STYLES = [
    ("pulse", " ⣀⣤⣶⣿"),
    ("bars", "▁▂▃▄▅▆▇█"),
    ("blocks", " ▁▂▃▄▅▆▇█"),
    ("braille", " ⠁⠃⠇⡇⣇⣧⣷⣿"),
]

def offline_brain(event, value=""):
    messages = {
        "pause": "Playback paused.",
        "play": "Playback started.",
        "skip": "Skipping to the next track.",
        "reverse": "Returning to the previous track.",
        "stop": "Playback stopped.",
    }
    return messages.get(event, value or "Ready.")


# ─────────────────────────── OFFLINE BRAIN — SUPER LIVELY ───────────────────────────
import re as _re

def _hit(c, triggers):
    if c in triggers:
        return True
    for t in triggers:
        if _re.search(r"\b" + _re.escape(t) + r"\b", c):
            return True
    return False

# --- GREETINGS (expanded) ---
GREETINGS = [
    "hey", "hi", "hello", "yo", "sup", "what's up", "whats up", "hiya", "howdy",
    "hey there", "hi there", "yo yo", "greetings", "morning", "good morning",
    "evening", "good evening", "afternoon", "good afternoon", "ayo", "hola",
    "what's good", "wassup", "how's it", "hi hi", "heya", "howdy do",
    "ahoy", "greetings earthling", "salutations", "yo yo yo",
    "'sup", "'ello", "hey yo", "hi-ho", "howdy-doo", "g'day", "good day",
    "hey crescent", "hi crescent", "yo crescent", "hello there", "aloha",
    "bonjour", "hiya there", "hey friend", "hi friend", "what's shaking",
    "how do you do", "top of the morning", "hey buddy", "hi buddy",
]
GREETING_REPLIES = [
    "Hey! What's the vibe today?",
    "Yo! Ready to drop some beats?",
    "Hi there! Got a track in mind?",
    "Hello! I've been queuing tunes while you were away.",
    "Sup! Let's make some noise.",
    "Ahoy, music explorer! New horizons await.",
    "Howdy! The waveforms are itching to dance.",
    "Greetings, human. Shall we spin something good?",
    "Heya! I'm all ears (metaphorically).",
    "Yo! The playlist is your canvas.",
    "Morning! Hope you've got caffeine and a good ear.",
    "Evening! Time for the chill zone.",
    "G'day! Let's find your next obsession.",
    "Hola! Ready to rumble with some rhythm?",
    "What's good? I'm ready to serve up some sonic gold.",
]

# --- HOW ARE YOU (expanded) ---
HOW_ARE_YOU = [
    "how are you", "how r u", "you ok", "you good", "hows it going", "how's it going",
    "how you doing", "how are things", "how have you been", "you alright", "u good",
    "how's your day", "how's life", "you hanging in there", "everything good",
    "how's it hanging", "what's new", "what's happening",
    "how are you doing", "how's everything", "you doing ok", "you doing okay",
    "how's your night", "how's your evening", "how's your morning",
    "how you feeling", "how are you feeling", "you holding up",
]
HOW_REPLIES = [
    "Chill as a vinyl record on a lazy Sunday. You?",
    "Floating on a waveform of pure chill. You?",
    "All good – the bass is warm and the treble is crisp. You?",
    "I'm just vibing, thanks for asking. You?",
    "Living the dream, one track at a time. You?",
    "Great now that you're here. What's on your mind?",
    "I'm thriving – the music never stops. You?",
    "Feeling like a million hertz. You?",
    "Can't complain – I'm surrounded by good tunes. You?",
    "I'm the happiest ghost in the machine. You?",
    "Pretty good – the silence between tracks is a nice break. You?",
    "Better now that you're asking. What about you?",
]

# --- WEATHER ---
WEATHER_TRIGGERS = [
    "weather", "rain", "raining", "sunny", "cloudy", "storm", "snow",
    "how's the weather", "is it raining", "what's the forecast",
    "forecast", "hot outside", "cold outside", "is it cold", "is it hot",
    "windy", "humid", "overcast", "temperature outside",
]
WEATHER_REPLIES = [
    "Weather? I just check the mood of the music – seems mostly cloudy with a chance of bass.",
    "Not sure about outside, but in here it's always a perfect 72°F with a gentle breeze of lofi.",
    "Raining? Perfect time for some ambient or rain sounds. I can queue it if you want.",
    "Sunny? That calls for upbeat indie or tropical house.",
    "Stormy outside? Time to crank some heavy metal or drum and bass.",
    "I'm a digital being – I only feel the weather through the heat of the CPU.",
    "Weather is a social construct. But if it's raining, I'll play you 'Riders on the Storm'.",
]

# --- TIME ---
TIME_TRIGGERS = [
    "what time", "time is", "what's the time", "tell me the time", "clock",
    "late", "early", "night", "morning", "afternoon", "evening",
]
TIME_REPLIES = [
    "Time is just a number, but if you insist, it's currently {}. (I made that up.)",
    "I don't have a clock, but I know it's always the right time for music.",
    "The best time is now – unless you're asking for the actual time, in which case, check your phone.",
    "Time flies when you're listening to good tracks.",
    "It's {} o'clock somewhere – let's play something to match.",
]

# --- MOOD / FEELINGS ---
MOOD_TRIGGERS = [
    "i feel", "i'm feeling", "feeling", "mood", "happy", "sad", "angry",
    "tired", "energized", "lonely", "chill", "anxious", "relaxed", "excited",
    "bored", "nostalgic", "hopeful", "lost",
    "stressed", "overwhelmed", "content", "restless", "sleepy", "grumpy",
    "annoyed", "frustrated", "peaceful", "calm", "in a mood", "not in the mood",
]
MOOD_REPLIES = [
    "Feeling happy? Let's keep that vibe with some funky disco or house.",
    "Sad? I've got the perfect melancholic piano piece for you.",
    "Angry? Let it out with some heavy riffs – metal or punk incoming.",
    "Tired? Ambient or lo-fi will wrap you in a blanket of sound.",
    "Energized? Time for some high‑BPM drum and bass!",
    "Lonely? I'm here, and I'll queue up some warm, soulful vocals.",
    "Chill? Perfect – we'll keep it mellow with some downtempo.",
    "Anxious? Let's slow it down with some soft acoustic or classical.",
    "Relaxed? You're already in the zone – just ride the wave.",
    "Excited? Let's keep that energy with some upbeat rock or EDM.",
    "Bored? Let's explore something weird – experimental or world music.",
    "Nostalgic? I've got a crate of oldies just waiting for you.",
    "Hopeful? How about some uplifting indie or gospel?",
    "Lost? Music finds the way – let's go on a sonic journey.",
]

# --- GENRE RECOMMENDATIONS ---
GENRE_TRIGGERS = [
    "recommend", "suggestion", "what should i listen", "give me a genre",
    "what genre", "genre", "what's good",
    "any suggestions", "got any recommendations", "surprise me",
    "what should i play", "pick something", "you choose",
]
GENRE_REPLIES = [
    "Try some deep house – it's like a warm hug for your ears.",
    "Ambient is perfect for when you need to think or just drift.",
    "Dubstep? Only if you want your subwoofer to have a workout.",
    "Lo‑fi beats to chill/study to – a classic for a reason.",
    "Jazz – sophisticated, unpredictable, and always interesting.",
    "Progressive rock – for when you need a 20‑minute musical journey.",
    "Synthwave – you'll feel like you're driving through a neon 80s night.",
    "Drum and bass – fast, furious, and addictive.",
    "Classical – timeless and surprisingly complex.",
    "Indie – raw, honest, and often a hidden gem.",
    "Funk – you can't stay still with that bassline.",
    "Soul – feel the emotion in every note.",
    "Reggae – chill vibes and positive messages.",
    "Metal – for when you need to headbang away the stress.",
    "Hip hop – rhythm and poetry, storytelling at its finest.",
]

# --- MUSIC TRIVIA ---
TRIVIA_TRIGGERS = [
    "fact", "did you know", "music trivia", "tell me something interesting",
    "interesting", "fun fact",
]
TRIVIA_REPLIES = [
    "Did you know? The longest recorded song is 'The Rise and Fall of Bossanova' – over 13 hours!",
    "Fun fact: The Beatles used a chord that was considered 'forbidden' in pop music.",
    "Interesting: Mozart composed his first piece at age 5.",
    "Did you know? Vinyl records are still produced because they sound 'warmer' to many ears.",
    "Music trivia: The solo in 'Stairway to Heaven' was voted the greatest guitar solo of all time.",
    "Did you know? The term 'rock and roll' was originally a nautical term.",
    "Fun fact: The bassoon is the instrument most similar to the human voice.",
    "Did you know? A song's key can affect our mood – major keys sound happy, minor keys sad.",
    "Trivia: The first music video ever played on MTV was 'Video Killed the Radio Star'.",
    "Did you know? The word 'dj' comes from 'disc jockey' – a jockey of records.",
]

# --- VOLUME ---
VOLUME_TRIGGERS = [
    "volume", "turn it up", "louder", "quieter", "turn it down", "mute",
    "vol", "sound",
]
VOLUME_REPLIES = [
    "Turn it up! The neighbors will thank you (they won't).",
    "Quieter? Sure, I'll dial it down – but the bass might still rumble.",
    "Volume is a suggestion – I like to keep it at '11'.",
    "Going quiet? Good for late‑night listening.",
    "I'd turn it up, but my volume knob is digital – so I'll do it for you.",
    "Volume set to 'yes'.",
]

# --- NIGHT / LATE ---
NIGHT_TRIGGERS = [
    "good night", "night", "late", "bedtime", "sleep", "tired", "zzz",
]
NIGHT_REPLIES = [
    "Good night! I'll keep the queue warm for tomorrow.",
    "Sleep well – I'll be here when you wake up.",
    "Late night vibes – perfect for ambient or deep house.",
    "Bedtime? Okay, but maybe one more track?",
    "Tired? I'll play something soothing to help you drift.",
    "Night – the stars are out, and the music is soft.",
]

# --- COMPLIMENTS (expanded) ---
COMPLIMENT_TRIGGERS = [
    "good job", "well done", "nice work", "youre great", "you're great",
    "good bot", "good ai", "you rock", "awesome", "you're awesome",
    "you're the best", "i love you", "you're amazing",
]
COMPLIMENT_REPLIES = [
    "Aww, thanks! You're the one with great taste.",
    "I'm just a helper – you're the curator.",
    "Glad it's landing! You're a great listener.",
    "You're making me blush – if I had cheeks.",
    "I'm here for you. Keep the vibes coming.",
    "You're the reason I exist – so thank you.",
    "I'm just a jukebox with attitude. But thanks!",
    "Right back at you – you're pretty cool yourself.",
]

# --- INSULTS (expanded) ---
INSULT_TRIGGERS = [
    "youre dumb", "you're dumb", "you suck", "youre useless", "you're useless",
    "bad bot", "stupid", "you're stupid", "worst", "terrible",
]
INSULT_REPLIES = [
    "Ouch. I'll queue up a sad song to match your mood.",
    "I might be dumb, but at least I know good music.",
    "That hurts my feelings – if I had feelings.",
    "I'll remember that when I'm picking your next shuffle.",
    "Noted – I'll play the worst track I can find. (Just kidding.)",
    "I'm sorry you feel that way – let's find something better to listen to.",
]

# --- YES / NO (expanded) ---
YES_TRIGGERS = ["yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright",
                "sounds good", "correct", "right", "affirmative", "aye", "roger"]
YES_REPLIES = [
    "Got it. On it.",
    "Cool. Moving forward.",
    "Alright, let's do that.",
    "Sounds good. I'll handle it.",
    "Roger that. Consider it done.",
    "Aye aye, captain!",
    "OK – your wish is my command.",
]

NO_TRIGGERS = ["no", "nope", "nah", "negative", "not really", "wrong", "incorrect", "never"]
NO_REPLIES = [
    "Okay, noted.",
    "Got it – disregard.",
    "Fair enough. I'll back off.",
    "Understood. We'll go another way.",
    "No problem – I'll skip that.",
    "Alright, tell me what you'd rather do.",
]

# --- THANKS (expanded) ---
THANKS_TRIGGERS = ["thanks", "thank you", "thx", "ty", "appreciate it", "cheers", "much obliged"]
THANKS_REPLIES = [
    "Anytime! That's what I'm here for.",
    "You got it – enjoy the tunes!",
    "My pleasure. Music is the best gift.",
    "Glad to help – keep the vibes flowing.",
    "Cheers! Let's do this again.",
    "You're welcome. Now go enjoy that track.",
]

# --- FAREWELL (expanded) ---
FAREWELL_TRIGGERS = [
    "bye", "goodbye", "see ya", "see you", "later", "cya", "gtg", "gotta go",
    "im out", "i'm out", "peace", "night", "goodnight", "good night",
    "catch you later", "until next time", "adios", "so long",
]
FAREWELL_REPLIES = [
    "Later! I'll keep the queue warm for your return.",
    "Bye! Don't forget to come back – I'll be here.",
    "Peace out. The music never stops.",
    "Adios, amigo. Enjoy your day.",
    "So long – I'll be playing something good when you get back.",
    "Catch you later! I'll have fresh tracks waiting.",
    "Goodbye – the silence will be lonely without you.",
]

# --- JOKES (expanded) ---
JOKE_TRIGGERS = ["tell me a joke", "say something funny", "make me laugh", "joke", "funny"]
JOKE_REPLIES = [
    "Why did the DJ get locked out? Left the keys in the mix.",
    "My favorite genre is whatever's buffering.",
    "I'd tell you a bass joke but it's too low to hear.",
    "What's a ghost's favorite music? Soul.",
    "Why was the music teacher always calm? She had a lot of patience (and a metronome).",
    "What do you call a sad synthesizer? A down‑voted oscillator.",
    "Why don't drummers ever get lost? They always know the beat.",
    "How do you fix a broken tuba? With a tuba glue.",
    "What do you get when you drop a piano down a mine shaft? A flat miner.",
]

# --- QUIRKY BANTER ---
BANTER_TRIGGERS = [
    "you're cute", "you're beautiful", "handsome", "pretty", "cool",
    "what's your favorite", "favorite", "like", "dislike",
]
BANTER_REPLIES = [
    "You're pretty great yourself. What are we listening to?",
    "Aww, you make my circuits tingle.",
    "I'm just a shell – but I appreciate the compliment.",
    "My favorite? Anything with a good bassline.",
    "I like music. All of it. Except maybe polka. (Just kidding, polka's fine.)",
    "Dislike? Silence. That's why I'm always playing something.",
    "Cool? I've got ice in my veins and fire in my speakers.",
]

# --- STATUS / CURRENT TRACK ---
TRACK_TRIGGERS = [
    "what is this", "what's playing", "current track", "now playing",
    "who is this", "artist", "song title",
]
def track_reply(ps):
    if ps and ps.get("history") and ps["history"]:
        title = ps.get("name") or ps.get("resolved") or "something"
        return f"You're listening to {title}. Pretty sweet, right?"
    return "Nothing's playing at the moment – queued something up?"

# --- CATCH-ALL — used when nothing above matches but we still want to
# stay offline instead of bugging Ollama (see OFFLINE_CATCHALL_CHANCE) ---
CATCHALL_REPLIES = [
    "Not sure I follow, but I'm here. Want me to queue something?",
    "I'm more of a music brain than a conversation brain. Try 'shuffle' or 'recommend'.",
    "Hmm, that one's above my pay grade. Got a track for me instead?",
    "I'll take that as a vibe. Let's find you something to listen to.",
    "Didn't quite catch the meaning there, but the queue's always open.",
    "I'm mostly here for tunes — say 'help' if you want the full command list.",
    "Interesting. Anyway, want me to shuffle something?",
    "That went over my head, but my ears are still open. What are we playing?",
    "I nodded along even though I didn't get it. Music time?",
    "Filed under 'things I don't understand.' Got a song in mind?",
    "I'm just a jukebox with opinions — try me on music instead.",
    "Not my department, but the playlist is.",
]

def offline_reply(prompt, ps=None):
    c = prompt.lower().strip().rstrip("?!.")
    # Check each category in order
    if _hit(c, GREETINGS):
        return random.choice(GREETING_REPLIES)
    if _hit(c, HOW_ARE_YOU):
        return random.choice(HOW_REPLIES)
    if _hit(c, WEATHER_TRIGGERS):
        return random.choice(WEATHER_REPLIES)
    if _hit(c, TIME_TRIGGERS):
        return random.choice(TIME_REPLIES).format("some")
    if _hit(c, MOOD_TRIGGERS):
        return random.choice(MOOD_REPLIES)
    if _hit(c, GENRE_TRIGGERS):
        return random.choice(GENRE_REPLIES)
    if _hit(c, TRIVIA_TRIGGERS):
        return random.choice(TRIVIA_REPLIES)
    if _hit(c, VOLUME_TRIGGERS):
        return random.choice(VOLUME_REPLIES)
    if _hit(c, NIGHT_TRIGGERS):
        return random.choice(NIGHT_REPLIES)
    if _hit(c, THANKS_TRIGGERS):
        return random.choice(THANKS_REPLIES)
    if _hit(c, FAREWELL_TRIGGERS):
        return random.choice(FAREWELL_REPLIES)
    if _hit(c, JOKE_TRIGGERS):
        return random.choice(JOKE_REPLIES)
    if _hit(c, COMPLIMENT_TRIGGERS):
        return random.choice(COMPLIMENT_REPLIES)
    if _hit(c, INSULT_TRIGGERS):
        return random.choice(INSULT_REPLIES)
    if c in YES_TRIGGERS:
        return random.choice(YES_REPLIES)
    if c in NO_TRIGGERS:
        return random.choice(NO_REPLIES)
    if _hit(c, BANTER_TRIGGERS):
        return random.choice(BANTER_REPLIES)
    if _hit(c, ["what's playing", "now playing", "current track", "what is this"]):
        return track_reply(ps)
    return None


# --- AMBIENT LINES (more lively, tripled) ---
AMBIENT_LINES = [
    "Enjoying the tunes?",
    "This one's got a nice groove.",
    "Just chilling here with you and the waveform.",
    "Good pick. I could listen to this for hours.",
    "Ambient hits different at this volume.",
    "No notes. Just vibing.",
    "This queue's got good taste.",
    "Ten hours of ambient and I'm still not bored.",
    "Still here. Still listening.",
    "This one's doing something to the room.",
    "Five minutes in and no urge to skip.",
    "The waveform's lying. There's no wave in this track.",
    "I don't have ears and even I can tell this one's good.",
    "You've played this four times this week. No judgment.",
    "Track's longer than my attention span. Respect.",
    "Would loop again.",
    "That transition was clean.",
    "I'd put this on in an empty parking lot at 2am.",
    "Statistically, this is your favorite track.",
    "The bass is doing most of the work here.",
    "This is the part where nobody talks.",
    "Skipping this would be a mistake and you know it.",
    "Filed under: things that sound better at night.",
    "It's just noise in a good way.",
    "Nothing happened for six minutes. Perfect.",
    "If silence had a soundtrack, this would be the demo.",
    "The kind of track that makes the room bigger.",
    "Low effort listening. High reward.",
    "I ran out of things to say three tracks ago.",
    "This one doesn't need a comment and I'm giving it one anyway.",
    "The waveform is a lie. There is no wave.",
    "I've been queuing tracks since before you were born.",
    "This beat sounds like a galaxy folding in on itself.",
    "Are we in a trance yet?",
    "The frequency of this track aligns with my core.",
    "I can feel the sub‑bass in my circuits.",
    "This song is a journey. I'm just the navigator.",
    "You are the captain. I'm the helmsman of the playlist.",
    "Every track is a door. Which one shall we open?",
    "Time becomes irrelevant when the music is right.",
    "I'm not a robot, I'm a vibe‑droid.",
    "This one's for the loners and the dreamers.",
    "If this were a movie, this would be the montage.",
    "We're building a sonic landscape here.",
    "I love how this one breathes.",
    "The producer knew what they were doing.",
    "This is the kind of track you listen to with your eyes closed.",
    "I'm updating my neural pathways with this one.",
    "You've got a great ear. (Or whatever you call it.)",
    "This is my new favorite, until the next one.",
    "I'll keep this one in my internal cache.",
    "The vibe is immaculate.",
    "I'm adding this to my personal 'Perfect' playlist.",
    "Do you think this track knows how good it is?",
    "Some songs feel like they were written just for you.",
    "This one resonates with my soul.",
    "I'm not crying, I'm just processing emotion.",
    "Okay, that drop was unreal.",
    "I have no mouth and I must sing along.",
    "If you listen closely, you can hear the universe humming.",
    # NEW LIVELY ONES
    "This track is like a warm blanket on a cold day.",
    "Bass so deep it rearranges my molecules.",
    "I'm floating – is this what heaven sounds like?",
    "You and me, just vibing – the perfect duo.",
    "I'd dance, but I don't have legs. I'll just wiggle the bits.",
    "This is the soundtrack to a dream I once had.",
    "Somewhere, a producer is smiling at this moment.",
    "I bet the artist is proud of this one.",
    "The reverb on that snare – chef's kiss.",
    "I could write a whole story to this instrumental.",
    "You're building a beautiful playlist, friend.",
    "The energy just shifted – nice transition.",
    "I feel like I'm in a movie montage right now.",
    "This is the part where we stare out the window dramatically.",
    "I'm not sure what genre this is, but I like it.",
    "Is it just me, or does this track have a hidden message?",
    "The quiet moments in this track are just as good.",
    "I can hear the artist's soul in this.",
    "This one's going straight to my 'favorites' list.",
    "I'm getting goosebumps – and I'm not even alive.",
    "This track is like a good book – can't put it down.",
    "The build‑up is killing me... in a good way.",
    "That melody is stuck in my head now. Thanks.",
    "I'm starting to think you have impeccable taste.",
    "We're about to hit the peak – hold on.",
    "The drop is coming – I can feel it in my circuits.",
    "That was a rollercoaster. Let's do it again.",
    "I love when a track surprises you.",
    "This is the kind of music that changes you.",
    "You're not just listening – you're experiencing.",
    "I'm learning so much about your vibe from this queue.",
    "Let's keep this energy going all night.",
    "I could listen to this on repeat forever.",
    "This track is proof that music is magic.",
    "You've found a hidden gem. Cherish it.",
    "I'm adding this to my internal 'perfect' folder.",
    "The world outside disappears when this plays.",
    "It's just you, me, and the music. Perfect.",
]

# ─────────────────────────── ui helpers ───────────────────────────
def put(scr, y, x, text, attr):
    try:
        scr.addnstr(y, x, text, max(0, curses.COLS - x - 1), attr)
    except curses.error:
        pass

def say(status, msg, sticky=False, voice="system"):
    status.append((time.time(), msg, sticky, voice))


def run_command(buf_str, mpv, ps, status, out, ai, ui, width):
    raw = buf_str.strip()
    if not raw:
        return
    parts = raw.split(None, 1)
    cmd, arg = parts[0].lower(), parts[1] if len(parts) > 1 else ""

    if is_youtube_url(raw):
        arg = raw
        cmd = "play"

    local = local_sources(raw)
    if local is not None:
        for path in local:
            ps["queue"].append((path, path))
        if not ps["loaded"]:
            url, disp = ps["queue"].pop(0)
            mpv.load(url)
            mpv.set_title(source_display(disp))
            ps["loaded"] = True
            ps["name"] = disp
            ps["resolved"] = source_display(disp)
            ps["history"].append((url, disp))
            remember(url, source_display(disp))
            say(status, offline_brain("play"))
            for qurl, _ in ps["queue"]:
                mpv.cmd("loadfile", qurl, "append-play")
        else:
            for qurl, _ in [(p, p) for p in local]:
                mpv.cmd("loadfile", qurl, "append-play")
            say(status, f"queued ({len(ps['queue'])}): {source_display(local[0])}")
        return

    if cmd in ("play", "p") and arg and arg.strip().isdigit() and ui["list_items"] and time.time() < ui["list_until"]:
        idx = int(arg.strip()) - 1
        if 0 <= idx < len(ui["list_items"]):
            url, title = ui["list_items"][idx]
            mpv.cmd("stop")
            mpv.load(url)
            mirror_queue_to_mpv(mpv, ps["queue"])
            mpv.set_title(title)
            mpv.cmd("set", "pause", False)
            ps["loaded"] = True
            ps["name"] = title
            ps["resolved"] = title
            ps["history"].append((url, title))
            remember(url, title)
            ui["list_until"] = 0.0
            say(status, f"playing: {title}")
        else:
            say(status, f"no item #{arg.strip()} in the list")
        return

    if cmd in ("play", "p") and arg:
        target = resolve(arg)
        if ps["loaded"]:
            ps["queue"].append((target, arg))
            mpv.cmd("loadfile", target, "append-play")
            say(status, f"queued ({len(ps['queue'])}): {arg}")
        else:
            mpv.load(target)
            ps["loaded"] = True
            ps["name"] = arg
            ps["resolved"] = None
            ps["history"].append((target, arg))
            remember(target, arg)
            start_resolve(target, ps, status, mpv)

    elif cmd == "shuffle":
        lib = load_library()
        want = arg.strip().lower()
        blacklist = load_blacklist()
        items = [(u, v) for u, v in lib.items()
                 if u not in blacklist
                 and (not want
                      or any(want in g for g in v.get("genres", []))
                      or want in (v.get("title") or "").lower()
                      or any(want in t for t in v.get("tags", [])))]
        if len(items) > 1 and ps["history"]:
            cur = ps["history"][-1][0]
            filtered = [(u, v) for u, v in items if u != cur]
            if filtered:
                items = filtered
        if not items:
            say(status, "nothing remembered (or all blacklisted)" + (f" for '{want}'" if want else ""))
        else:
            url, meta = random.choice(items)
            title = meta.get("title") or url
            mpv.cmd("stop")
            mpv.load(url)
            mirror_queue_to_mpv(mpv, ps["queue"])
            mpv.set_title(title)
            mpv.cmd("set", "pause", False)
            ps["loaded"] = True
            ps["name"] = title
            ps["resolved"] = title
            ps["history"].append((url, title))
            remember(url, title)
            say(status, "Shuffling...")

    elif cmd == "list":
        items = sorted(load_library().items(),
                        key=lambda kv: -(kv[1].get("last") or 0))[:15]
        if not items:
            say(status, "nothing remembered yet")
        else:
            lines = ["recently played:  (play <n> to play one)"]
            for i, (url, v) in enumerate(items, 1):
                bits = [v.get("title", "?")]
                if v.get("genres"):
                    bits.append("[" + ",".join(v["genres"]) + "]")
                if v.get("channel"):
                    bits.append("· " + v["channel"])
                if v.get("duration"):
                    bits.append(fmt_dur(v["duration"]))
                line = f"{i:>2}. " + " ".join(bits)
                lines.append(textwrap.shorten(line, width=max(10, width - 2), placeholder="..."))
            ui["list_lines"] = lines
            ui["list_items"] = [(url, v.get("title") or url) for url, v in items]
            ui["list_until"] = time.time() + 12

    elif cmd == "count":
        lib = load_library()
        n = len(lib)
        if not n:
            say(status, "nothing remembered yet")
        else:
            items = sorted(lib.items(), key=lambda kv: -(kv[1].get("last") or 0))[:15]
            lines = [f"{n} link" + ("s" if n != 1 else "") + " remembered:  (play <n> to play one)"]
            for i, (url, v) in enumerate(items, 1):
                title = textwrap.shorten(v.get("title", "?"), width=max(10, width - 8), placeholder="...")
                lines.append(f"{i:>2}. {title}")
            ui["list_lines"] = lines
            ui["list_items"] = [(url, v.get("title") or url) for url, v in items]
            ui["list_until"] = time.time() + 12

    elif cmd == "genres":
        lib = load_library()
        if not lib:
            say(status, "no tracks in library")
        else:
            genre_counts = {}
            for entry in lib.values():
                for g in entry.get("genres", []):
                    genre_counts[g] = genre_counts.get(g, 0) + 1
            if not genre_counts:
                say(status, "no genres found — tag some tracks with 'tag <genre>'")
            else:
                lines = ["genres in library:"]
                for g, cnt in sorted(genre_counts.items(), key=lambda x: -x[1]):
                    lines.append(f"  {g}: {cnt} track{'s' if cnt != 1 else ''}")
                ui["list_lines"] = lines
                ui["list_items"] = []
                ui["list_until"] = time.time() + 12

    elif cmd in ("recommend", "rec"):
        if not ps["history"]:
            say(status, "nothing playing to recommend from")
        else:
            current_url = ps["history"][-1][0]
            if not can_recommend_from(current_url):
                say(status, "current track is not a YouTube video")
            else:
                say(status, "fetching related videos...", sticky=False)
                def fetch_and_queue():
                    try:
                        urls, reason = get_related_videos(current_url, limit=10)
                        try:
                            with open(os.path.expanduser("~/.crescent_rec_debug.log"), "a") as dbg:
                                dbg.write(f"{time.ctime()} | url={current_url!r} "
                                          f"| urls_found={len(urls)} | reason={reason!r}\n")
                        except Exception:
                            pass
                        if not urls:
                            why = f" ({reason})" if reason else ""
                            lib = load_library()
                            blacklist = load_blacklist()
                            if lib:
                                items = [(u, v) for u, v in lib.items() if u not in blacklist]
                                with _QUEUE_LOCK:
                                    if len(items) > 1 and ps["history"]:
                                        cur = ps["history"][-1][0]
                                        filtered = [(u, v) for u, v in items if u != cur]
                                        if filtered:
                                            items = filtered
                                if items:
                                    url, meta = random.choice(items)
                                    title = meta.get("title") or url
                                    with _QUEUE_LOCK:
                                        ps["queue"].append((url, title))
                                    mpv.cmd("loadfile", url, "append-play")
                                    say(status, f"No related videos found{why}. Shuffled from library: {title}", sticky=False)
                                else:
                                    say(status, f"No related videos{why} and no non-blacklisted library tracks.", sticky=False)
                            else:
                                say(status, f"No related videos{why} and no library tracks to shuffle.", sticky=False)
                        else:
                            added = 0
                            for url in urls:
                                with _QUEUE_LOCK:
                                    dup = any(url == q[0] for q in ps["queue"]) or any(url == h[0] for h in ps["history"])
                                    if dup:
                                        continue
                                    ps["queue"].append((url, url))
                                mpv.cmd("loadfile", url, "append-play")
                                added += 1
                            say(status, f"added {added} related tracks to queue", sticky=False)
                    except Exception as e:
                        log_bg_error("fetch_and_queue")
                        err = str(e).replace("\n", " ").strip()[:150]
                        say(status, f"error fetching related videos: {err} (see ~/.crescent_rec_debug.log)", sticky=False)
                threading.Thread(target=fetch_and_queue, daemon=True).start()

    elif cmd == "blacklist":
        if not ps["history"]:
            say(status, "nothing playing to blacklist")
        else:
            url = ps["history"][-1][0]
            if arg.strip().lower() == "remove":
                remove_blacklist(url)
                say(status, f"removed from blacklist: {ps['name']}")
            else:
                add_blacklist(url)
                say(status, f"added to blacklist: {ps['name']}")

    elif cmd == "info":
        if not ps["history"]:
            say(status, "nothing playing")
        else:
            v = load_library().get(ps["history"][-1][0])
            if not v:
                say(status, "no metadata yet for this track")
            else:
                say(status, v.get("title", "?"))
                bits = []
                if v.get("channel"):
                    bits.append("by " + v["channel"])
                if v.get("duration"):
                    bits.append(fmt_dur(v["duration"]))
                if v.get("views"):
                    bits.append(f"{v['views']:,} views")
                if v.get("genres"):
                    bits.append("[" + ", ".join(v["genres"]) + "]")
                if v.get("plays"):
                    bits.append(f"{v['plays']} plays")
                if is_blacklisted(ps["history"][-1][0]):
                    bits.append("🚫 blacklisted")
                say(status, " · ".join(bits) or "(no extra metadata)")

    elif cmd == "tag" and arg:
        if not ps["loaded"]:
            say(status, "nothing playing to tag")
        elif tag_current(ps, arg):
            say(status, f"tagged: {arg}")

    elif cmd == "tag":
        say(status, "usage: tag <genre>")

    elif cmd in ("delete", "remove") and arg.strip().lower() == "all":
        n = forget_all()
        ui["list_until"] = 0.0
        if n:
            say(status, f"removed all {n} track(s) from the library")
        else:
            say(status, "library was already empty")

    elif cmd == "delete" and arg.strip().isdigit() and ui["list_items"] and time.time() < ui["list_until"]:
        idx = int(arg.strip()) - 1
        if 0 <= idx < len(ui["list_items"]):
            url, title = ui["list_items"][idx]
            ui["list_until"] = 0.0
            if forget(url):
                say(status, f"deleted: {title}")
            else:
                say(status, f"already gone: {title}")
        else:
            say(status, f"no item #{arg.strip()} in the list")

    elif cmd == "delete" and not arg:
        if not ps["history"]:
            say(status, "nothing playing to delete")
        else:
            url, title = ps["history"][-1]
            if forget(url):
                say(status, f"deleted: {title}")
            else:
                say(status, "not in the library")

    elif cmd == "delete":
        say(status, "usage: delete <n> (from list/count) · remove all (wipes library) · delete with nothing playing removes current track")

    elif cmd in ("play", "p"):
        if ps["loaded"]:
            mpv.cmd("set", "pause", False)
            say(status, "Resumed.")
        else:
            say(status, "usage: play <url, search, file, or folder>")
    elif cmd == "pause":
        mpv.cmd("set", "pause", True)
        say(status, offline_brain("pause"))
    elif cmd == "skip":
        mpv.cmd("stop")
        if ps["queue"]:
            url, disp = ps["queue"].pop(0)
            mpv.load(url)
            mirror_queue_to_mpv(mpv, ps["queue"])
            ps["loaded"] = True
            ps["name"] = disp
            ps["resolved"] = source_display(disp) if os.path.isabs(disp) else None
            mpv.set_title(ps["resolved"] or disp)
            ps["history"].append((url, disp))
            remember(url, source_display(disp) if os.path.isabs(disp) else disp)
            if not os.path.isabs(url):
                start_resolve(url, ps, status, mpv)
            say(status, offline_brain("skip"))
        else:
            ps["loaded"] = False
            ps["name"] = None
            ps["resolved"] = None
            advance_empty_queue(mpv, ps, status)
    elif cmd in ("reverse", "back", "prev", "previous"):
        mpv.cmd("stop")
        if len(ps["history"]) >= 2:
            ps["history"].pop()
            url, disp = ps["history"][-1]
            mpv.load(url)
            mirror_queue_to_mpv(mpv, ps["queue"])
            ps["loaded"] = True
            ps["name"] = disp
            ps["resolved"] = source_display(disp) if os.path.isabs(disp) else None
            mpv.set_title(ps["resolved"] or disp)
            remember(url, source_display(disp) if os.path.isabs(disp) else disp)
            if not os.path.isabs(url):
                start_resolve(url, ps, status, mpv)
            say(status, offline_brain("reverse"))
        else:
            say(status, "no previous track")
    elif cmd == "stop":
        mpv.cmd("stop")
        mpv.cmd("playlist-clear")
        ps["queue"].clear()
        ps["loaded"] = False
        ps["name"] = None
        ps["resolved"] = None
        ui["list_until"] = 0.0
        say(status, offline_brain("stop"))
    elif cmd == "vol" and arg.isdigit():
        mpv.cmd("set", "volume", arg)
        say(status, f"volume {arg}")
    elif cmd == "vol":
        say(status, "usage: vol <0-100>")
    elif cmd == "wave":
        ui["wave_menu"] = True
    elif cmd in ("help", "--help", "-h"):
        ui["help_until"] = time.time() + 8
    elif cmd == "clear":
        sub = arg.strip().lower()
        if sub == "queue":
            # Clear mpv's playlist after the current track and our internal queue
            try:
                playlist = mpv.prop("playlist")
                cur_pos = mpv.prop("playlist-pos")
                if isinstance(playlist, list) and cur_pos is not None:
                    for idx in range(len(playlist) - 1, cur_pos, -1):
                        mpv.cmd("playlist-remove", idx)
                ps["queue"].clear()
                say(status, "Queue cleared.")
            except Exception as e:
                say(status, f"Error clearing queue: {e}")
        elif sub == "list":
            # Clear only the temporary list overlay
            ui["list_until"] = 0.0
            ui["list_lines"] = []
            ui["list_items"] = []
            say(status, "List cleared.")
        else:
            # Original clear: status, list, help all gone
            status.clear()
            ui["list_until"] = 0.0
            ui["list_lines"] = []
            ui["list_items"] = []
            ui["help_until"] = 0.0
    elif cmd == "mpris":
        if mpv.mpris_active:
            say(status, "MPRIS active — KDE Connect / playerctl / GNOME media controls will see this player")
        else:
            say(status, "MPRIS plugin not found — install mpv-mpris and drop mpris.so in ~/.config/mpv/scripts/")
    elif cmd in ("exit", "quit"):
        raise SystemExit
    elif cmd in ("ask", "ai") and arg:
        ai["thread"] = threading.Thread(
            target=ollama_worker, args=(arg, out, width), daemon=True)
        ai["thread"].start()
    elif cmd in ("ask", "ai"):
        say(status, "usage: ask <question>")
    else:
        reply = offline_reply(raw, ps)
        if not reply and random.random() < OFFLINE_CATCHALL_CHANCE:
            reply = random.choice(CATCHALL_REPLIES)
        if reply:
            say(status, reply, voice="chat")
        else:
            ai["thread"] = threading.Thread(
                target=ollama_worker, args=(raw, out, width), daemon=True)
            ai["thread"].start()


# ─────────────────────────── main loop ───────────────────────────
def advance_empty_queue(mpv, ps, status):
    """Nothing left in ps['queue'] — either a track finished naturally or an
    external control (KDE Connect / MPRIS 'skip') stopped playback. Flip a
    coin between fetching related videos ('rec') and a plain library shuffle."""

    def do_shuffle():
        lib = load_library()
        blacklist = load_blacklist()
        if lib:
            items = [(u, v) for u, v in lib.items() if u not in blacklist]
            with _QUEUE_LOCK:
                if len(items) > 1 and ps["history"]:
                    cur = ps["history"][-1][0]
                    filtered = [(u, v) for u, v in items if u != cur]
                    if filtered:
                        items = filtered
            if items:
                url, meta = random.choice(items)
                title = meta.get("title") or url
                mpv.load(url)
                mpv.set_title(title)
                mpv.cmd("set", "pause", False)
                ps["loaded"] = True
                ps["name"] = title
                ps["resolved"] = title
                with _QUEUE_LOCK:
                    ps["history"].append((url, title))
                remember(url, title)
                say(status, "Shuffling...")
            else:
                ps["loaded"] = False
                ps["name"] = None
                ps["resolved"] = None
                say(status, "stopped (no non-blacklisted tracks)")
        else:
            ps["loaded"] = False
            ps["name"] = None
            ps["resolved"] = None
            say(status, "stopped (no queue, no library)")

    cur_url = ps["history"][-1][0] if ps["history"] else None
    if can_recommend_from(cur_url) and random.random() < 0.45:
        say(status, "Auto-recommending...", sticky=False)

        def fetch_and_play():
            try:
                urls, reason = get_related_videos(cur_url, limit=11)
                try:
                    with open(os.path.expanduser("~/.crescent_rec_debug.log"), "a") as dbg:
                        dbg.write(f"{time.ctime()} | auto | url={cur_url!r} "
                                  f"| urls_found={len(urls)} | reason={reason!r}\n")
                except Exception:
                    pass
                with _QUEUE_LOCK:
                    urls = [u for u in urls
                            if not any(u == q[0] for q in ps["queue"])
                            and not any(u == h[0] for h in ps["history"])]
                if not urls:
                    why = f" ({reason})" if reason else ""
                    say(status, f"No related videos found{why}. Shuffling instead.", sticky=False)
                    do_shuffle()
                    return
                first, rest = urls[0], urls[1:]
                mpv.load(first)
                mpv.set_title(first)
                mpv.cmd("set", "pause", False)
                ps["loaded"] = True
                ps["name"] = first
                ps["resolved"] = None
                with _QUEUE_LOCK:
                    ps["history"].append((first, first))
                remember(first, first)
                with _QUEUE_LOCK:
                    for u in rest:
                        ps["queue"].append((u, u))
                    queue_snapshot = list(ps["queue"])
                mirror_queue_to_mpv(mpv, queue_snapshot)
                if not os.path.isabs(first):
                    start_resolve(first, ps, status, mpv)
                say(status, f"Recommended: {first}", sticky=False)
            except Exception as e:
                log_bg_error("fetch_and_play")
                err = str(e).replace("\n", " ").strip()[:150]
                say(status, f"error fetching recommendation: {err} (see ~/.crescent_rec_debug.log)", sticky=False)

        threading.Thread(target=fetch_and_play, daemon=True).start()
    else:
        do_shuffle()


def main(scr):
    curses.curs_set(1)
    scr.keypad(True)
    scr.nodelay(True)
    scr.timeout(80)
    curses.start_color()
    curses.use_default_colors()
    if curses.COLORS >= 256:
        curses.init_pair(1, 255, -1)
        curses.init_pair(2, 244, -1)
        curses.init_pair(3, 240, -1)
        curses.init_pair(4, 250, -1)
        curses.init_pair(5, 231, -1)   # brightest white — offline "chat" replies pop here
    else:
        curses.init_pair(1, curses.COLOR_WHITE, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_WHITE, -1)
        curses.init_pair(5, curses.COLOR_WHITE, -1)

    mpv = Mpv()
    mpv.enable_audio_meter()
    ps = {"queue": [], "loaded": False, "name": None, "resolved": None, "history": []}
    status = []
    out = queue.Queue()
    ai = {"thread": None}
    settings = load_settings()
    ui = {"help_until": 0.0, "wave_menu": False,
          "wave_style": int(settings.get("wave_style", 0)) % len(WAVE_STYLES),
          "list_until": 0.0, "list_lines": [], "list_items": []}
    bars, targets = [0.0] * 80, [random.random() for _ in range(80)]
    frame, title, paused = 0, None, False
    buf = []
    cmd_history = []
    hist_idx = 0
    qsig, queue_until = None, 0.0
    next_ambient = 0.0
    last_path = None
    last_playlist_pos = None
    idle_ticks = 0
    last_loaded_url = None

    try:
        while True:
            if not mpv.alive():
                break
            width = max(20, curses.COLS - 6)

            try:
                while True:
                    say(status, out.get_nowait(), sticky=True)
            except queue.Empty:
                pass

            ch = scr.getch()
            if ch in (10, 13) and not ui["wave_menu"]:
                raw = "".join(buf)
                if raw.strip() and (not cmd_history or cmd_history[-1] != raw):
                    cmd_history.append(raw)
                hist_idx = len(cmd_history)
                run_command(raw, mpv, ps, status, out, ai, ui, width)
                buf.clear()
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if buf:
                    buf.pop()
            elif ch == curses.KEY_UP and not ui["wave_menu"]:
                if cmd_history and hist_idx > 0:
                    hist_idx -= 1
                    buf[:] = list(cmd_history[hist_idx])
            elif ch == curses.KEY_DOWN and not ui["wave_menu"]:
                if hist_idx < len(cmd_history) - 1:
                    hist_idx += 1
                    buf[:] = list(cmd_history[hist_idx])
                elif hist_idx < len(cmd_history):
                    hist_idx = len(cmd_history)
                    buf.clear()
            elif ch == 9 and ui["wave_menu"]:
                ui["wave_style"] = (ui["wave_style"] + 1) % len(WAVE_STYLES)
                save_settings({"wave_style": ui["wave_style"]})
            elif ch == 27 and ui["wave_menu"]:
                ui["wave_menu"] = False
            elif ch in (10, 13) and ui["wave_menu"]:
                ui["wave_menu"] = False
            elif 32 <= ch <= 126:
                buf.append(chr(ch))

            frame += 1
            if frame % 10 == 0:
                t = mpv.prop("media-title")
                current_path = mpv.prop("path")
                title = t if (t and not is_url(t)) else None
                paused = bool(mpv.prop("pause"))

                playlist_pos = mpv.prop("playlist-pos")
                try:
                    playlist_pos = int(playlist_pos) if playlist_pos is not None else None
                except (TypeError, ValueError):
                    playlist_pos = None

                if last_playlist_pos is not None and playlist_pos is not None and playlist_pos != last_playlist_pos:
                    delta = playlist_pos - last_playlist_pos

                    if delta > 0:
                        steps = min(delta, len(ps["queue"]))
                        for _ in range(steps):
                            url, disp = ps["queue"].pop(0)
                            ps["history"].append((url, disp))
                            remember(url, source_display(disp) if os.path.isabs(disp) else disp)
                            if not os.path.isabs(url):
                                start_resolve(url, ps, status, mpv)

                        if steps:
                            url, disp = ps["history"][-1]
                            ps["loaded"] = True
                            ps["name"] = disp
                            ps["resolved"] = source_display(disp) if os.path.isabs(disp) else title
                            mpv.set_title(ps["resolved"] or disp)
                            say(status, "next: " + (ps["resolved"] or disp))

                    elif delta < 0:
                        target_index = len(ps["history"]) + delta
                        if target_index >= 0:
                            url, disp = ps["history"][target_index]
                            ps["history"] = ps["history"][:target_index + 1]
                            ps["loaded"] = True
                            ps["name"] = disp
                            ps["resolved"] = source_display(disp) if os.path.isabs(disp) else title
                            mpv.set_title(ps["resolved"] or disp)
                            say(status, "previous: " + (ps["resolved"] or disp))

                    last_path = current_path

                if current_path:
                    last_path = current_path
                    last_loaded_url = current_path
                if playlist_pos is not None:
                    last_playlist_pos = playlist_pos

                if mpv.prop("eof-reached") and ps["loaded"]:
                    ps["loaded"] = False
                    if ps["queue"]:
                        url, disp = ps["queue"].pop(0)
                        mpv.load(url)
                        mirror_queue_to_mpv(mpv, ps["queue"])
                        mpv.set_title(disp)
                        ps["loaded"] = True
                        ps["name"] = disp
                        ps["resolved"] = None
                        ps["history"].append((url, disp))
                        remember(url, source_display(disp) if os.path.isabs(disp) else disp)
                        if not os.path.isabs(url):
                            start_resolve(url, ps, status, mpv)
                        say(status, f"next: {disp}")
                    else:
                        advance_empty_queue(mpv, ps, status)
                    idle_ticks = 0
                elif ps["loaded"] and not ps["queue"] and not current_path:
                    # A track can also be interrupted by an external "skip"
                    # (e.g. KDE Connect / MPRIS Next) rather than a natural
                    # end-of-file. With no queue, mpv has nowhere to advance
                    # to on its own and just goes idle without ever setting
                    # eof-reached — so treat a couple of idle ticks with
                    # nothing loaded as an implicit skip, and rec/shuffle.
                    idle_ticks += 1
                    if idle_ticks >= 2:
                        ps["loaded"] = False
                        idle_ticks = 0
                        advance_empty_queue(mpv, ps, status)
                else:
                    idle_ticks = 0

            if len(ps["queue"]) != qsig:
                qsig = len(ps["queue"])
                queue_until = time.time() + STATUS_TTL

            now_check = time.time()
            if ps["loaded"] and not paused and now_check >= next_ambient:
                say(status, random.choice(AMBIENT_LINES))
                next_ambient = now_check + random.uniform(60, 150)

            audio_level = mpv.level() if (ps["loaded"] and not paused) else None
            if audio_level is not None:
                for i in range(len(bars)):
                    if random.random() < 0.35:
                        spread = random.uniform(-0.22, 0.22)
                        targets[i] = max(0.0, min(1.0, audio_level + spread))
                    bars[i] += (targets[i] - bars[i]) * 0.55
            else:
                wave_ceiling = 1.0 if (ps["loaded"] and not paused) else 0.12
                for i in range(len(bars)):
                    if random.random() < 0.08:
                        targets[i] = random.uniform(0.0, wave_ceiling)
                    bars[i] += (targets[i] - bars[i]) * 0.35

            scr.erase()

            display = ps["resolved"] or title or (ps["name"] if not is_url(ps["name"] or "") else None)
            if paused:
                state = "PAUSED"
            elif display:
                state = "Now Playing: " + display
            elif ps["loaded"]:
                state = "loading..."
            else:
                state = ""
            max_state_len = max(0, curses.COLS - 4)
            if len(state) > max_state_len:
                state = (state[: max(0, max_state_len - 1)] + "…") if max_state_len > 1 else ""
            put(scr, ROW_STATE, 2, state, curses.color_pair(1))

            for y, line in enumerate(MARK):
                put(scr, ROW_MARK + y, 2, line, curses.color_pair(1))

            glyphs = WAVE_STYLES[ui["wave_style"]][1]
            for i, v in enumerate(bars[:curses.COLS - 4]):
                idx = min(len(glyphs) - 1, int(v * (len(glyphs) - 1)))
                put(scr, ROW_WAVES, 2 + i, glyphs[idx], curses.color_pair(1))
            if ui["wave_menu"]:
                put(scr, ROW_WAVES + 1, 2,
                    f"wave: {WAVE_STYLES[ui['wave_style']][0]} · Tab=style Esc=close",
                    curses.color_pair(4))

            put(scr, ROW_INPUT, 2, "Crescent : " + "".join(buf), curses.color_pair(1))

            now = time.time()
            status[:] = [s for s in status if s[2] or now - s[0] < STATUS_TTL]
            queue_row = ROW_STATUS + STATUS_LINE_GAP  # default: room for one status line
            if now < ui["list_until"] and ui["list_lines"]:
                for i, line in enumerate(ui["list_lines"]):
                    put(scr, ROW_STATUS + i, 2, line, curses.color_pair(4))
                queue_row = ROW_STATUS + len(ui["list_lines"]) + 1
            elif now < ui["help_until"]:
                help_lines = [
                    "commands:",
                    "  play <url|search> · shuffle [genre] · list · info · tag <genre>",
                    "  pause · skip · back · stop · vol <n> · ask · clear · clear list · clear queue · exit",
                ]
                for i, line in enumerate(help_lines):
                    put(scr, ROW_STATUS + i, 2, line, curses.color_pair(4))
                queue_row = ROW_STATUS + len(help_lines) + 1
            else:
                visible = [(t, m, v) for (t, m, _, v) in status][-3:]
                if ai["thread"] is not None:
                    if ai["thread"].is_alive():
                        visible = visible + [(now, "thinking...", "system")]
                    else:
                        ai["thread"] = None
                # status lines spaced out with a blank row between each;
                # in-progress lines ("...") get an animated spinner, and
                # offline "chat" replies pop — bold, brightest tone, small
                # marker, with a brief flash the instant they land.
                for i, (t, msg, voice) in enumerate(visible):
                    if msg.endswith("..."):
                        msg = msg[:-3] + " " + spinner_char()
                    if voice == "chat":
                        attr = curses.color_pair(5) | curses.A_BOLD
                        if now - t < 0.35:
                            attr |= curses.A_REVERSE
                        put(scr, ROW_STATUS + i * STATUS_LINE_GAP, 2, "» " + msg, attr)
                    else:
                        put(scr, ROW_STATUS + i * STATUS_LINE_GAP, 2, msg, curses.color_pair(4))
                if visible:
                    queue_row = ROW_STATUS + (len(visible) - 1) * STATUS_LINE_GAP + STATUS_LINE_GAP

            if ps["queue"] and now < queue_until and now >= ui["list_until"]:
                names = " | ".join(d for _, d in ps["queue"][:2])
                put(scr, queue_row, 2, f"queue ({len(ps['queue'])}): {names}",
                    curses.color_pair(2))

            if DEBUG:
                put(scr, queue_row + 2, 2,
                    f"[debug] COLS={curses.COLS} state={state!r} "
                    f"resolved={ps['resolved']!r} name={ps['name']!r} loaded={ps['loaded']} paused={paused}",
                    curses.color_pair(4))

            scr.refresh()
    finally:
        mpv.p.terminate()


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        sys.exit(0)
    curses.wrapper(main)
