"""The four local models. Every function here runs fully offline from weights in ~/models (see fetch_models.sh)."""

import json
import os
import re
from functools import cache
from pathlib import Path

import numpy as np

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # never reach out to Hugging Face at runtime
MODELS = Path(os.environ.get("EARSHOT_MODELS", "~/models")).expanduser()
WHISPER = str(MODELS / "whisper-large-v3-turbo-mlx")
EMBEDDER = str(MODELS / "embeddinggemma-2")
LLM = str(MODELS / "gemma-4-e4b-it-4bit")
LAYA = str(MODELS / "laya-multilingual")


def transcribe(audio: np.ndarray) -> str:
    """16 kHz mono float32 PCM -> text. ~0.9s for an 8s clip on M5."""
    import mlx_whisper

    return mlx_whisper.transcribe(audio, path_or_hf_repo=WHISPER)["text"].strip()


@cache
def _embedder():
    from sentence_transformers import SentenceTransformer

    # Text-only load (270M of the 740M): no vision/audio encoders needed for KB search.
    return SentenceTransformer(EMBEDDER, config_kwargs={"vision_config": None, "audio_config": None})


def embed_docs(docs: list[str]):
    return _embedder().encode(docs, prompt_name="Document")


def search(query: str, doc_vecs, docs: list[str], k: int = 3) -> list[tuple[float, str]]:
    m = _embedder()
    scores = m.similarity(m.encode(query, prompt_name="SearchQuery"), doc_vecs)[0].tolist()
    return sorted(zip(scores, docs), reverse=True)[:k]


@cache
def _llm():
    from mlx_vlm import load

    return load(LLM)


def generate(prompt: str, max_tokens: int = 300) -> str:
    """Gemma 4 E4B via MLX. ~34 tok/s on M5."""
    from mlx_vlm import generate as gen
    from mlx_vlm.prompt_utils import apply_chat_template

    model, proc = _llm()
    out = gen(model, proc, apply_chat_template(proc, model.config, prompt), max_tokens=max_tokens, verbose=False)
    return getattr(out, "text", out).strip()


@cache
def _laya():
    import laya

    # Official PyTorch package on the Mac GPU, loaded from a local folder (Router() would hit Hugging Face).
    return laya.load(LAYA, device="mps")


def decide(text: str, questions: dict) -> dict:
    """Laya typed decisions, ~30-250 ms on M5. Returns {name: {choice|score|noul: ...}}."""
    return _laya().predict(text, questions)["answers"]


def parse_json(text: str) -> dict:
    """Pull the first {...} block out of a model reply (it likes ```json fences)."""
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def warm():
    """Load everything once at startup so the first call in the demo isn't slow."""
    search("warm up", embed_docs(["warm up"]), ["warm up"])  # first MPS call is ~0.7s, then ~20ms
    _llm()
    decide("warm up", {"x": {"type": "noul", "instructions": "Is this a test?"}})  # first call ~1.4s
    transcribe(np.zeros(16000, dtype=np.float32))
