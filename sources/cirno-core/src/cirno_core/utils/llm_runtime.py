"""Immutable execution settings for one LLM turn."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from cirno_core.providers.base import LLMProvider
from cirno_core.providers.generation import GenerationSettings

if TYPE_CHECKING:
    from cirno_core.providers.factory import ProviderSnapshot


@dataclass(frozen=True, slots=True)
class LLMRuntime:
    """One captured provider/model configuration used for an entire execution.

    The provider itself is stateful, but all mutable selection and generation
    values are copied into this frozen value.  Consumers must use these fields
    instead of consulting ``provider.generation`` after admission.
    """

    provider: LLMProvider
    model: str
    generation: GenerationSettings
    context_window_tokens: int
    model_preset: str | None = None
    snapshot_signature: tuple[object, ...] | None = None
    idle_compact_percent: float | None = None
    idle_compact_keep_percent: float | None = None
    active_compact_percent: int = 100
    compaction_max_tokens: int = 8192
    compaction_max_retries: int = 1
    compaction_reasoning_effort: str = "low"
    checkpoint_reminder_percent: int = 85
    output_reserve_percent: int = 5
    consolidation_learn: bool = True
    consolidation_max_updates: int = 8
    consolidation_context_chars: int = 16000

    @classmethod
    def capture(
        cls,
        provider: LLMProvider,
        model: str,
        *,
        context_window_tokens: int,
        model_preset: str | None = None,
        snapshot_signature: tuple[object, ...] | None = None,
    ) -> LLMRuntime:
        """Capture provider defaults without retaining mutable generation state."""
        defaults = GenerationSettings()
        generation = getattr(provider, "generation", defaults)
        return cls(
            provider=provider,
            model=model,
            generation=GenerationSettings(
                temperature=getattr(generation, "temperature", defaults.temperature),
                max_tokens=getattr(generation, "max_tokens", defaults.max_tokens),
                reasoning_effort=getattr(
                    generation,
                    "reasoning_effort",
                    defaults.reasoning_effort,
                ),
            ),
            context_window_tokens=context_window_tokens,
            model_preset=model_preset,
            snapshot_signature=snapshot_signature,
        )

    def with_generation_overrides(
        self,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMRuntime:
        """Return a derived runtime for explicit per-run generation overrides."""
        generation = self.generation
        return replace(
            self,
            generation=GenerationSettings(
                temperature=(
                    generation.temperature if temperature is None else temperature
                ),
                max_tokens=generation.max_tokens if max_tokens is None else max_tokens,
                reasoning_effort=(
                    generation.reasoning_effort
                    if reasoning_effort is None
                    else reasoning_effort
                ),
            ),
        )


def runtime_from_provider_snapshot(
    snapshot: ProviderSnapshot,
) -> LLMRuntime:
    """Convert a provider factory snapshot into the canonical runtime value."""
    if snapshot.generation is not None:
        return LLMRuntime(
            provider=snapshot.provider,
            model=snapshot.model,
            generation=snapshot.generation,
            context_window_tokens=snapshot.context_window_tokens,
            model_preset=snapshot.model_preset,
            snapshot_signature=snapshot.signature,
            idle_compact_percent=snapshot.idle_compact_percent,
            idle_compact_keep_percent=snapshot.idle_compact_keep_percent,
            active_compact_percent=snapshot.active_compact_percent,
            compaction_max_tokens=snapshot.compaction_max_tokens,
            compaction_max_retries=snapshot.compaction_max_retries,
            compaction_reasoning_effort=snapshot.compaction_reasoning_effort,
            checkpoint_reminder_percent=snapshot.checkpoint_reminder_percent,
            output_reserve_percent=snapshot.output_reserve_percent,
            consolidation_learn=snapshot.consolidation_learn,
            consolidation_max_updates=snapshot.consolidation_max_updates,
            consolidation_context_chars=snapshot.consolidation_context_chars,
        )
    return replace(LLMRuntime.capture(
        snapshot.provider,
        snapshot.model,
        context_window_tokens=snapshot.context_window_tokens,
        model_preset=snapshot.model_preset,
        snapshot_signature=snapshot.signature,
    ), active_compact_percent=snapshot.active_compact_percent,
       compaction_max_tokens=snapshot.compaction_max_tokens, compaction_max_retries=snapshot.compaction_max_retries, compaction_reasoning_effort=snapshot.compaction_reasoning_effort,
       checkpoint_reminder_percent=snapshot.checkpoint_reminder_percent,
       output_reserve_percent=snapshot.output_reserve_percent,
       consolidation_learn=snapshot.consolidation_learn,
       consolidation_max_updates=snapshot.consolidation_max_updates,
       consolidation_context_chars=snapshot.consolidation_context_chars)
