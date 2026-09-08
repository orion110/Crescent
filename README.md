# Crescent — Terminal Music Player 

**Crescent** is a command-driven, terminal-based music player that lives in your terminal. 

It plays YouTube videos (audio only), local `.mp3`/`.wav` files. 

It remembers every track you play, automatically enriches them with metadata (title, channel, duration, tags, genres), and learns your taste over time.

But Crescent is not just a jukebox – it’s a **companion**. 

It talks back with a lively offline brain, can answer questions via **Ollama**, shuffles intelligently, recommends related tracks, and even auto‑plays when the queue runs dry.

It integrates with **MPRIS** (KDE Connect, GNOME media controls, `playerctl`) and shows a real‑time audio waveform in your terminal.

---

## Features

- **Play anything** – YouTube URLs, search queries (`play <search>`), local files/folders.
- **Queue** – Add tracks to a queue; the queue persists across tracks.
- **Library** – Every played track is stored in `~/.crescent_library.json` with metadata, play counts, and last‑played time.
- **Auto‑metadata** – Uses `yt‑dlp` or `youtube‑dl` to fetch title, channel, duration, tags, categories, and description.
- **Genres** – Automatically detects genres from title/description, and you can manually tag tracks (`tag <genre>`).
- **Shuffle** – `shuffle` picks a random track from your library (optionally filtered by genre).
- **Recommendations** – `recommend` fetches 5 related videos using smart strategies (same channel, artist search, title search).
- **Blacklist** – Skip tracks you never want to hear again in shuffle.
- **Offline Brain** – Chat naturally – Crescent responds to greetings, moods, weather, time, jokes, compliments, and more without calling Ollama.
- **Ollama integration** – `ask <question>` sends your prompt to a local Ollama model (default `qwen2:0.5b`).
- **MPRIS** – Automatically loads `mpv‑mpris` if installed, so KDE Connect, GNOME, or `playerctl` can control playback.
- **Waveform display** – A real‑time audio level visualisation in four styles (pulse, bars, blocks, braille).
- **Command history** – Arrow up/down recalls previous commands.
- **Persistent settings** – Wave style and other preferences saved in `~/.crescent_settings.json`.

---

## Installation

### Prerequisites

- Python 3.6+ (with `curses` support – available on Linux, macOS, and Windows via Cygwin/WSL)
- **mpv** – the media player backend
- **yt-dlp** or **youtube-dl** – for metadata and recommendations (optional but recommended)
- **Ollama** (optional) – for AI chat integration

### Steps

1. Clone or download `Crescent.py` to your machine.
2. Make it executable:
   ```bash
   chmod +x Crescent.py
   ```
3. Install dependencies:
   ```bash
   pip install yt-dlp   # or youtube-dl
   ```
4. (Optional) Install `mpv-mpris` for MPRIS support:
   ```bash
   # For Debian/Ubuntu:
   sudo apt install mpv-mpris
   # Or build from source:
   git clone https://github.com/hoyon/mpv-mpris
   cd mpv-mpris
   make
   cp mpris.so ~/.config/mpv/scripts/
   ```

---

## Usage

Run the player in your terminal:

```bash
./Crescent.py
```

You'll see the Crescent logo, a waveform, and a prompt:

```
Crescent : _
```

Type commands and press Enter. Arrow keys navigate command history.

---

## Commands

| Command | Description |
|---------|-------------|
| `<YouTube URL>` | Play/queue a video. |
| `play <url\|search>` | Play a URL or a YouTube search (e.g., `play lofi chill`). |
| `shuffle [genre]` | Stop current and play a random remembered track (optionally by genre). |
| `list` | Show 15 most recently played tracks (with numbers). |
| `count` | Show total number of remembered links and list the 15 most recent. |
| `info` | Show detailed metadata for the current track. |
| `tag <genre>` | Tag the current track with a genre. |
| `genres` | List all genres in the library with track counts. |
| `recommend` / `rec` | Fetch 5 related YouTube videos and queue them (fallback to shuffle). |
| `blacklist` | Add the current track to the blacklist (skipped in shuffle). |
| `blacklist remove` | Remove the current track from the blacklist. |
| `delete <n>` | Delete track number `n` from the list/count results. |
| `delete` | Delete the current track from the library. |
| `remove all` | Wipe the entire library. |
| `pause` / `play` | Pause / resume playback. |
| `skip` | Stop current, play the next in queue. |
| `back` / `reverse` / `prev` | Go back to the previous track. |
| `stop` | Stop playback and clear the queue. |
| `vol <0-100>` | Set volume. |
| `ask <question>` | Send a question to Ollama. |
| `wave` | Enter the wave‑style selection menu (Tab to cycle, Enter/Esc to close). |
| `help` | Show a quick command overview. |
| `clear` | Clear status, list, and help overlays. |
| `clear list` | Dismiss only the displayed list (from `list`/`count`/`genres`). |
| `clear queue` | Remove all queued tracks without stopping the current one. |
| `mpris` | Check if MPRIS is active. |
| `exit` / `quit` | Quit Crescent. |

---

## Configuration

### Files

| File | Purpose |
|------|---------|
| `~/.crescent_library.json` | The main track database (metadata, play counts, genres, etc.). |
| `~/.crescent_blacklist.json` | List of URLs to skip in shuffle. |
| `~/.crescent_settings.json` | UI settings (currently only wave style). |
| `~/.crescent_cookies.txt` | Optional Netscape‑format cookies file for YouTube authentication. |
| `/tmp/play-mpv.sock` | IPC socket used to communicate with mpv. |
| `~/.crescent_rec_debug.log` | Log file for debugging recommendation errors. |

### Environment Variables

- `OLLAMA_URL` – default `http://127.0.0.1:11434/api/generate`
- `MODEL` – default `qwen2:0.5b` (change to any model from `ollama list`)

You can edit these at the top of `Crescent.py` or set them in your shell.

---

## Offline Brain

Every non‑command input is first checked against a large set of **trigger patterns** (greetings, mood, weather, etc.). If a match is found, a hand‑crafted reply is shown immediately (no network).  
If no pattern matches and the random chance `OFFLINE_CATCHALL_CHANCE` (default 0.65) says “stay offline”, a canned catch‑all reply is used. Otherwise, the input is sent to **Ollama** (running locally) in a background thread, and the response appears in the status area.

### Example conversational interactions

- `Hey Crescent` → “Hey! What's the vibe today?”
- `How are you?` → “Chill as a vinyl record on a lazy Sunday. You?”
- `Tell me a joke` → “Why did the DJ get locked out? Left the keys in the mix.”
- `I'm feeling sad` → “Sad? I've got the perfect melancholic piano piece for you.”
- `What's the weather like?` → “Weather? I just check the mood of the music – seems mostly cloudy with a chance of bass.”

---

## How It Works

- **mpv backend** – Crescent launches `mpv` with an IPC socket and sends JSON‑RPC commands to control playback.
- **Metadata & recommendations** – `yt-dlp` (or `youtube-dl`) fetches metadata and related videos in background threads.
- **Library** – JSON file stores all played tracks with rich metadata.
- **UI** – Built with Python `curses` – logo, waveform, input line, status area, and overlays.
- **Automatic queueless behaviour** – When the current track ends and the queue is empty, Crescent flips a coin (45% chance auto‑recommend, 55% chance library shuffle) to keep music flowing.
- **MPRIS** – If `mpv-mpris` is installed, Crescent loads it, making the player visible to system media controls.

---

## Customization

- **Wave styles** – Choose from `pulse`, `bars`, `blocks`, `braille` via the `wave` command.
- **Model** – Change the `MODEL` variable at the top of the script to use a different Ollama model.
- **Catch‑all chance** – Adjust `OFFLINE_CATCHALL_CHANCE` (0.0–1.0) to control how often unrecognised chat is handled offline vs. sent to Ollama.

---

## Troubleshooting

- **`mpv` not found** – Install mpv: `sudo apt install mpv` (Debian/Ubuntu) or `brew install mpv` (macOS).
- **`yt-dlp` not found** – Install via pip: `pip install yt-dlp`.
- **MPRIS not working** – Ensure `mpv-mpris.so` is in `~/.config/mpv/scripts/` and restart Crescent.
- **Waveform not moving** – Check if audio is playing and the mpv `af` filter is enabled (it is by default).
- **Ollama not responding** – Verify Ollama is running (`ollama serve`) and the model is installed (`ollama pull qwen2:0.5b`).

---

## License

This project is provided as-is. You are free to use, modify, and distribute it for personal or non‑commercial purposes. Attribution is appreciated but not required.




Enjoy the music! 🎵
