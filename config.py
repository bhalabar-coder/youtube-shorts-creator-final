import os

# Loads variables from a local .env file if python-dotenv is installed
# and a .env file is present. This is how API keys / secrets should be
# supplied — never hardcode them in source files.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================
# OLLAMA (free, local LLM)
# ============================================================

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate"
)

# NOTE: the previous default ("gemma4:e4b") is not a real Ollama model
# tag and would fail at request time. Pick any model you've pulled
# with `ollama pull <name>`, e.g.:
#   ollama pull llama3.2        (fast, 3B, great default)
#   ollama pull gemma2:9b       (higher quality, slower)
#   ollama pull qwen2.5:7b      (strong instruction following)
MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "llama3.2"
)

OLLAMA_TIMEOUT = 180
OLLAMA_MAX_RETRIES = 3


# ============================================================
# CONTENT / AUDIENCE
# ============================================================

# Kept configurable instead of hardcoded into every prompt string,
# so the same pipeline can target different audiences/channels.
AUDIENCE = os.getenv(
    "AUDIENCE",
    "curious people who love quick, fun facts"
)

# A wide pool of topic categories so the channel doesn't get stuck
# doing "space" or "animals" every single run. topic_agent.py picks
# one at random each run (weighted away from recently-used ones).
TOPIC_CATEGORIES = [
    "space and astronomy",
    "ocean and marine life",
    "dinosaurs and prehistoric life",
    "animals and insects",
    "human body and brain",
    "weather and natural phenomena",
    "volcanoes and earthquakes",
    "inventions and how things work",
    "history and ancient civilizations",
    "geography and world records",
    "plants and forests",
    "robots and technology",
    "chemistry and cool reactions",
    "physics and everyday science",
    "mythology and legends",
    "food science",
    "sports science",
    "weird and wonderful facts",
]

# How many recent topics to remember so we can steer the model away
# from repeating itself.
TOPIC_HISTORY_SIZE = 200
TOPIC_HISTORY_FILE = "output/topic_history.json"

# Recently-used narration hook styles are tracked the same way, so the
# opening line doesn't fall back to the same "Can you believe..."
# pattern every time.
HOOK_HISTORY_SIZE = 30
HOOK_HISTORY_FILE = "output/hook_history.json"


# ============================================================
# VIDEO
# ============================================================

VIDEO_DURATION = 30

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

FPS = 30

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

VIDEO_BITRATE = "5000k"


# ============================================================
# OUTPUT
# ============================================================

OUTPUT_AUDIO = "output/audio/voice.mp3"
OUTPUT_VIDEO = "output/videos/final_video.mp4"
OUTPUT_CAPTIONS = "output/captions/captions.srt"
OUTPUT_WORDS = "output/captions/words.json"


# ============================================================
# PEXELS (free stock video/photo API — https://www.pexels.com/api/)
# ============================================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")


# ============================================================
# PIXABAY (free, optional second source — https://pixabay.com/api/docs/)
# Used only as a fallback when Pexels has no good match, which widens
# how many topics can find decent visuals.
# ============================================================

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")


# ============================================================
# YOUTUBE
# ============================================================

YOUTUBE_CATEGORY = "27"  # Education

YOUTUBE_PRIVACY_STATUS = os.getenv(
    "YOUTUBE_PRIVACY_STATUS",
    "public"
)

YOUTUBE_MADE_FOR_KIDS = os.getenv(
    "YOUTUBE_MADE_FOR_KIDS",
    "false"
).lower() == "true"

YOUTUBE_CLIENT_SECRET_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRET_FILE",
    "credentials/client_secret.json"
)

# Where the OAuth refresh token is cached after the first login, so
# every subsequent run (including cron/scheduled runs) can upload
# without opening a browser again.
YOUTUBE_TOKEN_FILE = os.getenv(
    "YOUTUBE_TOKEN_FILE",
    "credentials/token.json"
)


# ============================================================
# AUDIO
# ============================================================

ENABLE_BACKGROUND_MUSIC = True

BACKGROUND_MUSIC_VOLUME = 0.08


# ============================================================
# DIRECTORIES
# ============================================================

MUSIC_DIR = "assets/music"
SFX_DIR = "assets/sfx"
CLIPS_DIR = "output/clips"
TEMP_DIR = "output/temp"


# ============================================================
# ENSURE OUTPUT DIRECTORIES EXIST
# ============================================================
# Git doesn't track empty directories, and .gitignore intentionally
# excludes generated output — so on a fresh checkout (e.g. a GitHub
# Actions runner) none of these folders exist yet. Call this once at
# the start of a run so every agent can assume its output directory
# is already there.

def ensure_output_dirs():

    import os as _os

    paths = [
        _os.path.dirname(OUTPUT_AUDIO),
        _os.path.dirname(OUTPUT_VIDEO),
        _os.path.dirname(OUTPUT_CAPTIONS),
        _os.path.dirname(TOPIC_HISTORY_FILE),
        CLIPS_DIR,
        TEMP_DIR,
        MUSIC_DIR,
        SFX_DIR,
    ]

    for path in paths:
        if path:
            _os.makedirs(path, exist_ok=True)