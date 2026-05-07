"""Tests for meet.summarize — system prompt construction."""

from __future__ import annotations

from meet.summarize import _build_system_prompt
from meet.languages import SECTION_HEADERS as _SECTION_HEADERS


class TestBuildSystemPrompt:
    def test_english_default(self):
        prompt = _build_system_prompt("en")
        assert "Meeting Overview" in prompt
        assert "Key Topics Discussed" in prompt
        assert "Action Items" in prompt
        assert "Decisions Made" in prompt
        assert "Open Questions" in prompt

    def test_farsi_headers(self):
        prompt = _build_system_prompt("fa")
        h = _SECTION_HEADERS["fa"]
        assert h["overview"] in prompt  # "خلاصه جلسه"
        assert h["topics"] in prompt
        assert h["actions"] in prompt
        # Should contain the "write ENTIRE summary in Persian" instruction
        assert "Persian" in prompt or "Farsi" in prompt

    def test_all_supported_languages(self):
        """Every language in _SECTION_HEADERS should produce a valid prompt."""
        for lang in _SECTION_HEADERS:
            prompt = _build_system_prompt(lang)
            h = _SECTION_HEADERS[lang]
            assert h["overview"] in prompt
            assert h["topics"] in prompt
            assert h["actions"] in prompt
            assert h["decisions"] in prompt
            assert h["questions"] in prompt

    def test_unknown_language_falls_back_to_english(self):
        prompt = _build_system_prompt("xx")
        assert "Meeting Overview" in prompt

    def test_prompt_file_path_includes_json_contract(self):
        """The prompt loaded from disk must instruct the LLM to emit a
        fenced JSON block — this is the schema_version 1 contract."""
        prompt = _build_system_prompt("en")
        assert "```json" in prompt
        assert "action_items" in prompt
        assert "REQUIRED" in prompt

    def test_inline_fallback_includes_json_contract(self, monkeypatch):
        """When the prompt file is missing, the inline fallback must still
        carry the JSON contract so meet ingest / record never silently
        ships frontmatter-less summaries."""
        import meet.summarize as sm

        # Force the loader to act as if the prompt files were missing.
        monkeypatch.setattr(sm, "_load_prompt", lambda _: None)
        prompt = sm._build_system_prompt("en")
        assert "```json" in prompt
        assert "action_items" in prompt
        assert '"open"' in prompt  # status enumeration documented

    def test_format_inline_fallback_includes_json_contract(self, monkeypatch):
        """Same contract for the two-pass format prompt fallback."""
        import meet.summarize as sm

        monkeypatch.setattr(sm, "_load_prompt", lambda _: None)
        prompt = sm._build_format_system_prompt("en")
        assert "json" in prompt.lower()
        assert "action_items" in prompt
