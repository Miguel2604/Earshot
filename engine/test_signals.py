"""Assert check for the Phase 3 plain rules (translation skip, reply gate, KB boost). No models: uv run python test_signals.py"""
import server

assert server.is_english("I can see the double charge. I will file a refund today.")
assert not server.is_english("Na charge ako ng dalawang beses")
assert server.REQUEST.search("Pwede ko po bang makuha") and server.REQUEST.search("Why? ") and not server.REQUEST.search("Okay sige")

server.kb_docs = ["Slow internet\nx", "Billing dispute\ny", "Angry or escalating customer\nz"]
hits = [(0.70, server.kb_docs[0]), (0.68, server.kb_docs[1])]
assert server.boosted(hits, "billing", False)[0][1].startswith("Billing")  # +0.05 bonus flips the order
assert server.boosted(hits, "technical", False)[0][1].startswith("Slow")
assert server.boosted(hits, None, True)[0][1].startswith("Angry")  # escalation pins the script on top
assert server.small_talk("Good afternoon. Thank you for calling Fiberlink. How may I help you?") and server.small_talk("Fibberlink")
assert not server.small_talk("Ho. Hi, yes. Na charge ako ng dalawang beses")
st = server.new_call()  # call intent is the running best: one noisy chunk can't flip it
assert server.vote(st, "closing", 0.9) == (None, 0)
for i, p in [("billing", 0.86), ("billing", 0.99), ("technical", 0.70)]:
    best, _ = server.vote(st, i, p)
assert best == "billing"
t = "Po. Weed ko po bang makyuhang account number ninyo?\nyou will get an SMS confirmation."  # QA quotes must be in the call
assert server.grounded("you will get an SMS confirmation", t) and server.grounded("Po. Weed ko po bang account number ninyo", t)
assert not server.grounded(None, t) and not server.grounded("null", t) and not server.grounded("I will call you back within 24 hours", t)
assert server.customer_english(["Hi, I was charged twice. Can you fix it?"])  # reply language follows the customer
assert not server.customer_english(["Ilang beses na akong tumawag.", "I'm sorry to hear that. I will check."])
print("ok")
