"""The startup welcome line: greets by name only when this profile's memory records one."""

from pathlib import Path

import pytest

from shiina_cli.welcome_line import DEFAULT_WELCOME, get_welcome_text, user_display_name

_BRANDING = "Welcome to Shiina CLI! Type your message or /help for commands."


@pytest.fixture
def memory(tmp_path, monkeypatch):
    """A profile home whose memories/USER.md the test controls."""
    home = tmp_path / ".shiina"
    (home / "memories").mkdir(parents=True)
    monkeypatch.setenv("SHIINA_HOME", str(home))
    return home / "memories" / "USER.md"


def test_greets_by_name_when_memory_records_one(memory):
    memory.write_text("User's name is Daryll\n§\nUser prefers short reports.\n", encoding="utf-8")

    assert user_display_name() == "Daryll"
    assert get_welcome_text(_BRANDING) == "Welcome back, Daryll! Type your message or /help for commands."


@pytest.mark.parametrize("text", ["User's name is Jean-Luc Picard", "the user's name is Ada", "my name is Grace Hopper",
                                 "Name: Katherine"])
def test_name_forms_are_recognised(memory, text):
    memory.write_text(f"{text}\n", encoding="utf-8")

    assert get_welcome_text("").startswith("Welcome back, ")
    assert get_welcome_text("").split(",")[1].split("!")[0].strip().isalpha() or "-" in get_welcome_text("")


def test_falls_back_to_the_default_when_memory_has_no_name(memory):
    memory.write_text("User prefers short reports.\n§\nThe user's editor is Neovim.\n", encoding="utf-8")

    assert user_display_name() == ""
    assert get_welcome_text("") == DEFAULT_WELCOME
    assert get_welcome_text(_BRANDING) == _BRANDING


def test_missing_memory_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIINA_HOME", str(tmp_path / "empty-profile"))  # no memories/ at all

    assert user_display_name() == ""
    assert get_welcome_text("") == DEFAULT_WELCOME


def test_custom_persona_greeting_survives_without_a_name(memory):
    memory.write_text("User's editor is Neovim.\n", encoding="utf-8")

    assert get_welcome_text("Welcome to Ares Agent! ⚔") == "Welcome to Ares Agent! ⚔"


def test_default_welcome_names_the_cli():
    assert DEFAULT_WELCOME == "Welcome to Shiina CLI! Type your message or /help for commands."


def test_default_branding_welcome_is_the_cli_line():
    from shiina_cli.skin_engine import load_skin

    assert "Shiina CLI" in load_skin("default").get_branding("welcome", "")


def test_name_is_scoped_to_the_profile_home(tmp_path, monkeypatch):
    named = tmp_path / "named"
    (named / "memories").mkdir(parents=True)
    (named / "memories" / "USER.md").write_text("User's name is Daryll\n", encoding="utf-8")
    monkeypatch.setenv("SHIINA_HOME", str(named))
    assert user_display_name() == "Daryll"

    monkeypatch.setenv("SHIINA_HOME", str(tmp_path / "other"))  # a profile with no memory
    assert user_display_name() == ""


def test_path_resolution_never_reads_the_real_home(monkeypatch, tmp_path):
    """Guards the fixture's premise: the greeting reads get_shiina_home(), not ~/.shiina."""
    monkeypatch.setenv("SHIINA_HOME", str(tmp_path / "nothing-here"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")

    assert user_display_name() == ""
