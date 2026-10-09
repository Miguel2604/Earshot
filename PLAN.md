# Earshot: implementation plan

**Deadline: 10:00 AM Sat Oct 10, 2026. Code freezes then; the repo must be public.** Demo Day is in person at Cyberzone, SM Makati, on a MacBook (M5, 24 GB). There is no Windows build.

## Product in one line
A desktop copilot for Filipino BPO agents: live call transcript → live mood + intent → matching knowledge-base procedure → drafted reply → masked after-call notes, all on-device.

## Judging (what we optimize for)
| Weight | Criterion | How Earshot scores |
|---|---|---|
| 25% | Problem & usefulness | Clear user (BPO agents, a huge PH workforce); after-call work, KB lookup and angry callers are daily pain. |
| 25% | Local AI implementation | Cloud AI is *not allowed* on customer data in most centers. Remove the local models and the product is gone. Show it working with Wi-Fi off. Four local models, each with one job. |
| 20% | Technical execution | Fast decisions every chunk (Laya, ms), slow generation only when needed (Gemma, seconds). The demo must not fail: always have the demo-call path. |
| 15% | Innovation | Taglish-aware, privacy-first, live PII masking, a mood meter that drives the UI. |
| 15% | Product & demo | One screen, obvious value in 60–90 seconds. |

## Architecture
```
Tauri window (SvelteKit)                 engine/ (Python, 127.0.0.1:8765)
  mic or demo WAV -> 16 kHz float32, 5 s chunks ──WS──> Whisper large-v3-turbo (mlx-whisper)   ~0.8 s
                                                          │ transcript (PII-masked before it leaves the engine)
                                                          ├─> Gemma 4 E4B: Taglish → English subtitle  ~0.5–1.4 s, every chunk
                                                          ├─> Laya multilingual on the ENGLISH text  ~30–250 ms, every chunk
                                                          │     intent (choice), mood (score)
                                                          ├─> EmbeddingGemma 2 search over kb/*.md  ~20 ms, boosted by intent
                                                          └─> Gemma 4 E4B (mlx-vlm)  3–7 s, only when gated (see Phase 3)
  transcript, mood, intent, suggestions, reply  <── WS messages
  "End call" ─────────────POST /notes──────────> Laya: category/priority/disposition (fixed options)
                                                 + Gemma: summary + follow-up (free text)
```
- Tauri (`app/src-tauri/src/lib.rs`) spawns the engine with `uv run uvicorn` and kills it on exit.
- Models live in `~/models`. `engine/fetch_models.sh` downloads from ModelScope. **Do not download from Hugging Face** (it's ~26 KB/s from this network). The engine sets `HF_HUB_OFFLINE=1`.
- One global `asyncio.Lock` serializes model jobs (`engine/server.py`). Laya is fast enough to share it.
- **Decided:** Laya runs on the official PyTorch package on the Mac GPU, *not* the community MLX port (its weights are only on Hugging Face). Ticket routing is **out of scope**.

## Measured on the demo Mac
| Step | Time |
|---|---|
| Whisper, 8 s clip | 0.8–0.9 s |
| EmbeddingGemma 2 search | ~20 ms warm (pre-warmed at startup) |
| Laya multilingual, 3 questions | ~30–250 ms warm (first call ~1.4 s, pre-warmed) |
| Gemma 4 E4B, reply + JSON notes | 3.7–7 s at ~34 tok/s |
| Gemma 4 E4B, translate one chunk to English | 0.4–0.8 s warm (clean output) |

**Translator choice: Gemma 4 E4B, tested against MiniCPM5 2B (MLX 8-bit) on the same 6 Taglish lines.** MiniCPM5 was a bit faster (0.3–0.66 s) but got the meaning wrong on 5/6: "kahapon" → "the last time", "ngayong buwan" → "new year", "ayos na po" → "let's go", "lilipat kami ng bahay" → "we have a problem with our house". Gemma got all 6 right and even repaired a garbled Whisper line. Keep Gemma; don't add MiniCPM5 (weights are in `~/models/minicpm5-2b-8bit` but unused).
| All models load at startup | ~25 s |

### Laya zero-shot on Taglish (6 test lines, read this before building on it)
| Question type | Result | Use it for |
|---|---|---|
| `choice` (intent) | 3/5 right: technical, billing and cancel were correct; "salamat, ayos na" and "lilipat kami ng bahay" both came out `technical`. Possibly biased toward the first option. | Intent chip + KB boost. Tune option wording, try reordering, keep only 4–5 options. |
| `score` (mood, 4 levels) | Directional: angry billing line highest (1.72), "salamat, ayos na" lowest (0.81), but a calm relocation line (1.33) beat an annoyed tech line (1.25). | Mood meter, **smoothed over the last 3 chunks** and relative to the call's start, not absolute thresholds. |
| `noul` (yes/no) | **Unusable:** every line scored 0.00–0.09, including angry and question lines. | Nothing. Don't gate on Laya yes/no. |

**Same lines translated to English** (the reason for Phase 3's subtitles): intent 3/6 → **4/6** ("salamat, ayos na" → `closing`), mood separates better (calm 0.37 vs angry 1.72, was 0.81 vs 1.72), yes/no still broken. Small sample; the gain is modest, but the subtitle is a visible feature anyway.

Laya's own docs show zero-shot accuracy is modest (0.362 base vs 0.766 fine-tuned on their benchmark). Fine-tuning tonight is out of scope. **Fallback if mood stays flat on real voices:** EmbeddingGemma 2 against ~5 labeled Taglish examples per mood level (~20 ms, no new model).

## Status
### Phase 0: scaffold ✅ done
- Tauri 2 + SvelteKit app, engine auto-start, 3-panel UI with `DESIGN.md` tokens.
- Engine: `/health`, `/ws/call` (transcript + top-3 KB hits), `/notes` (JSON notes). Verified end to end with a test clip.
- `models.decide(text, questions)` wraps Laya (loaded + warmed at startup, not yet called from the pipeline).
- Sample KB: `engine/kb/telco.md` (fictional PH fiber ISP, 8 procedures).

### Phase 0.5: Cluely-style overlay ✅ done
- **Verified:** `pnpm check` (0 errors), `cargo build`, `pnpm tauri dev` starts cleanly and its engine answers `/health` → `{"ok":true,"kb_docs":8}`. Native window confirmed via `screencapture`: frameless, transparent, rounded glass panel docked top-right, on top of other apps. Browser render at `localhost:1420` saved to `docs/phase-0.5.png`. **Not verified:** the Cmd+\ toggle by keypress (no accessibility permission for synthetic keys here); the shortcut registers without error. Press it once by hand.
- Spec:
- Turn the Tauri window into a floating overlay instead of a normal app window: transparent, no title bar/decorations, always on top, visible on all workspaces/Spaces, about 420x720, docked top-right of the screen on launch (24px margins), resizable. macOS transparency needs `app.macOSPrivateApi: true` in tauri.conf.json plus the `macos-private-api` feature on the `tauri` crate.
- Global shortcut Cmd+\ toggles show/hide (tauri-plugin-global-shortcut, registered in Rust).
- Layout becomes one vertical glass panel: rounded 16px, white at ~92% opacity with backdrop blur, hairline border, soft shadow; the header bar is the drag region (data-tauri-drag-region) with the status badge and Start/End call button. Stack below it, top to bottom: suggestion/reply card (most important, always visible), live transcript (last few lines, scrolling), call notes (after the call ends). Keep DESIGN.md (Airtable) tokens; body background transparent.
- Do NOT hide the window from screen capture (no content protection): the demo video must show it.
- All later phases build their UI inside this overlay.

### Phase 1: reliable audio in ✅ done (mic in the Tauri webview not verified)
- **Built:** `WS /ws/demo` streams `engine/demo/call.wav` through the same pipeline as `/ws/call` at real-time pace, then sends `{"type":"end"}`; `GET /demo/call.wav` serves the audio; header "Demo call" button plays it and auto-ends the call (notes appear). Chunks are cut at the quietest 0.1 s of each chunk's last second (`split_on_silence`, remainder carried into the next chunk; check: `engine/test_chunking.py`). Whisper is forced to `language="tl"` (auto-detect output Hindi script on a TTS chunk). Mic path now shows "Microphone unavailable… Use Demo call." if `getUserMedia` fails.
- **Placeholder demo audio:** `engine/demo/make_demo.sh` (macOS `say` Samantha + Rishi, ffmpeg → 16 kHz mono) makes a 59 s Taglish double-charge call. Replace with the real recording in Phase 6.
- **Verified:** `pnpm check` 0 errors, `cargo build`, `/health` (engine startup ~13 s warm cache), `test_chunking.py` ok. Scripted WS client: `/ws/call` transcript ~0.7 s per 5 s chunk; `/ws/demo` 12 transcripts, each ~0.4–0.5 s after its audio ends, suggestions ~0.1 s later, `end` at 59.9 s for a 59.4 s file; "Billing dispute or double charge" top hit on 9/12 chunks. In the browser at `localhost:1420` under `pnpm tauri dev`: Demo call → transcript + procedures stream in, call auto-ends, notes generated (issue/resolution/disposition/follow_up correct). Screenshot `docs/phase-1.png`.
- **Not verified:** mic capture inside the Tauri webview (no way to grant the mic permission prompt unattended). The demo path doesn't depend on it.
- Spec:
1. Verify mic capture inside the Tauri window (`pnpm tauri dev`). The mic permission string is in `app/src-tauri/Info.plist`. If `getUserMedia` fails in the webview, move capture into the engine (`sounddevice`) and keep the same WS messages.
2. **Demo-call mode** (top priority): an engine endpoint that streams a WAV from `engine/demo/` in 5 s chunks through the same pipeline at real-time pace, plus a "Play demo call" button. This is what we show on stage.
3. Chunking: add ~0.5 s overlap, or cut on silence, so words aren't split. Keep it simple.

### Phase 2: live PII masking ✅ done
- **Built:** `mask()` in `engine/server.py` runs on every transcript before it leaves the engine (so the UI, KB search and `/notes` only ever see masked text). One rule covers cards, PH mobiles and account numbers: any run of 7+ digits, allowing spaces/dots/dashes between groups (`4111 2222-3333.4821`, `0917 123 4567`, `+63 917-123-4567`), becomes `•••• 4821`; emails become `••••@domain`. Amounts/times (`1,299`, `5 to 7`, `10:30`) stay. **Split numbers:** `hold_tail()` holds digits at the very end of a chunk's text and prepends them to the next chunk, so Whisper's real output `For 111.` | `2222-3333-4821 …` is masked as one number. Held digits are flushed on the demo's last chunk. Check: `engine/test_masking.py`. Panel footer: "0 bytes sent to cloud · PII masked on-device" (static: the engine makes no network calls). The transcript card now auto-scrolls to the newest line.
- **Verified:** `test_masking.py` + `test_chunking.py` ok, `pnpm check` 0 errors, `cargo build`, engine startup ~15 s, `/health` ok. Scripted `/ws/demo` client: 12 transcripts, the card arrives as `•••• 4821 Ibalik ni Iona young perico` at 35.4 s (~0.4 s after its audio), no raw card digits in any message; the preceding line ends `…card ko. For` (the `111` is held back). In the browser at `localhost:1420` under `pnpm tauri dev`: Demo call → masked line + footer visible, call auto-ends, notes generated from the masked transcript. Screenshot `docs/phase-2.png`.
- **Not handled (by choice):** numbers Whisper writes as words ("four one one one", Tagalog "isa, dalawa"); the demo WAV's digits come out as numerals. Revisit with the real recording in Phase 6.
- Spec:
- Regex mask in the engine *before* any text is sent to the UI or stored: PH mobile numbers (`09xx`/`+639xx`), card numbers (13–19 digits, Luhn optional), account numbers, emails. Show `•••• 4821`.
- Header counter: "0 bytes sent to cloud".

### Phase 3: live English subtitles, Laya live signals, gated reply ✅ done
- **Built:** `handle_chunk` sends the transcript, then an `enrich` background job per chunk does translation → Laya → KB → reply under the one lock (FIFO, so the next chunk's Whisper call goes ahead of any queued step of the previous chunk; translation/reply are skipped if a newer chunk has arrived). Messages: `translation` (masked Gemma subtitle, skipped when no common Tagalog word is present), `signals` (`intent`, `intent_p`, `mood` smoothed over 3 chunks, `mood_raw`, `escalate`), `suggestions` (+0.05 for titles matching the intent; escalation pins "Angry or escalating customer" on top), `reply` (masked Gemma "say this", gated on `?`/request words/intent change/escalation). Each message carries the chunk `id`. UI: "Say this" reply at the top of the coral card, then procedures; intent chip + mood meter under it; escalation banner with "Flag supervisor" (local toggle); muted italic English subtitle under each line. Idle header tightened to fit 420px. Check: `engine/test_signals.py`.
- **Mood change:** the 4-level `score` question was flat on the demo (greeting 1.11 = "give me back my money" 1.11). A 2-way `choice` (polite vs angry, criteria with descriptions) and P(angry) separates: greeting 0.01, angry lines 0.88–0.92, calm lines ≤0.24. Escalate when the 3-chunk mean ≥ 0.5 for 2 chunks in a row. EmbeddingGemma fallback was tried and is useless (similarities 0.85–0.98 for everything); not used.
- **Verified:** `pnpm check` 0 errors, `cargo build`, `/health` ok (~15 s startup), `test_signals.py`/`test_masking.py`/`test_chunking.py` ok. Scripted `/ws/demo` client (12 chunks, 59 s file, `end` at 60.4 s): no raw card digits in any text field; card line `•••• 4821 …` at 35.4 s. Escalation fires on chunks 8–9 (40.9 s, 45.5 s), right after the outburst (chunk 7, raw P(angry) 0.98) and clears at chunk 10 once the agent resolves it. Browser at `localhost:1420` under `pnpm tauri dev`, 420px wide: reply card, pinned de-escalation script, intent chip, mood meter, escalation banner and subtitles all visible; notes still generated at the end. Screenshot `docs/phase-3.png`.
- **Measured per chunk (warm):** Whisper 0.40–0.43 s, translation 0.39–0.79 s, Laya + KB 0.06–0.14 s, reply 0.68–1.17 s (10/12 chunks gated in). Worst chunk total ≈ 2.5 s of a 5 s budget; every transcript arrives ~0.4 s after its audio, every reply ≤ 1.5 s after its transcript. **Keeps up with real time** with ~2.5 s headroom; no job was ever dropped as stale on the demo.
- **Known weak spots (TTS placeholder audio):** Laya intent is noisy (greeting and "thank you for calling" → `technical` 0.93–0.97, so the last chunk ranks "Slow internet" first and the first reply asks about modem lights); garbled Whisper lines translate to nonsense ("Why aren't you still awake?"). Re-check with the real recording (Phase 6) before tuning.
- Spec:
- **Subtitles:** right after Whisper, Gemma translates the (masked) chunk to English: prompt `Translate to natural English. Output only the translation.`, `max_tokens≈60`. Send `{"type":"translation","text":...}` and show it as a muted line under each Taglish line. Skip the call if the chunk is already English (cheap check: Whisper's detected language, or no common Tagalog words). Pitch it as "foreign clients' QA teams can read local-language calls."
- On the **English** text, call `models.decide` with **intent** (`choice`) and **mood** (`score`). Send `{"type":"signals","intent":...,"intent_p":...,"mood":...}`.
- Priority under the single lock: transcript → translation → Laya → reply. If a newer chunk is waiting, drop stale translation/reply jobs, never the transcript.
- UI: intent chip ("Billing · 0.92") and a **mood meter** (smoothed). When mood stays high for 2 chunks → escalation banner + pin the "Angry or escalating customer" procedure + "Flag supervisor" button.
- KB boost: add a small bonus to procedures whose section title matches the intent.
- **Gemma "say this" reply, gated by plain rules** (Laya yes/no is unusable): run only if the chunk contains `?` or a request word (`paki`, `pwede`, `bakit`, `paano`, `can you`, `please`), or the intent changed, and drop the job if a newer chunk is already waiting. 1–2 sentences, Taglish OK, grounded in the top KB hit + last 3 lines, `max_tokens≈80`. Send `{"type":"reply"}`.

### Phase 4: notes polish ✅ done
- **Built:** `POST /notes` (in `engine/server.py`): Gemma writes only `summary` + `follow_up` (JSON, 160 tokens, told to use only facts in the transcript and not invent names/amounts/dates/numbers), both passed through `mask()`; then Laya answers `NOTE_QUESTIONS` on that English summary + follow-up: **category** (billing/technical/cancellation/relocation/other), **priority** (low/medium/high), **disposition** (resolved/follow-up/escalated/unresolved). Response: `{category|priority|disposition: {value, confidence, options}, summary, follow_up}`. Malformed Gemma JSON falls back to the raw text as the summary. UI: notes card shows three dropdowns (Laya's pick + confidence), two editable textareas, and a full-width "Copy to CRM" button that copies plain text (`Category: …\nPriority: …\nDisposition: …\nSummary: …\nFollow-up: …`, including edits). Once notes exist the suggestion card shrinks to 22% so the notes get the space.
- **Clipboard:** `navigator.clipboard.writeText` is denied in the built-in browser pane, so the copy uses a synchronous `document.execCommand("copy")` inside the click (no permission needed; WKWebView supports it) with `navigator.clipboard` as fallback. No Tauri plugin added.
- **Verified:** `pnpm check` 0 errors, `cargo build`, `/health` ok, `test_masking.py`/`test_signals.py`/`test_chunking.py` ok. Scripted: `/ws/demo` → 12 masked lines → `POST /notes`: category billing 1.00, priority medium 0.53, disposition follow-up 0.82; summary "double charge on their bill… processed a refund… credited within five to seven banking days", follow-up "SMS confirmation once the refund is processed": every fact is in the transcript, no names/amounts invented, no digits at all in the output. Browser at `localhost:1420` under `pnpm tauri dev` (420px): Demo call → call auto-ends → notes card; changed priority to High and edited follow-up, clicked "Copy to CRM" → button reads "Copied to clipboard" and `pbpaste` shows the edited notes. Screenshot `docs/phase-4.png`.
- **Measured:** `/notes` 2.0–2.1 s warm (3.4 s on the first call after startup); Laya part ~0.1 s.
- **Weak spots:** priority confidence is low (0.53, medium vs high); disposition was 0.50 while the option was named "follow-up needed" and 0.82 after renaming it "follow-up" (also fits the 420px dropdown), so option wording matters. They're dropdowns, so the agent corrects them. Copy not tested by a click inside the native Tauri window (only the browser pane).
- Spec:
- `/notes`: Laya picks **category, priority, disposition** from fixed lists (dropdown-safe values with confidence); Gemma writes only the summary and follow-up, and is told not to invent facts.
- Editable fields, "Copy to CRM" (clipboard, formatted). Notes use the masked transcript.

### Phase 5: prove "local" ✅ done (Wi-Fi-off run is the user's, by hand)
- **Built:** footer now reads "● Online/Offline · 0 bytes sent to cloud" + "PII masked on-device" (`<svelte:window bind:online>` = `navigator.onLine`, updates on the `online`/`offline` events; green dot when offline). Engine sets `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY` (in `models.py`, before any HF library is imported). Tauri launches the engine with `uv run --offline`, so uv never tries to resolve packages over the network. README "What runs locally / what needs internet" updated.
- **Verified (no system settings touched):** `pnpm check` 0 errors, `cargo build`, the three `test_*.py` ok, engine starts with all offline flags set (`uv run --offline`, `/health` ok in 13 s). Locality: `lsof -nP -i -a -p <pid>` sampled every 0.5 s over the uv + Python engine processes from launch through model loading, a full `/ws/demo` run and `POST /notes` (2 runs, ~215 samples each): the only sockets were `127.0.0.1:8765` LISTEN and `127.0.0.1:8765<->127.0.0.1` client connections; no other TCP/UDP socket ever. Browser pane network log: every request went to `localhost:1420` or `127.0.0.1:8765`. Demo run: 12 masked lines, `end` at 60.4 s, no raw card digits in any text field, notes billing 1.00 / medium 0.53 / follow-up 0.82 in 2.0–2.1 s. Browser at `localhost:1420` under `pnpm tauri dev` (420 px): footer fits (scrollWidth 378 = clientWidth), Demo call → notes; `offline` emulated in-page (overriding `navigator.onLine` + dispatching the event) → "Offline · 0 bytes sent to cloud" with green dot, `online` → back to "Online". Screenshot `docs/phase-5.png`.
- **Measured:** engine startup 13 s (warm cache); per chunk whisper 0.41–0.49 s, translate 0.54–0.62 s, Laya+KB 0.06–0.08 s, reply ~0.7 s; `/notes` 2.0–2.1 s.
- **Wi-Fi-off rehearsal (user, by hand, before Demo Day):**
  1. Quit everything. Turn Wi-Fi off (and unplug Ethernet / turn off iPhone hotspot).
  2. `cd app && pnpm tauri dev`. Expect the panel within ~1 min and the badge to go from "Loading models…" to "On-device · offline" (~15–25 s). Footer shows a green dot + "Offline".
  3. Click **Demo call**: transcript + subtitles stream, `•••• 4821` appears ~35 s, mood meter climbs, escalation banner, "Say this" reply, call auto-ends ~60 s, notes appear (Billing / Medium / Follow-up).
  4. Edit a field, click **Copy to CRM**, paste somewhere (`pbpaste`).
  5. Optional proof for the video: in another terminal `lsof -nP -i -a -p $(lsof -tnP -iTCP:8765 -sTCP:LISTEN)` shows only `127.0.0.1` sockets.
  6. Turn Wi-Fi back on: footer flips to "Online" (grey dot).
  If step 2 fails offline: run `cd engine && uv run --offline uvicorn server:app --port 8765` alone to see the error; most likely a missing package in the uv cache (fix with Wi-Fi on: `uv sync`).
- Spec:
- Network indicator (`navigator.onLine`) next to the "0 bytes" counter. Rehearse the full demo with Wi-Fi off.
- Keep README's "What runs locally / what requires internet" accurate.

### Phase 6: demo assets + submission (start by 7:00 AM at the latest)
- Record a 60–90 s mock Taglish call with 2 people that escalates: e.g. a double charge, the customer gets angry and reads out a card number, the agent calms them. Save as 16 kHz mono WAV in `engine/demo/`. This one recording exercises masking, mood meter, escalation, KB, reply and notes.
- Demo video (~1 min), post on X or LinkedIn, tag Devin / Cognition, include #AppBuildersPH.
- Submit on the Cerebral Valley page: project name, short description, team, GitHub repo (public!), hardware (MacBook M5 24 GB), demo video, screenshots, what runs locally / what needs internet, models, frameworks, APIs (none), existing code (none; scaffolded tonight), AI dev tools (Claude Code), and **"Why does this product benefit from running AI locally?"**

### Stretch (only if Phases 1–6 are done)
- **QA checklist** that ticks itself (verify identity, offer retention promo, confirm via SMS). Laya yes/no can't do it zero-shot; use Gemma at end of call, or EmbeddingGemma against step descriptions.
- **Screenshot KB:** load the full EmbeddingGemma 2 (vision) and index procedure screenshots directly.
- Speaker labels (agent vs customer) only via two audio inputs, no diarization models.

## Demo script (90 s)
1. "Play demo call": the Taglish transcript streams in with English subtitles underneath; the right procedure appears as the customer explains.
2. Customer reads out a card number, which shows as `•••• 4821`.
3. Customer gets angry: the mood meter climbs and the escalation banner appears with the de-escalation script.
4. Agent asks; the "say this" reply card suggests what to say.
5. End call: notes appear (category/priority/disposition + summary), all masked.
6. Turn Wi-Fi off and replay: it still works. "Zero bytes left this laptop."

## Known risks
- **Whisper on real Taglish** is untested: the only test clip is an English TTS voice reading Taglish (garbled words, though KB search still ranked the right procedure first at 0.73). Test with a real voice early. Levers: `initial_prompt` with domain words; `~/models/whisper-small-tagalog` exists but is transformers-format (needs MLX conversion; probably not worth it tonight).
- **Laya on Taglish** is weak zero-shot (see table above). Build the UI so a wrong intent is harmless (it's a hint, not an action).
- Mic permission in `tauri dev` on macOS (Phase 1.1).
- Lock contention: per chunk ≈ Whisper 0.8 s + translation ~1 s + Laya 0.25 s ≈ 2.5 s of a 5 s budget, leaving little room for the 3–7 s reply. Gating + dropping stale jobs is the mitigation; a smaller translator model is the next lever.
- Python is pinned to 3.12 (MLX wheels). Don't add `sentence-transformers[audio]` (conflicts with mlx-vlm). `torchvision` is required by EmbeddingGemma 2's processor.

## Out of scope
Ticket routing, Windows build, installer/sidecar bundling, real telephony (WASAPI loopback), CRM API integrations, fine-tuning.
