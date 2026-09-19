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

# ============================================================
# SEARCH TERM CONFLICT DETECTION
# ============================================================
# Prevent showing shallow coral reefs when narrating deep sea,
# or vice versa. Catches misalignments before they happen.

SEARCH_CONFLICTS = {
    # If narration contains these keywords, AVOID these search terms
    "deep": {
        "avoid": [
            "coral reef", "shallow", "tropical", "sunlit", "clear water",
            "bright fish", "colorful reef", "surface", "snorkel"
        ],
        "prefer": [
            "deep sea", "bioluminescence", "anglerfish", "lanternfish",
            "trench", "abyss", "pressure", "dark ocean", "hydrothermal"
        ]
    },
    "shallow": {
        "avoid": [
            "trench", "abyss", "deep", "bioluminescence", "dark ocean",
            "pressure", "hydrothermal", "anglerfish"
        ],
        "prefer": [
            "coral reef", "tropical", "colorful", "sunlit", "clear water",
            "surface", "reef fish"
        ]
    },
    "dark": {
        "avoid": [
            "bright", "sunlit", "colorful", "tropical", "clear", "sunny"
        ],
        "prefer": [
            "dark", "night", "bioluminescence", "glowing", "shadows"
        ]
    },
    "glow": {
        "avoid": [
            "coral reef", "shallow", "tropical", "sunlit", "daytime"
        ],
        "prefer": [
            "bioluminescence", "glowing", "deep sea", "dark", "night"
        ]
    },
    "cold": {
        "avoid": [
            "tropical", "warm", "reef", "colorful", "sunlit"
        ],
        "prefer": [
            "arctic", "ice", "glacier", "polar", "snow"
        ]
    },
    "arctic": {
        "avoid": [
            "tropical", "warm", "reef", "desert", "hot"
        ],
        "prefer": [
            "arctic", "ice", "glacier", "polar", "snow", "penguin", "seal"
        ]
    },
}

def check_search_conflicts(
    narration,
    search_query
):
    """
    Validate that a search query doesn't contradict the narration.
    Returns (is_valid, message, suggested_fixes)
    """
    
    narration_lower = narration.lower()
    search_lower = search_query.lower()
    
    conflicts_found = []
    suggested_improvements = []
    
    for keyword, rules in SEARCH_CONFLICTS.items():
        
        if keyword not in narration_lower:
            continue
        
        # Check if search contains any "avoid" terms
        for avoid_term in rules["avoid"]:
            if avoid_term in search_lower:
                conflicts_found.append(
                    f"Narration mentions '{keyword}' "
                    f"but search includes '{avoid_term}'"
                )
        
        # If we found conflicts, suggest improvements
        if conflicts_found:
            for prefer_term in rules["prefer"]:
                if prefer_term not in search_lower:
                    suggested_improvements.append(
                        f"Add '{prefer_term}' to search"
                    )
    
    if conflicts_found:
        return False, "; ".join(conflicts_found), suggested_improvements
    
    return True, "OK", []


def fix_search_query(
    narration,
    original_search
):
    """
    Auto-fix a search query to align with narration.
    Adds preferred terms and removes conflicting ones.
    """
    
    narration_lower = narration.lower()
    fixed = original_search.lower()
    
    for keyword, rules in SEARCH_CONFLICTS.items():
        
        if keyword not in narration_lower:
            continue
        
        # Remove conflicting terms
        for avoid_term in rules["avoid"]:
            fixed = fixed.replace(avoid_term, "").strip()
        
        # Add preferred terms if missing
        for prefer_term in rules["prefer"]:
            if prefer_term not in fixed:
                fixed = f"{prefer_term} {fixed}".strip()
                break  # Only add one preferred term to keep it concise
    
    # Clean up excessive whitespace
    fixed = " ".join(fixed.split())[:100]  # Cap at 100 chars
    
    return fixed if fixed else original_search


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
    """
    Parse a JSON scene array from an Ollama response.

    Supports:
    - a raw JSON array
    - JSON inside ```json fences
    - a wrapped object such as {"scenes": [...]}
    - extra text before/after the JSON array
    """

    if text is None:
        raise ValueError("Empty model response.")

    if isinstance(text, list):
        return text

    if isinstance(text, dict):
        if isinstance(text.get("scenes"), list):
            return text["scenes"]
        raise ValueError("Model response JSON object does not contain a scenes array.")

    text = str(text).strip()

    # Remove markdown code fences if the model ignored the structured-output request.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()

    # First try parsing the complete response.
    try:
        parsed = json.loads(text)

        if isinstance(parsed, list):
            return parsed

        if isinstance(parsed, dict) and isinstance(parsed.get("scenes"), list):
            return parsed["scenes"]

    except json.JSONDecodeError:
        pass

    # Fallback: locate the first balanced JSON array.
    array_start = text.find("[")

    if array_start != -1:
        depth = 0
        in_string = False
        escape = False

        for index in range(array_start, len(text)):
            char = text[index]

            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1

                if depth == 0:
                    candidate = text[array_start:index + 1]

                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        break

    preview = text[:500].replace("\n", " ")

    raise ValueError(
        "No valid JSON scene array found in model response. "
        f"Response preview: {preview}"
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
    scenes,
    narration_moments=None
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

        # CONFLICT DETECTION: Validate search against narration
        if narration_moments:
            
            moment = narration_moments[
                min(index - 1, len(narration_moments) - 1)
            ]
            
            narration = moment.get("narration", "")
            
            is_valid, msg, suggestions = (
                check_search_conflicts(
                    narration,
                    scene["search"]
                )
            )
            
            if not is_valid:
                
                print(
                    f"⚠️  Scene {index} search conflict: "
                    f"{msg}"
                )
                
                # Auto-fix the search
                fixed = fix_search_query(
                    narration,
                    scene["search"]
                )
                
                print(
                    f"   Fixed: '{scene['search']}' "
                    f"→ '{fixed}'"
                )
                
                scene["search"] = fixed

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

def generate_scene_plan_with_sync(
    topic,
    script,
    narration_moments
):
    """
    Generate exactly SCENE_COUNT visual scenes synchronized to narration.

    Uses Ollama structured output so the response is always requested
    as a JSON array matching SCENE_SCHEMA. If all model attempts fail,
    the workflow falls back to deterministic scene generation instead
    of terminating the whole video workflow.
    """

    moments_text = "\n".join([
        (
            f"Moment {m['moment']}:\n"
            f"Narration: {m['narration']}\n"
            f"Keywords: {', '.join(m['keywords'])}\n"
            f"Base stock search: {m['search_query']}"
        )
        for m in narration_moments
    ])

    prompt = f"""
You are creating a high-retention visual storyboard for a viral
educational YouTube Short.

TOPIC:
{topic}

FULL NARRATION:
{script}

NARRATION MOMENTS:
{moments_text}

Create exactly {SCENE_COUNT} scenes in the same order as the narration moments.

Each scene MUST contain exactly these fields:
- scene: integer from 1 to {SCENE_COUNT}
- text: narration text for that moment
- search: literal 2-6 word Pexels/Pixabay search phrase
- animation: one of zoom_in, zoom_out, pan_left, pan_right, static

SEARCH RULES:
- Show what is literally being spoken about in that moment.
- Prefer concrete visible nouns and actions.
- Include environment only when important.
- Every search query must be different.
- Do not use abstract phrases such as amazing discovery, science concept,
  interesting nature, cinematic footage, or stock footage.
- Do not invent subjects that are absent from the narration.

Return ONLY the JSON array.
Do not add Markdown fences.
Do not add an introduction or explanation.
Do not write anything before or after the JSON.
"""

    last_error = None

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,

                    # IMPORTANT: force Ollama structured JSON output.
                    # This was missing from the synced implementation.
                    "format": SCENE_SCHEMA,

                    # Low temperature makes schema-following more deterministic.
                    "options": {
                        "temperature": 0,
                        "num_predict": 2048,
                    },
                },
                timeout=OLLAMA_TIMEOUT,
            )

            response.raise_for_status()

            response_data = response.json()
            raw_result = response_data.get("response", "")

            if not raw_result:
                raise ValueError(
                    f"Ollama returned an empty response: {response_data}"
                )

            scenes = extract_json(raw_result)

            return _validate_scenes(
                scenes,
                narration_moments=narration_moments
            )

        except Exception as exc:
            last_error = exc

            print(
                f"Scene plan generation (synced) attempt {attempt} "
                f"failed: {exc}"
            )

            if attempt < OLLAMA_MAX_RETRIES:
                time.sleep(attempt * 2)

    # Do not kill the entire Shorts workflow because the local LLM
    # returned invalid structured output. Use deterministic scenes instead.
    print(
        "All synced scene-plan attempts failed. "
        "Using deterministic fallback scene plan."
    )
    print(f"Last scene-plan error: {last_error}")

    fallback_scenes = split_narration_into_scenes(
        topic,
        script
    )

    # Improve fallback searches using the narration-moment search queries.
    for index, scene in enumerate(fallback_scenes):
        if index < len(narration_moments):
            moment = narration_moments[index]

            scene["text"] = moment.get(
                "narration",
                scene["text"]
            )

            scene["search"] = moment.get(
                "search_query",
                scene["search"]
            ) or topic

    # Ensure duplicate fallback queries do not fail validation.
    seen = set()

    for index, scene in enumerate(fallback_scenes, start=1):
        base_query = " ".join(str(scene["search"]).split()).strip() or topic
        candidate = base_query
        suffix = 2

        while candidate.lower() in seen:
            words = str(scene.get("text") or "").split()
            extra = " ".join(words[:min(suffix, len(words))])
            candidate = f"{base_query} {extra}".strip()
            suffix += 1

            if suffix > 6:
                candidate = f"{base_query} scene {index}"
                break

        scene["search"] = candidate[:100]
        seen.add(scene["search"].lower())

    return _validate_scenes(
        fallback_scenes,
        narration_moments=narration_moments
    )


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