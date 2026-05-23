# Changelog

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
