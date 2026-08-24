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
    # Space & astronomy
    "space and astronomy",
    "planets and moons",
    "the sun and solar flares",
    "black holes and neutron stars",
    "galaxies and star clusters",
    "comets and meteor showers",
    "constellations and star myths",
    "space exploration missions",
    "astronauts and life in space",
    "rockets and how they work",
    "space stations",
    "telescopes and observatories",
    "exoplanets and the search for alien life",
    "the moon and its phases",
    "asteroids and near-earth objects",
    "space robots and rovers",
 
    # Ocean & marine life
    "ocean and marine life",
    "deep sea creatures",
    "coral reefs",
    "sharks",
    "whales and dolphins",
    "octopuses and squids",
    "sea turtles",
    "tides and ocean currents",
    "famous shipwrecks",
    "submarines and deep sea exploration",
    "the arctic and antarctic oceans",
    "jellyfish and bioluminescence",
 
    # Prehistoric life
    "dinosaurs and prehistoric life",
    "how dinosaurs went extinct",
    "fossils and fossil hunting",
    "paleontology and dinosaur digs",
    "prehistoric mammals",
    "ancient sea monsters",
    "the first animals on earth",
    "amber and preserved insects",
    "dinosaur eggs and babies",
    "giant prehistoric insects",
 
    # Animals & insects
    "animals and insects",
    "big cats",
    "birds of prey",
    "insect societies like ants and bees",
    "spiders and arachnids",
    "reptiles and amphibians",
    "animal camouflage",
    "migratory animals",
    "endangered species",
    "animal communication",
    "nocturnal animals",
    "desert animal adaptations",
    "arctic animal adaptations",
    "rainforest animals",
    "farm animals",
    "animal babies",
    "the fastest animals on earth",
    "animal intelligence",
 
    # Human body & brain
    "human body and brain",
    "the five senses",
    "how memory works",
    "sleep and dreams",
    "the skeletal system",
    "the digestive system",
    "the circulatory system",
    "how muscles work",
    "the immune system",
    "human growth and development",
    "taste and smell science",
    "how the eye sees",
 
    # Weather & natural phenomena
    "weather and natural phenomena",
    "tornadoes",
    "hurricanes and typhoons",
    "lightning and thunder",
    "rainbows",
    "the northern lights",
    "clouds and how they form",
    "seasons and why they happen",
    "the day and night cycle",
    "snow and how it forms",
    "droughts",
    "monsoons",
 
    # Volcanoes & earthquakes
    "volcanoes and earthquakes",
    "types of volcanoes",
    "tsunamis",
    "how mountains form",
    "plate tectonics",
    "famous volcanic eruptions in history",
 
    # Inventions & technology
    "inventions and how things work",
    "famous inventors",
    "robots and technology",
    "robots in daily life",
    "humanoid robots",
    "artificial intelligence basics",
    "how computers work",
    "the history of the internet",
    "coding and programming basics",
    "video game design",
    "3D printing",
    "drones",
    "renewable energy",
    "how electricity works",
    "magnets and magnetism",
    "how airplanes fly",
    "trains and railways",
    "how cars work",
    "bicycles and how they work",
    "satellites and GPS",
 
    # History & civilizations
    "history and ancient civilizations",
    "ancient egypt",
    "ancient rome",
    "ancient greece",
    "the vikings",
    "medieval castles and knights",
    "famous explorers",
    "the silk road",
    "ancient wonders of the world",
    "pirates and sailing ships",
    "ancient measurement systems",
    "the history of writing",
    "the history of maps",
    "ancient calendars",
    "lost cities and ruins",
    "famous ancient inventions",
    "the history of money",
    "world flags and their meanings",
 
    # Geography & world records
    "geography and world records",
    "the world's tallest mountains",
    "the world's longest rivers",
    "deserts of the world",
    "rainforests of the world",
    "caves and underground wonders",
    "islands and archipelagos",
    "the world's biggest lakes",
    "continents and how they formed",
    "famous bridges and tunnels",
    "the world's tallest buildings",
    "time zones",
    "world languages",
    "gemstones and minerals",
    "volcanic islands",
 
    # Plants & forests
    "plants and forests",
    "how plants make food",
    "giant trees",
    "carnivorous plants",
    "flowers and pollination",
    "seeds and how plants spread",
    "mushrooms and fungi",
    "rainforest ecosystems",
    "desert plants",
    "the water cycle in plants",
 
    # Chemistry & cool reactions
    "chemistry and cool reactions",
    "states of matter",
    "chemical reactions in nature",
    "the periodic table",
    "how soap and bubbles work",
    "fireworks chemistry",
    "how batteries work",
    "acids and bases",
    "crystals and how they form",
    "the science of color",
 
    # Physics & everyday science
    "physics and everyday science",
    "gravity",
    "light and how we see color",
    "sound waves and music science",
    "friction",
    "simple machines",
    "how mirrors and lenses work",
    "static electricity",
    "optical illusions",
    "how magnets attract",
    "momentum and motion",
    "buoyancy and why things float",
 
    # Mythology & legends
    "mythology and legends",
    "greek mythology",
    "norse mythology",
    "egyptian mythology",
    "legendary creatures",
    "world folk tales",
    "ancient myths about the stars",
 
    # Food science
    "food science",
    "how chocolate is made",
    "how bread rises",
    "fermentation and cheese making",
    "spices and where they come from",
    "how ice cream is made",
    "unusual foods around the world",
    "the science of taste",
 
    # Sports science
    "sports science",
    "the history of the olympics",
    "the physics of a curveball",
    "the world's fastest sports",
    "extreme sports",
    "sports records",
    "the science of running fast",
    "how athletes train",
 
    # Weird & wonderful facts
    "weird and wonderful facts",
    "optical illusions in nature",
    "unbelievable world records",
    "strange animal behaviors",
    "mysterious unsolved phenomena",
    "unusual weather events",
    "strange but true science facts",
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