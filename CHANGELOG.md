# Changelog

## v0.12.7 — Single-source path: keep diarized in-room speakers

### Fixed

* **Second collapse in the single-source fallback.**  v0.12.6 routed in-room
  recordings to the mono path, which correctly diarized two in-room speakers —
  but the mono path then remapped the diarized speakers onto YOU/REMOTE by
  channel energy.  On dual-mono audio every speaker is equally "mic-dominant",
  so that remap collapsed the genuine speakers back into one.  The mono path
  now **skips** the channel-energy YOU/REMOTE relabeling (and the channel
  correction) when the recording was detected as single-source, keeping the
  pyannote diarization result (`SPEAKER_00`/`SPEAKER_01`/…) so voiceprint
  naming can label each in-room speaker.

## v0.12.6 — Fix in-room multi-speaker collapse in the dual-diarize path

### Fixed

* **Multiple in-room speakers on the mic channel collapsed into one.**  The
  default `dual-diarize` path assumes the mic (left) channel carries a single
  local speaker (labeled `YOU`) and only diarizes the system (right) channel.
  For an **in-room recording** — several people sharing one mic, with the
  system channel silent or merely a duplicate of the mic — every mic speaker
  was therefore merged into a single speaker.  The pipeline now detects this
  single-source case and falls back to the mono path (mix down + diarize the
  combined signal), which splits the in-room speakers correctly.  Genuine
  remote calls (an active, distinct system channel) are unaffected and keep
  using `dual-diarize`.

### Added

* `--single-source-fallback` / `--no-single-source-fallback` (default on) and
  `TranscriptionConfig.single_source_fallback`.  Detection thresholds are
  tunable via `system_inactive_rms_ratio` (default 0.10) and
  `channel_duplicate_corr` (default 0.98).  New helpers
  `_is_single_source_stereo` + `_load_stereo_int16`.

### Notes

* Single-source is detected when the system channel's active-sample RMS is
  below `system_inactive_rms_ratio` of the mic channel's, OR the two channels'
  Pearson correlation is at/above `channel_duplicate_corr`.  Conservative on
  analysis failure (keeps `dual-diarize`), so remote calls are never
  mis-routed.

## v0.12.5 — Title-aware schedule matching + collision guard for sync

### Fixed

* **Title-aware schedule matching.**  `detect_meeting_type` now considers the
  session `title` (when present in `*.session.json`).  A *titled* session only
  auto-matches a scheduled meeting whose `name`/`folder` slug equals the
  title's slug; otherwise it returns `None` so the caller files it under its
  own folder.  This stops an ad-hoc meeting recorded *inside* a schedule
  window (e.g. a "post-scrum" at 09:03 inside the 06:30–09:30 standup window)
  from being misfiled as the scheduled meeting.  **Untitled sessions keep the
  prior pure time-window behavior** (back-compat — existing scheduled-meeting
  workflows are unchanged).

* **Collision guard: never silently overwrite a different meeting.**
  `sync_session` writes a small local-only `.session-id` marker into each
  synced folder and, before reusing a dated folder, checks it.  If an existing
  folder belongs to a *different* session, the new meeting is filed into a
  disambiguated folder (`<folder>-<sessionid-suffix>`) instead of clobbering
  the existing one.  Previously two meetings that resolved to the same folder
  (e.g. two ad-hoc meetings in one schedule window) overwrote each other.

### Notes

* The `.session-id` marker is kept strictly local: it is registered in the
  clone's `.git/info/exclude`, so it is never committed/pushed and never trips
  the "uncommitted changes" sync guard.
* Pairs with vezir v0.7.16, which injects the session `title` into
  `*.session.json` (so the title-aware matching above can engage) and adds an
  explicit "sync as" folder override.

## v0.12.4 — Robust language detection + sync exit-code

### Changed

* **Multi-window language detection.**  whisperx detected language from only
  the first ~30 s of each channel, so a misleading opener (e.g. an opening
  "Gracias") mislabeled an English meeting as Spanish even after the
  dominant-channel fix.  Now samples N windows across each channel via
  faster-whisper's `detect_language(language_detection_segments=N)`
  (whisperx backend; `--language-detection-segments`, default 6).
* **Soft default-language bias.**  `--default-language <lang>` keeps the team
  default unless a channel confidently detects another language
  (≥ `default_language_override_confidence`, default 0.70); fed into
  dominant-channel selection.

### Fixed

* **`millet sync` exit code.**  `cli/sync.py` now raises `SystemExit(1)` when
  any session fails (e.g. git push rejected) instead of exiting 0 — callers
  no longer have to scrape the log to notice a failed sync.

## v0.12.3 — Summary language from the dominant channel + per-language summaries

### Fixed

* **Summary/transcript language now follows the channel with the most
  speech** (`_dominant_channel_language`; mic wins exact ties).  Previously
  the dual-channel paths took the language from the mic channel only, so a
  local speaker's minority-language asides made the whole summary that
  language.  Each channel is also word-aligned with its OWN detected language
  (`_align_channel`) instead of sharing the mic's model.

### Added

* `apply_labels` gains `summary_language`: regenerate the summary in a chosen
  language and save it as an ADDITIONAL `<base>.summary.<lang>.md` (with
  suffixed meta/frontmatter sidecars), preserving the primary auto-detected
  summary.  `MeetingSummary.save` gains `lang_suffix`.
* `sync`: `<base>.summary.<lang>.md` syncs as a distinct `summary.<lang>.md`;
  `.frontmatter.json` is excluded (also fixes a latent collision).

## v0.12.2 — Suppress phantom remote speakers in dual-diarize

### Fixed

* pyannote can over-segment a single remote stream into multiple clusters
  (peeling short backchannel "yeah/cool" off the main speaker into a
  phantom), which voiceprint matching then mis-named from a weak,
  barely-over-threshold match.
  * **Voiceprint auto-apply gate**: a match at/above `MATCH_THRESHOLD` is
    applied only if it has enough embeddable speech AND is unambiguous
    (strong absolute confidence OR a clear margin over the runner-up).
    `SpeakerMatch` gains `evidence_seconds` + `margin`; weak/ambiguous
    matches stay raw and route to `needs_labeling` instead of confidently
    mislabeling.  The sidecar records only applied matches.
  * **Remote-cluster consolidation** (dual-diarize): merge same-speaker
    clusters (cosine ≥ `cluster_merge_similarity`) and absorb thin clusters
    (< `cluster_min_speech_seconds`) into the dominant remote.

## v0.12.1 — Fix auto-label discarding matches in non-interactive runs

### Fixed

* **`label --auto` aborted (and discarded all matches) when any speaker was
  unmatched in a non-interactive context.**  After auto-applying confident
  voiceprint matches, the command unconditionally prompted for unrecognized
  speakers; in a worker/batch context (no TTY) `click.prompt` hit EOF and
  raised `Abort`, so the already-collected confident matches were never
  written.  Now: when stdin is not a TTY, skip the prompt — apply the
  auto-matches and leave unmatched speakers as their raw `SPEAKER_N` ids
  (the documented "unknowns remain as REMOTE_N" behavior).  This is the bug
  that left fully-recognizable meetings stuck in `needs_labeling` with raw
  speaker ids.

### Added

* **`*.autoid.json` sidecar** written by `label --auto`: records each
  auto-matched speaker's name + confidence, keyed by the final transcript
  speaker id.  Lets downstream UIs (vezir's labeling screen) pre-fill
  recognized names and show match confidence.  Excluded from `millet sync`
  pushes and from transcript-file resolution.

## v0.12.0 — Dual-diarize: per-channel transcription + remote speaker diarization

New default for stereo recordings (`--mixdown dual-diarize`).  Transcribes the
mic and system channels **separately** — Kemal's mic stream is captured as a
continuous "YOU" source immune to overlap with remote speakers — then runs
**pyannote diarization on the system channel only** to split distinct remote
speakers (Openoms, Jonas, Max, …).  Downstream voiceprint naming maps each
SPEAKER_N to a real name, exactly as before.

This eliminates the **overlap-fragmentation** problem of the mono path, where
WhisperX's word timestamps during overlapping speech caused words to flicker
between speakers ("This year" → Openoms, "they" → Kemal, "rented the" →
Openoms, "whole island" → Kemal — when Kemal said the entire sentence).
Overlapping segments from different channels are **preserved**, not
serialized.

### Added

* **`--mixdown dual-diarize`** (now the **default** for stereo): dual-channel
  ASR + system-channel diarization.  `mono` and `dual` remain available via
  the flag.
* **Channel-energy correction** (mono path, `--channel-correct`): per-segment
  and per-word mic/(mic+sys) RMS reassignment for turn-boundary leaks.  On by
  default when `--mixdown mono` is used; includes `--channel-correct-margin`
  (default 0.30) for tuning.  Mixed segments are split at word-speaker
  boundaries.  11 new tests.
* **DNS-retry hardening** for `millet sync` git operations (clone/pull/push):
  transient DNS failures auto-retry up to 5× with backoff instead of aborting.

### Notes

* 2× ASR cost (both channels transcribed); still fast on GPU — a 62-minute
  meeting completes in ~3 minutes on a 3090.
* Diarization on the isolated system channel produces a **cleaner speaker
  signal** (no local mic bleed), improving remote-speaker clustering.
* Minor over-segmentation of single-remote meetings (pyannote may split one
  person into 2–3 clusters); voiceprint matching merges them.
* Validated on DEVSTANDUP (5 speakers), LUKAS_2 (2 speakers), AB_BOARD (4
  speakers, .ogg): the known overlap-fragmentation is eliminated and all
  distinct remote speakers are preserved.

## v0.11.0 — Parakeet ASR backend (opt-in, English, ONNX)

Adds a third ASR backend alongside `whisperx` and `mlx`: **NVIDIA Parakeet
TDT** via [onnx-asr](https://github.com/istupakov/onnx-asr) (ONNX Runtime,
pure-Python — no extra torch/transformers).  Opt-in only; `auto` selection is
unchanged.  Intended for benchmarking against the WhisperX default on English
meetings before any default change.

### Added

* **`--asr-backend parakeet`** (`millet transcribe`).  Uses the English
  `nemo-parakeet-tdt-0.6b-v2` model by default; override with
  `--parakeet-model`.  Long audio is automatically chunked through onnx-asr's
  Silero VAD adapter (Parakeet's per-utterance limit is ~20-30 s), with
  global timestamps stitched back.  Emits the same WhisperX-shaped result
  dict the other backends produce, so alignment / diarization / dual-channel
  labeling downstream are unchanged.
* **Alignment toggle for Parakeet** — `--parakeet-keep-alignment`:
  * default (config "B"): trust Parakeet's native VAD-segment timestamps
    (skips WhisperX wav2vec2 alignment; faster).
  * with the flag (config "C"): run WhisperX alignment on top of Parakeet
    text for word-level timestamps.
  This exists so the ASR benchmark can measure B vs C and pick a default.
* **`millet download parakeet`** — explicit, lazy fetch of the Parakeet +
  Silero VAD ONNX weights into the HF cache (mirrors `millet download <lang>`
  for alignment models).  Never auto-downloads inside `transcribe`.
* **`millet-pipeline[parakeet]` optional extra** — pulls `onnx-asr[hub]`
  (numpy + onnxruntime + huggingface-hub only).  For CUDA, install
  `onnxruntime-gpu` on the GPU host.
* **`scripts/bench_asr.py`** — benchmark harness comparing configs A
  (whisperx) / B (parakeet native ts) / C (parakeet + alignment): reports
  RTFx, wall time, segment/speaker counts, and dumps transcripts for
  side-by-side human comparison.  WER-vs-stored-transcripts is intentionally
  not computed (those are themselves Whisper output).
* `millet/parakeet.py` module + `tests/test_parakeet.py` (12 tests: contract
  shape, config B/C wiring, backend validation, dispatch, availability guard).

### Notes

* `auto` deliberately never selects Parakeet; it remains opt-in pending
  benchmark data (English-only, separate timestamp behavior).
* Parakeet v2 is English-only; multilingual v3 (`nemo-parakeet-tdt-0.6b-v3`)
  is reachable via `--parakeet-model` but is not the benchmark target.

## v0.10.0 — tech-debt sweep: import-bug fix, CI, ruff, cli.py split

Code-health release.  No user-facing behavior change; minor bump because
the internal `cli.py` module became a `cli/` package.

### Fixed

* **Latent clean-install crash**: `millet/{capture,audio,utils,languages}.py`
  shims imported `from meet_record.*` (the pre-rename package).  On a
  clean `pip install millet-pipeline` (which depends on `millet-record`,
  providing `millet_record`) every shim raised
  `ModuleNotFoundError: meet_record`.  It only worked where the legacy
  `meetscribe-record` happened to be co-installed.  Now they import
  `from millet_record.*`.  `voiceprint.py` likewise switched its lazy
  `from meet.* import` to `from millet.*` (and dropped two unused
  imports).  New `tests/test_shim_imports.py` guards against regression.

### Changed

* **`cli.py` (1929 lines) split into a `cli/` package**: one module per
  command (`transcribe`, `run`, `download`, `translate`, `label`,
  `enroll`, `sync`, `gui`, `ingest`) + a shared `cli/_helpers.py`, with
  `cli/__init__.py` defining the `main` group and re-exporting every
  command symbol so the `millet.subcommands` / `meet.subcommands` entry
  points (`millet.cli:transcribe` etc.) keep resolving.
* **CI fixed**: the workflow linted/tested dead `meet/` paths (package is
  `millet/`) and installed `meetscribe-record` (old PyPI name).  Now
  lints the full `millet/` + `tests/` tree, installs `millet-record`,
  and runs the no-torch/no-GTK test suites.
* **Ruff config added** (`[tool.ruff]`, mirroring vezir's
  `E,F,W,I,B,UP,RUF` ruleset) and the tree cleaned up (≈120 findings:
  unused imports, `raise ... from`, import sorting, etc.).
* Legacy `meet.*` references in the test suite rewritten to `millet.*`
  (recovered ~29 previously-erroring tests).

### Notes

* `test_gui.py` (needs GTK/`gi`) and the torch-device-detection cases in
  `test_transcribe.py` / `test_cli.py` still require a GPU/display
  environment; they are excluded from the CI no-torch run.

## v0.9.2 — resilient Tinfoil (confidential) summarization

The `confidential` summary preset (Tinfoil TEE backend) could hard-fail
on a single transient DNS/network blip: the Tinfoil SDK does a network
fetch at client construction (router discovery,
`GET https://atc.tinfoil.sh/routers`) and the client init was outside
the retry path, so one flaky lookup aborted the whole summarization.

### Fixed

* **`_summarize_tinfoil` now retries transient network/DNS errors** with
  exponential backoff (3 attempts, ~2s/4s/8s).  Both the client
  construction (router discovery) and the completion call are inside the
  retry.  Genuine auth/model errors still fail fast (no retry), and a
  persistent outage surfaces a clear "Tinfoil TEE unreachable after N
  attempts" message naming the likely cause.
* New `_is_transient_network_error()` classifier walks the exception
  cause chain (the SDK wraps `URLError` in `ValueError("Failed to fetch
  router addresses…")`) and matches common DNS/connection failure text.

## v0.9.1 — team-aware paths (`--team`) + millet env-var aliases

Adds an optional team dimension so a scribe recording for multiple
teams can keep voiceprints, sync config, and recordings separated
locally, and introduces `MILLET_*` env-var names alongside the legacy
`MEETSCRIBE_*` / `MEET_*` ones.  Fully back-compatible: with no
`--team` flag and the old env vars, behavior is unchanged.

### Added

- **`millet.paths` module** — central, call-time path resolver with an
  optional `team` argument:
  - `profiles_path(team)` → `~/.config/meet/<team>/speaker_profiles.json`
  - `sync_config_path(team)` → `~/.config/meet/<team>/sync_config.json`
  - `recordings_dir(team)` → `~/meet-recordings/<team>/`
  - Team slugs validated (`[a-z][a-z0-9-]{2,31}`) so a bad value can
    never escape its directory.
- **`--team <slug>` flag** on `millet sync`, `millet enroll`,
  `millet label`.
  - `sync --team` reads `~/.config/meet/<team>/sync_config.json` and
    clones into a team-namespaced dir
    (`~/.local/share/meet/<team>/<repo>/`), so two teams can sync to
    different repos that share a name without colliding.
  - `enroll`/`label --team` use the team's voiceprint DB for matching
    and profile updates.
- **`MILLET_*` environment variables** with one-release fallback to the
  legacy names (one-time `DeprecationWarning` on legacy use), via
  `millet.paths.getenv_renamed`:
  - `MILLET_SUMMARY_BACKEND` ← `MEETSCRIBE_SUMMARY_BACKEND`
  - `MILLET_SUMMARY_MODEL` ← `MEETSCRIBE_SUMMARY_MODEL`
  - `MILLET_SUMMARY_PRESET` ← `MEETSCRIBE_SUMMARY_PRESET`
  - `MILLET_OLLAMA_SINGLEPASS` ← `MEETSCRIBE_OLLAMA_SINGLEPASS`
  - `MILLET_OPENAI_BASE_URL` ← `MEETSCRIBE_OPENAI_BASE_URL`
  - `MILLET_OPENAI_API_KEY` ← `MEETSCRIBE_OPENAI_API_KEY`
  - `MILLET_PROFILES_PATH` ← `MEET_PROFILES_PATH`
  - `MILLET_CONFIG_DIR` ← `MEET_CONFIG_DIR`
  - `MILLET_RECORDINGS_DIR` ← `MEET_RECORDINGS_DIR`

### Changed

- `millet.sync` config accessors and entry points
  (`load_sync_config`, `save_sync_config`, `is_sync_configured`,
  `detect_meeting_type`, `check_sync_candidate`, `sync_session`,
  `maybe_sync_session`, `ensure_repo_cloned`) now accept an optional
  `team` (and `config_path` override).  Teamless callers unaffected.
- `millet.voiceprint._default_profiles_path` now delegates to
  `millet.paths`.

### Notes

- On-disk paths remain `~/.config/meet/` and `~/meet-recordings/` (the
  `meet` spelling); only the env-var names gained `MILLET_*` aliases.
  Migrating the on-disk paths is deferred to a future release with a
  data-move step.

### Tests

- `tests/test_paths.py` (NEW), `tests/test_sync_team.py` (NEW).

## v0.9.0 — 2026-05-24 — rename to `millet-pipeline`

The package formerly known as `meetscribe-offline` is now
**`millet-pipeline`**.  Named after the Ottoman *millet system* — the
legal framework of communal autonomy that, in 1493, made it possible
for two Sephardic Jewish brothers to establish Istanbul's first
printing press, just one year after their expulsion from Spain.  Part
of the [vezir](https://github.com/pretyflaco/vezir) ecosystem.

This release is **all rename, no feature change.**  Functional
behavior is identical to 0.8.3.  Companion: `millet-record 0.4.0`
(formerly `meetscribe-record`); the `meet` console script is retained
as a deprecation-warning alias of the new `millet` command for two
minor versions before removal.

### Why not `millet`?

The bare `millet` name on PyPI is held by an unrelated dialogue-
framework package (last upload 2021).  We've opened a PEP 541 takeover
petition; if it succeeds in the future, a simpler `millet` name may
follow in a later major release.  `-pipeline` is more honest than
`-offline` (which was no longer accurate — the Tinfoil TEE and
OpenRouter summary backends are network-attached).

### Migration

```bash
# Out:
pip uninstall meetscribe-offline meetscribe-record
# In:
pip install millet-pipeline           # full pipeline (pulls millet-record transitively)
# or just the capture-only sibling:
pip install millet-record
```

CLI: `meet` keeps working in `millet-record 0.4.0` and `0.5.0`, with a
deprecation warning forwarding to `millet`.  Removed in `millet-record
0.6.0`.

### Changed

* **Distribution name**: `meetscribe-offline` → `millet-pipeline`.
* **Import name**: `from meet.X` → `from millet.X` (e.g. `from
  millet.label import apply_labels`, `from millet.transcribe import
  TranscriptionConfig`, `from millet.summarize import summarize`).
* **Entry-point group**: `meet.subcommands` → `millet.subcommands`.
  The legacy `meet.subcommands` group is also published for one
  deprecation cycle so a transitional `meet` CLI from `millet-record
  < 0.4.0` continues to load these subcommands.
* **Compatibility shims** (`millet/audio.py`, `millet/utils.py`,
  `millet/languages.py`, `millet/capture.py`) re-export from
  `millet_record.*` (formerly `meet_record.*`).  Both import paths
  work via the alias module shipped in `millet-record 0.4.0`.
* **CLI prog_name**: `meet (meetscribe-offline)` →
  `millet (millet-pipeline)` in `--version` output.
* **PDF model attribution line**: "AI transcription (meetscribe)" →
  "AI transcription (millet)".

### Compatibility

* **vezir 0.4.0** is the first vezir release pinning `millet-pipeline
  >= 0.9.0`.  Vezir 0.3.x continues to work against `meetscribe-offline
  0.8.3` (the last release under the old name); both old names stay on
  PyPI as historical artifacts.
* **No wire-format changes.**  Sessions produced by 0.8.3 are read
  unchanged.  All artifact paths and formats unchanged.

### What did NOT change

* Module-internal class names, function names, function signatures.
* `~/.config/meet/speaker_profiles.json` and other runtime paths
  (these live in `vezir-data` for the vezir-managed deployments; the
  standalone CLI's user-config path is the same).
* The `meet-record-mac` Swift sidecar binary name.  (Renaming would
  require macOS code-signing bundle-path changes.)

### Reserved names (future submodules)

`hattat`, `nahmias`, `basmahane`, `amire` — see the project's
RENAMING handoff for the reasoning behind reserving each.

---

## v0.8.3 — 2026-05-23

### Fixed

- **`apply_labels()` now re-raises summary failures when `summary_preset`
  is set.**  Previously, all summary exceptions were silently caught and
  `regenerate_summary` was set to `False`, making it impossible for
  callers to detect that the summary was not generated.  When
  `summary_preset` is explicitly provided (e.g. by vezir's retry-summary
  flow), the exception now propagates so the caller can surface it.
  Callers that don't pass `summary_preset` (the default `meet label`
  CLI flow) keep the existing silent-skip behavior.

## v0.8.2 — 2026-05-23

### Fixed

- **Voiceprint profile path was frozen at module-import time.**
  `PROFILES_PATH = Path.home() / ".config/meet/speaker_profiles.json"`
  was computed once at `import meet.voiceprint` time.  When an embedder
  (such as vezir) overrode `$HOME` after import and called voiceprint
  functions in-process, reads and writes went to the original home
  directory instead of the overridden one.  This caused the central
  voiceprint DB to go stale while a shadow copy at the real `$HOME`
  accumulated updates silently.

### Changed

- **All public voiceprint functions accept an optional `profiles_path`
  keyword argument**: `load_profiles()`, `save_profiles()`,
  `identify_speakers()`, `update_profiles_from_confirmed_labels()`,
  `enroll_session()`.  When `None` (the default), the path is resolved
  at **call time** (not import time) via `_default_profiles_path()`.
  Existing callers are unaffected — the default behavior matches 0.8.1.

- **New `MEET_PROFILES_PATH` environment variable** overrides the
  default profile path.  Useful for shell users or service managers
  that want a non-default location without modifying code.

- **`PROFILES_PATH` module constant** is now a lazy attribute via
  PEP 562 `__getattr__`.  `from meet.voiceprint import PROFILES_PATH`
  still works and resolves at access time (respecting current `$HOME`
  and `$MEET_PROFILES_PATH`).

## v0.8.1 — 2026-05-22

### Fixes

- **`apply_labels()` accepts `summary_preset` kwarg.**  `meet label`'s
  CLI was passing `summary_preset=...` to `apply_labels()` since the
  preset feature landed in 0.8.0, but the parameter wasn't in the
  function signature.  Every `meet label --auto` that found a
  confident voiceprint match crashed with `TypeError`.  The bug was
  latent because the auto-label path itself was failing on the
  `MIN_SEGMENT_RMS` regression below; with both fixed, the auto-label
  contract works end-to-end.  Regression test added.
- **Voiceprint matcher: lower per-segment RMS floor 0.005 → 0.0015.**
  The 0.005 floor introduced as a silence guard turned out to be too
  aggressive for real-world recordings with quiet mic gain
  (mean ~-49 dBFS, peaks at -4 dBFS).  Per-segment RMS clustered in
  [0.0016, 0.0024] — all silently skipped (`log.debug`) → no embedding
  → no match → every session needed manual labeling against an already-
  populated profile DB.  New floor at ~ -56 dBFS is well above true
  silence (-90) but below the lowest validated mic-recording RMS.
  Skip log promoted to `log.info`; a `log.warning` fires when ≥80% of
  segments were skipped.
- **Relabeled PDF preserves model attribution + backend.**
  `apply_labels(regenerate_summary=False)` used to hardcode
  `model="(relabeled)"` and lose the original `backend`, breaking the
  CONFIDENTIAL watermark on relabel-driven PDF regeneration.  Now reads
  `.summary.meta.json` and threads model + backend through.

## v0.8.0 — 2026-05-22

### New features

- **Summarization preset selector** — `--summary-preset
  {high-quality,confidential,alternative}` on `transcribe`, `run`,
  `label`, `gui`, and `ingest`.  Resolves to a concrete
  `(backend, model)` pair via `meet.summarize.SUMMARY_PRESETS`.  GUI
  gains a preset dropdown above the Advanced panel.
- **Tinfoil TEE backend** — `pip install 'meetscribe-offline[tee]'`
  pulls in the `tinfoil` SDK.  Inference runs inside a hardware-
  attested TEE (AMD SEV-SNP or Intel TDX); prompts are not visible to
  the model provider or the cloud operator.  ~$0.009 per meeting,
  ~66 s for a 30-min recording on DeepSeek V4 Pro.  Set
  `TINFOIL_API_KEY` or drop a key file at `~/models/tinfoil/tinfoil.txt`.
- **CONFIDENTIAL PDF watermark** — sessions summarized via the
  `tinfoil` backend get a red CONFIDENTIAL watermark on every page
  header and footer.  Auto-detected from `summary.backend`.

### Behavior changes

- **Preset guard semantics**: when a preset is explicitly chosen,
  summarization failures are NOT silently absorbed into the fallback
  chain.  A silent tinfoil → claudemax fallback would defeat the
  entire point of the Confidential preset.  Preset failures now raise
  `RuntimeError` from `summarize()`; the CLI catches it, finishes
  writing the transcript artifact, then exits non-zero so downstream
  tooling (vezir, CI) can detect the partial failure.
- **Default Ollama model** changed from `gpt-oss:20b` to `qwen3.5:9b`
  (better quality and no hallucinations on unseen transcripts).
- **Fallback chain** now: `claudemax → tinfoil → openrouter → ollama`
  (was `claudemax → openrouter → ollama`).
- **PDF: strip trailing JSON block from summary body**, so the
  rendered PDF shows clean Markdown rather than the structured data
  block contract introduced in 0.7.0.

### Internals

- New `tee` optional-dependency group in `pyproject.toml`.
- `SUMMARY_PRESETS` table at `meet/summarize.py:77`.
- `_resolve_tinfoil_api_key()` helper reads from env var or fallback
  file at `~/models/tinfoil/tinfoil.txt`.
- PDF generator auto-enables `confidential=True` when
  `summary.backend in ("tinfoil", "tinfoil-tee")`.

## v0.7.2 — 2026-05-17

### Fixes

- **`meet download <lang>` no longer fails with
  `CERTIFICATE_VERIFY_FAILED` on python.org Python builds (macOS)**
  (reported by @patternn in the M8 retrospective). `torchaudio`'s
  alignment-model fetcher uses raw `urllib`, which inherits the
  interpreter's default SSL context — empty on python.org Python
  installs that ship without a CA bundle. `meet/__init__.py` now
  injects `certifi`'s CA bundle as `SSL_CERT_FILE` at package
  import time (only if not already set), so every `urllib` caller
  in the process picks up a working store. HuggingFace downloads
  were never affected (they use `requests` + `certifi` directly).

### Internals

- `certifi` is now listed explicitly in `dependencies` (it was
  already a transitive dep via `requests`).

## v0.7.1 — 2026-05-14

### Fixes

- **Transcription auto-falls back to CPU + `int8` when CUDA is
  unavailable** (#19, thanks @fadenb) — running `meet run` on a machine
  without a GPU (laptop, container without passthrough, CI runner)
  previously crashed with `ValueError: device='cuda' but CUDA is not
  available`. `TranscriptionConfig` now warns and falls back to
  `device=cpu`, downgrading `compute_type=float16` to `int8` (float16
  is unsupported on CPU). The model-load log line annotates whether
  CPU was forced (`--device cpu`) or auto-selected because no GPU was
  found, so the diagnostic distinction is preserved.

### Internals

- `TranscriptionConfig` gains an internal `_device_auto_fallback`
  flag set in `__post_init__` when the device is auto-flipped, so
  `_load_whisperx_asr_model` can label the load line accurately
  without re-sniffing torch at print time.

## v0.7.0 — 2026-05-08

### Features

- **Structured YAML frontmatter on every summary (schema_version 1)** —
  `.summary.md` now begins with a typed YAML frontmatter block carrying
  `participants`, `topics`, `action_items` (with assignee, task, due,
  status), `decisions` (text, topic), `language`, `duration`, and a
  `source` pointer. A matching `.frontmatter.json` sidecar is written
  next to it for tools that don't want to parse YAML. The schema is
  intentionally small in v1; downstream tools (e.g. the
  [vezir](https://github.com/pretyflaco/vezir) 0.2.0+ indexer) build
  richer derived views over this stable surface. See the README's
  "Structured frontmatter" section for the schema.
- **`meet ingest` subcommand** — re-extract structured frontmatter for
  one or more existing session directories. Idempotent: skips sessions
  whose `.summary.meta.json` already records `data_extracted: true`
  unless `--force` is passed. Accepts the standard summary-backend
  flags. `--dry-run` previews without invoking the LLM. `--no-pdf`
  skips PDF regeneration.
- **LLM contract: fenced JSON data block** — every summarization prompt
  (single-pass, two-pass formatter, and inline fallbacks) instructs
  the model to append exactly one fenced ```json block at the end of
  its output with the structured fields. Single source of truth: the
  Markdown body still drives the PDF, the JSON block populates the
  frontmatter. JSON is required to be in English even when the body is
  in another language so cross-language indexing works.

### Internals

- New module `meet/frontmatter.py`: schema, build/parse/validate, YAML
  render and read-back, and a `context_from_transcript()` helper that
  pulls `started_at` / `title` from the session's `*.session.json`.
  No PyYAML dependency added; the writer is small enough to maintain
  in-tree and the reader prefers PyYAML when installed but falls back
  to a tightly-scoped subset parser otherwise.
- `MeetingSummary.save(out_dir, basename, *, frontmatter_context=...)` —
  new keyword argument. When provided, the saved Markdown is prefixed
  with the YAML block and a `.frontmatter.json` sidecar is written.
  When omitted, behavior is unchanged from 0.6.x for backward
  compatibility.
- `_dispatch()` in `summarize.py` strips the trailing JSON block off
  every backend's output once, so PDF rendering keeps using a clean
  Markdown body and `MeetingSummary.data` exposes the parsed dict to
  callers.
- `meet label` (find-and-replace fallback) splits, replaces, and
  re-renders both the YAML frontmatter and the JSON sidecar in step
  with the body, so renames stay consistent across all four artifacts.
- The summary `.summary.meta.json` sidecar now records
  `data_extracted: true` on success or `data_error: "<reason>"` on
  failure to extract.

### Backwards compatibility

- All callers that don't pass `frontmatter_context=` to
  `MeetingSummary.save()` continue to produce the legacy artifacts.
- Sessions recorded before 0.7.0 work unchanged; run `meet ingest` to
  upgrade them to schema_version 1.

### Tests

- 33 new tests across `tests/test_frontmatter.py` (24) and
  `tests/test_ingest.py` (9), plus 3 new assertions in
  `tests/test_summarize.py` confirming both the on-disk and inline
  fallback prompts carry the JSON contract.

---

## v0.6.1 — 2026-05-05

### GUI

- **Language dropdown** in the GTK Advanced expander to mitigate
  Whisper's auto-detect failure on sparse / quiet audio (long opening
  silences, short initial utterances).  Without an explicit language,
  Whisper's classifier can mis-identify English audio as Japanese /
  Chinese / Korean and produce pages of CJK hallucinations interspersed
  with correctly-transcribed English fragments.  A real Blink dev-sync
  recorded on 2026-05-05 was rendered useless this way: the meeting
  was English but every artifact came out in Japanese hallucinations.
- New fourth row in **Advanced**: a Language combobox with values
  `auto` (default) plus `en`, `de`, `fr`, `es`, `tr`, `fa`, `it`, `pt`,
  `nl`, `ja`, `zh`, `ko`, `ar`, `ru`.  Selection writes back into
  `transcribe_kwargs["language"]` immediately so the next recording's
  transcription picks it up.

### Compatibility

- CLI `--language` plumbing unchanged (in place since PR #4).
- vezir 0.1.3 unaffected — vezir doesn't invoke the GUI.

### PRs

- #16 feat(gui): add Language dropdown to Advanced settings panel

---

## v0.6.0 — 2026-05-04

### Apple Silicon (first-class support)

- **New `--asr-backend [auto|whisperx|mlx]` flag.** `auto` selects
  MLX Whisper on Apple Silicon when `mlx-whisper` is installed.
  Contributed by @openoms in #4 (first external contribution).
- **New `--torch-device [cuda|cpu|mps]` flag** for splitting
  alignment / diarization device from the ASR device.
- **New `--mlx-model` flag** to override the MLX repo (defaults to
  alias-mapped variants of `--model`).
- **`--device` and `--torch-device` auto-detect platform-appropriate
  defaults**: `cpu` / `mps` on Apple Silicon, `cuda` elsewhere.  Mac
  users no longer need to pass flags manually.
- New collapsible **Advanced** settings panel in the GTK recorder
  widget exposes the three new options without restarting.

Install with `pip install 'meetscribe-offline[mlx]'` on Apple Silicon
to pull in the MLX backend.

### Robustness

- `TranscriptionConfig` now validates `device` and `torch_device`
  against runtime availability with clear `ValueError` messages.
  Bad device combinations fail fast instead of deep inside whisperx.
- MLX backend always logs a one-time info note that VAD options
  (`--vad-onset`, `--vad-offset`) are inert under MLX.

### Infrastructure

- New GitHub Actions workflow runs `ruff` + focused `pytest` on
  push and PR.  First green CI on the repo.

### Compatibility

- **vezir 0.1.2+** detects the new flags via help-parsing
  (`meet_supports_option`); existing deployments work without
  configuration changes.
- **vezir-android** unchanged — communicates with vezir's HTTP API,
  not meetscribe directly.
- **`meetscribe-record`** dependency unchanged (still `>=0.1.0`).

### PRs

- #4 Add support for Apple Silicon and PyTorch device configuration (@openoms)
- #10 Validate torch device availability in TranscriptionConfig (closes #7)
- #11 Expose ASR backend, torch device, and MLX model in GUI (closes #5)
- #12 Auto-default device on Apple Silicon (closes #8)
- #13 Add minimal CI workflow with ruff and pytest (closes #9)
- #14 Always note that MLX backend ignores VAD options (closes #6)

---

## v0.5.0 — 2026-04-25

### Package split

The capture-only modules (`capture`, `audio`, `utils`, `languages`)
and the four capture-only subcommands (`record`, `devices`, `check`,
`archive`) move into a new sibling package
[`meetscribe-record`](https://github.com/pretyflaco/meetscribe-record).
`meetscribe-offline` now depends on it, keeps the heavy
transcription / diarization / summarization stack, and registers its
remaining subcommands via Click plugin entry-points
(`meet.subcommands`) so they appear under the same single `meet`
console script that `meetscribe-record` provides.

### Why

A meetscribe install pulls ~3 GB of transitive deps (whisperx +
torch + pyannote + ctranslate2 + reportlab).  For thin clients that
only need to record audio (e.g. [vezir](https://github.com/pretyflaco/vezir)
scribe widgets on teammate laptops), that's wasteful and slow to
install.  With the split:

| Profile | Install command | Footprint |
|---|---|---|
| Capture-only client | `pip install meetscribe-record` | ~30 MB |
| Full pipeline | `pip install meetscribe-offline` | ~3 GB (pulls -record transitively) |

### User-facing changes

- `meet` console script is now provided by `meetscribe-record`.
  When `meetscribe-offline` is also installed, the same `meet`
  command exposes all 12 subcommands (4 capture + 8 offline) via
  Click entry-point plugin discovery.
- `meet --version` reports both packages: e.g.
  `meet, version 0.5.0 (meetscribe-offline 0.5.0; meetscribe-record 0.1.0)`.
- `meetscribe-offline` 0.5.0 no longer registers a `meet` console
  script of its own; this avoids pip's last-installed-wins
  entry-point conflict.

### Internal changes

- `meet/capture.py`, `meet/audio.py`, `meet/utils.py`,
  `meet/languages.py` become thin compat shims that
  `from meet_record.X import *`, so any existing
  `from meet.capture import ...` continues to work.
- `meet/cli.py` loses the 4 capture commands (~286 lines deleted).
  The remaining 8 subcommands keep their `@main.command()`
  decorators and are exposed by name to the `meet.subcommands`
  entry-point group.
- `meet/__init__.py` now exposes `__version__` resolved via
  `importlib.metadata`, fixing the historical hardcoded `0.4.1`
  literal in `cli.py`.

### Compatibility

Existing installs continue to work after `pip install --upgrade
meetscribe-offline` — the dependency on `meetscribe-record>=0.1.0`
pulls it in transparently.  No flag or config changes required.

### Fixes

- `cli.py` no longer reports a stale `0.4.1` from `python -m
  meet.cli --version`; the version is resolved dynamically from
  package metadata.

---

## v0.4.2 — 2026-04-24

### Improvements

- **Two-pass Ollama summarization (default for local LLMs)** — the local
  Ollama backend now runs a separate extraction pass (Pass 1: pull topics,
  actions, decisions, questions out of the transcript with a wide context
  window) followed by a formatting pass (Pass 2: organize the extracted
  data into the canonical Markdown structure with a small 8K context).
  This dramatically improves format compliance and reduces hallucinations
  on 20B-class local models like `gpt-oss:20b`. Cloud backends
  (claudemax, openrouter, openai) are unchanged — they remain single-pass.
- **Improved cloud-summary prompt** — the system prompt used by the
  cloud backends has been rewritten based on A/B-tested results: more
  topics extracted, ~20% faster on Sonnet, no regressions.
- **`--ollama-singlepass` opt-out flag** — added to `transcribe`, `run`,
  `gui`, and `label` commands for users who want the previous single-pass
  behavior. Also configurable via `MEETSCRIBE_OLLAMA_SINGLEPASS=1`.
- **Per-pass timing in summary sidecar** — the `.summary.meta.json`
  sidecar now records `mode: "two_pass"`, `pass1_seconds`,
  `pass2_seconds`, and `pass1_chars` when two-pass was used.

### Documentation

- Added `docs/local-model-evaluation.md` — full evaluation of local
  20B-class models on 4 reference transcripts, including known
  failure modes (gpt-oss:20b unreliability on low-information short
  transcripts, qwen3.6:27b reasoning-mode bottleneck, and the
  rationale for the two-pass design).

### Testing

- Added 27 new tests covering env-var resolution, two-pass system
  prompts (en + de), two-pass call flow, dispatcher routing, and
  sidecar serialization. All 127 tests pass.

### Known limitations

- `gpt-oss:20b` may hallucinate on transcripts dominated by very
  short low-information utterances ("yes", "okay"). For such meetings
  the cloud backends produce more reliable summaries — the fallback
  chain (claudemax → openrouter → ollama) handles this automatically
  if a cloud backend is configured.
- `gpt-oss:20b` may exceed the default 600s timeout on very large
  (>100 KB) non-English transcripts during Pass 1. The fallback chain
  catches this; alternatively pass `--summary-timeout 1200` or use a
  cloud backend.

---

## v0.4.1 — 2026-04-13

### Improvements

- **Speaker labeling and sync prompts no longer deferred during recording** —
  previously, the speaker labeling dialog and sync confirmation prompt would
  wait until the user stopped recording before appearing. They now appear
  immediately, allowing users to label speakers from a previous meeting while
  the next one records.

---

## v0.4.0 — 2026-04-13

### New features

- **Background post-processing for back-to-back meetings** — after stopping a
  recording, the GUI returns to idle within seconds (drain time) so you can
  immediately start recording the next meeting. Transcription, speaker labeling,
  summarization, PDF generation, and sync all run in a background job queue.
  A small status line at the bottom of the window shows background progress
  (e.g., "Transcribing: meeting-20260413-143453..."). Interactive dialogs
  (speaker labeling, alignment model prompts, sync confirmation) are deferred
  until the user is not actively recording.

### Improvements

- Simplified GUI state machine: removed 8 post-processing states that blocked
  the recording controls. Primary states are now: idle, recording, paused,
  draining, done, error.
- Background jobs process sequentially via a FIFO queue, ensuring GPU resources
  are not contended between concurrent transcriptions.
- Clean shutdown: closing the window unblocks any background threads waiting
  for user input.

### Testing

- All 100 tests pass (99 + 1 pre-existing environment-dependent skip).

---

## v0.3.3 — 2026-04-13

### New features

- **GUI Pause/Resume** — the recording widget now shows side-by-side Pause and
  Stop buttons while recording. Pressing Pause stops the current ffmpeg chunk
  and freezes the timer; pressing Resume starts a new chunk. Stopping from
  either recording or paused state works seamlessly — chunks are stitched
  together automatically. The idle/done/error states still show a single
  centered Record button as before.

### Improvements

- `RecordingSession` in `capture.py` gained `pause()` and `resume()` methods
  and a `paused` field on `RecordingStatus`, making pause/resume available to
  any future consumer (CLI, scripts, etc.) without GUI dependency.
- The watchdog thread now skips health checks while paused, preventing false
  stall-restart triggers.
- Stopping from the paused state skips the 10-second drain buffer since there
  is no active ffmpeg pipeline to flush.

### Bug fixes

- **CLI version string** — `meet --version` now reports the correct version
  (`0.3.3`) instead of the stale `0.1.0` it has shown since the initial release.

### Testing

- 13 new tests for pause/resume functionality (`tests/test_capture.py`):
  pause flag, ffmpeg stop, error cases, resume chunk creation, status reporting,
  elapsed-time freezing, stop-from-paused, and watchdog behaviour.
- All 100 tests pass.

---

## v0.3.2 — 2026-04-10

### New features

- **`--mixdown dual` mode for headphone users** — new CLI flag on `meet transcribe`
  and `meet run` that transcribes each stereo channel independently (mic → YOU,
  system → REMOTE) instead of mixing to mono. This fixes transcription for
  headphone setups where the ~20× energy difference between mic and system
  channels causes WhisperX to suppress the quieter voice. Diarization is skipped
  in dual mode since channel identity equals speaker identity. Default behavior
  (`--mixdown mono`) is unchanged.
  *(Contributed by [@Rolloniel](https://github.com/Rolloniel) in [#1](https://github.com/pretyflaco/meetscribe/pull/1))*

### Bug fixes

- **Speaker labeling threshold** — `_label_speakers_from_channels()` now requires
  `mic_ratio > 0.5` before labeling a speaker as YOU. Previously, the speaker
  with the highest mic ratio was always labeled YOU even when no speaker was
  actually mic-dominant (e.g. system-only audio capture). When no speaker exceeds
  the threshold, all speakers are labeled REMOTE.
  *(Contributed by [@Rolloniel](https://github.com/Rolloniel) in [#1](https://github.com/pretyflaco/meetscribe/pull/1))*

---

## v0.3.1 — 2026-04-10

### Bug fixes

- **CUDA NVRTC JIT fix** — replaced `_ensure_nvrtc_compat()` symlink approach
  with `_preload_nvrtc_builtins()` using `ctypes.CDLL`. The old method created
  a wrong-version symlink and set `LD_LIBRARY_PATH` too late (after
  `libnvrtc.so` was already loaded). The new approach preloads the correct
  `libnvrtc-builtins.so` into the process address space before NVRTC needs it,
  with automatic version detection across `nvidia-cuda-nvrtc` pip packages.

- **Channel-based diarization fallback** — added `_split_by_channel()` for
  stereo recordings where pyannote detects only 0–1 speakers. This can happen
  on short recordings or when GPU-dependent floating-point differences in
  WeSpeaker speaker embeddings cause VBx clustering to collapse multiple
  speakers into one. The fallback uses per-segment and per-word mic vs system
  channel RMS energy to assign YOU/REMOTE labels, which is hardware-independent
  and reliable when stereo channels are cleanly separated.

---

## v0.3.0 — 2026-04-01

### New features

- **Multi-backend summarization** — supports four backends with automatic
  fallback: `claudemax` (Claude Max API Proxy), `openrouter` (OpenRouter API),
  `openai` (any OpenAI-compatible endpoint), and `ollama` (local). If the
  configured backend is unavailable, meetscribe automatically tries the next
  one. Use `--summary-backend` and `--summary-model` flags, or set
  `MEETSCRIBE_SUMMARY_BACKEND` / `MEETSCRIBE_SUMMARY_MODEL` env vars.

- **Generic OpenAI-compatible backend** — use any OpenAI-compatible API for
  summarization (Lemonade, LiteLLM, vLLM, LocalAI, self-hosted endpoints).
  Set `MEETSCRIBE_OPENAI_BASE_URL` and optionally `MEETSCRIBE_OPENAI_API_KEY`.

- **Voiceprint speaker recognition** — automatically identifies speakers across
  meetings using voice embeddings. After labeling a meeting, speaker profiles
  are stored in `~/.config/meet/speaker_profiles.json`. Future meetings match
  voices against the database using cosine similarity. Use `meet enroll` to
  build profiles from past sessions, or let the GUI update profiles
  automatically after each labeling.

- **Meeting sync** — push meeting artifacts (transcript, summary, PDF, SRT) to
  any configured Git repository on a schedule. Configure your repo URL and
  meeting schedule in `~/.config/meet/sync_config.json`. Use `meet sync` to
  push manually or let the GUI auto-sync after recording. Run
  `meet sync --init-config` to generate an example config.

- **Improved summarization prompts** — prompt templates extracted to standalone
  markdown files (`meet/prompts/summarize_system.md`, etc.) for easy iteration
  without touching Python code. Prompt rewritten for better results with
  local/open-source models: more information-dense, preserves technical
  specificity, captures implied action items, provides format guidance.

### Improvements

- Dynamic context window sizing for ollama — automatically sizes `num_ctx` to
  fit long transcripts (up to 64K tokens) instead of truncating.
- Response validation catches upstream API errors (expired tokens, rate limits)
  that would otherwise be silently saved as the meeting summary.
- Thinking mode explicitly disabled for ollama models (`think: false`) to avoid
  wasting tokens on hidden reasoning with models like GLM-4.7-flash and Qwen 3.5.
- GUI auto-sync guarded by `is_sync_configured()` — silently skips if no repo
  is configured.

### Testing

- All 81 existing tests pass with the new prompt loading system.

---

## v0.2.0 — 2026-03-14

### New features

- **Multilingual support** — Whisper large-v3-turbo supports 99 languages.
  meetscribe now passes language hints through the full pipeline: transcription,
  wav2vec2 alignment, Ollama summary (prompted in the source language), and PDF.
  Use `--language auto` (default) or specify a code: `en`, `de`, `tr`, `fr`,
  `es`, `fa`.

- **Farsi / RTL support** — Farsi transcripts render correctly in PDF using
  Noto Naskh Arabic with arabic-reshaper + python-bidi for right-to-left layout.
  Install optional deps with `pip install "meetscribe-offline[rtl]"`.

- **`meet label` CLI command** — assign real names to speakers after the fact.
  For each speaker: shows a summary table, plays a short audio clip from the
  correct stereo channel (via ffplay), prompts for a name. Regenerates all
  outputs (txt, srt, json, summary.md, pdf) with the new names. Options:
  `--no-audio`, `--no-summary`.

- **GUI speaker labeling dialog** — when 2+ speakers are detected, a dialog
  appears before results are saved. Shows each speaker's channel and a sample
  line. Labels are applied before writing any output files.

### Improvements

- PDF now uses DejaVu Sans for full Unicode coverage (replaces previous
  Latin-only font). Handles Cyrillic, Greek, Turkish special characters, etc.
- Ollama summary prompts are now language-aware: when a non-English language is
  detected, the prompt instructs the LLM to write the summary in that language.
- `post_process()` function centralises all output generation (txt, srt, json,
  pdf) so that `meet label` and the GUI dialog share the same code path.
- Shared utilities extracted to `meet/audio.py`, `meet/languages.py`,
  `meet/utils.py`, `meet/label.py` for cleaner architecture.

### Testing

- 81-test suite added covering `label`, `pdf`, `summarize`, `transcribe`, and
  `utils` modules.

### Package

- PyPI package renamed to `meetscribe-offline` to distinguish from an unrelated
  squatted project. Install with `pip install meetscribe-offline`.

---

## v0.1.0 — 2026-03-01

Initial release.

- Dual-channel audio capture (mic left, system audio right) via
  PipeWire/PulseAudio + ffmpeg
- WhisperX transcription (faster-whisper + wav2vec2 alignment)
- pyannote-audio speaker diarization with YOU/REMOTE channel mapping
- Ollama AI meeting summaries (qwen3.5:9b default)
- PDF output (summary + full transcript)
- Output formats: `.txt`, `.srt`, `.json`, `.summary.md`, `.pdf`
- GTK3 GUI widget (always-on-top, record/stop, live timer, open results)
- CLI: `meet run`, `meet record`, `meet transcribe`, `meet gui`, `meet devices`,
  `meet check`
