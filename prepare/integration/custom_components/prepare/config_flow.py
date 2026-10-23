"""Config flow: found automatically from the App (Supervisor discovery) or added by URL."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .const import CONF_URL, DEFAULT_URL, DOMAIN


class PrepareConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._url: str | None = None

    async def _check(self, url: str) -> bool:
        try:
            async with async_get_clientsession(self.hass).get(
                f"{url.rstrip('/')}/api/health", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200 and (await resp.json()).get("ok") is True
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            if await self._check(url):
                return self.async_create_entry(title="Prepare", data={CONF_URL: url})
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL, default=DEFAULT_URL): str}),
            errors=errors,
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        cfg = discovery_info.config
        self._url = f"http://{cfg['host']}:{cfg.get('port', 8999)}"
        self._abort_if_unique_id_configured(updates={CONF_URL: self._url})
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if await self._check(self._url):
                return self.async_create_entry(title="Prepare", data={CONF_URL: self._url})
            return self.async_abort(reason="cannot_connect")
        return self.async_show_form(step_id="hassio_confirm", description_placeholders={"url": self._url})
