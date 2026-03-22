from __future__ import annotations

import os

import httpx
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, function_tool
from livekit.plugins import openai, silero

from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE

RETRIEVAL_API_URL = os.getenv("RETRIEVAL_API_URL", "http://localhost:8000")


def validate_env() -> None:
    # Voice mode requires an API key because STT/TTS/LLM are OpenAI-backed in this baseline.
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for voice agent startup.")


class ArmenianBankAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
    # may be the problem is bank_id or may be change in stt
    @function_tool
    # async def ask_grounded_bank_kb(self, question: str, bank_id: str | None = None) -> str:
    async def ask_grounded_bank_kb(self, question: str) -> str:
        """Query the grounded retrieval API and return a citation-backed Armenian answer."""
        # print(bank_id, 'bank_id')
        print(question, '----++++----')
        payload = {
            "question": question,
            # "bank_id": bank_id,
            "top_k": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(f"{RETRIEVAL_API_URL}/ask", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return "Ժամանակավորապես չեմ կարող միանալ գիտելիքի ծառայությանը։ Խնդրում եմ փորձեք քիչ անց։"
        print(data, 'data')
        answer = data["answer"]
        print(answer, 'answer')
        if data.get("refused"):
            return answer

        links = []
        for source in data.get("sources", [])[:3]:
            links.append(source["url"])

        if links:
            answer += "\nԱղբյուրներ՝ " + ", ".join(links)
        return answer


async def entrypoint(ctx: JobContext) -> None:
    validate_env()
    await ctx.connect()

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(
            model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe"),
            language="hy",
        ),
        llm=openai.LLM(model=os.getenv("OPENAI_LLM_MODEL", "gpt-4.1-mini")),
        tts=openai.TTS(
            model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
        ),
    )

    agent = ArmenianBankAssistant()
    await session.start(agent=agent, room=ctx.room)
    await session.generate_reply(instructions=WELCOME_MESSAGE)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )

