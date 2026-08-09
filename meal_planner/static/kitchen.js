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
    var hours = (new Date() - startedAt) / 3600000;
    if (hours >= RELOAD_HOURS) {
      window.location.reload();
    }
  }

  $("bell-btn").onclick = ringBell;

  tickClock();
  load();
  setInterval(load, REFRESH_MS);
  setInterval(tickClock, CLOCK_MS);
  setInterval(maybeReload, 600000);
})();
