import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import (
    YOUTUBE_CLIENT_SECRET_FILE,
    YOUTUBE_TOKEN_FILE,
    YOUTUBE_CATEGORY,
    YOUTUBE_PRIVACY_STATUS,
    YOUTUBE_MADE_FOR_KIDS,
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    # force-ssl is required to post the auto first-comment below.
    # NOTE: if you already have a cached credentials/token.json from
    # before this change, delete it and re-run setup_youtube_auth.py
    # once so the token picks up this new scope.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


# ============================================================
# AUTH (cached — only opens a browser once)
# ============================================================

def get_credentials():

    credentials = None

    if os.path.exists(YOUTUBE_TOKEN_FILE):

        credentials = Credentials.from_authorized_user_file(
            YOUTUBE_TOKEN_FILE,
            SCOPES
        )

    if credentials and credentials.expired and credentials.refresh_token:

        credentials.refresh(Request())

    if not credentials or not credentials.valid:

        flow = InstalledAppFlow.from_client_secrets_file(
            YOUTUBE_CLIENT_SECRET_FILE,
            SCOPES
        )

        credentials = flow.run_local_server(port=0)

    os.makedirs(
        os.path.dirname(YOUTUBE_TOKEN_FILE) or ".",
        exist_ok=True
    )

    with open(YOUTUBE_TOKEN_FILE, "w", encoding="utf-8") as token_file:
        token_file.write(credentials.to_json())

    return credentials


# ============================================================
# UPLOAD
# ============================================================

def upload_video(
    video_file,
    title,
    description,
    tags=None,
):

    credentials = get_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials
    )

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": YOUTUBE_CATEGORY,
        },
        "status": {
            "privacyStatus": YOUTUBE_PRIVACY_STATUS,
            "selfDeclaredMadeForKids": YOUTUBE_MADE_FOR_KIDS,
        }
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            video_file,
            resumable=True
        )
    )

    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:
            print(f"    Upload progress: {int(status.progress() * 100)}%")

    print(f"Video uploaded: https://youtu.be/{response['id']}")

    return response


# ============================================================
# FIRST COMMENT (engagement seeding)
# ============================================================
#
# Posting a comment right after upload — ideally a question tied to
# the hook — is one of the cheapest ways to prime the comment section
# before real viewers arrive. Best-effort: if the channel has comments
# restricted, held for review, or the API call fails for any reason,
# this must NOT take down an otherwise-successful upload.

def post_first_comment(
    video_id,
    comment_text,
):

    if not comment_text:
        return None

    try:

        credentials = get_credentials()

        youtube = build(
            "youtube",
            "v3",
            credentials=credentials
        )

        body = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": comment_text[:9999],
                    }
                },
            }
        }

        response = (
            youtube.commentThreads()
            .insert(
                part="snippet",
                body=body,
            )
            .execute()
        )

        print(f"Posted first comment: \"{comment_text}\"")

        return response

    except Exception as exc:

        # Common causes: comments disabled/held for review on new
        # channels, or a cached token that predates the force-ssl
        # scope above. Never let this break the pipeline.
        print(
            "Could not post first comment "
            f"(non-fatal): {exc}"
        )

        return None