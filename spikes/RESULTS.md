# Phase 0 — Results

_Hardware: M2 Max, 32 GB unified RAM. Docker stopped during benchmarks. Started 2026-10-31._

## 1. Writer bake-off (song + storyboard JSON, EN + HI)

Brief: Pip & Paro, counting 1–5 with fruits, ages 2–4, 75 s, 100 BPM, call-and-response. Script: `writer/bakeoff.py`. Raw outputs: `results/writer/`.

| Model | Settings | Wall | Valid JSON | Lines | Syll. gap EN / HI | Verdict |
|---|---|---|---|---|---|---|
| **gemma4:26b** | think off | **42 s** | ✅ | 16 | 0.56 / 2.19 | **Winner.** Most natural, singable Hindi; short toddler lines; minor grammar slips (gender agreement) |
| gpt-oss:20b | reasoning low | 43 s | ✅ | 16 | 1.44 / 5.56 | Hindi off-meter |
| gpt-oss:20b | reasoning medium | 239 s | ✅ | 18 | 0.44 / 3.0 | Good structure, weak rhyme, translated-feeling Hindi |
| qwen3:30b | think off | 15 s | ✅ | 6 | 1.0 / 3.0 | Too short — stops after 2 fruits |
| qwen3:30b | think on | 1722 s | ❌ | — | — | Spent 82k tokens reasoning, never answered |

_Hindi syllable counter is a rough akshara heuristic; treat HI gaps as indicative._

**Decision:** Gemma 4 26B is the default writer. No local model rhymes well → keep optional `lyrics.en/hi` in the brief (user's cloud AI) and a human check of Hindi at the song gate. Prompt needs explicit rhyme scheme + chorus-repeat constraints.

## 2. Image models

Same character prompt (flat-vector preschool robot "Pip"), fixed seeds, pre-quantized 4-bit mflux weights (`mflux-community/*-q4`; full bf16 repos are 24–33 GB and were impractical to download). Script: `image/bench_images.sh`. Sheets: `results/image/*_sheet.png`.

| Model (q4, mflux 0.24) | 768² | 1024² | 4 candidates @1024² | Peak mem Δ | Prompt adherence |
|---|---|---|---|---|---|
| **FLUX.2 klein 4B** (Apache-2.0) | **20 s** | **33 s** | **131 s** | ~8–11 GB | ✅ All 4 on-brief: round robot, teal/orange, antenna bulb, thick outlines; consistent set |
| Z-Image-Turbo (Apache-2.0) | 53 s | 96 s | 497 s | ~8–12 GB | ❌ Drifted: 2 turtle-like, 1 human face, mostly frowning |

**Decision: FLUX.2 klein 4B (q4) is the image model** — 3–4× faster and clearly better on-brief. Qwen-Image 2.1 excluded (reported Qwen Research License = non-commercial). Original Qwen-Image / Qwen-Image-Edit-2511 (Apache-2.0) remain fallbacks; not needed. **ComfyUI not needed** — mflux covers generation + editing natively on MLX.

## 3. Pose edits

FLUX.2 klein 4B edit mode, source = chosen candidate, 3 poses (wave / jump / point). Script: `image/bench_poses.sh`. Sheet: `results/image/poses/poses_sheet.png`.

| Metric | Value |
|---|---|
| Time per pose @1024² | **~75 s** |
| Peak memory | **~28 GB total system** (Δ 16–20 GB) — edit mode is the heaviest step; nothing else may be loaded |
| Identity | ✅ Excellent — same colors, proportions, antenna, blush, line style in all 3 poses |

**Decision: klein edit for poses — GO.** No Qwen-Image-Edit download needed.

## 4. Songs (ACE-Step 1.5)

Setup: ACE-Step 1.5 turbo DiT (2B) + 5Hz LM 1.7B, MLX backend, API server. Same counting song in EN, HI (Devanagari) and HI (romanized), 60 s, 100 BPM, 3 takes each. Script: `song/ace_spike.py`; scoring `asr/score_songs.py` (Whisper large-v3-turbo with loop protection; Parakeet for EN).

| Metric | Value |
|---|---|
| Generation time | 3 × 60 s takes in **~75 s** (≈25 s per song); first request +35 s model load |
| Peak memory | **~19 GB** while generating (LM + DiT + MLX VAE) |
| Server picked LM automatically | 4B (8.4 GB download) → pinned to 1.7B via `ACESTEP_LM_MODEL_PATH`; run with `HF_HUB_OFFLINE=1` |

| Take | EN WER (Whisper / Parakeet) | HI CER (Whisper) |
|---|---|---|
| en_0 | 0.04 / **0.00** | |
| en_1 | 0.04 / 0.04 | |
| en_2 | 0.38 / 0.21 | |
| hi_0 (Devanagari) | | **0.27** |
| hi_1 (Devanagari) | | 1.28 |
| hi_2 (Devanagari) | | 0.89 |
| hi_roman_0/1/2 | | 0.77 / 0.64 / 0.28 |

Findings:
- **English: production-usable.** 2 of 3 takes are near-perfect → generating 3 takes and auto-picking the best works.
- **Hindi: usable but inconsistent.** hi_0 is clearly sung (transcript ≈ lyrics; typical sung g→k slurs). Other takes vary; Whisper also hallucinates loops on Hindi singing, so HI CER over-penalizes. **Human listening at the song gate is required for Hindi.**
- Devanagari lyric input ≥ romanized on average → **write Hindi lyrics in Devanagari**.
- Parakeet is more robust than Whisper for EN scoring.
- **Hindi go/no-go: GO (provisional)** — pending user listening test. Generate 4–6 HI takes per song to raise the odds of a clean one.

## 5. Alignment + mouth track

stable-ts `align` (known lyrics, MLX Whisper — reuses cached weights) + loudness-envelope mouth states. Script: `align/align_and_mouth.py`.

| Take | Lines aligned | Mean word confidence | Time | Peak mem |
|---|---|---|---|---|
| en_0 | **12/12** | 0.90 | 6.6 s | ~5 GB |
| hi_0 | **12/12** | 0.87 | 4.7 s | ~5 GB |

Line timings are plausible (instrumental intros skipped, 2–4 s lines, no overlaps). Mouth open 29% (EN) / 41% (HI) of frames. **Line- and word-level alignment both work for EN and HI — no vocal separation needed for the MVP.**

### 5b. Prototype video (character + procedural mouth + karaoke)

`align/prep_video.py` → `remotion/` (Remotion 4.0.539). Outputs: `results/prototype_en.mp4`, `results/prototype_hi.mp4`, stills `results/still_open.png`, `results/still_hi.png`.

| Step | Result |
|---|---|
| Mouth/eye anchors via vision model | `qwen3-vl:8b` returned empty (reasoning-mode quirk). **`gemma4:26b` worked** (14 s, accurate coords) → Gemma 4 covers both writer + vision |
| Render 60 s @1080p30 | **~23 s**, ~2.3 GB |
| Devanagari karaoke | ✅ Conjuncts, matras, chandrabindu correct; per-word highlight works |
| Known gaps → Phase 1 | White box behind character (add BiRefNet cutout); tiny drawn mouth visible under the animated one (generate characters *without* a mouth); anchor needs a minimum mouth width (applied: 55% of eye spacing) |

## 6. Licenses (verified from Hugging Face model metadata / repos)

| Component | License | Commercial outputs | Login needed |
|---|---|---|---|
| FLUX.2 klein 4B (+ mflux-community q4) | Apache-2.0 | ✅ | No |
| Z-Image-Turbo (not used) | Apache-2.0 | ✅ | No |
| Gemma 4 | Apache-2.0 | ✅ | No (Ollama) |
| ACE-Step 1.5 (code + weights) | MIT | ✅ (output terms not formally documented — see upstream discussion #1256) | No |
| Whisper large-v3-turbo (MLX) | MIT | ✅ | No |
| Parakeet TDT 0.6B v2 | CC-BY-4.0 (attribution) | ✅ | No |
| stable-ts, mflux | MIT | ✅ | — |
| Remotion | Remotion License (free for individuals / ≤3-person companies) | ✅ | — |
| Qwen-Image 2.1 | Qwen Research License (reported) | ❌ excluded | — |
| SAM Audio / SAM 3 (Phase 2+) | SAM License | ✅ w/ restrictions | **Yes — manual approval** |
| Indic Parler-TTS (Phase 2) | Apache-2.0 | ✅ | **Yes — click-through** |

## 7. Summary — go / fallback per stage

| Stage | Decision | Measured |
|---|---|---|
| Writer | ✅ **Gemma 4 26B** (think off) | 42 s / song+storyboard |
| Vision (anchors, QA) | ✅ **Gemma 4 26B** | 14 s / image |
| Character candidates | ✅ **FLUX.2 klein 4B q4** | ~33 s / image @1024² |
| Poses | ✅ **klein 4B edit** | ~75 s / pose |
| Song EN | ✅ **ACE-Step 1.5** turbo + LM 1.7B | ~25 s / 60 s song |
| Song HI | ⚠️ **GO, provisional** — needs listening + 4–6 takes | ~25 s / take |
| Lyric alignment | ✅ **stable-ts + MLX Whisper** (line + word) | ~5 s / song |
| Mouth | ✅ **Loudness envelope → SVG mouth** | instant |
| Render | ✅ **Remotion** | ~23 s / 60 s @1080p |
| Vocal separation | ⏸ Not needed for MVP | — |
| ComfyUI | ❌ Not needed | — |

**Estimated time per episode (both languages, new character):** writer 1 min + 4 candidates 2 min + 3 poses 4 min + ~6 backgrounds 3.5 min + EN 3 takes 1.5 min + HI 6 takes 2.5 min + align/anchors 1 min + 2 renders 1 min + model loads ~3 min ≈ **~20 min**. **With a cached cast: ~10 min.** Well under the 2 h / 20 min targets.

**Memory rule confirmed:** heaviest steps are pose edits (~28 GB system peak) and ACE-Step (~19 GB Δ) → strictly one heavy model at a time; Docker must be stopped during generation.

**Operational lessons:** pin ACE-Step LM path + run offline; download pre-quantized weights; disable reasoning on Ollama models; Whisper needs `condition_on_previous_text=False` on singing; xet downloads under-report in `du`.
