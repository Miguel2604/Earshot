#!/bin/sh
# Phase 11: clips/NN.mp3 (from gen.html) -> ../call-11labs.wav (16 kHz mono s16), gaps between lines.
set -e
cd "$(dirname "$0")"
clips=${1:-clips}; tmp=$(mktemp -d)
for f in "$clips"/*.mp3; do
  n=$(basename "$f" .mp3)
  case $n in 03) gap=0.9;; *) gap=0.5;; esac   # longer beat before the outburst (line 04)
  ffmpeg -loglevel error -y -i "$f" -ar 16000 -ac 1 -af "apad=pad_dur=$gap" -c:a pcm_s16le "$tmp/$n.wav"
  echo "file '$tmp/$n.wav'" >> "$tmp/list.txt"
done
ffmpeg -loglevel error -y -f concat -safe 0 -i "$tmp/list.txt" -c:a pcm_s16le ../call-11labs.wav
rm -rf "$tmp"
ffprobe -v error -show_entries format=duration:stream=sample_rate,channels,codec_name -of compact ../call-11labs.wav
