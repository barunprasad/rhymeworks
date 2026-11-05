#!/bin/zsh
# Rhymeworks: set up the engines and models on a fresh Mac (Apple Silicon).
#
#   npm run doctor          # only check: what is there, what is missing (changes nothing)
#   npm run setup:engines   # fetch whatever is missing (about 80 GB the first time; safe to rerun)
#   npm run setup:engines -- --skip-writer   # leave out the optional story helper (gemma4:26b, 18 GB)
#
# Everything lands inside this repo (spikes/, gitignored) or in the standard caches (~/.cache/huggingface, Ollama).
# The engines and the video models are pinned to the versions Rhymeworks was tested with; the cached models
# (pictures, speech) follow their main branch, because the tools load them by name while offline.
set -u
cd "${0:A:h}/.."
ROOT=$PWD

CHECK=0 WRITER=1
for a in "$@"; do
  case $a in
    --check) CHECK=1 ;;
    --skip-writer) WRITER=0 ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done

LTX_REPO=https://github.com/dgrauet/ltx-2-mlx.git   LTX_REV=895201d
ACE_REPO=https://github.com/ace-step/ACE-Step-1.5.git ACE_REV=ca1e85f
SPLEETER_URL=https://github.com/deezer/spleeter/releases/download/v1.4.0/2stems.tar.gz
WRITER_MODEL=gemma4:26b
LTX_FILES=(LICENSE README.md "*.json" audio_vae.safetensors connector.safetensors spatial_upscaler_x2_v1_1.safetensors
           transformer-distilled-1.1.safetensors vae_decoder.safetensors vae_encoder.safetensors vocoder.safetensors)

missing=0
ok()   { print -P "  %F{green}✓%f $1"; }
miss() { print -P "  %F{yellow}✗%f $1"; missing=$((missing + 1)); }
step() { print -P "\n%B$1%b"; }
hf()   { uvx --from "huggingface_hub[cli]" hf download "$@"; }
hf_cached() { [ -d "$HOME/.cache/huggingface/hub/models--${1//\//--}/snapshots" ]; }

# 1 ---------------------------------------------------------------- tools
step "1. Tools"
[ "$(uname -sm)" = "Darwin arm64" ] && ok "macOS on Apple Silicon" || { miss "needs a Mac with Apple Silicon (M1 or newer)"; exit 1; }
mem=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
[ $mem -ge 32 ] && ok "${mem} GB memory" || print -P "  %F{yellow}!%f ${mem} GB memory: 32 GB is recommended (moving video may run out)"
free=$(df -g "$ROOT" | awk 'NR==2 {print $4}')
[ "$free" -ge 90 ] && ok "${free} GB free disk" || print -P "  %F{yellow}!%f ${free} GB free disk: the first setup needs about 80 GB"
tools_missing=()
for t in uv node npm ffmpeg ffprobe ollama; do
  command -v $t >/dev/null && ok "$t" || { miss "$t"; tools_missing+=$t; }
done
xcrun --find swift >/dev/null 2>&1 && ok "swift (Xcode command line tools)" || miss "swift: run  xcode-select --install"
if (( ${#tools_missing} )); then
  pkgs=${${tools_missing:#ffprobe}:#npm}
  print "  install with:  brew install ${pkgs:-ffmpeg}   (https://brew.sh)"
  [ $CHECK = 1 ] || { echo "Install the tools above, then run this again."; exit 1; }
fi

# 2 ---------------------------------------------------------------- engines (code)
step "2. Engines"
engine() {   # dir, repo, rev
  local dir=$1 repo=$2 rev=$3
  if [ -d "$dir/.git" ]; then
    ok "$dir ($(git -C "$dir" rev-parse --short HEAD))"
  elif [ $CHECK = 1 ]; then
    miss "$dir"
  else
    git clone "$repo" "$dir" && git -C "$dir" checkout -q "$rev" && ok "$dir ($rev)"
  fi
}
engine spikes/vendor/ltx-2-mlx "$LTX_REPO" $LTX_REV
engine spikes/vendor/ACE-Step-1.5 "$ACE_REPO" $ACE_REV

# 3 ---------------------------------------------------------------- Python environments + web app
step "3. Python environments and the web app"
for p in pipeline spikes/envs/image spikes/envs/audio spikes/envs/sep spikes/vendor/ltx-2-mlx spikes/vendor/ACE-Step-1.5; do
  [ -f "$p/pyproject.toml" ] || continue
  if [ $CHECK = 1 ]; then
    [ -x "$p/.venv/bin/python" ] && ok "$p" || miss "$p (uv sync)"
  else
    uv sync --project "$p" -q && ok "$p" || miss "$p (uv sync failed)"
  fi
done
if [ -d packages/studio/node_modules ]; then ok "packages/studio (npm)"
elif [ $CHECK = 1 ]; then miss "packages/studio (npm install)"
else npm --prefix packages/studio install --no-fund --no-audit && ok "packages/studio (npm)"; fi

# 4 ---------------------------------------------------------------- models
step "4. Models"
model_dir() {   # local dir, repo, last file to arrive, label, [hf args…]  (hf writes each file only once it is complete)
  local dir=$1 repo=$2 marker=$3 label=$4; shift 4
  if [ -f "$dir/$marker" ]; then ok "$label"
  elif [ $CHECK = 1 ]; then miss "$label"
  else hf "$repo" --local-dir "$dir" "$@" && ok "$label"; fi
}
model_cache() {   # repo, label
  if hf_cached "$1"; then ok "$2"
  elif [ $CHECK = 1 ]; then miss "$2"
  else hf "$1" >/dev/null && ok "$2"; fi
}
model_dir spikes/models/ltx-2.3-mlx-q4 dgrauet/ltx-2.3-mlx-q4 transformer-distilled-1.1.safetensors "Moving video: LTX-2.3 distilled q4 (~20 GB)" \
  --revision f306259444116d71927188af2fbbf7fdc1a8089a --include $LTX_FILES
model_dir spikes/models/gemma-3-12b-it-4bit mlx-community/gemma-3-12b-it-4bit model-00002-of-00002.safetensors "Moving video text encoder: Gemma 3 12B 4-bit (~8 GB)" \
  --revision 86cc6a8dedbc456dd0e4af01a9d09f396f77e558
model_cache mflux-community/flux2-klein-4b-mflux-q4 "Pictures: FLUX.2 klein 4B q4 (~9 GB)"
model_cache mlx-community/whisper-large-v3-turbo "Song check: Whisper large-v3 turbo (~1.5 GB)"
model_cache mlx-community/parakeet-tdt-0.6b-v2 "Song check: Parakeet TDT 0.6B (~2.5 GB)"

if [ -f spikes/vendor/ACE-Step-1.5/checkpoints/acestep-v15-turbo/model.safetensors ]; then ok "Songs: ACE-Step 1.5 turbo (~9.5 GB)"
elif [ $CHECK = 1 ] || [ ! -d spikes/vendor/ACE-Step-1.5 ]; then miss "Songs: ACE-Step 1.5 turbo (~9.5 GB)"
else (cd spikes/vendor/ACE-Step-1.5 && uv run acestep-download) && ok "Songs: ACE-Step 1.5 turbo"; fi

SEP=spikes/envs/sep/pretrained_models
if [ -d $SEP/2stems ]; then ok "Vocal splitter: Spleeter 2 stems"
elif [ $CHECK = 1 ]; then miss "Vocal splitter: Spleeter 2 stems"
else mkdir -p $SEP/2stems && curl -fsSL "$SPLEETER_URL" -o $SEP/2stems.tar.gz && tar -xzf $SEP/2stems.tar.gz -C $SEP/2stems && ok "Vocal splitter: Spleeter 2 stems"; fi

if [ $WRITER = 1 ]; then
  if ollama list 2>/dev/null | grep -q "^$WRITER_MODEL "; then ok "Story helper: $WRITER_MODEL in Ollama (18 GB)"
  elif [ $CHECK = 1 ]; then miss "Story helper: $WRITER_MODEL (optional: ollama pull $WRITER_MODEL)"
  else ollama pull $WRITER_MODEL && ok "Story helper: $WRITER_MODEL"; fi
fi

# ---------------------------------------------------------------- done
echo
if [ $missing = 0 ]; then
  print -P "%F{green}All set.%f Start the studio with:  npm run studio"
elif [ $CHECK = 1 ]; then
  echo "$missing missing. Run  npm run setup:engines  to fetch them."
else
  echo "$missing step(s) failed (see above). Fix them and run this again; finished parts are skipped."
  exit 1
fi
