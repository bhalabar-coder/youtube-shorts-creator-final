import json
import os
import subprocess

from config import VIDEO_WIDTH, VIDEO_HEIGHT


def inspect_rendered_video(video_file, expected_audio_duration=None):
    """Inspect the final render and return a technical QC report."""
    report = {
        "passed": False,
        "score": 0.0,
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "has_video": False,
        "has_audio": False,
        "file_size_bytes": 0,
        "issues": [],
    }

    if not os.path.exists(video_file):
        report["issues"].append("Rendered video file does not exist.")
        return report

    report["file_size_bytes"] = os.path.getsize(video_file)
    if report["file_size_bytes"] < 500_000:
        report["issues"].append("Rendered video file is unexpectedly small.")

    command = [
        "ffprobe",
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        video_file,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        report["issues"].append(f"ffprobe could not run: {exc}")
        return report

    if result.returncode != 0:
        report["issues"].append(
            "ffprobe failed: " + (result.stderr or "unknown error").strip()
        )
        return report

    try:
        payload = json.loads(result.stdout or "{}")
    except Exception as exc:
        report["issues"].append(f"Could not parse ffprobe output: {exc}")
        return report

    streams = payload.get("streams") or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    report["has_video"] = bool(video_streams)
    report["has_audio"] = bool(audio_streams)

    if not report["has_video"]:
        report["issues"].append("Final render has no video stream.")
    if not report["has_audio"]:
        report["issues"].append("Final render has no audio stream.")

    if video_streams:
        stream = video_streams[0]
        report["width"] = int(stream.get("width") or 0)
        report["height"] = int(stream.get("height") or 0)

        if report["width"] != VIDEO_WIDTH or report["height"] != VIDEO_HEIGHT:
            report["issues"].append(
                f"Unexpected resolution {report['width']}x{report['height']} "
                f"(expected {VIDEO_WIDTH}x{VIDEO_HEIGHT})."
            )

        if report["height"] <= report["width"]:
            report["issues"].append("Final video is not portrait/vertical.")

    try:
        report["duration"] = float((payload.get("format") or {}).get("duration") or 0.0)
    except Exception:
        report["duration"] = 0.0

    if report["duration"] <= 0:
        report["issues"].append("Final video duration is invalid.")

    if expected_audio_duration:
        difference = abs(report["duration"] - float(expected_audio_duration))
        if difference > 1.25:
            report["issues"].append(
                f"Video/audio duration mismatch is {difference:.2f}s."
            )

    # Technical QC score. A hard failure still blocks upload below.
    score = 100.0
    if not report["has_video"]:
        score -= 45
    if not report["has_audio"]:
        score -= 35
    if report["width"] != VIDEO_WIDTH or report["height"] != VIDEO_HEIGHT:
        score -= 15
    if report["duration"] <= 0:
        score -= 30
    if report["file_size_bytes"] < 500_000:
        score -= 15
    if expected_audio_duration and abs(report["duration"] - float(expected_audio_duration)) > 1.25:
        score -= 20

    report["score"] = round(max(0.0, score), 1)
    report["passed"] = not report["issues"] and report["score"] >= 90.0
    return report


def calculate_pre_upload_quality(
    visual_match,
    media_count,
    scene_count,
    technical_qc,
):
    """Combine content alignment and final technical quality into one 0-100 score."""
    visual_score = float((visual_match or {}).get("overall_score") or 0.0)
    hook_score = float((visual_match or {}).get("hook_score") or 0.0)
    min_scene_score = float((visual_match or {}).get("min_scene_score") or 0.0)
    coverage = 100.0 * min(max(media_count, 0), max(scene_count, 1)) / max(scene_count, 1)
    technical_score = float((technical_qc or {}).get("score") or 0.0)

    overall = (
        visual_score * 0.40
        + hook_score * 0.15
        + min_scene_score * 0.10
        + coverage * 0.10
        + technical_score * 0.25
    )

    return {
        "overall_score": round(overall, 1),
        "visual_score": round(visual_score, 1),
        "hook_score": round(hook_score, 1),
        "min_scene_score": round(min_scene_score, 1),
        "media_coverage_score": round(coverage, 1),
        "technical_score": round(technical_score, 1),
        "passed": bool((technical_qc or {}).get("passed")) and overall >= 90.0,
    }
