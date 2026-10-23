# Changelog

## 0.3.2 - 2026-10-23

- Beans in tomato sauce are "Baked beans", whatever the tin calls them.
- Vague Open Food Facts categories ("canned common beans") no longer replace a
  clearer name taken from the pack.

## 0.3.1 - 2026-10-23

- Brands: Open Food Facts sometimes lists the maker's company ("H J Heinz Foods
  UK Ltd"). Prepare now prefers the brand on the pack ("Heinz").
- Product types drop "in a rich tomato sauce" and similar, and use a more
  specific Open Food Facts category when it says the same thing ("Beans" with
  the category baked beans becomes "Baked beans").

## 0.3.0 - 2026-10-23

Barcode scanning, and grouping different brands of the same thing.

- **Scan** page: live camera on the https address (the browser's own barcode
  reader on Android, the bundled ZXing reader on iPhone), a photo of the barcode
  on the plain http address, or type the number. Reads EAN-13 and EAN-8, as on
  UK groceries and own-label packs, plus UPC for imported goods. Check digits are
  verified, so a misread never becomes a wrong product.
- Lookups go to Open Food Facts' UK site first, then Open Beauty Facts (hand gel,
  wipes, toiletries) and Open Pet Food Facts. Results and your corrections are
  kept in the app, so the second scan of anything is instant and works offline.
  Unknown barcodes are filled in once and remembered.
- **Product types** group brands: Napolina and Tesco chopped tomatoes are both
  "Chopped tomatoes". Suggested from the product name with the brand, UK
  own-label names (Tesco Finest, Sainsbury's, Asda, Aldi and others), sizes and
  packing liquids ("in tomato juice") taken out, and matched to types you
  already use. Editable on every item.
- Inventory has two views: **By product** (one line per type, totals and the
  earliest best-before, batches inside) and **Every batch**.
- Water multipacks count their litres ("6 x 1.5l" = 9 litres); food counts meals
  per pack, which you set once per barcode.
- Scanning carries on to the next item with the same storage place, ready for
  unpacking a shop.

## 0.2.0 - 2026-10-23

A proper look, based on the UK Be Ready campaign's poster style.

- Light and dark modes from the start. A switch in the masthead picks light,
  dark or automatic (follows the device); each phone remembers its own choice,
  and the page never flashes white before going dark.
- Condensed capital headings in the campaign's two blues, a navy masthead,
  solid status tags and line icons for each checklist section. The heading font
  (Barlow Condensed, SIL Open Font Licence) is bundled, so it works offline.
- Dashboard: a big readiness figure, days covered, and a card per checklist
  section with its own progress bar that opens that section of the inventory.
- Family plans: an "In any emergency" panel with the meeting points, then a
  card per scenario with numbered steps and a reviewed or review-due label.
- Forms grouped into panels; editable tables turn into stacked cards on phones.
- Colour contrast checked against WCAG AA in both modes; visible focus outline.
- The printed pack stays plain black on white whatever the screen setting.
- New app icon. No crown, GOV.UK wordmark or GDS Transport: it's based on the
  campaign, not presented as an official service.

## 0.1.2 - 2026-10-23

- Inventory filters by the Be Ready checklist sections: Food, Water, Hygiene,
  Light and warmth, Communication and information, Money and documents, Medical
  and health, Baby products, Pet products, plus Other / car kit. Each button shows
  how many items are in stock in that section; empty sections are greyed out.
- Adding an item while a section is selected keeps you in that section and
  starts with its first category.
- Existing databases get the sections added on start; nothing to do.

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
