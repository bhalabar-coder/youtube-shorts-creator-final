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
    TOPIC_CATEGORIES,
    TOPIC_HISTORY_SIZE,
    TOPIC_HISTORY_FILE,
)

try:
    from agents.analytics_agent import get_performance_stats
except ImportError:
    # Analytics not available yet (fresh install)
    get_performance_stats = None


TOPIC_CANDIDATE_COUNT = 5


# ============================================================
# HISTORY
# ============================================================

def load_history():

    if not os.path.exists(TOPIC_HISTORY_FILE):
        return []

    try:

        with open(
            TOPIC_HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return []


def save_history(history):

    os.makedirs(
        os.path.dirname(TOPIC_HISTORY_FILE) or ".",
        exist_ok=True
    )

    trimmed = history[-TOPIC_HISTORY_SIZE:]

    with open(
        TOPIC_HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            trimmed,
            file,
            indent=2,
            ensure_ascii=False
        )


def add_to_history(
    topic,
    category
):

    history = load_history()

    history.append({
        "topic": topic,
        "category": category,
    })

    save_history(
        history
    )


# ============================================================
# CATEGORY SELECTION
# ============================================================

def pick_category(history):
    """
    Pick a category, preferring ones with good performance history.
    
    Strategy:
    1. Never pick a category used in the last 6 videos (variety)
    2. If analytics available, weight by performance
    3. Fallback to random if no analytics
    """

    recent_categories = [
        entry.get("category")
        for entry in history[-6:]
        if entry.get("category")
    ]

    fresh = [
        category
        for category in TOPIC_CATEGORIES
        if category not in recent_categories
    ]

    candidates = (
        fresh if fresh else TOPIC_CATEGORIES
    )

    # Try to use performance data if available
    if get_performance_stats:
        
        try:
            
            stats = get_performance_stats()
            
            if stats and stats.get("by_category"):
                
                # Weight by average views per category
                weights = {}
                
                for category in candidates:
                    
                    if category in stats["by_category"]:
                        
                        cat_data = (
                            stats["by_category"][category]
                        )
                        
                        count = cat_data.get("count", 0)
                        
                        if count > 0:
                            
                            avg_views = (
                                cat_data["views"] / count
                            )
                            
                            weights[category] = (
                                avg_views
                            )
                    
                    else:
                        # Categories with no data
                        # yet get neutral weight
                        weights[category] = 100
                
                # Random choice weighted by views
                if weights:
                    
                    return random.choices(
                        list(weights.keys()),
                        weights=list(
                            weights.values()
                        ),
                        k=1
                    )[0]
        
        except Exception as e:
            
            # Analytics failed, fall back to random
            print(
                f"Could not use performance "
                f"weighting: {e}"
            )

    # Fallback: random choice
    return random.choice(
        candidates
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
# CLEAN TOPIC
# ============================================================

def _clean_candidate(line):

    line = re.sub(
        r"^\s*[-*\d.)]+\s*",
        "",
        line.strip()
    )

    line = (
        line
        .strip('"')
        .strip("'")
        .strip()
    )

    line = line.rstrip(
        ".!:;-"
    )

    return line.strip()


# ============================================================
# GENERATE MULTIPLE CANDIDATES
# ============================================================

def generate_candidates(
    category,
    recent_topics
):

    avoid_block = ""

    if recent_topics:

        avoid_block = (
            "Avoid these recently used topics and their "
            "main subjects:\n- "
            +
            "\n- ".join(
                recent_topics
            )
        )

    prompt = f"""
Generate exactly {TOPIC_CANDIDATE_COUNT} high-retention educational
YouTube Shorts topic ideas.

Audience:
{AUDIENCE}

Category:
{category}

Each idea must:

- create an immediate curiosity gap
- contain a surprising fact, mystery, misconception,
  comparison, or question
- be understandable by a non-expert
- be highly visual with real footage or photos
- have broad audience appeal
- have strong share/comment potential
- be specific enough for a 20-40 second Short
- be maximum 9 words
- be meaningfully different from the other ideas

Avoid generic ideas such as:

Amazing Space Facts
Cool Animal Facts
Interesting Science Facts

{avoid_block}

Return ONLY {TOPIC_CANDIDATE_COUNT} topics.

One topic per line.

No labels.
No explanations.
"""

    raw = _ollama(
        prompt
    )

    candidates = []

    for line in raw.splitlines():

        topic = _clean_candidate(
            line
        )

        if not topic:
            continue

        if topic.lower() in {
            item.lower()
            for item in candidates
        }:
            continue

        candidates.append(
            topic
        )

    return candidates[
        :TOPIC_CANDIDATE_COUNT
    ]


# ============================================================
# SELECT STRONGEST TOPIC
# ============================================================

def select_best_topic(
    candidates,
    category
):

    numbered = "\n".join(
        f"{index}. {topic}"
        for index, topic in enumerate(
            candidates,
            start=1
        )
    )

    prompt = f"""
You are selecting the strongest concept for a YouTube Short.

Category:
{category}

Candidates:

{numbered}

Judge each idea on:

- curiosity in the first second
- surprise
- broad audience appeal
- visual potential using real footage/photos
- ability to deliver a satisfying payoff in under 40 seconds
- share potential
- comment potential

Prefer a concrete and instantly understandable idea
over a broad subject.

Avoid misleading clickbait.

Return ONLY the number of the strongest candidate.
"""

    raw = _ollama(
        prompt
    )

    match = re.search(
        r"\b([1-9])\b",
        raw
    )

    if match:

        selected_index = (
            int(match.group(1))
            - 1
        )

        if (
            0
            <= selected_index
            < len(candidates)
        ):

            return candidates[
                selected_index
            ]

    # Safe fallback
    return candidates[0]


# ============================================================
# GENERATE TOPIC
# ============================================================

def generate_topic(
    category=None,
    return_category=False
):

    history = load_history()

    if category is None:

        category = pick_category(
            history
        )

    recent_topics = [
        entry.get(
            "topic",
            ""
        )
        for entry in history[-25:]
        if entry.get("topic")
    ]

    last_error = None

    for attempt in range(
        1,
        OLLAMA_MAX_RETRIES + 1
    ):

        try:

            candidates = (
                generate_candidates(
                    category,
                    recent_topics
                )
            )

            if len(candidates) < 2:

                raise ValueError(
                    "Only "
                    f"{len(candidates)} "
                    "usable topic candidate(s) returned."
                )

            topic = select_best_topic(
                candidates,
                category
            )

            if not topic:

                raise ValueError(
                    "Topic selector returned "
                    "an empty topic."
                )

            print(
                "Topic candidates:"
            )

            for candidate in candidates:

                marker = (
                    " <-- selected"
                    if candidate == topic
                    else ""
                )

                print(
                    f"  - {candidate}"
                    f"{marker}"
                )

            add_to_history(
                topic,
                category
            )

            if return_category:

                return (
                    topic,
                    category
                )

            return topic

        except Exception as exc:

            last_error = exc

            print(
                "Topic generation "
                f"attempt {attempt} "
                f"failed: {exc}"
            )

            if (
                attempt
                < OLLAMA_MAX_RETRIES
            ):

                time.sleep(
                    attempt * 2
                )

    raise RuntimeError(
        "Unable to generate a topic after "
        f"{OLLAMA_MAX_RETRIES} attempts: "
        f"{last_error}"
    )