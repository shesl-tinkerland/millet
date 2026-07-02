---
name: Millet Meeting Transcription
description: |
  Guide users through setting up and running Millet — a fully local meeting
  transcription pipeline with WhisperX speaker diarization, AI summaries,
  and professional PDF output.
---

# Millet Meeting Transcription

> Provenance: shaped from [pretyflaco/millet](https://github.com/pretyflaco/millet)
> (351 stars, Python, active development). The original repository has no
> SKILL.md; this skill wraps its public workflow into a single entry point.
>
> Source URL: https://github.com/pretyflaco/millet
> Discovery URL: https://x.com/_pretyflaco/status/2032255715478258119

## What This Skill Does

Millet records meetings from any voice/video call application (Zoom, Teams,
Meet, Discord, Signal), transcribes the audio locally using WhisperX with
word-level timestamps, identifies speakers via pyannote-audio diarization,
generates AI-powered summaries, and exports professional PDFs.

The entire transcription pipeline runs offline on the user's machine.
Summarization can use local Ollama models or optional cloud backends
(OpenRouter, Claude Max, Tinfoil TEE, OpenAI-compatible endpoints).

## Core Pipeline

1. **Dual-channel audio capture** — microphone + system audio via
   PipeWire/PulseAudio (Linux recording; macOS for post-processing)
2. **WhisperX transcription** — batched speech-to-text with wav2vec2 forced
   alignment for precise word-level timestamps
3. **Speaker diarization** — pyannote-audio segments speakers; voiceprint
   recognition carries identities across sessions
4. **AI summarization** — structured YAML frontmatter with action items,
   decisions, topics, and narrative summary (five backend choices)
5. **PDF generation** — ReportLab-based professional output with Unicode
   support combining transcript and summary

## When To Use This Skill

- Setting up Millet on a Linux workstation or preparing macOS for
  post-processing
- Configuring audio capture for a specific meeting platform
- Choosing and configuring a summarization backend (Ollama, OpenRouter,
  Claude Max, Tinfoil, OpenAI-compatible)
- Building and managing voiceprint profiles for recurring speakers
- Troubleshooting transcription quality, diarization accuracy, or language
  detection across 99+ supported languages
- Understanding output formats (TXT, SRT, JSON, Markdown, PDF) and
  customizing summary templates
- Setting up git-based transcript synchronization

## Required Inputs

- The user's operating system and audio setup (PipeWire vs PulseAudio,
  CUDA availability, Apple Silicon)
- Which meeting application(s) they use
- Preferred summarization backend and any API keys
- Language requirements if not English

## Output Contract

Provide concrete, actionable guidance: installation commands, configuration
file edits, CLI invocations, and troubleshooting steps. Reference the
official repository documentation at
https://github.com/pretyflaco/millet for the latest instructions.

## Key Repository Structure

| Path | Purpose |
|---|---|
| `millet/capture.py` | Dual-channel audio capture via PipeWire/PulseAudio |
| `millet/transcribe.py` | WhisperX transcription and alignment |
| `millet/label.py` | Speaker diarization and labeling |
| `millet/voiceprint.py` | Voice profile management across sessions |
| `millet/summarize.py` | Multi-backend AI summarization |
| `millet/pdf.py` | Professional PDF generation |
| `millet/frontmatter.py` | YAML frontmatter parsing for summaries |
| `millet/gui.py` | GTK3 recording widget |
| `millet/sync.py` | Git-based transcript synchronization |
| `millet/cli/` | CLI entry points |
| `millet/prompts/` | Summary prompt templates |
