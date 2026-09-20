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
    break_script_into_scenes,
)
from agents.scene_agent import (
    generate_scene_plan,
    generate_scene_plan_with_sync,
)
from agents.media_agent import download_scene_media
from agents.voice_agent import generate_voice
from agents.caption_agent import create_captions
from agents.video_agent import build_video
from agents.youtube_agent import upload_video, post_first_comment
from agents.analytics_agent import add_to_performance_history

from config import (
    OUTPUT_AUDIO,
    OUTPUT_VIDEO,
    CLIPS_DIR,
    TOPIC_CATEGORIES,
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
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


# ============================================================
# CONTENT / MEDIA RETRY SETTINGS
# ============================================================
#
# Stock libraries will not contain suitable footage for every narration.
# Instead of terminating the whole workflow, retry a different script for
# the same topic first. Automatic runs can then move on to a new topic.

MAX_SCRIPT_RETRIES_PER_TOPIC = 3
MAX_TOPIC_RETRIES = 3
MIN_MEDIA_SCENES = 6


def validate_media_configuration():
    """Validate the free stock-video configuration."""

    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        raise RuntimeError(
            "No stock visual source is configured. Set PEXELS_API_KEY and/or "
            "PIXABAY_API_KEY in the environment/GitHub Actions secrets."
        )

    if not PEXELS_API_KEY:
        print("WARNING: PEXELS_API_KEY missing; using Pixabay only.")
    elif not PIXABAY_API_KEY:
        print("WARNING: PIXABAY_API_KEY missing; using Pexels only.")
    else:
        print("Pexels + Pixabay configured for multi-candidate visual search.")


def _clear_downloaded_media():
    """Remove stock files from a failed content attempt."""

    shutil.rmtree(
        CLIPS_DIR,
        ignore_errors=True,
    )

    ensure_output_dirs()


def generate_content_with_media(
    topic,
    category,
    max_script_retries=MAX_SCRIPT_RETRIES_PER_TOPIC,
):
    """
    Build script -> smart scene searches -> ranked free stock media for one topic.

    Voice and captions are deliberately NOT generated here. Visual generation
    runs first so narration/caption work is only performed after enough scene
    media has been prepared.
    """

    last_error = None

    for script_attempt in range(1, max_script_retries + 1):

        print("\n" + "=" * 70)
        print(
            f"SCRIPT ATTEMPT {script_attempt}/"
            f"{max_script_retries} FOR TOPIC"
        )
        print(f"Topic: {topic}")
        print("=" * 70)

        try:
            # ----------------------------------------------------
            # SCRIPT
            # ----------------------------------------------------
            print("\n[2/8] Generating script...")

            script, hook_style = generate_script(topic)
            script = review_script(topic, script)

            if not script or not script.strip():
                raise ValueError("Generated script is empty.")

            print(f"\nSCRIPT:\n{script}")
            print(f"Hook style used: {hook_style}")

            # ----------------------------------------------------
            # NARRATION BREAKDOWN
            # ----------------------------------------------------
            print(
                "\n[2.5/8] Breaking narration into visual moments..."
            )

            narration_moments = break_script_into_scenes(script)

            if not narration_moments:
                raise ValueError(
                    "Narration could not be split into visual moments."
                )

            print(
                f"Narration split into {len(narration_moments)} "
                "visual moments:"
            )

            for moment in narration_moments:
                print(
                    f"\n  Moment {moment['moment']}: "
                    f"\"{moment['narration'][:60]}...\""
                )
                print(
                    f"    Search: {moment['search_query']}"
                )

            # ----------------------------------------------------
            # SCENE PLAN
            # ----------------------------------------------------
            print(
                "\n[3/8] Creating scene plan "
                "(synced to narration)..."
            )

            scenes = generate_scene_plan_with_sync(
                topic,
                script,
                narration_moments,
            )

            if not scenes:
                raise ValueError(
                    "Scene generation returned no scenes."
                )

            print(f"Created {len(scenes)} scenes.")

            for scene in scenes:
                print(f"\nScene {scene['scene']}")
                print(f"Primary search: {scene.get('search')}")
                print(f"Search alternatives: {scene.get('search_queries')}")
                print(f"Visual keywords: {scene.get('visual_keywords')}")
                print(f"Animation: {scene.get('animation')}")

            # ----------------------------------------------------
            # VISUAL GENERATION / FALLBACK
            # ----------------------------------------------------
            # Search several highly specific Pexels/Pixabay queries for each scene,
            # collect multiple candidates, then rank them locally for narration fit.
            # Visuals are prepared before TTS/Whisper so a failed media attempt
            # does not waste narration/caption work.
            # ----------------------------------------------------
            print(
                "\n[4/8] Searching and ranking free stock visuals for each scene..."
            )

            _clear_downloaded_media()

            media_files = download_scene_media(scenes)
            media_count = len(media_files or [])

            print(
                f"\nMedia found for {media_count}/"
                f"{len(scenes)} scenes."
            )

            if media_count >= MIN_MEDIA_SCENES:
                print(
                    "\nSUCCESS: Sufficient relevant media found. "
                    "Continuing with narration and rendering."
                )

                return {
                    "topic": topic,
                    "category": category,
                    "script": script,
                    "hook_style": hook_style,
                    "scenes": scenes,
                    "media_files": media_files,
                }

            print(
                f"\nOnly {media_count} scene(s) had media; "
                f"at least {MIN_MEDIA_SCENES} are required."
            )

            if script_attempt < max_script_retries:
                print(
                    "Retrying with a different script for "
                    "the SAME topic..."
                )

            _clear_downloaded_media()

        except Exception as exc:
            last_error = exc

            print(
                f"\nContent attempt {script_attempt} failed: {exc}"
            )

            _clear_downloaded_media()

    print(
        "\nAll script attempts failed or had insufficient "
        f"media for topic: {topic}"
    )

    if last_error:
        print(f"Last error: {last_error}")

    return None


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
    validate_media_configuration()

    print("=" * 70)
    print("        AI YOUTUBE SHORTS GENERATOR")
    print("=" * 70)

    # ========================================================
    # TOPIC / SCRIPT / SCENE / MEDIA RETRY LOOP
    # ========================================================
    #
    # Automatic mode:
    #   topic 1 -> up to 3 scripts -> topic 2 -> ...
    #
    # Explicit --topic mode:
    #   preserve the requested topic and retry scripts only.
    #   We should not silently replace a topic explicitly chosen by user.
    # ========================================================

    content_result = None

    topic_attempt_limit = (
        1
        if args.topic
        else MAX_TOPIC_RETRIES
    )

    for topic_attempt in range(1, topic_attempt_limit + 1):

        print("\n" + "#" * 70)
        print(
            f"TOPIC ATTEMPT {topic_attempt}/"
            f"{topic_attempt_limit}"
        )
        print("#" * 70)

        # ----------------------------------------------------
        # TOPIC
        # ----------------------------------------------------
        print("\n[1/8] Generating topic...")

        if args.topic:
            topic = args.topic
            category = args.category or "custom"
        else:
            topic, category = generate_topic(
                category=args.category,
                return_category=True,
            )

        print(f"TOPIC: {topic}")
        print(f"CATEGORY: {category}")

        # ----------------------------------------------------
        # TRY MULTIPLE SCRIPTS FOR THIS TOPIC
        # ----------------------------------------------------
        content_result = generate_content_with_media(
            topic,
            category,
        )

        if content_result:
            print(
                "\nSUCCESS: Content and media are ready."
            )
            break

        if topic_attempt < topic_attempt_limit:
            print(
                "\nNo suitable media was found after all script "
                "attempts. Trying a NEW topic..."
            )

    # ========================================================
    # COMPLETE CONTENT FAILURE
    # ========================================================

    if not content_result:

        if args.topic:
            raise RuntimeError(
                "Unable to prepare enough scene visuals for the requested "
                f"topic after {MAX_SCRIPT_RETRIES_PER_TOPIC} "
                "different script attempts."
            )

        raise RuntimeError(
            "Unable to generate a usable Short with AI-video/stock visuals after "
            f"{MAX_TOPIC_RETRIES} topic attempts and "
            f"{MAX_SCRIPT_RETRIES_PER_TOPIC} script attempts "
            "per topic."
        )

    # ========================================================
    # USE THE SUCCESSFUL CONTENT ATTEMPT
    # ========================================================

    topic = content_result["topic"]
    category = content_result["category"]
    script = content_result["script"]
    hook_style = content_result["hook_style"]
    scenes = content_result["scenes"]
    media_files = content_result["media_files"]

    # ========================================================
    # VOICE
    # ========================================================

    print("\n[5/8] Generating narration...")

    asyncio.run(
        generate_voice(
            script,
            OUTPUT_AUDIO,
        )
    )

    # ========================================================
    # CAPTIONS
    # ========================================================

    print("\n[6/8] Generating captions...")

    create_captions(OUTPUT_AUDIO)

    # ========================================================
    # VIDEO
    # ========================================================

    print("\n[7/8] Creating final video...")

    build_video(
        media_files,
        scenes,
        OUTPUT_AUDIO,
        OUTPUT_VIDEO,
    )

    # ========================================================
    # YOUTUBE
    # ========================================================

    if args.no_upload:

        print("\n[8/8] Skipping upload (--no-upload).")

    else:

        print("\n[8/8] Uploading to YouTube...")

        full_description = build_full_description(
            script,
            topic,
            category,
        )

        youtube_title = generate_title(
            topic,
            script,
        )

        tags = build_tags(
            topic,
            category,
        )

        print(
            f"YouTube title: {youtube_title}"
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

        video_id = response["id"]
        narration_length = len(script.split())

        add_to_performance_history(
            video_id,
            youtube_title,
            topic,
            category,
            hook_style,
            narration_length,
        )

        print(
            f"\nVideo tracked for analytics: {video_id}"
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    shutil.rmtree(
        CLIPS_DIR,
        ignore_errors=True,
    )

    print("\n" + "=" * 70)
    print("                    COMPLETED")
    print("=" * 70)
    print(f"\nVideo: {OUTPUT_VIDEO}")


if __name__ == "__main__":
    main()
