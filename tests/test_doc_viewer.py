"""
tests/test_doc_viewer.py — Unit tests for the built-in `/docs` documentation command.

Covers:
  1. Topic id constants & alias coverage (DOC_TOPICS / TOPIC_ALIASES)
  2. Topic routing for canonical names, Indonesian aliases and menu numbers
  3. `/docs help` table of contents & unknown-topic hint
  4. Every topic renderer actually produces output
  5. Interactive menu presentation + Esc cancel handling
  6. Registration: autocomplete list, fuzzy aliases, and the slash dispatcher
"""

import pytest

import commands.doc_viewer as doc_viewer
from commands.doc_viewer import (
    DOC_TOPICS,
    DOC_TOPIC_DESCRIPTIONS,
    MENU_OPTIONS,
    TOPIC_ALIASES,
    run_doc_command,
)


def _record_topic_calls(monkeypatch):
    """Replace every topic renderer with a recorder so routing is measurable."""
    calls = []
    patched = {
        key: (label, (lambda k=key: calls.append(k)))
        for key, (label, _renderer) in DOC_TOPICS.items()
    }
    monkeypatch.setattr(doc_viewer, "DOC_TOPICS", patched)
    return calls


# ─────────────────────────────────────────────────────────────────
# 1. TOPIC CONSTANTS
# ─────────────────────────────────────────────────────────────────
def test_topic_registry_is_consistent():
    """DOC_TOPICS, descriptions and menu rows must stay in sync."""
    assert list(DOC_TOPICS) == list(DOC_TOPIC_DESCRIPTIONS)
    assert len(MENU_OPTIONS) == len(DOC_TOPICS)
    for option in MENU_OPTIONS:
        assert option["label"]
        assert option["description"]
        assert len(option["description"]) <= 60


def test_topic_aliases_resolve_to_known_topics():
    for alias, canonical in TOPIC_ALIASES.items():
        assert canonical in DOC_TOPICS, f"alias '{alias}' → unknown topic '{canonical}'"


def test_menu_number_aliases_map_to_menu_order():
    """`/docs 1..6` must line up with the rows shown in the interactive menu."""
    for idx, key in enumerate(DOC_TOPICS, start=1):
        assert TOPIC_ALIASES[str(idx)] == key
        assert DOC_TOPICS[key][0].startswith(f"{idx}.")


# ─────────────────────────────────────────────────────────────────
# 2. TOPIC ROUTING
# ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("quickstart", "quickstart"),
    ("START", "quickstart"),
    ("mulai", "quickstart"),
    ("1", "quickstart"),
    ("commands", "commands"),
    ("cmd", "commands"),
    ("perintah", "commands"),
    ("2", "commands"),
    ("features", "features"),
    ("fitur", "features"),
    ("3", "features"),
    ("providers", "providers"),
    ("models", "providers"),
    ("free", "providers"),
    ("4", "providers"),
    ("tips", "tips"),
    ("shortcuts", "tips"),
    ("5", "tips"),
    ("all", "all"),
    ("full", "all"),
    ("semua", "all"),
    ("6", "all"),
])
def test_docs_topic_routing(monkeypatch, raw, expected):
    calls = _record_topic_calls(monkeypatch)
    run_doc_command(raw)
    assert calls == [expected]


def test_docs_topic_argument_is_trimmed(monkeypatch):
    calls = _record_topic_calls(monkeypatch)
    run_doc_command("   Tips  ")
    assert calls == ["tips"]


# ─────────────────────────────────────────────────────────────────
# 3. HELP LISTING & UNKNOWN TOPIC
# ─────────────────────────────────────────────────────────────────
def test_docs_help_lists_every_topic(capsys):
    run_doc_command("help")
    out = capsys.readouterr().out
    assert "Topik Dokumentasi" in out
    for key in DOC_TOPICS:
        assert f"/docs {key}" in out


def test_unknown_topic_prints_hint_without_menu(capsys):
    run_doc_command("nonsense")
    out = capsys.readouterr().out
    assert "tidak dikenal" in out
    assert "nonsense" in out
    assert "/docs help" in out


# ─────────────────────────────────────────────────────────────────
# 4. REAL RENDERERS
# ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("topic", list(DOC_TOPICS))
def test_every_topic_renders_documentation(topic, capsys):
    run_doc_command(topic)
    out = capsys.readouterr().out
    assert "Klyro Documentation" in out
    assert "╭" in out and "╰" in out


# ─────────────────────────────────────────────────────────────────
# 5. INTERACTIVE MENU
# ─────────────────────────────────────────────────────────────────
def test_interactive_menu_maps_selection_to_topic(monkeypatch):
    calls = _record_topic_calls(monkeypatch)
    captured = {}

    def fake_select(title, options, default_idx=0):
        captured["title"] = title
        captured["options"] = options
        captured["default_idx"] = default_idx
        return 2

    monkeypatch.setattr(doc_viewer, "interactive_select", fake_select)

    run_doc_command("")
    assert len(captured["options"]) == len(DOC_TOPICS)
    assert captured["default_idx"] == 0
    assert "Dokumentasi" in captured["title"]
    assert calls == [list(DOC_TOPICS)[2]]


def test_interactive_menu_cancel_is_graceful(monkeypatch, capsys):
    monkeypatch.setattr(doc_viewer, "interactive_select", lambda *a, **k: -1)
    run_doc_command()
    out = capsys.readouterr().out
    assert "ditutup" in out


# ─────────────────────────────────────────────────────────────────
# 6. REGISTRATION (COMPLETER, ALIASES, DISPATCHER)
# ─────────────────────────────────────────────────────────────────
def test_docs_registered_in_slash_completer():
    from cli.completer import SLASH_COMMANDS

    cmd_names = [cmd for cmd, _ in SLASH_COMMANDS]
    assert "/docs" in cmd_names


def test_docs_topic_completion():
    from klyro_cli import KlyroCompleter
    from prompt_toolkit.document import Document

    completer = KlyroCompleter(lambda: ".")
    doc = Document("/docs prov", cursor_position=len("/docs prov"))
    completions = [c.text for c in completer.get_completions(doc, None)]
    assert "providers" in completions


def test_docs_registered_as_known_command():
    from commands.aliases import ALL_KNOWN_COMMANDS, COMMON_SLASH_ALIASES, suggest_slash_command

    assert "/docs" in ALL_KNOWN_COMMANDS
    # Fuzzy typo recovery routes users to the docs viewer
    assert suggest_slash_command("/docss") == "/docs"
    # `/doc` (singular) must keep meaning "doctor" so diagnostics never break
    assert COMMON_SLASH_ALIASES["/doc"] == "/doctor"


def test_slash_handler_dispatches_docs(monkeypatch):
    from unittest.mock import MagicMock

    from commands.command_handler import handle_slash_command

    calls = []
    monkeypatch.setattr(doc_viewer, "run_doc_command", lambda args="": calls.append(args))

    folder = handle_slash_command("/docs", "quickstart", ".", MagicMock())
    assert calls == ["quickstart"]
    assert folder == "."

    handle_slash_command("/guide", "tips", ".", MagicMock())
    assert calls == ["quickstart", "tips"]

    handle_slash_command("/manual", "", ".", MagicMock())
    assert calls == ["quickstart", "tips", ""]
