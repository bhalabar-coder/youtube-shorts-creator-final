import os
import random
import math
import subprocess

from moviepy import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    concatenate_audioclips,
    TextClip,
    ColorClip,
    ImageClip,
)

from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    FPS,
    VIDEO_CODEC,
    AUDIO_CODEC,
    VIDEO_BITRATE,
    OUTPUT_CAPTIONS,
    ENABLE_BACKGROUND_MUSIC,
    BACKGROUND_MUSIC_VOLUME,
    MUSIC_DIR,
    TEMP_DIR,
)


# ============================================================
# CONSTANTS
# ============================================================

TRANSITION_DURATION = 0.35

ZOOM_MIN = 1.00
ZOOM_MAX = 1.08

CAPTION_FONT_SIZE = 72

CAPTION_Y = int(
    VIDEO_HEIGHT * 0.72
)

CAPTION_MARGIN = 70

PROGRESS_HEIGHT = 8


# ============================================================
# BASIC HELPERS
# ============================================================

def loop_clip_to_duration(
    clip,
    duration
):
    """
    Repeat a video clip until it reaches
    the requested duration.

    Works for both video clips and image clips.
    """

    if duration <= 0:
        raise ValueError(
            "Requested duration must be greater than 0."
        )

    # ImageClip may have no duration yet.
    if clip.duration is None:

        clip = clip.with_duration(
            duration
        )

        return clip

    if clip.duration <= 0:

        raise ValueError(
            "Clip has invalid duration."
        )

    # Already long enough
    if clip.duration >= duration:

        return clip.subclipped(
            0,
            duration
        )

    repetitions = (
        math.ceil(
            duration / clip.duration
        )
    )

    repeated_clips = []

    for _ in range(repetitions):

        repeated_clips.append(
            clip.copy()
        )

    result = concatenate_videoclips(
        repeated_clips,
        method="compose"
    )

    return result.subclipped(
        0,
        duration
    )

def clamp(value, minimum, maximum):

    return max(
        minimum,
        min(value, maximum)
    )


def ease_in_out(t):

    return (
        3 * t * t
        -
        2 * t * t * t
    )


# ============================================================
# VERTICAL VIDEO PREPARATION
# ============================================================

def prepare_vertical_clip(
    clip,
    duration
):
    """
    Converts any source media into a true
    1080x1920 vertical frame.

    No letterboxing.
    No pillarboxing.
    No black borders.
    """

    source_width, source_height = (
        clip.size
    )

    target_ratio = (
        VIDEO_WIDTH / VIDEO_HEIGHT
    )

    source_ratio = (
        source_width / source_height
    )

    # ========================================================
    # SOURCE TOO WIDE
    # ========================================================

    if source_ratio > target_ratio:

        new_width = int(
            source_height
            * target_ratio
        )

        x1 = (
            source_width
            - new_width
        ) / 2

        clip = clip.cropped(
            x1=x1,
            y1=0,
            x2=x1 + new_width,
            y2=source_height
        )

    # ========================================================
    # SOURCE TOO TALL
    # ========================================================

    else:

        new_height = int(
            source_width
            / target_ratio
        )

        y1 = (
            source_height
            - new_height
        ) / 2

        clip = clip.cropped(
            x1=0,
            y1=y1,
            x2=source_width,
            y2=y1 + new_height
        )

    # ========================================================
    # FORCE EXACT OUTPUT SIZE
    # ========================================================

    clip = clip.resized(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT
    )

    # ========================================================
    # PHOTO
    # ========================================================

    if clip.duration is None:

        clip = clip.with_duration(
            duration
        )

    return clip

# ============================================================
# KEN BURNS EFFECT
# ============================================================

def apply_zoom_effect(
    clip,
    direction="zoom_in",
):
    """
    Creates a subtle cinematic zoom.

    We intentionally keep the zoom small.
    Too much zoom looks unnatural.
    """

    original_size = clip.size

    def resize_function(t):

        progress = (
            t / clip.duration
            if clip.duration > 0
            else 0
        )

        progress = clamp(
            progress,
            0,
            1
        )

        progress = ease_in_out(
            progress
        )

        if direction == "zoom_out":

            scale = (
                ZOOM_MAX
                -
                (
                    (ZOOM_MAX - ZOOM_MIN)
                    * progress
                )
            )

        else:

            scale = (
                ZOOM_MIN
                +
                (
                    (ZOOM_MAX - ZOOM_MIN)
                    * progress
                )
            )

        return scale

    # MoviePy's dynamic resizing
    # keeps the effect lightweight.

    return clip.resized(
        lambda t: resize_function(t)
    )


# ============================================================
# PAN EFFECT
# ============================================================

def apply_pan_effect(
    clip,
    direction="pan_left",
):
    """
    Creates a horizontal pan while guaranteeing
    that the entire 1080x1920 frame remains covered.

    No black borders.
    """

    # --------------------------------------------------------
    # Make the clip slightly larger than the target frame.
    # --------------------------------------------------------

    oversized = clip.resized(
        1.08
    )

    width, height = oversized.size

    # --------------------------------------------------------
    # Make absolutely sure the clip is large enough.
    # --------------------------------------------------------

    if width < VIDEO_WIDTH:

        oversized = oversized.resized(
            width=VIDEO_WIDTH
        )

        width, height = oversized.size

    if height < VIDEO_HEIGHT:

        oversized = oversized.resized(
            height=VIDEO_HEIGHT
        )

        width, height = oversized.size

    # --------------------------------------------------------
    # Available horizontal movement.
    # --------------------------------------------------------

    max_x = max(
        0,
        width - VIDEO_WIDTH
    )

    max_y = max(
        0,
        height - VIDEO_HEIGHT
    )

    def position(t):

        if oversized.duration <= 0:

            progress = 0

        else:

            progress = (
                t / oversized.duration
            )

        progress = clamp(
            progress,
            0,
            1
        )

        progress = ease_in_out(
            progress
        )

        # ----------------------------------------------------
        # Horizontal pan
        # ----------------------------------------------------

        if direction == "pan_right":

            x = (
                -max_x
                * progress
            )

        else:

            x = (
                -max_x
                * (1 - progress)
            )

        # ----------------------------------------------------
        # Always vertically centered.
        # ----------------------------------------------------

        y = (
            -max_y / 2
        )

        return (
            x,
            y
        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # No black ColorClip.
    #
    # The oversized image itself must completely cover
    # the target frame.
    # --------------------------------------------------------

    return oversized.with_position(
        position
    )

# ============================================================
# SCENE EFFECT
# ============================================================

def apply_scene_animation(
    clip,
    animation,
):

    try:

        if animation == "zoom_in":

            return apply_zoom_effect(
                clip,
                "zoom_in"
            )

        if animation == "zoom_out":

            return apply_zoom_effect(
                clip,
                "zoom_out"
            )

        if animation == "pan_left":

            return apply_pan_effect(
                clip,
                "pan_left"
            )

        if animation == "pan_right":

            return apply_pan_effect(
                clip,
                "pan_right"
            )

    except Exception as exc:

        print(
            f"Animation failed: {exc}"
        )

    return clip


# ============================================================
# CAPTION PARSER
# ============================================================

def parse_srt(filename):

    if not os.path.exists(filename):

        return []

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as file:

        content = file.read()

    blocks = content.split(
        "\n\n"
    )

    captions = []

    for block in blocks:

        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if len(lines) < 3:

            continue

        try:

            timing = lines[1]

            start_text, end_text = (
                timing.split("-->")
            )

            start = parse_timestamp(
                start_text.strip()
            )

            end = parse_timestamp(
                end_text.strip()
            )

            text = " ".join(
                lines[2:]
            )

            captions.append(
                {
                    "start": start,
                    "end": end,
                    "text": text,
                }
            )

        except Exception:

            continue

    return captions


def parse_timestamp(value):

    value = value.replace(
        ",",
        "."
    )

    parts = value.split(":")

    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])

    return (
        hours * 3600
        +
        minutes * 60
        +
        seconds
    )


# ============================================================
# CAPTION CLIP
# ============================================================

def caption_has_emphasis(
    text
):

    important_words = {

        "never",
        "only",
        "secret",
        "largest",
        "smallest",
        "fastest",
        "deadliest",
        "oldest",
        "youngest",
        "million",
        "billion",
        "trillion",
        "impossible",
        "weird",
        "giant",
        "tiny",
    }

    words = [

        word
        .strip(
            ".,!?;:'\""
        )
        .lower()

        for word
        in text.split()
    ]

    has_number = any(

        any(
            char.isdigit()
            for char
            in word
        )

        for word
        in words
    )

    has_keyword = any(

        word
        in important_words

        for word
        in words
    )

    return (
        has_number
        or
        has_keyword
    )

def create_caption_clip(
    caption
):
    """
    Creates ONE caption layer.

    Captions are displayed ONLY at the bottom
    of the video.
    """

    text = caption["text"]

    if not text:
        return None

    try:

        text_clip = TextClip(
            text=text.upper(),

            font_size=CAPTION_FONT_SIZE,

            color=(
                "yellow"
                if caption_has_emphasis(
                    text
                )
                else "white"
            ),

            stroke_color="black",

            stroke_width=4,

            method="caption",

            size=(
                VIDEO_WIDTH
                - 2 * CAPTION_MARGIN,
                220
            ),

            text_align="center",
        )

        # ----------------------------------------------------
        # Position caption at bottom only
        # ----------------------------------------------------

        text_clip = (
            text_clip
            .with_start(
                caption["start"]
            )
            .with_end(
                caption["end"]
            )
            .with_position(
                (
                    "center",
                    CAPTION_Y
                )
            )
        )

        return text_clip

    except Exception as exc:

        print(
            f"Caption creation failed: {exc}"
        )

        return None

# ============================================================
# CAPTION OVERLAY
# ============================================================

def create_caption_overlays(
    captions
):

    overlays = []

    for caption in captions:

        clip = create_caption_clip(
            caption
        )

        if clip is not None:

            overlays.append(
                clip
            )

    return overlays


# ============================================================
# PROGRESS BAR
# ============================================================

def create_progress_bar(
    duration
):

    background = ColorClip(
        size=(
            VIDEO_WIDTH,
            PROGRESS_HEIGHT
        ),
        color=(40, 40, 40),
        duration=duration
    )

    def progress_width(t):

        progress = (
            t / duration
            if duration > 0
            else 0
        )

        return max(
            1,
            int(
                VIDEO_WIDTH
                * progress
            )
        )

    progress = ColorClip(
        size=(
            VIDEO_WIDTH,
            PROGRESS_HEIGHT
        ),
        color=(255, 255, 255),
        duration=duration
    )

    progress = progress.resized(
        lambda t: (
            progress_width(t),
            PROGRESS_HEIGHT
        )
    )

    progress = progress.with_position(
        (
            0,
            0
        )
    )

    background = background.with_position(
        (
            0,
            0
        )
    )

    return [
        background,
        progress
    ]


# ============================================================
# BACKGROUND MUSIC
# ============================================================

def find_music():

    if not ENABLE_BACKGROUND_MUSIC:

        return None

    if not os.path.exists(
        MUSIC_DIR
    ):

        return None

    supported = (
        ".mp3",
        ".wav",
        ".m4a",
        ".aac"
    )

    files = []

    for filename in os.listdir(
        MUSIC_DIR
    ):

        if filename.lower().endswith(
            supported
        ):

            files.append(
                os.path.join(
                    MUSIC_DIR,
                    filename
                )
            )

    if not files:

        return None

    return random.choice(
        files
    )


def add_background_music(
    video,
    duration
):

    music_file = find_music()

    if music_file is None:

        return video

    try:

        music = AudioFileClip(
            music_file
        )

        # Loop if necessary

        if music.duration < duration:

            repetitions = math.ceil(
                duration / music.duration
            )

            music_parts = [
                music.copy()
                for _ in range(
                    repetitions
                )
            ]

            music = concatenate_audioclips(
                music_parts
            )

        music = music.subclipped(
            0,
            duration
        )

        music = music.with_volume_scaled(
            BACKGROUND_MUSIC_VOLUME
        )

        current_audio = video.audio

        if current_audio is not None:

            combined_audio = (
                CompositeAudioClip(
                    [
                        current_audio,
                        music
                    ]
                )
            )

            video = video.with_audio(
                combined_audio
            )

        else:

            video = video.with_audio(
                music
            )

    except Exception as exc:

        print(
            f"Background music failed: {exc}"
        )

    return video


# ============================================================
# BUILD SCENES
# ============================================================

def calculate_scene_durations(
    total_duration,
    count
):
    """
    First visual cuts are intentionally faster.

    This makes the first few seconds feel
    significantly more active.
    """

    if count <= 0:

        return []

    if count == 1:

        return [
            total_duration
        ]

    weights = [
        0.55,
        0.75,
        0.90,
    ]

    while len(weights) < count:

        weights.append(
            1.0
        )

    weights = weights[
        :count
    ]

    total_weight = sum(
        weights
    )

    return [

        total_duration
        * weight
        / total_weight

        for weight
        in weights
    ]

def build_scene_clips(
    media_files,
    scenes,
    duration
):
    """
    Build all visual scenes so that the total
    visual duration matches the narration duration.

    Short videos are automatically repeated.
    Images remain on screen for the complete
    scene duration.
    """

    if not media_files:

        raise RuntimeError(
            "No media files available."
        )

    if not scenes:

        raise RuntimeError(
            "No scenes available."
        )

    clips = []

    # ========================================================
    # IMPORTANT
    #
    # We use the actual number of media files that
    # successfully downloaded.
    # ========================================================

    usable_count = len(
        media_files
    )

    if usable_count == 0:

        raise RuntimeError(
            "No usable scenes available."
        )

    scene_durations = (
        calculate_scene_durations(
            duration,
            usable_count
        )
    )

    print(
        "Scene durations: "
        +
        ", ".join(
            f"{value:.2f}s"
            for value
            in scene_durations
        )
    )

    # ========================================================
    # BUILD EACH SCENE
    # ========================================================

    for index in range(
        usable_count
    ):

        media = media_files[
            index
        ]

        scene_index = (
            media.get(
                "scene_index",
                index
            )
        )

        if (
            scene_index < 0
            or
            scene_index >= len(scenes)
        ):

            scene_index = min(
                index,
                len(scenes) - 1
            )

        scene = scenes[
            scene_index
        ]

        scene_duration = (
            scene_durations[
                index
            ]
        )

        filename = media[
            "file"
        ]

        media_type = media["type"]

        print(
            "\n--------------------------------"
        )

        print(
            f"Rendering scene "
            f"{index + 1}/{usable_count}"
        )

        print(
            f"Media: {filename}"
        )

        print(
            f"Type: {media_type}"
        )

        # ====================================================
        # VIDEO
        # ====================================================

        if media_type == "video":

            if not validate_video_file(
                filename
            ):

                print(
                    f"WARNING: Invalid video:"
                    f" {filename}"
                )

                continue

            try:

                clip = VideoFileClip(
                    filename
                )

            except Exception as exc:

                print(
                    f"Could not open video: "
                    f"{exc}"
                )

                continue

            # -----------------------------------------------
            # Prepare vertical format
            # -----------------------------------------------

            clip = prepare_vertical_clip(
                clip,
                scene_duration
            )

            # -----------------------------------------------
            # Short video?
            #
            # Example:
            #
            # Scene duration = 6 sec
            # Pexels video = 2 sec
            #
            # Result:
            #
            # 0-2 sec   video
            # 2-4 sec   video again
            # 4-6 sec   video again
            # -----------------------------------------------

            if clip.duration < scene_duration:

                print(
                    f"Video is shorter than "
                    f"scene duration "
                    f"({clip.duration:.2f}s). "
                    f"Looping it."
                )

                clip = loop_clip_to_duration(
                    clip,
                    scene_duration
                )

            else:

                # -------------------------------------------
                # Video is long enough.
                #
                # Start from a random position to make
                # repeated videos less predictable.
                # -------------------------------------------

                max_start = (
                    clip.duration
                    - scene_duration
                )

                if max_start > 0:

                    start = random.uniform(
                        0,
                        max_start
                    )

                else:

                    start = 0

                clip = clip.subclipped(
                    start,
                    start + scene_duration
                )

        # ====================================================
        # PHOTO
        # ====================================================

        else:

            print(
                "Using photo for entire "
                f"{scene_duration:.2f}s scene."
            )

            clip = ImageClip(
                filename
            )

            clip = prepare_vertical_clip(
                clip,
                scene_duration
            )

            clip = clip.with_duration(
                scene_duration
            )

        # ====================================================
        # ANIMATION
        # ====================================================

        animation = scene.get(
            "animation",
            "zoom_in"
        )

        print(
            f"Animation: {animation}"
        )

        try:

            clip = apply_scene_animation(
                clip,
                animation
            )

            if clip.size != (
                VIDEO_WIDTH,
                VIDEO_HEIGHT
            ):

                clip = clip.resized(
                    width=VIDEO_WIDTH,
                    height=VIDEO_HEIGHT
                )

        except Exception as exc:

            print(
                f"Animation failed: {exc}"
            )

            print(
                "Using static scene."
            )

        # ====================================================
        # FINAL SCENE DURATION
        # ====================================================

        clip = clip.with_duration(
            scene_duration
        )

        clips.append(
            clip
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    if not clips:

        raise RuntimeError(
            "All scenes failed to render."
        )

    total_duration = sum(
        clip.duration
        for clip in clips
    )

    print(
        "\n--------------------------------"
    )

    print(
        f"Created {len(clips)} scene clips."
    )

    print(
        f"Total visual duration: "
        f"{total_duration:.2f}s"
    )

    print(
        f"Target narration duration: "
        f"{duration:.2f}s"
    )

    return clips

# ============================================================
# ADD TRANSITIONS
# ============================================================

def concatenate_scenes(
    clips
):

    if len(clips) == 1:

        return clips[0]

    # Hard cuts are intentional.
    #
    # For short-form content they usually feel
    # faster and more energetic than applying
    # a crossfade to every scene.

    return concatenate_videoclips(
        clips,
        method="compose"
    )


# ============================================================
# FINAL VIDEO
# ============================================================

def build_video(
    media_files,
    scenes,
    audio_file,
    output_file
):

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    print(
        "\nPreparing final video..."
    )

    narration = AudioFileClip(
        audio_file
    )

    duration = narration.duration

    print(
        f"Narration duration: "
        f"{duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # Build scenes
    # --------------------------------------------------------

    clips = build_scene_clips(
        media_files,
        scenes,
        duration
    )

    # --------------------------------------------------------
    # Concatenate
    # --------------------------------------------------------

    print(
        "Joining scenes..."
    )

    video = concatenate_scenes(
        clips
    )

    # --------------------------------------------------------
    # Ensure exact duration
    # --------------------------------------------------------

    if video.duration < duration:

        print(
            f"Visual video is shorter than narration "
            f"({video.duration:.2f}s < {duration:.2f}s)."
        )

        print(
            "Looping the complete visual sequence."
        )

        video = loop_clip_to_duration(
            video,
            duration
        )

    else:

        video = video.subclipped(
            0,
            duration
        )

    # --------------------------------------------------------
    # Narration
    # --------------------------------------------------------

    video = video.with_audio(
        narration
    )

    # --------------------------------------------------------
    # Captions
    # --------------------------------------------------------

    captions = parse_srt(
        OUTPUT_CAPTIONS
    )

    print(
        f"Captions found: "
        f"{len(captions)}"
    )

    caption_layers = (
        create_caption_overlays(
            captions
        )
    )

    # --------------------------------------------------------
    # Progress bar
    # --------------------------------------------------------

    # progress_layers = (
    #     create_progress_bar(
    #         video.duration
    #     )
    # )

    # --------------------------------------------------------
    # Composite
    # --------------------------------------------------------

    layers = [
        video
    ]

    layers.extend(
        caption_layers
    )

    final_video = CompositeVideoClip(
        layers,
        size=(
            VIDEO_WIDTH,
            VIDEO_HEIGHT
        )
    )

    final_video = final_video.with_duration(
        video.duration
    )

    # --------------------------------------------------------
    # Background music
    # --------------------------------------------------------

    final_video = add_background_music(
        final_video,
        video.duration
    )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    print(
        "\nExporting:"
    )

    print(
        output_file
    )

    final_video.write_videofile(
        output_file,
        fps=FPS,
        codec=VIDEO_CODEC,
        audio_codec=AUDIO_CODEC,
        bitrate=VIDEO_BITRATE,
        threads=4,
        preset="medium",
    )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    try:

        narration.close()

        video.close()

        final_video.close()

        for clip in clips:

            clip.close()

    except Exception:

        pass

    print(
        "\nVideo rendering completed."
    )

def validate_video_file(filename):

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filename,
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:

            print(
                "FFprobe validation failed:"
            )

            print(
                result.stderr
            )

            return False

        return True

    except Exception as exc:

        print(
            f"FFprobe validation error: {exc}"
        )

        return False