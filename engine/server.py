"""Earshot engine: local HTTP/WebSocket API the Tauri app talks to. Nothing here calls the internet.

Run: uv run uvicorn server:app --port 8765
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import models

KB_DIR = Path(__file__).parent / "kb"
kb_docs: list[str] = []
kb_vecs = None
lock = asyncio.Lock()  # ponytail: one global lock, MLX runs one job at a time; queue per model if latency matters


def load_kb() -> list[str]:
    """Each `## ` section of every kb/*.md file is one searchable procedure."""
    docs = []
    for f in sorted(KB_DIR.glob("*.md")):
        docs += [s.strip() for s in f.read_text().split("\n## ")[1:] if s.strip()]
    return docs


@asynccontextmanager
async def lifespan(_):
    global kb_docs, kb_vecs
    kb_docs = load_kb()
    kb_vecs = await asyncio.to_thread(models.embed_docs, kb_docs)
    await asyncio.to_thread(models.warm)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True, "kb_docs": len(kb_docs)}


@app.websocket("/ws/call")
async def call(ws: WebSocket):
    """Client streams binary chunks of 16 kHz mono float32 PCM (~5s each).
    Server answers each chunk with {"type":"transcript"} then {"type":"suggestions"}."""
    await ws.accept()
    try:
        while True:
            pcm = np.frombuffer(await ws.receive_bytes(), dtype=np.float32)
            async with lock:
                text = await asyncio.to_thread(models.transcribe, pcm)
            if not text:
                continue
            await ws.send_json({"type": "transcript", "text": text})
            async with lock:
                hits = await asyncio.to_thread(models.search, text, kb_vecs, kb_docs)
            await ws.send_json({"type": "suggestions", "items": [{"score": s, "text": d} for s, d in hits]})
            # TODO(plan phase 3): Gemma-drafted reply from top hit, sent as {"type":"reply"}
    except WebSocketDisconnect:
        pass


class Transcript(BaseModel):
    transcript: str


@app.post("/notes")
async def notes(body: Transcript):
    prompt = (
        "You write after-call notes for a Philippine call center agent. Transcript (Taglish ok):\n"
        f"{body.transcript}\n\n"
        "Reply with ONLY a JSON object with keys: issue, resolution, disposition, follow_up. English, concise."
    )
    async with lock:
        out = await asyncio.to_thread(models.generate, prompt)
    return models.parse_json(out) or {"raw": out}
