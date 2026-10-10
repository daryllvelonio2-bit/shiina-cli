"""Regression: attaching an image in the CLI must not die before the turn starts.

``_chat_route_images`` builds the persisted ``@image:<path>`` override by passing its
``Path`` images through ``context_references.format_reference_value`` (declared
``value: str``). A ``Path`` raised ``TypeError: expected string or bytes-like object``
inside that block — which only runs when images are attached, so plain text turns looked
fine while every attach produced no response and no analysis.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent import image_routing
from cli import ShiinaCLI


def _make_cli() -> ShiinaCLI:
    cli_obj = ShiinaCLI.__new__(ShiinaCLI)
    cli_obj.model = "gpt-4o-mini"
    cli_obj.provider = "openai"
    cli_obj.requested_provider = ""
    return cli_obj


def _make_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


class TestRouteImagesPersistOverride:
    def test_accepts_path_images_and_records_image_references(self, tmp_path):
        img = _make_image(tmp_path / "shot.png")
        cli_obj = _make_cli()
        agent = SimpleNamespace()

        with (
            patch.object(image_routing, "decide_image_input_mode", return_value="text"),
            patch.object(ShiinaCLI, "_preprocess_images_with_vision", return_value="PRE look"),
        ):
            message = cli_obj._chat_route_images("look", [img], agent=agent)

        assert message == "PRE look"
        override = agent._persist_user_message_override
        assert override.startswith("look\n@image:")
        assert str(img) in override
