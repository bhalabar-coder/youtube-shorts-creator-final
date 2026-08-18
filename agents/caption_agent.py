import re
import json
import os
from faster_whisper import WhisperModel

from config import (
    OUTPUT_CAPTIONS,
    OUTPUT_WORDS
)


# ============================================================
# SETTINGS
# ============================================================

WHISPER_MODEL = "small"

MAX_WORDS_PER_CAPTION = 5

MIN_WORDS_PER_CAPTION = 2

MAX_CAPTION_DURATION = 2.2

MIN_CAPTION_DURATION = 0.45


# ============================================================
# TIMESTAMP
# ============================================================

def timestamp(seconds):

    milliseconds = int(
        (seconds - int(seconds))
        * 1000
    )

    total_seconds = int(
        seconds
    )

    hours = (
        total_seconds // 3600
    )

    minutes = (
        (total_seconds % 3600)
        // 60
    )

    secs = (
        total_seconds % 60
    )

    return (
        f"{hours:02}:"
        f"{minutes:02}:"
        f"{secs:02},"
        f"{milliseconds:03}"
    )


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_word(word):

    word = word.strip()

    word = re.sub(
        r"\s+",
        " ",
        word
    )

    return word


# ============================================================
# IMPORTANT WORD DETECTION
# ============================================================

def is_important_word(
    word
):

    clean = re.sub(
        r"[^a-zA-Z]",
        "",
        word
    ).lower()

    important_words = {
        "amazing",
        "incredible",
        "wow",
        "secret",
        "why",
        "how",
        "never",
        "always",
        "giant",
        "tiny",
        "huge",
        "fast",
        "slow",
        "space",
        "planet",
        "earth",
        "moon",
        "sun",
        "star",
        "ocean",
        "dinosaur",
        "volcano",
        "bee",
        "bees",
        "honey",
        "shark",
        "whale",
        "dolphin",
        "fire",
        "water",
    }

    return clean in important_words


# ============================================================
# GROUP WORDS
# ============================================================

def group_words(
    words
):

    captions = []

    current = []

    for word in words:

        current.append(
            word
        )

        start = current[0]["start"]

        end = current[-1]["end"]

        duration = (
            end - start
        )

        # ----------------------------------------------------
        # Break after punctuation
        # ----------------------------------------------------

        punctuation_break = (
            word["word"].rstrip()
            .endswith(
                (
                    ".",
                    "?",
                    "!",
                    ","
                )
            )
        )

        # ----------------------------------------------------
        # Break after word count
        # ----------------------------------------------------

        word_limit = (
            len(current)
            >= MAX_WORDS_PER_CAPTION
        )

        # ----------------------------------------------------
        # Break if caption too long
        # ----------------------------------------------------

        duration_limit = (
            duration
            >= MAX_CAPTION_DURATION
        )

        if (
            word_limit
            or punctuation_break
            or duration_limit
        ):

            if (
                len(current)
                >= MIN_WORDS_PER_CAPTION
            ):

                captions.append(
                    current
                )

                current = []

    if current:

        captions.append(
            current
        )

    return captions


# ============================================================
# CREATE SRT
# ============================================================

def create_captions(
    audio_file
):

    os.makedirs(os.path.dirname(OUTPUT_CAPTIONS) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(OUTPUT_WORDS) or ".", exist_ok=True)

    print(
        "Loading Whisper model..."
    )

    model = WhisperModel(
        WHISPER_MODEL,
        device="cpu",
        compute_type="int8"
    )

    print(
        "Transcribing narration..."
    )

    segments, _ = model.transcribe(
        audio_file,
        word_timestamps=True,
        vad_filter=True,
    )

    all_words = []

    for segment in segments:

        if not segment.words:

            continue

        for word in segment.words:

            text = clean_word(
                word.word
            )

            if not text:

                continue

            all_words.append({
                "word": text,
                "start": word.start,
                "end": word.end,
                "important": (
                    is_important_word(
                        text
                    )
                ),
            })

    if not all_words:

        raise RuntimeError(
            "Whisper did not detect "
            "any words."
        )

    groups = group_words(
        all_words
    )

    print(
        f"Generated "
        f"{len(groups)} caption groups."
    )

    with open(
        OUTPUT_CAPTIONS,
        "w",
        encoding="utf-8"
    ) as file:

        for index, group in enumerate(
            groups,
            start=1
        ):

            start = group[0][
                "start"
            ]

            end = group[-1][
                "end"
            ]

            text = " ".join(
                word["word"]
                for word in group
            )

            file.write(
                f"{index}\n"
            )

            file.write(
                f"{timestamp(start)} --> "
                f"{timestamp(end)}\n"
            )

            file.write(
                text.upper()
            )

            file.write(
                "\n\n"
            )

    with open(
        OUTPUT_WORDS,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            all_words,
            file,
            indent=2,
            ensure_ascii=False
        )

    return groups