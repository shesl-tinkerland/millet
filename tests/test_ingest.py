"""Tests for `meet ingest` — backfill structured frontmatter on existing sessions."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from meet.cli import ingest
from meet.summarize import MeetingSummary


def _fake_summary(markdown: str = "## Meeting Overview\nHi.", *, with_data: bool = True) -> MeetingSummary:
    return MeetingSummary(
        markdown=markdown,
        model="fake-model",
        elapsed_seconds=0.1,
        backend="fake",
        data={
            "participants": ["YOU", "Alice"],
            "topics": ["agenda", "budget"],
            "action_items": [
                {"assignee": "YOU", "task": "Share screen", "due": None, "status": "open"},
            ],
            "decisions": [],
        } if with_data else None,
        data_error=None if with_data else "no JSON block found",
    )


@pytest.fixture
def patched_summarize(monkeypatch):
    """Stub out the LLM call so tests don't need a backend."""
    calls = []

    def fake_do_summarize(transcript_text, config, language=None, progress_callback=None):
        calls.append({"text": transcript_text, "language": language})
        return _fake_summary()

    # Patch where _ingest_one_session imports it.
    import meet.summarize as sm

    monkeypatch.setattr(sm, "summarize", fake_do_summarize)
    return calls


@pytest.fixture
def patched_no_pdf(monkeypatch):
    """Stub PDF generation so we don't depend on reportlab + WAV in unit tests."""
    import meet.pdf as pdf_mod

    monkeypatch.setattr(pdf_mod, "generate_pdf", lambda *a, **kw: None)


@pytest.fixture
def patched_gpu(monkeypatch):
    """Stub the GPU helper so the ollama backend default doesn't try to reach Ollama."""
    import meet.transcribe as tx

    monkeypatch.setattr(tx, "ensure_gpu_available", lambda: None)


# ─── Happy path ────────────────────────────────────────────────────────────


class TestIngestHappyPath:
    def test_writes_frontmatter_and_sidecar(
        self, session_dir, patched_summarize, patched_no_pdf, patched_gpu
    ):
        runner = CliRunner()
        result = runner.invoke(
            ingest,
            [str(session_dir), "--summary-backend", "ollama"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert "1 processed, 0 skipped, 0 failed" in result.output

        # frontmatter sidecar exists
        sidecar = session_dir / "meeting-20260314-100000.frontmatter.json"
        assert sidecar.exists()
        fm = json.loads(sidecar.read_text(encoding="utf-8"))
        assert fm["schema_version"] == 1
        assert fm["topics"] == ["agenda", "budget"]
        assert fm["action_items"][0]["assignee"] == "YOU"

        # summary.md begins with a YAML frontmatter block
        md = (session_dir / "meeting-20260314-100000.summary.md").read_text(
            encoding="utf-8"
        )
        assert md.startswith("---\n")
        assert "schema_version: 1" in md
        # The Markdown body comes after the closing ---
        assert "## Meeting Overview" in md

        # meta sidecar records data_extracted
        meta = json.loads(
            (session_dir / "meeting-20260314-100000.summary.meta.json").read_text(
                encoding="utf-8"
            )
        )
        assert meta["data_extracted"] is True

        # The summarizer was actually called once
        assert len(patched_summarize) == 1

    def test_dry_run_does_not_invoke_llm(
        self, session_dir, patched_summarize, patched_gpu
    ):
        runner = CliRunner()
        result = runner.invoke(
            ingest, [str(session_dir), "--dry-run"], catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "would re-extract" in result.output
        # No frontmatter sidecar produced
        assert not (
            session_dir / "meeting-20260314-100000.frontmatter.json"
        ).exists()
        # And no LLM call
        assert len(patched_summarize) == 0

    def test_skips_already_extracted_without_force(
        self, session_dir, patched_summarize, patched_no_pdf, patched_gpu
    ):
        # First run writes frontmatter
        runner = CliRunner()
        runner.invoke(ingest, [str(session_dir)], catch_exceptions=False)
        assert len(patched_summarize) == 1

        # Second run should be a no-op skip
        result = runner.invoke(ingest, [str(session_dir)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already has frontmatter" in result.output
        # Summarize was NOT invoked again
        assert len(patched_summarize) == 1

    def test_force_re_extracts(
        self, session_dir, patched_summarize, patched_no_pdf, patched_gpu
    ):
        runner = CliRunner()
        runner.invoke(ingest, [str(session_dir)], catch_exceptions=False)
        runner.invoke(
            ingest, [str(session_dir), "--force"], catch_exceptions=False,
        )
        # Two LLM calls: initial + forced re-run
        assert len(patched_summarize) == 2


# ─── Failure modes ─────────────────────────────────────────────────────────


class TestIngestFailures:
    def test_missing_transcript_json_fails(self, tmp_path, patched_gpu):
        empty_dir = tmp_path / "empty-session"
        empty_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(ingest, [str(empty_dir)], catch_exceptions=False)
        assert result.exit_code == 1
        assert "no transcript JSON" in result.output

    def test_summarizer_failure_is_reported(
        self, session_dir, monkeypatch, patched_no_pdf, patched_gpu
    ):
        import meet.summarize as sm

        def boom(*a, **kw):
            raise RuntimeError("backend down")

        monkeypatch.setattr(sm, "summarize", boom)

        runner = CliRunner()
        result = runner.invoke(ingest, [str(session_dir)], catch_exceptions=False)
        assert result.exit_code == 1
        assert "summary failed: backend down" in result.output

    def test_no_re_llm_flag_is_rejected(self, tmp_path, patched_gpu):
        runner = CliRunner()
        result = runner.invoke(
            ingest, [str(tmp_path), "--no-re-llm"], catch_exceptions=False,
        )
        # Click parses the negation as falsy --re-llm
        assert result.exit_code == 2
        assert "not supported" in result.output


# ─── No-pdf option ─────────────────────────────────────────────────────────


def test_no_pdf_skips_pdf_generation(
    session_dir, patched_summarize, monkeypatch, patched_gpu
):
    import meet.pdf as pdf_mod

    pdf_calls: list = []

    def fake_pdf(*a, **kw):
        pdf_calls.append((a, kw))

    monkeypatch.setattr(pdf_mod, "generate_pdf", fake_pdf)

    runner = CliRunner()
    result = runner.invoke(
        ingest, [str(session_dir), "--no-pdf"], catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert pdf_calls == []  # PDF generation was skipped


# ─── Multiple sessions ─────────────────────────────────────────────────────


def test_multi_session_summary_counts(
    tmp_path, transcript, patched_summarize, patched_no_pdf, patched_gpu
):
    """Process two sessions in one invocation; verify counts."""
    # Build two sessions side by side.
    s1 = tmp_path / "meeting-1"
    s2 = tmp_path / "meeting-2"
    for s in (s1, s2):
        s.mkdir()
        # transcript json
        (s / f"{s.name}.session.json").write_text(
            json.dumps({"started_at": "2026-04-25T10:00:00+00:00"}),
            encoding="utf-8",
        )
        transcript.save(s, basename=s.name)

    runner = CliRunner()
    result = runner.invoke(
        ingest, [str(s1), str(s2)], catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "2 processed, 0 skipped, 0 failed" in result.output
    assert (s1 / "meeting-1.frontmatter.json").exists()
    assert (s2 / "meeting-2.frontmatter.json").exists()
