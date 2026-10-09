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
print("ok")
