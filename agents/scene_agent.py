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
    Generate a scene plan that's tightly synced to the narration.
    Uses extracted keywords from each narration moment to guide
    the visual search queries, ensuring visuals match what's spoken.
    
    narration_moments is output from script_agent.break_script_into_scenes()
    """
    
    # Build a detailed breakdown that LLM can use
    moments_text = "\n".join([
        f"Moment {m['moment']}: \"{m['narration']}\"\n"
        f"  Visual keywords: {', '.join(m['keywords'])}"
        for m in narration_moments
    ])
    
    prompt = f"""
You are creating a high-retention visual storyboard
for a viral educational YouTube Short.

Topic:

{topic}

Narration:

{script}

NARRATION BREAKDOWN (each moment tells you WHAT TO SHOW):

{moments_text}

Your task: Generate exactly {SCENE_COUNT} scenes that match these
narration moments precisely. Use the visual keywords as your guide
for what to search for.

CRITICAL: Each scene must directly visualize what's being said at
that moment. No mismatches.

Break the narration into exactly {SCENE_COUNT} fast-paced visual scenes.

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
- directly match the visual keywords for that narration moment

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

ANIMATION FIELD:

Do not simply repeat the narration.

Animation options:

zoom_in
zoom_out
pan_left
pan_right
static

Return ONLY valid JSON array with exactly {SCENE_COUNT} objects.
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
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=OLLAMA_TIMEOUT,
            )
            
            response.raise_for_status()
            
            result = response.json()["response"]
            
            scenes = extract_json(result)
            
            _validate_scenes(
                scenes,
                narration_moments=narration_moments
            )
            
            return scenes
        
        except Exception as exc:
            
            last_error = exc
            
            print(
                f"Scene plan generation "
                f"(synced) attempt {attempt} "
                f"failed: {exc}"
            )
            
            if attempt < OLLAMA_MAX_RETRIES:
                time.sleep(attempt * 2)
    
    raise RuntimeError(
        f"Unable to generate synced "
        f"scene plan after "
        f"{OLLAMA_MAX_RETRIES} attempts: "
        f"{last_error}"
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