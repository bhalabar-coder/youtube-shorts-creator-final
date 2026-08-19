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
    TOPIC_CATEGORIES,
    TOPIC_HISTORY_SIZE,
    TOPIC_HISTORY_FILE,
)


# ============================================================
# HISTORY (keeps the channel from repeating itself)
# ============================================================

def load_history():

    if not os.path.exists(TOPIC_HISTORY_FILE):
        return []

    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_history(history):

    os.makedirs(
        os.path.dirname(TOPIC_HISTORY_FILE),
        exist_ok=True
    )

    trimmed = history[-TOPIC_HISTORY_SIZE:]

    with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(trimmed, file, indent=2, ensure_ascii=False)


def add_to_history(topic, category):

    history = load_history()

    history.append({
        "topic": topic,
        "category": category,
    })

    save_history(history)


# ============================================================
# CATEGORY SELECTION
# ============================================================

def pick_category(history):

    recent_categories = [
        entry["category"]
        for entry in history[-6:]
    ]

    # Prefer categories that haven't been used in the last few runs,
    # falling back to the full list if everything has been used
    # recently (small TOPIC_CATEGORIES pools, early runs, etc.).
    fresh = [
        category
        for category in TOPIC_CATEGORIES
        if category not in recent_categories
    ]

    pool = fresh if fresh else TOPIC_CATEGORIES

    return random.choice(pool)


# ============================================================
# GENERATE TOPIC
# ============================================================

def generate_topic(category=None):

    history = load_history()

    if category is None:
        category = pick_category(history)

    recent_topics = [
        entry["topic"]
        for entry in history[-25:]
    ]

    avoid_block = (
        "Avoid these recently used topics AND avoid reusing their main "
        "subject (same animal, object, place, or phenomenon) even if "
        "phrased differently:\n- "
        + "\n- ".join(recent_topics)
        if recent_topics
        else ""
    )

    prompt = f"""
Generate ONE viral educational topic for YouTube Shorts.

Audience:
{AUDIENCE}

Category:
{category}

Requirements:
- Curiosity driven
- Easy English
- Highly visual (something that can be shown with real footage or photos)
- Maximum 8 words

{avoid_block}

Return ONLY the topic. No quotes, no labels, no punctuation at the end.
"""

    last_error = None

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):

        try:

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=OLLAMA_TIMEOUT,
            )

            response.raise_for_status()

            topic = response.json()["response"].strip()

            # Strip stray quotes/labels the model sometimes adds.
            topic = topic.strip('"').strip("'").strip()

            if topic.lower().startswith("topic:"):
                topic = topic[len("topic:"):].strip()

            if not topic:
                raise ValueError("Model returned an empty topic.")

            add_to_history(topic, category)

            return topic

        except Exception as exc:

            last_error = exc

            print(f"Topic generation attempt {attempt} failed: {exc}")

            if attempt < OLLAMA_MAX_RETRIES:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"Unable to generate a topic after {OLLAMA_MAX_RETRIES} "
        f"attempts: {last_error}"
    )