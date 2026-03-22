# Web Voice Client

Minimal browser client for speaking with the LiveKit voice agent.

## Run

```bash
cd voice-bank-agent/apps/web-client
python3 -m http.server 8080
```

Open `http://localhost:8080`.

## Requirements

- Retrieval API running on `http://localhost:8000` (token endpoint + CORS)
- LiveKit server running on `ws://localhost:7880`
- Voice agent worker connected to the same LiveKit server

## How it works

1. Calls `POST /livekit/token` on the retrieval API.
2. Uses returned token + URL to connect with LiveKit JS SDK.
3. Publishes local microphone and plays remote audio tracks.

