import json
import os
import random
import re
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

HOOK_STYLES = [

    (
        "shocking_fact",
        (
            "Open with a bold surprising fact. "
            "Do not use a question."
        )
    ),

    (
        "surprising_question",
        (
            "Open with an unusual question. "
            "Never use 'Did you know' or "
            "'Can you believe'."
        )
    ),

    (
        "myth_debunk",
        (
            "Open with a common belief, then "
            "immediately contradict it."
        )
    ),

    (
        "direct_challenge",
        (
            "Open with a short challenge or "
            "guess for the viewer."
        )
    ),

    (
        "mystery_hook",
        (
            "Open with a mystery or puzzle "
            "that needs an explanation."
        )
    ),

    (
        "imagine_scenario",
        (
            "Open with a vivid 'Imagine...' "
            "scenario the viewer can picture."
        )
    ),

    (
        "comparison_hook",
        (
            "Open with a striking size, speed, "
            "distance, age, or quantity comparison."
        )
    ),

    (
        "number_hook",
        (
            "Open with a specific surprising "
            "number as the first words."
        )
    ),

    (
        "cliffhanger_statement",
        (
            "Open with a tension-building statement "
            "whose explanation comes later."
        )
    ),

    (
        "second_person_flip",
        (
            "Open with something the viewer assumes "
            "is true, then flip it."
        )
    ),
]


BANNED_OPENERS = (
    "can you believe",
    "did you know",
    "today we're",
    "today we are",
    "in this video",
    "welcome",
)


# ============================================================
# HISTORY
# ============================================================

def load_hook_history():

    if not os.path.exists(
        HOOK_HISTORY_FILE
    ):
        return []

    try:

        with open(
            HOOK_HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )

    except Exception:

        return []


def save_hook_history(
    history
):

    os.makedirs(
        os.path.dirname(
            HOOK_HISTORY_FILE
        ) or ".",
        exist_ok=True
    )

    trimmed = history[
        -HOOK_HISTORY_SIZE:
    ]

    with open(
        HOOK_HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            trimmed,
            file,
            indent=2,
            ensure_ascii=False
        )


def pick_hook_style(
    history,
    exclude_keys
):

    recent_keys = (
        [
            entry.get("style")
            for entry in history[-4:]
        ]
        +
        list(
            exclude_keys
        )
    )

    fresh = [
        style
        for style in HOOK_STYLES
        if style[0] not in recent_keys
    ]

    return random.choice(
        fresh
        if fresh
        else HOOK_STYLES
    )


# ============================================================
# OLLAMA
# ============================================================

def _ollama(prompt):

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
        },
        timeout=OLLAMA_TIMEOUT,
    )

    response.raise_for_status()

    return response.json()[
        "response"
    ].strip()


# ============================================================
# CLEAN SCRIPT
# ============================================================

def _clean_spoken_text(
    result
):

    unwanted_prefixes = (
        "narration:",
        "script:",
        "sound suggestion:",
        "sound:",
        "music suggestion:",
        "music:",
        "topic:",
        "title:",
    )

    cleaned_lines = []

    for line in result.splitlines():

        clean = line.strip()

        if not clean:
            continue

        lower = clean.lower()

        if any(
            lower.startswith(prefix)
            for prefix
            in unwanted_prefixes
        ):
            continue

        if clean.startswith("#"):
            continue

        cleaned_lines.append(
            clean
        )

    result = " ".join(
        cleaned_lines
    )

    result = re.sub(
        r"\s+",
        " ",
        result
    ).strip()

    result = re.sub(
        r"[\[\]{}]",
        "",
        result
    )

    return result


# ============================================================
# GENERATE SCRIPT
# ============================================================

def shorten_script(
    topic,
    script,
    max_words=105
):
    """
    Shorten an otherwise valid script instead of failing
    the complete generation process.
    """

    word_count = len(
        script.split()
    )

    if word_count <= max_words:
        return script

    prompt = f"""
Shorten the following YouTube Shorts narration.

Topic:
{topic}

Narration:
{script}

Current length:
{word_count} words

Target:
80-105 words.

IMPORTANT:

- Preserve the hook.
- Preserve the strongest facts.
- Preserve the payoff.
- Remove filler and repetition.
- Keep short conversational sentences.
- Do not introduce new facts.
- Do not add labels.
- Do not add markdown.
- Do not add production notes.

Return ONLY the shortened spoken narration.
"""

    try:

        shortened = _clean_spoken_text(
            _ollama(
                prompt
            )
        )

        shortened_word_count = len(
            shortened.split()
        )

        if shortened_word_count >= 55:

            return shortened

    except Exception as exc:

        print(
            "Automatic script shortening "
            f"failed: {exc}"
        )

    # Do not crash the entire pipeline.
    # Keep the original script as fallback.
    return script

def generate_script(topic):

    history = load_hook_history()

    last_error = None

    tried_styles = []

    for attempt in range(
        1,
        OLLAMA_MAX_RETRIES + 1
    ):

        (
            style_key,
            style_instruction
        ) = pick_hook_style(
            history,
            tried_styles
        )

        tried_styles.append(
            style_key
        )

        prompt = f"""
Create a high-retention YouTube Shorts narration.

Audience:
{AUDIENCE}

Topic:
{topic}

Target length:

70-105 spoken words.

Usually suitable for approximately 22-35 seconds.

Required story structure:

1. HOOK
One short sentence.
Ideally under 10 words.

2. OPEN LOOP
Create a reason to stay for the explanation.

3. FAST REVEAL
Begin delivering useful information immediately.

4. ESCALATION
Introduce an even more surprising detail.

5. PAYOFF
Put the strongest memorable fact near the end.

6. END
Finish with a thought, question, or line that can
encourage comments, sharing, or a natural rewatch.

Do not force a CTA.

HOOK STYLE FOR THIS SCRIPT:

{style_instruction}

Writing rules:

- Never start with "Did you know".
- Never start with "Can you believe".
- Never say "Today we're going to".
- Never say "In this video".
- Never say "Welcome".
- No introduction.
- No filler.
- Use short conversational sentences.
- Use simple English.
- Prefer concrete numbers when accurate.
- Prefer familiar comparisons when useful.
- Do not reveal every interesting point in the first sentence.
- Create curiosity between sentences.
- Avoid exaggerated claims.
- Avoid unsupported claims.
- Every sentence should earn the next second of attention.

When natural, make the final thought connect conceptually
to the opening so the automatic Shorts loop feels smooth.

Return ONLY spoken narration.

Do not include:

Title
Labels
Markdown
Bullets
Scene notes
Sound notes
Visual notes
Production notes
Brackets
"""

        try:

            result = (
                _clean_spoken_text(
                    _ollama(
                        prompt
                    )
                )
            )

            word_count = len(
                result.split()
            )

            if word_count < 55:

                raise ValueError(
                    "Generated script "
                    f"is too short "
                    f"({word_count} words)."
                )

            if word_count > 105:

                print(
                    f"Generated script is "
                    f"{word_count} words. "
                    "Automatically shortening..."
                )

                result = shorten_script(
                    topic,
                    result,
                    max_words=105
                )

                word_count = len(
                    result.split()
                )

                print(
                    f"Final script length: "
                    f"{word_count} words."
                )

            opening = (
                result
                .lower()
                .strip()
            )

            if any(
                opening.startswith(
                    banned
                )
                for banned
                in BANNED_OPENERS
            ):

                raise ValueError(
                    "Script used a banned "
                    f"opener ({style_key})."
                )

            save_hook_history(
                history
                +
                [{
                    "style": style_key,
                    "topic": topic,
                }]
            )

            return result

        except Exception as exc:

            last_error = exc

            print(
                "Script generation "
                f"attempt {attempt} "
                f"({style_key}) failed: "
                f"{exc}"
            )

            if (
                attempt
                < OLLAMA_MAX_RETRIES
            ):

                time.sleep(
                    attempt * 2
                )

    raise RuntimeError(
        "Unable to generate script after "
        f"{OLLAMA_MAX_RETRIES} attempts: "
        f"{last_error}"
    )


# ============================================================
# SCRIPT REVIEW
# ============================================================

def review_script(
    topic,
    script
):

    prompt = f"""
Review this educational YouTube Shorts narration.

Topic:

{topic}

Narration:

{script}

Fix the narration ONLY when needed for:

- obviously false claims
- internally inconsistent claims
- suspicious extreme numbers
- misleading clickbait
- weak first sentence
- filler
- repetition

Preserve the high-retention style.

Keep it approximately 70-105 words when possible.

Do not add citations.
Do not add labels.
Do not add markdown.
Do not add production notes.
Do not add warnings.

Return ONLY the improved spoken narration.
"""

    try:

        reviewed = (
            _clean_spoken_text(
                _ollama(
                    prompt
                )
            )
        )

        word_count = len(
            reviewed.split()
        )

        if word_count >= 50:

            if word_count > 105:

                reviewed = shorten_script(
                    topic,
                    reviewed,
                    max_words=105
                )

            return reviewed

    except Exception as exc:

        print(
            "Script review skipped "
            f"because it failed: {exc}"
        )

    return script


# ============================================================
# GENERATE YOUTUBE TITLE
# ============================================================

def generate_title(
    topic,
    script
):

    prompt = f"""
Create ONE clickable YouTube Shorts title.

Topic:

{topic}

Narration:

{script}

Rules:

- Prefer 35-55 characters.
- Never exceed 70 characters.
- Put the important idea near the beginning.
- Create curiosity without misleading clickbait.
- Make it instantly understandable.
- Use at most one emoji.
- Do not include #Shorts.
- Do not use ALL CAPS except one emphasis word.
- Do not end with a period.

Return ONLY the title.
"""

    try:

        title = (
            _ollama(
                prompt
            )
            .splitlines()[0]
            .strip()
        )

        title = re.sub(
            r"^(title\s*:\s*)",
            "",
            title,
            flags=re.IGNORECASE
        )

        title = (
            title
            .strip('"')
            .strip("'")
            .strip()
            .rstrip(".")
        )

        if title:

            return title[
                :70
            ].rstrip()

    except Exception as exc:

        print(
            "Title generation failed. "
            "Using topic as title. "
            f"{exc}"
        )

    return topic[:70]