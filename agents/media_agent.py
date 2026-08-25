import os
import random
import time
import requests

from pathlib import Path

from config import (
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
    CLIPS_DIR,
)


PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"

PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
PIXABAY_PHOTO_URL = "https://pixabay.com/api/"


# ============================================================
# SETTINGS
# ============================================================

DOWNLOAD_TIMEOUT = (30, 180)

MAX_DOWNLOAD_RETRIES = 3

CHUNK_SIZE = 1024 * 1024


# ============================================================
# SESSIONS
# ============================================================

pexels_session = requests.Session()

pexels_session.headers.update({
    "Authorization": PEXELS_API_KEY or "",
    "User-Agent": "AI-YouTube-Shorts-Generator/1.0"
})

pixabay_session = requests.Session()

pixabay_session.headers.update({
    "User-Agent": "AI-YouTube-Shorts-Generator/1.0"
})


# ============================================================
# API KEY
# ============================================================

def validate_pexels_key():

    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is not configured. Get a free key at "
            "https://www.pexels.com/api/ and set it in your .env file."
        )


# ============================================================
# PEXELS: VIDEO SEARCH
# ============================================================

def search_pexels_videos(query, orientation="portrait"):

    validate_pexels_key()

    response = pexels_session.get(
        PEXELS_VIDEO_URL,
        params={
            "query": query,
            "orientation": orientation,
            "size": "large",
            "per_page": 10,
            "page": 1,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get("videos", [])


def search_pexels_photos(query):

    validate_pexels_key()

    response = pexels_session.get(
        PEXELS_PHOTO_URL,
        params={
            "query": query,
            "orientation": "portrait",
            "size": "large",
            "per_page": 10,
            "page": 1,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get("photos", [])


def select_pexels_video_file(video):

    files = video.get("video_files", [])

    candidates = []

    for file in files:

        link = file.get("link")

        if not link:
            continue

        width = file.get("width", 0)
        height = file.get("height", 0)
        file_type = file.get("file_type", "")

        if file_type and file_type != "video/mp4":
            continue

        if width <= 0 or height <= 0:
            continue

        candidates.append({
            "link": link,
            "width": width,
            "height": height,
        })

    if not candidates:
        return None

    portrait = [
        item for item in candidates
        if item["height"] >= item["width"]
    ]

    if portrait:
        candidates = portrait

    suitable = [
        item for item in candidates
        if item["width"] >= 720 and item["height"] >= 1280
    ]

    if suitable:
        candidates = suitable

    candidates.sort(
        key=lambda item: (
            abs(item["width"] - 1080) + abs(item["height"] - 1920)
        )
    )

    return candidates[0]


def find_pexels_video(query):

    candidates = []

    for orientation in (
        "portrait",
        "landscape"
    ):

        try:

            videos = (
                search_pexels_videos(
                    query,
                    orientation
                )
            )

            for video in videos:

                selected = (
                    select_pexels_video_file(
                        video
                    )
                )

                if selected:

                    candidates.append({

                        "type":
                            "video",

                        "url":
                            selected[
                                "link"
                            ],

                        "width":
                            selected[
                                "width"
                            ],

                        "height":
                            selected[
                                "height"
                            ],

                        "source":
                            "pexels",

                        "source_id":
                            video.get(
                                "id"
                            ),

                        "source_url":
                            video.get(
                                "url"
                            ),
                    })

        except Exception as exc:

            print(
                f"Pexels "
                f"{orientation} "
                "video search failed: "
                f"{exc}"
            )

    if not candidates:

        return None

    # Previously the first Pexels result was always selected.
    #
    # Pick from the strongest first few results instead.
    #
    # This gives more visual variety between generated videos.

    return random.choice(
        candidates[:5]
    )


def find_pexels_photo(query):

    try:

        photos = search_pexels_photos(query)

    except Exception as exc:

        print(f"Pexels photo search failed: {exc}")

        return None

    for photo in photos:

        source = photo.get("src", {})

        url = (
            source.get("large2x")
            or source.get("large")
            or source.get("original")
        )

        if url:

            return {
                "type": "photo",
                "url": url,
                "width": photo.get("width"),
                "height": photo.get("height"),
                "source": "pexels",
                "source_id": photo.get("id"),
                "source_url": photo.get("url"),
            }

    return None


# ============================================================
# PIXABAY (free fallback — widens coverage for niche topics that
# Pexels doesn't have footage for)
# ============================================================

def find_pixabay_video(query):

    if not PIXABAY_API_KEY:
        return None

    try:

        response = pixabay_session.get(
            PIXABAY_VIDEO_URL,
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "per_page": 10,
            },
            timeout=30,
        )

        response.raise_for_status()

        hits = response.json().get("hits", [])

    except Exception as exc:

        print(f"Pixabay video search failed: {exc}")

        return None

    for hit in hits:

        videos = hit.get("videos", {})

        # Pixabay doesn't offer native portrait video, so prefer the
        # largest rendition available; prepare_vertical_clip() in
        # video_agent.py will crop it to 1080x1920.
        for quality in ("large", "medium", "small", "tiny"):

            candidate = videos.get(quality)

            if candidate and candidate.get("url"):

                return {
                    "type": "video",
                    "url": candidate["url"],
                    "width": candidate.get("width"),
                    "height": candidate.get("height"),
                    "source": "pixabay",
                    "source_id": hit.get("id"),
                    "source_url": hit.get("pageURL"),
                }

    return None


def find_pixabay_photo(query):

    if not PIXABAY_API_KEY:
        return None

    try:

        response = pixabay_session.get(
            PIXABAY_PHOTO_URL,
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "per_page": 10,
            },
            timeout=30,
        )

        response.raise_for_status()

        hits = response.json().get("hits", [])

    except Exception as exc:

        print(f"Pixabay photo search failed: {exc}")

        return None

    for hit in hits:

        url = hit.get("largeImageURL") or hit.get("webformatURL")

        if url:

            return {
                "type": "photo",
                "url": url,
                "width": hit.get("imageWidth"),
                "height": hit.get("imageHeight"),
                "source": "pixabay",
                "source_id": hit.get("id"),
                "source_url": hit.get("pageURL"),
            }

    return None


# ============================================================
# SMART SEARCH (Pexels first, Pixabay as a free fallback)
# ============================================================

def get_media(query):

    print(f"Searching media: {query}")

    for finder, label in (
        (find_pexels_video, "Pexels video"),
        (find_pixabay_video, "Pixabay video"),
        (find_pexels_photo, "Pexels photo"),
        (find_pixabay_photo, "Pixabay photo"),
    ):

        media = finder(query)

        if media:

            print(f"  {label} selected: {media.get('width')}x{media.get('height')}")

            return media

        print(f"  {label} unavailable.")

    print("  No media found from any source.")

    return None


# ============================================================
# DOWNLOAD
# ============================================================

def download_media(media, filename):

    url = media["url"]

    temp_filename = filename + ".part"

    if os.path.exists(temp_filename):
        os.remove(temp_filename)

    if os.path.exists(filename):
        os.remove(filename)

    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):

        try:

            print(f"    Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}")

            with requests.get(
                url,
                stream=True,
                timeout=DOWNLOAD_TIMEOUT,
            ) as response:

                response.raise_for_status()

                expected_size = response.headers.get("Content-Length")

                if expected_size:
                    expected_size = int(expected_size)

                with open(temp_filename, "wb") as output:

                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):

                        if not chunk:
                            continue

                        output.write(chunk)

            actual_size = os.path.getsize(temp_filename)

            print(f"    Downloaded: {actual_size / 1024 / 1024:.2f} MB")

            if expected_size:

                print(f"    Expected: {expected_size / 1024 / 1024:.2f} MB")

                if actual_size != expected_size:
                    raise IOError(
                        f"Incomplete download: {actual_size} != {expected_size} bytes"
                    )

            if actual_size < 50_000:
                raise IOError("Downloaded file is suspiciously small.")

            os.replace(temp_filename, filename)

            return filename

        except Exception as exc:

            print(f"    Download failed: {exc}")

            if os.path.exists(temp_filename):
                os.remove(temp_filename)

            if attempt < MAX_DOWNLOAD_RETRIES:

                wait_time = attempt * 2

                print(f"    Retrying in {wait_time} seconds...")

                time.sleep(wait_time)

    raise RuntimeError(
        f"Unable to download media after {MAX_DOWNLOAD_RETRIES} attempts."
    )


# ============================================================
# DOWNLOAD SCENE MEDIA
# ============================================================

def download_scene_media(
    scenes
):

    Path(
        CLIPS_DIR
    ).mkdir(
        parents=True,
        exist_ok=True
    )

    media_files = []

    used_media_ids = set()

    for index, scene in enumerate(
        scenes,
        start=1
    ):

        query = (
            scene.get(
                "search"
            )
            or
            scene.get(
                "visual_query"
            )
        )

        if not query:

            print(
                f"Scene {index}: "
                "No media query."
            )

            continue

        print(
            "\n--------------------------------"
        )

        print(
            f"SCENE {index}"
        )

        print(
            f"Query: {query}"
        )

        media = None

        # ====================================================
        # AVOID EXACT DUPLICATE STOCK MEDIA
        # ====================================================

        for _ in range(3):

            candidate = get_media(
                query
            )

            if not candidate:

                break

            media_key = (

                candidate.get(
                    "source"
                ),

                candidate.get(
                    "source_id"
                ),
            )

            if (
                media_key
                not in used_media_ids
                or
                media_key
                == (None, None)
            ):

                media = candidate

                used_media_ids.add(
                    media_key
                )

                break

            print(
                "Duplicate stock asset "
                "detected; trying again."
            )

        if not media:

            print(
                "Skipping scene."
            )

            continue

        extension = (
            ".mp4"
            if media["type"]
            == "video"
            else ".jpg"
        )

        filename = os.path.join(
            CLIPS_DIR,
            f"scene_{index}"
            f"{extension}"
        )

        try:

            download_media(
                media,
                filename
            )

            media_files.append({

                # Very important.
                #
                # Keeps downloaded media linked
                # to its original scene even if
                # another scene failed to download.

                "scene_index":
                    index - 1,

                "file":
                    filename,

                "type":
                    media["type"],

                "source":
                    media.get(
                        "source"
                    ),

                "source_url":
                    media.get(
                        "source_url"
                    ),

                "source_id":
                    media.get(
                        "source_id"
                    ),

                "query":
                    query,
            })

            print(
                f"Scene {index} ready."
            )

        except Exception as exc:

            print(
                f"Scene {index} "
                f"failed: {exc}"
            )

    return media_files
