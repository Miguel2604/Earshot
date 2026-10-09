#!/bin/bash
# Downloads the four models into ~/models from ModelScope (Hugging Face is slow/unreliable from PH).
# Big weight files are pulled in parallel byte ranges: ~25 MB/s vs ~1 MB/s single-stream.
set -e
DEST=${EARSHOT_MODELS:-~/models}
MS=https://modelscope.cn/models

pdl() { # url out size chunks
  local url=$1 out=$2 size=$3 n=$4 step=$(( ($3 + $4 - 1) / $4 ))
  for i in $(seq 0 $((n - 1))); do
    local s=$((i * step)) e=$(( (i + 1) * step - 1 )); [ $e -ge $size ] && e=$((size - 1))
    ( until [ -f "$out.p$i" ] && [ $(stat -f%z "$out.p$i") -eq $((e - s + 1)) ]; do
        have=$([ -f "$out.p$i" ] && stat -f%z "$out.p$i" || echo 0)
        curl -sL --retry 5 --speed-limit 20000 --speed-time 20 -r $((s + have))-$e "$url" >> "$out.p$i"
      done ) &
  done
  wait
  cat $(for i in $(seq 0 $((n - 1))); do echo "$out.p$i"; done) > "$out" && rm "$out".p*
  [ $(stat -f%z "$out") -eq $size ] || { echo "size mismatch: $out"; exit 1; }
}

fetch() { # repo local_dir big_file big_size small_files...
  local repo=$1 dir=$DEST/$2 big=$3 size=$4; shift 4
  mkdir -p "$dir"
  for f in "$@"; do mkdir -p "$dir/$(dirname $f)"; curl -sfL "$MS/$repo/resolve/master/$f" -o "$dir/$f"; done
  [ -f "$dir/$big" ] && [ $(stat -f%z "$dir/$big") -eq $size ] || pdl "$MS/$repo/resolve/master/$big" "$dir/$big" $size 16
  echo "ok $dir"
}

fetch mlx-community/whisper-large-v3-turbo whisper-large-v3-turbo-mlx weights.safetensors 1613977612 config.json &
fetch google/embeddinggemma-2 embeddinggemma-2 model.safetensors 1488915288 \
  config.json config_sentence_transformers.json modules.json sentence_bert_config.json 1_Pooling/config.json \
  2_Normalize/config.json preprocessor_config.json processor_config.json tokenizer.json tokenizer.model \
  tokenizer_config.json chat_template.jinja &
fetch mlx-community/gemma-4-e4b-it-4bit gemma-4-e4b-it-4bit model.safetensors 5146800534 \
  config.json generation_config.json model.safetensors.index.json processor_config.json tokenizer.json \
  tokenizer_config.json chat_template.jinja &
fetch convaiinnovations/laya-multilingual laya-multilingual model.safetensors 643835514 \
  config.json rl_agent_config.json encoder/config.json tokenizer/tokenizer.json tokenizer/tokenizer_config.json &
wait
