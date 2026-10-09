# Phase 11: ElevenLabs demo voices (via Puter) — generation notes

## Status: DONE. Miguel generated the clips; `build.sh` (0.2 s gap before the card line, see there) now writes `call.wav` directly; the `say` version is `call-tts.wav`. History below.

## Earlier status: BLOCKED on Puter sign-in (2026-10-10)

**For Miguel: sign in to Puter in the browser pane, then rerun Phase 11 generation.**

What happened: the generator page loaded Puter.js fine, but the first `puter.ai.txt2speech(...)` call
opened a puter.com auth popup (Puter is "user-pays": every call runs on the visitor's Puter account).
The agent did not sign in, create an account, or accept terms, so the call failed with
`{"code":"auth_canceled"}`. No audio was generated and nothing was sent besides that one attempt.
`call-11labs.wav` / `call-11labs.txt` do not exist yet; `call.wav` is untouched.

## Rerun (about 2 minutes, you click once)
1. `python3 -I engine/demo/elevenlabs/serve.py 8811` (serves the page, saves clips to `engine/demo/elevenlabs/clips/NN.mp3`).
2. Open http://127.0.0.1:8811/gen.html, click **Generate** yourself (the popup only opens from a real click), sign in to Puter in the popup.
   The log shows `01 ok <bytes>` ... `11 ok`, then `DONE`. If it stops on a line, click Generate again (it redoes all 11).
3. `engine/demo/elevenlabs/build.sh` → `engine/demo/call-11labs.wav` (16 kHz mono s16; 0.5 s gaps, 0.9 s before the outburst) and prints duration/format. Target 60–90 s.
4. Whisper check, offline, without the server (same model + language as `engine/models.py`):
   ```sh
   cd engine && uv run --offline python -c "import mlx_whisper, os; p=os.path.expanduser('~/models/whisper-large-v3-turbo-mlx'); \
   r=mlx_whisper.transcribe('demo/call-11labs.wav', path_or_hf_repo=p, language='tl'); \
   open('demo/call-11labs.txt','w').write('\n'.join(f\"{s['start']:5.1f} {s['text'].strip()}\" for s in r['segments'])+'\n')"
   ```
   Confirm the card digits (`4111 2222 3333 4821`) and the CVV line come through.
5. Commit only these: `git add engine/demo/call-11labs.wav engine/demo/call-11labs.txt engine/demo/PHASE11_NOTES.md engine/demo/elevenlabs/{gen.html,serve.py,build.sh}` (don't commit `clips/`).
6. Swap into `call.wav` only after `check_demo.py` passes every beat (PLAN Phase 11).

## Settings
- Provider `elevenlabs`, model `eleven_multilingual_v2`, `output_format: mp3_44100_128`.
- Agent (Ana): `21m00Tcm4TlvDq8ikWAM` (Rachel, calm female; the tutorial's public sample voice).
- Customer: `pNInz6obpgDQGcFmaJgB` (Adam, male ElevenLabs premade voice). If it errors as unavailable on your account, swap in any other premade voice ID in `gen.html`.

## Script (= `make_demo.sh` + Phase 8 CVV beat before the card line)
| # | Voice | Text |
|---|---|---|
| 01 | Agent | Good afternoon, thank you for calling Fiberlink, this is Ana. How may I help you po? |
| 02 | Customer | Hi, yes. Na-charge ako ng dalawang beses ngayong buwan sa bill ko. Same amount, twice. |
| 03 | Agent | I'm sorry to hear that po. Pwede ko po bang makuha ang account number ninyo? |
| 04 | Customer | Ilang beses na akong tumawag! Bakit hanggang ngayon hindi pa rin naaayos? Nakakainis na talaga! |
| 05 | Agent | Para ma-verify po, pakibigay po ng CVV ng card niyo. |
| 06 | Customer | Uh, one two three... ay, wait, bakit niyo kailangan yan? |
| 07 | Customer | Eto na yung card ko, 4 1 1 1, 2 2 2 2, 3 3 3 3, 4 8 2 1. Ibalik niyo na yung pera ko! |
| 08 | Customer | Ayoko na ng sorry! Gusto ko makausap ang supervisor ninyo, ngayon din! |
| 09 | Agent | Naiintindihan ko po kayo, and I apologize for the trouble. I can see the double charge. I will file a refund today, and it will be credited in five to seven banking days. |
| 10 | Customer | Sige, okay. Basta i-text niyo ako pag na-process na. |
| 11 | Agent | Opo, you will get an SMS confirmation. Salamat po sa pasensya, and thank you for calling Fiberlink. |

The card number is written as spaced single digits so ElevenLabs reads it digit by digit (not "four thousand one hundred eleven").

## Files
- `elevenlabs/gen.html`: Puter.js page, voices the 11 lines in order and POSTs each MP3 to the receiver.
- `elevenlabs/serve.py`: stdlib server on 127.0.0.1 (static page + `POST /save/NN`).
- `elevenlabs/build.sh`: ffmpeg concat + gaps → `call-11labs.wav` (smoke-tested with dummy tones: 4×1 s clips → 6.4 s, pcm_s16le 16 kHz mono).
- Build-time only: nothing here is used by the app at runtime.
