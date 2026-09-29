"""Plain-language contracts for shiina_state user-facing errors (CLI UX message campaign, cluster D)."""

import shiina_state
from shiina_state import SessionResumeTooLargeError, format_session_db_unavailable


def test_resume_too_large_names_export_and_config_commands():
    text = str(SessionResumeTooLargeError(4312, 4000))
    assert "4312" in text and "4000" in text
    assert "shiina sessions export" in text
    assert "shiina config set sessions.max_resume_messages 0" in text
    for jargon in ("lineage", "guard", "safe resume limit"):
        assert jargon not in text


def test_resume_too_large_keeps_structured_fields():
    exc = SessionResumeTooLargeError(20_001, 20_000, scope="in its tip segment")
    assert (exc.message_count, exc.limit) == (20_001, 20_000)
    assert isinstance(exc, ValueError)


def test_db_unavailable_points_to_doctor_without_sqlite_internals():
    shiina_state._set_last_init_error("OperationalError: database is locked")
    try:
        text = format_session_db_unavailable(details=True)
    finally:
        shiina_state._set_last_init_error(None)
    lead, *rest = text.splitlines()
    assert "session history" in lead
    assert "will not be saved" in lead.lower()
    for internal in ("sqlite.org", "WAL", "NFS/SMB/FUSE/ZFS"):
        assert internal not in lead
    assert rest and rest[0].startswith("Details: ") and "database is locked" in rest[0]


def test_db_unavailable_is_one_line_for_chat_surfaces_by_default():
    shiina_state._set_last_init_error("OperationalError: database is locked")
    try:
        text = format_session_db_unavailable(prefix="Cannot resume")
    finally:
        shiina_state._set_last_init_error(None)
    assert "\n" not in text
    assert "Details:" not in text
    assert text.startswith("Cannot resume:")


def test_db_unavailable_unknown_cause_on_network_drive_points_at_moving_not_doctor_fix():
    shiina_state._set_last_init_error("OperationalError: locking protocol")
    try:
        text = format_session_db_unavailable()
    finally:
        shiina_state._set_last_init_error(None)
    assert "network" in text
    assert "local disk" in text
    assert "shiina doctor --fix" not in text


def test_db_unavailable_without_cause_still_names_doctor():
    shiina_state._set_last_init_error(None)
    text = format_session_db_unavailable(details=True)
    assert "shiina doctor" in text
    assert "will not be saved" in text.lower()
    assert "Details:" not in text


def test_db_unavailable_commands_are_pinned_to_the_failing_profile(monkeypatch, tmp_path):
    """Both fallbacks that bypass the shared cause table (no cause; network-drive gloss) name the
    profile whose store failed, like the table's actions do."""
    from shiina_constants import profile_cli_selector

    monkeypatch.setenv("SHIINA_HOME", str(tmp_path / ".shiina" / "profiles" / "research"))
    selector = profile_cli_selector()
    assert selector.strip()
    shiina_state._set_last_init_error(None)
    no_cause = format_session_db_unavailable()
    shiina_state._set_last_init_error("OperationalError: locking protocol")
    try:
        network = format_session_db_unavailable()
    finally:
        shiina_state._set_last_init_error(None)
    for text in (no_cause, network):
        assert f"`shiina {selector}doctor`" in text and "`shiina doctor`" not in text
        assert "{profile_arg}" not in text
