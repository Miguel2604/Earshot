"""Run: uv run python test_chunking.py  (no models loaded)"""
import numpy as np

from server import SR, split_on_silence

loud = np.ones(SR, dtype=np.float32)
quiet = np.zeros(SR // 5, dtype=np.float32)
# 5 s of "speech" with a 0.2 s pause starting at 4.5 s: the cut must land inside the pause.
pcm = np.concatenate([loud] * 4 + [loud[: SR // 2], quiet, loud[: SR * 3 // 10]])
now, carry = split_on_silence(pcm)
assert 4.5 * SR <= len(now) <= 4.7 * SR, len(now) / SR
assert len(now) + len(carry) == len(pcm)
assert len(split_on_silence(pcm[:SR])[1]) == 0  # short chunks pass through whole
print("ok")
