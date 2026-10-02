"""The startup welcome line — greets the user by name when the profile's memory knows one.

The name comes from the profile's own ``memories/USER.md`` (the user profile the agent curates):
only a name the user actually stated is used, and nothing else is inferred from the file.
"""

import logging
import re

from shiina_constants import get_shiina_home

logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "Welcome to Shiina CLI! Type your message or /help for commands."
_TAIL = " Type your message or /help for commands."

# Ordered: the explicit "my name is X" forms before an incidental "Name: X" line.
_NAME_PATTERNS = (
    re.compile(r"\buser'?s name is ([\w][\w'\-]{0,23})", re.I),
    re.compile(r"\b(?:my name is|i am|i'm|call me) ([\w][\w'\-]{0,23})", re.I),
    re.compile(r"^name\s*[:=]\s*([\w][\w'\-]{0,23})", re.I | re.M),
)


def user_display_name() -> str:
    """The first name recorded in this profile's USER.md, or "" when memory has none."""
    try:
        text = (get_shiina_home() / "memories" / "USER.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip("'-")
    return ""


def get_welcome_text(branding_welcome: str = "") -> str:
    """Name-aware welcome: "Welcome back, <name>!" once memory knows a name, else the default.

    ``branding_welcome`` is the active skin's own greeting (a custom persona keeps its wording).
    """
    name = user_display_name()
    if name:
        return f"Welcome back, {name}!{_TAIL}"
    return (branding_welcome or "").strip() or DEFAULT_WELCOME
