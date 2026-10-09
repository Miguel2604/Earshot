# Handoff: Earshot (Phase 0.5 overlay done; start PLAN.md Phase 1)

You are picking up a hackathon project mid-build. Read this, then `PLAN.md`, then start Phase 1. Don't re-litigate the decisions below; the user already made them.

## Situation
- **Event:** AppBuildersPH Hackathon 2026, theme **Local AI** (https://appbuildersph.com/hackathon/). **Code freeze 10:00 AM Sat Oct 10, 2026, no extensions.** Judges review the public GitHub repo as of the deadline. Demo Day is in person, on the user's MacBook.
- **Product:** Earshot, an on-device copilot for Filipino call center agents: live transcript → mood + intent → KB procedure → drafted reply → masked after-call notes.
- **Repo state:** `main` has the scaffold, the Earshot rename, and Phase 0.5 (floating overlay) committed. An earlier, unrelated project lives on branch `bantai`. **Leave it alone; the user said to forget it.** There's no git remote yet.

## Decisions already made (by the user)
- Demo on **Mac only** (Apple M5, 24 GB). No Windows build.
- **Tauri 2 + SvelteKit (Svelte 5)** frontend; Python engine on `127.0.0.1:8765`.
- Models, each with one job:
  - **Whisper large-v3-turbo** (`mlx-whisper`): speech-to-text.
  - **EmbeddingGemma 2** (sentence-transformers, text-only): KB search.
  - **Laya multilingual** (official `laya` PyTorch package on `mps`, **not** the MLX port): live typed decisions.
  - **Gemma 4 E4B 4-bit MLX** (`mlx-vlm`): live English subtitles, reply, and notes text.
- **No ticket routing.** Dropped.
- **Never download from Hugging Face** (very slow here, and the user said not to). All weights are in `~/models`; `engine/fetch_models.sh` pulls from ModelScope in parallel chunks.
- UI style comes from `DESIGN.md` (getdesign.md Airtable analysis, chosen by the user over Intercom): white canvas, hairline cards, near-black ink and primary button (12px radius), signature coral `#aa2d00` only for AI elements, headings weight 400–500 (never bold), no web fonts (the app must work offline).
- The user prefers minimal, lazy-but-correct code (ponytail style): no speculative abstractions, shortest working diff.

## What works now (verified)
- `cd app && pnpm tauri dev` builds, opens the window, and auto-starts the engine (`uv run uvicorn server:app`) from `app/src-tauri/src/lib.rs`.
- Engine startup loads + warms all four models (~25 s); `GET /health` → `{"ok":true,"kb_docs":8}`.
- `WS /ws/call`: send binary 16 kHz mono float32 PCM → `{"type":"transcript"}` (~0.8 s), then `{"type":"suggestions","items":[{score,text}]}`.
- `POST /notes {"transcript": "..."}` → `{issue, resolution, disposition, follow_up}` in ~3.7 s.
- `models.decide(text, questions)` returns Laya answers (~30–250 ms warm). **Not yet wired into the pipeline**; that's PLAN Phase 3.
- **Overlay (Phase 0.5):** the window is a frameless, transparent, always-on-top 420x720 panel, visible on all Spaces, docked top-right of the work area with 24px margins on launch (`setup` in `lib.rs`), resizable. Header is the drag region. Stack: suggestion card (coral border) → live transcript (last 6 lines) → call notes (only once the call ends). Screenshot: `docs/phase-0.5.png`. **All later UI goes inside this panel.** `pnpm check` passes.
- Cmd+\ toggles show/hide (global shortcut registered in Rust). Registers without error; **not yet tested by an actual keypress** (synthetic keys were blocked here). **Not yet verified:** mic capture inside the Tauri webview (Phase 1.1).

## Laya: what we learned (important)
Tested zero-shot on 6 Taglish lines (details in PLAN.md):
- `choice` (intent): 3/5 correct. Usable as a hint.
- `score` (mood): directional. Smooth it.
- `noul` (yes/no): **always ~0, unusable.** Gate Gemma with plain rules instead.
- On English translations of the same lines: intent 4/6 and clearer mood. **Decided:** Gemma translates each chunk to English (0.5–1.4 s). It's shown as a live subtitle and fed to Laya (PLAN Phase 3).

Question format that works:
```python
models.decide(text, {
  "intent": {"type": "choice", "instructions": "What is the customer calling about?",
             "criteria": {"technical": "slow or no internet, modem lights", "billing": "double charge, payment, refund", ...}},
  "mood": {"type": "score", "instructions": "How upset or frustrated is the customer?",
           "criteria": ["calm", "slightly annoyed", "frustrated", "angry"]},
})  # -> {"intent": {"choice": "billing", ...}, "mood": {"score": 1.72, ...}}
```

## Map
| Path | What |
|---|---|
| `PLAN.md` | Phases, demo script, risks, submission checklist. **Source of truth for what to do next.** |
| `engine/models.py` | The 4 model calls (`transcribe`, `embed_docs`/`search`, `decide`, `generate`) + `warm()`. Paths from `EARSHOT_MODELS` (default `~/models`). |
| `engine/server.py` | FastAPI app, WS pipeline, notes endpoint, global model lock. |
| `engine/kb/telco.md` | Sample KB; each `## ` section is one retrievable procedure. |
| `engine/fetch_models.sh` | ModelScope downloader (parallel byte ranges) for all 4 models. |
| `app/src/routes/+page.svelte` | The whole UI: mic capture (ScriptProcessor, 5 s chunks), WS client, the glass overlay panel, design tokens. |
| `app/src-tauri/src/lib.rs` | Spawns/kills the engine; docks + shows the overlay; registers Cmd+\. |
| `app/src-tauri/tauri.conf.json` | Overlay window flags (`transparent`, `decorations:false`, `alwaysOnTop`, `visibleOnAllWorkspaces`, `visible:false` until docked) + `macOSPrivateApi`. |
| `app/src-tauri/Info.plist` | macOS mic permission string. |

## Quick checks
```bash
cd engine && uv run uvicorn server:app --port 8765   # engine alone; wait ~25 s for /health
curl -s 127.0.0.1:8765/health
cd app && pnpm check && pnpm tauri dev                 # full app (starts its own engine; don't run both)
```
The frontend also runs in a normal browser at `http://localhost:1420` while `tauri dev` is up (CORS is open), which is handy for UI work.

## Gotchas
- Python is pinned to **3.12**. Don't add `sentence-transformers[audio]` (conflicts with mlx-vlm). `torchvision` must stay; EmbeddingGemma 2 imports it.
- Load Laya with `laya.load(local_path, device="mps")`, never `laya.Router()` (it downloads from Hugging Face).
- `mlx_whisper.audio.load_audio` returns an MLX array. Wrap it with `np.array(..., dtype=np.float32)` before `.tobytes()`.
- Overlay: the window is transparent, so the visible panel has an 8px inset (`.panel { margin: 8px }`) to keep its CSS shadow from being clipped; native window shadow is off (`shadow:false`). Keep `body` background transparent.
- Drag: `data-tauri-drag-region` only works on the element itself, not its children, so the header's text/badge/spacer carry it too. It needs the `core:window:allow-start-dragging` capability (added).
- Don't add content protection (screen-capture hiding): the demo video must show the overlay.
- A stale `vite dev` on port 1420 (orphaned from an earlier session) makes `tauri dev` fail with "beforeDevCommand terminated". Check `lsof -nP -iTCP:1420 -sTCP:LISTEN` first.
- Only one engine can bind port 8765. Kill stray `uvicorn server:app` processes before `tauri dev`.
- Model jobs share one lock, so a long Gemma call delays the next transcript. See PLAN Phase 3 gating.
- Whisper quality on *real* Taglish speech is unknown (only tested on a TTS clip). Ask the user for a real recording early; it doubles as the demo call (PLAN Phase 6).

## Next actions
1. Press Cmd+\ once in `pnpm tauri dev` to confirm the toggle. Then PLAN Phase 1: mic in the Tauri webview (overlay window), then **demo-call mode** (stream a WAV from `engine/demo/`). Ask the user to record the 60–90 s escalating Taglish mock call described in PLAN Phase 6.
2. Phases 2 → 5 in order. Start Phase 6 (video + submission) no later than 7:00 AM.
3. Commit early and often; ask the user before creating the GitHub remote or pushing. The repo must be public by 10:00 AM.
