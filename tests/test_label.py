"""Tests for meet.label — speaker labeling module."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from meet.label import (
    SpeakerInfo,
    _detect_speaker_channels,
    _find_session_files,
    _load_transcript,
    apply_labels,
    extract_speaker_clip,
    get_speakers,
    relabel_transcript_in_memory,
)
from meet.transcribe import Segment, Speaker, Transcript


# ─── _find_session_files() ─────────────────────────────────────────────────

class TestFindSessionFiles:
    def test_finds_all_file_types(self, session_dir):
        files = _find_session_files(session_dir)
        assert "json" in files
        assert "session" in files
        assert "wav" in files
        assert "summary" in files

    def test_ignores_translation_files(self, session_dir):
        # Create a translation file that should NOT be picked up as "json"
        (session_dir / "meeting-20260314-100000.translation.en.json").write_text("{}")
        files = _find_session_files(session_dir)
        assert ".translation." not in files["json"].name

    def test_empty_dir(self, tmp_path):
        files = _find_session_files(tmp_path)
        assert "json" not in files
        assert "wav" not in files


# ─── _load_transcript() ────────────────────────────────────────────────────

class TestLoadTranscript:
    def test_round_trip(self, session_dir):
        files = _find_session_files(session_dir)
        t = _load_transcript(files["json"])
        assert len(t.segments) == 6
        assert len(t.speakers) == 3
        assert t.language == "en"

    def test_segment_data(self, session_dir):
        files = _find_session_files(session_dir)
        t = _load_transcript(files["json"])
        seg = t.segments[0]
        assert seg.start == 0.0
        assert seg.speaker == "YOU"
        assert "Hello" in seg.text


# ─── _detect_speaker_channels() ────────────────────────────────────────────

class TestDetectSpeakerChannels:
    def test_you_on_mic(self, transcript, stereo_wav_with_speakers):
        channels = _detect_speaker_channels(
            stereo_wav_with_speakers, transcript.segments, transcript.speakers,
        )
        assert channels["YOU"] == "mic"

    def test_remote_on_system(self, transcript, stereo_wav_with_speakers):
        channels = _detect_speaker_channels(
            stereo_wav_with_speakers, transcript.segments, transcript.speakers,
        )
        assert channels["REMOTE_1"] == "system"
        assert channels["REMOTE_2"] == "system"

    def test_sensitive_mic_you_still_on_mic(self, tmp_path):
        sr = 16000
        n_each = int(3.0 * sr)
        t = np.linspace(0, 3.0, n_each, dtype=np.float32)

        mic_you = (5000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
        sys_you = (7500 * np.sin(2 * np.pi * 880 * t)).astype(np.int16)
        mic_rem = (500 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
        sys_rem = (20000 * np.sin(2 * np.pi * 1100 * t)).astype(np.int16)

        mic = np.concatenate([mic_you, mic_rem])
        system = np.concatenate([sys_you, sys_rem])
        stereo = np.column_stack((mic, system)).flatten()

        path = tmp_path / "sensitive-mic.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(stereo.tobytes())

        segments = [
            Segment(start=0.0, end=3.0, text="local", speaker="YOU"),
            Segment(start=3.0, end=6.0, text="remote", speaker="REMOTE"),
        ]
        speakers = [Speaker(id="YOU"), Speaker(id="REMOTE")]

        channels = _detect_speaker_channels(path, segments, speakers)
        assert channels["YOU"] == "mic", (
            f"YOU mic_ratio < 0.5 but margin should keep it on mic; got {channels}"
        )

    def test_mono_defaults_to_mic(self, tmp_path, transcript):
        # Create a mono WAV
        mono_path = tmp_path / "mono.wav"
        with wave.open(str(mono_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(16000, dtype=np.int16).tobytes())

        channels = _detect_speaker_channels(
            mono_path, transcript.segments, transcript.speakers,
        )
        for sp in transcript.speakers:
            assert channels[sp.id] == "mic"


# ─── get_speakers() ────────────────────────────────────────────────────────

class TestGetSpeakers:
    def test_returns_all_speakers(self, session_dir):
        speakers = get_speakers(session_dir)
        assert len(speakers) == 3
        ids = {sp.id for sp in speakers}
        assert ids == {"YOU", "REMOTE_1", "REMOTE_2"}

    def test_speaker_info_fields(self, session_dir):
        speakers = get_speakers(session_dir)
        for sp in speakers:
            assert isinstance(sp, SpeakerInfo)
            assert sp.channel in ("mic", "system")
            assert sp.segment_count > 0
            assert sp.sample_text
            assert sp.sample_start >= 0
            assert sp.sample_end > sp.sample_start


# ─── extract_speaker_clip() ────────────────────────────────────────────────

class TestExtractSpeakerClip:
    def test_produces_mono_wav(self, session_dir):
        speakers = get_speakers(session_dir)
        files = _find_session_files(session_dir)
        sp = speakers[0]

        clip_path = extract_speaker_clip(files["wav"], sp)
        try:
            with wave.open(str(clip_path), "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 16000
        finally:
            clip_path.unlink(missing_ok=True)

    def test_clip_duration_capped(self, session_dir):
        speakers = get_speakers(session_dir)
        files = _find_session_files(session_dir)
        sp = speakers[0]

        clip_path = extract_speaker_clip(files["wav"], sp, max_duration=2.0)
        try:
            with wave.open(str(clip_path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
                assert duration <= 2.1  # small tolerance
        finally:
            clip_path.unlink(missing_ok=True)

    def test_quiet_clip_is_normalized(self, tmp_path):
        """A very quiet mic channel should be peak-normalized so the clip is audible."""
        sr = 16000
        duration = 3.0
        n_frames = int(duration * sr)
        t = np.arange(n_frames, dtype=np.float32) / sr

        # Mic: very quiet (amplitude 500 out of 32767 — ~1.5% full-scale)
        mic = (500 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
        # System: normal level
        system = (18000 * np.sin(2 * np.pi * 880 * t)).astype(np.int16)

        wav_path = tmp_path / "quiet-mic.wav"
        stereo = np.column_stack((mic, system)).flatten()
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(stereo.tobytes())

        sp = SpeakerInfo(
            id="YOU", channel="mic",
            sample_text="test", sample_start=0.0, sample_end=3.0,
            segment_count=1,
        )

        clip_path = extract_speaker_clip(wav_path, sp)
        try:
            with wave.open(str(clip_path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16)
            peak = int(np.max(np.abs(samples)))

            # After normalization the peak should be near 70% of 32767 (~22937)
            assert peak > 15000, f"Clip should be normalized louder, got peak={peak}"
            assert peak <= 32767, f"Clip should not clip, got peak={peak}"
        finally:
            clip_path.unlink(missing_ok=True)

    def test_already_loud_clip_not_clipped(self, tmp_path):
        """A clip whose peak already exceeds the target should not be altered."""
        sr = 16000
        duration = 3.0
        n_frames = int(duration * sr)
        t = np.arange(n_frames, dtype=np.float32) / sr

        # Mic: already at 30000 — above the 70% target (~22937)
        mic = (30000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
        system = (5000 * np.sin(2 * np.pi * 880 * t)).astype(np.int16)

        wav_path = tmp_path / "loud-mic.wav"
        stereo = np.column_stack((mic, system)).flatten()
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(stereo.tobytes())

        sp = SpeakerInfo(
            id="YOU", channel="mic",
            sample_text="test", sample_start=0.0, sample_end=3.0,
            segment_count=1,
        )

        clip_path = extract_speaker_clip(wav_path, sp)
        try:
            with wave.open(str(clip_path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16)
            peak = int(np.max(np.abs(samples)))

            # Peak was 30000, above the 22937 target — should stay unchanged.
            assert 29000 <= peak <= 31000, (
                f"Already-loud clip should not be re-scaled, got peak={peak}"
            )
        finally:
            clip_path.unlink(missing_ok=True)


# ─── relabel_transcript_in_memory() ────────────────────────────────────────

class TestRelabelTranscriptInMemory:
    def test_remaps_segments(self, transcript):
        label_map = {"YOU": "Alice", "REMOTE_1": "Bob"}
        new_t = relabel_transcript_in_memory(transcript, label_map)
        alice_segs = [s for s in new_t.segments if s.speaker == "Alice"]
        assert len(alice_segs) == 2

    def test_remaps_speakers(self, transcript):
        label_map = {"YOU": "Alice", "REMOTE_1": "Bob"}
        new_t = relabel_transcript_in_memory(transcript, label_map)
        ids = {sp.id for sp in new_t.speakers}
        assert "Alice" in ids
        assert "Bob" in ids
        # REMOTE_2 unchanged
        assert "REMOTE_2" in ids

    def test_empty_map_returns_copy(self, transcript):
        new_t = relabel_transcript_in_memory(transcript, {})
        assert new_t is transcript  # no-op returns same object

    def test_preserves_language_and_metadata(self, transcript):
        label_map = {"YOU": "Alice"}
        new_t = relabel_transcript_in_memory(transcript, label_map)
        assert new_t.language == "en"
        assert new_t.duration == 42.0
        assert new_t.audio_file == transcript.audio_file


# ─── apply_labels() ────────────────────────────────────────────────────────

class TestApplyLabels:
    def test_updates_txt(self, session_dir):
        apply_labels(session_dir, {"YOU": "Alice"}, regenerate_summary=False)
        txt = (session_dir / "meeting-20260314-100000.txt").read_text()
        assert "Alice:" in txt
        assert "YOU:" not in txt

    def test_updates_srt(self, session_dir):
        apply_labels(session_dir, {"YOU": "Alice"}, regenerate_summary=False)
        srt = (session_dir / "meeting-20260314-100000.srt").read_text()
        assert "[Alice]" in srt
        assert "[YOU]" not in srt

    def test_updates_json_speakers(self, session_dir):
        apply_labels(session_dir, {"YOU": "Alice"}, regenerate_summary=False)
        data = json.loads(
            (session_dir / "meeting-20260314-100000.json").read_text()
        )
        ids = {sp["id"] for sp in data["speakers"]}
        assert "Alice" in ids

    def test_stores_label_map_in_session(self, session_dir):
        label_map = {"YOU": "Alice", "REMOTE_1": "Bob"}
        apply_labels(session_dir, label_map, regenerate_summary=False)
        meta = json.loads(
            (session_dir / "meeting-20260314-100000.session.json").read_text()
        )
        assert meta["speaker_labels"] == label_map

    def test_find_replace_summary(self, session_dir):
        """With regenerate_summary=False, apply_labels should do
        find-and-replace on the existing summary file."""
        # Put a speaker name in the summary so we can verify replacement
        summary_path = session_dir / "meeting-20260314-100000.summary.md"
        text = summary_path.read_text()
        text = text.replace("the meeting", "YOU discussed the meeting")
        summary_path.write_text(text)

        apply_labels(session_dir, {"YOU": "Alice"}, regenerate_summary=False)
        new_text = summary_path.read_text()
        assert "Alice discussed the meeting" in new_text

    def test_accepts_summary_preset_kwarg(self, session_dir):
        """Regression: cli.py `meet label` passes summary_preset= to
        apply_labels().  If the kwarg isn't in the signature, every
        auto-label call from `meet label --auto` raises TypeError and
        the relabel never lands on disk.  See git history for context.

        Validates the signature itself; runs with regenerate_summary=False
        so the LLM path is bypassed and we don't need a live backend."""
        apply_labels(
            session_dir,
            {"YOU": "Alice"},
            regenerate_summary=False,
            summary_preset="high-quality",
        )
        txt = (session_dir / "meeting-20260314-100000.txt").read_text()
        assert "Alice:" in txt
