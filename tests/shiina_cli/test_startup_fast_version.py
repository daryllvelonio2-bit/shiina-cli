"""Invariant tests for the pre-import ``shiina --version`` fast path.

``shiina_cli._startup_fast`` runs BEFORE main.py's heavy import wall, so its version path must not
import ``shiina_cli.config`` (which drags in yaml/argparse/plugins and costs ~800 ms — the reason
``shiina --version`` was slow). Its stdlib install-method resolver must also agree with the
authoritative ``shiina_cli.config.detect_install_method`` so the two cannot silently drift and print
a wrong install method / update command.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_fast_version_does_not_import_config():
    """A subprocess that runs only the fast path must load neither config nor yaml."""
    probe = (
        "import sys\n"
        "from shiina_cli import _startup_fast as s\n"
        "assert s.try_fast_version(['--version'])\n"
        "print('config_loaded', 'shiina_cli.config' in sys.modules)\n"
        "print('yaml_loaded', 'yaml' in sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            timeout=60, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert "config_loaded False" in result.stdout, result.stdout
    assert "yaml_loaded False" in result.stdout, result.stdout


def _tree(tmp_path, name, *, stamp=None, with_git_dir=False):
    tree = tmp_path / name
    tree.mkdir()
    if stamp is not None:
        (tree / ".install_method").write_text(stamp + "\n", encoding="utf-8")
    if with_git_dir:
        (tree / ".git").mkdir()
    return tree


def test_fast_detect_install_method_matches_config(tmp_path, monkeypatch):
    """The stdlib resolver agrees with config.detect_install_method on stamp / .git / bare trees."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SHIINA_HOME", str(home))
    monkeypatch.delenv("SHIINA_MANAGED", raising=False)
    monkeypatch.delenv("SHIINA_REVISION", raising=False)

    from shiina_cli import _startup_fast
    from shiina_cli.config import detect_install_method as config_detect

    for tree in (
        _tree(tmp_path, "stamped", stamp="git"),
        _tree(tmp_path, "gitdir", with_git_dir=True),
        _tree(tmp_path, "bare"),
    ):
        assert _startup_fast.detect_install_method(str(tree)) == config_detect(tree), tree
