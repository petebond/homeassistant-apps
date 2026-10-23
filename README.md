# Home Assistant Apps

Apps I run at home, packaged so anyone else can install them. Everything here
runs on your own Home Assistant machine — no account, no cloud service, and
nothing leaves the house.

> Home Assistant now calls these **apps**. Older versions call the same thing
> **add-ons**, and the menus below read *Add-ons* and *Add-on Store* instead.
> Nothing else differs.

## Adding this repository

You only need to do this once. Every app below then appears in your store.

1. Go to **Settings → Apps**.
2. Click **Install app**, bottom right, to open the **App store**.
3. Open the **⋮** menu, top right, and choose **Repositories**.
4. Paste `https://github.com/petebond/homeassistant-apps` and click **Add**.
5. Close the dialog. The apps appear in the store under
   *Pete Bond's Home Assistant Apps*.

Apps here are built on your own machine rather than pulled as prebuilt images,
so the first install takes a few minutes on a Raspberry Pi.

## Apps in this repository

### 🍽 Home Meal Planner

Plan the family's week, work out the shopping from it, and put the week on a
kitchen display.

**Plan the week** — who is eating what, on which night. Each meal knows how
many it serves, so quantities follow the head count rather than a fixed recipe.
A guest slot covers the nights with extra mouths.

**Work out the shopping** — the list is built from the plan, scaled by how many
are eating and rounded up to what a shop actually sells. Alongside it is a
standing list for the things no recipe mentions: foil, bin bags, baking paper.
Items can be marked bought, or marked ordered and left visible until the
delivery turns up.

**Show it in the kitchen** — a display page built for a Nest Hub or any Cast
screen, showing today's meal, the cook, and the week ahead. The app can put it
on the screen by itself and hand the screen back at night. The kitchen display
needs the [DashCast](https://github.com/AlexxIT/DashCast) integration from
HACS; everything else works without it.

**Call everyone to the table** — one button plays a chime on every speaker in
the house. A bell is included; upload your own if you'd rather. Needs Home
Assistant for the speakers.

**Read it away from home** — the week installs on a phone as an app and can be
read offline, for the supermarket car park where the signal has gone.

**Take a copy with you** — everything the household has put in downloads as a
single file and restores from the same screen, so reinstalling or moving to a
new machine doesn't cost you your meals.

New installs start with an example household and a library of 37 meals, all of
which you can edit or delete.

→ [Full documentation](meal_planner/README.md) ·
[Changelog](meal_planner/CHANGELOG.md)

| | |
| --- | --- |
| Ports | 8080 (web interface and kitchen display), 8443 (the same over https, needed for offline reading) |
| Requires | Home Assistant OS or Supervised |
| Data | Written to the app's `/data` volume, and included in Home Assistant's own backups |

### 🛟 Prepare

Get the household ready for emergencies, and keep it ready, following the UK
Government [Be Ready](https://beready.campaign.gov.uk/) guidance.

**Know what you've got** — emergency water, food and kit, with best-before dates
and a *use first* list, so stock is eaten and replaced rather than thrown away.

**Know how ready you are** — a score against the guidance, scaled to who lives in
the house, and exactly what to buy to close the gap.

**Know what to do** — family plans for power cuts, flooding, fire, evacuation,
severe weather and outages, plus contacts, meeting points and medication.

**Have it on paper** — a printed pack, because there's no point having it online
when the power goes out. Prepare says when it needs reprinting.

**Have it on your phone** — installs as an app over https and works offline.

**Reminders in Home Assistant** — the app installs its own integration (sensors,
a shopping To-do list, services) and blueprints for expiry, reprinting and power cuts.

Light and dark modes, in the Be Ready campaign's poster style.

→ [Full documentation](prepare/README.md) · [Changelog](prepare/CHANGELOG.md)

| | |
| --- | --- |
| Ports | 8999 (web interface), 8998 (the same over https, needed for phones and offline) |
| Requires | Home Assistant OS or Supervised |
| Data | Written to the app's `/data` volume, and included in Home Assistant's own backups |

## Licence

MIT — see [LICENSE](LICENSE).
