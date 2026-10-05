import json
import os
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import CONFIG_DIR

YOUTUBE_ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtubeAnalytics.readonly",
]

ANALYTICS_HISTORY_FILE = os.path.join(CONFIG_DIR, "video_performance_history.json")


def get_analytics_credentials():
    token_file = os.path.join("credentials", "token.json")
    if not os.path.exists(token_file):
        raise RuntimeError("No credentials found. Run setup_youtube_auth.py first.")

    credentials = Credentials.from_authorized_user_file(
        token_file,
        YOUTUBE_ANALYTICS_SCOPES,
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        with open(token_file, "w", encoding="utf-8") as file:
            file.write(credentials.to_json())
    return credentials


def get_channel_id(credentials):
    try:
        youtube = build("youtube", "v3", credentials=credentials)
        response = youtube.channels().list(part="id", mine=True).execute()
        if response.get("items"):
            return response["items"][0]["id"]
    except Exception as exc:
        print(f"Error getting channel ID: {exc}")
    return None


def _safe_rate(numerator, denominator):
    return float(numerator or 0) / max(float(denominator or 0), 1.0)


def _parse_uploaded_at(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def get_video_metrics(video_id, credentials):
    """Fetch the latest available YouTube Analytics metrics for one video."""
    try:
        channel_id = get_channel_id(credentials)
        if not channel_id:
            return None

        analytics = build("youtubeAnalytics", "v2", credentials=credentials)
        end_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")

        metric_names = [
            "views",
            "engagedViews",
            "likes",
            "comments",
            "shares",
            "subscribersGained",
            "averageViewDuration",
            "averageViewPercentage",
        ]

        response = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics=",".join(metric_names),
            dimensions="video",
            filters=f"video=={video_id}",
            maxResults=1,
        ).execute()

        rows = response.get("rows") or []
        if not rows:
            return None

        headers = [item["name"] for item in response.get("columnHeaders", [])]
        values = dict(zip(headers, rows[0]))

        views = int(values.get("views") or 0)
        engaged_views = int(values.get("engagedViews") or views)
        likes = int(values.get("likes") or 0)
        comments = int(values.get("comments") or 0)
        shares = int(values.get("shares") or 0)
        subscribers_gained = int(values.get("subscribersGained") or 0)

        return {
            "video_id": video_id,
            "views": views,
            "engaged_views": engaged_views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "subscribers_gained": subscribers_gained,
            "avg_view_duration": float(values.get("averageViewDuration") or 0),
            "avg_view_percentage": float(values.get("averageViewPercentage") or 0),
            "like_rate": _safe_rate(likes, engaged_views),
            "comment_rate": _safe_rate(comments, engaged_views),
            "share_rate": _safe_rate(shares, engaged_views),
            "subscriber_rate": _safe_rate(subscribers_gained, engaged_views),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        print(f"Error fetching metrics for {video_id}: {exc}")
        return None


def load_performance_history():
    if os.path.exists(ANALYTICS_HISTORY_FILE):
        try:
            with open(ANALYTICS_HISTORY_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            print(f"Error loading history: {exc}")
    return {}


def save_performance_history(history):
    os.makedirs(os.path.dirname(ANALYTICS_HISTORY_FILE) or ".", exist_ok=True)
    with open(ANALYTICS_HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=2, ensure_ascii=False, default=str)


def add_to_performance_history(
    video_id,
    title,
    topic,
    category,
    hook_style,
    narration_length,
    metrics=None,
    visual_match_score=None,
    scene_count=None,
    video_duration=None,
    quality_score=None,
):
    history = load_performance_history()
    history[video_id] = {
        "title": title,
        "topic": topic,
        "category": category,
        "hook_style": hook_style,
        "narration_length": narration_length,
        "visual_match_score": visual_match_score,
        "scene_count": scene_count,
        "video_duration": video_duration,
        "quality_score": quality_score,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "metrics_history": [metrics] if metrics else [],
    }
    save_performance_history(history)


def _snapshot_name(uploaded_at):
    uploaded = _parse_uploaded_at(uploaded_at)
    if not uploaded:
        return None
    age_hours = (datetime.now(timezone.utc) - uploaded).total_seconds() / 3600.0
    if age_hours >= 168:
        return "7d"
    if age_hours >= 72:
        return "72h"
    if age_hours >= 24:
        return "24h"
    return None


def update_video_metrics(video_id, credentials):
    metrics = get_video_metrics(video_id, credentials)
    if not metrics:
        return False

    history = load_performance_history()
    record = history.setdefault(video_id, {"metrics_history": []})
    record.setdefault("metrics_history", []).append(metrics)

    snapshot = _snapshot_name(record.get("uploaded_at"))
    if snapshot:
        record.setdefault("snapshots", {})[snapshot] = metrics

    save_performance_history(history)
    return True


def update_all_video_metrics():
    history = load_performance_history()
    if not history:
        print("No tracked videos yet.")
        return 0

    credentials = get_analytics_credentials()
    updated = 0
    for video_id in list(history.keys()):
        if update_video_metrics(video_id, credentials):
            updated += 1
    print(f"Updated analytics for {updated}/{len(history)} tracked videos.")
    return updated


def _latest_metrics(data):
    snapshots = data.get("snapshots") or {}
    for key in ("72h", "7d", "24h"):
        if snapshots.get(key):
            return snapshots[key]
    history = data.get("metrics_history") or []
    return history[-1] if history else None


def _add_bucket(bucket, key, metrics):
    item = bucket.setdefault(
        key,
        {
            "count": 0,
            "views": 0,
            "engaged_views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "subscribers_gained": 0,
            "avg_view_percentage_total": 0.0,
        },
    )
    item["count"] += 1
    for name in ("views", "engaged_views", "likes", "comments", "shares", "subscribers_gained"):
        item[name] += metrics.get(name, 0) or 0
    item["avg_view_percentage_total"] += metrics.get("avg_view_percentage", 0) or 0


def _finalize_bucket(bucket, channel_avg_views):
    for item in bucket.values():
        count = max(item["count"], 1)
        engaged = max(item["engaged_views"], 1)
        item["avg_views"] = item["views"] / count
        item["avg_engaged_views"] = item["engaged_views"] / count
        item["avg_view_percentage"] = item["avg_view_percentage_total"] / count
        item["like_rate"] = item["likes"] / engaged
        item["comment_rate"] = item["comments"] / engaged
        item["share_rate"] = item["shares"] / engaged
        item["subscriber_rate"] = item["subscribers_gained"] / engaged

        confidence = min(item["count"] / 5.0, 1.0)
        view_index = item["avg_engaged_views"] / max(channel_avg_views, 1.0)
        retention_index = min(item["avg_view_percentage"] / 100.0, 1.5)
        engagement_index = min(
            item["like_rate"] * 8.0
            + item["comment_rate"] * 30.0
            + item["share_rate"] * 20.0
            + item["subscriber_rate"] * 30.0,
            2.0,
        )
        raw_score = 0.45 * view_index + 0.35 * retention_index + 0.20 * engagement_index
        item["performance_score"] = raw_score * confidence + 1.0 * (1.0 - confidence)


def _duration_band(value):
    try:
        seconds = float(value or 0)
    except Exception:
        seconds = 0
    if seconds <= 0:
        return "unknown"
    if seconds < 20:
        return "under_20s"
    if seconds < 30:
        return "20_29s"
    if seconds < 40:
        return "30_39s"
    return "40s_plus"


def _scene_band(value):
    try:
        count = int(value or 0)
    except Exception:
        count = 0
    if count <= 0:
        return "unknown"
    if count <= 6:
        return "1_6_scenes"
    if count <= 9:
        return "7_9_scenes"
    return "10_plus_scenes"


def get_performance_stats():
    history = load_performance_history()
    if not history:
        return None

    stats = {
        "by_topic": {},
        "by_category": {},
        "by_hook_style": {},
        "by_duration_band": {},
        "by_scene_count": {},
        "overall": {
            "total_videos": 0,
            "avg_views": 0,
            "avg_engaged_views": 0,
            "avg_likes": 0,
            "avg_comments": 0,
            "avg_view_percentage": 0,
        },
    }

    metric_rows = []
    for data in history.values():
        latest = _latest_metrics(data)
        if latest:
            metric_rows.append((data, latest))

    if not metric_rows:
        return stats

    avg_engaged_views = sum((m.get("engaged_views", m.get("views", 0)) or 0) for _, m in metric_rows) / len(metric_rows)

    for data, latest in metric_rows:
        normalized = dict(latest)
        normalized["engaged_views"] = normalized.get("engaged_views", normalized.get("views", 0)) or 0
        _add_bucket(stats["by_topic"], data.get("topic", "Unknown"), normalized)
        _add_bucket(stats["by_category"], data.get("category", "Unknown"), normalized)
        _add_bucket(stats["by_hook_style"], data.get("hook_style", "Unknown"), normalized)
        _add_bucket(stats["by_duration_band"], _duration_band(data.get("video_duration")), normalized)
        _add_bucket(stats["by_scene_count"], _scene_band(data.get("scene_count")), normalized)

    for bucket in (
        stats["by_topic"],
        stats["by_category"],
        stats["by_hook_style"],
        stats["by_duration_band"],
        stats["by_scene_count"],
    ):
        _finalize_bucket(bucket, avg_engaged_views)

    count = len(metric_rows)
    stats["overall"]["total_videos"] = count
    stats["overall"]["avg_views"] = sum((m.get("views", 0) or 0) for _, m in metric_rows) / count
    stats["overall"]["avg_engaged_views"] = avg_engaged_views
    stats["overall"]["avg_likes"] = sum((m.get("likes", 0) or 0) for _, m in metric_rows) / count
    stats["overall"]["avg_comments"] = sum((m.get("comments", 0) or 0) for _, m in metric_rows) / count
    stats["overall"]["avg_view_percentage"] = sum((m.get("avg_view_percentage", 0) or 0) for _, m in metric_rows) / count
    return stats
