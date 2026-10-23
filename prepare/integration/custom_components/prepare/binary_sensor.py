"""Prepare binary sensors: things that need doing."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import PrepareEntity

BINARY = {
    "pack_out_of_date": ("mdi:printer-alert", lambda d: d["pack_out_of_date"], lambda d: {"last_printed": d["pack_last_printed"]}),
    "kit_check_due": ("mdi:clipboard-check-outline", lambda d: d["kit_check_due"], lambda d: {}),
    "plans_review_due": ("mdi:file-document-alert", lambda d: bool(d["plans_review_due"]), lambda d: {"plans": d["plans_review_due"]}),
    # Added in app 0.4.0; .get() keeps the integration working with an older app.
    "backup_due": ("mdi:backup-restore", lambda d: bool(d.get("backup_due")),
                   lambda d: {"last_backup": d.get("backup_last") or None, "last_downloaded": d.get("backup_downloaded") or None}),
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(PrepareBinary(entry.runtime_data, key) for key in BINARY)


class PrepareBinary(PrepareEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_icon, self._value, self._attrs = BINARY[key]

    @property
    def is_on(self) -> bool:
        return self._value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs(self.coordinator.data)
