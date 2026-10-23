"""Integration tests against a mocked Prepare App."""
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

URL = "http://prepare.test:8999"
SUMMARY = {
    "readiness": 62, "categories": {"water": 50, "food": 100}, "days_covered": 1.5, "target_days": 3.0,
    "people": 3, "pets": 1, "warning_days": 30, "items_expiring": 1,
    "items_expiring_list": [{"id": 7, "name": "Beans", "best_before": "2026-11-01", "days_left": 9, "quantity": 4, "unit": "meals"}],
    "items_expired": 1, "items_expired_list": [{"id": 3, "name": "Soup", "best_before": "2026-10-01"}],
    "meds_expiring": 0, "meds_repeat_due": [],
    "shortfall": [{"key": "water", "name": "Drinking water", "short": 18.0, "unit": "litres"}],
    "pack_last_printed": "2026-10-20T10:00:00", "pack_out_of_date": True,
    "kit_check_due": False, "plans_review_due": ["Flooding"],
}


async def test_user_flow(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/health", json={"ok": True})
    aioclient_mock.get(f"{URL}/api/summary", json=SUMMARY)
    result = await hass.config_entries.flow.async_init("prepare", context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": URL}


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/health", status=500)
    result = await hass.config_entries.flow.async_init("prepare", context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_entities_and_services(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/summary", json=SUMMARY)
    aioclient_mock.post(f"{URL}/api/items/7/consume", json={"id": 7, "name": "Beans", "taken": 2, "left": 2})
    aioclient_mock.post(f"{URL}/api/items", json={"id": 99})
    aioclient_mock.post(f"{URL}/api/print/mark", json={"pack_last_printed": "2026-10-23T10:00:00"})
    entry = MockConfigEntry(domain="prepare", data={"url": URL}, unique_id="prepare")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.prepare_readiness").state == "62"
    assert hass.states.get("sensor.prepare_days_covered").state == "1.5"
    exp = hass.states.get("sensor.prepare_items_expiring")
    assert exp.state == "1" and exp.attributes["items"][0]["name"] == "Beans"
    assert hass.states.get("sensor.prepare_items_expired").state == "1"
    assert hass.states.get("sensor.prepare_pack_last_printed").state.startswith("2026-10-20")
    assert hass.states.get("binary_sensor.prepare_pack_out_of_date").state == "on"
    assert hass.states.get("binary_sensor.prepare_kit_check_due").state == "off"
    assert hass.states.get("binary_sensor.prepare_plans_review_due").state == "on"
    # An app older than 0.4.0 sends no backup fields: the sensor stays off rather than failing.
    assert hass.states.get("binary_sensor.prepare_backup_due").state == "off"
    assert hass.states.get("todo.prepare_shortfall").state == "2"

    resp = await hass.services.async_call("prepare", "consume_item", {"item_id": 7, "quantity": 2},
                                          blocking=True, return_response=True)
    assert resp["left"] == 2
    resp = await hass.services.async_call("prepare", "add_item", {"name": "Water", "category": "water", "quantity": 6,
                                          "best_before": "2027-10-01"}, blocking=True, return_response=True)
    assert resp["id"] == 99
    await hass.services.async_call("prepare", "mark_printed", {}, blocking=True)
    posted = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert len(posted) == 3
    assert posted[1][2]["best_before"] == "2027-10-01"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_hassio_discovery(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers.service_info.hassio import HassioServiceInfo

    aioclient_mock.get("http://abc123-prepare:8999/api/health", json={"ok": True})
    aioclient_mock.get("http://abc123-prepare:8999/api/summary", json=SUMMARY)
    info = HassioServiceInfo(config={"host": "abc123-prepare", "port": 8999}, name="Prepare", slug="prepare", uuid="1")
    result = await hass.config_entries.flow.async_init("prepare", context={"source": config_entries.SOURCE_HASSIO}, data=info)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "hassio_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": "http://abc123-prepare:8999"}
