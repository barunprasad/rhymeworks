#!/usr/bin/env bash
# Image model benchmark: same character prompt, fixed seed, per model × size.
# Uses pre-quantized mflux-community 4-bit weights (full bf16 repos were 30+ GB each — too slow to fetch).
# First run per model is a warm-up (model load); later runs are the measurement.
# Usage: bash bench_images.sh <model-key> ...   keys: zimage klein4b
set -uo pipefail
cd "$(dirname "$0")/.."
ENV=envs/image
OUT=results/image
mkdir -p "$OUT"

PROMPT="Pip, a small friendly round robot for a preschool cartoon, big expressive eyes, teal and orange body, short antenna with a yellow bulb, flat vector illustration, simple shapes, thick clean outlines, soft pastel colors, full body, front view, mouth closed, plain white background"
SEED=42

run() { # label, cmd...
  local label=$1; shift
  HF_HUB_OFFLINE=1 uv run --project "$ENV" python bench.py "$label" -- uv run --project "$ENV" "$@"
}

for key in "$@"; do
  case $key in
    zimage)  cmd=(mflux-generate-z-image-turbo --model mflux-community/z-image-turbo-mflux-q4 --base-model z-image-turbo) ;;
    klein4b) cmd=(mflux-generate-flux2 --model mflux-community/flux2-klein-4b-mflux-q4 --base-model flux2-klein-4b) ;;
    *) echo "unknown $key"; continue ;;
  esac
  run "$key q4 768 warmup" "${cmd[@]}" --width 768  --height 768  --seed $SEED --prompt "$PROMPT" --output "$OUT/${key}_768_warm.png"
  run "$key q4 768"        "${cmd[@]}" --width 768  --height 768  --seed 7     --prompt "$PROMPT" --output "$OUT/${key}_768.png"
  run "$key q4 1024"       "${cmd[@]}" --width 1024 --height 1024 --seed $SEED --prompt "$PROMPT" --output "$OUT/${key}_1024.png"
  # 4 character candidates in one process (what the character gate needs)
  run "$key q4 1024 x4 seeds" "${cmd[@]}" --width 1024 --height 1024 --seed 1 2 3 4 --prompt "$PROMPT" --output "$OUT/${key}_cand.png"  # mflux appends _seed_N
done
