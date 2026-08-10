# Changelog

## 1.18.0

**New: drag the household into the order you want.** Settings → Household, grip
handle on each row. That order is now the order names appear in everywhere —
the chips on a week card, the eating toggles, the rating pills, the kitchen
display.

Before this, a meal card listed people in the order they were *tapped*, so the
same two people at the same table could read "Sam, Alex" on Tuesday and "Alex,
Sam" on Wednesday. A row of names in a settled order is something you
recognise; one that shuffles is something you have to read.

The grip is the whole hit area, so a thumb resting on a name while scrolling
Settings doesn't pick anybody up. It is also a button: with it focused, the
arrow keys move that person one place, which is how this stays reachable from a
keyboard and from a screen reader. Escape during a drag puts everything back.

The guest slot is pinned to the end, because that is where it reads on a card —
"Alex, Sam and 2 guests". It had been drifting into the middle of the Settings
list, which nothing noticed while the order meant nothing.

**Fixed: the star picker was unreadable on the brighter half of the palette.**
An unearned star was white at 35% opacity and an earned one a fixed gold. On
the ten muted colours that preceded 1.17.0 that was merely faint; against the
palette as it is now, white at 35% on the yellow is 1.01:1, and the gold falls
under 3:1 on fourteen of the thirty-six — worst 1.03:1 on the green.

Stars are now outlined when unearned and solid when earned, which is how a star
rating is read everywhere else and is a difference of shape rather than of
colour, so it survives any background. The gold is kept where it can be seen
and falls back to the picker's own lettering colour where it can't. The rating
numbers and the Clear label were dimmed to 75% and 80%, which washed them into
the strongest reds and pinks at 2.4:1; both are at 90% now. Worst pairing
anywhere in the picker is 3.07:1.

**Fixed:** rating pills on a library card were drawn at 90% opacity, which
composited them with the card behind and cost the strongest colours about
0.15:1. They are full strength; the drained look for someone whose opinion the
list isn't asking for was always carried by its own rule.

## 1.17.0

**New: pick everyone's colour.** Settings → Household, tap the coloured disc
beside a name. Thirty-six colours in a grid, and they are proper colours now —
pure red, pure blue, yellow, cyan, hot pink — rather than the ten muted
mid-tones that were hard to tell apart on a chip the size of a name.

That is possible because the lettering on a chip now follows the colour behind
it: white on the deep half of the palette, near-black on the bright half. White
on yellow is why yellow could not be offered before.

A colour somebody else in the house is already wearing is greyed out and cannot
be picked. The whole point of the colour is to say which chip is whose, and two
people in the same one makes every name on the Week ambiguous — so rather than
warn about the clash, the picker has nothing there to press. The app refuses it
on the way in too, in case two phones reach for the same colour at once.

**Changed: the Week's meal cards are quieter.** The "*N* kcal cooked in total
for six people" line is gone — nobody eats the pan, and what one portion costs
is the figure above it, which is still there. Tags are gone from these cards
too: they are how you find a meal in the Library, but on the Week the meal is
already chosen and seven rows of "fast" and "weekend" sat above the thing you
opened the app to read. Both are untouched in the Library.

**Changed: changing week lands at the top of it.** Paging forward from a Friday
used to arrive on next Friday, with Monday to Thursday scrolled off above and
unread. It now lands on the Monday. Coming *back* to this week is the exception
and still lands on today, on the Week and the Planner both — that is what you
pressed it for.

**Fixed: the Dinner time! button on the kitchen display was unreadable on the
light theme.** Its lettering was a fixed near-black, chosen against the dark
theme's accents — those are bright colours meant to glow on a dark screen. The
light theme's twelve are the deep versions of the same names, so black on the
light blue came out at 2:1. The lettering now follows the theme: black on the
bright set, white on the deep set. Worst of the twenty-four is now 6.3:1.

**Fixed:** air between the Add person button and the household list, which read
as one control.

## 1.16.0

**New: the dinner bell.** Settings → **Dinner bell**. Switch it on, tick the
speakers, and one press plays a chime on all of them — so calling everyone to
the table stops being a walk to the foot of the stairs.

There is a **Dinner time!** button on the kitchen display for the person doing
the plating up, and a **Ring it now** button on the phone. The display's button
has its own switch, so a Hub in a room where a nine-year-old can reach it need
not have one.

A bell is shipped with the app, so the switch works the moment it is turned on.
Choose a sound to replace it with anything else — mp3, wav, ogg, m4a or flac,
including a recording of somebody shouting "dinner" — and **Listen** plays it
on your phone rather than on the speakers, which is the question you actually
want answered at that point. **Use the built-in bell** puts the original back.
Your sound goes into the backup with everything else.

Two things it deliberately doesn't do. It doesn't touch the volume: the chime
plays at whatever each speaker is already set to, because reading and restoring
six volumes is three round trips each and leaves the house loud for good if the
app dies halfway. And it doesn't ring on its own, ever — Cast can't resume what
it interrupts, so a podcast the bell stops stays stopped, and that is only
acceptable when somebody meant it. Pressing it twice in a row does nothing; the
second press is swallowed for a few seconds.

Needs Home Assistant, like casting does — the speakers are its, not ours. On a
PC the card doesn't appear.

**Changed: the Household tab is now Settings**, with a cog. It had been a
settings page in everything but name for a while — the display picker, how the
display looks and backups all live there, and the list of people is one card
among several. The household is still the first thing on it. Old links and
bookmarks to `#people` still land on the right page.

## 1.15.0

**New: how many the cook is cooking for.** The Week's day cards now read
"Cooking: Han, for 5 people", and the kitchen display says the same under the
name in its info panel. It is a line worth its space because the chips above it
can't be counted for it — one of them may read "+ 3 guests", and four names on
a card can mean nine at the table.

It counts the day, not each meal. A day with two sittings on it is one cook
feeding the house twice, so somebody marked for both is still one person, and
the guest slot is counted once at the largest number any single meal puts on
it. On a day with one meal — nearly every day — the figure beside the cook is
exactly the number the ingredients on the back of the card were scaled by.
Those two agreeing is the whole point: a display promising five dinners over a
recipe measured for four is worse than a display that says neither.

Nothing is said when nobody is marked yet. A card reading "Cooking: not
decided, for 0 people" answers a question nobody asked.

**New: a switch for it on the kitchen display.** Appearance → what's on screen
now has "How many they're cooking for", on by default, beside "Who's cooking".
A Nest Hub is a small screen and a household of a fixed size already knows the
answer.

**Changed: backups say that the ratings are in them.** They always have been —
the stars live on the sittings inside the meal plan, which goes into the zip
whole — but the summary on the backup card listed meals, people and photos, and
a list like that reads as a list of everything that's in there. It now names
the ratings and the weeks planned, on the card, in the confirmation before a
restore, and in the message afterwards. Nothing about the file itself has
changed, and backups made by older versions are described the same way, because
the numbers are counted out of the zip rather than read off what the app that
wrote it claimed.

## 1.14.0

**New: order the library by what *some* of the house thinks.** Tap the button
beside the search box — it reads back what the list is doing, "Highest · Pete,
Jules +1" — and two rows of chips open underneath. The first row is the
household: tap the names whose opinion you want. The second is the order:
A–Z, Highest, Lowest, Divisive, Unrated. So "the meals Pete, Jules and Han
rate highly, never mind what the other three make of them" is four taps, and
the answer can be a meal the house as a whole scores 3.0.

Everything downstream follows the selection. Highest and Lowest average only
the people you picked. Divisive is the spread between them, so a meal three
people all give 5 stops being divisive the moment the two who hate it are
deselected. Unrated means none of *them* has rated it — which is the useful
question when three of six have never tried something.

The card agrees with the list it is in: the stars and the figure are the
selected people's average, captioned "from Pete, Jules and Han", and everyone
else's pill goes grey rather than disappearing. What the rest of the house
thought is still worth seeing; it just isn't what you asked.

No chips lit means the whole house, which is where it starts and where
deselecting the last name lands. Selecting everybody is the same thing, so it
collapses back to that. The choice is remembered per device, like the theme —
the phone in your pocket asking for what you like doesn't change what the
kitchen tablet shows.

**Changed: the default order is A–Z.** It was whatever order the library
happened to be stored in, which was alphabetical in practice but only by
accident.

**Removed: the order dropdown.** A `<select>` holds one choice, so "best for
one person" meant two entries per person — a list that grew with the household
and still couldn't answer a question about three of them at once.

## 1.13.1

**Changed: the name chips on The Week are just names again.** 1.13.0 put a
small star on every chip you could rate, and left the ones you couldn't
without. That made the row of names a status display: four chips, each
carrying a badge, on a card whose job is to say who is eating. The chips are
now identical whether the meal was last night or is next Thursday — what you
gave it lives in the picker, which is where you go to change it anyway.

**Changed: the star picker is cleaner.** The person's name is off the top of
it; instead the whole list takes the colour of the chip it came out of, which
on a card with four names answers "did I tap the right one" without a line of
text to read first. Numbers moved to the left of the stars, the rows are
tighter, and the stars are drawn rather than typed — ★ is whatever the device's
font makes of it, thin and spiky on some machines, and it can't be given
rounded points. These are rounder, fatter and properly yellow.

## 1.13.0

**New: everyone who ate it can say what they thought of it.** On The Week, tap
your name at the foot of a meal and five stars drop out underneath it — one
nearest your name, five furthest away, so the rating is how far you reach
rather than which of five identical stars you managed to hit with a thumb. Tap
the star already showing to take it back. Each person rates for themselves, so
a meal eaten by four people carries four opinions rather than one household
verdict nobody agreed on.

Only the people the plan says ate the meal can rate it, and only from today
backwards — nobody can say what Thursday was like on Tuesday. The guest slot
doesn't rate: it stands for however many visitors turned up, so a single star
count against it would be nobody's opinion in particular.

**Changed: The Week no longer says "Everyone".** A meal the whole house was
down for used to collapse into one chip, which read well and saved a line. But
the chip is now the thing you tap to rate, and one chip can't stand for four
people's opinions, so every eater gets their own name back.

**New: the meal library can be sorted by what the house thought.** Next to the
search box, which is unchanged: highest rated, lowest rated, most divisive, not
yet rated, and — per person — what each of them likes most and least. Each card
shows the average, how many ratings it is from, and a small coloured pill per
person with their own average, because "4.2" is a number and "Ellie 5, Sam 2"
is the reason you are or aren't cooking it again.

"Most divisive" compares people, not nights: someone who rates the same meal 3
one week and 5 the next is having an off week, whereas two people who rate it 1
and 5 disagree about the meal. So each person is reduced to their own average
first and the spread is measured across those. A meal nobody has rated is never
"lowest rated" — an unknown goes to the bottom of every order rather than
winning the worst one by default.

**Ratings are attached to the meal as it was eaten, not to the recipe.** They
are stored against the night, which is why deleting a week takes its ratings
with it, and why the same recipe cooked in March and again in August counts as
two opinions. Taking somebody off a meal removes their rating of it, and so
does removing them from the household — a rating from somebody the plan says
wasn't there is a number with nothing behind it, and it would go on pulling the
library's averages around under a name no longer on screen.

Existing weeks need nothing doing to them: a meal planned before this version
simply has no ratings yet.

**Changed: adding a meal is a + by the heading.** The library used to open on a
full-width "Add meals" bar with two tabs behind it, which spent the top of the
screen and a card's worth of height on a page whose job is mostly to be
browsed. It is now a round + next to *Meal library*, turning a quarter into a ×
while the form is up. Saving an edit puts the form away; adding a new meal
leaves it up and empty, ready for the next one.

**Removed: the Bulk Add tab.** One of two tabs, behind a panel, for a paste of
pipe-separated lines — a thing you do once when you set the app up and never
again, taking up half the width of the control that adds meals every other day
of the year. The `/api/meals/import` endpoint it posted to is still there for
anyone seeding a library from a script.

**Changed: the add-meal form stops explaining itself.** Links and Photo were
boxed sections with a legend and a line of prose each; both are now plain
fields like Meal name and Tags, and the photo's URL box, Upload button and
thumbnail sit on one row rather than three. Gone with them: "A recipe, or one
page per shop-bought item", "(shows on the meal card, and the search looks in
it)", and a sentence explaining that a picture from your phone is stored with
the meal planner. The placeholders already said it. Ingredients and Nutrition
keep their boxes, being genuinely sub-forms.

## 1.12.1

**Fixed: initialisms typed in lower case came out mangled.** "bbq sauce" was
stored and shown as "Bbq Sauce". The rule was only ever able to *keep* capitals
that had already been typed — "BBQ sauce" survived, "bbq sauce" did not, and
nobody holds shift while writing a shopping list. A short list of initialisms
(BBQ, UHT, XL, MSG, IPA, PB) is now recognised however it was typed, punctuation
and all: "3 bbq sauce", "BBQ SAUCE" and "(bbq) sauce" all land on the same
spelling. Existing entries fix themselves the first time the list is read —
names are normalised on the way out of the file, not only when something is
saved, so nothing needs re-typing.

**Changed: joining words stay small.** "a bunch of coriander" was becoming
"A Bunch Of Coriander", which reads like a shop sign. Words like *of*, *and*,
*in* and *with* are now left lower case unless they open the name, so it comes
out as "A Bunch of Coriander" and "Tin of Chopped Tomatoes".

**Changed: "Also needed" is Title Cased like everything else on the list.** It
used to keep whatever spelling was typed, on the grounds that correcting it
wasn't worth a settings page. But it sits directly above the shopping list,
where every line is Title Cased, and the mismatch was the thing you actually
noticed. Remembered names and the suggestions under the box follow the same
rule, so the suggestion now reads as the line it is about to become. Matching is
unchanged: "bbq sauce", "BBQ Sauce" and "3 bbq sauces" still collapse onto one
entry rather than three.

**Fixed: the action bar for ordered items overlapped itself on a phone.** With
something ticked, "2 selected" sat on top of the Arrived button. The count had
been told it could shrink to nothing, and text in a box that narrow spills out
rather than wrapping — at phone width the three buttons already needed the whole
row. The count now rides on the button that uses it ("Arrived (2)", "Got it
(2)"), which puts the number where the decision is, keeps the bar one row tall
on a screen where a second row costs list you can see, and leaves nothing in
the bar that is able to overflow.

## 1.12.0

**New: Backup & restore, at the bottom of the Household tab.** One button
downloads everything the household has put in — the meals, the plan, the photos
taken in the kitchen, the standing shopping list, the kitchen-display settings —
as a single zip. A second puts one back. The point is that reinstalling the app
stops being something to be nervous about: download, uninstall, install again
from the repository, restore.

- **The https certificate travels with it.** `certs/` is in the zip on purpose.
  The private CA is created once and never regenerated, because regenerating it
  silently breaks the trust already installed on every phone in the house — a
  reinstall without the old `certs/` would do exactly that. Carrying it through
  means the phones never notice. It also means the zip holds a private key, so
  keep it somewhere you'd keep a password. After a restore that included it,
  restart the app: the certificate was loaded into memory at startup and stays
  there until it starts again. Everything else is live immediately.
- **Restore replaces, and says what it is about to replace.** Choosing a file
  asks the app what is in it before anything is written, so the confirmation
  reads "142 meals, 96 photos, made on 3 August" rather than "are you sure".
- **It can be undone.** A copy of the current data is zipped up first and kept
  alongside it; the last two are offered on the same screen. That copy is
  itself a valid backup, so undoing a mistake goes back through the same door.
- **Anything the zip doesn't carry is left alone rather than deleted**, so an
  older backup made before a settings file existed doesn't wipe that setting.
- **A file that isn't right is refused before anything is touched**: not a zip,
  no manifest, made by another app, made by a newer version, meal data that
  won't parse, or any path trying to write outside the data folder.
- The daily `data.json` snapshots are deliberately not included — they're a
  local undo for a bad edit, not something worth carrying to a new install.
- New: `backup.py`, `GET /api/backup`, `GET /api/backup/info`,
  `POST /api/restore`, `POST /api/restore/check`, and `tests/test_backup.py`.

**Fixed: a clean clone of this repository could not be built.** `seed/data.json`
was matched by the `data.json` line in `.gitignore` and so never reached GitHub,
while the Dockerfile copies `seed/` into the image unconditionally — meaning the
build worked on the machine it was written on and failed everywhere else. The
seed is now tracked explicitly.

**Also:** `config.yaml` is copied into the image, so the version stamped into a
backup is the real one rather than `unknown`.

## 1.11.1

**Changed: the Configuration panel says less.** Every option had grown into a
paragraph, and Home Assistant renders each one as a single grey line under the
field — so the explanations were long enough that nobody would read them and
were, in places, explaining things that had stopped being true. Each is now a
sentence or two: what the setting does, and the one thing you'd otherwise get
wrong. The reasoning stays in `config.yaml`, where it was always meant to live.

## 1.11.0

**Removed: the AI nutrition estimates.** Two buttons on the meal form asked
Claude Code to guess the macros for a meal, either from its description or from
a photo. They went unused — anything worth working out is easier to work out in
a conversation and paste into the boxes, which are right there and always were.

- **Nothing about your meals changes.** Macros already saved stay exactly as
  they are, including the ones an estimate produced, and the card still says
  where its numbers came from. That label is kept on the way in and never
  generated: rewriting an old estimate to "entered by hand" would be a lie about
  a number nobody checked.
- **Gone:** `ai.py`, `ai_local.py`, `ai_bridge.py`, the bridge's `.bat` launcher
  and `AI-BRIDGE-SETUP.md`; the `/api/ai/*` endpoints; the estimate buttons, the
  status line and the "AI estimates are off" banner; and the `ai` block that
  every `/api/data` carried.
- **Two add-on options are gone with it:** `ai_bridge_url` and `ai_token`. Home
  Assistant drops saved values for options a schema no longer declares, so
  there's nothing to do — but if the Configuration panel complains after the
  update, open it once and Save.
- **Photo uploads are untouched.** `decode_image` lived in the AI module for the
  good reason that the photo estimate needed it too; it has moved into
  `server.py`, where it always belonged. Uploading a picture for a meal works
  exactly as before.
- The startup banner no longer spends a line on whether Claude Code is
  reachable, and no longer runs a check to find out.
- **The caption under the macros is gone entirely.** It said whether a figure
  had been estimated or entered by hand, which was worth knowing while both were
  possible. With one way in it had nothing left to tell anyone, and a meal saved
  back then is not a different kind of meal. Old estimates now look like every
  other meal: four numbers.
- The Description field used to explain itself as the thing the estimate read.
  It now says what it actually does: shows on the meal card, and the search
  looks in it.
- Dead styling removed with the rest: the estimate button row, the status text,
  the spinner, and the confidence badge, which nothing had drawn in a while.
  `.cast-pick` and `.meal-link` went too — both unreferenced, neither anything
  to do with the estimates, but this was the sweep to catch them in.
- **`confidence`, `source` and `note` are gone from the data.** How sure a guess
  claimed to be, whether it was a guess, and the sentence it wrote about itself.
  Meals shed all three as the file is read, so it clears itself without a
  migration step. The numbers are untouched, and `estimatedAt` stays: nothing
  shows it either, but it is the only record of how old a figure is, and unlike
  the rest it makes no claim that stopped being true.

## 1.10.0

**Changed: "Also needed" is now one standing list, and knows the difference
between buying a thing and ordering one.** It used to be kept per week, on the
reasoning that a roll of baking paper bought on Saturday shouldn't still be on
the list a fortnight later. What actually happened is that the week rolled over
and took everything *unbought* with it — which is precisely the stuff that
needed remembering.

- **One list, whichever week is on screen.** It isn't part of the meal plan and
  never was. Stepping between weeks no longer changes it, and no longer blanks
  it while the week's food is still loading.
- **Two ways off the list, because there are two ways things get into this
  house.** *Got it* means bought, and it goes, same as before. *Ordered* drops
  it into an ordered group — struck through, greyed, out of the way but still on
  the page — where it waits for the van.
- **Ordered things are grouped by the day they were ordered**, because an order
  is one trip to one website arriving in one box.
- **Every group heading has a tick box that takes the lot**, and so does the
  heading over the things still needed. It selects rather than acting, which is
  the point: the usual delivery is everything bar the one thing they'd run out
  of, so you take the lot, untick that one, and the bar is already offering the
  two things you might do with the rest. A heading with a button on it instead
  would leave you unpicking that one item afterwards. Half-selected groups show
  it, and two orders arriving together can be cleared in one go.
- **Didn't arrive** puts something straight back on the list. Substitutions and
  things that were out of stock are the normal case, not the exception, and they
  are the whole reason ordered items stay visible rather than being deleted on
  trust.
- **Nothing is on a timer.** An order that never came is the one thing on this
  page that ought to be shouting; the rows say how long they have been waiting
  instead. Ordered items are also left off the shared list — a delivery on its
  way is not something to put in a trolley.
- **A tick box on every row**, which is how you act on one thing and how you act
  on twelve. No separate select mode, nothing to long-press. The buttons appear
  in a bar at the bottom of the screen once something is ticked, and only ever
  the two that make sense for what's ticked.
- **Quantities.** Type "3 cucumbers", "500g mince" or "2 tins chopped tomatoes"
  and the number comes off the front and lives on the row, with a − and + beside
  it for when three turns out to be two. A word is only read as a unit if the
  shopping list already knows it, so "2 chicken breasts" keeps its chicken, and
  anything without a number in front is left exactly as typed.
- **The suggestions got better as a side effect.** They are trained on the bare
  name now, so "cucumber", "2 cucumbers" and "3 cucumbers" stopped being three
  competing entries; singulars and plurals collapse together; and typing
  something already on the list adds to the row that's there rather than making
  a second one.
- Everything already written down is carried over on first run: all the weekly
  lists fold into the one standing list, newest first, with the repeats merged.
- `test_extras.py` covers the parsing, the plural rules and the migration —
  including the one that only turned up once it was written, where "glass" was
  being filed as the plural of "glas".

## 1.9.17

**Fixed: the display list got confused when displays were added to or removed
from the Home.** Doing either reloads Home Assistant's Cast integration, and for
a few seconds around that its answers are wrong in three ways that all showed up
in Household → *Kitchen display* as a list that couldn't be trusted.

- **The picker no longer empties itself.** A template rendered mid-reload
  answers "no Cast devices" perfectly successfully, and that was taken at face
  value: the list would clear and every chosen screen turn into a "not
  answering" ghost. It now takes two passes in a row saying the same thing.
  `Look for displays` goes through the same gate, which matters because that
  button is most likely to be pressed in exactly the minute Home Assistant can
  least answer.
- **A speaker is no longer promoted to a screen.** When the integration can't
  be asked, the add-on sweeps `/states` for every media player instead — a list
  with no model on it, which meant almost everything looked castable. That sweep
  is now only used when there is nothing better, rather than replacing a good
  list, and when it is used the card says so.
- **A display that has really gone is now said to be gone.** Taking a device out
  of the Google Home and putting it back usually brings it back under a *new*
  entity id, leaving the old one ticked forever. That stale id was 404ing every
  minute, and — the part nobody could have guessed at — each failure put the
  watcher into a back-off that slowed the poll for every screen that *was*
  working, up to five minutes. Removed displays are now reported separately,
  stop being asked about, and don't count as a fault.
- **Forget removed displays** appears under the list when there are any, and the
  rows themselves now carry the entity id under the name — which is the only
  thing that tells two Hubs both called "Kitchen display" apart.
- A screen that is merely switched off at the wall is still shown ticked and
  still tried, as before. Only one that Home Assistant no longer has at all is
  written off, and it comes straight back if it reappears.
- `test_cast_churn.py` covers all of it, including the case that only turned up
  once the test was written: a single 404 during a reload was enough to declare
  a perfectly good display removed.

## 1.9.16

**Fixed: the preview's Light/Dark buttons did nothing.** `/preview` frames the
display as `/kitchen?theme=light`, which `kitchen.html` has always applied before
first paint — and which `applyDisplay()` then painted straight over with the
house's shared setting on the first poll, a fraction of a second later. Too fast
to see happen, so the buttons simply looked dead.

- `?theme=` is now honoured by `kitchen.js` as well: an override for that one
  display, above whatever the house has set. It is the only setting that can be
  overridden per screen, because it is the only one with a way to say so from
  the casting end — the accent, the size and what's on screen stay the app's.
  It works on a real display too: put it on the end of `cast_url` to keep one
  screen light in a house set to dark.
- The theme remembered for the next reload is now the one actually on screen
  rather than the one the server asked for, so a forced display doesn't blink
  through the house's theme on its six-hourly reload.
- Broken since the display's settings moved to the server; the comment in
  `kitchen.html` promising `?theme=` still won has been true again since.
- No `CACHE_VERSION` bump: nothing under `/kitchen` is in the app shell cache,
  so the display picks this up on its next reload.

## 1.9.15

**The display can move on to tomorrow before midnight.** Household → *How the
kitchen display looks* → **Moving on to the next day**. Once the meal has been
eaten, what the house already had is no longer the useful answer; set it to
21:00 and by nine the wall is showing tomorrow.

- The big card, who's cooking, the date and the seven-day strip all move
  together — the strip starts at the new day, so it is still a week of what's
  next rather than six days and a memory.
- **The display only.** The app on a phone, the shopping list, backups and
  anything reading `/api/kitchen` for a calendar week keep the calendar's
  answer. A shopping list that started talking about tomorrow at teatime would
  be a bug in every other part of the house, so the shift is applied to the
  rolling window and nowhere else.
- It says **Tomorrow** while it is doing it, in the accent, above the day name.
  "Thursday" on a Wednesday evening is otherwise indistinguishable from a
  display stuck on the wrong day, and the word is cheaper than the doubt. It
  shares the slot the "Currently showing" label already used, which is a
  conflict that can't arise: the rollover only ever labels the day the display
  chose for itself, and that is the one tapping anything moves off. An empty
  evening says "Nothing planned for tomorrow" to match.
- `/api/kitchen` now also carries `date`, the real one, beside `today`. A screen
  showing Thursday on a Wednesday evening is either this setting working or the
  Pi's clock being wrong, and a feed that reports one date can't tell you which.
- Midnight is the default and is not a special case: "00:00" is exactly when the
  calendar turns over, so the general rule gives the old behaviour for free.

**And casting can be limited to certain hours.** Household → *Kitchen display* →
**Casting hours**. A window for taking the screen over, off by default.

- Outside it, nothing is taken over — and a screen still showing the week is
  handed back rather than left up all night. Quit properly, so a Nest Hub falls
  back to its photos instead of going dark.
- Only ever our own page. A Hub with music on it, or one already back on its
  photo frame, is not ours to switch off and isn't touched.
- The window may cross midnight — 16:00 to 01:00, for a house that eats late.
  Equal times mean all day rather than a window of zero length, which is nobody's
  intention.
- Widening the hours at half past ten puts the week up now: the watcher is
  kicked when these change rather than waiting out its next minute. The
  "never came up" counter is cleared with the release too, so a display given
  back at eleven isn't three strikes closer to being given up on by morning.
- The card says which state it is in — "Until 23:00, then the screen goes back
  to normal", or "Nothing until 07:00" — because a picker with screens ticked
  and nothing on them otherwise looks broken.

`CACHE_VERSION` → `mp-v16`: the two new controls are in the app shell, which the
service worker does cache. Nothing under `/kitchen` is, so the display picks up
its half on the next reload either way.

## 1.9.14

**Who's cooking has moved into the clock panel, and the meal cards are taller
for it.** It had a header row of its own across the top of the display, which
cost every card about seven vertical percent of the screen to say one name.

- It now sits under the date, separated by a rule, reading as part of the same
  answer as the day and the time.
- The header is gone entirely rather than left empty, and the padding under it
  with it. The meal photo goes from 25vh to 31vh and the clock from 17vh to
  19vh — the freed height, spent on the two things read from across a kitchen.
- The "not updating" warning was the only other thing up there. It floats in the
  top corner now, out of the flow: it is a rare warning and shouldn't cost a row
  of the display on the days it has nothing to say.
- Turning the cook off in the display settings still hides it; the panel only
  disappears entirely when the clock, the date **and** the cook are all off,
  which is one more condition than before.
- No `CACHE_VERSION` bump: the service worker leaves everything under `/kitchen`
  alone, so the Hub picks this up on its next six-hourly reload.

## 1.9.13

**The shopping list takes things that aren't ingredients.** Baking paper, foil,
bin bags, a card for somebody's birthday: an "Also needed" box at the top of the
Shopping tab. Type it, and it's on the list. Bought it? **Got it** takes it off.

- **They belong to one week.** Something added to next week's list is on next
  week's list and nowhere else — a roll of baking paper has no business
  reappearing a fortnight later. Copying a week's plan brings the meals and
  leaves the extras behind, for the same reason.
- Stored beside the weeks rather than inside them, keyed by the same Monday.
  A week's record is seven days and nothing else — `migrate_weeks` deletes any
  key that isn't a day, so anything kept in there would quietly vanish.
- They come down with the shopping list itself rather than in a second request,
  go into the shared and printed list at the top, and are ticked off by being
  removed: a list of crossed-out lines is just a longer list.
- Removing one leaves no trace of the week in the file, so an unused week costs
  nothing.

**And the box remembers.** Every extra ever typed is kept, so "bak" finds baking
paper again in seven weeks' time.

- Suggestions are ordered by how often something has been typed, then by how
  recently — what this house really buys comes up before the one-off that was
  spelled wrong in March. Two hundred are kept; beyond that the least used and
  oldest fall off the end.
- Ticking something off does **not** forget it. Bought is the opposite of
  irrelevant, and remembering is the entire point.
- Matched without case, so "baking paper" doesn't become a second entry beside
  "Baking paper"; the spelling first used is the one kept.
- Anything already on this week's list is left out of the suggestions — it is
  two inches above the box, and offering it is only an invitation to add it
  twice.
- It is a `datalist`, so it is the browser's own suggestion list: one attribute,
  behaves like every other field on the phone, and doesn't fight the on-screen
  keyboard.

## 1.9.12

**The kitchen display's week now starts at today.** The strip along the bottom
runs from today forward a week, instead of Monday to Sunday — half of which was
given over to meals the house had already eaten, on a screen that is only ever
asked what's next.

- It rolls over at midnight rather than waiting for Monday, because the display
  polls for the window rather than for a week.
- A window that starts on a Thursday runs off the end of one stored week and
  into the next, so each day's plan is now looked up by date rather than pulled
  out of a single week's record.
- `/api/kitchen` still answers Monday to Sunday by default. The rolling window
  is `?from=today&days=7`, which is what `/kitchen` asks for — anything else
  reading that endpoint, a Home Assistant sensor say, was written against the
  calendar week and shouldn't have it changed underneath it. `days` accepts
  anything from 1 to 14.
- `todayMeals`, `todayCook` and `todayNotEating` are unchanged either way.

## 1.9.11

**The week can go on more than one screen.** Household → Kitchen display is now
a list of tick boxes rather than a dropdown: choose the kitchen Hub and the
bedroom one and both are kept showing the week.

- **Each screen is watched on its own.** One in use is left alone while the
  others are cast to; one unplugged in a spare room doesn't stop the kitchen
  being fed; the "sent it three times and it never came up" giving-up count is
  per screen. A display that stops being chosen has its bookkeeping forgotten,
  so picking it again next month starts clean.
- `cast_device` in the Configuration panel takes a comma separated list. The
  app's `/data/cast.json` gained a `devices` list and still reads the old
  single-`device` shape, so nobody has to choose again.
- The app sends the whole list on every tick, and the server still understands a
  single `device` from a copy of the app sitting in a phone's cache.

**Speakers are no longer offered as displays.** A Google Home Mini is a Cast
device in every respect except the one that matters here, and a kitchen with
three of them in it was offering five "displays", three of which did nothing.

- The decision comes from Home Assistant: the Cast integration's device class
  marks audio devices and speaker groups, and the model in the device registry
  settles the rest. The registry is the half that still works for a device
  that's switched off, since a state can lose its attributes but a registry
  entry doesn't go anywhere.
- **What a device is called is deliberately not consulted.** A Hub named
  "Kitchen Speaker" is still a screen, and an earlier version of this guessed
  from the name and would have got that wrong.
- An unknown model counts as a screen, and a tick box under the list shows
  everything Home Assistant can cast to. Offering a speaker that does nothing is
  a smaller problem than hiding the display someone is looking for — which is
  the bug this picker had a version ago.

## 1.9.10

**Fixed: the Cast picker couldn't see a display that wasn't doing anything.**
A Hub sitting idle, asleep or switched off at the wall was missing from the
list — which is exactly backwards, since a free screen is the one you want to
send the week to.

- The picker identified a Cast device by its attributes carrying `app_id`, on
  the reasoning that only a Chromecast reports which receiver app it is running.
  True enough, but Home Assistant leaves out attributes that are `None`, and a
  display running no app publishes neither `app_id` nor `app_name`. So the
  picker could see a Hub in the evening and not in the morning.
- It now asks Home Assistant which entities the Cast integration actually owns,
  with `{{ integration_entities('cast') }}` through the template API. That is
  the question that was being asked all along.
- If Home Assistant won't render the template, every media player is listed
  instead. A list with a Sonos in it that DashCast will refuse is a nuisance; a
  list missing the display someone is looking for is this bug.
- The test harness was flattering the old code: its fake Home Assistant always
  sent `app_id`, even as `None`. It now leaves those attributes out the way the
  real one does, and the old filter fails against it immediately.

## 1.9.9

**Fixed: on a cold open, today's meal sat behind the week bar** — the day and
most of the photo cut off above the top of the screen.

- **One measurement was the mistake.** 1.9.5 worked out where today's card
  should go, scrolled there once, and considered the job done. A page is not
  finished settling at that moment: the offline banner appears and disappears
  above everything (and it is tall, because it carries the phone's status-bar
  inset), a photo that turns out to be a dead link collapses the card it was in,
  and a phone can apply its own restored scroll position after the load event.
  Any of those moves the card after it has been placed.
- **The intent is now held for two seconds and re-applied**, which costs two
  measurements and no scroll when the card is already right. It ends the moment
  the person touches the screen — `touchstart`, `wheel` or a key, never the
  scroll event, because our own scrolling raises that too and telling them apart
  is guesswork.
- **Where the bars end is measured, not modelled.** It now reads the week bar's
  own position on screen rather than adding up the top bar's height, the safe
  area and any banner. Once the page has scrolled, the bar is stuck and where it
  actually is cannot be wrong — and the model is what got this wrong.
- **The "it's on screen already, leave it" rule is gone.** It could not tell
  "today is where it should be" from "today is eighty pixels too low because the
  banner was still up when this was worked out", so it never corrected the
  second one. Nothing replaces it: with the whole week on screen there is
  nowhere to scroll and the browser ignores the request.
- `history.scrollRestoration` is now `manual`. This app decides where the page
  should be looking, so the browser must not also have an opinion.

**The week's Today button works when you are already on this week.** It was
disabled there, because going flat is how the bar says which week you are
looking at. But it has a second job now — scrolling back to today's card after
you have wandered off down the week — and a button that looks like the answer to
"take me back" should not be the one control on the page that ignores you. It
keeps the flat look (a class rather than `disabled`) and stays pressable. The
planner's and the shopping list's are unchanged: they have nothing to scroll to.
- The test harness grew a fake layout with sticky bars and a page that can
  change height, and reproduces the reported symptom before the fix.
- `CACHE_VERSION` is `mp-v13`.

## 1.9.8

**Guests.** "Guest(s)" is now in the household list, and on any meal you can
turn it on and say how many. Alex, Sam, Jo and Guest(s) × 2 is five people,
and the shopping list buys for five.

- **A person with a number, not a number hidden on the meal.** It sits among the
  eater toggles, takes a colour and a chip like everybody else, and the one
  thing it does differently is stand for more than one mouth. Everything that
  was already scaled by how many are eating — the shopping quantities, the
  ingredient lists on the card backs, the calories cooked in total, the kitchen
  display — is scaled by the head count instead, in both the app and the server.
  The two work it out the same way on purpose: quantities that disagree in front
  of someone holding a trolley are worse than no quantities at all.
- **The count belongs to the meal**, because six for dinner on Saturday says
  nothing about Tuesday. Turning the slot off forgets the number rather than
  keeping it for next time, which is how six people get cooked for by accident.
- **Guests are exempt from the one-dinner rule.** Marking someone for a meal
  takes them off the other meal that day; two friends at the early sitting and
  four relatives at the late one are not the same people twice.
- The slot is never "not eating" — it isn't anybody until a meal says how many
  of them there are — is not offered as the cook, and can't be deleted, only
  renamed. It appears with the first real person in the household, so a brand
  new install doesn't open on "you have one person, Guest(s)".
- It is created on the way out of `load_data`, which runs on reads too, so its
  id is fixed rather than generated: a fresh one each time would give a week
  saved yesterday a guest who no longer exists.
- `CACHE_VERSION` is `mp-v12`.

## 1.9.7

**Fixed: 1.9.6 wouldn't start.** `display.py` was new in that release and the
Dockerfile copies its modules into the image by name — so the built image had
no such file and the add-on died on the import, taking the kitchen display with
it. Dev mode ran fine throughout, because dev mode runs the folder, where the
file was there all along.

- The `COPY` line is now a `*.py` glob. The explicit list existed to keep
  `ai_bridge.py` (a PC-side script) out of the image; 6KB that is never executed
  is a far better trade than a release that refuses to start.
- This was the one failure the tests structurally could not see: they all import
  from the source folder. There is now a check that builds the image's `/app`
  the way the Dockerfile would, then starts the app from it with nothing else on
  `sys.path` — it reproduces this crash against the old line and passes against
  the new one.

## 1.9.6

**The kitchen display can be dressed to suit the kitchen.** Household → How the
kitchen display looks: accent colour, light or dark, text size, which parts are
on screen at all, and dimming overnight.

- **These are the house's settings, not a device's.** The app's own appearance
  panel is per device and lives in localStorage, which is no use at all for a
  screen nobody opens the app on. So they are kept on the server, edited from a
  phone, and sent to the display with the plan it already polls for once a
  minute — nothing to re-cast, and no second request for the sake of a dozen
  small fields.
- **Text size scales the display, not the type.** Everything in `kitchen.css` is
  sized in `vh` and `vw`, so there is no font-size to turn up. The screen is
  laid out at 1/zoom of the viewport and scaled back up to fill it, which grows
  the photos, rules and gaps along with the words. At the default size there is
  no transform at all — not even `scale(1)` — so what is on the wall today
  renders exactly as it did.
- **Turning a part off gives its space to what's left.** A hidden clock makes
  the day name the headline; a hidden week strip goes to the meal cards; with
  nothing left in the right-hand panel it stops taking a third of the screen.
- **Dimming is a black sheet at low opacity**, not a filter — nothing for the
  Hub to composite twice — and never fully opaque. The window wraps midnight,
  which is the whole point of it, so the test is "after the start *or* before
  the end", not "and".
- Values are validated on the way in (`display.py`), because a bad one here
  doesn't show as an error, it shows as a wall display gone black in an empty
  kitchen.
- `CACHE_VERSION` is `mp-v11`: the kitchen page and the app both changed.

**The add-on has the app's own icon in Home Assistant.** `icon.png` for the
store list and sidebar, and `logo.png` — the house on an accent panel — across
the top of the add-on page.

- Drawn by `icon.py` rather than kept as artwork, so there is still one drawing
  behind the home-screen icon, the favicon, the top-bar mark and now the add-on
  store. `python3 icon.py --brand .` rewrites both; the render was generalised
  to a rectangle to do it.
- They have to be real files in the add-on folder — Supervisor reads the folder,
  not the running app — so unlike every other image here they are committed.

## 1.9.5

**Opening the app puts you on today.** The Week already opened on the current
week, but seven day cards are one column on a phone, so by Friday the day you
wanted was two screens down. The week view now scrolls to today's card on
opening, and the Today button takes you to the day rather than only to the week.

- It scrolls only when it has to. On a Monday, and on a wide screen where the
  whole week is on the page already, the card is where it was going to be
  anyway, and a scroll that changes nothing still costs a flicker.
- The stop is worked out from the measured heights of the two sticky bars at the
  top and the phone's fixed tab bar at the bottom, not from `scrollIntoView`,
  which would tuck the card behind them.
- **A phone is rarely closed, only put down**, so `start_url` alone doesn't get
  you there — a resumed app keeps whatever tab and week it was left on. Coming
  back after more than thirty minutes now counts as a cold open and returns to
  this week, at today. Shorter absences don't: nipping out to a timer and coming
  back to a changed tab feels like an app with a mind of its own. Nor does it
  fire mid-edit, with the add panel open or a field focused, where it would cost
  someone a half-typed recipe.
- Links and the manifest's shortcuts still land on the tab they name; only a
  plain launch defaults to the week.
- `CACHE_VERSION` is `mp-v10`, or phones would keep the old `app.js`.

**The add-on can now keep the kitchen display on a Cast screen itself.**
Household → Kitchen display lists every Cast device Home Assistant can see, and
picking one puts this week's meals on it and keeps them there.

- **Casting is done by Home Assistant, not by us.** It is a protobuf
  conversation over TLS that nothing in the standard library can hold, and this
  app has no dependencies to spend on it. `cast.py` asks Supervisor's proxy to
  the core API which media players exist and asks DashCast to load `/kitchen` on
  the chosen one, so the only new requirement is the DashCast integration from
  HACS — and `homeassistant_api: true` in `config.yaml`, which is what gets the
  add-on a token to ask with.
- **It waits its turn.** A Nest Hub is also a photo frame, a timer and a
  speaker; an add-on that re-cast every minute would take it away mid-song. The
  watcher only steps in when the screen is idle or showing its ambient view,
  and gives up after three casts the display never acknowledged rather than
  looping quietly for the rest of the year.
- **The address is the hard part.** The display fetches the page itself, and the
  container can only see its own 172.30.x address — the same blindness
  `cover_host` deals with for certificates. So the Host header from `/api/data`
  is remembered: an address a phone really used is one that works from across
  the house. Home Assistant's own `internal_url` is the fallback, and `cast_url`
  overrides both.
- Nothing here is load-bearing. No Supervisor token, no DashCast, no device
  chosen — each just means the picker reports casting as off, and on a PC the
  card doesn't appear at all.

**Every option in the Configuration panel now explains itself.** The reasoning
was in `config.yaml` comments, which is the one place nobody configuring an
add-on ever looks. It now lives in `translations/en.yaml`, which is where Home
Assistant reads the label and description under each field from.

- Two new options: `cast_device` pins the display from outside the app (empty,
  the default, leaves the choice to the app and the app's picker), and
  `cast_url` overrides the address the display is sent to.

## 1.9.4

**Fixed: the spoon in the icon was lying across its own handle.** The bowl is an
ellipse turned onto the diagonal the handle runs down, and the rotation puts the
first of its two semi-axes on that diagonal — but the smaller number was first,
so the bowl came out ninety degrees off and wider than it was long. Swapped, and
made a little more elongated at about 3:2. The two fields are now named `along`
and `across` at both ends rather than `brx` and `bry`, which gave no clue which
was which.

- `icon.REV` is 4, so a browser holding the old drawing refetches it: the icon
  URLs don't change when the artwork does, so that counter is the only thing
  that tells it to.
- `CACHE_VERSION` is `mp-v9` for the same reason on phones. The service worker
  serves icons from its own cache before the network is consulted, so without
  this the old spoon would survive one more load.

## 1.9.3

**A new icon: a house with a spoon and fork crossed inside it.** It replaces the
plate-and-cutlery drawing, and it now appears in three places rather than one —
the home screen, the favicon in the browser tab, and the mark in the top bar.
All three still follow the accent colour and the light/dark ink, as the home
screen icon already did.

- One set of shapes, three uses. The favicon used to be an emoji in an inline
  SVG and the top-bar mark another emoji; both are now the same PNG `icon.py`
  already draws, so there is no second copy of the artwork to drift out of step.
- The top-bar mark has no `src` in the HTML. Its background is the accent and so
  is the bar behind it, so only the house shows — but the head script can't
  reach into the body, and a default-green square would flash on a rose bar
  before the page corrected it. `paintShell()` fills it in instead.
- A 64px size was added for those two smaller uses.

**The icon draws about four and a half times faster.** The new artwork is all
distance-to-a-line arithmetic, and a 512px icon asks about a million points —
so working out each stroke's direction and length a million times over, in
Python on a Raspberry Pi, was the difference between one second and thirty. The
strokes are now worked out once into a table with a bounding box each, and most
of the border is answered by four comparisons rather than thirteen shapes. The
512px icon went from 4.5s to 1.0s, which is quicker than the old, simpler
drawing managed.

## 1.9.2

**The desktop layout is wider, and the cards with it.** The page was capped at
1100px, set when this was mostly read on a phone, which left the meal library
squeezed into the middle third of a monitor. It now goes to 1500px, and library
cards go from about 260px wide to about 360px. There's still a cap — a plan row
stretched across a 34" screen is its own kind of unreadable.

- Week cards were raised too. Left as they were, the extra room would have gone
  into a sixth column, which for a seven-day week strands one card alone on the
  second row. Four wider columns give 4 + 3.

**Fixed: quantities printing over ingredient names on a flipped card.** The
quantity is a flex item, and a flex item will shrink below its own content
unless told not to — so anything longer than the 2.9rem floor, "1.5 tbsp" say,
was squeezed narrower than its text and spilled across the name beside it. The
quantity now holds its width and the name gives way instead, which it can
afford to do because it wraps and a quantity doesn't.

**The navigation pills are centred and all one width.** They were sized to their
labels, so the row read as a ragged line with "Plan" a third the size of "The
Week". They now share the space equally, stop growing at 11rem so five pills
don't span a whole monitor, and sit centred as a group. The phone bottom bar is
unchanged.

## 1.9.1

The accent colour now reaches the two places it couldn't before: the icon on
the home screen and the screen you see while the app is opening.

**The home-screen icon is drawn in your accent.** Pick rose in Appearance and
the icon is rose. It follows light and dark too — in dark mode the accent is a
pale pastel, so the knife and fork are drawn dark rather than white, the same
way the top bar already works.

**The launch splash matches the app it's opening.** Its background is the page
colour, so it's cream in light mode and near-black in dark, rather than a slab
of green in front of a dark app.

**Add a meal to a date straight from the library.** Browsing the library is
where you decide you fancy something, so each meal card now has an "Add to
date" button. It opens a date picker; choose a day and you land on the planner
at that week with the meal already in place and the day marked, ready for who's
cooking and who's eating.

- The planner is where you finish, rather than a second smaller copy of those
  controls somewhere else.
- It's one request, with the meal already on it. Creating the block and then
  setting the meal would have stranded an empty block on that day if the second
  call failed.
- The picker is limited to a year either side of today — not a restriction
  anyone will meet on purpose, just so a slipped keystroke lands somewhere you
  can see is wrong instead of quietly planning dinner for the year 0202.
- Greyed out when offline, like the other buttons on those cards.

**The "AI estimates are off" banner is much shorter.** It used to run to four
sentences, two of which explained that macros can be typed in by hand — while
sitting directly above the boxes for doing exactly that. It's now the headline
plus one short reason: "AI estimates are off. The AI bridge isn't running on
your PC." The other two causes (still probing, no Claude Code installed) were
trimmed to one sentence each as well.

**Swipe sideways to change tab.** On a phone, where the tabs are a bottom bar
and already read as a row of pages, dragging left or right moves through The
Week, Plan, Shopping, Meals and Household in the order they appear on the bar.
It stops at both ends rather than wrapping round.

The gesture is deliberately fussy, because a page that changes tab when you
meant to scroll feels broken in a way that's hard to put a finger on. It has to
be one finger, travel at least 60px, stay within about 29° of horizontal, and
finish inside 700ms. It's ignored if it starts on a text field, on anything
that scrolls sideways of its own accord, on the tab bar, or hard against the
left edge where iOS keeps its own back gesture. A swipe that lands also
swallows the click that might follow it, so you can't flip a meal card over on
your way past.

Nothing follows the finger during the drag — switching tab rebuilds the whole
view, and there's no cheap way to drag a page that doesn't exist yet. The
arriving view slides in afterwards instead, which is enough to show which way
you went, and is skipped entirely under `prefers-reduced-motion`.

**Today's highlight follows the accent too.** The border round today's card and
the "Today" pill were a fixed orange — fine behind green, a clash behind rust,
amber or cocoa. Each accent now has its own marker: the opposite hue at the
same saturation, so it stands out from the accent by construction rather than
by luck. The faint wash behind the card is mixed from it, so the whole
highlight moves together.

- All 24 markers carry the pill text at 4.5:1 or better, checked rather than
  eyeballed.
- Slate and charcoal are so nearly grey that their true opposite would be
  another grey, so those two take the opposite hue at a saturation that shows —
  which is why the neutral themes still get a warm marker.
- `--warm` was doing two jobs. It's now only the offline dot, which should stay
  a warning colour whatever accent is picked; `--today-mark` took over the rest.

**The cutlery is redrawn.** The fork's tines are wider with narrower gaps
between them, which stops them reading as a comb at icon size. The knife is no
longer a symmetrical blade — that looked like a spoon — but has a straight
spine flush with its handle and the point at the top corner, so only the
cutting edge curves. It also sits further right, clear of the plate and mirror
to the fork.

- The accent is a per-device setting in `localStorage`, and the phone's OS —
  which is what actually fetches the manifest and the icons — has no sight of
  it. So the page resolves the colours from the stylesheet and puts them on the
  URL: `/manifest.webmanifest?c=…&f=…&b=…`, `/icon-192.png?c=…&f=…`. The
  palette stays in `style.css` alone; adding an accent still needs no change
  anywhere else.
- `manifest.webmanifest` is now a template the server tints per request rather
  than a file served as-is. Everything in it except the colours is still edited
  in that file.
- `icon.py` takes its two colours as arguments and caches per size and colour.
  Requesting the manifest starts drawing the icons it names in the background,
  so the fetch that follows is served from memory.

**Already installed on a phone?** The icon there was copied at install time.
Android re-checks the manifest on its own and will catch up within a day or so.
iOS never re-checks — to change the icon on an iPhone, remove it from the home
screen and add it again.

## 1.8.1

Taking the shopping list to the shop, by both routes: hand it to Google Keep
before you leave, or read it out of the app's own saved copy if you didn't.

**The shopping list is now readable offline.** It's still worked out by the
server — the phone can't rebuild it — but the service worker keeps the last
answer it saw for each week, so a list you opened at home is there in the shop
whether or not you remembered to share it first.

- Cached per week: the query string is part of the cache key, so last week and
  next week don't overwrite each other.
- It says how old it is, because unlike the week view there's no way to tell
  from the contents whether the plan has moved on since.
- A week you never opened at home says so, rather than failing silently.
- The Share button works from the saved copy too, so the two go together.
- **Offline, the list no longer rebuilds itself every 20 seconds.** The poll
  that watches for the server coming back re-renders the current view, which
  would have thrown away your place halfway round the shop. Offline, once the
  list is up it stays up.

**Share the shopping list to your phone, so it survives the walk to the shop.**
A "Share list" button on the Shopping tab hands the week's list to the phone's
share sheet, where Google Keep is one of the targets. Do it at home on the
wifi and Keep has the list in the shop, with the Pi long out of range.

- There is no way to write into Keep directly — its API is Workspace-only and
  personal accounts can't use it — so the share sheet is the supported route.
  The list arrives as a text note; Keep's "Show checkboxes" turns it into a
  tickable list.
- The text is flat, one item per line, because every line becomes tickable —
  a "TO BUY" heading would become a thing to buy. The week goes in the note's
  title instead of the first line, for the same reason. Cupboard staples come
  last, and meals with no ingredients on file are listed as "Also buy for:".
- Desktop has no share sheet, so there the button copies to the clipboard, and
  falls back to a downloaded `.txt` if the clipboard is blocked.
- Print moved out of the sticky week bar into a row beneath it, alongside
  Share. That bar has to stay short enough to keep the dates readable.

## 1.8.0

**Meal library cards turn over to their ingredients too**, and a card is now
only as tall as the side you're looking at.

- Tap a library card's title or photo to see its ingredients at the recipe's
  own serves count; tap the list to turn it back. Cards with no ingredients,
  or no serves count to scale them by, stay flat as before.
- **Fixed: a long ingredient list made the *front* of the card tall.** Both
  faces share one grid cell, so the card was always sized to the taller of the
  two, leaving a mostly empty picture card on the week view. The height now
  follows whichever face is showing and animates between them.
- The height is timed around the half-turn: it leads when growing so the list
  has room by the time it appears, and waits when shrinking so it isn't cut
  off from under itself. It respects `prefers-reduced-motion`.
- The list-building and the flip assembly were duplicated between the week
  view and the library; they're one function each now.

**On a phone, the tabs are now a bar along the bottom.** Five pills in a
sideways-scrolling row at the top of the screen meant Household was invisible
until you found the scroll, and the top of a phone is the hardest place to
reach with the hand that isn't holding a spoon.

- Same five buttons and the same routing — only the stylesheet moves them,
  below 700px wide. Wide screens keep the pills in the header.
- Each tab gets an outline icon, stroked in `currentColor` so the active one
  takes the accent along with its label and the rule above it. Checked at
  4.5:1 or better for all 12 accents in both themes.
- Sits above the home-indicator inset, and the toast was raised to clear it.
- The active tab now carries `aria-current="page"`, since as a bottom bar this
  reads as site navigation rather than a set of pills.

**The week picker is now one row and stays put as you scroll.** It was two
rows — a "This week" / "Week of ..." heading above the date range — and it
scrolled away, so changing week from the bottom of a long list meant scrolling
back up.

- The heading is gone from the bar. It is kept as a screen-reader-only `h1` so
  the page still has a heading, and the date range moves up to carry the row.
- The bar is pinned directly under the top bar. That edge moves with the
  safe-area inset and with the tabs wrapping, so `app.js` measures the top bar
  and publishes `--topbar-h` rather than the stylesheet guessing at it.
- Knowing whether you're on the current week was the heading's other job. The
  **Today** button now goes flat when you are already there.
- Unpinned again for printing, where the date range stays — a printed shopping
  list needs to say which week it's for.

**Twelve accent colours instead of six**, and the phone's status bar now
follows the one you pick.

- Added Olive, Indigo, Rose, Amber, Cocoa and Charcoal, and reordered the row
  so it runs round the colour wheel rather than in the order they were added.
- The Android status bar and task-switcher card were stuck on the default
  green. They take their colour from the `theme-color` meta tag, which was a
  hardcoded hex; it is now written from the accent the stylesheet resolved, and
  set before first paint so it doesn't flash green on launch. iOS needs nothing
  — its status bar is transparent and already shows the top bar through it.
- **Fixed: the faint hover tint stayed green whatever accent you chose.**
  `--accent-wash` was a fixed `#eef4f0`; it is now mixed from the live accent.
- **Fixed: Rust failed contrast against the white header text** at 4.40:1.
  Darkened a shade to `#b26039`, which clears 4.5:1. Every accent has now been
  checked at 4.5:1 or better on all three pairings, in both themes.

## 1.7.3

**Fixed: the "Today" highlight stopped moving once a phone left the house.**
`today` and `thisWeek` came from the server with `/api/data`, so an offline PWA
was reading them out of a cached response — frozen at whatever day the plan was
last downloaded. Three days away and the highlight was still three days behind.
The same staleness applied to a page simply left open overnight.

- Both are now worked out from the device's own clock and the server's values
  ignored. `monday_of` and the client agree that a week starts on Monday.
- The day rolls over on a timer just after midnight, and — because phones
  throttle background timers and laptops get shut for a week — is re-checked
  whenever the page becomes visible, on every 20-second poll, and on restore
  from the back/forward cache.
- When the week turns over, any view still sitting on "this week" follows it.
  A week you navigated to on purpose stays where you left it.
- The week view now has a valid week to draw before the first fetch, so a cold
  start with no server and no cache no longer comes up blank.

## 1.7.2

**Fixed: a restart could silently strand every phone set up for offline use.**
The address a phone actually uses (`192.168.0.x`) can only be learned from a
real request — the add-on runs in a bridged container and sees a docker address
at startup. That learned address was held in memory only, so on the next
restart or update the certificate was rebuilt from the startup list alone, the
LAN address dropped out of it, and the handshake failed. Inside an installed
PWA there is no certificate warning to click through: it just falls back to the
cached copy and shows "Offline", with nothing in the log to say why.

- Learned addresses are now kept in `/data/certs/learned.hosts` and go back
  into the certificate at startup, so a restart keeps covering whatever the
  phones were set up against.
- The certificate authority is untouched by this — phones stay trusted.
- Only plain hostnames and IPv4 addresses are accepted, capped at 12, and an
  address is remembered only once the certificate has actually reissued.
- Setting `cert_hosts` still works and is worth doing as a belt-and-braces
  measure; it is no longer the only thing standing between you and this.

## 1.7.1

**Ingredient names are tidied on save.** However an ingredient is typed —
`chopped TOMATOES`, `olive oil` — it is stored in Title Case, so the meal card,
the week view's flip side, the shopping list and the kitchen display all read
the same. Acronyms and measurements are left alone (`BBQ sauce`, `2% milk`,
`UHT milk`), and hyphens, slashes and apostrophes are handled properly
(`Semi-Skimmed Milk`, `Hershey's Chocolate`). Meals saved before this update are
tidied the next time they are loaded.

## 1.7.0

**https, so the offline copy actually works.** 1.6.0 shipped offline viewing but
it could never engage: browsers only allow it on a secure address, and a home
network has no public name to get a real certificate for.

- **New `https_enabled` option.** The add-on now runs a small certificate
  authority of its own, keeps it in `/data/certs`, and serves the same app on
  **8443** over https. No domain, no port forwarding, nothing outside the house.
- Plain http on 8080 is untouched and the kitchen display still uses it — the
  Nest Hub can't be given a private CA.
- **New `/setup` page**, reachable over http, that walks a phone through
  trusting the certificate. It detects iPhone vs Android and puts the right
  instructions first, including the Certificate Trust Settings step on iOS that
  is easy to miss. The week view now links to it instead of mentioning the
  README.
- **The certificate teaches itself the right address.** The container sees a
  Docker address, not the `192.168.x.x` one you type, so the address guessed at
  startup is usually wrong. Loading `/setup` over http tells the server the
  address you are actually about to use; it adds it and reissues on the live
  listener, with no restart. Extra names can also be listed in `cert_hosts`.
- The CA is generated once and never regenerated — replacing it would silently
  break every phone already set up. The server certificate is reissued when the
  address list changes or it comes within a month of expiring. It is valid for
  800 days, which is inside the ceiling Apple applies even to user-added roots.
- Certificates use P-256 rather than RSA, so generating them on a Pi is
  instant rather than a visible pause at startup.

## 1.6.0

**Faster first load.**

- **The long pause on opening the app is gone.** Every page load asked the
  server for data, and the server would not answer until it had checked whether
  the AI helper on the PC was reachable - a network call with a four second
  timeout that only ever timed out when the PC was off, which is most of the
  time. The check now runs on a background thread and the page is served the
  last known answer immediately.
- **About 40ms shaved off every single request.** Responses were being written
  as two separate TCP sends, which is exactly the pattern Nagle's algorithm
  delays. TCP_NODELAY is now set. In a bench test, thirty requests went from
  1.19s to 0.01s.
- **Connections are reused.** The server spoke HTTP/1.0, so a phone paid a fresh
  TCP handshake for the page, the stylesheet, the script and every API call.
  HTTP/1.1 keep-alive is now on.
- **One fetch on startup instead of two.** Opening a tab re-fetched everything
  immediately after the initial load had already fetched it.

**Reading the week away from home.**

- **The app can now be installed to a phone's home screen** and the week read
  while off the home network. A service worker keeps a copy of the app and the
  last meal plan it saw; meal photos are kept too.
- Offline it is strictly read-only. A banner says how old the copy is, editing
  controls grey out, and any change is refused up front - nothing is queued,
  because two people editing the same week from different places would silently
  overwrite each other.
- The shopping list is worked out by the server, so it says so rather than
  showing a blank page when offline. The Week and the meal library both read
  from the saved copy.
- **This needs an https address.** Browsers only allow offline caching in a
  secure context, so it will not engage over `http://<your-ha-ip>:8080`. Until
  the app is reachable over https the week view carries a one-line note saying
  as much. See the README.
- App icons are drawn by the server (`icon.py`) rather than stored as image
  files, since the add-on source lives on a Windows share.

## 1.5.1

- Renamed the "This Week" tab to "The Week", since the view can show any week,
  not just the current one. The heading inside the view still reads "This week /
  Next week / Last week" as you move between weeks.

## 1.5.0

- **Meals page restyled around browsing.** The "Add a meal" form no longer sits
  at the top of the page taking up the whole screen - it's collapsed into an
  "Add meals" panel that you tap to open, so the page now opens straight onto the
  search box and the meal library, which is what most visits are for.
- Adding meals and bulk-importing are now two tabs of that one panel: "Add a
  meal" and "Bulk Add" (the old "Import several meals at once"). Editing a saved
  meal opens the panel on the "Add a meal" tab automatically.

## 1.4.2

- **Kitchen hub: long ingredient lists now page on a tap instead of scrolling.**
  The Nest Hub can't be relied on to scroll an overflowing card, so a list too
  long for the card is split into pages sized to whatever fits. A tap on the
  ingredients moves to the next page; a tap on the last page turns the card back
  to the photo. Short lists stay a single page and a tap just flips back. The
  footer shows where you are ("More ↓  2 / 3"). The phone week view still
  scrolls, which works fine in a normal browser.

## 1.4.1

- Ingredient lists on the flip side now scroll vertically when they're too long
  for the card, instead of running off the bottom - most noticeable on the
  kitchen hub, where the card is a fixed height. The quantity column was
  tightened and the line font reduced slightly so more of each ingredient fits
  on one line before scrolling is needed.

## 1.4.0

- **Tap a meal's picture to see its ingredients.** Meal cards now flip over: the
  photo turns to reveal the ingredient quantities for that meal, scaled from the
  recipe's own serving figure to the number actually sitting down to eat it
  (e.g. a fish pie that serves 4, eaten by 3, shows 0.75 of each line - 525g
  potatoes, 319ml milk, and so on). The list is titled "<Meal> ingredients for
  X people"; tap it to flip back. Works on both the phone week view and the
  kitchen hub. Unlike the shopping list these figures are what goes in the pan,
  so they're not rounded up to trolley quantities. Cards for meals with no
  ingredients or no serving figure stay as they were.
- The `/api/kitchen` payload now carries each meal's scaled ingredient lines and
  serving figure, so the kitchen display needs no recipe lookups of its own.

## 1.3.0

- **AI nutrition estimates on the Pi, via a bridge on your PC.** `ai.py` is now
  a dispatcher: with no bridge configured it behaves exactly as before (local
  Claude Code CLI); set `ai_bridge_url` in the add-on Configuration tab and it
  sends estimate requests over HTTP to `ai_bridge.py` running on your PC, which
  has the CLI. When the PC is off the add-on degrades to manual macros and
  recovers automatically when it's back - the reachability check is cached so an
  off PC never hangs a page load. Optional `ai_token` shared secret.
- The CLI implementation moved to `ai_local.py` (imported by both `ai.py` and
  the bridge). `decode_image()` stays local so ordinary photo uploads never
  depend on the bridge.
- To run the bridge: copy `ai_bridge.py`, `ai_local.py` and `Start AI Bridge.bat`
  onto the PC and double-click the .bat. See AI-BRIDGE-SETUP.md.

## 1.2.0

- **Daily backups now actually run daily.** The dated `data.json` backup moved
  from `run.sh` (which only fired at container start) into a timer thread in
  `server.py`, so a snapshot is taken every day the add-on is up, not just when
  it happens to restart. Still keyed on the date and still keeps the last 7.
- **Cache headers on static files and photos.** Meal photos are sent with a
  one-year immutable cache (their filenames are timestamped and never reused),
  so the Nest Hub stops re-downloading every photo each time it re-casts. HTML,
  JS and CSS carry an ETag and revalidate, returning a cheap 304 when unchanged
  while still picking up edits immediately in dev mode.

## 1.1.0

- **Dev mode.** Turn on `dev_mode` in the add-on's Configuration tab and the
  add-on runs the source directly from the add-ons folder, so a change needs a
  Restart (seconds) rather than a Rebuild (minutes). Turn it off for a release
  and it runs the copy baked into the image. Falls back to the baked-in copy
  automatically if the live folder isn't there.
- **Timezone fixed.** `tzdata` is now installed, so the container follows the
  timezone Home Assistant passes in. Previously it ran in UTC, which during BST
  rolled the planner over to the next day an hour early.
- Dropped `armhf` and `i386` from `arch`; `python:3.12-slim` publishes no base
  image for either, so a build on those would have failed.
- Stopped Python writing `__pycache__` into the add-ons folder.

## 1.0.0

- First release: the Home Meal Planner packaged as a local Home Assistant add-on.
- Data and meal photos moved to the persistent `/data` volume, so they survive
  updates and are picked up by Home Assistant backups.
- Existing `data.json` and images bundled in `seed/` and copied in on first run.
- Rolling daily backups of `data.json` kept in `/data` (last 7).
