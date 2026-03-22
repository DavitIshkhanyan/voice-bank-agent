from __future__ import annotations

import time

import jwt


def build_livekit_access_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    room: str,
    ttl_seconds: int = 3600,
) -> str:
    now = int(time.time())
    payload = {
        "iss": api_key,
        "sub": identity,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "video": {
            "roomJoin": True,
            "room": room,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }
    return jwt.encode(payload, api_secret, algorithm="HS256")

