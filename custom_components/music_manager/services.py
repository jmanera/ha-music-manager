"""Actions: search Soulseek from automations and scripts, and download the best match."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import MusicManagerError, MusicManagerNotFoundError
from .const import (
    ATTR_FREE_SLOT_ONLY,
    ATTR_LIMIT,
    ATTR_LOSSLESS_ONLY,
    ATTR_MIN_TRACKS,
    ATTR_QUERY,
    ATTR_SEARCH_TIME,
    DOMAIN,
    SERVICE_DOWNLOAD_BEST,
    SERVICE_SEARCH,
)
from .coordinator import MusicManagerCoordinator

_FILTERS = {
    probatio.Required(ATTR_QUERY): probatio.All(cv.string, probatio.Length(min=2, max=200)),
    probatio.Optional(ATTR_LOSSLESS_ONLY, default=False): cv.boolean,
    probatio.Optional(ATTR_FREE_SLOT_ONLY, default=False): cv.boolean,
    probatio.Optional(ATTR_MIN_TRACKS, default=1): probatio.All(
        probatio.Coerce(int), probatio.Range(min=1, max=100)
    ),
    probatio.Optional(ATTR_SEARCH_TIME, default=20): probatio.All(
        probatio.Coerce(float), probatio.Range(min=5, max=120)
    ),
}
SEARCH_SCHEMA = probatio.Schema(
    {
        **_FILTERS,
        probatio.Optional(ATTR_LIMIT, default=10): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=50)
        ),
    }
)
DOWNLOAD_BEST_SCHEMA = probatio.Schema(_FILTERS)


def _coordinator(hass: HomeAssistant) -> MusicManagerCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    coordinator: MusicManagerCoordinator = entries[0].runtime_data
    return coordinator


def _arguments(call: ServiceCall) -> tuple[str, float, dict[str, Any]]:
    data = dict(call.data)
    return data.pop(ATTR_QUERY), data.pop(ATTR_SEARCH_TIME), data


async def _search(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call.hass)
    query, search_time, filters = _arguments(call)
    try:
        return await coordinator.api.search(query, search_time, **filters)
    except MusicManagerError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="request_failed",
            translation_placeholders={"error": str(err)},
        ) from err


async def _download_best(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call.hass)
    query, search_time, filters = _arguments(call)
    try:
        result = await coordinator.api.download_best(query, search_time, **filters)
    except MusicManagerNotFoundError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_match",
            translation_placeholders={"query": query},
        ) from err
    except MusicManagerError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="request_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await coordinator.async_request_refresh()
    return result if call.return_response else None


def async_setup_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, SERVICE_SEARCH, _search, SEARCH_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD_BEST,
        _download_best,
        DOWNLOAD_BEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
