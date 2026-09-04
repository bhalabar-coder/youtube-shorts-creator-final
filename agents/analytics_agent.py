import json
import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import AuthorizedSession
from googleapiclient.discovery import build

from config import CONFIG_DIR


# ============================================================
# YOUTUBE ANALYTICS SETUP
# ============================================================

YOUTUBE_ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtubeAnalytics.readonly"
]

ANALYTICS_HISTORY_FILE = os.path.join(
    CONFIG_DIR,
    "video_performance_history.json"
)


# ============================================================
# CREDENTIALS
# ============================================================

def get_analytics_credentials():
    """
    Get or refresh OAuth credentials for YouTube Analytics API.
    Reuses the same credentials file as youtube_agent if available.
    """
    
    token_file = os.path.join(
        CONFIG_DIR,
        "token.json"
    )
    
    if os.path.exists(token_file):
        
        credentials = Credentials.from_authorized_user_file(
            token_file,
            YOUTUBE_ANALYTICS_SCOPES
        )
        
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            with open(token_file, "w") as f:
                f.write(credentials.to_json())
        
        return credentials
    
    raise RuntimeError(
        "No credentials found. Run setup_youtube_auth.py first."
    )


# ============================================================
# FETCH VIDEO METRICS
# ============================================================

def get_channel_id(credentials):
    """
    Get the authenticated user's channel ID.
    """
    
    try:
        
        youtube = build(
            "youtube",
            "v3",
            credentials=credentials
        )
        
        response = youtube.channels().list(
            part="id",
            mine=True
        ).execute()
        
        if response.get("items"):
            return response["items"][0]["id"]
        
        raise RuntimeError("No channel found")
    
    except Exception as e:
        print(f"Error getting channel ID: {e}")
        return None


def get_video_metrics(
    video_id,
    credentials
):
    """
    Fetch views, likes, comments, and average view duration
    for a specific video from YouTube Analytics API.
    
    Returns dict with metrics or None if not available yet.
    """
    
    try:
        
        channel_id = get_channel_id(
            credentials
        )
        
        if not channel_id:
            return None
        
        analytics = build(
            "youtubeAnalytics",
            "v2",
            credentials=credentials
        )
        
        # YouTube Analytics needs 24-48 hours to populate data
        # Start from 2 days ago to give data time to appear
        end_date = (
            datetime.now() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        
        start_date = (
            datetime.now() - timedelta(days=90)
        ).strftime("%Y-%m-%d")
        
        response = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="views,likes,comments,averageViewDuration",
            dimensions="video",
            filters=f"video=={video_id}",
            maxResults=1
        ).execute()
        
        if not response.get("rows"):
            # Data not available yet
            return None
        
        row = response["rows"][0]
        
        return {
            "video_id": video_id,
            "views": int(row[1]),
            "likes": int(row[2]),
            "comments": int(row[3]),
            "avg_view_duration": float(row[4]),
            "fetched_at": datetime.now().isoformat(),
        }
    
    except Exception as e:
        
        print(
            f"Error fetching metrics for "
            f"{video_id}: {e}"
        )
        
        return None


# ============================================================
# PERFORMANCE HISTORY
# ============================================================

def load_performance_history():
    """
    Load the performance history from disk.
    Returns dict: {video_id: {metrics, metadata}}
    """
    
    if os.path.exists(ANALYTICS_HISTORY_FILE):
        
        try:
            
            with open(
                ANALYTICS_HISTORY_FILE,
                "r"
            ) as f:
                return json.load(f)
        
        except Exception as e:
            print(f"Error loading history: {e}")
    
    return {}


def save_performance_history(
    history
):
    """
    Save performance history to disk.
    """
    
    try:
        
        with open(
            ANALYTICS_HISTORY_FILE,
            "w"
        ) as f:
            json.dump(
                history,
                f,
                indent=2,
                default=str
            )
    
    except Exception as e:
        print(f"Error saving history: {e}")


def add_to_performance_history(
    video_id,
    title,
    topic,
    category,
    hook_style,
    narration_length,
    metrics=None
):
    """
    Add a newly uploaded video to the performance history.
    Includes metadata (topic, hook, etc.) so we can later
    correlate performance with content choices.
    """
    
    history = load_performance_history()
    
    history[video_id] = {
        "title": title,
        "topic": topic,
        "category": category,
        "hook_style": hook_style,
        "narration_length": narration_length,
        "uploaded_at": datetime.now().isoformat(),
        "metrics_history": [metrics] if metrics else [],
    }
    
    save_performance_history(
        history
    )


def update_video_metrics(
    video_id,
    credentials
):
    """
    Fetch latest metrics for a video and update the history.
    Called periodically to track performance over time.
    """
    
    metrics = get_video_metrics(
        video_id,
        credentials
    )
    
    if not metrics:
        return False
    
    history = load_performance_history()
    
    if video_id not in history:
        history[video_id] = {"metrics_history": []}
    
    history[video_id]["metrics_history"].append(
        metrics
    )
    
    save_performance_history(
        history
    )
    
    return True


def get_performance_stats():
    """
    Analyze performance history and return insights.
    Groups by topic, category, hook_style to find patterns.
    """
    
    history = load_performance_history()
    
    if not history:
        return None
    
    stats = {
        "by_topic": {},
        "by_category": {},
        "by_hook_style": {},
        "overall": {
            "total_videos": 0,
            "avg_views": 0,
            "avg_likes": 0,
            "avg_comments": 0,
            "avg_duration": 0,
        }
    }
    
    total_videos = 0
    total_views = 0
    total_likes = 0
    total_comments = 0
    total_duration = 0
    
    for video_id, data in history.items():
        
        # Get latest metrics for this video
        if not data.get("metrics_history"):
            continue
        
        latest = data["metrics_history"][-1]
        
        topic = data.get("topic", "Unknown")
        category = data.get("category", "Unknown")
        hook = data.get("hook_style", "Unknown")
        
        # Track by topic
        if topic not in stats["by_topic"]:
            stats["by_topic"][topic] = {
                "count": 0,
                "views": 0,
                "likes": 0,
                "comments": 0,
            }
        
        stats["by_topic"][topic]["count"] += 1
        stats["by_topic"][topic]["views"] += latest["views"]
        stats["by_topic"][topic]["likes"] += latest["likes"]
        stats["by_topic"][topic]["comments"] += latest["comments"]
        
        # Track by category
        if category not in stats["by_category"]:
            stats["by_category"][category] = {
                "count": 0,
                "views": 0,
                "likes": 0,
                "comments": 0,
            }
        
        stats["by_category"][category]["count"] += 1
        stats["by_category"][category]["views"] += latest["views"]
        stats["by_category"][category]["likes"] += latest["likes"]
        stats["by_category"][category]["comments"] += latest["comments"]
        
        # Track by hook style
        if hook not in stats["by_hook_style"]:
            stats["by_hook_style"][hook] = {
                "count": 0,
                "views": 0,
                "likes": 0,
                "comments": 0,
            }
        
        stats["by_hook_style"][hook]["count"] += 1
        stats["by_hook_style"][hook]["views"] += latest["views"]
        stats["by_hook_style"][hook]["likes"] += latest["likes"]
        stats["by_hook_style"][hook]["comments"] += latest["comments"]
        
        # Overall
        total_videos += 1
        total_views += latest["views"]
        total_likes += latest["likes"]
        total_comments += latest["comments"]
        total_duration += latest.get("avg_view_duration", 0)
    
    if total_videos > 0:
        
        stats["overall"]["total_videos"] = total_videos
        stats["overall"]["avg_views"] = total_views / total_videos
        stats["overall"]["avg_likes"] = total_likes / total_videos
        stats["overall"]["avg_comments"] = total_comments / total_videos
        stats["overall"]["avg_duration"] = total_duration / total_videos
    
    return stats