# Home Meal Planner

Family meal planning, shopping list and kitchen display, served from your
Home Assistant machine so no PC needs to stay on.

## Using it

Once started, open **`http://<your-ha-ip>:8080`** on any device on the home
network.

- `/` — the planner: people, meals, weeks
- `/kitchen` — the kitchen display, cast to a Nest Hub (see below)
- `/setup` — one-off setup for reading the week offline (see below)
- `/api/kitchen` — JSON for the Home Assistant REST sensor (Monday to Sunday;
  add `?from=today&days=7` for a rolling week, which is what `/kitchen` uses)

With `https_enabled` on, the same thing is also served at
**`https://<your-ha-ip>:8443`**.

### Guests

**Guest(s)** is in the household list alongside everyone else. On any meal, turn
it on and set a number: *Alex, Sam, Jo and Guest(s) × 2* is five people, and
the shopping list, the ingredient quantities and the kitchen display all say
five. The number belongs to that meal — six on Saturday says nothing about
Tuesday — and turning the slot off forgets it rather than saving it for next
time.

It can be renamed ("Visitors") but not removed, it is never listed as *not
eating*, and it isn't offered as the cook.

### Rating a meal

After a meal, tap your own name at the foot of it on **The Week**. Five stars
drop out underneath — one nearest your name, five furthest away — and tapping
the star already showing takes your rating back off. Everyone who ate it rates
separately, so a meal carries as many opinions as it had people.

Only the people the plan says ate it can rate it, only from today backwards,
and not the guest slot — it stands for however many visitors turned up, so one
star count against it would be nobody's opinion in particular.

The **meal library** is ordered from the button beside the search box, which
reads back what the list is doing ("Highest · Pete, Jules +1"). Tapping it
opens two rows: the household, where you pick whose opinion counts, and the
order — A–Z, Highest, Lowest, Divisive, Unrated. Pick three names and the list
answers for those three: their average, their disagreements, the things none of
them has tried. No names picked means everyone. The choice is remembered per
device.

Each card shows the selected people's average and a pill per person; anyone not
being asked keeps their pill in grey.

Ratings belong to the night, not to the recipe: deleting a week takes its
ratings with it, and taking somebody off a meal — or out of the household —
removes their rating of it.

### The shopping list

Worked out from the week's plan, scaled by how many are eating each meal and
rounded up. **Also needed** at the top takes anything a recipe would never
mention — baking paper, foil, bin bags. It is one standing list, the same
whichever week is on screen: it isn't part of the plan, and a thing you still
need on Sunday is a thing you still need on Monday.

Tick the rows you're dealing with and the bar at the bottom offers the two
things you can do with them. **Got it** means bought, and it goes. **Ordered**
drops it into an ordered group, struck through and out of the way, grouped by
the day you ordered it. **Didn't arrive** puts something straight back on the
list, which is what substitutions and out-of-stock items need. Nothing expires
on a timer: an order that never came is the thing you most want the list to keep
nagging you about.

Every group heading has a tick box that takes all of it, so the usual delivery —
everything bar the one thing they'd run out of — is select all, untick that one,
**Arrived**.

Quantities come off the front of what you type — "3 cucumbers", "500g mince",
"2 tins chopped tomatoes" — and sit on the row with a − and + beside them. A
word is only read as a unit if the shopping list already knows it, so "2 chicken
breasts" keeps its chicken.

Tap a line to correct what it says. "Coke Xero" becomes "Coke Zero" without
deleting it and typing it again: the quantity, the unit and the fact that it was
ordered on the 3rd all survive. Corrected onto something already on the list,
the two fold into one row with the quantities added.

The box remembers every name ever typed into it and suggests as you type, so
"bak" finds baking paper again months later. Ticking something off doesn't
forget it; the suggestions are ordered by what gets bought most, and they hold
bare names, so the number you needed last time doesn't come back with them.

Correcting a line corrects the suggestion too — the misspelling is retired and
the corrected spelling inherits what it had been counted for, so a weekly staple
doesn't drop to the bottom of the list the day somebody fixes a letter in it. A
name another line on the list still goes by is left alone.

Settings → **Shopping list management** is the drawer for everything else the
box has learned: every remembered name, how often it has been asked for, when it
was last asked for, and an × to stop it being suggested. That is the place for
the candle bought for one birthday and the brand tried once. It only changes
what gets offered — something still to be bought stays on the list whatever the
box stops suggesting.

## Where the data lives

Everything is written to `/data`, the app's persistent volume:

- `/data/data.json` — the meal plan, the star ratings, and the shopping list's
  weekly extras
- `/data/images/` — meal photos
- `/data/chime/` — the dinner bell's sound, if you uploaded one
- `/data/display.json`, `/data/cast.json`, `/data/bell.json` — the kitchen
  display, the screens it casts to, and the dinner bell
- `/data/data.json.backup-YYYYMMDD` — automatic daily copies, last 7 kept
- `/data/certs/` — the private CA and server certificate, if https is on.
  `ca.key` is the one file worth not sharing.

`/data` is **included in Home Assistant backups**, so the meal plan is covered
by your normal backup schedule.

On the very first start only, if `/data` is empty, the bundled `seed/` folder
is copied in. Updates never overwrite live data.

### Taking a copy out, and putting one back

Every section of the **Settings** tab is a heading you open — the tab is a list
of what can be changed rather than four screens of controls. They arrive shut
each time the app is loaded.

The bottom of the tab has **Backup & restore**. One button
downloads all of the above as a single zip; the other puts one back. This is
what makes reinstalling the app safe: download a backup, uninstall, install
again from the repository, restore.

The zip holds `data.json` (the plan and every star given), `images/`, `certs/`,
your dinner-bell sound, and the kitchen-display, Cast and bell settings. The
daily `data.json.backup-*` snapshots are left out — they are a local undo for a
bad edit, not something worth carrying to a new install.

Two things worth knowing:

- **`certs/` is in there, which means the zip contains a private key.** Keep it
  somewhere you would keep a password. It is included on purpose: the CA is
  created once and never regenerated, because regenerating it breaks the trust
  already installed on every phone in the house. A reinstall without it would
  do exactly that.
- **Restart the app after restoring a backup that included `certs/`.** The
  certificate is read into memory when the server starts and stays there.
  Everything else — meals, plan, photos, settings — is live immediately.

Restoring replaces what is there. Before it does, it zips up the current
contents and keeps it; the last two are offered on the same screen for
download, and each is a valid backup in its own right, so an accidental restore
goes back the way it came. A file that isn't a planner backup is refused before
anything is written.

This sits alongside Home Assistant's own backups rather than replacing them.
`/data` is in those too — but restoring one is an all-or-nothing operation on
the whole machine, which is a large hammer for "put my meals back".

## Reading the week away from home

The app can be installed to a phone's home screen, and will then show the last
meal plan it saw even with no connection to the house. It is **read-only**
offline: a banner says how old the copy is, the editing controls grey out, and
changes are refused rather than queued. Queuing would let two people edit the
same week from different places and silently overwrite each other.

The Week and the meal library work offline. The shopping list does not — it is
worked out by the server from the plan, so there is nothing to show.

### Turning it on

Browsers only allow offline caching (a *service worker*) in a **secure
context** — `https://…` or `localhost`. Over `http://<your-ha-ip>:8080` the
browser refuses to register one and says nothing about why. A home network has
no public name a real certificate could be issued for, so the app runs a
small certificate authority of its own.

**On the Pi, once:**

1. App → **Configuration** → turn on **`https_enabled`** → Save → **Restart**.
2. On first start it generates a CA and a server certificate into
   `/data/certs`. Both survive updates. The CA is created once and never
   regenerated — replacing it would silently break every phone already set up.

**On each phone, once:** open **`http://<your-ha-ip>:8080/setup`** and follow
the steps. The page detects iPhone vs Android and puts the right instructions
first. In short:

- **iPhone/iPad** — download the certificate, install the profile from Settings,
  then the step everyone misses: **Settings → General → About → Certificate
  Trust Settings** and switch on *Home Meal Planner Local CA*.
- **Android** — download it, then **Settings → Security → Encryption &
  credentials → Install a certificate → CA certificate**. Android then shows a
  standing "network may be monitored" notice. That is normal for any private
  CA; this one signs nothing but the meal planner.

Then open **`https://<your-ha-ip>:8443`**, add it to the home screen, and load
it once while you're at home. The week is readable from then on.

Plain http on 8080 is unaffected and the kitchen display still uses it — the
Nest Hub can't be given a private CA.

### Which addresses the certificate covers

The container sees a Docker address (172.30.x.x), not the `192.168.x.x` one you
type, so the address guessed at startup is usually wrong. The `/setup` page is
fetched over http on *exactly* the address you're about to use over https, so
the server takes that as its cue: it adds the address and reissues on the spot,
no restart needed.

`localhost`, `homeassistant.local` and `meal-planner.local` are always
included. Anything else — a second hostname, a reserved DHCP address you plan to
move to — can be listed in the **`cert_hosts`** option, comma separated.

If the Pi's address changes, visit `/setup` from the new one and the certificate
catches up. Giving the Pi a static or DHCP-reserved address avoids the question.

### If a phone says the certificate isn't valid

- The address isn't on the certificate — load `/setup` over http from that exact
  address and try again.
- On iOS, the profile is installed but not *trusted* — that's the Certificate
  Trust Settings switch above.
- Compare the fingerprint at the bottom of `/setup` with what the phone shows.

## The kitchen display

`/kitchen` is the display page. The app can keep it on a Google Cast screen
by itself:

1. Install **DashCast** in Home Assistant (HACS → custom repository
   `AlexxIT/DashCast`) and restart Home Assistant. Casting is a protocol nothing
   in the Python standard library speaks, so the app asks Home Assistant to
   do it rather than growing a dependency.
2. Open the planner → **Settings** → **Kitchen display**, and tick the screens
   you want. **More than one is fine** — the kitchen and a bedroom Hub is an
   ordinary pair — and each is watched separately.

Only Cast devices that can actually show a web page are listed. Speakers are
left out (a tick box reveals them), decided from Home Assistant's own device
class and the model in its device registry rather than from what you've named
the thing: a Hub called "Kitchen Speaker" is still a screen. Anything unknown
counts as a screen, because offering a speaker that does nothing is a smaller
problem than hiding the display you're looking for.

It then checks once a minute and re-casts if a display has dropped back to its
photo frame — but **only when nothing else is using that screen**. If someone is
watching or listening to something, it waits until they've finished; the other
screens carry on regardless.

**Casting hours** are on the same card: tick *Only cast at certain times of day*
and set a window. Outside it nothing is taken over, and any screen still showing
the week is handed back — quit, so a Nest Hub returns to its photos rather than
going dark. A screen someone has put music on is never touched either way. The
window may cross midnight (16:00 to 01:00 is fine); widening it takes effect at
once rather than at the next minute's check. Leave it off and casting works
around the clock, as it always did.

The choice is kept in `/data/cast.json`, so it survives updates. To pin it
outside the app instead, put one or more media player entity ids in
**`cast_device`** in the app's Configuration panel, comma separated; the
app's picker then goes read-only.

The display fetches the page over the network, so it needs an address that works
from the other side of the house. The app takes the one a phone last used to
reach it, then Home Assistant's own address, then its own — override it with
`cast_url` if all three are wrong.

The strip along the bottom is **today and the five days after it**. A
Monday-to-Sunday strip spends half of itself on meals the house has already
eaten, and a screen on a wall is only ever asked what's next. It rolls over on
its own, without waiting for Monday — at midnight by default, or earlier if you
set a rollover time (below).

Six days rather than seven because it isn't a week and doesn't have to be: the
column that went was the one furthest off and least likely to be planned, and
the width it freed went to the ones you actually read. Meal names too long for
a column are cut short with an ellipsis rather than clipped mid-letter — the
full name is on the card above.

### How it looks

Settings → **How the kitchen display looks**, on a phone. Unlike the app's own
appearance panel, these are shared by the house: the Hub has nobody sitting at
it to set them.

- **Accent colour** — the same twelve the app offers.
- **Light or dark** — dark suits a Hub in the evening; light suits a bright
  kitchen.
- **Text size** — 70% to 140%, scaling the whole design rather than the type
  alone, so photos and gaps keep their proportions.
- **What's on screen** — the cook, how many they're cooking for, the clock, the
  date, meal photos, **Meals coming up** (the strip along the bottom), whether
  an empty evening says "Nothing planned" or stays quiet, and the shopping
  button. Whatever is left takes the space.
- **Moving on to the next day** — when the display stops showing today and
  starts showing tomorrow. Midnight by default, which is the calendar's own
  answer; set it to 21:00 and by nine the wall is answering the only question
  left, which is what happens next. The big card, who's cooking and the week
  strip all move together, and the panel says **Tomorrow** above the day name
  while they have. **The display only** — the app on a phone, the
  shopping list and anything reading `/api/kitchen` for a calendar week still
  call today today.
- **At night** — dim between two times, to a brightness you set. Never to black:
  a display that goes dark looks like a display that has died.

Changes reach the Hub on its next poll, within a minute, with nothing to
re-cast. Settings live in `/data/display.json`, so they survive updates and are
in your Home Assistant backups. `/preview` shows the result at the Hub's real
size from a phone or laptop; its Light/Dark buttons affect only what is in the
frame, by way of `/kitchen?theme=light`. That override works on a real display
too — put it in `cast_url` to keep one screen light in a house set to dark. It
is the only setting that can differ per screen.

### The shopping list on the display

**Shopping** is the last column of the bottom strip, one more alongside the six
days, with the number of things still needed under it in the accent colour and
a small *Tap to open* under that. The count is most of the answer on its own —
you can read it from where you're standing.

Pressing it takes the whole screen and shows the list — still needed first,
then what is already on order, dimmed. Every line has a − and a +.

**Adding is done by tapping a name.** A Nest Hub running DashCast is a cast
receiver, not a browser: there is no soft keyboard to raise, and a text box on
one is a box you can look at. So **Add something** opens a grid of the names
the app already remembers, most-used first — the same list the phone's "Also
needed" box suggests from, filled up by every add anyone has ever made on a
phone. Something genuinely new still has to be typed on a phone; it will be on
the grid from then on.

**Nothing here can lose anything.** There is no tick-off — that stays on the
phone, where a shop gets unpacked. The stepper is the only way a line leaves
this screen, and only by being counted down to none. A wall display gets
touched by accident, and a list that quietly drops a line is worse than one
with a line too many on it.

The panel closes itself after a minute and a half of nobody touching it, so the
Hub never spends an evening showing a shopping list. It also holds off the
six-hourly self-heal reload while it is open, and a poll landing mid-tap
changes nothing under your finger.

Turn it off under **What's on screen** if you would rather the display stayed
something you only look at; the seven days take the width back. With the week
strip switched off instead, the button keeps its place at the bottom of the
screen as a pill rather than a column.

## The dinner bell

Settings → **Dinner bell**. Switch it on, tick the speakers, and one press
plays a chime on all of them.

There are two ways to press it: **Dinner time!** on the kitchen display, for
whoever is plating up, and **Ring it now** on the phone. The display's button
has its own switch — a Hub within reach of a small child need not have one.

**The sound** is a bell shipped with the app, so the switch works the moment it
is turned on. Choose a sound to replace it with anything else: mp3, wav, ogg,
m4a or flac, up to 8 MB. The file is identified by its contents rather than by
what the phone's file picker called it, so a `.wav` that is really an mp3 works
fine. **Listen** plays it on the device you are holding rather than on the
speakers, which is the question worth answering before you wake the house.
**Use the built-in bell** deletes yours and puts the original back. Your sound
lives in `/data/chime/` and goes into the backup.

**Any media player Home Assistant has** can be ticked, screens included —
unlike the display picker, nothing is filtered out, because a speaker with no
screen is exactly what most people want here. **Select all** and **Clear** are
there for a house with a lot of them.

Three things worth knowing:

- **It plays over whatever is on, and Cast can't put that back.** A podcast the
  bell interrupts stays stopped. This is why nothing rings on a schedule and
  nothing ever will — the interruption is only acceptable when somebody meant
  it.
- **It doesn't touch the volume.** The chime plays at whatever each speaker is
  already set to. Reading and restoring six volumes is three round trips each,
  and an app that dies between the two leaves the house loud for good.
- **Pressed twice, it rings once.** The second press inside about ten seconds
  is swallowed.

The speakers fetch the sound from the app over plain `http`, the same as the
kitchen page and the meal photos: a Cast device has never been told to trust
the app's own certificate authority, and one handed an `https` address it can't
verify downloads nothing and says nothing about why.

Needs Home Assistant, like casting does — the speakers belong to it. On a PC
the card doesn't appear. Settings live in `/data/bell.json`.

## Notes

- **Nutrition is typed in by hand.** There was an estimate button that asked
  Claude; it went unused, and anything that needs working out is easier to work
  out in a conversation and paste in. Meals saved while it existed keep their
  numbers, and still say on the card where they came from.
- **Port 8080** is exposed directly rather than using ingress, because the app
  serves absolute paths and because casting to a Nest Hub needs a URL that
  works without a Home Assistant login.
- Timezone follows whatever Home Assistant is set to.

## Developing

Rebuilding the image for every small change is slow on a Pi. Dev mode avoids it.

1. App → **Configuration** → turn **`dev_mode`** on → Save.
2. **Restart** the app.
3. The log should say `DEV MODE: running live source from /addons/meal_planner`.

From then on:

| Changed | To see it |
| --- | --- |
| `static/` — HTML, CSS, JS | Just refresh the browser. Files are read per request. |
| `static/sw.js` | Refresh twice, or DevTools → Application → Service Workers → Update. Bump `CACHE_VERSION` inside it or the old shell stays cached. |
| `server.py`, `backup.py`, `bell.py`, `cast.py`, `display.py`, `icon.py`, `tls.py` | Restart the app (a few seconds). |
| `static/chime.wav` — the built-in dinner bell | `python3 tools/make_chime.py` to resynthesise it, then refresh. Not copied into the image from `tools/`; only the `.wav` it writes is. |
| The shapes in `icon.py` | `python3 icon.py --brand .` to redraw `icon.png` and `logo.png`, then Rebuild — Home Assistant reads those from the folder. |
| `config.yaml`, `Dockerfile`, `run.sh` | Rebuild. These are read at build time. |
| `translations/en.yaml` — the wording in the Configuration panel | Rebuild, or Reload from the App store. |

Data lives in `/data` in both modes, so there's no separate dev meal plan to
keep in step — you're developing against the real one. Worth a Home Assistant
backup before anything experimental.

If `dev_mode` is on but the folder isn't reachable, the app logs a warning
and starts the baked-in copy instead, so the kitchen display stays up.

## Releasing

When a change is ready to bake in:

1. Bump `version:` in `config.yaml` and add a `CHANGELOG.md` entry.
2. If anything under `static/` changed, bump `CACHE_VERSION` in `static/sw.js` —
   that string is what evicts the copy already cached on everyone's phones.
3. If the shapes in `icon.py` changed, run `python3 icon.py --brand .` and bump
   `icon.REV` — the first redraws the app's `icon.png` and `logo.png`, the
   second is what tells a browser holding the old drawing to fetch it again.
4. **Rebuild** from the app's three-dot menu.
5. Turn **`dev_mode` off** and Restart, so it runs the image copy.

The last step matters: left on, the app keeps running from the folder and the
version number stops meaning anything.

### Tests

Plain scripts, no dependencies. Run them from this folder, on the Pi or
anywhere with Python 3:

```
python3 tests/test_backup.py
python3 tests/test_bell.py
python3 tests/test_cast_churn.py
python3 tests/test_extras.py
python3 tests/test_head_count.py
python3 tests/test_naming.py
python3 tests/test_ratings.py
```

Each works in a temporary directory of its own and never touches `/data`.
