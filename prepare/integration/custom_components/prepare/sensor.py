"""Prepare sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import PrepareEntity


def _ts(value: str | None):
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


@dataclass(frozen=True, kw_only=True)
class PrepareSensorDescription(SensorEntityDescription):
    value: Callable[[dict], Any]
    attrs: Callable[[dict], dict] = lambda d: {}


SENSORS = (
    PrepareSensorDescription(
        key="readiness", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shield-check", value=lambda d: d["readiness"],
        attrs=lambda d: {"categories": d["categories"], "shortfall": d["shortfall"]},
    ),
    PrepareSensorDescription(
        key="days_covered", native_unit_of_measurement=UnitOfTime.DAYS, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-check", value=lambda d: d["days_covered"],
        attrs=lambda d: {"target_days": d["target_days"], "people": d["people"], "pets": d["pets"]},
    ),
    PrepareSensorDescription(
        key="items_expiring", icon="mdi:food-off-outline", state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["items_expiring"],
        attrs=lambda d: {"items": d["items_expiring_list"], "warning_days": d["warning_days"]},
    ),
    PrepareSensorDescription(
        key="items_expired", icon="mdi:delete-alert", state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["items_expired"], attrs=lambda d: {"items": d["items_expired_list"]},
    ),
    PrepareSensorDescription(
        key="meds_expiring", icon="mdi:pill", state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["meds_expiring"], attrs=lambda d: {"repeat_due": d["meds_repeat_due"]},
    ),
    PrepareSensorDescription(
        key="pack_last_printed", device_class=SensorDeviceClass.TIMESTAMP, icon="mdi:printer",
        value=lambda d: _ts(d["pack_last_printed"]),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(PrepareSensor(entry.runtime_data, desc) for desc in SENSORS)


class PrepareSensor(PrepareEntity, SensorEntity):
    entity_description: PrepareSensorDescription

    def __init__(self, coordinator, description: PrepareSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        return self.entity_description.attrs(self.coordinator.data)
