"""Schema configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from cirno_core.config.agents import AgentsConfig
from cirno_core.config.channels import ChannelsConfig
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.network import NetworkConfig
from cirno_core.config.providers import ProviderConfig, ProvidersConfig
from cirno_core.config.server import ServerConfig
from cirno_core.config.tools import ToolsConfig
from pydantic import AliasChoices, Field, PrivateAttr, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class _ExecRuntimeConfigSource(PydanticBaseSettingsSource):
    """Merge shell runtime aliases using the normal settings-source precedence."""

    def __init__(self, source: PydanticBaseSettingsSource) -> None:
        super().__init__(source.settings_cls)
        self._source = source

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self._source.get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        data = self._source()
        tools: object = data.get("tools")
        if not isinstance(tools, dict):
            return data
        tools = cast(dict[str, Any], tools)
        execution: object = tools.get("exec")
        if not isinstance(execution, dict):
            return data
        execution = cast(dict[str, Any], execution)
        aliases = ("maxRuntime", "max_runtime")
        previous_tools: object = self.current_state.get("tools")
        if not any(name in execution for name in aliases) or not isinstance(previous_tools, dict):
            return data
        previous_tools = cast(dict[str, Any], previous_tools)
        previous_execution: object = previous_tools.get("exec")
        if not isinstance(previous_execution, dict):
            return data
        previous_execution = cast(dict[str, Any], previous_execution)
        if not any(name in previous_execution for name in aliases):
            return data
        execution = {name: value for name, value in execution.items() if name not in aliases}
        return {**data, "tools": {**tools, "exec": execution}}


class Config(BaseSettings):
    """Root configuration for cirno."""

    _source_path: Path | None = PrivateAttr(default=None)

    last_run_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices("lastRunVersion", "last_run_version"),
        serialization_alias="lastRunVersion",
    )

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    model_presets: dict[str, ModelPresetConfig] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("modelPresets", "model_presets"),
        serialization_alias="modelPresets",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return tuple(
            _ExecRuntimeConfigSource(source)
            for source in (
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            )
        )

    def bind_source_path(self, path: Path) -> None:
        """Record the config file that owns instance-level runtime data."""
        self._source_path = path.expanduser().resolve(strict=False)

    @property
    def source_path(self) -> Path | None:
        """The instance configuration file, including a custom filename."""
        return self._source_path

    @property
    def runtime_data_dir(self) -> Path | None:
        """Return the active instance data directory when loaded from a config path."""
        return self._source_path.parent / "state" if self._source_path is not None else None

    @model_validator(mode="after")
    def _validate_model_preset(self) -> "Config":
        # Dictionary keys are stable IDs; display names are validated when edited.
        if "default" in self.model_presets:
            raise ValueError("model_preset ID 'default' is reserved for agents.defaults")
        defaults = self.agents.defaults
        for preset in [defaults, *self.model_presets.values()]:
            trigger = (
                preset.idle_compact_percent
                if preset.idle_compact_percent is not None
                else defaults.idle_compact_percent
            )
            keep = (
                preset.idle_compact_keep_percent
                if preset.idle_compact_keep_percent is not None
                else defaults.idle_compact_keep_percent
            )
            if trigger > 0 and keep >= trigger:
                raise ValueError(
                    "Compaction retention percentage must be below its trigger percentage"
                )
        name = self.agents.defaults.model_preset
        if name and name != "default" and name not in self.model_presets:
            raise ValueError(f"model_preset {name!r} not found in model_presets")
        dream_name = self.agents.defaults.dream.model_override
        if dream_name and dream_name != "default" and dream_name not in self.model_presets:
            raise ValueError(f"Dream model preset {dream_name!r} not found in model_presets")
        for fallback in self.agents.defaults.fallback_models:
            if isinstance(fallback, str) and fallback not in self.model_presets:
                raise ValueError(f"fallback_models entry {fallback!r} not found in model_presets")
        return self

    def resolve_default_preset(self) -> ModelPresetConfig:
        """Return the implicit `default` preset from agents.defaults fields."""
        d = self.agents.defaults
        return ModelPresetConfig(
            model=d.model,
            provider=d.provider,
            max_tokens=d.max_tokens,
            context_window_tokens=d.context_window_tokens,
            temperature=d.temperature,
            reasoning_effort=d.reasoning_effort,
            reasoning_history=d.reasoning_history,
            api=d.api,
            idle_compact_percent=d.idle_compact_percent,
            idle_compact_keep_percent=d.idle_compact_keep_percent,
        )

    def resolve_preset(self, name: str | None = None) -> ModelPresetConfig:
        """Return effective model params from a named preset or the implicit default."""
        name = self.agents.defaults.model_preset if name is None else name
        if not name or name == "default":
            return self.resolve_default_preset()
        if name not in self.model_presets:
            raise KeyError(f"model_preset {name!r} not found in model_presets")
        return self.model_presets[name]

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self,
        model: str | None = None,
        *,
        preset: ModelPresetConfig | None = None,
    ) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from cirno_core.providers.registry import PROVIDERS, find_by_name

        resolved = preset or self.resolve_preset()
        forced = resolved.provider

        def _custom_provider_by_name(name: str) -> tuple[ProviderConfig, str] | None:
            normalized = name.replace("-", "_").lower()
            for attr_name, provider in (self.providers.model_extra or {}).items():
                if not isinstance(provider, ProviderConfig):
                    continue
                if attr_name.replace("-", "_").lower() == normalized:
                    return provider, attr_name
            return None

        if forced != "auto":
            spec = find_by_name(forced)
            if spec:
                p = getattr(self.providers, spec.name, None)
                return (p, spec.name) if p else (None, None)
            custom = _custom_provider_by_name(forced)
            if custom is not None:
                return custom
            return None, None

        model_lower = (model or resolved.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")
        prefixed_provider = find_by_name(model_prefix) if model_prefix else None

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        # Explicit provider prefix wins — prevents `github-copilot/...codex` matching openai_codex.
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and model_prefix and normalized_prefix == spec.name:
                if spec.is_oauth or spec.is_local or spec.is_direct or p.api_key:
                    return p, spec.name

        # Check for custom provider by prefix (e.g., "companyProxy/gpt-4").
        # Return the matching provider even when apiBase is missing, so a
        # malformed explicit prefix fails instead of falling through to a
        # different custom provider.
        if model_prefix:
            custom = _custom_provider_by_name(normalized_prefix)
            if custom is not None:
                return custom

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(_kw_matches(kw) for kw in spec.keywords):
                # Local providers (Ollama, vLLM, …) keep model-family keywords
                # like "nemotron" or "llama" to enable bare-model auto-routing,
                # but those keywords collide with cloud-hosted variants of the
                # same family (e.g. `nvidia/nemotron-...` via OpenRouter). Only
                # honor a local keyword match when the user has actually
                # configured that local endpoint via `api_base` — mirrors the
                # gate already used by the local-fallback loop below.
                if spec.is_local:
                    # A qualified model belongs to its explicit provider or a
                    # gateway fallback, never to a different local provider
                    # whose model-family keyword happens to match.
                    foreign_prefix = bool(
                        prefixed_provider is not None and prefixed_provider.name != spec.name
                    )
                    if not p.api_base or foreign_prefix:
                        continue
                if spec.is_oauth or spec.is_local or spec.is_direct or p.api_key:
                    return p, spec.name

        # Fallback: configured local providers can route models without
        # provider-specific keywords (for example plain "llama3.2" on Ollama).
        # Prefer providers whose detect_by_base_keyword matches the configured api_base
        # (e.g. Ollama's "11434" in "http://localhost:11434") over plain registry order.
        local_fallback: tuple[ProviderConfig, str] | None = None
        if prefixed_provider is None:
            for spec in PROVIDERS:
                if not spec.is_local:
                    continue
                p = getattr(self.providers, spec.name, None)
                if not (p and p.api_base):
                    continue
                if spec.detect_by_base_keyword and spec.detect_by_base_keyword in p.api_base:
                    return p, spec.name
                if local_fallback is None:
                    local_fallback = (p, spec.name)
        if local_fallback:
            return local_fallback

        # Fallback: gateways first, then others (follows registry order)
        # OAuth providers are NOT valid fallbacks — they require explicit model selection
        for spec in PROVIDERS:
            if spec.is_oauth:
                continue
            p = getattr(self.providers, spec.name, None)
            if p and p.api_key:
                return p, spec.name

        # Final fallback: check for any configured custom provider
        for attr_name, p in (self.providers.model_extra or {}).items():
            if isinstance(p, ProviderConfig) and p.api_base:
                return p, attr_name

        return None, None

    def get_provider(
        self,
        model: str | None = None,
        *,
        preset: ModelPresetConfig | None = None,
    ) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model, preset=preset)
        return p

    def get_provider_name(
        self,
        model: str | None = None,
        *,
        preset: ModelPresetConfig | None = None,
    ) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model, preset=preset)
        return name

    def get_api_key(
        self,
        model: str | None = None,
        *,
        preset: ModelPresetConfig | None = None,
    ) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model, preset=preset)
        return p.api_key if p else None

    def get_api_base(
        self,
        model: str | None = None,
        *,
        preset: ModelPresetConfig | None = None,
    ) -> str | None:
        """Get API base URL for the given model, falling back to the provider default when present."""
        from cirno_core.providers.registry import find_by_name

        p, name = self._match_provider(model, preset=preset)
        if p and p.api_base:
            return p.api_base
        if name:
            spec = find_by_name(name)
            if spec and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = SettingsConfigDict(
        env_prefix="CIRNO_",
        env_nested_delimiter="__",
    )
