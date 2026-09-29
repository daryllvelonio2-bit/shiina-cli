from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    # The launchers live in the managed binary dir OUTSIDE the git checkout
    # (SHIINA_HOME\bin, next to the managed uv) — NOT the whole venv\Scripts
    # (which would shadow the user's python, #83797) and NOT a dir inside
    # the checkout (which `shiina update`'s autostash swept off disk).
    assert "%LOCALAPPDATA%\\shiina\\bin" in doc
    assert (
        "Get-Command shiina        # should print "
        "C:\\Users\\<you>\\AppData\\Local\\shiina\\bin\\shiina.exe"
    ) in doc
    # Installer exposes $ShiinaHome\bin, and must copy the launchers into it.
    assert '$shiinaBin = "$ShiinaHome\\bin"' in install
    assert "shiina.exe" in install and "shiina-acp.exe" in install
    # Guard against regressions to either legacy layout.
    assert '$shiinaBin = "$InstallDir\\venv\\Scripts"' not in install
    assert '$shiinaBin = "$InstallDir\\bin"' not in install
