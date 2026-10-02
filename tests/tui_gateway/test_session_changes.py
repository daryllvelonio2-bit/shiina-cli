"""``session.changes``: the working-tree change list behind the TUI's collapsed change strip.

The handler is the only place the TUI learns which files moved and by how much, so the contract
pinned here is: a repo cwd answers with per-file counts and totals, a non-repo cwd answers
``repo: False`` (the strip simply does not render), and the git scan is shared between calls.
"""

import threading
import types

import pytest

from tui_gateway import server
from tui_gateway.methods_session import _REPO_STATUS_TTL, _repo_status_cache, _repo_status_cached


def _session(cwd="/tmp/work"):
    return {
        "agent": types.SimpleNamespace(), "session_key": "session-key", "history": [],
        "history_lock": threading.Lock(), "history_version": 0, "running": False,
        "attached_images": [], "image_counter": 0, "cols": 80, "slash_worker": None,
        "show_reasoning": False, "tool_progress_mode": "all", "cwd": cwd,
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    _repo_status_cache.clear()
    yield
    _repo_status_cache.clear()


def _fake_repo_status(cwd):
    assert cwd == "/tmp/work"
    return {
        "branch": "main", "changed": 2, "added": 42, "removed": 7,
        "files": [
            {"path": "src/app.py", "added": 30, "removed": 2, "status": "M"},
            {"path": "src/new.py", "added": 12, "removed": 0, "status": "?"},
        ],
    }


def test_reports_files_and_totals(monkeypatch):
    seen = []

    def _fake(cwd):
        seen.append(cwd)

        return {
            "branch": "main", "changed": 2, "added": 42, "removed": 2,
            "files": [
                {"path": "src/app.py", "added": 30, "removed": 2, "status": "M"},
                {"path": "src/new.py", "added": 12, "removed": 0, "status": "?"},
            ],
        }

    monkeypatch.setattr("shiina_cli.web_git.repo_status", _fake)
    server._sessions["sid"] = _session()
    try:
        resp = server.handle_request({"id": "1", "method": "session.changes", "params": {"session_id": "sid"}})
    finally:
        server._sessions.pop("sid", None)

    result = resp["result"]
    assert len(seen) == 1 and seen[0]  # the session cwd was probed exactly once
    assert result["repo"] is True
    assert result["branch"] == "main"
    assert (result["changed"], result["added"], result["removed"]) == (2, 42, 2)
    assert [f["path"] for f in result["files"]] == ["src/app.py", "src/new.py"]
    assert result["files"][1]["status"] == "?"


def test_totals_match_the_rows_they_summarize(monkeypatch):
    """The collapsed line must equal the sum of the rows the user expands (untracked included)."""
    monkeypatch.setattr("shiina_cli.web_git.repo_status", lambda cwd: {
        "branch": "main", "changed": 1, "added": 3, "removed": 0,
        "files": [{"path": "new.py", "added": 0, "removed": 0, "status": "?"}],
    })
    monkeypatch.setattr("shiina_cli.web_git.fill_untracked_counts",
                        lambda cwd, files: [{**f, "added": 3} for f in files])
    server._sessions["sid"] = _session()
    try:
        resp = server.handle_request({"id": "1", "method": "session.changes", "params": {"session_id": "sid"}})
    finally:
        server._sessions.pop("sid", None)

    result = resp["result"]
    assert (result["changed"], result["added"], result["removed"]) == (1, 3, 0)
    assert result["files"][0]["added"] == result["added"]


def test_non_repo_cwd_reports_no_repo(monkeypatch):
    monkeypatch.setattr("shiina_cli.web_git.repo_status", lambda cwd: None)
    server._sessions["sid"] = _session()
    try:
        resp = server.handle_request({"id": "1", "method": "session.changes", "params": {"session_id": "sid"}})
    finally:
        server._sessions.pop("sid", None)

    assert resp["result"]["repo"] is False
    assert "files" not in resp["result"] or resp["result"]["files"] == []


def test_git_scan_is_shared_between_calls(monkeypatch):
    """The client re-asks at every loop end; one scan must serve the burst."""
    calls = []

    def _counting(cwd):
        calls.append(cwd)

        return {"branch": "main", "changed": 0, "added": 0, "removed": 0, "files": []}

    monkeypatch.setattr("shiina_cli.web_git.repo_status", _counting)

    for _ in range(3):
        _repo_status_cached("/tmp/work")

    assert calls == ["/tmp/work"]
    assert _REPO_STATUS_TTL > 0
