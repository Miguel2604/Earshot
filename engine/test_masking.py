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
# Phase 8: secrets after CVV/OTP/PIN/password keywords (3-8 digits within 5 words), incl. real Whisper output
# on demo/call-11labs.wav, where the agent's ask ends one chunk and the CVV keyword + digits start the next.
from server import alert, mask_with
assert mask("CVV ko 123") == "CVV ko •••"
assert mask("ang OTP po ay 482913.") == "ang OTP po ay ••••••."
assert mask("yung PIN niyo po, 1234") == "yung PIN niyo po, ••••"
assert mask("5 to 7 days") == "5 to 7 days" and mask("pin 5 to 7 days") == "pin 5 to 7 days"
ctx = "pa rin naayos, nakakainis na talaga. Para ma-verify po, pakibigay po ng..."
line = "CVV ng card nyo. Uh, 1, 2, 3. Ay, wait, bakit?"
assert mask_with(ctx, line) == "CVV ng card nyo. Uh, •••. Ay, wait, bakit?", mask_with(ctx, line)
assert mask_with("Para ma-verify po, pakibigay po ang CVV.", "1 2 3 po") == "••• po"
assert mask_with("", "For 111.") == "For 111."
assert alert(ctx, line) == "CVV" and alert("", "ano po ang OTP?") == "OTP" and alert("", "yung PIN niyo") == "PIN"
assert alert("", "Na-charge ako ng dalawang beses") is None and alert("", "CVV.") is None
assert hold_tail("Uh, 1, 2,") == ("Uh,", "1, 2,")
print("ok")
