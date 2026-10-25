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
    f"https://graph.instagram.com/"
    f"{INSTAGRAM_GRAPH_API_VERSION}"
)

UPLOAD_BASE_URL = (
    f"https://rupload.facebook.com/"
    f"ig-api-upload/"
    f"{INSTAGRAM_GRAPH_API_VERSION}"
)

REQUEST_TIMEOUT = 120
PROCESSING_TIMEOUT = 600
POLL_INTERVAL = 10


def _validate_config():

    if not INSTAGRAM_USER_ID:
        raise RuntimeError(
            "INSTAGRAM_USER_ID is not configured."
        )

    if not INSTAGRAM_ACCESS_TOKEN:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN is not configured."
        )


def _raise_for_instagram_error(response):

    try:
        data = response.json()
    except Exception:
        data = None

    if response.ok:
        return data

    if isinstance(data, dict):
        error = data.get("error", {})

        message = error.get(
            "message",
            response.text,
        )

        code = error.get("code")
        subcode = error.get("error_subcode")

        raise RuntimeError(
            "Instagram API error: "
            f"{message} "
            f"(code={code}, subcode={subcode})"
        )

    response.raise_for_status()


# ============================================================
# CREATE REEL CONTAINER
# ============================================================

def create_reel_container(
    caption,
):

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

    data = _raise_for_instagram_error(response)

    container_id = data.get("id")

    if not container_id:
        raise RuntimeError(
            "Instagram did not return a "
            "Reel container ID."
        )

    print(
        f"Instagram Reel container created: "
        f"{container_id}"
    )

    return container_id


# ============================================================
# UPLOAD LOCAL VIDEO
# ============================================================

def upload_video_file(
    container_id,
    video_file,
):

    if not os.path.exists(video_file):
        raise FileNotFoundError(
            f"Instagram video not found: {video_file}"
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
        "Uploading video file to Instagram..."
    )

    with open(video_file, "rb") as file_handle:

        response = requests.post(
            url,
            headers=headers,
            data=file_handle,
            timeout=300,
        )

    data = _raise_for_instagram_error(response)

    print(
        "Instagram video upload completed."
    )

    return data


# ============================================================
# CHECK PROCESSING STATUS
# ============================================================

def get_container_status(
    container_id,
):

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

    return _raise_for_instagram_error(response)


def wait_for_processing(
    container_id,
):

    print(
        "Waiting for Instagram to process Reel..."
    )

    started = time.time()

    while True:

        status_data = get_container_status(
            container_id
        )

        status_code = status_data.get(
            "status_code"
        )

        status_message = status_data.get(
            "status"
        )

        print(
            "Instagram processing status: "
            f"{status_code}"
        )

        if status_code == "FINISHED":

            print(
                "Instagram Reel processing finished."
            )

            return status_data

        if status_code in (
            "ERROR",
            "EXPIRED",
        ):

            raise RuntimeError(
                "Instagram Reel processing failed: "
                f"{status_message or status_code}"
            )

        if (
            time.time() - started
            > PROCESSING_TIMEOUT
        ):

            raise TimeoutError(
                "Instagram Reel processing timed out."
            )

        time.sleep(POLL_INTERVAL)


# ============================================================
# PUBLISH
# ============================================================

def publish_reel(
    container_id,
):

    url = (
        f"{GRAPH_BASE_URL}/"
        f"{INSTAGRAM_USER_ID}/media_publish"
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

    data = _raise_for_instagram_error(response)

    media_id = data.get("id")

    if not media_id:
        raise RuntimeError(
            "Instagram did not return "
            "a published media ID."
        )

    print(
        f"Instagram Reel published: {media_id}"
    )

    return data


# ============================================================
# COMPLETE UPLOAD FLOW
# ============================================================

def upload_reel(
    video_file,
    caption,
):

    _validate_config()

    container_id = create_reel_container(
        caption=caption,
    )

    upload_video_file(
        container_id=container_id,
        video_file=video_file,
    )

    wait_for_processing(
        container_id=container_id,
    )

    return publish_reel(
        container_id=container_id,
    )