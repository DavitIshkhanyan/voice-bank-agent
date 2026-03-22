# Armenian Bank Voice AI Agent (LiveKit OSS)

End-to-end Voice AI customer support agent for Armenian banks, built on **self-hosted LiveKit** (not LiveKit Cloud).

The assistant is **strictly grounded** to scraped official bank websites and only handles:
- Credits
- Deposits
- Branch Locations

Out-of-scope questions are refused.

## Repository Link

This workspace is ready to push as a GitHub repository. Create your repo and push this folder:

```bash
cd voice-bank-agent
git init
git add .
git commit -m "Initial Armenian bank voice agent"
git branch -M main
git remote add origin https://github.com/<your-username>/voice-bank-agent.git
git push -u origin main
```

Use the resulting URL as your submission link.

## Bank Sources (Official Websites)

Configured in `services/scraper/config/banks.yaml`:
- Ameriabank (`ameriabank.am`)
- ACBA Bank (`acba.am`)
- Evocabank (`evoca.am`)

The scraper ingests pages under topic-specific seed URLs and same-domain links.

## Architecture & Decisions

### 1) Voice and real-time orchestration: LiveKit OSS
- **Why**: Open-source, production-grade WebRTC infrastructure, low-latency media transport, and flexible agent workers.
- **How**: `docker-compose.yml` runs `livekit/livekit-server` + `redis` locally.

### 2) Armenian speech stack
- **STT**: OpenAI `gpt-4o-mini-transcribe` (multilingual, works for Armenian in practice).
- **TTS**: OpenAI `gpt-4o-mini-tts` (natural conversational voice with low integration complexity).
- **Why these choices**:
  - Fast implementation and low ops overhead for evaluation.
  - Strong multilingual quality-to-latency tradeoff.
  - Fits stated expected cost budget.

### 3) Retrieval + grounding guardrails
- **Retriever**: ChromaDB vector store over scraped chunks, with TF-IDF fallback.
  - Default backend is `auto` (try ChromaDB, fallback to TF-IDF if unavailable).
  - Metadata filters enforce `topic` and optional `bank_id` during retrieval.
- **Guardrails**:
  - Topic classifier only allows `credits`, `deposits`, `branch_locations`.
  - If topic is ambiguous/out-of-scope -> refusal.
  - If retrieval confidence below threshold -> refusal.
  - Answer is generated only from retrieved source snippets.

### 4) Scalability design
- Add new banks by extending `banks.yaml`; no code changes needed.
- Retrieval corpus is bank-agnostic and supports optional `bank_id` filtering.
- Services are decoupled:
  - `services/scraper`: data ingestion
  - `services/retrieval-api`: policy + grounded QA API
  - `apps/voice-agent`: LiveKit voice worker
- Can scale horizontally by running multiple `voice-agent` and `retrieval-api` replicas.

## Project Structure

```text
apps/voice-agent/src/agent.py           # LiveKit voice worker
services/scraper/scrape_and_ingest.py   # website scraper + chunker
services/retrieval-api/app/main.py      # grounded QA API with guardrails
services/retrieval-api/app/policy.py    # scope control
services/retrieval-api/app/retriever.py # ChromaDB + TF-IDF fallback retrieval
data/knowledge/processed/chunks.jsonl   # generated grounded corpus
infra/livekit.yaml                       # LiveKit OSS config
docker-compose.yml
```

## Setup Instructions

### Prerequisites
- Docker + Docker Compose
- Python 3.11+
- OpenAI API key (or replace model integrations with your own providers)

### 1) Configure env

```bash
cd voice-bank-agent
cp .env.example .env
# then edit .env and set OPENAI_API_KEY
# CHUNKS_PATH is prefilled for Docker default: /app/data/knowledge/processed/chunks.jsonl
```

### 2) Scrape and ingest bank data

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r services/scraper/requirements.txt
python services/scraper/scrape_and_ingest.py
```

This generates `data/knowledge/processed/chunks.jsonl`.
At retrieval API startup, chunks are synchronized into ChromaDB at `CHROMA_PERSIST_DIR`.

### 3) Start all services (LiveKit OSS + retrieval API + voice worker)

```bash
docker compose --env-file .env up --build
```

`retrieval-api` waits for grounded data at `CHUNKS_PATH`; if you regenerate data, restart that service.

### 4) Validate retrieval API

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"ACBA-ում ինչ ավանդներ կան?","bank_id":"acba"}'
python scripts/inspect_retriever.py
```

`/health` now also returns `retriever_backend` (e.g., `chroma` or `tfidf`).

### 5) Use the included browser client

Run a static server for `apps/web-client`:

```bash
cd voice-bank-agent/apps/web-client
python3 -m http.server 8080
```

Open `http://localhost:8080` and click **Connect & Speak**.

The web client calls `POST /livekit/token` on the retrieval API, gets a short-lived token, joins the room, and publishes your microphone automatically.
The token endpoint also dispatches `LIVEKIT_AGENT_NAME` into the same room so the worker starts handling your speech session.

This is the recommended way to connect a LiveKit client for local testing.

## Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -r services/retrieval-api/requirements.txt
pytest -q
```

## Accuracy & Guardrail Behavior

- If question is not about credits/deposits/branch locations -> refusal.
- If retrieved evidence is weak/absent -> refusal.
- If in scope and grounded snippets exist -> answer with citations/sources.

## Notes for Evaluators

- Bring your own API keys via `.env`.
- Cost profile is mostly STT/TTS/LLM tokens/audio and should fit small test budget.
- To switch model vendors, change integration in `apps/voice-agent/src/agent.py` and `services/retrieval-api/app/main.py`.
- Retrieval backend controls:
  - `RETRIEVER_BACKEND=auto|chroma|tfidf`
  - `CHROMA_PERSIST_DIR=/app/data/chroma`
  - `CHROMA_COLLECTION=bank_chunks`
- Browser client controls:
  - `WEB_CLIENT_ORIGIN=http://localhost:8080`
  - `LIVEKIT_INTERNAL_URL=http://livekit:7880`
  - `LIVEKIT_AGENT_NAME=armenian-bank-voice-agent`

