# Prepare

Get the household ready for emergencies, and keep it ready, following the UK
Government [Be Ready](https://beready.campaign.gov.uk/) guidance.

> The look follows the Be Ready campaign's poster style, in light and dark. Use the
> switch at the top of any page; *A* follows the device's own setting.

## Using it

Open **`http://homeassistant.local:8999`** on anything on the home network.

- **Dashboard** - readiness score, days of water and food covered, what to buy,
  what to eat first, and everything else that needs doing.
- **Inventory** - emergency stock with best-before dates, filtered by the Be Ready
  checklist sections (Food, Water, Hygiene, Light and warmth, and so on). Water counts
  in litres, food in meals. *Used* and *Binned* keep a record, so you can see the rotation
  working and the waste going down.
- **Scan** - add stock by barcode: live camera on phones (https address), a photo of the
  barcode, or type the number. Products are looked up on Open Food Facts (UK site first),
  Open Beauty Facts and Open Pet Food Facts, and remembered in the app.
- **Product types** - different brands of the same thing group together: Napolina and Tesco
  chopped tomatoes both count as *Chopped tomatoes*, each batch keeping its own date.
- **Meals that need two things** - each food says what it is: *a meal on its own* (soup,
  stew, beans, porridge), *needs something with it* (pasta, rice, noodles), *goes with
  something* (pasta sauce, curry, tuna) or *a snack or extra* (biscuits, bars, milk).
  Pasta for 10 and a sauce for 4 make **4 meals**, not 14; the dashboard says what's
  missing to use up the other 6. Extras are kept but not counted as meals. Prepare
  guesses from the product type, and remembers your choice for each barcode.
- **Spreadsheet view** - *Inventory → Edit as a spreadsheet*: every item in one table
  to edit in place, filter and sort, and tick rows to change many at once (category,
  what it is, where it's kept, product type, brand, date, used up, binned, delete).
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
| `binary_sensor.prepare_backup_due` | On when a backup should be downloaded |
| `todo.prepare_shortfall` | What to buy, and expired stock to replace |

Services: `prepare.add_item`, `prepare.consume_item`, `prepare.mark_printed`.

Blueprints: weekly expiry digest, reprint the pack, readiness dropped, power cut
(opens the plan on phones).

## Backup and restore

**Settings → Backup** downloads one JSON file with everything the household has entered:
inventory and best-before dates, household members and details, medication, plans,
contacts, kit targets, settings, remembered barcodes and product types, and the
activity log. Keep it somewhere other than Home Assistant. Restoring shows what's in
the file and what's here now before anything changes, and saves a copy of the current
data first. (The light/dark choice is kept by each phone, so it isn't in the file.)

Prepare also saves backups on Home Assistant in `/data/backups`: once a day when
something has changed (14 kept), before and after every update (a database copy and a
full backup), and before every restore. The dashboard asks for a download when there
has never been one, or when the last is over a month old and things have changed.

**Every backup restores into every later version.** That's a rule for anyone changing
the code - see the top of `app/backup.py`. In short: new tables and columns need
nothing; any other change to stored data bumps `backup.FORMAT` with a migration step,
and adds a real backup of the new format to `tests/backups/`, which the tests restore
on every run. If a change ever can't be migrated, `MIN_RESTORABLE` goes up and the app
asks the household to download a fresh backup straight away.

## Where the data lives

`/data/prepare.db` inside the app, with backups in `/data/backups`; both are included
in Home Assistant backups. The certificate authority is in `/data/certs`.

## Developing

```sh
pip install -r requirements.txt httpx
tests/run_local.sh            # http://localhost:8999, data in .devdata/
python tests/smoke.py         # every page and API call
pytest tests/test_backup.py   # backups, including every past format
pip install pytest-homeassistant-custom-component
pytest                        # integration tests
```

## Licence

MIT, as the rest of this repository. The heading font, Barlow Condensed, is under the
SIL Open Font Licence (`app/static/fonts/OFL-Barlow.txt`). The barcode reader is ZXing
(`@zxing/library` 0.21.3, Apache 2.0, `app/static/vendor/`). Product data comes from Open Food
Facts and its sister databases, © their contributors, under the Open Database Licence. Seed content in `app/seed/` is derived from UK
Government guidance and contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
This is not an official government service.
