import os
import re
import time
from pathlib import Path

import requests

from config import PEXELS_API_KEY, PIXABAY_API_KEY, CLIPS_DIR


PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
PIXABAY_PHOTO_URL = "https://pixabay.com/api/"

DOWNLOAD_TIMEOUT = (30, 180)
MAX_DOWNLOAD_RETRIES = 3
CHUNK_SIZE = 1024 * 1024
MAX_RESULTS_PER_QUERY = 6
MAX_QUERY_COUNT = 5

pexels_session = requests.Session()
pexels_session.headers.update({
    "Authorization": PEXELS_API_KEY or "",
    "User-Agent": "AI-YouTube-Shorts-Generator/1.0",
})

pixabay_session = requests.Session()
pixabay_session.headers.update({
    "User-Agent": "AI-YouTube-Shorts-Generator/1.0",
})


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
    "from", "had", "has", "have", "he", "her", "his", "in", "into",
    "is", "it", "its", "of", "on", "or", "our", "she", "that", "the",
    "their", "them", "they", "this", "to", "was", "were", "with", "you",
    "your", "can", "could", "would", "will", "than", "then", "these",
    "those", "very", "more", "most", "much", "many", "some", "about",
}


def validate_pexels_key():
    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is not configured. Get a free key at "
            "https://www.pexels.com/api/ and set it as a secret/environment variable."
        )


def _tokenize(text):
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def _clean_query(query):
    return " ".join(str(query or "").strip().split())


def normalize_search_queries(query):
    """Build progressively broader stock-search queries from one phrase."""
    query = _clean_query(query).lower()
    if not query:
        return []

    queries = [query]
    removable = {
        "closeup", "close-up", "cinematic", "footage", "video", "real",
        "large", "giant", "dramatic", "photorealistic", "vertical",
    }
    words = [word for word in query.split() if word not in removable]

    if words:
        simplified = " ".join(words)
        if simplified not in queries:
            queries.append(simplified)
    if len(words) > 3:
        candidate = " ".join(words[:3])
        if candidate not in queries:
            queries.append(candidate)
    if len(words) > 2:
        candidate = " ".join(words[:2])
        if candidate not in queries:
            queries.append(candidate)
    if words and words[0] not in queries:
        queries.append(words[0])

    return queries[:MAX_QUERY_COUNT]


def build_scene_queries(scene):
    """Use the AI scene planner's alternatives first, then safe broader fallbacks."""
    queries = []

    for value in scene.get("search_queries") or []:
        value = _clean_query(value)
        if value and value.lower() not in {q.lower() for q in queries}:
            queries.append(value)

    primary = _clean_query(scene.get("search") or scene.get("visual_query"))
    if primary and primary.lower() not in {q.lower() for q in queries}:
        queries.insert(0, primary)

    if primary:
        for value in normalize_search_queries(primary):
            if value.lower() not in {q.lower() for q in queries}:
                queries.append(value)

    return queries[:MAX_QUERY_COUNT]


# ============================================================
# PEXELS
# ============================================================

def search_pexels_videos(query, orientation="portrait"):
    validate_pexels_key()
    response = pexels_session.get(
        PEXELS_VIDEO_URL,
        params={
            "query": query,
            "orientation": orientation,
            "size": "large",
            "per_page": MAX_RESULTS_PER_QUERY,
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
            "per_page": MAX_RESULTS_PER_QUERY,
            "page": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("photos", [])


def select_pexels_video_file(video):
    candidates = []
    for item in video.get("video_files", []):
        link = item.get("link")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        file_type = item.get("file_type", "")
        if not link or width <= 0 or height <= 0:
            continue
        if file_type and file_type != "video/mp4":
            continue
        candidates.append({"link": link, "width": width, "height": height})

    if not candidates:
        return None

    # Prefer portrait, then a rendition close to 1080x1920 without requiring it.
    candidates.sort(
        key=lambda item: (
            0 if item["height"] >= item["width"] else 1,
            abs(item["width"] - 1080) + abs(item["height"] - 1920),
        )
    )
    return candidates[0]


def collect_pexels_video_candidates(query, query_rank):
    candidates = []
    seen = set()

    for orientation in ("portrait", "landscape"):
        try:
            videos = search_pexels_videos(query, orientation)
        except Exception as exc:
            print(f"Pexels {orientation} video search failed for '{query}': {exc}")
            continue

        for api_rank, video in enumerate(videos):
            source_id = video.get("id")
            if source_id in seen:
                continue
            selected = select_pexels_video_file(video)
            if not selected:
                continue
            seen.add(source_id)
            candidates.append({
                "type": "video",
                "url": selected["link"],
                "width": selected["width"],
                "height": selected["height"],
                "duration": video.get("duration"),
                "source": "pexels",
                "source_id": source_id,
                "source_url": video.get("url"),
                "matched_query": query,
                "query_rank": query_rank,
                "api_rank": api_rank,
                "metadata_text": query,
            })

    return candidates


def collect_pexels_photo_candidates(query, query_rank):
    try:
        photos = search_pexels_photos(query)
    except Exception as exc:
        print(f"Pexels photo search failed for '{query}': {exc}")
        return []

    candidates = []
    for api_rank, photo in enumerate(photos):
        source = photo.get("src", {})
        url = source.get("large2x") or source.get("large") or source.get("original")
        if not url:
            continue
        candidates.append({
            "type": "photo",
            "url": url,
            "width": photo.get("width"),
            "height": photo.get("height"),
            "source": "pexels",
            "source_id": photo.get("id"),
            "source_url": photo.get("url"),
            "matched_query": query,
            "query_rank": query_rank,
            "api_rank": api_rank,
            "metadata_text": query,
        })
    return candidates


# ============================================================
# PIXABAY
# ============================================================

def collect_pixabay_video_candidates(query, query_rank):
    if not PIXABAY_API_KEY:
        return []

    try:
        response = pixabay_session.get(
            PIXABAY_VIDEO_URL,
            params={"key": PIXABAY_API_KEY, "q": query, "per_page": MAX_RESULTS_PER_QUERY},
            timeout=30,
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])
    except Exception as exc:
        print(f"Pixabay video search failed for '{query}': {exc}")
        return []

    candidates = []
    for api_rank, hit in enumerate(hits):
        renditions = hit.get("videos", {})
        selected = None
        for quality in ("large", "medium", "small", "tiny"):
            item = renditions.get(quality)
            if item and item.get("url"):
                selected = item
                break
        if not selected:
            continue
        candidates.append({
            "type": "video",
            "url": selected["url"],
            "width": selected.get("width"),
            "height": selected.get("height"),
            "duration": hit.get("duration"),
            "source": "pixabay",
            "source_id": hit.get("id"),
            "source_url": hit.get("pageURL"),
            "matched_query": query,
            "query_rank": query_rank,
            "api_rank": api_rank,
            "metadata_text": f"{query} {hit.get('tags', '')}",
        })
    return candidates


def collect_pixabay_photo_candidates(query, query_rank):
    if not PIXABAY_API_KEY:
        return []

    try:
        response = pixabay_session.get(
            PIXABAY_PHOTO_URL,
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "per_page": MAX_RESULTS_PER_QUERY,
            },
            timeout=30,
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])
    except Exception as exc:
        print(f"Pixabay photo search failed for '{query}': {exc}")
        return []

    candidates = []
    for api_rank, hit in enumerate(hits):
        url = hit.get("largeImageURL") or hit.get("webformatURL")
        if not url:
            continue
        candidates.append({
            "type": "photo",
            "url": url,
            "width": hit.get("imageWidth"),
            "height": hit.get("imageHeight"),
            "source": "pixabay",
            "source_id": hit.get("id"),
            "source_url": hit.get("pageURL"),
            "matched_query": query,
            "query_rank": query_rank,
            "api_rank": api_rank,
            "metadata_text": f"{query} {hit.get('tags', '')}",
        })
    return candidates


# ============================================================
# RELEVANCE RANKING
# ============================================================

def _candidate_score(candidate, scene):
    """Cheap relevance ranking designed for GitHub-hosted runners.

    No extra paid service/model is used. The scene planner (Ollama) creates
    several literal queries/keywords; this scorer combines those semantics
    with provider relevance order, metadata overlap, portrait suitability,
    and resolution.
    """
    narration_tokens = _tokenize(scene.get("text"))
    keyword_tokens = _tokenize(" ".join(scene.get("visual_keywords") or []))
    target_tokens = narration_tokens | keyword_tokens

    candidate_tokens = _tokenize(candidate.get("metadata_text"))
    matched_tokens = _tokenize(candidate.get("matched_query"))

    overlap = len(target_tokens & candidate_tokens)
    query_overlap = len(target_tokens & matched_tokens)

    query_rank = int(candidate.get("query_rank") or 0)
    api_rank = int(candidate.get("api_rank") or 0)
    width = int(candidate.get("width") or 0)
    height = int(candidate.get("height") or 0)

    score = 0.0
    score += overlap * 8.0
    score += query_overlap * 12.0
    score += max(0, 24 - query_rank * 5)     # planner's first query is most specific
    score += max(0, 12 - api_rank * 2)       # provider relevance order still matters

    if height >= width and width > 0:
        score += 12
    if width >= 720 or height >= 1280:
        score += 6
    if candidate.get("type") == "video":
        score += 8

    # Slightly prefer Pexels when scores tie because portrait video coverage is better.
    if candidate.get("source") == "pexels":
        score += 1

    return score


def _dedupe_candidates(candidates, used_media_ids):
    unique = []
    seen = set()
    used_media_ids = used_media_ids or set()

    for candidate in candidates:
        key = (candidate.get("source"), candidate.get("source_id"))
        if key != (None, None) and (key in seen or key in used_media_ids):
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def get_media_for_scene(scene, used_media_ids=None):
    """Search multiple queries/providers and pick the highest-scoring candidate."""
    used_media_ids = used_media_ids if used_media_ids is not None else set()
    queries = build_scene_queries(scene)

    if not queries:
        return None

    print("Search queries: " + " | ".join(queries))

    video_candidates = []
    for query_rank, query in enumerate(queries):
        print(f"  Searching video candidates for: {query}")
        video_candidates.extend(collect_pexels_video_candidates(query, query_rank))
        video_candidates.extend(collect_pixabay_video_candidates(query, query_rank))

    video_candidates = _dedupe_candidates(video_candidates, used_media_ids)
    if video_candidates:
        for candidate in video_candidates:
            candidate["relevance_score"] = _candidate_score(candidate, scene)
        video_candidates.sort(key=lambda item: item["relevance_score"], reverse=True)
        best = video_candidates[0]
        print(
            f"  Selected {best['source']} video, score={best['relevance_score']:.1f}, "
            f"query='{best['matched_query']}', size={best.get('width')}x{best.get('height')}"
        )
        return best

    # A tightly matching still is better than unrelated motion. MoviePy animates it.
    photo_candidates = []
    for query_rank, query in enumerate(queries):
        print(f"  Searching photo candidates for: {query}")
        photo_candidates.extend(collect_pexels_photo_candidates(query, query_rank))
        photo_candidates.extend(collect_pixabay_photo_candidates(query, query_rank))

    photo_candidates = _dedupe_candidates(photo_candidates, used_media_ids)
    if photo_candidates:
        for candidate in photo_candidates:
            candidate["relevance_score"] = _candidate_score(candidate, scene)
        photo_candidates.sort(key=lambda item: item["relevance_score"], reverse=True)
        best = photo_candidates[0]
        print(
            f"  Selected {best['source']} photo, score={best['relevance_score']:.1f}, "
            f"query='{best['matched_query']}'"
        )
        return best

    print("  No stock media found for this scene.")
    return None


# Backwards-compatible helper used by older callers/tests.
def get_media(query, used_media_ids=None):
    return get_media_for_scene(
        {"text": query, "search": query, "search_queries": [query], "visual_keywords": []},
        used_media_ids=used_media_ids,
    )


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
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
                response.raise_for_status()
                expected_size = response.headers.get("Content-Length")
                expected_size = int(expected_size) if expected_size else None

                with open(temp_filename, "wb") as output:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            output.write(chunk)

            actual_size = os.path.getsize(temp_filename)
            print(f"    Downloaded: {actual_size / 1024 / 1024:.2f} MB")

            if expected_size and actual_size != expected_size:
                raise IOError(f"Incomplete download: {actual_size} != {expected_size} bytes")
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

    raise RuntimeError(f"Unable to download media after {MAX_DOWNLOAD_RETRIES} attempts.")


# ============================================================
# DOWNLOAD SCENE MEDIA
# ============================================================

def download_scene_media(scenes):
    """Prepare one best-matching free stock visual per scene.

    Flow:
      Ollama scene planner -> multiple literal search queries ->
      Pexels + Pixabay candidates -> local relevance ranking -> MoviePy.

    This intentionally has no hosted AI-video dependency, so the twice-daily
    GitHub Actions workflow can remain free and reliable.
    """
    Path(CLIPS_DIR).mkdir(parents=True, exist_ok=True)

    media_files = []
    used_media_ids = set()

    for index, scene in enumerate(scenes, start=1):
        print("\n--------------------------------")
        print(f"SCENE {index}")
        print(f"Narration: {scene.get('text', '')}")

        media = get_media_for_scene(scene, used_media_ids=used_media_ids)
        if not media:
            print("No media found. Skipping scene.")
            continue

        media_key = (media.get("source"), media.get("source_id"))
        if media_key != (None, None):
            used_media_ids.add(media_key)

        extension = ".mp4" if media["type"] == "video" else ".jpg"
        filename = os.path.join(CLIPS_DIR, f"scene_{index}_stock{extension}")

        try:
            download_media(media, filename)
            media_files.append({
                "scene_index": index - 1,
                "file": filename,
                "type": media["type"],
                "source": media.get("source"),
                "source_url": media.get("source_url"),
                "source_id": media.get("source_id"),
                "query": scene.get("search"),
                "matched_query": media.get("matched_query"),
                "relevance_score": media.get("relevance_score"),
            })
            print(f"Scene {index} ready from {media.get('source')}.")
        except Exception as exc:
            print(f"Scene {index} download failed: {exc}")

    return media_files
