import { Room, RoomEvent, createLocalAudioTrack } from "https://cdn.jsdelivr.net/npm/livekit-client@2.15.7/+esm";

const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const statusEl = document.getElementById("status");
const logsEl = document.getElementById("logs");

const apiBaseInput = document.getElementById("apiBase");
const roomInput = document.getElementById("roomName");
const identityInput = document.getElementById("identity");
const ttlInput = document.getElementById("ttl");

let room = null;
let localTrack = null;

function setStatus(text) {
  statusEl.textContent = `Status: ${text}`;
}

function log(message) {
  const stamp = new Date().toLocaleTimeString();
  logsEl.textContent += `[${stamp}] ${message}\n`;
  logsEl.scrollTop = logsEl.scrollHeight;
}

async function requestToken(apiBase, roomName, identity, ttlSeconds) {
  const payload = {
    room: roomName,
    ttl_seconds: ttlSeconds,
  };
  if (identity) {
    payload.identity = identity;
  }

  const response = await fetch(`${apiBase}/livekit/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Token request failed: ${response.status} ${await response.text()}`);
  }

  return response.json();
}

function fallbackLivekitUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "localhost") {
      parsed.hostname = "127.0.0.1";
      return parsed.toString();
    }
  } catch {
    // Keep original URL if parsing fails.
  }
  return url;
}

function attachRemoteAudio(track) {
  const element = track.attach();
  element.autoplay = true;
  document.body.appendChild(element);
}

connectBtn.addEventListener("click", async () => {
  try {
    connectBtn.disabled = true;
    setStatus("requesting token...");

    const apiBase = apiBaseInput.value.trim();
    const roomName = roomInput.value.trim();
    const identity = identityInput.value.trim();
    const ttlSeconds = Number(ttlInput.value || 3600);

    const tokenResp = await requestToken(apiBase, roomName, identity, ttlSeconds);
    console.log(tokenResp, 'tokenResp')
    log(`Token issued for identity=${tokenResp.identity}, room=${tokenResp.room}`);

    room = new Room({ adaptiveStream: true, dynacast: true });

    room.on(RoomEvent.Connected, () => {
      setStatus(`connected to ${tokenResp.room}`);
      log("Connected to LiveKit room.");
    });

    room.on(RoomEvent.Disconnected, () => {
      setStatus("disconnected");
      log("Disconnected from LiveKit room.");
      connectBtn.disabled = false;
      disconnectBtn.disabled = true;
    });

    room.on(RoomEvent.ParticipantConnected, (participant) => {
      log(`Participant joined: ${participant.identity}`);
    });

    room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind === "audio") {
        log(`Subscribed to remote audio from ${participant.identity}`);
        attachRemoteAudio(track);
      }
    });

    log(`Connecting to ${tokenResp.livekit_url}`);
    try {
      await room.connect(tokenResp.livekit_url, tokenResp.token);
    } catch (firstError) {
      const fallbackUrl = fallbackLivekitUrl(tokenResp.livekit_url);
      if (fallbackUrl !== tokenResp.livekit_url) {
        log(`Primary connect failed, retrying with ${fallbackUrl}`);
        await room.connect(fallbackUrl, tokenResp.token);
      } else {
        throw firstError;
      }
    }

    localTrack = await createLocalAudioTrack();
    await room.localParticipant.publishTrack(localTrack);
    log("Microphone track published.");

    disconnectBtn.disabled = false;
  } catch (error) {
    setStatus("error");
    log(error instanceof Error ? error.message : String(error));
    connectBtn.disabled = false;
  }
});

disconnectBtn.addEventListener("click", async () => {
  try {
    if (localTrack) {
      localTrack.stop();
      localTrack = null;
    }
    if (room) {
      room.disconnect();
      room = null;
    }
    setStatus("disconnected");
    log("Disconnected by user.");
  } finally {
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
  }
});

