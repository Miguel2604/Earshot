#!/bin/sh
# Placeholder demo call (TTS) until a real 2-person recording replaces call.wav (PLAN Phase 6).
# Taglish double-charge story: customer charged twice, gets angry, reads a card number, agent calms them.
# Needs macOS `say` + ffmpeg. Output: call-tts.wav (the old placeholder; call.wav is the ElevenLabs version), 16 kHz mono 16-bit, ~66 s.
# Note: `say` voices change across macOS updates, so a rerun won't match the committed call.wav byte for byte
# (that one was verified end to end; rerun the scripted /ws/demo check after regenerating).
set -e
cd "$(dirname "$0")"
tmp=$(mktemp -d)
i=0
line() { # voice, text
  i=$((i + 1)); f="$tmp/$(printf %02d $i).aiff"
  say -v "$1" -r 175 -o "$f" "$2 [[slnc 600]]"
  echo "file '$f'" >> "$tmp/list.txt"
}
A="Samantha"; C="Rishi"
line "$A" "Good afternoon, thank you for calling Fiberlink, this is Ana. How may I help you po?"
line "$C" "Hi, yes. Na-charge ako ng dalawang beses ngayong buwan sa bill ko. Same amount, twice."
line "$A" "I'm sorry to hear that po. Pwede ko po bang makuha ang account number ninyo?"
line "$C" "Ilang beses na akong tumawag! Bakit hanggang ngayon hindi pa rin naaayos? Nakakainis na talaga!"
line "$C" "Eto na yung card ko, four one one one, two two two two, three three three three, four eight two one. Ibalik niyo na yung pera ko!"
line "$C" "Ayoko na ng sorry! Gusto ko makausap ang supervisor ninyo, ngayon din!"
line "$A" "Naiintindihan ko po kayo, and I apologize for the trouble. I can see the double charge. I will file a refund today, and it will be credited in five to seven banking days."
line "$C" "Sige, okay. Basta i-text niyo ako pag na-process na."
line "$A" "Opo, you will get an SMS confirmation. Salamat po sa pasensya, and thank you for calling Fiberlink."
ffmpeg -loglevel error -y -f concat -safe 0 -i "$tmp/list.txt" -ar 16000 -ac 1 -c:a pcm_s16le call-tts.wav
rm -rf "$tmp"
echo "wrote $(pwd)/call-tts.wav"
