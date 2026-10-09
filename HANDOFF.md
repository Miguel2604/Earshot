# Handoff: Earshot (Phase 3 live signals done; start PLAN.md Phase 4)

You are picking up a hackathon project mid-build. Read this, then `PLAN.md`, then start Phase 4. Don't re-litigate the decisions below; the user already made them.

## Situation
- **Event:** AppBuildersPH Hackathon 2026, theme **Local AI** (https://appbuildersph.com/hackathon/). **Code freeze 10:00 AM Sat Oct 10, 2026, no extensions.** Judges review the public GitHub repo as of the deadline. Demo Day is in person, on the user's MacBook.
- **Product:** Earshot, an on-device copilot for Filipino call center agents: live transcript → mood + intent → KB procedure → drafted reply → masked after-call notes.
- **Repo state:** `main` has the scaffold, the Earshot rename, Phase 0.5 (floating overlay), Phase 1 (demo-call mode, silence chunking), Phase 2 (live PII masking) and Phase 3 (subtitles, Laya signals, escalation, gated reply) committed. An earlier, unrelated project lives on branch `bantai`. **Leave it alone; the user said to forget it.** There's no git remote yet.

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
- `WS /ws/call`: send binary 16 kHz mono float32 PCM → per chunk `transcript`, `translation`, `signals`, `suggestions`, `reply` (see Phase 3 below). The engine cuts each chunk at its quietest 0.1 s in the last second and carries the rest into the next chunk (`split_on_silence`), so words aren't split.
- **Demo-call mode (Phase 1):** `WS /ws/demo` streams `engine/demo/call.wav` through the same `handle_chunk` pipeline at real-time pace, then `{"type":"end"}`. The header's "Demo call" button opens it, plays `GET /demo/call.wav`, and auto-ends the call when `end` arrives (notes appear). Each transcript lands ~0.4–0.5 s after its audio. Screenshot: `docs/phase-1.png`.
- `engine/demo/call.wav` is a **placeholder** (59 s, macOS `say` voices, regenerate with `engine/demo/make_demo.sh`): Taglish double charge, angry customer, card number `4111 2222 3333 4821`, agent files a refund. Replace with the real recording in Phase 6 (same filename, 16 kHz mono 16-bit WAV).
- **PII masking (Phase 2):** every transcript goes through `mask()` in `engine/server.py` before it's sent, so the UI, KB search and notes only see masked text. Any run of 7+ digits (groups may be split by spaces/dots/dashes) → `•••• 4821` (cards, PH mobiles, account numbers); emails → `••••@domain`; short numbers (amounts, days, times) stay. `hold_tail()` holds digits at the end of a chunk and prepends them to the next one, so a number cut across chunks is masked as one. On the demo WAV the card shows as `•••• 4821 Ibalik ni Iona young perico` (35.4 s, ~0.4 s after its audio); the line before ends `…card ko. For`. Panel footer: "0 bytes sent to cloud" / "PII masked on-device". Transcript card auto-scrolls. Screenshot: `docs/phase-2.png`.
- `POST /notes {"transcript": "..."}` → `{issue, resolution, disposition, follow_up}` in ~3.7 s.
- **Live signals (Phase 3):** after each transcript, a background `enrich` job (in `server.py`) runs translation → Laya → KB → reply under the one lock; translation/reply are skipped if a newer chunk has arrived. Messages (all carry the chunk `id`; all text masked): `{"type":"translation","text"}` (Gemma English subtitle, skipped when the chunk has no common Tagalog word), `{"type":"signals","intent","intent_p","mood","mood_raw","escalate"}`, `{"type":"suggestions"}` (intent boost +0.05; escalation pins "Angry or escalating customer"), `{"type":"reply","text"}` (Gemma "say this", gated by `?`/request words/intent change/escalation). Per chunk: Whisper 0.4 s, translate 0.4–0.8 s, Laya+KB 0.07 s, reply 0.7–1.2 s → ≤2.5 s of each 5 s chunk, keeps up with real time. On the demo, escalation fires at 40.9 s and 45.5 s (right after the 35 s outburst) and clears at 50 s. UI: "Say this" reply at the top of the coral card, procedures under it, intent chip + mood meter, escalation banner + "Flag supervisor" (local toggle only), italic English subtitle under each line. Screenshot: `docs/phase-3.png`.
- **Overlay (Phase 0.5):** the window is a frameless, transparent, always-on-top 420x720 panel, visible on all Spaces, docked top-right of the work area with 24px margins on launch (`setup` in `lib.rs`), resizable. Header is the drag region. Stack: suggestion card (coral border) → live transcript (last 6 lines) → call notes (only once the call ends). Screenshot: `docs/phase-0.5.png`. **All later UI goes inside this panel.** `pnpm check` passes.
- Cmd+\ toggles show/hide (global shortcut registered in Rust). Registers without error; **not yet tested by an actual keypress** (synthetic keys were blocked here).
- **Not verified:** mic capture inside the Tauri webview (the permission prompt can't be accepted unattended). If `getUserMedia` fails, the transcript card says "Microphone unavailable… Use Demo call." Fallback if it fails for real: capture in the engine with `sounddevice`, same WS messages (PLAN Phase 1.1).

## Laya: what we learned (important)
Tested zero-shot on 6 Taglish lines (details in PLAN.md):
- `choice` (intent): 3/5 correct. Usable as a hint.
- `score` (mood): directional. Smooth it.
- `noul` (yes/no): **always ~0, unusable.** Gate Gemma with plain rules instead.
- On English translations of the same lines: intent 4/6 and clearer mood. **Decided:** Gemma translates each chunk to English (0.5–1.4 s). It's shown as a live subtitle and fed to Laya (PLAN Phase 3).

**Mood (Phase 3 finding):** the 4-level `score` was flat on the demo (greeting = shouting ≈ 1.1). What works: a 2-way `choice` and its P(angry), see `QUESTIONS["mood"]` in `server.py` (greeting 0.01, angry 0.88–0.92, calm ≤0.24). EmbeddingGemma-vs-examples was tried as the fallback and is useless (all similarities 0.85–0.98).

Question format that works (intent):
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
| `engine/server.py` | FastAPI app: `handle_chunk` (transcript) + `enrich` (translation/signals/KB/reply), Laya `QUESTIONS`, `MOOD_HIGH`, `/ws/call` (mic), `/ws/demo` (demo WAV), `/demo/*` static, `/notes`, global model lock. |
| `engine/demo/` | `call.wav` (placeholder demo call) + `make_demo.sh` that generates it. |
| `engine/test_chunking.py` | Assert check for `split_on_silence` (`uv run python test_chunking.py`, no models). |
| `engine/test_signals.py` | Assert check for the Phase 3 rules: `is_english`, reply gate `REQUEST`, KB `boosted` (no models). |
| `engine/test_masking.py` | Assert check for `mask`/`hold_tail`, using real Whisper output from the demo WAV (`uv run python test_masking.py`, no models). |
| `engine/kb/telco.md` | Sample KB; each `## ` section is one retrievable procedure. |
| `engine/fetch_models.sh` | ModelScope downloader (parallel byte ranges) for all 4 models. |
| `app/src/routes/+page.svelte` | The whole UI: mic capture (ScriptProcessor, 5 s chunks), demo-call playback, WS client, the glass overlay panel (reply card, signals strip, escalation banner, subtitles), "0 bytes sent to cloud" footer, design tokens. |
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
- Whisper is forced to `language="tl"` in `models.transcribe`: auto-detect turned an Indian-accent TTS chunk into Hindi script; forced Tagalog still writes English words fine. Quality on *real* Taglish speech is still unknown (only TTS so far). Ask the user for a real recording; it replaces `engine/demo/call.wav` (PLAN Phase 6).
- KB suggestions follow only the latest chunk, so the closing line ("thank you for calling") puts "Slow internet" on top at the end of the demo. The intent boost doesn't fix it because Laya also calls that line `technical` (0.93); same bias makes the first reply ask about modem lights. Searching the last 2 lines instead was tried and didn't help (Relocation came out on top). Re-check on the real recording before tuning (options: freeze suggestions when intent is `closing`, reword the `technical` criteria).
- Escalation needs the smoothed mood ≥ 0.5 on 2 chunks in a row, so the banner lands ~5 s after the outburst. Tune `MOOD_HIGH` / the 2-chunk rule on the real recording, not the TTS one.
- `enrich` runs as an `asyncio` task; `/ws/demo` awaits the last one before sending `end`. The engine log prints per-stage timings per chunk (`chunk N: whisper … translate … laya+kb … reply …`).
- Whisper errors seen on the TTS demo: "Na charge ako ng Daloyang bes" (dalawang beses), "Bastard I text" (Basta i-text). The card number came out as `For 111.` + `2222-3333-4821` across two chunks ("four" → "For"); masking handles it via `hold_tail`, but digits spoken as words ("four one one one", Tagalog numbers) are **not** masked. Check the real recording's transcript in Phase 6 and extend `mask()` only if needed.
- Any new text that leaves the engine must go through `mask()` (translations and replies already do; Gemma's input is the masked chunk). Phase 4's notes fields too.
- `hold_tail` delays digits at a chunk's end by one chunk (~5 s). On `/ws/call` (mic) a trailing held fragment is dropped if the call ends; on `/ws/demo` it's flushed on the last chunk.
- The "0 bytes sent to cloud" footer is static text (true by construction: the engine makes no network calls, `HF_HUB_OFFLINE=1`). Phase 5 adds the `navigator.onLine` indicator next to it.
- The built-in browser's screenshots save as JPEG under `~/.claude/projects/.../tool-results/`; convert with `sips -s format png <file> --out docs/phase-N.png`.
- `tauri dev` binary is `app/src-tauri/target/debug/earshot`; killing `tauri dev` can leave it running. Check `pgrep -fl target/debug/earshot`.
- `pkill -f "tauri dev"` leaves its `vite dev` child listening on 1420; kill it too (`lsof -nP -iTCP:1420 -sTCP:LISTEN`).
- At 420px the idle header (badge + "Demo call" + "Start call") is tight: header buttons use 12px side padding and a 6px gap to fit. Don't add header items without re-checking `scrollWidth`.
- The engine closes `/ws/demo` without a close frame after `end`; a Python `websockets` client raises `ConnectionClosedError` (harmless, the UI closes on `end`).

## Next actions
1. PLAN **Phase 4**: `/notes` → Laya picks category, priority, disposition from fixed lists (with confidence); Gemma writes only summary + follow-up, told not to invent facts; editable fields + "Copy to CRM" (clipboard). Notes use the masked transcript; mask Gemma's output too. Verify with the demo call and a `docs/phase-4.png` screenshot.
2. Still unverified (needs the user at the keyboard): press Cmd+\ once in `pnpm tauri dev`; click "Start call" once to accept the mic prompt. If the webview can't capture, use the PLAN Phase 1.1 fallback (`sounddevice` in the engine).
3. Phase 5, then Phase 6. Ask the user to record the 60–90 s Taglish mock call and save it as `engine/demo/call.wav`; then re-check Laya intent/mood and `MOOD_HIGH` on it. Start Phase 6 (video + submission) no later than 7:00 AM.
4. Commit early and often; ask the user before creating the GitHub remote or pushing. The repo must be public by 10:00 AM.
