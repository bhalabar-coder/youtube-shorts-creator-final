import json
import os
import random
import re
import time
from difflib import SequenceMatcher

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
    """Choose a category using a 60/25/15 explore/exploit strategy."""
    recent_categories = [
        entry.get("category")
        for entry in history[-6:]
        if entry.get("category")
    ]
    fresh = [c for c in TOPIC_CATEGORIES if c not in recent_categories]
    candidates = fresh if fresh else list(TOPIC_CATEGORIES)

    try:
        stats = get_performance_stats() if get_performance_stats else None
    except Exception as exc:
        print(f"Could not use performance weighting: {exc}")
        stats = None

    by_category = (stats or {}).get("by_category") or {}
    ranked = sorted(
        [
            (category, by_category[category].get("performance_score", 1.0))
            for category in candidates
            if category in by_category
        ],
        key=lambda item: item[1],
        reverse=True,
    )

    if not ranked:
        return random.choice(candidates)

    roll = random.random()

    # 60%: proven winners, but still rotate among the strongest categories.
    if roll < 0.60:
        top_count = max(1, min(8, len(ranked)))
        top = ranked[:top_count]
        return random.choices(
            [item[0] for item in top],
            weights=[max(item[1], 0.05) for item in top],
            k=1,
        )[0]

    # 25%: adjacent/mid-performing known categories to preserve variety.
    if roll < 0.85:
        known = [item[0] for item in ranked]
        middle = known[max(1, len(known) // 4): max(2, (len(known) * 3) // 4)]
        return random.choice(middle or known)

    # 15%: exploration, favor categories with little/no performance history.
    unexplored = [c for c in candidates if c not in by_category]
    return random.choice(unexplored or candidates)


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
# DUPLICATE / VISUALABILITY QUALITY
# ============================================================

TOPIC_SIMILARITY_THRESHOLD = 0.78
MIN_TOPIC_VISUALABILITY = 65


def _topic_tokens(text):
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "how", "in", "is", "it", "of", "on", "or", "the", "this", "to",
        "what", "when", "where", "why", "with", "your", "you",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(token) > 2 and token not in stopwords
    }


def topic_similarity(left, right):
    """Conservative local similarity used to prevent near-duplicate topics."""
    left_text = " ".join(sorted(_topic_tokens(left)))
    right_text = " ".join(sorted(_topic_tokens(right)))
    if not left_text or not right_text:
        return 0.0

    left_tokens = set(left_text.split())
    right_tokens = set(right_text.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / max(len(union), 1)
    sequence = SequenceMatcher(None, left_text, right_text).ratio()
    return max(jaccard, sequence * 0.90)


def filter_similar_candidates(candidates, recent_topics):
    accepted = []
    for candidate in candidates:
        max_similarity = max(
            (topic_similarity(candidate, previous) for previous in recent_topics),
            default=0.0,
        )
        if max_similarity >= TOPIC_SIMILARITY_THRESHOLD:
            print(
                f"Skipping near-duplicate topic ({max_similarity:.0%} similar): "
                f"{candidate}"
            )
            continue
        accepted.append(candidate)
    return accepted


def score_visualability(candidates):
    """Score how realistically each topic can be illustrated with stock footage/photos."""
    if not candidates:
        return {}

    numbered = "\n".join(
        f"{index}. {topic}" for index, topic in enumerate(candidates, start=1)
    )
    prompt = f"""
Score each YouTube Shorts topic from 0 to 100 for VISUALABILITY using real
stock video/photos from libraries such as Pexels or Pixabay.

High score: concrete people, animals, places, machines, nature, space objects,
visible experiments, actions, or objects that can be shown directly.
Low score: abstract ideas, internal thoughts, invisible mechanisms, or topics
that would mostly require custom animation.

Topics:
{numbered}

Return exactly one line per topic in this format:
NUMBER|SCORE

No explanation.
"""
    try:
        raw = _ollama(prompt)
        scores = {}
        for line in raw.splitlines():
            match = re.search(r"^\s*(\d+)\s*\|\s*(\d{1,3})\s*$", line)
            if not match:
                continue
            index = int(match.group(1)) - 1
            score = max(0, min(100, int(match.group(2))))
            if 0 <= index < len(candidates):
                scores[candidates[index]] = score
        return {candidate: scores.get(candidate, 75) for candidate in candidates}
    except Exception as exc:
        print(f"Could not score topic visualability: {exc}")
        return {candidate: 75 for candidate in candidates}

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

            candidates = filter_similar_candidates(
                candidates,
                recent_topics,
            )

            if len(candidates) < 2:

                raise ValueError(
                    "Only "
                    f"{len(candidates)} "
                    "non-duplicate topic candidate(s) returned."
                )

            visualability_scores = score_visualability(candidates)
            visual_candidates = [
                candidate for candidate in candidates
                if visualability_scores.get(candidate, 0) >= MIN_TOPIC_VISUALABILITY
            ]

            if len(visual_candidates) < 2:
                ranked_visual = sorted(
                    candidates,
                    key=lambda item: visualability_scores.get(item, 0),
                    reverse=True,
                )
                visual_candidates = ranked_visual[:max(2, min(len(ranked_visual), 3))]

            topic = select_best_topic(
                visual_candidates,
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

                visual_score = visualability_scores.get(candidate, 0)
                print(
                    f"  - {candidate} [visualability={visual_score}%]"
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