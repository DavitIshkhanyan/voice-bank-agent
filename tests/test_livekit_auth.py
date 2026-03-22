import sys
import time
from pathlib import Path

import jwt

sys.path.append(str(Path(__file__).resolve().parents[1] / "services/retrieval-api"))

from app.livekit_auth import build_livekit_access_token


def test_build_livekit_access_token_contains_video_grant():
    token = build_livekit_access_token(
        api_key="devkey",
        api_secret="devsecret",
        identity="tester",
        room="demo-room",
        ttl_seconds=600,
    )

    decoded = jwt.decode(token, "devsecret", algorithms=["HS256"], options={"verify_aud": False})

    assert decoded["iss"] == "devkey"
    assert decoded["sub"] == "tester"
    assert decoded["video"]["roomJoin"] is True
    assert decoded["video"]["room"] == "demo-room"
    assert decoded["exp"] > int(time.time())

