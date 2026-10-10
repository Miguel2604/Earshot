#!/bin/sh
# Phase 11: clips/NN.mp3 (from gen.html) -> ../call.wav, the demo call (16 kHz mono s16), gaps between lines.
set -e
cd "$(dirname "$0")"
clips=${1:-clips}; tmp=$(mktemp -d)
for f in "$clips"/*.mp3; do
  n=$(basename "$f" .mp3)
  # longer beat before the outburst (line 04); short one before the card (07): with 0.5-1.4 s the card digits land in
  # one chunk and Whisper loops on "4 1 1 1, 2 2 2 2" (2-7 s fallback); 0.2 s splits them and stays at 0.5 s
  case $n in 03) gap=0.9;; 06) gap=0.2;; *) gap=0.5;; esac
  ffmpeg -loglevel error -y -i "$f" -ar 16000 -ac 1 -af "apad=pad_dur=$gap" -c:a pcm_s16le "$tmp/$n.wav"
  echo "file '$tmp/$n.wav'" >> "$tmp/list.txt"
done
ffmpeg -loglevel error -y -f concat -safe 0 -i "$tmp/list.txt" -c:a pcm_s16le ../call.wav
rm -rf "$tmp"
ffprobe -v error -show_entries format=duration:stream=sample_rate,channels,codec_name -of compact ../call.wav
