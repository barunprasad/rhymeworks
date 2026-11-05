#!/usr/bin/env bash
# Pose-edit spike: take one character image, ask FLUX.2 klein 4B (edit mode) for 3 body poses.
# Identity is judged by eye at the gate; this measures time + memory and saves the variants.
# Usage: bash bench_poses.sh <character.png>
set -uo pipefail
cd "$(dirname "$0")/.."
ENV=envs/image
SRC=$1
OUT=results/image/poses
mkdir -p "$OUT"

KEEP="Keep the exact same character design, colors, proportions, line style and flat vector look. Mouth closed. Plain white background, full body."
declare -a POSES=(
  "wave:The same robot character waving hello with its right arm raised high, happy expression."
  "jump:The same robot character jumping up joyfully, both arms raised, feet off the ground."
  "point:The same robot character pointing to the right side with one arm, looking in that direction."
)

for p in "${POSES[@]}"; do
  name=${p%%:*}; text=${p#*:}
  HF_HUB_OFFLINE=1 uv run --project "$ENV" python bench.py "klein4b edit pose $name" -- \
    uv run --project "$ENV" mflux-generate-flux2-edit \
      --model mflux-community/flux2-klein-4b-mflux-q4 --base-model flux2-klein-4b \
      --image-paths "$SRC" --seed 42 --width 1024 --height 1024 \
      --prompt "$text $KEEP" --output "$OUT/$name.png"
done
