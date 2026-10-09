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


TAGALOG = set("ng po opo ako ko mo na yung ang sa mga niyo ninyo naman hindi pa ba kasi talaga sige salamat lang ito eto kayo siya natin namin bakit paano pwede paki ba't".split())
REQUEST = re.compile(r"\?|\b(paki\w*|pwede|puwede|bakit|paano|can you|please)\b", re.I)
INTENTS = {  # Laya intent option -> its description; KEYWORD marks the KB section titles it boosts
    "billing": "double charge, bill, payment, refund",
    "technical": "slow or no internet, modem, connection",
    "cancel": "cancel or end the subscription",
    "relocation": "moving house, transfer service to a new address",
    "closing": "thanks, issue resolved, goodbye",
}
KEYWORD = {"billing": ("billing", "payment"), "technical": ("internet",), "cancel": ("cancel",), "relocation": ("relocation",)}
ANGRY = "Angry or escalating"
QUESTIONS = {
    "intent": {"type": "choice", "instructions": "What is the customer calling about?", "criteria": INTENTS},
    # A 4-level `score` came out flat (1.0-1.5 for greeting and shouting alike); P(angry) of a 2-way choice separates.
    "mood": {"type": "choice", "instructions": "What is the speaker's tone?",
             "criteria": {"polite": "calm, friendly, thankful", "angry": "angry, demanding, complaining, impatient"}},
}
SMALL_TALK = re.compile(r"thank you for calling|how (may|can) i (help|assist)|salamat (po )?sa pagtawag", re.I)
MOOD_HIGH = 0.5  # smoothed P(angry) at or above this for 2 chunks -> escalate; calibrated on the demo call


def new_call() -> dict:
    """Per-connection state. seq counts chunks received; a job whose chunk number < seq is stale."""
    return {"held": "", "seq": 0, "lines": [], "moods": [], "high": 0, "intent": None, "esc": False, "votes": {}, "task": None}


def is_english(text: str) -> bool:
    return not TAGALOG & set(re.findall(r"[a-z']+", text.lower()))


def small_talk(text: str) -> bool:
    """Greetings, goodbyes and short fragments say nothing about the topic (Laya calls them `technical`, ~0.95)."""
    return len(text.split()) < 3 or bool(SMALL_TALK.search(text))


def vote(st: dict, intent: str, p: float) -> tuple[str | None, float]:
    """The call's intent is the running best (summed Laya confidence), so one noisy chunk can't flip it.
    Returns (call intent, its share of all votes)."""
    if intent != "closing":  # small talk is passed in as "closing": no vote
        st["votes"][intent] = st["votes"].get(intent, 0) + p
    v = st["votes"]
    best = max(v, key=v.get, default=None)
    return best, (v[best] / sum(v.values()) if best else 0)


def boosted(hits: list[tuple[float, str]], intent: str | None, escalate: bool) -> list[tuple[float, str]]:
    """Small bonus for procedures whose title matches the intent; escalation pins the angry-customer script on top."""
    kw = KEYWORD.get(intent, ())
    out = sorted(((s + 0.05 * any(k in d.split("\n")[0].lower() for k in kw), d) for s, d in hits), reverse=True)
    if escalate:
        out = [(1.0, d) for d in kb_docs if d.startswith(ANGRY)] + [h for h in out if not h[1].startswith(ANGRY)]
    return out[:3]


async def handle_chunk(ws: WebSocket, pcm: np.ndarray, st: dict, final: bool = False):
    """Transcribe one chunk and send {"type":"transcript"}; the rest (translation, signals, suggestions, reply)
    runs as a background job so the next chunk's transcript never waits behind a stale one."""
    st["seq"] += 1
    n, t0 = st["seq"], time.monotonic()
    async with lock:
        text = await asyncio.to_thread(models.transcribe, pcm)
    joined = f"{st['held']} {text}".strip()
    text, st["held"] = hold_tail(joined) if not final else (joined, "")
    text = mask(text)
    if not text:
        return
    await ws.send_json({"type": "transcript", "id": n, "text": text})
    st["lines"].append(text)
    st["task"] = asyncio.create_task(enrich(ws, n, text, st, {"whisper": time.monotonic() - t0}))


async def enrich(ws: WebSocket, n: int, text: str, st: dict, ms: dict):
    """Priority under the one lock: translation -> Laya -> KB -> reply. Stale translation/reply jobs are dropped."""
    def tick(k, t):
        ms[k] = time.monotonic() - t
    try:
        en = text
        if not is_english(text) and st["seq"] == n:
            t = time.monotonic()
            async with lock:
                en = mask(await asyncio.to_thread(models.generate,
                    f"Translate to natural English. Output only the translation.\n\n{text}", 60))
            tick("translate", t)
            await ws.send_json({"type": "translation", "id": n, "text": en})
        t = time.monotonic()
        async with lock:
            a = await asyncio.to_thread(models.decide, en, QUESTIONS)
            hits = await asyncio.to_thread(models.search, text, kb_vecs, kb_docs, 5)
        tick("laya+kb", t)
        small = small_talk(text)
        intent, p = vote(st, "closing" if small else a["intent"]["choice"], a["intent"].get("confidence", 0))
        st["moods"].append(a["mood"]["probabilities"]["angry"])
        mood = sum(st["moods"][-3:]) / len(st["moods"][-3:])  # smoothed over the last 3 chunks
        st["high"] = st["high"] + 1 if mood >= MOOD_HIGH else 0
        escalate = st["high"] >= 2
        await ws.send_json({"type": "signals", "id": n, "intent": intent, "intent_p": p, "mood": mood,
                            "mood_raw": st["moods"][-1], "escalate": escalate})
        if small and not escalate:  # keep the previous procedures and reply
            print(f"chunk {n}: small talk, " + " ".join(f"{k} {v:.2f}s" for k, v in ms.items()), flush=True)
            return
        hits = boosted(hits, intent, escalate)
        await ws.send_json({"type": "suggestions", "items": [{"score": s, "text": d} for s, d in hits]})
        changed = (intent, escalate) != (st["intent"], st["esc"])  # new topic, or escalation started/cleared
        st["intent"], st["esc"] = intent, escalate
        if (REQUEST.search(text) or changed or escalate) and st["seq"] == n:  # plain-rule gate (Laya yes/no is unusable)
            t = time.monotonic()
            recent = "\n".join(st["lines"][-3:])
            async with lock:
                reply = await asyncio.to_thread(models.generate,
                    "You help a Philippine call center agent. Suggest the agent's next line: 1-2 short sentences, "
                    "polite, Taglish ok (use po). Follow the procedure; don't invent facts. Output only the line.\n\n"
                    f"Procedure:\n{hits[0][1]}\n\nLast lines of the call:\n{recent}", 80)
            tick("reply", t)
            await ws.send_json({"type": "reply", "id": n, "text": mask(reply)})
        print(f"chunk {n}: " + " ".join(f"{k} {v:.2f}s" for k, v in ms.items()), flush=True)
    except (WebSocketDisconnect, RuntimeError):  # client hung up
        pass


@app.websocket("/ws/call")
async def call(ws: WebSocket):
    """Client streams binary chunks of 16 kHz mono float32 PCM (~5s each)."""
    await ws.accept()
    carry, st = np.zeros(0, dtype=np.float32), new_call()
    try:
        while True:
            pcm = np.concatenate([carry, np.frombuffer(await ws.receive_bytes(), dtype=np.float32)])
            now, carry = split_on_silence(pcm)
            await handle_chunk(ws, now, st)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/demo")
async def demo(ws: WebSocket):
    """Demo-call mode: stream engine/demo/call.wav through the same pipeline at real-time pace,
    then send {"type":"end"}. The UI plays /demo/call.wav alongside."""
    await ws.accept()
    with wave.open(str(DEMO_WAV)) as w:  # 16 kHz mono 16-bit (see demo/make_demo.sh)
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    t0, carry, st = time.monotonic(), audio[:0], new_call()
    try:
        for i in range(0, len(audio), CHUNK):
            end = min(i + CHUNK, len(audio))
            await asyncio.sleep(max(0.0, t0 + end / SR - time.monotonic()))  # wait until this audio "has been spoken"
            pcm = np.concatenate([carry, audio[i:end]])
            final = end >= len(audio)
            now, carry = (pcm, pcm[:0]) if final else split_on_silence(pcm)  # last chunk: send it all
            await handle_chunk(ws, now, st, final)
        if st["task"]:
            await st["task"]  # let the last chunk's signals/reply arrive before "end"
        await ws.send_json({"type": "end"})
    except (WebSocketDisconnect, RuntimeError):  # client hung up mid-demo
        pass


class Transcript(BaseModel):
    transcript: str


NOTE_QUESTIONS = {  # fixed lists -> dropdown-safe values; Laya answers them on Gemma's English summary
    "category": {"type": "choice", "instructions": "What was the call about?", "criteria": {
        "billing": "double charge, bill, payment, refund", "technical": "slow or no internet, modem, connection",
        "cancellation": "cancel or end the subscription", "relocation": "moving house, transfer service to a new address",
        "other": "general inquiry, anything else"}},
    "priority": {"type": "choice", "instructions": "How urgent is the follow-up?", "criteria": {
        "low": "nothing pending, simple question", "medium": "a pending action such as a refund, ticket or visit",
        "high": "angry or escalated customer, service down, repeat complaint"}},
    "disposition": {"type": "choice", "instructions": "How did the call end?", "criteria": {
        "resolved": "fixed during the call, nothing pending", "follow-up": "refund, ticket or callback still pending",
        "escalated": "handed to a supervisor", "unresolved": "no solution offered"}},
}


@app.post("/notes")
async def notes(body: Transcript):
    """Gemma writes only free text (summary, follow-up); Laya picks category/priority/disposition from fixed lists.
    The transcript is already masked; Gemma's output is masked again before it leaves."""
    prompt = (
        "You write after-call notes for a Philippine call center agent. Transcript (Taglish, may have speech-to-text errors):\n"
        f"{body.transcript}\n\n"
        'Reply with ONLY a JSON object: {"summary": "1-2 sentences in English: the issue and what was done", '
        '"follow_up": "what the agent or company must still do, or None"}. '
        "Use only facts stated in the transcript. Don't invent names, amounts, dates, or numbers."
    )
    async with lock:
        out = await asyncio.to_thread(models.generate, prompt, 160)
        try:
            j = models.parse_json(out) or {"summary": out}
        except ValueError:  # malformed JSON: keep the text, the agent edits it
            j = {"summary": out}
        summary, follow = mask(str(j.get("summary", ""))), mask(str(j.get("follow_up", "")))
        a = await asyncio.to_thread(models.decide, f"{summary}\nFollow-up: {follow}", NOTE_QUESTIONS)
    res = {k: {"value": a[k]["choice"], "confidence": a[k]["probabilities"][a[k]["choice"]],
               "options": list(q["criteria"])} for k, q in NOTE_QUESTIONS.items()}
    return res | {"summary": summary, "follow_up": follow}


QA_STEPS = [  # (checklist label, what Gemma looks for); from kb/telco.md's billing + angry-customer procedures
    ("Verify identity", "Asked for or verified the customer's identity or account"),
    ("Acknowledge & apologize", "Acknowledged the problem and apologized"),
    ("Resolution + timeline", "Gave the resolution and when it will happen"),
    ("Confirm via SMS", "Promised an SMS or text confirmation"),
    ("Supervisor callback", "Offered a supervisor callback when the customer asked for a supervisor"),
]


def grounded(quote, transcript: str) -> bool:
    """A step counts only if Gemma's evidence quote is really in the transcript (most of its words are)."""
    words = re.findall(r"\w+", str(quote or "").lower())
    have = set(re.findall(r"\w+", transcript.lower()))
    return quote not in (None, "null", "None") and len(words) > 0 and sum(w in have for w in words) >= 0.6 * len(words)


@app.post("/qa")
async def qa(body: Transcript):
    """QA checklist that ticks itself: Gemma quotes where the agent did each step (or null). Asking for a quote
    instead of yes/no stops it ticking steps that never happened; grounded() drops made-up quotes."""
    steps = "\n".join(f"{i + 1}. {d}" for i, (_, d) in enumerate(QA_STEPS))
    prompt = (
        "You check a Philippine call center call against a QA checklist. Transcript (Taglish, may have speech-to-text "
        f"errors, no speaker labels):\n{body.transcript}\n\nQA steps:\n{steps}\n\n"
        'Reply with ONLY a JSON object mapping each step number to a few words copied from the transcript where the '
        'agent did that step, or null if the agent didn\'t: {"1": "...", "2": null, ...}'
    )
    async with lock:
        out = await asyncio.to_thread(models.generate, prompt, 120)
    try:
        j = models.parse_json(out)
    except ValueError:
        j = {}
    return {"steps": [{"label": label, "done": grounded(q := j.get(str(i + 1)), body.transcript), "quote": mask(str(q or ""))}
                      for i, (label, _) in enumerate(QA_STEPS)]}
