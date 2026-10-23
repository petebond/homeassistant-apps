"""Read-only To-do list of what to buy to reach the readiness targets."""
from __future__ import annotations

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import PrepareEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PrepareShortfall(entry.runtime_data, "shortfall")])


class PrepareShortfall(PrepareEntity, TodoListEntity):
    """Items appear here until the kit meets its target; tick them off by adding stock in Prepare."""

    _attr_icon = "mdi:cart-outline"

    @property
    def todo_items(self) -> list[TodoItem]:
        items = [
            TodoItem(summary=f"{s['name']}: {s['short']:g} {s['unit']}", uid=f"short_{s['key']}",
                     status=TodoItemStatus.NEEDS_ACTION)
            for s in self.coordinator.data["shortfall"]
        ]
        items += [
            TodoItem(summary=f"Replace expired: {i['name']} ({i['best_before']})", uid=f"expired_{i['id']}",
                     status=TodoItemStatus.NEEDS_ACTION)
            for i in self.coordinator.data["items_expired_list"]
        ]
        return items
