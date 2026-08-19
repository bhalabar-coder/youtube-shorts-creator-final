import json
import os
import random
import time

import requests

from config import (
    OLLAMA_URL,
    MODEL_NAME,
    OLLAMA_TIMEOUT,
    OLLAMA_MAX_RETRIES,
    AUDIENCE,
    HOOK_HISTORY_FILE,
    HOOK_HISTORY_SIZE,
)


# ============================================================
# HOOK STYLES
# ============================================================
# A small local model tends to latch onto whichever single example
# it's shown ("Can you believe...") and reuse it almost every time.
# Forcing one specific, named style per script — and rotating which
# style gets picked — is what actually produces variety.

HOOK_STYLES = [
    ("shocking_fact", (
        "Open with a bold, jaw-dropping statement of fact. "
        "No question mark — state it as fact."
    )),
    ("surprising_question", (
        "Open with a surprising question. Do NOT use 'Can you believe' "
        "or 'Did you know' — invent a different question."
    )),
    ("myth_debunk", (
        "Open by stating what most people believe, then immediately "
        "contradict it in the same or next sentence "
        "(e.g. 'Everyone thinks X. They're wrong.')."
    )),
    ("direct_challenge", (
        "Open by challenging the viewer directly, e.g. 'Try to guess...' "
        "or 'Bet you didn't know...'."
    )),
    ("mystery_hook", (
        "Open by framing the topic as an unsolved mystery or puzzle "
        "scientists are still figuring out."
    )),
    ("imagine_scenario", (
        "Open with 'Imagine if...' or a vivid hypothetical scenario "
        "the viewer can picture."
    )),
    ("comparison_hook", (
        "Open with a striking comparison between two things — size, "
        "speed, distance, or quantity."
    )),
    ("number_hook", (
        "Open with a specific, surprising number or statistic as the "
        "very first words of the sentence."
    )),
    ("cliffhanger_statement", (
        "Open with an incomplete, tension-building statement that gets "
        "resolved a sentence or two later."
    )),
    ("second_person_flip", (
        "Open by describing something the viewer thinks is true, then "
        "flipping it within the same sentence."
    )),
]

BANNED_OPENERS = (
    "can you believe",
    "did you know",
)


# ============================================================
# HOOK HISTORY (avoids repeating the same style run after run)
# ============================================================

def load_hook_history():

    if not os.path.exists(HOOK_HISTORY_FILE):
        return []

    try:
        with open(HOOK_HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_hook_history(history):

    os.makedirs(os.path.dirname(HOOK_HISTORY_FILE) or ".", exist_ok=True)

    trimmed = history[-HOOK_HISTORY_SIZE:]

    with open(HOOK_HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(trimmed, file, indent=2, ensure_ascii=False)


def pick_hook_style(history, exclude_keys):

    recent_keys = [entry["style"] for entry in history[-4:]] + list(exclude_keys)

    fresh = [
        style for style in HOOK_STYLES
        if style[0] not in recent_keys
    ]

    pool = fresh if fresh else HOOK_STYLES

    return random.choice(pool)


# ============================================================
# GENERATE SCRIPT
# ============================================================

def generate_script(topic):

    history = load_hook_history()

    unwanted_prefixes = [
        "narration:",
        "script:",
        "sound suggestion:",
        "sound:",
        "music suggestion:",
        "music:",
        "topic:",
    ]

    last_error = None
    tried_styles = []

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):

        style_key, style_instruction = pick_hook_style(history, tried_styles)
        tried_styles.append(style_key)

        prompt = f"""
        Create a YouTube Shorts narration.

        Audience:
        {AUDIENCE}

        Topic:
        {topic}

        Requirements:

        - Length: approximately 100-120 words.
        - Fun, exciting and educational.
        - Simple English.
        - The FIRST sentence must be a powerful hook that immediately
        creates curiosity.

        HOOK STYLE FOR THIS SCRIPT (follow this exactly — do not use
        any other opening style):
        {style_instruction}

        Do NOT start with "Can you believe" or "Did you know" under
        any circumstances.

        - Do not waste the first few seconds introducing the topic.
        - Reveal the interesting fact quickly.
        - Keep the narration fast and engaging.
        - End with a memorable fact or conclusion.

        IMPORTANT:

        Return ONLY spoken narration.

        DO NOT include:
        - Title
        - Topic heading
        - Sound suggestions
        - Sound effects
        - Music suggestions
        - Visual suggestions
        - Scene descriptions
        - Animation instructions
        - Production notes
        - Markdown
        - Bullet points
        - Labels such as "Narration:", "Sound:", "Topic:",
        "Scene:", etc.
        - Anything inside brackets or braces

        Return ONLY the narration.
        """

        try:

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=OLLAMA_TIMEOUT
            )

            response.raise_for_status()

            result = response.json()["response"].strip()

            # ------------------------------------------------
            # Defensive cleanup
            # ------------------------------------------------

            lines = result.splitlines()

            cleaned_lines = []

            for line in lines:

                clean = line.strip()

                if not clean:
                    continue

                lower = clean.lower()

                if any(
                    lower.startswith(prefix)
                    for prefix in unwanted_prefixes
                ):
                    continue

                if clean.startswith("#"):
                    continue

                cleaned_lines.append(clean)

            result = " ".join(cleaned_lines).strip()

            if len(result.split()) < 20:
                raise ValueError(
                    "Generated script looks too short "
                    f"({len(result.split())} words)."
                )

            opening = result.lower().strip()

            if any(opening.startswith(banned) for banned in BANNED_OPENERS):
                raise ValueError(
                    f"Script opened with a banned phrase despite "
                    f"instructions (style attempted: {style_key})."
                )

            save_hook_history(history + [{
                "style": style_key,
                "topic": topic,
            }])

            return result

        except Exception as exc:

            last_error = exc

            print(
                f"Script generation attempt {attempt} "
                f"(style: {style_key}) failed: {exc}"
            )

            if attempt < OLLAMA_MAX_RETRIES:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"Unable to generate a script after {OLLAMA_MAX_RETRIES} "
        f"attempts: {last_error}"
    )