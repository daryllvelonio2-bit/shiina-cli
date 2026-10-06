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

BUILTINS = ("default", "minimal", "studio", "timeline")


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


def test_default_declares_nothing_so_wearing_it_is_a_no_op():
    design = de.load_design("default")

    assert design.is_empty()
    # `{}` on the wire, not an empty object: the renderer maps it to null and the
    # theme keeps referential equality instead of rebuilding every frame.
    assert de.DesignConfig(name="default").to_payload() == {"name": "default", "colors": {}}


def test_the_makeovers_carry_a_complete_look():
    for name in ("minimal", "studio", "timeline"):
        design = de.load_design(name)

        assert not design.is_empty()
        assert design.prompt, "a makeover must set its own prompt symbol"
        assert design.colors, "a makeover must carry a palette"
        assert design.design.get("glyphs"), "a makeover must set a glyph vocabulary"
        assert design.spinner.get("think") and design.spinner.get("tool")
        assert design.layout.get("regions") and design.layout.get("sections")


def test_unknown_name_falls_back_to_default_rather_than_failing():
    design = de.load_design("no-such-design")

    assert design.name == "default"
    assert design.is_empty()


def test_a_user_file_shadows_its_builtin(designs_dir):
    _write(designs_dir, "timeline", """
        name: timeline
        prompt: 'MINE'
        colors:
          accent: '#123456'
    """)

    design = de.load_design("timeline")

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

    assert design.name == "default"


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
    written = de.ensure_designs_dir()
    assert set(written) >= set(BUILTINS)

    # An edit must survive a re-seed: these files belong to the user.
    (designs_dir / "timeline.yaml").write_text("name: timeline\nprompt: 'MINE'\n", encoding="utf-8")
    again = de.ensure_designs_dir()

    assert "timeline" not in again
    assert de.load_design("timeline").prompt == "MINE"

    # --force is the documented way to discard local edits.
    forced = de.ensure_designs_dir(overwrite=True)

    assert "timeline" in forced
    assert de.load_design("timeline").prompt != "MINE"


def test_design_names_lists_builtins_sorted():
    names = de.design_names()

    assert names == sorted(names)
    assert set(names) >= set(BUILTINS)
