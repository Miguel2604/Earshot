# Handoff: Earshot (build stopped; see "Status at stop" at the bottom. Miguel watches one native run, uploads, posts, pushes and submits)

You are picking up a hackathon project at the finish line. Read this, then `PLAN.md`. The build is stopped: start with "Status at stop" at the bottom (what's done, verified, risky, and Miguel's demo steps + to-do list). Don't re-litigate the decisions below; the user already made them.

## Situation
- **Event:** AppBuildersPH Hackathon 2026, theme **Local AI** (https://appbuildersph.com/hackathon/). **Code freeze 10:00 AM Sat Oct 10, 2026, no extensions.** Judges review the public GitHub repo as of the deadline. Demo Day is in person, on the user's MacBook.
- **Product:** Earshot, an on-device copilot for Filipino call center agents: live transcript → mood + intent → KB procedure → drafted reply → masked after-call notes.
- **Repo state:** `main` has the scaffold, the Earshot rename, Phase 0.5 (floating overlay), Phase 1 (demo-call mode, silence chunking), Phase 2 (live PII masking), Phase 3 (subtitles, Laya signals, escalation, gated reply), Phase 4 (structured, editable notes + Copy to CRM), Phase 5 (Online/Offline indicator, offline flags, locality check) Phase 6 code side, the fix-up, the QA checklist, the Cluely-style UI, Phase 7, Phase 8 (slim), Phase 10, Phase 11, the demo rehearsal and the demo video committed. An earlier, unrelated project lives on branch `bantai`. **Leave it alone; the user said to forget it.** There's no git remote yet.

## Decisions already made (by the user)
- Demo on **Mac only** (Apple M5, 24 GB). No Windows build.
- **Tauri 2 + SvelteKit (Svelte 5)** frontend; Python engine on `127.0.0.1:8765`.
- Models, each with one job:
  - **Whisper large-v3-turbo** (`mlx-whisper`): speech-to-text.
  - **EmbeddingGemma 2** (sentence-transformers, text-only): KB search.
  - **Laya multilingual** (official `laya` PyTorch package on `mps`, **not** the MLX port): live typed decisions.
  - **Gemma 4 E4B 4-bit MLX** (`mlx-vlm`): live English subtitles, reply, and notes text.
- **Ticket routing: added back** (Miguel reversed the earlier drop). `/notes` also returns `route: {queue, p, reason, options}`: Laya picks one of 5 queues (`NOTE_QUESTIONS["route"]`) in the same `decide` call as the other picks; `route()` overrides to Supervisor Escalations when the transcript has a supervisor/manager demand or disposition is "escalated" (asserted in `test_signals.py`). UI: "Route to" dropdown + confidence + muted reason in the notes card; `Route: <queue>` in Copy to CRM. Demo → Supervisor Escalations 1.00. Screenshot `docs/ticket-routing.png`.
- **Never download from Hugging Face** (very slow here, and the user said not to). All weights are in `~/models`; `engine/fetch_models.sh` pulls from ModelScope in parallel chunks.
- UI style: **Cluely-style clear glass** (Miguel's request, overrides `DESIGN.md`'s light Airtable colors): a tinted glass wash that follows the macOS appearance (dark: `rgba(20,20,24,.7)` + white text with dark shadows; light: `rgba(250,250,252,.84)` + dark ink with a white halo, coral darkened to `#c8461a`), no `backdrop-filter`, no native vibrancy (see the Flicker gotcha), hairline borders, pill buttons/chips, light coral `#ff9470` (`--ai`, `--ai-tint`, `--ai-line`) only for AI elements. `DESIGN.md`'s restraint still applies: headings weight 400–500 (never bold), no web fonts (the app must work offline). Style any new UI with the tokens at the top of `+page.svelte`'s `<style>`.
- The user prefers minimal, lazy-but-correct code (ponytail style): no speculative abstractions, shortest working diff.

## What works now (verified)
- `cd app && pnpm tauri dev` builds, opens the window, and auto-starts the engine (`uv run uvicorn server:app`) from `app/src-tauri/src/lib.rs`.
- Engine startup loads + warms all four models (~25 s); `GET /health` → `{"ok":true,"kb_docs":8}`.
- `WS /ws/call`: send binary 16 kHz mono float32 PCM → per chunk `transcript`, `translation`, `signals`, `suggestions`, `reply` (see Phase 3 below). The engine cuts each chunk at its quietest 0.1 s in the last second and carries the rest into the next chunk (`split_on_silence`), so words aren't split.
- **Demo-call mode (Phase 1):** `WS /ws/demo` streams `engine/demo/call.wav` through the same `handle_chunk` pipeline at real-time pace, then `{"type":"end"}`. The header's "Demo call" button opens it, plays `GET /demo/call.wav`, and auto-ends the call when `end` arrives (notes appear). Each transcript lands ~0.4–0.5 s after its audio. Screenshot: `docs/phase-1.png`.
- **Phase 11:** `engine/demo/call.wav` is now the **ElevenLabs** call (64.3 s, built by `engine/demo/elevenlabs/build.sh` from Miguel's clips, which are gitignored; includes the CVV ask). Beats: subtitle 6.7, billing 11.2, CVV alert + `•••` 30.5, `•••• 4821` 40.5, escalation 46.2 (supervisor-demand rule), cleared 61.2, end 65.4 s. The old placeholder below is now `engine/demo/call-tts.wav`.
- **Phase 8 (slim):** CVV/OTP/PIN/password asks → red dismissable banner + failed QA chip; 3–8 digits after those keywords masked (`SECRET`, `mask_with`, `alert` in `server.py`). Live QA skipped. Screenshot `docs/phase-8.png`.
- `engine/demo/call-tts.wav` (formerly `call.wav`) is the old **placeholder** (66 s, macOS `say` voices): Taglish double charge, angry customer, card number `4111 2222 3333 4821`, supervisor demand, agent files a refund. It's the verified 59 s Phase 1 file with one line spliced in at 35.6 s (see Phase 6). `make_demo.sh` contains the same script, but today's `say` voices produce different audio, so a rerun is not byte-identical and changes the beat timings (re-verify if you regenerate).
- **PII masking (Phase 2):** every transcript goes through `mask()` in `engine/server.py` before it's sent, so the UI, KB search and notes only see masked text. Any run of 7+ digits (groups may be split by spaces/dots/dashes) → `•••• 4821` (cards, PH mobiles, account numbers); emails → `••••@domain`; short numbers (amounts, days, times) stay. `hold_tail()` holds digits at the end of a chunk and prepends them to the next one, so a number cut across chunks is masked as one. On the demo WAV the card shows as `•••• 4821 Ibalik ni Iona young perico` (35.4 s, ~0.4 s after its audio); the line before ends `…card ko. For`. Panel footer: live egress meter (Phase 7) / "PII masked on-device". Transcript card auto-scrolls. Screenshot: `docs/phase-2.png`.
- **Notes (Phase 4):** `POST /notes {"transcript": "<masked lines>"}` → `{category, priority, disposition: {value, confidence, options}, summary, follow_up}` in ~2.0 s warm. Gemma writes only `summary`/`follow_up` (masked; told not to invent facts); Laya picks the three fixed-list fields from Gemma's English summary (`NOTE_QUESTIONS` in `server.py`). On the demo: billing 1.00 / medium 0.53 / follow-up 0.82, summary only states transcript facts, no digits. UI: three dropdowns with confidence, editable summary + follow-up textareas, "Copy to CRM" (plain text incl. edits; verified via `pbpaste`). Screenshot: `docs/phase-4.png`.
- **Prove local (Phase 5):** footer "● Online/Offline · 0 bytes sent to cloud" + "PII masked on-device" (`<svelte:window bind:online>`; green dot when offline; fits 420px, scrollWidth 378 = clientWidth). `models.py` sets `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY` before any HF import; `lib.rs` starts the engine with `uv run --offline`. Locality proven without touching Wi-Fi: `lsof -nP -i -a -p` sampled every 0.5 s on the uv + Python engine from launch through model load, a full `/ws/demo` and `/notes` → only `127.0.0.1:8765` sockets. The browser pane's network log shows only `localhost:1420` / `127.0.0.1:8765`. The real Wi-Fi-off run is a by-hand checklist in PLAN Phase 5 (the user does it). Screenshot (offline emulated in-page): `docs/phase-5.png`.
- **Live signals (Phase 3):** after each transcript, a background `enrich` job (in `server.py`) runs translation → Laya → KB → reply under the one lock; translation/reply are skipped if a newer chunk has arrived. Messages (all carry the chunk `id`; all text masked): `{"type":"translation","text"}` (Gemma English subtitle, skipped when the chunk has no common Tagalog word), `{"type":"signals","intent","intent_p","mood","mood_raw","escalate"}`, `{"type":"suggestions"}` (intent boost +0.05; escalation pins "Angry or escalating customer"), `{"type":"reply","text"}` (Gemma "say this", gated by `?`/request words/call-intent change/escalation start or clear; skipped on small talk). Per chunk: Whisper 0.4 s, translate 0.4–0.8 s, Laya+KB 0.07 s, reply 0.7–1.2 s → ≤2.5 s of each 5 s chunk, keeps up with real time. On the demo, escalation fires at 40.9 s and 45.5 s (right after the 35 s outburst) and clears at 50 s. UI: "Say this" reply at the top of the coral card, procedures under it, intent chip + mood meter, escalation banner + "Flag supervisor" (local toggle only), italic English subtitle under each line. Screenshot: `docs/phase-3.png`.
- **Phase 6 (code side):** the 66 s demo WAV hits every demo-script beat (scripted `/ws/demo` + `/notes`, times from connect): first reply 6.1 s (12.4 s and billing-appropriate after the fix-up), English subtitle 11.0 s, billing procedure on top 11.1 s, `•••• 4821` 35.4 s, escalation + pinned "Angry or escalating customer" 41.0 s and 46.0 s (cleared 50.5 s), `end` 67.3 s, `/notes` 2.0 s → billing 1.00 / medium 0.64 / follow-up 0.83. Same run in the browser under `pnpm tauri dev`: escalation frame saved as `docs/phase-6.png` (re-shot in the fix-up with the Billing chip), notes card after auto-end. `SUBMISSION.md` = draft answers for every Cerebral Valley field + social post drafts + video shot list. README has the hero screenshot, "What it does", measured timings, run/check commands.
- **QA checklist (Stretch):** `POST /qa {"transcript"}` → `{steps: [{label, done, quote}]}` in 1.9–2.9 s. Gemma quotes where the agent did each of 5 fixed steps (`QA_STEPS` in `server.py`) or null; `grounded()` only ticks a step if the quote's words are really in the transcript (yes/no without quotes ticked steps that never happened). The UI calls it after `/notes` (notes still 2.1 s, checklist ~3 s later): "QA 4/5" + clickable chips under the dropdowns (hover = quote), included in Copy to CRM. On the demo: identity, apology, refund timeline, SMS ✓; supervisor callback ✗ (correct). Screenshot: `docs/stretch-qa.png`.
- **Cluely-style UI pass (before Phase 7):** the panel is almost-clear glass, same CSS in browser and native: `rgba(20,20,24,.08)` wash + `backdrop-filter: blur(6px)` + a 3-layer dark text shadow. No `windowEffects`: every macOS vibrancy material tried (`hudWindow`, `popover`, ...) blurred the desktop into flat grey; without it, the transparent Tauri window's CSS `backdrop-filter` frosts the real desktop lightly, so shapes behind stay visible like Cluely. Checked readable natively over dark, light and a busy striped image. Screenshots: `docs/ui-cluely.png` (browser, mid-call + notes), `docs/ui-cluely-native.png` (native, idle).
- **Phase 7 (live model strip + real egress meter):** every model job runs inside `running(ws, step, ms, key)` in `server.py`: it takes the lock, sends `{"type":"busy","step":"whisper"|"gemma"|"laya"|"embed"}`, runs, records the time, sends `{"type":"busy","step":null}`. `finish()` sends `{"type":"timings","id","ms":{whisper,translate?,laya,kb,reply?}}` at the end of every chunk (also small talk / no speech). UI: pill row under the header (Whisper · Gemma · Laya · EmbedGemma), the running one coral and pulsing, each with its last time. `GET /egress` → `{engine_bytes_out, engine_remote_conns, mac_bytes_out}` (nettop on the engine's python + `uv` parent, loopback dropped; `netstat -ib` non-loopback interfaces), polled by the UI every 2 s; footer "This Mac: 1.1 MB out · Earshot: 0 B, 0 connections" (Mac = delta since the call started) + "● Online · PII masked on-device". Verified over 3 scripted runs: Earshot 0 B / 0 connections on every poll while the Mac moved +0.3–0.8 MB; every demo beat unchanged. Screenshot: `docs/phase-7.png`.
- **Overlay (Phase 0.5):** the window is a frameless, transparent, always-on-top 420x720 panel, visible on all Spaces, docked top-right of the work area with 24px margins on launch (`setup` in `lib.rs`), resizable. Header is the drag region. Stack: suggestion card (coral border) → live transcript (last 6 lines) → call notes (only once the call ends; the suggestion card then shrinks to 22%). Screenshot: `docs/phase-0.5.png`. **All later UI goes inside this panel.** `pnpm check` passes.
- Cmd+\ toggles show/hide (global shortcut registered in Rust). Registers without error; **not yet tested by an actual keypress** (synthetic keys were blocked here).
- **Not verified:** mic capture inside the Tauri webview (the permission prompt can't be accepted unattended). If `getUserMedia` fails, the transcript card says "Microphone unavailable… Use Demo call." Fallback if it fails for real: capture in the engine with `sounddevice`, same WS messages (PLAN Phase 1.1).

- **Demo video:** `docs/demo-video.mp4` (89.8 s, 1080p, 7 MB, call audio included). Made per brag's `/brag-slim` skill with headless Chrome (puppeteer-core from the npx cache + `/Applications/Google Chrome.app`) + ffmpeg: `docs/video/capture.cjs` records a real Demo call at localhost:1420 over the video's backdrop (so the glass frosts the same image) and logs beat times + element boxes; `docs/video/compose.html` + `render.cjs` draw title cards, captions, rings and zoom callouts frame by frame. To re-render (engine + Vite up): re-render: `NODE_PATH=<dir with puppeteer-core> node docs/video/capture.cjs <workdir>` (after `node docs/video/render.cjs <workdir> --backdrop`), then `node docs/video/render.cjs <workdir>` (`--stills 10,20` writes check frames). The footer reads "Online" (real `navigator.onLine`); the egress meter is the proof.

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
| `engine/server.py` | FastAPI app: `running`/`finish` (busy + timings messages), `/egress` + `parse_nettop`/`parse_netstat`, `handle_chunk` (transcript) + `enrich` (translation/signals/KB/reply), Laya `QUESTIONS`, `MOOD_HIGH`, `/ws/call` (mic), `/ws/demo` (demo WAV), `/demo/*` static, `/notes` + `NOTE_QUESTIONS`, `/qa` + `QA_STEPS` + `grounded`, global model lock. |
| `engine/demo/` | `call.wav` (64.3 s ElevenLabs demo call, `elevenlabs/build.sh`), `call-tts.wav` (old `say` placeholder) + `make_demo.sh` (its script; not byte-reproducible, see above). |
| `SUBMISSION.md` | Cerebral Valley form answers (with `TODO`s for team, repo URL, video link), X/LinkedIn post drafts, demo video shot list. |
| `docs/phase-*.png` | Screenshots per phase; `phase-6.png` is the README hero (escalation moment). |
| `engine/check_demo.py` | Scripted `/ws/demo` + `/notes` + `/qa` client; prints message timings, per-chunk model `timings` + pill order, polls `/egress` (asserts Earshot stays 0) and a `BEATS` summary (needs the engine running). |
| `engine/test_egress.py` | Assert check for `parse_nettop`/`parse_netstat` on saved samples (loopback dropped; no models). |
| `engine/test_chunking.py` | Assert check for `split_on_silence` (`uv run python test_chunking.py`, no models). |
| `engine/test_signals.py` | Assert check for the Phase 3 rules: `is_english`, reply gate `REQUEST`, KB `boosted`, plus `small_talk`/`vote` and the QA `grounded` check (no models). |
| `engine/test_masking.py` | Assert check for `mask`/`hold_tail`, using real Whisper output from the demo WAV (`uv run python test_masking.py`, no models). |
| `engine/kb/telco.md` | Sample KB; each `## ` section is one retrievable procedure. |
| `engine/fetch_models.sh` | ModelScope downloader (parallel byte ranges) for all 4 models. |
| `app/src/routes/+page.svelte` | The whole UI: mic capture (ScriptProcessor, 5 s chunks), demo-call playback, WS client, the Cluely-style dark glass overlay panel (reply card, signals strip, escalation banner, subtitles, editable notes + Copy to CRM), model pill strip, footer (live egress meter + Online/Offline dot), design tokens. |
| `app/src-tauri/src/lib.rs` | Spawns (`uv run --offline`)/kills the engine; docks + shows the overlay; registers Cmd+\. |
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
- Overlay: the window is transparent with no native vibrancy; the `.panel` fills the window (no inset, no CSS drop shadow) with a 16px radius. Native window shadow is off (`shadow:false`). Keep `body` background transparent. No `backdrop-filter` (it blinked natively, see Flicker below); in a browser test the look with a temporary `document.body.style.background` (then remove it).
- Drag: `data-tauri-drag-region` only works on the element itself, not its children, so the header's text/badge/spacer carry it too. It needs the `core:window:allow-start-dragging` capability (added).
- Don't add content protection (screen-capture hiding): the demo video must show the overlay.
- A stale `vite dev` on port 1420 (orphaned from an earlier session) makes `tauri dev` fail with "beforeDevCommand terminated". Check `lsof -nP -iTCP:1420 -sTCP:LISTEN` first.
- Only one engine can bind port 8765. Kill stray `uvicorn server:app` processes before `tauri dev`.
- Model jobs share one lock, so a long Gemma call delays the next transcript. See PLAN Phase 3 gating.
- Whisper is forced to `language="tl"` in `models.transcribe`: auto-detect turned an Indian-accent TTS chunk into Hindi script; forced Tagalog still writes English words fine. Quality on *real* Taglish speech is still unknown (only TTS so far). Ask the user for a real recording; it replaces `engine/demo/call.wav` (PLAN Phase 6).
- **Call intent (fix-up after Phase 6):** Laya calls greetings, closings and anything with the brand name `technical` (~0.95; criteria rewording didn't help). So `small_talk()` chunks (< 3 words, or "thank you for calling" / "how may I help" / "salamat sa pagtawag") don't vote and keep the previous procedures + reply, and `vote()` makes the call's intent the running best (summed confidence). On the demo: first reply is billing (12.4 s), billing stays on top to the end. Limits: a real call whose topic changes mid-call switches late; if the greeting chunk also holds the customer's first words, that chunk's intent is skipped (the next chunk catches it). Extend `SMALL_TALK` if the real recording's greeting/closing is worded differently.
- Escalation needs the smoothed mood ≥ 0.5 on 2 chunks in a row, so the banner lands ~5 s after the outburst. Tune `MOOD_HIGH` / the 2-chunk rule on the real recording, not the TTS one.
- `enrich` runs as an `asyncio` task; `/ws/demo` awaits the last one before sending `end`. The engine log prints per-stage timings per chunk (`chunk N: whisper … translate … laya+kb … reply …`).
- Whisper errors seen on the TTS demo: "Na charge ako ng Daloyang bes" (dalawang beses), "Bastard I text" (Basta i-text). The card number came out as `For 111.` + `2222-3333-4821` across two chunks ("four" → "For"); masking handles it via `hold_tail`, but digits spoken as words ("four one one one", Tagalog numbers) are **not** masked. Check the real recording's transcript in Phase 6 and extend `mask()` only if needed.
- Any new text that leaves the engine must go through `mask()` (translations, replies and notes already do; Gemma's input is the masked text).
- `hold_tail` delays digits at a chunk's end by one chunk (~5 s). On `/ws/call` (mic) a trailing held fragment is dropped if the call ends; on `/ws/demo` it's flushed on the last chunk.
- The egress footer is live (`/egress`, Phase 7). It only sees sockets of the engine's python process and its `uv run` parent (found via `ps` at import; when you run uvicorn by hand the parent is your shell and is skipped). If you ever spawn a helper subprocess from the engine, add its pid to `ENGINE_PIDS`. Loopback = `127.*`, `::1`, `*%lo0`. The Online/Offline part is live `navigator.onLine`.
- `busy` is sent after the lock is acquired, not before (deliberate: a queued step doesn't light its pill). Laya/EmbeddingGemma pills flash for only ~50 ms.
- Pill row is at the 420 px limit (scrollWidth 394 = clientWidth with four `x.xxs` times). The 4th pill says "EmbedGemma" (full "EmbeddingGemma" overflowed); don't add a 5th pill or longer labels.
- Flicker report (Phase 7): Miguel saw the native panel blink clear/translucent. `screencapture` bursts (idle + during a call with pills pulsing) showed no change frame to frame; it matched dev restarts (window re-created) and Vite HMR reloads. The pulse now animates `opacity` only. If it comes back with nothing being edited, capture a burst (`screencapture -x -R <window rect>` every 0.3 s) and compare frames. **It came back (Oct 10) → `backdrop-filter` removed:** a 40-frame burst didn't catch a blink, so the cause is the likely one: the full-window blur in the transparent NSWindow gets re-rasterized when the DOM updates (2 s egress poll, pills, transcript) and briefly drops; the panel is now static paint only (wash + text halo), so it cannot blink. Light mode (`prefers-color-scheme: light`, window `theme` unset = follows macOS) uses a light frost + dark ink; both looks stay readable over light and dark content (`docs/ui-light-dark.png`: top before, bottom after; columns light-scheme/light-bg, light/dark-bg, dark/light-bg, dark/dark-bg). Native burst after the fix: 70 frames, identical with the egress meter ticking.
- `pnpm tauri dev` got killed from outside twice during Phase 7 (no exit line in its log; the engine stayed up orphaned on 8765, PPID 1). If the window vanishes: `pgrep -fl "uvicorn|earshot|vite|tauri dev"`, kill leftovers, relaunch.
- To see the Offline state without touching system settings (screenshots, UI work): in the page, `Object.defineProperty(navigator, "onLine", {get: () => false, configurable: true}); dispatchEvent(new Event("offline"))`. Never toggle Wi-Fi yourself; the user does that on stage.
- `uv run --offline` (in `lib.rs`) fails fast if a package isn't in the uv cache instead of hanging on the network. If you add a Python dependency, run `uv sync` (online) once so the offline launch keeps working.
- `lsof -i` on the engine shows its client connections as `127.0.0.1:8765->127.0.0.1:<port>`; anything else would be a leak. Re-run the sampler after any engine change that adds a library.
- The built-in browser's screenshots save as JPEG under `~/.claude/projects/.../tool-results/`; convert with `sips -s format png <file> --out docs/phase-N.png`.
- `tauri dev` binary is `app/src-tauri/target/debug/earshot`; killing `tauri dev` can leave it running. Check `pgrep -fl target/debug/earshot`.
- `pkill -f "tauri dev"` leaves its `vite dev` child listening on 1420; kill it too (`lsof -nP -iTCP:1420 -sTCP:LISTEN`).
- At 420px the idle header (badge + "Demo call" + "Start call") is tight: header buttons use 12px side padding and a 6px gap to fit. Don't add header items without re-checking `scrollWidth`.
- Clipboard: `navigator.clipboard.writeText` is denied in the built-in browser pane ("Write permission denied"). "Copy to CRM" uses a synchronous `document.execCommand("copy")` inside the click first (works there, and WKWebView supports it), then `navigator.clipboard`. Not yet clicked inside the native Tauri window; check once by hand (`pbpaste`).
- Laya option *labels* matter: disposition confidence went 0.50 → 0.82 just by renaming "follow-up needed" to "follow-up". Priority sits at ~0.53 (medium vs high). Fields are dropdowns, so a wrong pick is one click to fix; re-check on the real recording.
- Gemma is deterministic here (same transcript → same notes), so repeated `/notes` calls don't show variance.
- Vite HMR resets the page state (a finished demo call disappears) when `+page.svelte` changes; re-run the demo after edits.
- The built-in browser's screenshot can be taken before Svelte re-renders after a click; re-check text with `javascript_tool`/`find` before concluding a click failed.
- The engine closes `/ws/demo` without a close frame after `end`; a Python `websockets` client raises `ConnectionClosedError` (harmless, the UI closes on `end`).
- Demo beats are sensitive to the audio: regenerating the TTS WAV with today's `say` changed Whisper's text from 6 s on and fired escalation at 21 s on the agent's line ("May I have your account number?", smoothed mood 0.55 because the customer's "na-charge ako ng dalawang beses" scored P(angry) 0.96). Any new `call.wav` needs the scripted check below before the demo.
- The "Say this" reply sometimes repeats the masked tail ("card for account ending in 4821"): that's the masked form, not a leak.
- QA checklist: `/qa` must run *after* `/notes` (both take the one lock; fired together, `/qa` can win and delay the notes). The step list is fixed in `QA_STEPS`; edit it there (label, what Gemma looks for). Re-check on the real recording: if Whisper garbles the agent's lines badly, `grounded()` (≥60% of quote words in the transcript) may untick a step Gemma found.
- Scripted demo check: `cd engine && uv run --offline python check_demo.py` while the engine is up. Prints each WS message with its time, asserts no raw card digits, POSTs `/notes`, and ends with a `BEATS` line (first time each beat fired).

## Status at stop
Build stopped Sat Oct 10, ~02:00. Code freeze **10:00 AM today**, no extensions.

**Done (all committed on `main`, not pushed; no remote yet):**
- 0.5 floating overlay · 1 demo-call mode + silence chunking · 2 live PII masking · 3 subtitles, Laya intent/mood, escalation, gated reply · 4 editable notes + Copy to CRM · 5 Online/Offline + offline flags + lsof locality check · 6 demo WAV, README, `SUBMISSION.md` drafts · 7 live model strip + real egress meter · 8 (slim) CVV/OTP/PIN alert + masking.
- 10 reply in the customer's language · 11 ElevenLabs demo voices swapped into `engine/demo/call.wav`.
- Fix-up (sticky call intent, small talk doesn't vote) · Stretch QA checklist (`/qa`, grounded quotes) · UI Cluely glass passes (dark glass + icons, translucent overlay, lighter native glass).
- Demo rehearsal (notes fit after the call, clean reset between runs, stricter supervisor-callback QA) · demo video `docs/demo-video.mp4` (89.8 s, 1080p, call audio).

**Not done:** Phase 9 (mood timeline), skipped on Miguel's "don't polish" call · Phase 8 live QA (skipped; only the CVV alert + masking shipped) · remaining Stretch: screenshot KB, speaker labels.

**Verified** (latest rehearsal + video capture, seconds from the Demo call click; `check_demo.py` agrees): subtitle ~6 s · billing procedure ~11 s · Taglish "Say this" ~12 s · CVV alert + `•••` ~30 s · `•••• 4821` ~40 s · escalation ~46 s (none before) · cleared ~61 s · end ~65 s · notes +2 s · QA chips +2.5 s · Earshot egress 0 B / 0 connections throughout. A second click resets cleanly; nothing overflows 420 px. All assert checks (`test_*.py`) and `pnpm check` pass.

**Not verified / risky:**
- Nobody has watched it in the **native window** since the last changes (screen was locked; rehearsal and video ran in the browser at localhost:1420). Possible glass blink/flicker (see Gotchas) and readability over Miguel's wallpaper are unchecked.
- Untested by hand: Cmd+\ toggle, mic permission prompt on Start call, Copy to CRM in the native window (`pbpaste`), the Wi-Fi-off rehearsal.
- Plus the open items in Gotchas: Whisper on real (non-TTS) Taglish, digits spoken as words aren't masked, priority confidence ~0.5, `tauri dev` occasionally killed from outside (relaunch steps there), native-window frames `docs/demo-beat-*.png` never captured.

**Miguel: demo steps**
```bash
pgrep -fl "uvicorn|earshot|vite|tauri"      # kill anything listed (stale engine/vite blocks launch)
lsof -nP -iTCP:1420 -sTCP:LISTEN; lsof -nP -iTCP:8765 -sTCP:LISTEN   # both should be empty
cd ~/Documents/GitHub/"AppBuilders Hackathon"/app && pnpm tauri dev
```
1. Panel docks top-right; wait ~25 s for the badge "On-device · offline". Volume up (call audio plays).
2. Click **Demo call** and point at: ~6 s English subtitle under the Taglish line · ~11 s "Billing dispute" procedure + Billing chip · ~12 s "Say this" in Taglish · ~30 s red CVV banner, CVV shown as `•••` · ~40 s card as `•••• 4821` · ~46 s escalation banner + de-escalation script after "Gusto ko makausap ang supervisor" · ~61 s clears · ~65 s call ends → notes (Billing / Medium / Follow-up, summary, Copy to CRM), QA chips right after (CVV ask and supervisor callback correctly missed). Footer: "Earshot: 0 B, 0 connections" the whole time.
3. **Wi-Fi off:** turn Wi-Fi off in the menu bar → footer dot says **Offline** → click **Demo call** again: same beats. "Zero bytes left this laptop."

**Miguel: to-do before 10:00 AM**
1. Watch one native run end to end (blink? readable? press Cmd+\ twice; Copy to CRM then `pbpaste`). Do the Wi-Fi-off run once.
2. Upload `docs/demo-video.mp4` (YouTube/LinkedIn/X; you need a link for the form).
3. Social post from the drafts in `SUBMISSION.md`.
4. Create the public repo and push main only: `gh repo create earshot --public --source . --remote origin --push` (leave branch `bantai` alone).
5. Fill the `TODO`s in `SUBMISSION.md` (team, repo URL, video link) and submit on Cerebral Valley.

Optional, only with time to re-check: real recording → `ffmpeg -i ~/Desktop/call.m4a -ac 1 -ar 16000 -sample_fmt s16 engine/demo/call.wav`, then `cd engine && uv run --offline python check_demo.py` and read `BEATS` (re-tune `mask()`, `MOOD_HIGH`, `SMALL_TALK`, `NOTE_QUESTIONS` if beats move).

**Agents:** no more feature work before the freeze. Before any change `check_demo.py` must hit every beat, and again after. Commit only; never push or create the remote without Miguel.
