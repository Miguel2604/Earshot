"""Run: uv run python test_masking.py  (no models loaded)"""
from server import hold_tail, mask

# Real Whisper output on demo/call.wav: the card number is cut across two chunks.
sent, held = hold_tail("Kenis na talaga. Ito na young card ko. For 111.")
assert sent == "Kenis na talaga. Ito na young card ko. For" and held == "111.", (sent, held)
assert mask(f"{held} 2222-3333-4821 Ibalik ni Iona young perico") == "•••• 4821 Ibalik ni Iona young perico"
assert mask("card 4111222233334821 po") == "card •••• 4821 po"
assert mask("call me at 0917 123 4567 or +63 917-123-4567") == "call me at •••• 4567 or •••• 4567"
assert mask("account number 1234567") == "account number •••• 4567"
assert mask("email juan.dela-cruz@gmail.com po") == "email ••••@gmail.com po"
# Short numbers stay: amounts, days, times.
assert mask("five to seven banking days, 1,299 pesos, 5 to 7 days, 10:30") == "five to seven banking days, 1,299 pesos, 5 to 7 days, 10:30"
assert hold_tail("thank you for calling Fiberlink.") == ("thank you for calling Fiberlink.", "")
print("ok")
