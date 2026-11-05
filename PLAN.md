# Kidzone — Build Plan (v2)

_Status: revised after independent review · 2026-10-31_

## 0. Goal & hard constraints

**Goal:** one formatted prompt (`EpisodeBrief`, written by the user with another AI) → an original kids' educational **song video** in **English and Hindi** → published on **YouTube** (monetization intended).

| Constraint | Implication |
|---|---|
| Zero manual work; human only *chooses* | Every stage automated; choice gates + Autopilot. **Upload is manual by decision** (content quality first); API publishing deferred to Phase 4. Copyright-check confirmation in Studio stays manual (no API for it) |
| MacBook M2 Max, **32 GB unified RAM**, ~400 GB free disk | One heavy model process at a time; no local AI video generation |
| Local-first, cost-effective | Open-weight models on MLX/MPS; cloud only as optional fallback |
| YouTube publication | Every model/asset must permit **commercial use of outputs**; must survive *inauthentic content* + *Made for Kids* scrutiny |
| No photos/videos of the user's kids | All characters generated; references from curated presets / openly-licensed search |
| English first, Hindi required | Shared line skeleton across languages; per-language song, timing, render |

Environment: Python 3.14 (system → use uv-managed 3.12), Node 24, pnpm 10, ffmpeg 8.1, Ollama 0.34 (`qwen3:30b`, `qwen3-vl:8b`, `gpt-oss:20b` [reserved — do not remove], `qwen3:8b`, `llama3.2:3b`).

## 1. Core idea

**AI generates *assets* once; code does *animation* every time.** Limited animation (pose swaps + **procedural vector mouths** + camera moves + beat-synced motion) composed in Remotion from one source of truth, `episode.json`. Rendering is deterministic and free; AI generation is cached and reused via a recurring-cast library.

## 2. Architecture

```
kidzone/
├─ pipeline/                 Python (uv, 3.12) — CLI orchestrator + model workers
│  ├─ kidzone/stages/        brief, write, style, character, poses, song, align, mouth, beats, scenes, master, render, package, publish
│  └─ kidzone/workers/       one subprocess per model family (memory freed on exit)
├─ packages/compositions/    Remotion compositions (renderer now, studio Player later)
├─ apps/picker/              Phase 1: one static gate page (candidate grids)
├─ apps/studio/              Phase 3: Nover-style studio
├─ library/                  shows/, characters/ (poses + mouth anchors), styles/, mouth-sets/
└─ episodes/<slug>/          brief.json, episode.json, assets/, audio/, renders/, package/, license.json
```

- Stages idempotent, content-hash cached, resumable.
- **Memory governor:** exactly one heavy worker at a time; Ollama `keep_alive: 0` **and** poll `ollama ps` until unloaded before starting the next worker.
- Gates emit N candidates; Autopilot picks the top-scored one.

## Phase 0 outcome (2026-10-31) — see `spikes/RESULTS.md`

Writer + vision = **Gemma 4 26B**; images + poses = **FLUX.2 klein 4B q4 (mflux)**; songs = **ACE-Step 1.5 turbo + LM 1.7B**; alignment = **stable-ts + MLX Whisper**; mouth = loudness envelope → SVG; render = Remotion. ComfyUI, Demucs/SAM Audio, Qwen-Image(-Edit) not needed for MVP. Hindi = provisional GO (Devanagari lyrics, 4–6 takes, human listen). ~20 min/episode (new cast), ~10 min (cached cast).

## 3. Pipeline (MVP path in **bold**)

| # | Stage | Tool / model (license) | Notes |
|---|---|---|---|
| 1 | **Brief** | Pydantic schema, published as JSON Schema | Optional `lyrics.en` / `lyrics.hi` — user's cloud AI may write them (better Hindi meter) |
| 2 | **Write** | Ollama `qwen3:30b` (Apache-2.0), structured JSON output | Fills missing lyrics; storyboard from a **fixed action vocabulary**; **shared section/line-id skeleton across EN/HI** with syllable targets per line from tempo |
| 3 | **Style** ◆ | Curated style presets (flat-vector friendly) rendered as 4 samples | Phase 2: Openverse mood boards (CC0/BY; licenses unverified by Openverse → inspiration only) |
| 4 | **Character** ◆ | Default image model chosen in Phase 0 from **Z-Image-Turbo (Apache-2.0)**, **FLUX.2 klein 4B (Apache-2.0)**, Qwen-Image 4-bit/Lightning (Apache-2.0) | 4 candidates, neutral closed mouth, flat style |
| 4b | **Poses** | Qwen-Image-Edit (Apache-2.0) or equivalent | 3–4 body poses only; identity judged at the gate |
| 4c | **Cutouts + anchors** | BiRefNet (MIT); mouth/eye anchor via `qwen3-vl:8b` bbox | Stored once per pose in library |
| 4d | **Mouths** | **Procedural SVG mouth set per style** (code, no AI) | Perfect identity, frame-exact; colors sampled from character |
| 5 | **Song** ◆ | ACE-Step 1.5 (MIT; MLX) | 3 takes; auto-score EN by WER, **HI by CER on normalized Devanagari**; fallback: spoken/chant HI version or paid service (terms into license.json) |
| 6 | **Align** | stable-ts align (MIT) | **Line-level by default**, word-level when confident; per-language retiming of shots |
| 7 | **Mouth motion** | **Vocal loudness envelope → 3–4 mouth states** | Language-agnostic; Rhubarb (MIT) = later upgrade. Vocal stem via ACE-Step vocal output if available, else **Meta SAM Audio** (SAM License, commercial OK w/ restrictions; gated) — replaces Demucs (weights license unresolved) |
| 8 | **Beats** | librosa (ISC) | Bounce, cuts, transitions |
| 9 | **Scenes/props** | Same image model as #4 | Reuse from library |
| 10 | **Master** | ffmpeg loudnorm → −14 LUFS | Mix VO/SFX when added |
| 11 | **Render** | Remotion (free ≤3-person co./individual) | 1920×1080 30fps, SRT captions; Devanagari karaoke highlighting **per word (grapheme-cluster safe)** with Noto Sans Devanagari |
| 12 | **Thumbnail** | Remotion still from pose + title | |
| 13 | **Package** | — | `mp4, srt, thumbnail.png, metadata.json, license.json` ready for Studio upload |
| 14 | Publish (Phase 4) | YouTube Data API v3 | Only after audit passes; `selfDeclaredMadeForKids=true`; `containsSyntheticMedia` per-show config (cartoons generally not required); `thumbnails.set` needs phone-verified channel |
| 15 | QA (Phase 2) | LLM checklist (YouTube Kids quality principles) + `qwen3-vl:8b` on sampled frames + originality check vs past episodes | Fail → reason → re-run stage |
| 16 | SFX / narration (Phase 2) | Freesound CC0; Kokoro (Apache-2.0, espeak-ng GPL dep, weak HI voices) | Stable Audio Open only if Community License terms acceptable |

`license.json` per episode records every model, asset and license.

## 4. Data contracts

- **`EpisodeBrief`**: `show_id`, `topic`, `learning_goal`, `age_band`, `languages`, `duration_sec`, `cast`, `style`, `song {mood, tempo_bpm?, genre}`, `repetition_level`, `lyrics? {en, hi}`, `must_include`, `avoid`, `autopilot`.
- **`episode.json`**: `sections[] → lines[] (id shared across languages)`; per-language `text`, timings, mouth track; `shots[]` bound to line ids (re-timed per language); characters/action/pose/camera; metadata per language.

## 5. Studio UI (Phase 3) — Nover-style

Observed in Nover's editor: dark theme; infinite **node canvas** (image frames + pill "controller" nodes, blue bezier wires); left **outline tree**; right **properties panel**; top bar (breadcrumb, tools, blue **Render**); floating bottom toolbar (add/select/pan/comment/zoom); contextual floating toolbars.

Mapping: canvas = episode pipeline graph (nodes show status/outputs; gate nodes expand to candidate grids) · outline = Episodes → Scenes → Shots + Library · properties = selected node/shot/character, re-run · Remotion Player with EN/HI toggle. Stack: React + TS, shadcn/ui, Tailwind, @xyflow/react, @remotion/player, TanStack Query; FastAPI + SSE introduced here (not before). Vite vs Next.js decided at Phase 3.

## 6. Phases & exit criteria

**Phase 0 — Feasibility spikes** (YouTube API groundwork deferred to Phase 4; uploads are manual)
1. **Writer bake-off:** `qwen3:30b` vs `gemma4` (Apache-2.0, strong multilingual) vs `gpt-oss:20b` on EN + HI lyrics (meter, rhyme, line skeleton) and storyboard JSON validity.
2. Benchmark Z-Image-Turbo, FLUX.2 klein 4B, Qwen-Image (4-bit/Lightning) via mflux: sec/image + **peak RAM** at 768² and 1024² → pick default.
3. Pose edits: 3 poses on one character; identity by eye.
4. ACE-Step 1.5: 3 takes × EN + HI 60 s songs (Devanagari vs romanized); WER/CER + listening → **Hindi go/no-go**. Score HI with **Meta Omnilingual ASR** (Apache-2.0) vs Whisper; EN with Whisper vs NVIDIA Parakeet (CC-BY-4.0). If ACE-Step disappoints, try YuE2 / DiffRhythm 2 (verify licenses + Mac support first).
5. stable-ts line alignment on EN + HI; loudness-envelope mouth prototype in Remotion.
6. Licenses doc from primary sources (incl. Demucs decision).
- Exit: measured timing/RAM table + go/fallback per stage.

**Phase 1 — English CLI MVP:** `kidzone run brief.json` → write → style ◆ → character ◆ → poses + cutouts → song ◆ → align → envelope mouths → beats → backgrounds → render → loudnorm → package. Static picker page for gates; Autopilot available. No Openverse, SFX, narration, VLM QA, originality check yet.
- Exit: 60–90 s episode end-to-end with no edits besides picks; target < 2 h cold, < 20 min with cached cast.

**Phase 2 — Hindi + quality:** Hindi full path (only if spike passed; else fallback), QA + originality gates, Openverse references, SFX, library reuse, cache cleanup policy. Experiments: **SAM 3** (MLX port exists) to split characters into body parts for puppet rigs (arm waves, head tilts); **Meta Animated Drawings** (MIT) for skeleton-driven dance/walk cycles on generated characters; **Indic Parler-TTS** (AI4Bharat, reportedly Apache-2.0) for Hindi narration; **SoulX-Singer** (Apache-2.0) as melody-controlled singing alternative.

**Phase 3 — Studio UI** (Nover-style, on top of FastAPI). **Plus 3D experiment:** a Blender renderer driven by the same `episode.json` (keep it renderer-agnostic). Characters built procedurally from primitives + toon shading (LLM-authored character spec → Blender builder, rig comes free), mouth via shape keys from the envelope track. Render the 2D look-dev scene in 3D and compare. Image-to-3D models (TRELLIS, Hunyuan3D, SAM 3D) skipped — CUDA-only and/or license-restricted. Budget ~30–90 min render per 2-min episode per language.

**Phase 4 — API publishing** once audit passes; until then the package is uploaded in Studio.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Image gen hours/episode (Qwen-Image ~4 min/img; 8-bit doesn't fit 32 GB) | Smaller Apache models, 768² drafts, upscale chosen only, procedural mouths remove most edits, cast reuse |
| Unaudited API uploads are **permanently locked private** | No API uploads before audit; Studio upload of package |
| OAuth "Testing" refresh tokens expire in 7 days | Consent screen In production |
| Content ID status not available via API | Manual "checks complete" confirmation before public |
| ACE-Step Hindi weak | Spike go/no-go; fallback paths defined |
| Singing lip-sync/alignment noisy | Envelope mouths; line-level alignment |
| Hindi meter from local LLM weak | Lyrics optionally supplied in brief; shared line skeleton with syllable targets |
| Demonetization (template/inauthentic; Made-for-Kids low RPM; YPP thresholds) | Recurring cast with personalities, explicit variety levers (structure, setting, song form), cadence cap, QA + originality gates |
| 32 GB pressure | One worker at a time, verified unload |
| Python 3.14 incompat | uv 3.12 envs |

## 8. Evaluated and rejected (for now)

| Model | Why not |
|---|---|
| Meta MusicGen / AudioGen | Weights CC-BY-NC; instrumental only |
| Meta MMS (forced alignment), SeamlessM4T | Non-commercial licenses |
| Meta Llama 4 | Smallest is 109B MoE — doesn't fit 32 GB |
| xAI Grok 2.5 | Restrictive license, hundreds of GB |
| Microsoft VibeVoice | License contested (MIT withdrawn) |
| Tencent SongGeneration / LeVo 2 | Custom license, no Hindi |
| FLUX.2 klein 9B / dev | FLUX Non-Commercial License (4B is Apache-2.0 → candidate) |
| NVIDIA Cosmos | Robotics/world video models; too heavy, off-target |
| NVIDIA Audio2Face-3D | Commercial OK (NVIDIA Open Model License) but for 3D faces — revisit if a 3D style is added |
| Qwen3-TTS | Apache-2.0 but no official Hindi |

## 9. Open decisions

1. Show concept.  2. First episode topic.  3. Hindi fallback if spike fails (spoken/chant vs paid).  4. Vite vs Next.js (Phase 3).  5. Same vs separate Hindi channel.
