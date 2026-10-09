# Kasama: implementation plan

**Deadline: 10:00 AM Sat Oct 10, 2026. Code freezes then; the repo must be public.** Demo Day is in person at Cyberzone, SM Makati, on a MacBook (M5, 24 GB). There is no Windows build.

## Product in one line
A desktop copilot for Filipino BPO agents: live call transcript → live mood + intent → matching knowledge-base procedure → drafted reply → masked after-call notes, all on-device.

## Judging (what we optimize for)
| Weight | Criterion | How Kasama scores |
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

### Phase 1: reliable audio in (do first)
1. Verify mic capture inside the Tauri window (`pnpm tauri dev`). The mic permission string is in `app/src-tauri/Info.plist`. If `getUserMedia` fails in the webview, move capture into the engine (`sounddevice`) and keep the same WS messages.
2. **Demo-call mode** (top priority): an engine endpoint that streams a WAV from `engine/demo/` in 5 s chunks through the same pipeline at real-time pace, plus a "Play demo call" button. This is what we show on stage.
3. Chunking: add ~0.5 s overlap, or cut on silence, so words aren't split. Keep it simple.

### Phase 2: live PII masking (cheap, high oomph)
- Regex mask in the engine *before* any text is sent to the UI or stored: PH mobile numbers (`09xx`/`+639xx`), card numbers (13–19 digits, Luhn optional), account numbers, emails. Show `•••• 4821`.
- Header counter: "0 bytes sent to cloud".

### Phase 3: live English subtitles, Laya live signals, gated reply
- **Subtitles:** right after Whisper, Gemma translates the (masked) chunk to English: prompt `Translate to natural English. Output only the translation.`, `max_tokens≈60`. Send `{"type":"translation","text":...}` and show it as a muted line under each Taglish line. Skip the call if the chunk is already English (cheap check: Whisper's detected language, or no common Tagalog words). Pitch it as "foreign clients' QA teams can read local-language calls."
- On the **English** text, call `models.decide` with **intent** (`choice`) and **mood** (`score`). Send `{"type":"signals","intent":...,"intent_p":...,"mood":...}`.
- Priority under the single lock: transcript → translation → Laya → reply. If a newer chunk is waiting, drop stale translation/reply jobs, never the transcript.
- UI: intent chip ("Billing · 0.92") and a **mood meter** (smoothed). When mood stays high for 2 chunks → escalation banner + pin the "Angry or escalating customer" procedure + "Flag supervisor" button.
- KB boost: add a small bonus to procedures whose section title matches the intent.
- **Gemma "say this" reply, gated by plain rules** (Laya yes/no is unusable): run only if the chunk contains `?` or a request word (`paki`, `pwede`, `bakit`, `paano`, `can you`, `please`), or the intent changed, and drop the job if a newer chunk is already waiting. 1–2 sentences, Taglish OK, grounded in the top KB hit + last 3 lines, `max_tokens≈80`. Send `{"type":"reply"}`.

### Phase 4: notes polish
- `/notes`: Laya picks **category, priority, disposition** from fixed lists (dropdown-safe values with confidence); Gemma writes only the summary and follow-up, and is told not to invent facts.
- Editable fields, "Copy to CRM" (clipboard, formatted). Notes use the masked transcript.

### Phase 5: prove "local"
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
