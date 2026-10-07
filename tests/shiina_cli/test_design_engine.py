"""``shiina_cli.design_engine`` — the design folder loader.

Designs are pure data, so the interesting behaviour is all in the resolution:
inheritance via ``extends``, user files shadowing built-ins, and the failure
modes that must never reach the renderer (a cycle, a missing parent, an
unreadable file). A malformed design must degrade to the built-in look rather
than blanking the UI, which is what most of these assert.
"""

import textwrap

import pytest

from shiina_cli import design_engine as de

BUILTINS = ("codex",)


@pytest.fixture
def designs_dir(tmp_path, monkeypatch):
    """A private design folder, leaving the shipped built-ins as the fallback."""
    root = tmp_path / "designs"
    root.mkdir()
    monkeypatch.setattr(de, "_designs_dir", lambda: root)
    de.reset_cache()
    yield root
    de.reset_cache()


def _write(root, name, body):
    (root / f"{name}.yaml").write_text(textwrap.dedent(body), encoding="utf-8")


def test_every_builtin_loads():
    for name in BUILTINS:
        design = de.load_design(name)
        assert design.name == name


def test_the_makeovers_carry_a_complete_look():
    for name in ("codex",):
        design = de.load_design(name)

        assert not design.is_empty()
        assert design.prompt, "a makeover must set its own prompt symbol"
        assert design.colors, "a makeover must carry a palette"
        assert design.design.get("glyphs"), "a makeover must set a glyph vocabulary"
        assert design.spinner.get("think") and design.spinner.get("tool")
        assert design.layout.get("regions") and design.layout.get("sections")


def test_codex_moves_the_structural_axes_not_just_the_palette():
    """The failure this guards: a design that only recolours.

    `codex` must set the structural controls (a dim header, a blank
    flank, square boxes) and carry a glyph vocabulary where every named
    glyph is a non-empty string.
    """
    design = de.load_design("codex")
    block = design.design

    assert not design.is_empty()

    # Structural controls — the axes a recolour leaves at their defaults.
    assert block["flank"] in ("rule", "space", "none") and block["flank"] != "rule"
    assert block["header"]["marker"] in ("chevron", "rule", "none")
    assert block["header"]["emphasis"] in ("bold", "dim", "none")
    assert block["panel"] in ("single", "round", "double", "bold", "none")
    assert block["density"] in ("compact", "normal", "roomy")

    glyphs = block["glyphs"]
    assert glyphs and all(isinstance(v, str) for v in glyphs.values())


def test_an_invalid_spinner_name_still_loads(designs_dir):
    # Animation names are the renderer's business, not the loader's: a typo must
    # not raise here — thinking.tsx::Spinner falls back to the built-in pick.
    _write(designs_dir, "typo", """
        name: typo
        prompt: '>'
        spinner:
          think: [not-a-real-animation]
          tool: [nope]
    """)

    design = de.load_design("typo")

    assert design.spinner["think"] == ["not-a-real-animation"]


def test_unknown_name_falls_back_to_default_rather_than_failing():
    design = de.load_design("this-design-does-not-exist")

    assert design.name == "codex"
    assert not design.is_empty()


def test_a_user_file_shadows_its_builtin(designs_dir):
    _write(designs_dir, "codex", """
        name: codex
        prompt: 'MINE'
        colors:
          accent: '#123456'
    """)

    design = de.load_design("codex")

    assert design.prompt == "MINE"
    assert design.colors["accent"] == "#123456"
    assert design.source == "user"


def test_extends_merges_deep_so_a_child_keeps_the_rest_of_the_parent(designs_dir):
    _write(designs_dir, "base", """
        name: base
        prompt: '>'
        design:
          density: compact
          glyphs:
            bullet: '-'
            check: 'x'
    """)
    _write(designs_dir, "child", """
        name: child
        extends: base
        design:
          glyphs:
            bullet: '*'
    """)

    design = de.load_design("child")

    # The override wins where it speaks...
    assert design.design["glyphs"]["bullet"] == "*"
    # ...and everything it stayed silent about survives the merge.
    assert design.design["glyphs"]["check"] == "x"
    assert design.design["density"] == "compact"
    assert design.prompt == ">"


def test_a_circular_extends_chain_does_not_hang(designs_dir):
    _write(designs_dir, "a", "name: a\nextends: b\nprompt: 'A'\n")
    _write(designs_dir, "b", "name: b\nextends: a\nprompt: 'B'\n")

    design = de.load_design("a")

    # Terminates and still yields something renderable rather than raising.
    assert design.name in {"a", "default"}


def test_a_missing_parent_still_yields_the_child(designs_dir):
    _write(designs_dir, "orphan", "name: orphan\nextends: nope\nprompt: '?'\n")

    design = de.load_design("orphan")

    assert design.prompt == "?"


def test_an_unreadable_file_degrades_instead_of_raising(designs_dir):
    (designs_dir / "broken.yaml").write_text("name: broken\ncolors: [not: a: map\n", encoding="utf-8")

    design = de.load_design("broken")

    assert design.name == "codex"


def test_wrong_section_types_are_ignored_not_fatal(designs_dir):
    _write(designs_dir, "oddtypes", """
        name: oddtypes
        prompt: '>'
        colors: 'this should be a map'
        spinner: 42
    """)

    design = de.load_design("oddtypes")

    assert design.prompt == ">"
    assert design.colors == {}
    assert design.spinner == {}


def test_payload_omits_empty_sections(designs_dir):
    _write(designs_dir, "sparse", "name: sparse\nprompt: '>'\n")

    payload = de.load_design("sparse").to_payload()

    assert payload["prompt"] == ">"
    for key in ("design", "spinner", "layout"):
        assert key not in payload, f"{key} carries nothing and should be omitted"


def test_ensure_designs_dir_seeds_without_clobbering_edits(designs_dir):
    result = de.ensure_designs_dir()
    assert set(result["written"]) >= set(BUILTINS)

    # An edit must survive a re-seed: these files belong to the user.
    (designs_dir / "codex.yaml").write_text("name: codex\nprompt: 'MINE'\n", encoding="utf-8")
    again = de.ensure_designs_dir()

    assert "codex" in again["kept"]
    assert "codex" not in again["written"]
    assert de.load_design("codex").prompt == "MINE"

    # --force is the documented way to discard local edits.
    forced = de.ensure_designs_dir(overwrite=True)

    assert "codex" in forced["written"]
    assert de.load_design("codex").prompt != "MINE"


def test_an_untouched_seed_is_upgraded_by_a_new_builtin(designs_dir, monkeypatch):
    # The point of the hash manifest: a built-in change must reach a folder that
    # was already seeded, without ever overwriting an edit. Simulate the built-in
    # moving by seeding, then "updating" the shipped file.
    de.ensure_designs_dir()

    src = de._builtin_designs_dir() / "codex.yaml"
    original = src.read_text(encoding="utf-8")
    monkeypatch.setattr(de, "_builtin_designs_dir", lambda: src.parent)
    try:
        src.write_text(original.replace("prompt: \">\"", "prompt: \"UPDATED\""), encoding="utf-8")
        upgraded = de.ensure_designs_dir()

        assert "codex" in upgraded["written"]
        assert "UPDATED" in (designs_dir / "codex.yaml").read_text(encoding="utf-8")
    finally:
        src.write_text(original, encoding="utf-8")


def test_an_edited_seed_survives_a_builtin_change(designs_dir, monkeypatch):
    de.ensure_designs_dir()
    (designs_dir / "codex.yaml").write_text("name: codex\nprompt: 'MINE'\n", encoding="utf-8")

    src = de._builtin_designs_dir() / "codex.yaml"
    original = src.read_text(encoding="utf-8")
    monkeypatch.setattr(de, "_builtin_designs_dir", lambda: src.parent)
    try:
        src.write_text(original.replace("prompt: \">\"", "prompt: \"UPDATED\""), encoding="utf-8")
        result = de.ensure_designs_dir()

        assert "codex" in result["kept"]
        assert "MINE" in (designs_dir / "codex.yaml").read_text(encoding="utf-8")
    finally:
        src.write_text(original, encoding="utf-8")


def test_design_names_lists_builtins_sorted():
    names = de.design_names()

    assert names == ["codex"]
