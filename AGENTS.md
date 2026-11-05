# Working on Rhymeworks

Notes for anyone changing the code, human or coding agent. The user guide is [README.md](README.md); this file is
about how the code fits together and the rules that keep the videos good.

Rhymeworks turns a song idea into an original kids' song video entirely on a Mac with Apple Silicon: song (ACE-Step),
keyframes (FLUX.2 klein), moving clips (LTX-2.3), assembly and upload pack (ffmpeg, CoreText). A person only *chooses*
at review gates; everything else is automated.

## Where things live (`pipeline/kidzone/paths.py`)

| | What | Where |
|---|---|---|
| **CODE** | this repo: engine, tools, web app, templates. Public, never personal content | the clone |
| **HOME** | the content folder: `episodes/`, `assets/` (registry, cast, props, scenes, brand, voices), `library/`, `briefs/`, `projects.toml` | `$RHYMEWORKS_HOME`, else `home` in `rhymeworks.local.toml` (gitignored), else the legacy layout (content inside the repo), else `~/Rhymeworks` |
| **STATE** | this computer only, never synced: `studio.db`, `logs/`, `drafts/`, `lan_key` | `$RHYMEWORKS_STATE`, else `<repo>/studio/` (gitignored) |

- Code must use `paths.*` (`EPISODES`, `ASSETS`, `REGISTRY`, `DRAFTS`, `find_spec()` …), never `ROOT / "episodes"`.
  `CODE` is only for code, tools, environments and models.
- `kidzone home [--set DIR]` shows or sets HOME (a new one is filled from `templates/home/`); `kidzone migrate --to DIR`
  moves content out of a legacy repo (refuses to overwrite).
- Channel text (tag, subscribe line, playlists) comes from `projects.toml` via `paths.projects()`; an episode without
  `project` belongs to `paths.default_project()` (the first one). Never hard-code a channel.
- A library draft may use a photo reference of an adult only with `"adult_consent": true` in draft.json; never children.
- Brand tools shared by every channel: `pipeline/tools/brand/` (`text.swift` CoreText lettering, `add_intro.sh`, Baloo 2
  font, OFL). A channel's own intro and icon are optional content in `HOME/assets/brand/`; packaging skips them when missing.

## How things run

- **Setup**: `npm run setup` = `scripts/setup-engines.sh`: checks tools, clones the engines at pinned commits into
  `spikes/vendor/`, syncs the uv environments, installs the web app, downloads the models (LTX-2.3 + Gemma 3 at pinned
  revisions into `spikes/models/`; FLUX.2, Whisper and Parakeet into the Hugging Face cache; ACE-Step via
  `acestep-download`; Spleeter 2 stems; `ollama pull gemma4:26b` unless `--skip-writer`). `npm run doctor` = `--check`.
  The `sep` environment pins spleeter 2.4.2 with uv overrides (tensorflow 2.15.1 etc.) because spleeter's own
  tensorflow 2.12 pin has no arm64 wheel. Tools always run offline (`HF_HUB_OFFLINE=1`).
- **Python environments (uv)**: `pipeline` (kidzone CLI, studio API), `spikes/envs/image` (mflux, Pillow),
  `spikes/envs/audio` (melody guide, Whisper, Parakeet, loudness, librosa), `spikes/envs/sep` (Spleeter; needs
  `MODEL_PATH=spikes/envs/sep/pretrained_models`). The engines have their own: `spikes/vendor/ltx-2-mlx`,
  `spikes/vendor/ACE-Step-1.5`. Don't move `spikes/`: uv environments hold absolute paths.
- **Pictures**: FLUX.2 klein 4B q4 via `mflux-generate-flux2[-edit]` (`--model mflux-community/flux2-klein-4b-mflux-q4 --base-model flux2-klein-4b`).
- **Video**: LTX-2.3 distilled q4: `cd spikes/vendor/ltx-2-mlx && uv run ltx-2-mlx generate|a2v --distilled --model
  spikes/models/ltx-2.3-mlx-q4 --gemma spikes/models/gemma-3-12b-it-4bit -W 1280 -H 720 --frame-rate 24` (frames = 8k+1),
  with `AGX_RELAX_CDM_CTXSTORE_TIMEOUT=1 HF_HUB_OFFLINE=1`. **1280×720 is the standard**: `--distilled` draws at half
  size and upscales 2×, so 1024×576 is soft; 720p ≈ 8 min per shot; 1920×1088 was only slightly sharper for 3.6× the time.
- **Songs**: ACE-Step 1.5 turbo through its local API server (started on demand on :8001). Traditional tunes:
  `pipeline/tools/melody_guide.py` spec → ACE "cover" at strength 0.75. Hindi in cover mode fails after verse 1;
  original Hindi songs in normal mode work.
- **Episodes**: `HOME/episodes/<slug>/episode.toml` + `uv run --project pipeline kidzone pixar <episode> --phase
  keys|clips|assemble|package` (engine `pipeline/kidzone/pixar.py`; assets described once in `assets/registry.toml`;
  starter `templates/episode.toml`). Prompt tokens `{asha}` expand to the registry `ref` + "(second image)" and attach
  the image. Resumable; `--redo s05`, `--only`, `--dry-run`, `--plan`. Review gates: `keys/contact.jpg`, `clips/contact.jpg`.
- **Studio**: `npm run studio` (`scripts/studio.mjs`, no dependencies) starts the API (`kidzone studio`,
  http://127.0.0.1:8765) and the web app (Vite, http://127.0.0.1:5173, proxies `/api` and `/files`) and opens the
  browser (`NO_OPEN=1` skips it; `API_PORT` / `WEB_PORT` run a second studio, e.g. with another `RHYMEWORKS_HOME` and
  `RHYMEWORKS_STATE`). `npm run studio:lan` also serves the web app on the Wi-Fi and prints a QR code.

## Studio architecture

- **Backend** `pipeline/kidzone/studio/`: FastAPI REST + one SSE stream `/api/events`; SQLite job queue
  (`STATE/studio.db`); the worker runs ONE GPU job at a time as a `kidzone …` subprocess (`worker.command_for`) and
  honours the settings paused / daytime_only (work hours, default 09:00–22:00) / yield_to_ollama. Quick jobs (Director)
  may run outside work hours.
- **Job kinds**: keys / clips / assemble / package (`kidzone pixar`), `options` (`kidzone options <toml> <shot> --n 4`
  → `keys/options/<shot>/<seed>.png`; using one writes its seed and approves it), `draft` (the writer LLM fills empty
  shot prompts; invented tokens become plain words), `director` (`kidzone director <toml> --ask …` proposes field
  changes → `episodes/<slug>/director.json`; nothing changes until Apply), `song` / `master` / `import`
  (`kidzone song`: ACE takes + Whisper scores → Spleeter vocal + polish −14 LUFS + first sung line on a shot boundary;
  import = reuse a mastered song, beat fit over all downbeats (`fit_bar`, never one median beat gap) + Whisper line
  alignment → shots rebuilt on its bar grid), `voice` (30 s sample), `upload` (upload text with LLM title, intro and
  tags + exact chapters and lyrics; thumbnails lettered with `text.swift`), `asset` (4 FLUX options for a library draft).
- **Review**: decisions → `episodes/<slug>/review.toml`; an approval goes stale when the file changes;
  `status = "published"` episodes count as approved. Redo bumps `seed` (keys) or `clip_seed` (clips) and queues only that shot.
- **Writes are safe**: every `episode.toml` / `registry.toml` write is format-preserving (comments survive) and
  validated by loading it with `pixar.load` before it hits disk (`studio/shotlist.py`, `studio/specedit.py`).
- **Phone lock** (`studio/lock.py`): loopback is trusted; other clients need the `rw_key` cookie set by the QR link
  `/api/unlock?k=…`; `POST /api/lan/reset` (this Mac only) changes the key; the Host must be loopback; unsafe methods
  need `Origin` = the address the browser used. Vite proxies with `xfwd` so the API sees the real client.
- **Frontend** `packages/studio/`: React 19 + Vite + TypeScript, hash router, no UI framework, one EventSource hub in
  `src/api.ts`. **Mobile first**: base CSS is the phone (top bar + floating bottom tabs, 44 px targets, one shot at a
  time in review with a fixed Approve/Redo bar, details in bottom sheets); `@media (min-width: 900px)` is the desktop
  sidebar layout; `useIsDesktop()` (`src/components/MobileBars.tsx`) for markup that differs. Media first, near-black.
  Filters persist per list (`useSaved`); shared filter bar `src/components/Filters.tsx`; full screen via
  `src/components/Fullscreen.ts` (real Fullscreen API, else a fixed layer, because iPhone Safari only allows `<video>`
  full screen). The QR encoder `src/lib/qr.js` is our own (dependency-free, shared by the launcher and the app).
- **Animatic / Watch** (`#/episodes/<slug>/watch`): keyframes (Ken Burns) or clips cut to the song in the browser, no
  GPU. The clip player keeps the previous, current and next `<video>` mounted with the keyframe as poster, so cuts never flash black.

## Production rules learned the hard way

- Keyframe style text mentions **only the characters in that shot** (otherwise extra kids or hybrids appear). One
  character per reference image; say "exactly N characters, each once". Never write "the two children": FLUX then
  draws one of them twice. Place each by name ("on the left {a}…, in the middle {b}…, on the right {c}…").
- Motion prompts: avoid "high-five" (LTX invents a partner) and "nobody else enters" (it invites someone). Never give
  one person more hand jobs than hands ("carries the box in both arms and waves" grows a third hand); let them nod or
  smile, or say "holding the box with both hands the whole time".
- Travel must read as travel: keep the camera **still** and let characters cross the frame or run away from it, paired
  with an end key further along. A camera that tracks, dollies or follows makes them run on the spot.
- `end = "same"` only for seated, staying-put shots, never travel. Even then LTX sometimes returns a frozen clip: after
  every clips run, `pipeline/tools/motion_check.py <ep>/clips/s*.mp4` and redo FROZEN ones with a new clip seed.
- Keep vehicles in the mid-distance (an approaching vehicle blurs); never "bouncing / dancing / springing" vehicles
  (they fly). A start + end keyframe pair of the same scene keeps LTX on the rails.
- Seats face the camera with a ceiling grab rail, or kids perch on seat backs.
- Feelings over mouths: shots carry `feel = "…"` (added to key and motion prompts; on non-lip-sync shots the engine
  also says nobody sings or talks, `pixar.NO_SINGING`). Keep `sing = true` for a few key lines.
- Lip-sync: a2v with the Spleeter-isolated vocal, audio start = shot start − 0.167 s.
- FLUX misspells text: **always set lettering with the font**. Pillow (no raqm) and ImageMagick (no harfbuzz) mangle
  Devanagari (हिंदी → हदिी): render Hindi with `text.swift` (CoreText).
- New episodes render at 1280×720; upscale to 1920×1080 (lanczos + light unsharp) for upload; prepend the intro with
  `pipeline/tools/brand/add_intro.sh <intro.mp4> <ep.mp4> <out.mp4>`.

## Rules for changes

- **One heavy model at a time** (32 GB): FLUX edit ≈ 20 GB, LTX ≈ 13 GB at 720p, the writer LLM 18 GB. All GPU work
  goes through the queue; tools wait for Ollama to unload before loading a model.
- Only models whose licence allows **commercial use of outputs**, and no gated downloads (no account needed).
- Only original or public-domain songs; never reproduce copyrighted lyrics.
- npm, not pnpm. Mobile first for every screen.
- Shell safety: never `rm` with an unguarded `$VAR` path; use literal paths or `"${VAR:?}"`.
- Keep README.md (the user guide) in step with features.

## Tests

`npm test` = `uv run --project pipeline --with pytest --with httpx pytest -q pipeline/tests` + `tsc`. Tests use a
neutral fixture registry (`pipeline/tests/fixtures/registry.toml`); tests that need a particular episode skip when it
isn't in HOME. The lock tests use a small app with the same middleware (importing `studio.app` would open the real database).

## Repo map

| Path | What |
|---|---|
| `pipeline/kidzone/` | CLI (`cli.py`), paths, the episode engine (`pixar.py`), songs (`songmaker.py`), library (`assetmaker.py`), writer / director / options, upload pack |
| `pipeline/kidzone/studio/` | API (`app.py`), queue (`store.py`), worker, review, validated writers (`shotlist.py`, `specedit.py`), phone lock |
| `pipeline/tools/` | melody guide, mastering and polish, vocal split, song scoring, motion check, `brand/` |
| `packages/studio/` | the studio web app |
| `scripts/` | `studio.mjs` launcher, `setup-engines.sh` |
| `templates/` | `episode.toml` starter, `home/` starter content folder |
| `spikes/` | engines, models, environments (only `pyproject.toml` / `uv.lock` and early benchmark scripts are in git) |
| `pipeline/kidzone/stages/`, `packages/compositions/` | the earlier 2D pipeline (Remotion; `kidzone run <brief.json>`), still working |
| `PLAN.md` | the original plan for the 2D pipeline (partly superseded) |
