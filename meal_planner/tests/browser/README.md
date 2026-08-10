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

Each exits non-zero and names what failed.

| file | covers |
| --- | --- |
| `test_colour_picker.js` | the 36-colour grid, which swatches are greyed out, the lettering each colour gets, and where the week views scroll to when the week changes |
| `test_chip_order.js` | name chips in household order rather than tap order, and the star picker's tones on a colour where the gold can't be seen |
| `test_drag_handle.js` | the grip, a pointer drag from `pointerdown` to `pointerup`, the guest slot staying last, Escape, and the arrow keys |

## Two things to know before adding to these

**jsdom has no layout.** Every `getBoundingClientRect()` returns zeros, so
anything that measures the page has to be given a fake. `test_drag_handle.js`
supplies one for the household rows, and it has to model the dragged row being
`position: fixed` and out of flow - without that, the midpoints it reports are
the ones from before the drag started, and the test passes while the app is
wrong.

**Wait for the app, don't guess.** Every action posts and then refreshes, and
the first version of the drag test used nested timeouts and ended up asserting
against a list the app had already moved past. Use `await settle()`, and re-read
the order from the DOM at the start of each section rather than carrying one
forward from the last.
