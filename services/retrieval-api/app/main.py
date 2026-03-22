from __future__ import annotations

import os
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from livekit import api as livekit_api
from openai import OpenAI

from .livekit_auth import build_livekit_access_token
from .models import AskRequest, AskResponse, LivekitTokenRequest, LivekitTokenResponse, SourceItem
from .policy import classify_topic, refusal_no_grounding, refusal_out_of_scope
from .retriever import build_retriever

app = FastAPI(title="Armenian Bank Grounded Retrieval API", version="1.0.0")
allowed_origins = [o.strip() for o in os.getenv("WEB_CLIENT_ORIGIN", "http://localhost:8080").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = build_retriever()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
MIN_SCORE = float(os.getenv("MIN_GROUNDING_SCORE", "0.12"))


def build_prompt(question: str, topic: str, sources: list[SourceItem]) -> str:
    context = "\n\n".join(
        f"[{i+1}] {s.bank_name} | {s.title} | {s.url}\n{s.snippet}" for i, s in enumerate(sources)
    )
    return (
        "Դու հայկական բանկային աջակցման օգնական ես։\n"
        "Պատասխանիր միայն տրված աղբյուրներից։ Արտաքին գիտելիք մի օգտագործիր։\n"
        "Եթե աղբյուրները լիարժեք չեն, ասա, որ տվյալը չի գտնվել։\n"
        f"Թեմա: {topic}\n"
        f"Հարց: {question}\n\n"
        f"Աղբյուրներ:\n{context}\n\n"
        "Պատասխանը տուր հայերեն, շատ կարճ, և վերջում ավելացրու հղումները [1], [2] ձևաչափով։"
    )


def generate_grounded_answer(question: str, topic: str, sources: list[SourceItem]) -> str:
    if openai_client is None:
        citations = " ".join(f"[{i+1}]" for i in range(len(sources)))
        snippets = " ".join(s.snippet[:180] for s in sources[:2])
        return f"Հիմնվելով պաշտոնական աղբյուրների վրա՝ {snippets} {citations}".strip()

    completion = openai_client.chat.completions.create(
        model=os.getenv("OPENAI_LLM_MODEL", "gpt-4.1-mini"),
        temperature=0,
        messages=[{"role": "user", "content": build_prompt(question, topic, sources)}],
    )
    return completion.choices[0].message.content.strip()


def resolve_livekit_url_for_client(configured_url: str, request: Request) -> str:
    parsed = urlparse(configured_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return configured_url

    host_header = request.headers.get("host", "")
    host = host_header.split(":")[0].strip()
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return configured_url

    # Keep the configured scheme/port, only swap hostname so LAN clients can connect.
    port = parsed.port or 7880
    return f"{parsed.scheme}://{host}:{port}"


def livekit_http_url() -> str:
    configured = os.getenv("LIVEKIT_INTERNAL_URL") or os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    parsed = urlparse(configured)
    if parsed.scheme in {"ws", "wss"}:
        scheme = "http" if parsed.scheme == "ws" else "https"
        port = parsed.port or 7880
        return f"{scheme}://{parsed.hostname}:{port}"
    return configured


async def ensure_agent_dispatch(room: str, api_key: str, api_secret: str) -> None:
    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "armenian-bank-voice-agent")
    lk_url = livekit_http_url()

    async with livekit_api.LiveKitAPI(url=lk_url, api_key=api_key, api_secret=api_secret) as lk:
        listed = await lk.agent_dispatch.list_dispatch(room)
        existing = [d for d in listed if d.agent_name == agent_name]
        if existing:
            return

        await lk.agent_dispatch.create_dispatch(
            livekit_api.CreateAgentDispatchRequest(
                room=room,
                agent_name=agent_name,
                metadata='{"source":"web-client"}',
            )
        )


@app.get("/health")
def health() -> dict:
    return {"ok": True, "chunks": len(retriever.chunks), "retriever_backend": retriever.backend}


@app.get("/banks")
def banks() -> dict:
    items = sorted({(c.bank_id, c.bank_name) for c in retriever.chunks})
    return {"banks": [{"id": b_id, "name": b_name} for b_id, b_name in items]}


@app.post("/livekit/token", response_model=LivekitTokenResponse)
async def mint_livekit_token(req: LivekitTokenRequest, request: Request) -> LivekitTokenResponse:
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    configured_livekit_url = os.getenv("LIVEKIT_URL", "ws://localhost:7880")

    if not api_key or not api_secret:
        raise HTTPException(status_code=503, detail="LiveKit credentials are not configured on the API service")

    identity = req.identity or f"web-{uuid4().hex[:8]}"
    livekit_url = resolve_livekit_url_for_client(configured_livekit_url, request)

    # Keep token issuance resilient even if explicit dispatch is temporarily unavailable.
    try:
        await ensure_agent_dispatch(req.room, api_key, api_secret)
    except Exception:
        pass

    token = build_livekit_access_token(
        api_key=api_key,
        api_secret=api_secret,
        identity=identity,
        room=req.room,
        ttl_seconds=req.ttl_seconds,
    )
    return LivekitTokenResponse(token=token, livekit_url=livekit_url, room=req.room, identity=identity)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    topic = classify_topic(req.question)
    if topic is None:
        return AskResponse(answer=refusal_out_of_scope(), topic=None, refused=True, reason="out_of_scope", sources=[])

    ranked = retriever.search(query=req.question, topic=topic, bank_id=req.bank_id, top_k=req.top_k)
    filtered = [(chunk, score) for chunk, score in ranked if score >= MIN_SCORE]

    if not filtered:
        return AskResponse(answer=refusal_no_grounding(), topic=topic, refused=True, reason="no_grounding", sources=[])

    sources = [
        SourceItem(
            bank_id=chunk.bank_id,
            bank_name=chunk.bank_name,
            topic=chunk.topic,
            url=chunk.url,
            title=chunk.title,
            score=score,
            snippet=chunk.text,
        )
        for chunk, score in filtered
    ]

    answer = generate_grounded_answer(req.question, topic, sources)
    return AskResponse(answer=answer, topic=topic, refused=False, reason=None, sources=sources)

