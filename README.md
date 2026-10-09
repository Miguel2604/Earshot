# Earshot

On-device AI copilot for Philippine call center agents. It transcribes the call, pulls up the right procedure from the company knowledge base as the customer talks, and drafts the after-call notes. **Everything runs on the agent's computer, so customer data never leaves the machine.**

Built for AppBuildersPH Hackathon 2026 (theme: Local AI).

## Why local
BPO clients forbid pasting customer data into cloud AI tools (client contracts, Data Privacy Act RA 10173). Agents need suggestions in real time, mid-call. Local inference makes both possible: no data egress, no per-call API cost, works with the network unplugged.

## Stack
| Layer | Tech |
|---|---|
| Desktop app | Tauri 2 + SvelteKit (Svelte 5) |
| AI engine | Python 3.12, FastAPI on `127.0.0.1:8765` |
| Speech-to-text | Whisper large-v3-turbo via `mlx-whisper` |
| Knowledge-base search | EmbeddingGemma 2 (text-only, 270M) via `sentence-transformers` |
| Live typed decisions (intent, mood) | Laya multilingual (322M) via the `laya` package (PyTorch, Apple GPU) |
| Reply + call notes | Gemma 4 E4B (4-bit MLX) via `mlx-vlm` |

Demo hardware: MacBook (Apple M5, 24 GB). Windows path (whisper.cpp + llama.cpp behind the same engine API) is planned, not built.

## What runs locally / what needs internet
- **Local:** all AI inference (speech-to-text, embeddings, LLM), the UI, the knowledge base.
- **Internet:** only once, to download model weights (`engine/fetch_models.sh`). The engine runs with `HF_HUB_OFFLINE=1`.

## Run it
Requires macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/), pnpm, Rust.

```bash
./engine/fetch_models.sh          # ~9 GB into ~/models, from ModelScope
cd engine && uv sync && cd ..
cd app && pnpm install && pnpm tauri dev
```
`pnpm tauri dev` starts the engine automatically; the first launch takes ~20 s to load models.

## Disclosures
- **Models:** Whisper large-v3-turbo (OpenAI, MIT, MLX conversion by mlx-community), EmbeddingGemma 2 (Google, Apache 2.0), Gemma 4 E4B-it 4-bit MLX (Google, Apache 2.0; conversion by mlx-community), Laya multilingual (Convai Innovations, Apache 2.0).
- **Frameworks:** Tauri, SvelteKit, FastAPI, MLX, mlx-whisper, mlx-vlm, sentence-transformers, PyTorch.
- **Cloud APIs:** none.
- **Design reference:** `DESIGN.md` from getdesign.md (Airtable analysis), used as a style starting point.
- **Prior work:** the idea of AI call classification is inspired by the team's earlier Neosolve project (Agora Voice AI Hackathon); no code reused.
- **AI dev tools:** Claude Code.
