"""Earshot engine: local HTTP/WebSocket API the Tauri app talks to. Nothing here calls the internet.

Run: uv run uvicorn server:app --port 8765
"""

import asyncio
import re
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import models

KB_DIR = Path(__file__).parent / "kb"
DEMO_WAV = Path(__file__).parent / "demo" / "call.wav"
SR, CHUNK = 16000, 16000 * 5
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
app.mount("/demo", StaticFiles(directory=DEMO_WAV.parent), name="demo")  # UI plays the demo audio from here


@app.get("/health")
def health():
    return {"ok": True, "kb_docs": len(kb_docs)}


def split_on_silence(pcm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cut at the quietest 0.1 s of the last second so words aren't split between chunks.
    Returns (audio to transcribe now, audio to carry into the next chunk)."""
    if len(pcm) < 2 * SR:
        return pcm, pcm[:0]
    win = SR // 10
    c = np.concatenate([[0.0], np.cumsum(pcm[-SR:].astype(np.float64) ** 2)])
    cut = len(pcm) - SR + int(np.argmin(c[win:] - c[:-win])) + win // 2
    return pcm[:cut], pcm[cut:]


NUMBER = re.compile(r"\+?\d[\d\s.\-]*\d")  # digit groups split by spaces/dots/dashes: "2222-3333-4821"
EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
TAIL = re.compile(r"\+?\d[\d\s.\-]*[.,]?$")  # digits at the very end of a chunk may continue in the next one


def mask(text: str) -> str:
    """Mask PII before text leaves the engine: any run of 7+ digits (cards, PH mobiles, account numbers)
    becomes "•••• 4821"; emails keep only the domain."""
    def num(m):
        d = re.sub(r"\D", "", m[0])
        return f"•••• {d[-4:]}" if len(d) >= 7 else m[0]
    return EMAIL.sub(r"••••@\1", NUMBER.sub(num, text))


def hold_tail(text: str) -> tuple[str, str]:
    """Split trailing digits off a chunk's text so a number cut across chunks ("For 111." | "2222-3333-4821")
    is masked as one. Returns (text to send now, text to prepend to the next chunk)."""
    m = TAIL.search(text)
    return (text[: m.start()].rstrip(), m[0]) if m else (text, "")


async def handle_chunk(ws: WebSocket, pcm: np.ndarray, held: str = "", final: bool = False) -> str:
    """One audio chunk through the pipeline: {"type":"transcript"} then {"type":"suggestions"}.
    `held` is trailing digits from the previous chunk; returns the new held text."""
    async with lock:
        text = await asyncio.to_thread(models.transcribe, pcm)
    text, held = hold_tail(f"{held} {text}".strip()) if not final else (f"{held} {text}".strip(), "")
    text = mask(text)
    if not text:
        return held
    await ws.send_json({"type": "transcript", "text": text})
    async with lock:
        hits = await asyncio.to_thread(models.search, text, kb_vecs, kb_docs)
    await ws.send_json({"type": "suggestions", "items": [{"score": s, "text": d} for s, d in hits]})
    # TODO(plan phase 3): Gemma-drafted reply from top hit, sent as {"type":"reply"}
    return held


@app.websocket("/ws/call")
async def call(ws: WebSocket):
    """Client streams binary chunks of 16 kHz mono float32 PCM (~5s each)."""
    await ws.accept()
    carry, held = np.zeros(0, dtype=np.float32), ""
    try:
        while True:
            pcm = np.concatenate([carry, np.frombuffer(await ws.receive_bytes(), dtype=np.float32)])
            now, carry = split_on_silence(pcm)
            held = await handle_chunk(ws, now, held)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/demo")
async def demo(ws: WebSocket):
    """Demo-call mode: stream engine/demo/call.wav through the same pipeline at real-time pace,
    then send {"type":"end"}. The UI plays /demo/call.wav alongside."""
    await ws.accept()
    with wave.open(str(DEMO_WAV)) as w:  # 16 kHz mono 16-bit (see demo/make_demo.sh)
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    t0, carry, held = time.monotonic(), audio[:0], ""
    try:
        for i in range(0, len(audio), CHUNK):
            end = min(i + CHUNK, len(audio))
            await asyncio.sleep(max(0.0, t0 + end / SR - time.monotonic()))  # wait until this audio "has been spoken"
            pcm = np.concatenate([carry, audio[i:end]])
            final = end >= len(audio)
            now, carry = (pcm, pcm[:0]) if final else split_on_silence(pcm)  # last chunk: send it all
            held = await handle_chunk(ws, now, held, final)
        await ws.send_json({"type": "end"})
    except (WebSocketDisconnect, RuntimeError):  # client hung up mid-demo
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
