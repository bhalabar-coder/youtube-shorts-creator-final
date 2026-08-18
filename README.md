# AI YouTube Shorts Generator

Fully free pipeline: Ollama (local LLM) → edge-tts (voice) → faster-whisper
(captions) → Pexels/Pixabay (stock media) → MoviePy (render) → YouTube API
(upload).

## Setup

1. `pip install -r requirements.txt`
2. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3.2`
3. Get a free Pexels key at https://www.pexels.com/api/ (required).
   Optionally get a free Pixabay key at https://pixabay.com/api/docs/ for
   wider topic coverage.
4. Copy `.env.example` to `.env` and fill in your keys.
5. Put your YouTube OAuth `client_secret.json` in `credentials/`
   (create it in Google Cloud Console → APIs & Services → Credentials →
   OAuth client ID → Desktop app).
6. Run `python setup_youtube_auth.py` once — this opens a browser for
   login and caches a token so future runs don't need one.
7. Run `python main.py`.

Useful flags:
- `python main.py --category "space and astronomy"` — force a category
- `python main.py --topic "Why do cats purr?"` — skip topic generation
- `python main.py --no-upload` — render locally without uploading

## What changed from the original version

**Security**
- Removed hardcoded Pexels API keys from `image_agent.py` and
  `config.py` (they were committed in plain text). Keys now come from
  a `.env` file that's git-ignored. **Rotate that old key on Pexels —
  it was exposed in the files you shared.**
- Deleted `image_agent.py` — it was dead code using a separate
  `pexels_api` package that isn't part of the pipeline, duplicated
  `media_agent.py`, and was the one hardcoding the leaked key.

**Bug fix**
- `MODEL_NAME = "gemma4:e4b"` in the original `config.py` isn't a real
  Ollama model tag and would fail every request. Default is now
  `llama3.2` (fast, free, good enough for short scripts); override via
  `.env`.

**Topic variety** (your main ask)
- Added `TOPIC_CATEGORIES` in `config.py` — 18 categories (space,
  ocean life, dinosaurs, history, geography, chemistry, mythology,
  inventions, weird facts, etc.) instead of always landing on
  "science, animals, space or nature."
- `topic_agent.py` now rotates categories, avoiding whatever was used
  in the last few runs, and keeps a rolling history
  (`output/topic_history.json`) of past topics that it feeds back into
  the prompt so the model doesn't regenerate the same idea. This is
  the main lever for "vast variety" — right now if you run this daily
  it'll likely repeat itself within a week.
- `AUDIENCE` is now a config value instead of hardcoded into every
  prompt, so you can point the same pipeline at a different channel/
  age group without touching agent code.

**More topics = more media coverage**
- `media_agent.py` now falls back to Pixabay (also free) when Pexels
  has nothing for a query. Niche topics (say, "how volcanoes formed
  the moon") are far more likely to find usable footage this way.

**Reliability**
- Added retries with backoff to every Ollama call (`topic_agent.py`,
  `script_agent.py`, `scene_agent.py`) and to `voice_agent.py` — these
  were the most likely points of silent failure in an unattended run.
- `scene_agent.py` now raises a clear error instead of crashing
  opaquely when the model doesn't return valid JSON.

**Automation-friendliness**
- `youtube_agent.py` now caches the OAuth token
  (`credentials/token.json`) after the first login and refreshes it
  automatically. The original always called `run_local_server()`,
  meaning every single run — even from a cron job — would try to pop
  open a browser and hang. Added `setup_youtube_auth.py` as the
  one-time login step.
- Removed `upload_video.py` and `youtube_auth.py` — they duplicated
  `youtube_agent.py` with hardcoded titles/descriptions and no token
  caching either.
- `main.py` now cleans up `output/clips/` after each run and exits
  cleanly if any stage fails, instead of leaving partial state around.
- Added `--topic`, `--category`, and `--no-upload` flags for testing
  without burning a YouTube upload/quota.

## Other free options worth considering

- **Background music**: `config.py` already has `MUSIC_DIR` and
  `ENABLE_BACKGROUND_MUSIC`, but no code populates `assets/music/`
  with anything. Pull a few tracks from the free, no-attribution-
  needed [YouTube Audio Library](https://www.youtube.com/audiolibrary)
  or [Pixabay Music](https://pixabay.com/music/) and drop them in that
  folder.
- **Bigger/better local LLM**: if your machine can handle it,
  `qwen2.5:7b` or `gemma2:9b` via Ollama tend to write noticeably
  better hooks than 3B models — still 100% free and local.
- **Thumbnails**: Shorts don't strictly need custom thumbnails, but if
  you want one, you could grab a frame from the rendered video with
  ffmpeg (`ffmpeg -i final_video.mp4 -ss 00:00:01 -frames:v 1
  thumb.jpg`) — free, no extra API.
- **YouTube quota**: the Data API's free daily quota is 10,000 units;
  a single video upload costs ~1,600, so you can comfortably post
  several times a day without hitting limits.
