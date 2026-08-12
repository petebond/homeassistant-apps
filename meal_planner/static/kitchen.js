/* Kitchen display.
   Written deliberately plainly - XMLHttpRequest rather than fetch, no arrow
   functions, no template literals - because this runs on a Nest Hub, whose
   browser is an older Chromium than a phone's. */
(function () {
  "use strict";

  var REFRESH_MS = 60000;        // pull the plan once a minute
  // How long a tapped day stays up before snapping back to today, so a wall
  // display never gets stuck on Thursday because someone had a look.
  var AUTO_BACK_MS = (typeof window.KITCHEN_AUTOBACK === "number")
    ? window.KITCHEN_AUTOBACK : 60000;
  var CLOCK_MS = 20000;          // tick the clock
  var RELOAD_HOURS = 6;          // full page reload now and then, to self-heal

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];

  var lastGood = null;
  var failures = 0;
  var shownDate = null;
  var startedAt = new Date();
  var selectedDate = null;       // null means "follow today"
  var backTimer = null;
  /* Whether the rollover time has passed and the server has moved the display
     on: the day it is calling today is not the calendar's. Held here because
     both the label above the day name and the "nothing planned" line need it,
     and neither is given the whole feed. */
  var showingTomorrow = false;

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.appendChild(document.createTextNode(text)); }
    return node;
  }

  function clear(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  /* "Alex, Jo and Sam" reads better than "Alex, Jo, Sam" on a wall. */
  function nameList(names) {
    if (!names || names.length === 0) { return ""; }
    if (names.length === 1) { return names[0]; }
    return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
  }

  function twoDigit(n) { return (n < 10 ? "0" : "") + n; }

  function tickClock() {
    var now = new Date();
    $("clock").firstChild.nodeValue =
      now.getHours() + ":" + twoDigit(now.getMinutes());
    applyNightfall();
  }

  // ------------------------------------------------------- how it looks

  /* Sent with the plan on every poll, so a change made on a phone shows up
     here within the minute with nothing to re-cast. Held here as well because
     the clock tick needs the dimming times between polls. */
  var look = null;

  /* A theme forced onto this one display from the casting end -
     /kitchen?theme=light - which is what the preview's Light/Dark buttons and
     a hand-set cast_url both use. kitchen.html applies it before first paint;
     this is what stops the first poll, a moment later, putting the house's
     shared setting straight back over the top. Without it the buttons appeared
     to do nothing at all.

     Read once, because the URL doesn't change under a page that never
     navigates - the six-hourly reload keeps the query string. */
  var forcedTheme = (function () {
    var m = /[?&]theme=(light|dark)/.exec(location.search);
    return m ? m[1] : null;
  })();

  function remember(key, value) {
    /* So a reload doesn't flash the defaults before the first poll lands. */
    try { localStorage.setItem(key, value); } catch (e) { /* storage off */ }
  }

  function minutesNow() {
    var now = new Date();
    return now.getHours() * 60 + now.getMinutes();
  }

  function toMinutes(text) {
    var m = /^(\d\d):(\d\d)$/.exec(text || "");
    return m ? (+m[1]) * 60 + (+m[2]) : -1;
  }

  /* Whether the clock is inside the dimming window. The window nearly always
     wraps midnight - 22:00 to 06:30 - so "after the start" and "before the
     end" can't both be required; when it doesn't wrap, they must be. */
  function dimmedNow(from, to) {
    var start = toMinutes(from), end = toMinutes(to), now = minutesNow();
    if (start < 0 || end < 0 || start === end) { return false; }
    return (start < end) ? (now >= start && now < end)
                         : (now >= start || now < end);
  }

  function applyNightfall() {
    if (!look) { return; }
    var on = look.dim && dimmedNow(look.dimFrom, look.dimTo);
    // dimLevel is how bright it should be, so the sheet over the top is the
    // rest of the way to black.
    $("nightfall").style.opacity = on ? String(1 - (look.dimLevel / 100)) : "0";
  }

  function applyDisplay(settings) {
    if (!settings) { return; }
    look = settings;
    var html = document.documentElement;

    /* Only the theme can be overridden per display. The accent, the size and
       what's on screen stay the house's business: they are the settings the
       app can actually see it changing. */
    var theme = forcedTheme || (settings.theme === "light" ? "light" : "dark");
    html.setAttribute("data-theme", theme);
    html.setAttribute("data-accent", settings.accent || "green");
    var zoom = String((settings.scale || 100) / 100);
    html.style.setProperty("--k-zoom", zoom);
    if (zoom === "1") { html.removeAttribute("data-zoomed"); }
    else { html.setAttribute("data-zoomed", ""); }
    // What is on screen, not what the server asked for - so a reload of a
    // forced display doesn't blink through the house's theme on the way.
    remember("mp-kitchen-theme", theme);
    remember("mp-kitchen-accent", settings.accent);
    remember("mp-kitchen-zoom", zoom);

    /* Hiding a piece is one class on the screen rather than a hidden attribute
       on each part, so the layout rules that go with it - the meal row growing
       into the space a hidden week strip leaves - live in the stylesheet with
       everything else. */
    var screen = $("screen");
    screen.className = "screen"
      + (settings.showCook ? "" : " no-cook")
      + (settings.showClock ? "" : " no-clock")
      + (settings.showDate ? "" : " no-date")
      + (settings.showWeek ? "" : " no-week")
      + (settings.showPhotos ? "" : " no-photos");

    applyNightfall();
  }

  function showPhotos() { return !look || look.showPhotos !== false; }
  function showEmpty() { return !look || look.showEmpty !== false; }
  function showHeads() { return !look || look.showHeads !== false; }

  function fetchJson(url, onOk, onFail) {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url + (url.indexOf("?") === -1 ? "?" : "&") + "t=" + Date.now(), true);
    xhr.timeout = 15000;
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      if (xhr.status >= 200 && xhr.status < 300) {
        var parsed;
        try {
          parsed = JSON.parse(xhr.responseText);
        } catch (e) {
          onFail();
          return;
        }
        onOk(parsed);
      } else {
        onFail();
      }
    };
    xhr.onerror = onFail;
    xhr.ontimeout = onFail;
    xhr.send();
  }

  // ------------------------------------------------------------- rendering

  function renderHeader(data, entry) {
    var d = new Date((entry ? entry.date : data.today) + "T00:00:00");
    /* A label above the day and date, for the two occasions the big date could
       be mistaken for now: a day somebody has tapped, and the rollover time
       having moved the display on to tomorrow of its own accord. "Thursday" on
       a Wednesday evening is otherwise indistinguishable from a display stuck
       on the wrong day, and the word is cheaper than the doubt.

       They can never both apply: the rollover only ever labels the day the
       display chose for itself, which is the one tapping anything moves off. */
    var label = "";
    if (entry && !entry.isToday) {
      label = "Currently showing";
    } else if (entry && showingTomorrow) {
      // No entry means the feed had no day in it to show, and the name falls
      // back to "Today". Labelling that "Tomorrow" would be two answers.
      label = "Tomorrow";
    }
    var tag = $("showing");
    tag.hidden = !label;
    if (label) { tag.firstChild.nodeValue = label; }
    $("day-name").firstChild.nodeValue = entry ? entry.name : "Today";
    $("day-date").firstChild.nodeValue = d.getDate() + " " + MONTHS[d.getMonth()];
    // Who's cooking now lives in the top bar, and follows the day on show.
    $("cook").firstChild.nodeValue = (entry && entry.cook) ? entry.cook : "not decided";

    /* And how many for. The server sends the day's total; the names on the
       cards can't be counted for it, because one of them may read "3 guests".

       Hidden rather than blanked when there is nobody to feed, and hidden on a
       feed from a server too old to send the number at all - the display is
       expected to survive an app that hasn't been updated yet, and "for
       undefined people" on a kitchen wall is worse than no line. */
    var heads = entry && typeof entry.headCount === "number" ? entry.headCount : 0;
    var forLine = $("cook-for");
    forLine.hidden = !heads || !showHeads();
    if (heads) {
      forLine.firstChild.nodeValue =
        "for " + heads + (heads === 1 ? " person" : " people");
    }
  }

  function renderToday(entry) {
    // #today is now the two-thirds meal-card row itself; the cook has moved to
    // the top bar and "not eating" has been dropped, so there is no footer.
    var box = $("today");
    clear(box);

    if (!entry || entry.meals.length === 0) {
      /* An empty evening can either say so or say nothing. Saying nothing suits
         a display that is mostly a clock; saying so suits a house where a blank
         Tuesday is a question someone needs to answer. */
      if (showEmpty()) {
        box.appendChild(el("div", "nothing",
          entry && !entry.isToday
            ? "Nothing planned for " + entry.name
            : (showingTomorrow ? "Nothing planned for tomorrow"
                               : "Nothing planned for today")));
      }
      return;
    }

    var cards = [];
    for (var i = 0; i < entry.meals.length; i++) {
      var card = buildMealCard(entry.meals[i]);
      box.appendChild(card);
      cards.push(card);
    }
    // Paging can only be worked out once the cards are laid out and their rows
    // have real heights, so it runs here, after they're on the page.
    for (var k = 0; k < cards.length; k++) {
      if (cards[k]._initPager) { cards[k]._initPager(); }
    }
  }

  /* A single meal card. Its picture turns over on a tap to show the ingredient
     quantities scaled to the number eating; a tap on that list turns it back.
     The scaled figures come ready-made from the server (see /api/kitchen). */
  function buildMealCard(m) {
    var card = el("div", "meal");
    var ings = m.ingredients || [];
    /* Not the number of names: one of them may be "3 guests". headCount is what
       the server scaled the ingredients by, so it is what the heading over them
       has to say. Older feeds don't carry it. */
    var count = (typeof m.headCount === "number") ? m.headCount : (m.eaters || []).length;

    // ----- front face: the card as it always looked -----
    var front = el("div", "meal-face meal-front");

    var photo = null;
    if (m.image && showPhotos()) {
      photo = el("img", "meal-photo");
      photo.setAttribute("src", m.image);
      photo.alt = "";
      // A dead link just disappears; the text below stands on its own. Wrapped
      // so the handler refers to its own image, not the last one in the loop.
      (function (img) {
        img.onerror = function () {
          if (img.parentNode) { img.parentNode.removeChild(img); }
        };
      })(photo);
      front.appendChild(photo);
    }

    if (m.meal) {
      front.appendChild(el("div", "meal-name", m.meal));
    } else {
      front.appendChild(el("div", "meal-name tbc", "Not decided"));
    }

    front.appendChild(el("div", "eaters", nameList(m.eaters) || "nobody yet"));

    if (m.note) {
      var foot = el("div", "meal-foot");
      foot.appendChild(el("span", "note", m.note));
      front.appendChild(foot);
    }

    // Nothing to turn over to - keep the plain card exactly as before.
    if (ings.length === 0 || count === 0) {
      while (front.firstChild) { card.appendChild(front.firstChild); }
      return card;
    }

    // ----- back face: the scaled ingredient list -----
    var back = el("div", "meal-face meal-back");
    var who = count + " " + (count === 1 ? "person" : "people");
    back.appendChild(el("div", "king-title",
      (m.meal || "Meal") + " ingredients for " + who));
    var list = el("div", "king-list");
    var rows = [];
    for (var j = 0; j < ings.length; j++) {
      var L = ings[j];
      var row = el("div", "king-item" + (L.staple ? " staple" : ""));
      row.appendChild(el("span", "king-qty", L.qty));
      row.appendChild(el("span", "king-name",
        L.item + (L.note ? " (" + L.note + ")" : "")));
      list.appendChild(row);
      rows.push(row);
    }
    back.appendChild(list);
    var hint = el("div", "king-hint", "Tap to flip back");
    back.appendChild(hint);

    // ----- assemble the flip -----
    var flip = el("div", "flip");
    var inner = el("div", "flip-inner");
    inner.appendChild(front);
    inner.appendChild(back);
    flip.appendChild(inner);
    card.appendChild(flip);

    // The picture is the tap target (or the whole front, if there's no picture).
    var trigger = photo || front;
    trigger.style.cursor = "pointer";
    front.appendChild(el("div", "king-front-hint", "Ingredients ↻"));

    // A Nest Hub can't be relied on to scroll an overflowing card, so a long
    // list is split into pages: a tap on the back moves to the next page, and a
    // tap on the last page turns the card back to the photo. Short lists stay a
    // single page and a tap just flips back. The split is worked out from the
    // rows' real heights once the card is laid out (see card._initPager).
    var pages = [[0, rows.length]];
    var current = 0;

    function showPage(p) {
      current = p;
      var range = pages[p];
      for (var r = 0; r < rows.length; r++) {
        rows[r].style.display = (r >= range[0] && r < range[1]) ? "" : "none";
      }
      if (pages.length <= 1) {
        hint.firstChild.nodeValue = "Tap to flip back";
      } else if (p < pages.length - 1) {
        hint.firstChild.nodeValue = "More ↓   " + (p + 1) + " / " + pages.length;
      } else {
        hint.firstChild.nodeValue = "Tap for the photo ↺   " + pages.length + " / " + pages.length;
      }
    }

    trigger.onclick = function () { showPage(0); flip.className = "flip flipped"; };
    back.onclick = function () {
      if (pages.length > 1 && current < pages.length - 1) {
        showPage(current + 1);          // more to see - turn the page
      } else {
        flip.className = "flip";        // done (or nothing to page) - back to photo
      }
    };

    card._initPager = function () {
      var avail = list.clientHeight;
      if (!avail || !rows.length) { return; }
      pages = [];
      var start = 0, used = 0;
      for (var r = 0; r < rows.length; r++) {
        var h = rows[r].offsetHeight;
        if (r > start && used + h > avail) {
          pages.push([start, r]);       // this row spills - it starts a new page
          start = r;
          used = 0;
        }
        used += h;
      }
      pages.push([start, rows.length]);
      showPage(0);
    };

    return card;
  }

  function selectDay(date) {
    if (!lastGood) { return; }
    var today = null;
    for (var i = 0; i < lastGood.days.length; i++) {
      if (lastGood.days[i].isToday) { today = lastGood.days[i].date; }
    }
    // Tapping today's column (or the day already showing) goes back to today.
    selectedDate = (date === today || date === selectedDate) ? null : date;
    if (backTimer) { clearTimeout(backTimer); backTimer = null; }
    if (selectedDate) {
      backTimer = setTimeout(function () {
        selectedDate = null;
        if (lastGood) { render(lastGood); }
      }, AUTO_BACK_MS);
    }
    render(lastGood);
  }

  function renderWeek(data, entry) {
    var strip = $("week");
    clear(strip);

    for (var i = 0; i < data.days.length; i++) {
      var day = data.days[i];
      var cls = "wday" + (day.isToday ? " is-today" : "");
      if (entry && day.date === entry.date && !day.isToday) {
        cls += " is-selected";
      }
      var col = el("div", cls);
      col.setAttribute("role", "button");
      col.setAttribute("data-date", day.date);
      (function (date) {
        col.onclick = function () { selectDay(date); };
      })(day.date);
      col.appendChild(el("div", "wday-name", day.name.slice(0, 3)));

      if (day.meals.length === 0) {
        col.appendChild(el("div", "wday-empty", "-"));
      } else {
        for (var j = 0; j < day.meals.length && j < 3; j++) {
          var name = day.meals[j].meal || "TBC";
          col.appendChild(el("div", "wday-meal" + (j > 0 ? " second" : ""), name));
        }
      }
      strip.appendChild(col);
    }
  }

  function render(data) {
    /* `date` is the calendar's answer and `today` the display's; they differ
       only past the rollover time. An older add-on sends no `date` at all,
       which reads correctly as "not shifted". */
    showingTomorrow = !!(data.date && data.today && data.date !== data.today);

    var todayEntry = null, picked = null;
    for (var i = 0; i < data.days.length; i++) {
      if (data.days[i].isToday) { todayEntry = data.days[i]; }
      if (selectedDate && data.days[i].date === selectedDate) {
        picked = data.days[i];
      }
    }
    // A selection that no longer exists (week rolled over) falls back to today.
    if (selectedDate && !picked) { selectedDate = null; }
    var entry = picked || todayEntry;
    renderHeader(data, entry);
    renderToday(entry);
    renderWeek(data, entry);
    renderBell(data.bell);
    renderShop(data);
    shownDate = data.today;
  }

  // ------------------------------------------------------------ the bell

  /* One button, and the app does the rest. Which speakers it rings, what it
     plays and whether it is allowed at all are all settled on a phone; this
     screen is only ever told yes or no.

     `bell` is absent from a server too old to send it, which reads correctly
     as no button - a display kept alive by an add-on that hasn't been updated
     shouldn't grow a control that 404s. */
  function renderBell(bell) {
    var btn = $("bell-btn");
    var on = !!(bell && bell.ready && bell.showButton);
    btn.hidden = !on;
    if (!on) { btn.classList.remove("is-ringing", "is-sorry"); }
  }

  var BELL_SETTLE_MS = 4000;
  var bellTimer = null;

  function ringBell() {
    var btn = $("bell-btn");
    if (btn.disabled) { return; }
    btn.disabled = true;
    btn.classList.remove("is-sorry");
    btn.classList.add("is-ringing");
    btn.firstChild.nodeValue = "Ringing…";

    /* Nothing on this screen can be read from across a kitchen anyway, so the
       outcome is the button itself: rung, or sorry. The reason lives on the
       phone, in Settings, where somebody can stand and read it. */
    function settle(label, sorry) {
      btn.classList.remove("is-ringing");
      btn.classList.toggle("is-sorry", !!sorry);
      btn.firstChild.nodeValue = label;
      if (bellTimer) { clearTimeout(bellTimer); }
      bellTimer = setTimeout(function () {
        btn.disabled = false;
        btn.classList.remove("is-ringing", "is-sorry");
        btn.firstChild.nodeValue = "Dinner time!";
      }, BELL_SETTLE_MS);
    }

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/bell/ring", true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.timeout = 15000;
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      /* A ring that reached the app but not the speakers comes back 200 with
         ok:false - the phone's card wants the detail either way, so the status
         line stays about whether the request worked. Here, only the speakers
         matter, so it is the body that decides. */
      var body = {};
      try { body = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      var reached = xhr.status >= 200 && xhr.status < 300;
      settle(reached && body.ok ? "Ringing…" : "Wouldn't ring",
             !(reached && body.ok));
    };
    xhr.ontimeout = xhr.onerror = function () {
      settle("Wouldn't ring", true);
    };
    xhr.send("{}");
  }

  // ----------------------------------------------------------- the shopping

  /* The standing list, on the screen it is actually asked about.

     Everything here works from what /api/kitchen already sends once a minute,
     and writes back through the same endpoints the phone uses. Two rules shape
     the whole thing:

     - **No keyboard.** A Nest Hub running DashCast is a cast receiver, not a
       browser: there is no soft keyboard to raise, and a focused text box on
       one is a box you can look at. So nothing is ever typed. Adding is done
       from the names the app has already remembered - see knownExtras in
       server.py, which has been filling up from every add made on a phone
       since long before this screen existed. Anything genuinely new is still
       a job for the phone, and always will be.
     - **Nothing here can destroy anything.** The stepper is the only way a
       line leaves this screen, and only by being counted down to none, which
       is somebody saying they don't need it after all. There is no tick-off:
       a mis-tap on a wall display is not rare, and a shopping list that
       quietly loses a line is worse than one with a line too many on it. */

  var extras = [];               // the list as last seen
  var suggestions = [];          // remembered names, most useful first
  var shopOn = false;            // whether the server offers this at all
  var shopPage = 0;
  var pickPage = 0;
  var shopRowsPerPage = 0;
  var pickPerPage = 0;
  var idleTimer = null;

  /* Long enough to read the list and add two or three things without being
     hurried, short enough that a display nobody walked away from properly is
     back on the meals before anyone next looks at it. Every touch starts it
     again, so it only ever fires on a screen that has been left. */
  var SHOP_IDLE_MS = 90000;

  function shopIsOpen() { return !$("shop").hidden; }

  /* Any touch anywhere in the panel puts the idle clock back to the start.
     Called from every handler rather than from one listener on the overlay,
     because a Hub's touch layer does not reliably bubble. */
  function stayAwake() {
    if (idleTimer) { clearTimeout(idleTimer); }
    idleTimer = setTimeout(closeShop, SHOP_IDLE_MS);
  }

  function needed() {
    var out = [];
    for (var i = 0; i < extras.length; i++) {
      if (extras[i].state !== "ordered") { out.push(extras[i]); }
    }
    return out;
  }

  /* Still needed first, then what is on order - the same order the server
     sends and the phone shows. Applied locally after an add, so a new line
     lands where it would have if the list had been fetched again. */
  function sortExtras(list) {
    var need = [], ordered = [];
    for (var i = 0; i < list.length; i++) {
      (list[i].state === "ordered" ? ordered : need).push(list[i]);
    }
    return need.concat(ordered);
  }

  /* "450g", "2 tins", "3". Matches extraQty() in app.js, except that a single
     countable thing shows its "1" rather than nothing: on the phone the number
     sits between the two stepper buttons and can be inferred, and here it is a
     column of its own that would otherwise be blank on half the rows. */
  function qtyLabel(extra) {
    var qty = extra.qty || 1;
    var unit = extra.unit || "each";
    if (unit === "g" || unit === "ml" || unit === "kg" || unit === "l") {
      return qty + unit;
    }
    if (unit === "each") { return String(qty); }
    var many = ["tin", "pack", "clove", "handful", "pinch", "sprig", "bunch",
                "slice"];
    var plural = (qty !== 1 && many.indexOf(unit) >= 0) ? unit + "s" : unit;
    return qty + " " + plural;
  }

  /* Whole ones for countable things, sensible jumps for weights - the same
     steps as the phone, so 100g goes to 150g on both. */
  function stepFor(extra) {
    var unit = extra.unit || "each";
    if (unit === "g" || unit === "ml") { return (extra.qty || 1) >= 200 ? 50 : 10; }
    if (unit === "tsp" || unit === "tbsp") { return 0.5; }
    return 1;
  }

  // ---- the column on the week strip

  function renderShopButton() {
    var btn = $("shop-btn");
    var count = needed().length;
    btn.hidden = !shopOn;
    var badge = $("shop-count");
    badge.hidden = !count;
    if (count) { badge.firstChild.nodeValue = String(count); }
  }

  // ---- the list

  function buildShopRow(extra) {
    var ordered = extra.state === "ordered";
    var row = el("div", "shop-row" + (ordered ? " is-ordered" : ""));

    var down = el("button", "shop-step", "−");
    down.type = "button";
    var up = el("button", "shop-step", "+");
    up.type = "button";

    row.appendChild(down);
    row.appendChild(el("span", "shop-name", extra.item));
    row.appendChild(el("span", "shop-qty", qtyLabel(extra)));
    row.appendChild(up);

    if (!ordered) {
      down.onclick = function () { stepExtra(extra, -1, [down, up]); };
      up.onclick = function () { stepExtra(extra, 1, [down, up]); };
    }
    return row;
  }

  /* How many rows fit. Measured from real rows rather than worked out from the
     stylesheet, because every size on this screen is in vh and the text scale
     multiplies all of it - so the answer is different on a Hub, a Hub Max and
     a tablet, and different again at 130%.

     Two probes rather than one, and the distance between them rather than the
     height of either: what has to divide into the box is the pitch from one
     row to the next, which is the height plus whatever the layout puts between
     them. Measuring one row and dividing gets an extra row onto the page and
     then clips it. */
  function measureShopRows() {
    var box = $("shop-rows");
    clear(box);
    var sample = { item: "Measuring", qty: 1, unit: "each", state: "need" };
    var first = buildShopRow(sample);
    var second = buildShopRow(sample);
    box.appendChild(first);
    box.appendChild(second);
    var pitch = second.offsetTop - first.offsetTop;
    if (pitch <= 0) { pitch = first.offsetHeight; }
    var room = box.clientHeight;
    clear(box);
    shopRowsPerPage = (pitch > 0 && room > 0)
      ? Math.max(1, Math.floor(room / pitch)) : 6;
  }

  function renderShopList() {
    var box = $("shop-rows");
    clear(box);

    if (!extras.length) {
      $("shop-page").hidden = true;
      $("shop-more").hidden = true;
      box.appendChild(el("div", "shop-empty", "Nothing on the list"));
      return;
    }

    if (!shopRowsPerPage) { measureShopRows(); }
    var pages = Math.max(1, Math.ceil(extras.length / shopRowsPerPage));
    // A page that no longer exists - the last thing on it was stepped away.
    if (shopPage >= pages) { shopPage = pages - 1; }

    var start = shopPage * shopRowsPerPage;
    var slice = extras.slice(start, start + shopRowsPerPage);
    for (var i = 0; i < slice.length; i++) {
      box.appendChild(buildShopRow(slice[i]));
    }

    var pager = $("shop-page");
    pager.hidden = pages <= 1;
    if (pages > 1) {
      clear(pager);
      pager.appendChild(document.createTextNode((shopPage + 1) + " / " + pages));
    }
    $("shop-more").hidden = pages <= 1;
  }

  function stepExtra(extra, direction, buttons) {
    var i;
    for (i = 0; i < buttons.length; i++) { buttons[i].disabled = true; }
    stayAwake();

    var next = Math.round(((extra.qty || 1) + stepFor(extra) * direction) * 100) / 100;
    postJson("/api/extras/qty", { id: extra.id, qty: next }, function (res) {
      /* The whole list comes back, which is the point: two people in the same
         kitchen with the same list open should both end up looking at what the
         file actually says, not at their own arithmetic. */
      if (res && res.extras) { extras = res.extras; }
      renderShopList();
      renderShopButton();
    }, function () {
      // It didn't take. Put the buttons back and leave the number alone -
      // there is nowhere on this screen to explain, and a row that refuses to
      // move says enough for somebody to go and look at their phone.
      for (var j = 0; j < buttons.length; j++) { buttons[j].disabled = false; }
    });
  }

  // ---- the grid of names

  /* Measured the same way as the rows, and for the same reason. The column
     count comes out of the measuring too rather than being assumed: it is
     three in the stylesheet and two on a stacked screen, and a third answer
     hardcoded here would be a third thing to keep in step.

     Enough probes to guarantee a second row whichever it is, then the pitch
     between the first tile and the first one below it. */
  function measurePickTiles() {
    var box = $("pick-grid");
    clear(box);
    var probes = [], i;
    for (i = 0; i < 6; i++) {
      var probe = el("button", "pick-tile", "Measuring");
      probe.type = "button";
      box.appendChild(probe);
      probes.push(probe);
    }
    // The first tile whose top is lower than the first tile's starts row two,
    // and its index is how many are across.
    var across = 0;
    for (i = 1; i < probes.length; i++) {
      if (probes[i].offsetTop > probes[0].offsetTop) { across = i; break; }
    }
    var pitch = across ? (probes[across].offsetTop - probes[0].offsetTop) : 0;
    if (!across) { across = 3; }
    if (pitch <= 0) { pitch = probes[0].offsetHeight; }
    var room = box.clientHeight;
    clear(box);
    var down = (pitch > 0 && room > 0) ? Math.max(1, Math.floor(room / pitch)) : 2;
    pickPerPage = across * down;
  }

  function renderPickGrid() {
    var box = $("pick-grid");
    clear(box);

    if (!suggestions.length) {
      $("pick-page").hidden = true;
      $("pick-more").hidden = true;
      /* Nothing has ever been added on a phone, so there is nothing to offer.
         Said plainly rather than shown as an empty grid, because the fix is
         somewhere else entirely and nobody would guess it from a blank
         screen. */
      box.appendChild(el("div", "pick-none",
        "Nothing remembered yet. Add a few things on a phone first and they "
        + "will show up here."));
      return;
    }

    if (!pickPerPage) { measurePickTiles(); }
    var pages = Math.max(1, Math.ceil(suggestions.length / pickPerPage));
    if (pickPage >= pages) { pickPage = 0; }

    var start = pickPage * pickPerPage;
    var slice = suggestions.slice(start, start + pickPerPage);
    for (var i = 0; i < slice.length; i++) {
      (function (name) {
        var tile = el("button", "pick-tile", name);
        tile.type = "button";
        tile.onclick = function () { addExtra(name, tile); };
        box.appendChild(tile);
      })(slice[i]);
    }

    var pager = $("pick-page");
    pager.hidden = pages <= 1;
    if (pages > 1) {
      clear(pager);
      pager.appendChild(document.createTextNode((pickPage + 1) + " / " + pages));
    }
    $("pick-more").hidden = pages <= 1;
  }

  function addExtra(name, tile) {
    if (tile.disabled) { return; }
    tile.disabled = true;
    tile.className = "pick-tile is-adding";
    stayAwake();

    /* This one endpoint answers with the line rather than the whole list -
       it is what the phone wants, and changing it would be changing the phone.
       The line is authoritative either way: a name already on the list comes
       back as that same line with one more of it, so merging on the id gets
       both cases right without a second round trip to a Nest Hub. */
    postJson("/api/extras", { item: name }, function (entry) {
      if (entry && entry.id) {
        var found = false;
        for (var i = 0; i < extras.length; i++) {
          if (extras[i].id === entry.id) { extras[i] = entry; found = true; }
        }
        if (!found) { extras.push(entry); }
        extras = sortExtras(extras);
      }
      renderShopButton();
      // Straight back to the list, so what just happened is visible. Adding
      // three things is three taps and three glances, not three taps into a
      // grid that never changes and a surprise at the end.
      showFace("list", entry && entry.id);
    }, function () {
      tile.disabled = false;
      tile.className = "pick-tile";
    });
  }

  // ---- opening, closing, and moving between the two faces

  /* `focusId` is the line that has just changed, if there is one. Without it
     the list opens at the top, which is right for arriving at it; with it the
     page holding that line is the one shown, which is right for coming back
     from having added something. A list two pages long that returns to page
     one after every add looks exactly like a list that ignored you. */
  function showFace(which, focusId) {
    var list = which === "list";
    /* Unhidden before anything is measured, and that order is the whole of it:
       a hidden box has no height, so a page size worked out against one is the
       fallback dressed up as a measurement. Both faces start hidden and one of
       them is hidden again on every swap, so this is not a first-run case - it
       is every time. */
    $("shop-list").hidden = !list;
    $("shop-pick").hidden = list;

    if (!list) {
      if (!pickPerPage) { measurePickTiles(); }
      pickPage = 0;
      renderPickGrid();
      return;
    }

    if (!shopRowsPerPage) { measureShopRows(); }
    shopPage = 0;
    if (focusId) {
      for (var i = 0; i < extras.length; i++) {
        if (extras[i].id === focusId) {
          shopPage = Math.floor(i / shopRowsPerPage);
          break;
        }
      }
    }
    renderShopList();
  }

  function openShop() {
    if (!shopOn) { return; }
    $("shop").hidden = false;
    /* Thrown away rather than kept, so both are measured again on the way in.
       The text scale can have been changed from a phone since this was last
       opened, and it is the one setting that changes how much fits. showFace()
       does the measuring, once each face is actually on the screen. */
    shopRowsPerPage = 0;
    pickPerPage = 0;
    showFace("list");
    stayAwake();
  }

  function closeShop() {
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
    $("shop").hidden = true;
    /* Polls that landed while this was open were kept but not drawn - see
       load(). Draw the newest one now, so closing the list never reveals a
       display that has been sitting on an old evening. */
    if (lastGood) { render(lastGood); }
  }

  /* The plain POST the panel needs. Deliberately not the bell's copy of this:
     that one settles a button by its own rules and has nowhere to put a body
     back. Same plainness though - XHR, no JSON body helpers, nothing an old
     Chromium has to be talked into. */
  function postJson(url, payload, onOk, onFail) {
    var xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.timeout = 15000;
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      if (xhr.status < 200 || xhr.status >= 300) { onFail(); return; }
      var parsed = null;
      try { parsed = JSON.parse(xhr.responseText); } catch (e) { onFail(); return; }
      onOk(parsed);
    };
    xhr.onerror = xhr.ontimeout = onFail;
    xhr.send(JSON.stringify(payload));
  }

  /* Called on every poll. Takes the list and the names, but never redraws a
     panel somebody is standing in front of: a list that reorders itself under
     a thumb is a list that gets the wrong thing pressed. The button behind it
     stays current regardless, because nothing is touching that. */
  function renderShop(data) {
    /* Absent from a server too old to send them, which reads correctly as no
       button at all - the same rule the bell follows. A display kept alive by
       an add-on that hasn't been updated shouldn't grow a control that 404s. */
    var offered = !!(data.display && data.display.showShopping !== false);
    shopOn = offered && !!data.extras;

    if (shopIsOpen()) {
      /* Somebody is standing in front of it. Their list is left exactly as it
         is - the whole reason load() comes here instead of render() - and the
         count behind the panel is left stale with it, because the panel covers
         it and closeShop() draws the newest feed on the way out.

         The setting being switched off on a phone is the one thing worth
         acting on mid-touch: what is on screen is then a panel that the app no
         longer offers a way back to. */
      if (!shopOn) { closeShop(); }
      return;
    }

    extras = data.extras || [];
    suggestions = data.knownExtras || [];
    renderShopButton();
  }

  // ---------------------------------------------------------------- polling

  function load() {
    /* Today first, then the six days after it. A Monday-to-Sunday strip spends
       half of itself on meals the house has already eaten, and a screen on a
       wall is only ever asked what's next. The server keeps the calendar week
       as its default for anything else reading this. */
    fetchJson("/api/kitchen?from=today&days=7", function (data) {
      failures = 0;
      $("stale").hidden = true;
      // Before render, so a change of accent or of what is on screen lands in
      // the same frame as the meals it applies to.
      applyDisplay(data.display);
      // If midnight has passed the server starts reporting a new week; asking
      // for no particular week means we always follow along.
      lastGood = data;
      /* Kept, but not drawn over somebody's hands. The shopping panel covers
         the whole screen, so redrawing the meals underneath it changes nothing
         anybody can see - but renderShop() also reorders the rows being
         pressed, and a poll landing between a finger going down and coming up
         is exactly how the wrong thing gets stepped. closeShop() draws the
         newest one on the way out. */
      if (shopIsOpen()) {
        renderShop(data);
        return;
      }
      render(data);
    }, function () {
      failures = failures + 1;
      // One blip is normal on wifi; only complain once it's clearly down.
      if (failures >= 3) {
        $("stale").hidden = false;
      }
    });
  }

  function maybeReload() {
    /* Not while somebody is using it. The six-hourly reload is a slow
       self-heal for a page that has been up for a week, and there is no
       version of it that is worth doing to a half-added shopping list. It runs
       on the next check, ten minutes later, or when the panel closes -
       whichever comes first, and both are soon enough for a self-heal. */
    if (shopIsOpen()) { return; }
    var hours = (new Date() - startedAt) / 3600000;
    if (hours >= RELOAD_HOURS) {
      window.location.reload();
    }
  }

  $("bell-btn").onclick = ringBell;
  $("shop-btn").onclick = openShop;
  $("shop-close").onclick = closeShop;
  $("shop-add").onclick = function () { stayAwake(); showFace("pick"); };
  $("pick-back").onclick = function () { stayAwake(); showFace("list"); };
  $("shop-more").onclick = function () {
    stayAwake();
    shopPage = shopPage + 1;      // renderShopList wraps a page past the end
    var pages = Math.max(1, Math.ceil(extras.length / (shopRowsPerPage || 1)));
    if (shopPage >= pages) { shopPage = 0; }
    renderShopList();
  };
  $("pick-more").onclick = function () {
    stayAwake();
    pickPage = pickPage + 1;
    var pages = Math.max(1, Math.ceil(suggestions.length / (pickPerPage || 1)));
    if (pickPage >= pages) { pickPage = 0; }
    renderPickGrid();
  };

  tickClock();
  load();
  setInterval(load, REFRESH_MS);
  setInterval(tickClock, CLOCK_MS);
  setInterval(maybeReload, 600000);
})();
