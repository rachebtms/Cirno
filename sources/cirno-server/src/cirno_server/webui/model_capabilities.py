"""Owner-requested capability checks against the configured model endpoint."""
import asyncio
from pathlib import Path
from typing import Any

from cirno_core.config.loader import load_config, resolve_config_env_vars
from cirno_core.config.models import ModelPresetConfig
from cirno_core.providers.factory import make_provider
from cirno_core.providers.media_capabilities import probe_visual_inputs
from cirno_core.providers.routing import resolve_automatic_model_api


async def probe_model_capabilities(values: dict[str, Any], *, config_path: Path | None = None) -> dict[str, Any]:
    config = await asyncio.to_thread(load_config, config_path)
    config = resolve_config_env_vars(config.model_copy(deep=True))
    # Probe one endpoint only. A successful fallback is not evidence about this model.
    config.agents.defaults.fallback_models = []
    preset = ModelPresetConfig.model_validate(values["preset"])
    stored = config.model_presets.get(values.get("preset_id", ""))
    if stored and (stored.provider, stored.model) == (preset.provider, preset.model):
        from cirno_server.webui.settings.requests import restore_request_secrets
        preset = preset.model_copy(update={key: restore_request_secrets(getattr(preset, key), getattr(stored, key))
            for key in ("extra_headers", "extra_body", "extra_query") if getattr(preset, key) is not None})
    _, api = resolve_automatic_model_api(config, preset=preset)
    provider = make_provider(config, preset=preset)
    try:
        return await probe_visual_inputs(provider, model=preset.model, video_transport=api == "chat_completions",
            image=preset.image_input is None, video=preset.video_input is None)
    finally:
        await provider.aclose()
