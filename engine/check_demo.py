"""Scripted demo check: stream engine/demo/call.wav via /ws/demo, print every message with its time,
assert no raw card digits, then POST /notes and /qa. Engine must be running: uv run --offline python check_demo.py"""
import asyncio, json, time, re, urllib.request, websockets
async def main():
    t0 = time.time(); lines = []; beats = {}
    async with websockets.connect("ws://127.0.0.1:8765/ws/demo", max_size=None) as ws:
        try:
            async for raw in ws:
                m = json.loads(raw); t = time.time() - t0; k = m["type"]
                if k == "suggestions": info = m["items"][0]["text"].splitlines()[0][:50]
                elif k == "signals": info = f'{m["intent"]} {m["intent_p"]:.2f} mood {m["mood"]:.2f} raw {m["mood_raw"]:.2f} esc {m["escalate"]}'
                else: info = m.get("text", "")
                print(f"{t:5.1f}s {k:11s} {info}")
                if k == "transcript": lines.append(m["text"])
                if k == "transcript" and "•••• 4821" in m["text"]: beats.setdefault("mask", t)
                if k == "translation": beats.setdefault("subtitle", t)
                if k == "suggestions" and "Billing" in info: beats.setdefault("billing_kb", t)
                if k == "signals" and m["escalate"]: beats.setdefault("escalate", t)
                if k == "suggestions" and "Angry" in info: beats.setdefault("deesc_pinned", t)
                if k == "reply": beats.setdefault("reply", t)
                if k == "end": beats["end"] = t; break
        except websockets.ConnectionClosedError: pass
    alltext = " ".join(lines)
    assert not re.search(r"\d{4}[ .-]?\d{4}", alltext), "raw digits leaked"
    t1 = time.time()
    req = urllib.request.Request("http://127.0.0.1:8765/notes", json.dumps({"transcript": "\n".join(lines)}).encode(), {"Content-Type": "application/json"})
    notes = json.load(urllib.request.urlopen(req)); beats["notes_s"] = round(time.time() - t1, 2)
    print(json.dumps({k: (v["value"], round(v["confidence"], 2)) if isinstance(v, dict) else v for k, v in notes.items()}, ensure_ascii=False, indent=1))
    t1 = time.time(); req = urllib.request.Request("http://127.0.0.1:8765/qa", req.data, req.headers)
    qa = json.load(urllib.request.urlopen(req))["steps"]; beats["qa_s"] = round(time.time() - t1, 2)
    print("QA", [(q["label"], q["done"]) for q in qa])
    print("BEATS", {k: round(v, 1) for k, v in beats.items()})
asyncio.run(main())
