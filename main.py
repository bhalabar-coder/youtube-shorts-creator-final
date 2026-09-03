import argparse
import asyncio
import random
import re
import shutil

from agents.topic_agent import generate_topic
from agents.script_agent import (
    generate_script,
    review_script,
    generate_title,
)
from agents.scene_agent import generate_scene_plan
from agents.media_agent import download_scene_media
from agents.voice_agent import generate_voice
from agents.caption_agent import create_captions
from agents.video_agent import build_video
from agents.youtube_agent import upload_video, post_first_comment

from config import (
    OUTPUT_AUDIO,
    OUTPUT_VIDEO,
    CLIPS_DIR,
    TOPIC_CATEGORIES,
    ensure_output_dirs,
)


def clean_youtube_description(text):

    if not text:
        return ""

    text = re.sub(r"\*\*", "", text)

    lines = []

    blocked_patterns = [
        r"sound suggestion\s*:",
        r"sound effect\s*:",
        r"music suggestion\s*:",
        r"music\s*:",
        r"visual suggestion\s*:",
        r"visual\s*:",
        r"scene suggestion\s*:",
        r"animation\s*:",
        r"sfx\s*:",
    ]

    for line in text.splitlines():

        lower = line.lower().strip()

        if any(re.search(pattern, lower) for pattern in blocked_patterns):
            continue

        if re.match(r"^\s*\{.*(sound|sfx|music).*?\}\s*$", lower):
            continue

        lines.append(line.strip())

    text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# A few CTA variants so every single description doesn't read
# identically — rotated at random per upload.
DESCRIPTION_CTAS = [
    "\U0001F4AC Drop a comment — what surprised you most?",
    "\U0001F4AC Comment your favorite fact from this one!",
    "\U0001F914 Did you already know this? Let us know below.",
]

FOLLOW_CTA = "\U0001F514 Follow for a new fact every day."


def build_hashtags(
    topic,
    category
):
    """
    #Shorts is the single most important tag for landing in the
    Shorts feed, followed by a couple of topic-specific hashtags for
    search/discovery. Built from the category so it stays relevant
    across all ~90+ TOPIC_CATEGORIES without needing a manual mapping.
    """

    words = re.findall(
        r"[a-zA-Z']+",
        category
    )

    topic_tags = []

    for word in words:

        word = word.lower()

        if len(word) < 4 or word in ("and", "the"):
            continue

        tag = "#" + word.capitalize()

        if tag not in topic_tags:
            topic_tags.append(tag)

    hashtags = (
        ["#Shorts"]
        + topic_tags[:3]
        + ["#DidYouKnow", "#Facts"]
    )

    # dedupe while preserving order
    seen = set()
    deduped = []

    for tag in hashtags:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            deduped.append(tag)

    return " ".join(deduped[:6])


def build_full_description(
    script,
    topic,
    category
):

    body = clean_youtube_description(script)

    hashtags = build_hashtags(topic, category)

    cta = random.choice(DESCRIPTION_CTAS)

    parts = [
        part
        for part in (body, hashtags, f"{cta}\n{FOLLOW_CTA}")
        if part
    ]

    return "\n\n".join(parts).strip()[:5000]


def build_first_comment(
    topic
):
    """
    Posted immediately after upload to seed engagement before real
    viewers arrive. Kept as a simple template (no LLM call) so it
    never becomes a point of failure in the pipeline.
    """

    templates = [
        f"What's the wildest thing you know about {topic}? \U0001F447",
        "Which part surprised you most — timestamp it below! \U0001F440",
        f"Rate this {topic} fact 1-10 in the comments \U0001F447",
    ]

    return random.choice(templates)


def build_tags(
    topic,
    category
):

    words = re.findall(
        r"[a-zA-Z']+",
        f"{topic} {category}"
    )

    unique = []

    for word in words:

        word = (
            word.lower()
        )

        if (
            len(word) >= 4
            and
            word not in unique
        ):

            unique.append(
                word
            )

    return (
        unique[:8]
        +
        [
            "shorts",
            "educational shorts",
            "interesting facts",
            "did you know",
            category.lower(),
        ]
    )


def parse_args():

    parser = argparse.ArgumentParser(
        description="Generate and upload an AI YouTube Short."
    )

    parser.add_argument(
        "--category",
        choices=TOPIC_CATEGORIES,
        default=None,
        help="Force a specific topic category instead of random rotation.",
    )

    parser.add_argument(
        "--topic",
        default=None,
        help="Skip topic generation and use this exact topic.",
    )

    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Build the video locally but skip the YouTube upload step.",
    )

    return parser.parse_args()


def main():

    args = parse_args()

    ensure_output_dirs()

    print("=" * 70)
    print("        AI YOUTUBE SHORTS GENERATOR")
    print("=" * 70)

    # ========================================================
    # TOPIC
    # ========================================================

    print("\n[1/8] Generating topic...")

    if args.topic:
        topic = args.topic
        category = args.category or "custom"
    else:
        topic, category = (
            generate_topic(
                category=args.category,
                return_category=True,
            )
        )

    print(f"TOPIC: {topic}")
    print(f"CATEGORY: {category}")

    # ========================================================
    # SCRIPT
    # ========================================================

    print("\n[2/8] Generating script...")

    script = generate_script(topic)

    script = review_script(
        topic,
        script
    )

    print(f"\nSCRIPT:\n{script}")

    # ========================================================
    # SCENE PLAN
    # ========================================================

    print("\n[3/8] Creating scene plan...")

    scenes = generate_scene_plan(topic, script)

    print(f"Created {len(scenes)} scenes.")

    for scene in scenes:

        print(f"\nScene {scene['scene']}")
        print(f"Visual: {scene.get('search')}")
        print(f"Animation: {scene.get('animation')}")

    # ========================================================
    # VOICE
    # ========================================================

    print("\n[4/8] Generating narration...")

    asyncio.run(generate_voice(script, OUTPUT_AUDIO))

    # ========================================================
    # CAPTIONS
    # ========================================================

    print("\n[5/8] Generating captions...")

    create_captions(OUTPUT_AUDIO)

    # ========================================================
    # MEDIA
    # ========================================================

    print("\n[6/8] Searching and downloading media...")

    media_files = download_scene_media(scenes)

    if not media_files:
        raise RuntimeError("No media could be downloaded.")

    print(f"Downloaded {len(media_files)} media files.")

    # ========================================================
    # VIDEO
    # ========================================================

    print("\n[7/8] Creating final video...")

    build_video(media_files, scenes, OUTPUT_AUDIO, OUTPUT_VIDEO)

    # ========================================================
    # YOUTUBE
    # ========================================================

    if args.no_upload:

        print("\n[8/8] Skipping upload (--no-upload).")

    else:

        print("\n[8/8] Uploading to YouTube...")

        full_description = (
            build_full_description(
                script,
                topic,
                category,
            )
        )

        youtube_title = (
            generate_title(
                topic,
                script
            )
        )

        tags = build_tags(
            topic,
            category
        )

        print(
            f"YouTube title: "
            f"{youtube_title}"
        )

        response = upload_video(
            OUTPUT_VIDEO,
            title=youtube_title,
            description=full_description,
            tags=tags,
        )

        post_first_comment(
            response["id"],
            build_first_comment(topic),
        )

    # ========================================================
    # CLEANUP (downloaded stock clips don't need to stick around)
    # ========================================================

    shutil.rmtree(CLIPS_DIR, ignore_errors=True)

    print("\n" + "=" * 70)
    print("                    COMPLETED")
    print("=" * 70)
    print(f"\nVideo: {OUTPUT_VIDEO}")


if __name__ == "__main__":
    main()