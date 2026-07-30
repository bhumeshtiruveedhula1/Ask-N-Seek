"""
engine/paths.py — Frame and video path resolution for Odysseus Part 3.

Templates are configured in config.py (or overridden via environment variables).
Update FRAME_PATH_TEMPLATE / VIDEO_PATH_TEMPLATE in config.py if the deployment
layout changes — no other file needs to change.

Default templates (from config.py):
    FRAME_PATH_TEMPLATE = "/mnt/agents/output/frames/{video_id}/{frame_index:04d}.jpg"
    VIDEO_PATH_TEMPLATE  = "/mnt/agents/output/videos/{video_id}.mp4"
"""

from __future__ import annotations

import config


def get_frame_path(video_id: str, frame_index: int) -> str:
    """
    Return the absolute path (or URL) for a specific frame image.

    Parameters
    ----------
    video_id : str
        Identifier of the source video (e.g. "vid1").
    frame_index : int
        Zero-based frame index (e.g. 42 → "0042.jpg").

    Returns
    -------
    str
        Resolved path using config.FRAME_PATH_TEMPLATE.
    """
    return config.FRAME_PATH_TEMPLATE.format(
        video_id=video_id,
        frame_index=frame_index,
    )


def get_video_path(video_id: str) -> str:
    """
    Return the absolute path (or URL) for a source video file.

    Parameters
    ----------
    video_id : str
        Identifier of the source video (e.g. "vid1").

    Returns
    -------
    str
        Resolved path using config.VIDEO_PATH_TEMPLATE.
    """
    return config.VIDEO_PATH_TEMPLATE.format(video_id=video_id)
