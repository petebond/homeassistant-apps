# Changelog

## 0.1.1 - 2026-10-23

- Fix: the app now announces itself to Home Assistant, so the integration is
  offered under Discovered. The base image's s6 init was hiding Supervisor's
  token from the app; it is now read back from s6's container environment.
- Fix: dates and times follow Home Assistant's time zone instead of UTC (same cause).
- Docs: the medication sensor is `sensor.prepare_medication_expiring`.

## 0.1.0 - 2026-10-23

First version. Deliberately plain HTML: function and content first.

- Inventory with best-before dates, use-first list, used/binned tracking.
- Medication, personal or household, with expiry and repeat prescription reminders.
- Household members drive the targets: readiness score, days covered, shortfall list.
- Family plans seeded from the UK Be Ready guidance, with review dates.
- Contacts and household details.
- Printable A4 pack, with out-of-date tracking.
- Plain http on 8999; https on 8998 with the app's own certificate authority
  (as Meal Planner) and a /setup page for phones; PWA with offline copies.
- Sidebar link through ingress.
- Companion integration and blueprints, installed into Home Assistant by the app.
