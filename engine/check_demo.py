"""Scripted demo check: stream engine/demo/call.wav via /ws/demo, print every message with its time,
assert no raw card digits, then POST /notes and /qa. Polls /egress every 2 s throughout (Earshot must stay at 0). Engine must be running: uv run --offline python check_demo.py"""
import asyncio, json, time, re, urllib.request, websockets
eg = []
async def poll_egress():
    while True:
        eg.append(await asyncio.to_thread(lambda: json.load(urllib.request.urlopen("http://127.0.0.1:8765/egress"))))
        await asyncio.sleep(2)
async def main():
    t0 = time.time(); lines = []; beats = {}; steps = []; poller = asyncio.create_task(poll_egress())
    async with websockets.connect("ws://127.0.0.1:8765/ws/demo", max_size=None) as ws:
        try:
            async for raw in ws:
                m = json.loads(raw); t = time.time() - t0; k = m["type"]
                if k == "busy":
                    if m["step"]: steps.append(m["step"])
                    continue
                if k == "timings": info = f'{m["ms"]}  order {"→".join(steps)}'; steps.clear()
                elif k == "suggestions": info = m["items"][0]["text"].splitlines()[0][:50]
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
                if k == "alert": beats.setdefault("alert", t)
                if k == "transcript" and re.search(r"CVV.*•••", m["text"]): beats.setdefault("cvv_mask", t)
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
    poller.cancel(); eg.append(json.load(urllib.request.urlopen("http://127.0.0.1:8765/egress")))
    mac = eg[-1]["mac_bytes_out"] - eg[0]["mac_bytes_out"]
    print(f"EGRESS {len(eg)} polls: Mac +{mac} B out; Earshot max {max(e['engine_bytes_out'] for e in eg)} B, {max(e['engine_remote_conns'] for e in eg)} connections")
    assert all(e["engine_bytes_out"] == 0 and e["engine_remote_conns"] == 0 for e in eg), "engine egress"
    print("BEATS", {k: round(v, 1) for k, v in beats.items()})
asyncio.run(main())
