from __future__ import annotations

from typing import Any

import pytest

from cirno.config.schema import Config
from cirno.webui.settings.capabilities import capability_settings_payload, update_network_safety_settings, update_web_search_settings
from cirno.webui.settings.contracts import WebUISettingsError
from cirno.webui.settings.models import create_provider_settings, update_provider_settings






def _oauth_status(_spec: Any) -> dict[str, Any]:
    return {"configured": False}


