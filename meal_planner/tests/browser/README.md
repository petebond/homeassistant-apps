# Browser tests

The Python tests cover the server. These cover the half that only exists once
`static/app.js` is running in a page: which element gets built, what colour it
comes out, and what a drag or a keypress actually posts.

They run `app.js` for real, against `index.html`, with `fetch` faked. Nothing
is mocked inside the app itself, so a change that breaks the wiring between
`renderPeople()` and the endpoint fails here rather than on a phone.

    npm install jsdom          # once
    node tests/browser/test_colour_picker.js
    node tests/browser/test_chip_order.js
    node tests/browser/test_drag_handle.js
    node tests/browser/test_kitchen_shopping.js
    node tests/browser/test_kitchen_strip.js
    node tests/browser/test_settings_and_rename.js

Each exits non-zero and names what failed.

| file | covers |
| --- | --- |
| `test_colour_picker.js` | the 36-colour grid, which swatches are greyed out, the lettering each colour gets, and where the week views scroll to when the week changes |
| `test_chip_order.js` | name chips in household order rather than tap order, and the star picker's tones on a colour where the gold can't be seen |
| `test_drag_handle.js` | the grip, a pointer drag from `pointerdown` to `pointerup`, the guest slot staying last, Escape, and the arrow keys |
| `test_kitchen_shopping.js` | the shopping panel on `/kitchen`: the corner count, what an ordered row won't do, what the stepper and the tiles post, the paging, and the three things that must not happen to a display somebody is touching |
| `test_kitchen_strip.js` | the strip along the bottom of `/kitchen`: how many days it asks for, and which meal names the one-line clamp claims — a selector that counts backwards from the end of a column, read out of the stylesheet rather than copied into the test |
| `test_settings_and_rename.js` | every Settings card being a `<details>` that arrives shut, the Home-Assistant-only ones staying hidden as one, the remembered names not being fetched until that section is opened, and correcting a name from either end — the shopping row and the Settings row — including a Settings correction reaching the line on the list |

Note that jsdom does not run the browser's own "clicking a summary toggles the
details" behaviour, so `test_settings_and_rename.js` sets `.open` and fires
`toggle` itself. It is testing what app.js does when a section opens, not
whether `<details>` works.

## Four things to know before adding to these

**jsdom has no layout.** Every `getBoundingClientRect()` returns zeros, so
anything that measures the page has to be given a fake. `test_drag_handle.js`
supplies one for the household rows, and it has to model the dragged row being
`position: fixed` and out of flow - without that, the midpoints it reports are
the ones from before the drag started, and the test passes while the app is
wrong.

The same trap, differently shaped, in `test_kitchen_shopping.js`: its fake
`clientHeight` returns zero for anything inside a `hidden` element. Measuring a
panel before it is on the screen is the easy mistake on that display, and a
fake that answered the same either way would let it through. When you write a
layout fake, make it model the thing that would go wrong, not just the thing
that goes right - and check it fails by breaking the code on purpose.

**The kitchen display never stops.** `kitchen.js` sets three intervals on
itself - the poll, the clock and the reload check - and each one holds jsdom's
event loop open, so a test that boots a display will hang instead of exiting.
End with `process.exit()`. If you need to fire one of those callbacks, capture
`setInterval` before `win.eval` and call it by hand rather than waiting a real
minute; `test_kitchen_shopping.js` does this for the poll and for the
six-hourly reload check, and does the same with `setTimeout` for the idle
close.

**Wait for the app, don't guess.** Every action posts and then refreshes, and
the first version of the drag test used nested timeouts and ended up asserting
against a list the app had already moved past. Use `await settle()`, and re-read
the order from the DOM at the start of each section rather than carrying one
forward from the last.
