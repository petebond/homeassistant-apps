"""Prepare - household emergency preparedness, as Home Assistant entities and services."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .coordinator import PrepareCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.TODO]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ADD_ITEM_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Optional("category", default="other"): cv.string,
    vol.Optional("quantity", default=1): vol.Coerce(float),
    vol.Optional("unit", default=""): cv.string,
    vol.Optional("best_before"): cv.date,
    vol.Optional("location", default=""): cv.string,
})
CONSUME_SCHEMA = vol.Schema({
    vol.Required("item_id"): vol.Coerce(int),
    vol.Optional("quantity"): vol.Coerce(float),
    vol.Optional("discard", default=False): cv.boolean,
})


def _coordinator(hass: HomeAssistant) -> PrepareCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("Prepare is not set up")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register services once."""

    async def add_item(call: ServiceCall) -> ServiceResponse:
        data = dict(call.data)
        if "best_before" in data:
            data["best_before"] = data["best_before"].isoformat()
        return await _coordinator(hass).post("/api/items", data)

    async def consume_item(call: ServiceCall) -> ServiceResponse:
        d = call.data
        return await _coordinator(hass).post(
            f"/api/items/{d['item_id']}/consume",
            {"quantity": d.get("quantity"), "discard": d["discard"]},
        )

    async def mark_printed(call: ServiceCall) -> ServiceResponse:
        return await _coordinator(hass).post("/api/print/mark")

    hass.services.async_register(DOMAIN, "add_item", add_item, ADD_ITEM_SCHEMA, SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "consume_item", consume_item, CONSUME_SCHEMA, SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "mark_printed", mark_printed, None, SupportsResponse.OPTIONAL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PrepareCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
