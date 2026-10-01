"""Vision / Image Analysis setup section for `shiina setup vision`."""

from shiina_cli.cli_output import print_info as _print_info, print_success as _print_success
from shiina_cli.colors import Colors, color
from shiina_cli.config import load_config, save_config
from shiina_cli.tools_config_providers import _configure_vision_backend


def setup_vision(config: dict) -> None:
    """Configure vision/image analysis backend (auxiliary.vision.provider/model)."""
    from shiina_cli.setup import print_header, _info
    print_header("Vision / Image Analysis")
    _info(
        "Vision tasks (image analysis, vision_analyze tool) use a multimodal model.",
        "This can be different from your main chat model.",
        "Guide: https://shiina-agent.nousresearch.com/docs/user-guide/features/vision",
        None,
    )
    _configure_vision_backend()
    # Reload config since _configure_vision_backend does its own load/save cycle
    config.clear()
    config.update(load_config())
    save_config(config)