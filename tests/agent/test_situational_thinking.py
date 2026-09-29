"""Tests for situational thinking indicators and big-eye emoticon combinations."""

from types import SimpleNamespace
import pytest

from agent.display import (
    KawaiiSpinner,
    get_agent_display_name,
    get_situational_thinking_status,
)
from agent.turn_iteration_prep import announce_api_call


def _split_status(status: str, name: str = "Shiina") -> tuple[str, str]:
    """Helper to separate emoticon and phrase without splitting on emoticon internal spaces."""
    marker = f" {name} is "
    face, sep, rest = status.partition(marker)
    if sep:
        return face.strip(), f"{name} is {rest}"
    return status.split(" ", 1)


def test_agent_display_name_default():
    """Default display name should be 'Shiina'."""
    assert get_agent_display_name(None) == "Shiina"
    agent = SimpleNamespace()
    assert get_agent_display_name(agent) == "Shiina"


def test_agent_display_name_custom():
    """Custom agent name or persona branding is stripped of ' Agent' suffix."""
    agent = SimpleNamespace(agent_name="Shiina Agent")
    assert get_agent_display_name(agent) == "Shiina"

    agent2 = SimpleNamespace(name="Ares Agent")
    assert get_agent_display_name(agent2) == "Ares"

    agent3 = SimpleNamespace(agent_name="CustomBot")
    assert get_agent_display_name(agent3) == "CustomBot"


def test_planning_situation():
    """Turn 1 with no prior tool calls triggers planning indicator."""
    for _ in range(15):
        status = get_situational_thinking_status(
            agent=None,
            messages=[],
            api_call_count=1,
            approx_tokens=500,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_PLANNING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase for w in ("planning", "brainstorming", "approach", "plan"))


def test_overthinking_forced_big_eyes():
    """Forced overthinking always uses big-eye emoticon and overthinking text."""
    for _ in range(20):
        status = get_situational_thinking_status(
            agent=None,
            messages=[],
            api_call_count=1,
            forced_situation="overthinking",
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_BIG_EYE
        assert "overthinking" in phrase
        assert phrase.startswith("Shiina is ")


def test_overthinking_via_reasoning_effort_and_model():
    """High reasoning effort or reasoning model triggers overthinking."""
    agent = SimpleNamespace(
        reasoning_config={"enabled": True, "effort": "high"},
        model="pixel-canary",
        quiet_mode=True,
    )
    statuses = [
        get_situational_thinking_status(
            agent=agent,
            messages=[],
            api_call_count=3,
        )
        for _ in range(25)
    ]
    overthinking_statuses = [s for s in statuses if "overthinking" in s]
    assert len(overthinking_statuses) > 0
    for s in overthinking_statuses:
        face, phrase = _split_status(s)
        assert face in KawaiiSpinner.KAWAII_BIG_EYE


def test_post_command_review_build():
    """Reviewing build/compiler command output (e.g. npx tsc)."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "run_command", "arguments": '{"command": "npx tsc --noEmit"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Found 0 errors."},
    ]
    for _ in range(10):
        status = get_situational_thinking_status(
            agent=None,
            messages=messages,
            api_call_count=2,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_INSPECTING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase.lower() for w in ("build", "compiler"))


def test_post_command_review_test():
    """Reviewing test command output (e.g. pytest)."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "run_command", "arguments": '{"command": "pytest tests/"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "10 passed"},
    ]
    for _ in range(10):
        status = get_situational_thinking_status(
            agent=None,
            messages=messages,
            api_call_count=2,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_INSPECTING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase.lower() for w in ("test", "testing"))


def test_post_edit_review():
    """Reviewing file changes/diffs after patch or edit."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "patch", "arguments": '{"file": "app.tsx"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Successfully patched app.tsx"},
    ]
    for _ in range(10):
        status = get_situational_thinking_status(
            agent=None,
            messages=messages,
            api_call_count=2,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_INSPECTING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase.lower() for w in ("changes", "diff", "edits", "file", "modifications"))


def test_post_read_inspection():
    """Inspecting code after viewing/grepping files."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "view_file", "arguments": '{"path": "display.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "file content here..."},
    ]
    for _ in range(10):
        status = get_situational_thinking_status(
            agent=None,
            messages=messages,
            api_call_count=2,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_INSPECTING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase.lower() for w in ("code", "files", "codebase", "source", "project"))


def test_post_error_debugging():
    """Diagnosing/debugging after tool failure."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "run_command", "arguments": '{"command": "python broken.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Traceback (most recent call last):\nError: fail"},
    ]
    for _ in range(10):
        status = get_situational_thinking_status(
            agent=None,
            messages=messages,
            api_call_count=2,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_DEBUGGING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase.lower() for w in ("diagnosing", "debugging", "troubleshooting", "wrong", "error"))


def test_announce_api_call_forwards_situational_text():
    """announce_api_call passes situational status string to thinking_callback."""
    captured = []
    agent = SimpleNamespace(
        quiet_mode=True,
        thinking_callback=captured.append,
        _has_stream_consumers=lambda: True,
        verbose_logging=False,
    )
    announce_api_call(
        agent,
        messages=[],
        api_messages=[],
        api_call_count=1,
        approx_tokens=100,
        total_chars=400,
    )
    assert len(captured) == 1
    assert captured[0].startswith("(")
    assert "Shiina is " in captured[0]


def test_cooking_forced_situation():
    """Forced cooking situation uses cooking face and cooking/focus phrases."""
    for _ in range(25):
        status = get_situational_thinking_status(
            agent=None,
            messages=[],
            api_call_count=2,
            forced_situation="cooking",
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_COOKING
        assert phrase.startswith("Shiina is ")
        assert any(
            w in phrase.lower()
            for w in (
                "cooking",
                "locked in",
                "zone",
                "simmer",
                "whipping up",
                "laser-focused",
                "brewing",
                "cylinders",
                "pathways",
                "gears",
                "deep focus",
                "puzzle",
                "magic",
                "brainpower",
                "galaxy-braining",
            )
        )


def test_reasoning_effort_variety():
    """Reasoning models produce a variety of cooking and overthinking phrases."""
    agent = SimpleNamespace(
        reasoning_config={"enabled": True, "effort": "high"},
        model="pixel-canary",
        quiet_mode=True,
    )
    statuses = [
        get_situational_thinking_status(
            agent=agent,
            messages=[],
            api_call_count=3,
        )
        for _ in range(40)
    ]
    overthinking_statuses = [s for s in statuses if "overthinking" in s]
    cooking_statuses = [
        s
        for s in statuses
        if any(
            w in s.lower()
            for w in (
                "cooking",
                "locked in",
                "zone",
                "simmer",
                "whipping up",
                "laser-focused",
                "brewing",
                "cylinders",
                "focus",
                "magic",
                "brainpower",
            )
        )
    ]
    # Must have both overthinking and cooking/focus variety, not just one repeated line
    assert len(overthinking_statuses) > 0
    assert len(cooking_statuses) > 0


def test_tool_round_preserved_with_reasoning_model():
    """Tool rounds (e.g. edit/command) are preserved even when using reasoning models."""
    agent = SimpleNamespace(
        reasoning_config={"enabled": True, "effort": "high"},
        model="pixel-canary",
        quiet_mode=True,
    )
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "patch", "arguments": '{"file": "main.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Applied patch"},
    ]
    for _ in range(15):
        status = get_situational_thinking_status(
            agent=agent,
            messages=messages,
            api_call_count=3,
        )
        face, phrase = _split_status(status)
        assert face in KawaiiSpinner.KAWAII_INSPECTING
        assert phrase.startswith("Shiina is ")
        assert any(w in phrase.lower() for w in ("changes", "diff", "edits", "file", "modifications"))
