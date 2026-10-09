# Submission draft (Cerebral Valley form, AppBuildersPH Hackathon 2026)

Draft answers for Miguel to paste. Replace every `TODO` before submitting. Code freeze: **10:00 AM Sat Oct 10, 2026**.

## Project name
Earshot

## Short description
An on-device AI copilot for Filipino call center agents. It listens to the call, shows a live Taglish transcript with English subtitles, masks card and phone numbers as they're spoken, tracks the customer's mood and pulls up the right procedure, drafts what to say next, and writes the after-call notes. Four local models on a MacBook; zero bytes of customer data leave the laptop.

## Team
TODO: names + roles (Miguel Kalaw, ...)

## GitHub repo
TODO: https://github.com/TODO/earshot (must be **public** before 10:00 AM)

## Hardware
MacBook, Apple M5, 24 GB unified memory. All inference runs on the Mac's GPU (MLX and PyTorch MPS).

## Demo video
TODO: link (60–90 s, shot list at the bottom of this file)

## Screenshots
In the repo under `docs/`:
- `docs/phase-6.png`: mid-call escalation: "Say this" reply, pinned de-escalation script, mood meter at Upset, masked card `•••• 4821`, Taglish lines with English subtitles.
- `docs/phase-4.png`: after-call notes (category/priority/disposition dropdowns with confidence, summary, follow-up, Copy to CRM).
- `docs/phase-5.png`: footer showing "Offline · 0 bytes sent to cloud".
- `docs/phase-3.png`, `docs/phase-2.png`: live signals and PII masking.

## What runs locally / what needs internet
- **Local (works with Wi-Fi off):** everything at call time: speech-to-text, English subtitles, live intent + mood, knowledge-base search, "say this" replies, PII masking, after-call notes, the demo call and the UI. The app only talks to its own engine on `127.0.0.1:8765`. We checked with `lsof` sampled every 0.5 s from engine launch through a full call and notes: the only sockets were `127.0.0.1:8765`.
- **Internet:** setup only: downloading model weights once (from ModelScope) and installing packages (`uv sync`, `pnpm install`, Rust crates). At runtime the engine runs with `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY` and `uv run --offline`.

## Models
| Model | Job | Runtime |
|---|---|---|
| Whisper large-v3-turbo (MLX) | Speech-to-text (Taglish) | `mlx-whisper` |
| Gemma 4 E4B-it, 4-bit MLX | English subtitles, "say this" reply, note summary + follow-up | `mlx-vlm` |
| Laya multilingual (322M) | Live intent + mood every chunk; note category / priority / disposition | `laya` (PyTorch, Apple GPU) |
| EmbeddingGemma 2 (270M, text) | Knowledge-base procedure search | `sentence-transformers` |

## Frameworks
Tauri 2, SvelteKit (Svelte 5), FastAPI, MLX, mlx-whisper, mlx-vlm, sentence-transformers, PyTorch, uv.

## APIs
None. No cloud AI or any other external API.

## Existing code
None. Scaffolded and built during the hackathon. Style reference: `DESIGN.md` (getdesign.md's Airtable analysis). The idea of AI call classification is inspired by the team's earlier Neosolve project; no code reused.

## AI dev tools
Claude Code.

## Why does this product benefit from running AI locally?
Because in a call center, cloud AI isn't an option. Without local inference, Earshot couldn't exist.

1. **Customer data can't leave the building.** BPO client contracts and the Data Privacy Act (RA 10173) forbid sending call audio, card numbers and account details to third-party AI services. Earshot runs all four models on the agent's laptop, so the raw call never leaves it. Even inside the app, card numbers, phone numbers and emails are masked (`•••• 4821`) before any text reaches the screen, the search or the notes.
2. **It has to keep up with live speech.** An agent needs the procedure and a suggested reply while the customer is still talking, not after a round trip. On an M5 MacBook each 5 s chunk is transcribed in ~0.4 s, translated in ~0.4–0.8 s, classified (intent + mood) and matched to a procedure in ~0.07 s, and gets a suggested reply in ~0.5–1.2 s: under 2.5 s of work per 5 s of audio, so it keeps up with real time. Each line appears ~0.4 s after it's spoken; notes are ready ~2 s after the call ends.
3. **No per-minute cost.** A center runs thousands of agent-hours a day. Cloud speech + LLM pricing per call adds up; local inference costs nothing per call on hardware the center already buys.
4. **Works when the network doesn't.** Philippine connectivity is uneven and centers lock down their networks. Earshot works with Wi-Fi off; we demo it that way.
5. **Taglish, done locally.** Small multilingual models (Whisper, Laya, Gemma) handle the code-switched Taglish real calls use and give foreign clients' QA teams an English subtitle, without shipping the call abroad to be translated.

---

## Social post draft (X / LinkedIn)

**X (≤280 chars):**
> Earshot: an on-device AI copilot for Filipino call center agents. Live Taglish transcript + English subtitles, card numbers masked as they're spoken, mood-triggered escalation, drafted replies and notes. 4 local models, Wi-Fi off, 0 bytes to the cloud. @cognition @DevinAI #AppBuildersPH

**LinkedIn:**
> We built **Earshot** at the AppBuildersPH Hackathon 2026 (theme: Local AI).
>
> Call center agents in the Philippines juggle an upset customer, a knowledge base and after-call notes at the same time, and they can't paste customer data into cloud AI. So we made a copilot that runs entirely on the agent's laptop:
> • live Taglish transcript with English subtitles
> • card and phone numbers masked as they're spoken (•••• 4821)
> • mood meter that pins the de-escalation script when a caller gets angry
> • the right procedure and a "say this" reply, mid-call
> • structured after-call notes, ready to paste into the CRM
>
> Four local models on a MacBook M5 (Whisper, Gemma 4, Laya, EmbeddingGemma 2). We demo it with Wi-Fi off: zero bytes leave the laptop.
>
> Demo: TODO video link · Code: TODO repo link
> Thanks @Cognition / @Devin and the AppBuildersPH team. #AppBuildersPH

(Check the exact handles when posting: Devin / Cognition on X and LinkedIn.)

---

## Demo video shot list (60–90 s)
Record the screen at the Mac's native resolution with the Earshot overlay docked top-right over a plausible agent desktop (e.g. a CRM page in the browser). Audio: the demo call itself plus a short voice-over.

| Time | Shot | Voice-over / on screen |
|---|---|---|
| 0–8 s | Title card or face cam, then the desktop with the overlay idle ("On-device · offline" badge). | "Call center agents in the Philippines can't paste customer data into cloud AI. Earshot runs entirely on this laptop." |
| 8–12 s | Turn Wi-Fi off in the menu bar; footer flips to "● Offline · 0 bytes sent to cloud". | "Wi-Fi off." |
| 12–25 s | Click **Demo call**. Taglish lines stream in with italic English subtitles; "Billing dispute or double charge" procedure on top. | "Live Taglish transcript, English subtitles, and the right procedure as the customer explains." |
| 25–40 s | Customer reads the card number: zoom on `•••• 4821`. | "Card numbers are masked before they ever hit the screen." |
| 40–50 s | Outburst: mood meter goes to Upset, escalation banner, "Angry or escalating customer" pinned, "Say this" card updates. Hold on this frame (it matches `docs/phase-6.png`). | "Mood rises, the de-escalation script pins itself, and Earshot drafts what to say." |
| 50–65 s | Agent resolves; call auto-ends; notes card appears: Billing / Medium / Follow-up + summary. Change a dropdown, click **Copy to CRM**, paste into the CRM page. | "After the call: structured notes, masked, one click into the CRM." |
| 65–80 s | Optional: terminal with `lsof -nP -i -a -p $(lsof -tnP -iTCP:8765 -sTCP:LISTEN)` showing only `127.0.0.1`. End card: "Earshot · 4 local models · 0 bytes to the cloud · #AppBuildersPH". | "Four local models on a MacBook. Zero bytes left this laptop." |
