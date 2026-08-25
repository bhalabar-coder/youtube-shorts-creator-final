import json
import os
import re

from faster_whisper import WhisperModel

from config import (
    OUTPUT_CAPTIONS,
    OUTPUT_WORDS
)


# ============================================================
# SETTINGS
# ============================================================

WHISPER_MODEL = "small"

MAX_WORDS_PER_CAPTION = 4

MIN_WORDS_PER_CAPTION = 1

MAX_CAPTION_DURATION = 1.5

MIN_CAPTION_DURATION = 0.30


IMPORTANT_WORDS = {

    "actually",
    "always",
    "billion",
    "biggest",
    "deadliest",
    "deepest",
    "fastest",
    "giant",
    "huge",
    "impossible",
    "incredible",
    "largest",
    "million",
    "never",
    "oldest",
    "only",
    "secret",
    "smallest",
    "tiny",
    "trillion",
    "weird",
    "youngest",
}


# ============================================================
# TIMESTAMP
# ============================================================

def timestamp(seconds):

    milliseconds = int(
        (
            seconds
            -
            int(seconds)
        )
        * 1000
    )

    total_seconds = int(
        seconds
    )

    hours = (
        total_seconds
        // 3600
    )

    minutes = (
        (
            total_seconds
            % 3600
        )
        // 60
    )

    secs = (
        total_seconds
        % 60
    )

    return (
        f"{hours:02}:"
        f"{minutes:02}:"
        f"{secs:02},"
        f"{milliseconds:03}"
    )


# ============================================================
# CLEAN WORD
# ============================================================

def clean_word(word):

    return re.sub(
        r"\s+",
        " ",
        word.strip()
    )


# ============================================================
# IMPORTANT WORD
# ============================================================

def is_important_word(
    word
):

    clean = re.sub(
        r"[^a-zA-Z0-9.]",
        "",
        word
    ).lower()

    if not clean:

        return False

    # Numbers are excellent visual emphasis candidates.
    if any(
        char.isdigit()
        for char in clean
    ):

        return True

    return (
        clean
        in IMPORTANT_WORDS
    )


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

        start = (
            current[0][
                "start"
            ]
        )

        end = (
            current[-1][
                "end"
            ]
        )

        duration = (
            end - start
        )

        punctuation_break = (
            word[
                "word"
            ]
            .rstrip()
            .endswith(
                (
                    ".",
                    "?",
                    "!",
                    ",",
                    ";",
                    ":",
                )
            )
        )

        word_limit = (
            len(current)
            >= MAX_WORDS_PER_CAPTION
        )

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
                and
                duration
                >= MIN_CAPTION_DURATION
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
# CREATE CAPTIONS
# ============================================================

def create_captions(
    audio_file
):

    os.makedirs(
        os.path.dirname(
            OUTPUT_CAPTIONS
        ) or ".",
        exist_ok=True
    )

    os.makedirs(
        os.path.dirname(
            OUTPUT_WORDS
        ) or ".",
        exist_ok=True
    )

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

    segments, _ = (
        model.transcribe(
            audio_file,
            word_timestamps=True,
            vad_filter=True,
        )
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

                "word":
                    text,

                "start":
                    word.start,

                "end":
                    word.end,

                "important":
                    is_important_word(
                        text
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
        f"{len(groups)} "
        "caption groups."
    )

    # ========================================================
    # SRT
    # ========================================================

    with open(
        OUTPUT_CAPTIONS,
        "w",
        encoding="utf-8"
    ) as file:

        for index, group in enumerate(
            groups,
            start=1
        ):

            start = (
                group[0][
                    "start"
                ]
            )

            end = (
                group[-1][
                    "end"
                ]
            )

            text = " ".join(
                word["word"]
                for word
                in group
            )

            file.write(
                f"{index}\n"
            )

            file.write(
                f"{timestamp(start)} "
                "--> "
                f"{timestamp(end)}\n"
            )

            file.write(
                text.upper()
            )

            file.write(
                "\n\n"
            )

    # ========================================================
    # WORD LEVEL JSON
    # ========================================================

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