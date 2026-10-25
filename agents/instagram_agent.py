import os
import time
import requests

from config import (
    INSTAGRAM_USER_ID,
    INSTAGRAM_ACCESS_TOKEN,
    INSTAGRAM_GRAPH_API_VERSION,
    INSTAGRAM_SHARE_TO_FEED,
)


GRAPH_BASE_URL = (
    f"https://graph.facebook.com/"
    f"{INSTAGRAM_GRAPH_API_VERSION}"
)

UPLOAD_BASE_URL = (
    f"https://rupload.facebook.com/"
    f"ig-api-upload/"
    f"{INSTAGRAM_GRAPH_API_VERSION}"
)

REQUEST_TIMEOUT = 120
UPLOAD_TIMEOUT = 300
PROCESSING_TIMEOUT = 600
POLL_INTERVAL = 10


# ============================================================
# CONFIG VALIDATION
# ============================================================

def _validate_config():

    if not INSTAGRAM_USER_ID:
        raise RuntimeError(
            "INSTAGRAM_USER_ID is not configured."
        )

    if not INSTAGRAM_ACCESS_TOKEN:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN is not configured."
        )

    if not INSTAGRAM_GRAPH_API_VERSION:
        raise RuntimeError(
            "INSTAGRAM_GRAPH_API_VERSION is not configured."
        )


# ============================================================
# INSTAGRAM ERROR HANDLING
# ============================================================

def _handle_response(response):

    try:
        data = response.json()
    except Exception:
        data = None

    if response.ok:

        if isinstance(data, dict) and data.get("error"):

            error = data["error"]

            raise RuntimeError(
                "Instagram API error: "
                f"{error.get('message')} "
                f"(code={error.get('code')}, "
                f"subcode={error.get('error_subcode')})"
            )

        return data

    if isinstance(data, dict):

        error = data.get("error", {})

        raise RuntimeError(
            "Instagram API error: "
            f"{error.get('message', response.text)} "
            f"(code={error.get('code')}, "
            f"subcode={error.get('error_subcode')})"
        )

    raise RuntimeError(
        "Instagram API request failed: "
        f"HTTP {response.status_code}: "
        f"{response.text}"
    )


# ============================================================
# VERIFY TOKEN / ACCOUNT
# ============================================================

def verify_instagram_connection():

    _validate_config()

    url = (
        f"{GRAPH_BASE_URL}/"
        f"{INSTAGRAM_USER_ID}"
    )

    params = {
        "fields": "id,username",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }

    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    data = _handle_response(response)

    print(
        "Instagram connection verified: "
        f"@{data.get('username', 'unknown')}"
    )

    return data


# ============================================================
# CREATE REEL CONTAINER
# ============================================================

def create_reel_container(caption):

    _validate_config()

    url = (
        f"{GRAPH_BASE_URL}/"
        f"{INSTAGRAM_USER_ID}/media"
    )

    payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption[:2200],
        "share_to_feed": (
            "true"
            if INSTAGRAM_SHARE_TO_FEED
            else "false"
        ),
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }

    response = requests.post(
        url,
        data=payload,
        timeout=REQUEST_TIMEOUT,
    )

    data = _handle_response(response)

    container_id = data.get("id")

    if not container_id:
        raise RuntimeError(
            "Instagram did not return "
            "a Reel container ID."
        )

    print(
        "Instagram Reel container created: "
        f"{container_id}"
    )

    return container_id


# ============================================================
# UPLOAD LOCAL MP4
# ============================================================

def upload_video_file(
    container_id,
    video_file,
):

    if not os.path.isfile(video_file):

        raise FileNotFoundError(
            f"Instagram video not found: "
            f"{video_file}"
        )

    file_size = os.path.getsize(video_file)

    if file_size <= 0:

        raise RuntimeError(
            "Instagram video file is empty."
        )

    url = (
        f"{UPLOAD_BASE_URL}/"
        f"{container_id}"
    )

    headers = {
        "Authorization": (
            f"OAuth {INSTAGRAM_ACCESS_TOKEN}"
        ),
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
    }

    print(
        "Uploading video to Instagram..."
    )

    with open(video_file, "rb") as file_handle:

        response = requests.post(
            url,
            headers=headers,
            data=file_handle,
            timeout=UPLOAD_TIMEOUT,
        )

    data = _handle_response(response)

    print(
        "Instagram video upload completed."
    )

    return data


# ============================================================
# GET CONTAINER STATUS
# ============================================================

def get_container_status(container_id):

    url = (
        f"{GRAPH_BASE_URL}/"
        f"{container_id}"
    )

    params = {
        "fields": "status_code,status",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }

    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    return _handle_response(response)


# ============================================================
# WAIT FOR VIDEO PROCESSING
# ============================================================

def wait_for_processing(container_id):

    print(
        "Waiting for Instagram "
        "to process Reel..."
    )

    start_time = time.time()

    while True:

        data = get_container_status(
            container_id
        )

        status_code = data.get(
            "status_code"
        )

        status_message = data.get(
            "status"
        )

        print(
            "Instagram processing status: "
            f"{status_code}"
        )

        if status_code == "FINISHED":

            print(
                "Instagram Reel "
                "processing finished."
            )

            return data

        if status_code in (
            "ERROR",
            "EXPIRED",
        ):

            raise RuntimeError(
                "Instagram Reel processing "
                "failed: "
                f"{status_message or status_code}"
            )

        elapsed = (
            time.time() - start_time
        )

        if elapsed > PROCESSING_TIMEOUT:

            raise TimeoutError(
                "Instagram Reel processing "
                "timed out."
            )

        time.sleep(
            POLL_INTERVAL
        )


# ============================================================
# PUBLISH REEL
# ============================================================

def publish_reel(container_id):

    url = (
        f"{GRAPH_BASE_URL}/"
        f"{INSTAGRAM_USER_ID}/"
        f"media_publish"
    )

    payload = {
        "creation_id": container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }

    response = requests.post(
        url,
        data=payload,
        timeout=REQUEST_TIMEOUT,
    )

    data = _handle_response(response)

    media_id = data.get("id")

    if not media_id:

        raise RuntimeError(
            "Instagram did not return "
            "published media ID."
        )

    print(
        "Instagram Reel published "
        f"successfully: {media_id}"
    )

    return data


# ============================================================
# COMPLETE INSTAGRAM REEL FLOW
# ============================================================

def upload_reel(
    video_file,
    caption,
):

    _validate_config()

    # First confirm that:
    # 1. token is valid
    # 2. token can access IG account
    # 3. INSTAGRAM_USER_ID is correct
    verify_instagram_connection()

    # Create resumable Reel container
    container_id = create_reel_container(
        caption=caption,
    )

    # Upload local MP4 directly to Meta
    upload_video_file(
        container_id=container_id,
        video_file=video_file,
    )

    # Wait for Meta processing
    wait_for_processing(
        container_id=container_id,
    )

    # Publish Reel
    return publish_reel(
        container_id=container_id,
    )