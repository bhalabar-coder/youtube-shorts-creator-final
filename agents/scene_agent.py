import json
import re
import time

import requests

from config import (
    OLLAMA_URL,
    MODEL_NAME,
    OLLAMA_TIMEOUT,
    OLLAMA_MAX_RETRIES,
)


SCENE_COUNT = 9


ANIMATIONS = [
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "static",
]


SCENE_SCHEMA = {

    "type": "array",

    "minItems": SCENE_COUNT,

    "maxItems": SCENE_COUNT,

    "items": {

        "type": "object",

        "properties": {

            "scene": {
                "type": "integer"
            },

            "text": {
                "type": "string"
            },

            "search": {
                "type": "string"
            },

            "animation": {

                "type": "string",

                "enum": ANIMATIONS,
            },
            
        },

        "required": [
            "scene",
            "text",
            "search",
            "animation",
        ],
    },
}


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text):

    text = re.sub(
        r"```json",
        "",
        text
    )

    text = re.sub(
        r"```",
        "",
        text
    ).strip()

    start = text.find(
        "["
    )

    end = text.rfind(
        "]"
    )

    if (
        start != -1
        and end != -1
        and end > start
    ):

        try:

            return json.loads(
                text[
                    start:end + 1
                ]
            )

        except json.JSONDecodeError:

            pass

    raise ValueError(
        "No JSON array found "
        "in model response."
    )


# ============================================================
# FALLBACK
# ============================================================

def split_narration_into_scenes(
    topic,
    script
):

    sentences = [

        sentence.strip()

        for sentence in re.split(
            r"(?<=[.!?])\s+",
            script.strip()
        )

        if sentence.strip()
    ]

    if not sentences:

        sentences = [
            script.strip()
            or topic
        ]

    scenes = []

    for index in range(
        SCENE_COUNT
    ):

        sentence_index = min(
            int(
                index
                * len(sentences)
                / SCENE_COUNT
            ),
            len(sentences) - 1,
        )

        text = sentences[
            sentence_index
        ]

        scenes.append({

            "scene":
                index + 1,

            "text":
                text,

            "search":
                topic,

            "animation":
                ANIMATIONS[
                    index
                    % len(ANIMATIONS)
                ],
        })

    return scenes


# ============================================================
# VALIDATION
# ============================================================

def _validate_scenes(
    scenes
):

    if (
        not isinstance(
            scenes,
            list
        )
        or
        len(scenes)
        != SCENE_COUNT
    ):

        raise ValueError(
            "Expected exactly "
            f"{SCENE_COUNT} scenes."
        )

    seen_queries = set()

    for index, scene in enumerate(
        scenes,
        start=1
    ):

        scene[
            "scene"
        ] = index

        scene[
            "text"
        ] = str(
            scene.get(
                "text"
            ) or ""
        ).strip()

        scene[
            "search"
        ] = str(
            scene.get(
                "search"
            ) or ""
        ).strip()

        animation = (
            scene.get(
                "animation"
            )
        )

        if animation not in ANIMATIONS:

            scene[
                "animation"
            ] = ANIMATIONS[
                (index - 1)
                % len(ANIMATIONS)
            ]

        if not scene["search"]:

            raise ValueError(
                f"Scene {index} "
                "has empty search query."
            )

        normalized_query = (
            scene[
                "search"
            ]
            .lower()
        )

        if (
            normalized_query
            in seen_queries
        ):

            raise ValueError(
                "Duplicate media query: "
                f"{scene['search']}"
            )

        seen_queries.add(
            normalized_query
        )

    return scenes


# ============================================================
# GENERATE SCENES
# ============================================================

def generate_scene_plan(
    topic,
    script
):

    prompt = f"""
You are creating a high-retention visual storyboard
for a viral educational YouTube Short.

Topic:

{topic}

Narration:

{script}

Break the narration into exactly {SCENE_COUNT}
fast-paced visual scenes.

Keep narration order.

VISUAL RULES:

- Scene 1 must visually reinforce the hook immediately.
- Change visuals frequently.
- Every scene must be meaningfully different.
- Prefer real subjects.
- Prefer movement.
- Prefer close-ups.
- Prefer scale comparisons.
- Prefer unusual perspectives.
- Prefer transformations.
- Prefer dramatic real footage.
- Avoid generic stock-footage ideas.

Consecutive scenes should change at least one:

- subject
- scale
- environment
- perspective
- comparison object

SEARCH FIELD:

The "search" field must:

- contain 2-5 words
- describe a REAL photographable subject
- work as a Pexels or Pixabay search query
- be unique for every scene

Bad searches:

interesting science
amazing nature
space concept

Good searches:

octopus underwater closeup
volcano lava eruption
astronaut earth window
giant blue whale underwater
lightning storm slow motion

OVERLAY FIELD:

Do not simply repeat the narration.

Animation options:

zoom_in
zoom_out
pan_left
pan_right
static
"""

    last_error = None

    for attempt in range(
        1,
        OLLAMA_MAX_RETRIES + 1
    ):

        try:

            response = requests.post(

                OLLAMA_URL,

                json={

                    "model":
                        MODEL_NAME,

                    "prompt":
                        prompt,

                    "stream":
                        False,

                    "format":
                        SCENE_SCHEMA,
                },

                timeout=
                    OLLAMA_TIMEOUT,
            )

            response.raise_for_status()

            scenes = extract_json(
                response.json()[
                    "response"
                ]
            )

            return _validate_scenes(
                scenes
            )

        except Exception as exc:

            last_error = exc

            print(
                f"Scene plan attempt "
                f"{attempt} failed: "
                f"{exc}"
            )

            if (
                attempt
                < OLLAMA_MAX_RETRIES
            ):

                time.sleep(
                    attempt * 2
                )

    print(
        "All scene-plan attempts failed. "
        "Using fallback."
    )

    print(
        last_error
    )

    return split_narration_into_scenes(
        topic,
        script
    )