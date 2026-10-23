# Prepare

Get the household ready for emergencies, and keep it ready, following the UK
Government [Be Ready](https://beready.campaign.gov.uk/) guidance.

> Version 0.1 is deliberately plain HTML: function and content first, looks later.

## Using it

Open **`http://homeassistant.local:8999`** on anything on the home network.

- **Dashboard** - readiness score, days of water and food covered, what to buy,
  what to eat first, and everything else that needs doing.
- **Inventory** - emergency stock with best-before dates. Water counts in litres,
  food in meals. *Used* and *Binned* keep a record, so you can see the rotation
  working and the waste going down.
- **Medication** - optional. Personal (one person) or household (e.g. paracetamol,
  ibuprofen). Expiry and repeat-prescription reminders; printed with doses.
- **Kit & targets** - the guidance's checklist, scaled to who lives here
  (3 litres of water per person per day, 3 days by default). The six-monthly kit check.
- **Family plans** - power cut, flooding, fire, evacuation, severe weather, water
  and phone outages. Starting points from the guidance: edit them for your household.
- **Contacts** and **Household** - people, numbers, meeting points, radio
  frequencies, suppliers, insurance, the grab bag.
- **Print pack** - an A4 pack of all of the above. Press *I've printed it*
  afterwards; Prepare tells you when it goes out of date.
- **Settings** - the warning window for dates (30 days by default), days to aim
  for, review interval.

There are no accounts or logins: one shared household view, on the home network
only. Don't forward ports 8999 or 8998 to the internet.

## On phones, offline

A power cut takes Home Assistant down with it, so phones keep their own copy.
Browsers only allow that on https:

1. In **Settings → Apps → Prepare → Configuration**, turn on **Serve https as well**
   and restart the app.
2. On each phone, open **`http://homeassistant.local:8999/setup`** and follow the steps
   to trust Prepare's certificate. This works exactly like the Meal Planner's, but it
   is a separate certificate, so a phone set up for one still needs the other.
3. Open **`https://homeassistant.local:8998`**, add it to the home screen, and open the
   Dashboard once at home. Every main page is then saved on the phone.

The certificate covers the addresses the app can work out, plus any address a phone
used to open `/setup`. Add others under *Extra addresses for the certificate*.

## Home Assistant integration

With **Install the Home Assistant integration** on (the default), the app copies its
integration into `custom_components/prepare` and its blueprints into
`blueprints/automation/prepare`. **Restart Home Assistant** once after the first install;
Prepare then appears under **Settings → Devices & services → Discovered**.

| Entity | |
| --- | --- |
| `sensor.prepare_readiness` | Overall %, per-category scores and shortfall as attributes |
| `sensor.prepare_days_covered` | Days the household could manage on water and food |
| `sensor.prepare_items_expiring` / `_items_expired` | Counts, with the items as attributes |
| `sensor.prepare_medication_expiring` | Medication expiring or expired |
| `sensor.prepare_pack_last_printed` | When the pack was last printed |
| `binary_sensor.prepare_pack_out_of_date` | On when the pack needs reprinting |
| `binary_sensor.prepare_kit_check_due` / `_plans_review_due` | Reviews due |
| `todo.prepare_shortfall` | What to buy, and expired stock to replace |

Services: `prepare.add_item`, `prepare.consume_item`, `prepare.mark_printed`.

Blueprints: weekly expiry digest, reprint the pack, readiness dropped, power cut
(opens the plan on phones).

## Where the data lives

`/data/prepare.db` inside the app, included in Home Assistant backups. The certificate
authority is in `/data/certs`.

## Developing

```sh
pip install -r requirements.txt httpx
tests/run_local.sh            # http://localhost:8999, data in .devdata/
python tests/smoke.py         # every page and API call
pip install pytest-homeassistant-custom-component
pytest                        # integration tests
```

## Licence

MIT, as the rest of this repository. Seed content in `app/seed/` is derived from UK
Government guidance and contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
This is not an official government service.
