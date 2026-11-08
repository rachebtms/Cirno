"""Owner-requested balance refreshes use the provider's independent endpoint."""

from datetime import datetime, timezone
from pathlib import Path

from cirno_core.config.loader import load_config, resolve_config_env_vars
from cirno_core.providers.balance import BalanceQueryError, query_balance
from cirno_server.webui.settings.contracts import QueryParams, WebUISettingsError, query_first
from cirno_server.webui.settings.providers.state import resolve_settings_provider


def provider_balance_payload(query: QueryParams, *, config_path: Path | None = None) -> dict:
    config = resolve_config_env_vars(load_config(config_path))
    provider_id = query_first(query, "provider_id") or ""
    resolved = resolve_settings_provider(config, provider_id)
    if resolved is None:
        raise WebUISettingsError("Unknown provider", status=404)
    _, provider_id, provider = resolved
    if provider.balance is None:
        return {"provider_id": provider_id, "status": "disabled", "balances": []}
    try:
        balances = query_balance(provider.balance, provider_key=provider.api_key,
                                 proxy=config.network.resolve_proxy(provider.use_proxy))
    except BalanceQueryError as error:
        raise WebUISettingsError(str(error), status=502) from error
    return {"provider_id": provider_id, "status": "ok", "balances": balances,
            "checked_at": datetime.now(timezone.utc).isoformat()}
