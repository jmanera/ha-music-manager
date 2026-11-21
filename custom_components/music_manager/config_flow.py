"""Config flow: set up automatically from the app's Supervisor discovery, or by hand."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import MusicManagerApi, MusicManagerAuthError, MusicManagerError
from .const import DEFAULT_PORT, DOMAIN

TITLE = "Music Manager"

USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): str,
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): int,
        probatio.Required(CONF_API_KEY): str,
    }
)


class MusicManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}
        self._app_name = TITLE

    async def _validate(self, data: Mapping[str, Any]) -> str | None:
        """Return an error key, or None if the app answered with this config."""
        api = MusicManagerApi(
            async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PORT], data[CONF_API_KEY]
        )
        try:
            await api.overview()
        except MusicManagerAuthError:
            return "invalid_auth"
        except MusicManagerError:
            return "cannot_connect"
        return None

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """The app announced itself through Supervisor discovery."""
        config = discovery_info.config
        self._discovered = {
            CONF_HOST: config["host"],
            CONF_PORT: config["port"],
            CONF_API_KEY: config["api_key"],
        }
        # One app per Home Assistant. A rediscovery (new key, new host) updates the entry.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates=self._discovered)
        self._app_name = discovery_info.name
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if error := await self._validate(self._discovered):
                return self.async_abort(reason=error)
            return self.async_create_entry(title=TITLE, data=self._discovered)
        return self.async_show_form(
            step_id="hassio_confirm", description_placeholders={"addon": self._app_name}
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual setup, e.g. for an app running outside Home Assistant OS."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._validate(user_input):
                errors["base"] = error
            else:
                return self.async_create_entry(title=TITLE, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            if error := await self._validate(data):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema({probatio.Required(CONF_API_KEY): str}),
            errors=errors,
        )
