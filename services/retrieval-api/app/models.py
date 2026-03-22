from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=2)
    bank_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class SourceItem(BaseModel):
    bank_id: str
    bank_name: str
    topic: str
    url: str
    title: str
    score: float
    snippet: str


class AskResponse(BaseModel):
    answer: str
    topic: str | None
    refused: bool
    reason: str | None = None
    sources: list[SourceItem] = []


class LivekitTokenRequest(BaseModel):
    room: str = Field(min_length=2, max_length=80)
    identity: str | None = Field(default=None, min_length=2, max_length=80)
    ttl_seconds: int = Field(default=3600, ge=60, le=7200)


class LivekitTokenResponse(BaseModel):
    token: str
    livekit_url: str
    room: str
    identity: str


