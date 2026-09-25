from __future__ import annotations


PROFILES = {
    "review": {
        "width": 854,
        "height": 480,
        "fps": 30,
        "crf": 30,
        "audio_bitrate": "128k",
        "extension": ".mp4",
    },
    "master_1080p": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "crf": 18,
        "audio_bitrate": "192k",
        "extension": ".mp4",
    },
    "youtube_1080p": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "crf": 20,
        "audio_bitrate": "192k",
        "extension": ".mp4",
    },
    "vertical_1080x1920": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "crf": 20,
        "audio_bitrate": "160k",
        "extension": ".mp4",
    },
    "square_1080": {
        "width": 1080,
        "height": 1080,
        "fps": 30,
        "crf": 20,
        "audio_bitrate": "160k",
        "extension": ".mp4",
    },
}


ALIASES = {
    "youtube": "youtube_1080p",
    "youtube-1080p": "youtube_1080p",
    "master": "master_1080p",
    "review_720p": "review",
    "shorts": "vertical_1080x1920",
    "reels": "vertical_1080x1920",
    "instagram-reel": "vertical_1080x1920",
    "square": "square_1080",
}


def get_profile(name: str):
    key = ALIASES.get(name.lower(), name.lower())
    if key not in PROFILES:
        raise KeyError(f"Unknown export profile: {name}")
    return key, PROFILES[key]
