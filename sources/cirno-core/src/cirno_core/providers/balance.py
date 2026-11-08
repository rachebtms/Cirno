"""Read account balances without coupling them to inference requests."""

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from cirno_core.config.balance import ProviderBalanceConfig


class BalanceQueryError(ValueError):
    """A balance endpoint failed or returned an unsupported payload."""


def _amount(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise BalanceQueryError("The balance field is not a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise BalanceQueryError("The balance field is not a number") from error
    if not number.is_finite():
        raise BalanceQueryError("The balance field must be finite")
    return str(number)


def _pointer(payload: object, path: str) -> object:
    current = payload
    try:
        for token in path.split("/")[1:] if path else []:
            if re.search(r"~(?![01])", token):
                raise ValueError(token)
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token):
                    raise ValueError(token)
                current = current[int(token)]
            elif isinstance(current, dict):
                current = current[token]
            else:
                raise KeyError(token)
    except (KeyError, IndexError, ValueError) as error:
        raise BalanceQueryError(f"Balance field not found at {path}") from error
    return current


def query_balance(
    settings: ProviderBalanceConfig, *, provider_key: str | None,
    proxy: str | None = None, http_get: Callable[..., httpx.Response] = httpx.get,
) -> list[dict[str, str]]:
    headers = {"Accept": "application/json"}
    credential = settings.api_key or provider_key
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    try:
        response = http_get(settings.endpoint, headers=headers, timeout=10.0,
                            follow_redirects=False, **({"proxy": proxy, "trust_env": False} if proxy else {}))
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise BalanceQueryError(f"Balance request failed with HTTP {error.response.status_code}") from None
    except httpx.HTTPError:
        raise BalanceQueryError("Could not reach the balance endpoint") from None
    try:
        payload: Any = response.json()
    except ValueError:
        raise BalanceQueryError("The balance endpoint did not return JSON") from None
    if settings.format == "json":
        return [{"amount": _amount(_pointer(payload, settings.amount_path)), "currency": settings.currency}]
    rows = payload.get("balance_infos") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise BalanceQueryError("The DeepSeek response has no balance_infos")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("currency"), str) or not row["currency"]:
            raise BalanceQueryError("The balance response is missing its currency")
        result.append({"amount": _amount(row.get("total_balance")), "currency": row["currency"]})
    return result
