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


SCENE_COUNT = 5

ANIMATIONS = [
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "static",
]

# A real JSON Schema (not just "format": "json") — this constrains
# Ollama's decoding so the model CANNOT return a single object or a
# short list. It must return an array of exactly SCENE_COUNT items
# matching this shape.
SCENE_SCHEMA = {
    "type": "array",
    "minItems": SCENE_COUNT,
    "maxItems": SCENE_COUNT,
    "items": {
        "type": "object",
        "properties": {
            "scene": {"type": "integer"},
            "text": {"type": "string"},
            "search": {"type": "string"},
            "animation": {
                "type": "string",
                "enum": ANIMATIONS,
            },
        },
        "required": ["scene", "text", "search", "animation"],
    },
}


# ============================================================
# JSON EXTRACTION (defensive — schema mode should already return
# clean JSON, but older Ollama versions / model quirks can still
# wrap it or add stray text)
# ============================================================

def extract_json(text):

    text = re.sub(r"```json", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    obj_start = text.find("{")
    obj_end = text.rfind("}")

    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        try:
            parsed = json.loads(text[obj_start:obj_end + 1])
            for value in parsed.values():
                if isinstance(value, list):
                    return value
            # Single scene object returned instead of a list —
            # treat it as a 1-item list so validation below can
            # catch it and retry, rather than crashing here.
            if "scene" in parsed:
                return [parsed]
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"No JSON array found in model response. Raw output:\n{text[:500]}"
    )


# ============================================================
# DETERMINISTIC FALLBACK (no LLM — guarantees SCENE_COUNT distinct
# scenes even if the model repeatedly fails to follow instructions)
# ============================================================

def split_narration_into_scenes(topic, script):

    sentences = re.split(r"(?<=[.!?])\s+", script.strip())

    sentences = [s for s in sentences if s.strip()]

    if not sentences:
        sentences = [script.strip()]

    # Distribute sentences across SCENE_COUNT buckets as evenly as
    # possible, keeping sentence order intact.
    buckets = [[] for _ in range(SCENE_COUNT)]

    for index, sentence in enumerate(sentences):
        buckets[index % SCENE_COUNT].append(sentence)

    scenes = []

    for index, bucket in enumerate(buckets, start=1):

        text = " ".join(bucket).strip() or topic

        scenes.append({
            "scene": index,
            "text": text,
            # No per-scene visual context here, so fall back to the
            # topic itself as the stock-footage search query.
            "search": topic,
            "animation": ANIMATIONS[(index - 1) % len(ANIMATIONS)],
        })

    return scenes


# ============================================================
# GENERATE SCENE PLAN
# ============================================================

def generate_scene_plan(topic, script):

    prompt = f"""
        You are a Pixar storyboard artist.

        Topic:
        {topic}

        Narration:
        {script}

        Break the narration into exactly {SCENE_COUNT} scenes covering
        the whole narration in order, from start to finish.

        The "search" field must be 2-4 words describing a REAL,
        photographable subject (no cartoons, no abstract ideas) so it
        can be used as a stock footage search query. Make each
        scene's search query DIFFERENT from the others.

        Animation options:
        zoom_in
        zoom_out
        pan_left
        pan_right
        static
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
                    "format": SCENE_SCHEMA,
                },
                timeout=OLLAMA_TIMEOUT,
            )

            response.raise_for_status()

            scenes = extract_json(response.json()["response"])

            if not isinstance(scenes, list) or len(scenes) < SCENE_COUNT:
                raise ValueError(
                    f"Expected {SCENE_COUNT} scenes, got "
                    f"{len(scenes) if isinstance(scenes, list) else 'non-list'}."
                )

            # Trim in case the model over-delivers.
            scenes = scenes[:SCENE_COUNT]

            # Re-number in case the model's own numbering is off.
            for index, scene in enumerate(scenes, start=1):
                scene["scene"] = index

            return scenes

        except Exception as exc:

            last_error = exc

            print(f"Scene plan attempt {attempt} failed: {exc}")

            if attempt < OLLAMA_MAX_RETRIES:
                time.sleep(attempt * 2)

    # --------------------------------------------------------
    # Every LLM attempt failed to produce a valid scene list —
    # fall back to a deterministic split so the pipeline still
    # produces a real multi-scene video instead of looping one clip.
    # --------------------------------------------------------

    print(
        f"All {OLLAMA_MAX_RETRIES} scene-plan attempts failed "
        f"({last_error}). Falling back to a deterministic narration split."
    )

    return split_narration_into_scenes(topic, script)
