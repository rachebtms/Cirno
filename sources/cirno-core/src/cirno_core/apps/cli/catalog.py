"""CLI App catalogs, cache freshness and asynchronous registry refresh."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import httpx
from cirno_core.apps.cli import contracts, records, resources
from loguru import logger


def _now() -> float:
    return time.time()


class RegistryCatalog:
    def __init__(self, data_dir: Path, runtime: contracts.CliAppsRuntimeConfig):
        self.data_dir = data_dir
        self.runtime = runtime

    def _cache_path(self, source: str) -> Path:
        return self.data_dir / f"{source}_registry_cache.json"

    def _cached_registry(self, cache_path: Path) -> tuple[dict[str, Any] | None, float]:
        cached = records._read_json(cache_path)
        if not cached:
            return None, 0.0
        data = records._as_object_dict(cached.get("data"))
        if data is None:
            return None, 0.0
        try:
            cached_at = float(cached.get("_cached_at", 0))
        except (TypeError, ValueError):
            cached_at = 0.0
        return data, cached_at

    def _fetch_registry(
        self,
        url: str,
        cache_path: Path,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        data, cached_at = self._cached_registry(cache_path)
        if (
            not force_refresh
            and data is not None
            and _now() - cached_at < self.runtime.catalog_ttl_seconds
        ):
            return data

        try:
            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            fetched = records._as_object_dict(response.json())
            if fetched is None:
                raise ValueError("registry response must be an object")
        except Exception as exc:
            if data is not None:
                logger.warning("CLI App catalog refresh failed; using cache for {}: {}", url, exc)
                return data
            raise

        records._write_json(cache_path, {"_cached_at": _now(), "data": fetched})
        return fetched

    async def _fetch_registry_async(
        self,
        url: str,
        cache_path: Path,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        data, cached_at = await asyncio.to_thread(self._cached_registry, cache_path)
        if (
            not force_refresh
            and data is not None
            and _now() - cached_at < self.runtime.catalog_ttl_seconds
        ):
            return data

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url)
            response.raise_for_status()
            fetched = records._as_object_dict(response.json())
            if fetched is None:
                raise ValueError("registry response must be an object")
        except Exception as exc:
            if data is not None:
                logger.warning("CLI App catalog refresh failed; using cache for {}: {}", url, exc)
                return data
            raise

        await asyncio.to_thread(
            records._write_json, cache_path, {"_cached_at": _now(), "data": fetched}
        )
        return fetched

    async def refresh_catalog_cache(self, *, force_refresh: bool = False) -> None:
        for source, url, _raw_base, required in resources._CATALOG_SOURCES:
            try:
                await self._fetch_registry_async(
                    url,
                    self._cache_path(source),
                    force_refresh=force_refresh,
                )
            except Exception as exc:
                if required:
                    raise
                logger.warning("Optional CLI App catalog {} could not refresh: {}", source, exc)

    def catalog(
        self,
        *,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        registries: list[tuple[str, str, dict[str, Any]]] = []
        for source, url, raw_base, required in resources._CATALOG_SOURCES:
            try:
                cache_path = self._cache_path(source)
                if cache_only:
                    registry, _ = self._cached_registry(cache_path)
                    if registry is None:
                        continue
                else:
                    registry = self._fetch_registry(
                        url,
                        cache_path,
                        force_refresh=force_refresh,
                    )
            except Exception as exc:
                if required:
                    raise
                logger.warning("Optional CLI App catalog {} is unavailable: {}", source, exc)
                continue
            registries.append((source, raw_base, registry))
        apps_by_name: dict[str, dict[str, Any]] = {}
        updated_values: list[str] = []
        for source, raw_base, registry in registries:
            meta = records._as_object_dict(registry.get("meta"))
            if meta is not None and isinstance(meta.get("updated"), str):
                updated_values.append(meta["updated"])
            for row in cast(Iterable[object], registry.get("clis", [])):
                entry = records._as_object_dict(row)
                if entry is None or not entry.get("name"):
                    continue
                entry = dict(entry)
                entry["_source"] = source
                entry["_raw_base"] = raw_base
                key = str(entry["name"]).lower()
                previous = apps_by_name.get(key)
                if previous:
                    previous_source = str(previous.get("_source") or source)
                    merged_source = (
                        previous_source
                        if previous_source == source
                        else f"{previous_source}+{source}"
                    )
                    apps_by_name[key] = {**previous, **entry, "_source": merged_source}
                else:
                    apps_by_name[key] = entry
        return list(apps_by_name.values()), max(updated_values) if updated_values else None

    def catalog_cache_fresh(self, *, include_optional: bool = False) -> bool:
        for source, _url, _raw_base, required in resources._CATALOG_SOURCES:
            if not required and not include_optional:
                continue
            data, cached_at = self._cached_registry(self._cache_path(source))
            if data is None or _now() - cached_at >= self.runtime.catalog_ttl_seconds:
                return False
        return True

    def get_app(self, name: str, *, force_refresh: bool = False) -> dict[str, Any]:
        wanted = name.lower()
        for app in self.catalog(force_refresh=force_refresh)[0]:
            if str(app.get("name", "")).lower() == wanted:
                return app
        raise contracts.CliAppError(f"CLI app '{name}' not found", status=404)
