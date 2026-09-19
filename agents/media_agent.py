import os
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


def find_pexels_video(query, used_media_ids=None):

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

    used_media_ids = used_media_ids or set()

    # Pexels returns results in relevance order.  Keep that order instead of
    # randomly selecting from the first few results, but skip assets already
    # used by another scene.
    for candidate in candidates:
        media_key = (candidate.get("source"), candidate.get("source_id"))
        if media_key not in used_media_ids or media_key == (None, None):
            return candidate

    return None


def find_pexels_photo(query, used_media_ids=None):

    try:

        photos = search_pexels_photos(query)

    except Exception as exc:

        print(f"Pexels photo search failed: {exc}")

        return None

    used_media_ids = used_media_ids or set()

    for photo in photos:

        media_key = ("pexels", photo.get("id"))

        if media_key in used_media_ids and media_key != (None, None):
            continue

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

def find_pixabay_video(query, used_media_ids=None):

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

    used_media_ids = used_media_ids or set()

    for hit in hits:

        media_key = ("pixabay", hit.get("id"))

        if media_key in used_media_ids and media_key != (None, None):
            continue

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


def find_pixabay_photo(query, used_media_ids=None):

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

    used_media_ids = used_media_ids or set()

    for hit in hits:

        media_key = ("pixabay", hit.get("id"))

        if media_key in used_media_ids and media_key != (None, None):
            continue

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

def normalize_search_queries(query):
    """
    Build progressively broader stock-search queries.

    Exact literal searches are attempted first.  If the stock library has no
    match, generic modifiers are removed before falling back to a shorter
    subject-focused query.
    """

    query = " ".join(str(query or "").lower().split())

    if not query:
        return []

    queries = [query]
    words = query.split()

    removable = {
        "closeup",
        "close-up",
        "cinematic",
        "footage",
        "video",
        "real",
        "large",
        "giant",
        "dramatic",
    }

    simplified = [word for word in words if word not in removable]

    if simplified:
        candidate = " ".join(simplified)
        if candidate not in queries:
            queries.append(candidate)

    if len(simplified) > 3:
        candidate = " ".join(simplified[:3])
        if candidate not in queries:
            queries.append(candidate)

    if len(simplified) > 2:
        candidate = " ".join(simplified[:2])
        if candidate not in queries:
            queries.append(candidate)

    # Keep at least the main subject as the final fallback.  In most generated
    # queries the first token is the subject because scene_agent is instructed
    # to put the visible subject first.
    if simplified:
        candidate = simplified[0]
        if candidate not in queries:
            queries.append(candidate)

    return queries[:5]


def get_media(
    query,
    used_media_ids=None
):
    """
    Find the most relevant free media for a scene.

    Priority:
      1. Exact/relevant stock video
      2. Broader stock video
      3. Exact/relevant stock photo
      4. Broader stock photo

    A relevant still image is preferable to unrelated video; video_agent can
    animate photos using the scene's pan/zoom animation.
    """

    used_media_ids = used_media_ids if used_media_ids is not None else set()
    search_queries = normalize_search_queries(query)

    print(f"Original media query: {query}")
    print("Search fallbacks: " + " -> ".join(search_queries))

    # First exhaust video possibilities across increasingly broad queries.
    video_finders = (
        (find_pexels_video, "Pexels video"),
        (find_pixabay_video, "Pixabay video"),
    )

    for search_query in search_queries:
        print(f"Searching video: {search_query}")

        for finder, label in video_finders:
            media = finder(search_query, used_media_ids=used_media_ids)

            if media:
                media["matched_query"] = search_query
                print(
                    f"  {label} selected: "
                    f"{media.get('width')}x{media.get('height')}"
                )
                return media

            print(f"  {label} unavailable.")

    # If there is no useful video, prefer a closely matching still image over
    # forcing an unrelated moving clip.
    photo_finders = (
        (find_pexels_photo, "Pexels photo"),
        (find_pixabay_photo, "Pixabay photo"),
    )

    for search_query in search_queries:
        print(f"Searching photo: {search_query}")

        for finder, label in photo_finders:
            media = finder(search_query, used_media_ids=used_media_ids)

            if media:
                media["matched_query"] = search_query
                print(
                    f"  {label} selected: "
                    f"{media.get('width')}x{media.get('height')}"
                )
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

        # get_media() now knows which assets were already selected, so it
        # can keep Pexels/Pixabay relevance ordering while skipping duplicates.
        media = get_media(
            query,
            used_media_ids=used_media_ids,
        )

        if media:
            media_key = (
                media.get("source"),
                media.get("source_id"),
            )

            if media_key != (None, None):
                used_media_ids.add(media_key)

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

                # Useful for debugging when the exact query had no stock
                # result and a broader fallback query was used.
                "matched_query":
                    media.get(
                        "matched_query",
                        query,
                    ),
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
