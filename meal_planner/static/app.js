/* Home Meal Planner - front end. No build step, no dependencies. */
(function () {
  "use strict";

  var DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  var DAY_NAMES = {
    mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday",
    fri: "Friday", sat: "Saturday", sun: "Sunday"
  };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* The tabs, left to right. This is the order on screen, so it is also the
     order a swipe moves through - keep it in step with the buttons in
     index.html. */
  var VIEWS = ["week", "plan", "shopping", "meals", "settings"];

  /* The Household tab became Settings, and its hash went with it. Anything
     bookmarked, shared or sitting in a phone's history still says #people, and
     landing those on the week view would look like the page had gone. */
  var OLD_VIEWS = { people: "settings" };

  var state = {
    people: [], meals: [], weeks: {},
    palette: [],          // colours a person can wear; the server decides
    today: null, thisWeek: null,
    viewWeek: null,   // Monday key shown on the week view
    planWeek: null,   // Monday key shown on the planner
    view: "week",
    editingMealId: null,
    mealFilter: "",
    mealSort: "az",       // how the library is ordered; see MEAL_SORTS
    ratedBy: [],          // whose ratings the order uses; empty = everyone
    sortOpen: false,      // the order panel under the search box
    shopWeek: null,
    planFocus: null,      // day just added to from the library; see applyPlanFocus
    shopList: null,       // last list fetched, kept so it can be shared
    shopRendered: null,   // which week that list is on screen for
    grabbed: null,        // person whose drag handle should keep the focus
    pendingImage: null,   // picture chosen from this device, awaiting save
    imageShown: "",       // what the image field held when editing began
    offline: false,       // server unreachable; the page is read-only
    cachedAt: null,       // when the copy being shown was last downloaded
    booted: false,        // first load finished, so setView may refresh again
    cast: null,           // kitchen display status, fetched with the Settings tab
    backup: null,         // what there is to back up, fetched with the Settings tab
    backupBusy: false,    // a backup or restore is in flight; leave its buttons be
    display: null,        // how the kitchen display looks; shared by the house
    bell: null,           // the dinner bell: switch, speakers and chime
    bellBusy: false,      // ringing or uploading; leave its buttons be
    bellNote: null,       // what the bell card is saying, so a redraw keeps it
    focusUntil: 0,        // keep today's card on screen until this moment
    hiddenAt: 0           // when the page was last put away; see backFromAway
  };

  // ---------------------------------------------------------------- utils

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  /* Dates are handled as plain yyyy-mm-dd strings in UTC so that time zones
     and daylight saving can never shift a day by one. */
  function toDate(key) {
    var p = key.split("-");
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
  }

  function toKey(d) {
    return d.getUTCFullYear() + "-" +
      String(d.getUTCMonth() + 1).padStart(2, "0") + "-" +
      String(d.getUTCDate()).padStart(2, "0");
  }

  function addDays(key, n) {
    var d = toDate(key);
    d.setUTCDate(d.getUTCDate() + n);
    return toKey(d);
  }

  function prettyDate(key) {
    var d = toDate(key);
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()];
  }

  /* "Today" is read from this device's clock, never from the server. A phone
     that has been away from the house for days is showing a cached /api/data
     whose `today` was frozen when it was saved; trusting it leaves the
     highlight stuck on whatever day the plan was last downloaded. */
  function localToday() {
    var d = new Date();
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  function mondayOf(key) {
    /* getUTCDay is Sunday-first; shift so Monday is 0. */
    return addDays(key, -((toDate(key).getUTCDay() + 6) % 7));
  }

  /* Which entry in DAYS a date falls on - the reverse of addDays(weekKey, i). */
  function dayOf(key) {
    return DAYS[(toDate(key).getUTCDay() + 6) % 7];
  }

  /* Move the app on to whatever day it actually is now. Any of the three week
     pointers that was sitting on "this week" follows along; a week someone has
     deliberately navigated to is left where they put it. */
  function syncToday(quiet) {
    var today = localToday();
    if (today === state.today) return false;
    var wasWeek = state.thisWeek;
    state.today = today;
    state.thisWeek = mondayOf(today);
    if (state.thisWeek !== wasWeek) {
      ["viewWeek", "planWeek", "shopWeek"].forEach(function (k) {
        if (!state[k] || state[k] === wasWeek) state[k] = state.thisWeek;
      });
    }
    if (!quiet && state.ready) render();
    return true;
  }

  /* A timer alone can't be trusted here: phones throttle or suspend background
     tabs, and a laptop can be shut for a week. So midnight is a nudge, and
     syncToday is called again on every poll and every time the page is shown. */
  var midnightTimer = null;

  function scheduleMidnight() {
    if (midnightTimer) clearTimeout(midnightTimer);
    var now = new Date();
    var next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 5);
    var ms = Math.min(Math.max(next.getTime() - now.getTime(), 1000), 2147483647);
    midnightTimer = setTimeout(function () {
      syncToday();
      scheduleMidnight();
    }, ms);
  }

  function weekRange(key) {
    var end = addDays(key, 6);
    var a = toDate(key), b = toDate(end);
    var year = b.getUTCFullYear() === new Date().getFullYear() ? "" : " " + b.getUTCFullYear();
    if (a.getUTCMonth() === b.getUTCMonth()) {
      return a.getUTCDate() + "-" + b.getUTCDate() + " " + MONTHS[b.getUTCMonth()] + year;
    }
    return prettyDate(key) + " - " + prettyDate(end) + year;
  }

  function weekLabel(key) {
    if (key === state.thisWeek) return "This week";
    if (key === addDays(state.thisWeek, 7)) return "Next week";
    if (key === addDays(state.thisWeek, -7)) return "Last week";
    return "Week of " + prettyDate(key);
  }

  function personById(id) {
    for (var i = 0; i < state.people.length; i++) {
      if (state.people[i].id === id) return state.people[i];
    }
    return null;
  }

  function mealById(id) {
    for (var i = 0; i < state.meals.length; i++) {
      if (state.meals[i].id === id) return state.meals[i];
    }
    return null;
  }

  // ---------------------------------------------------------------- colours
  //
  /* Everywhere a person's colour is worn - name chips, the eating toggles, the
     rating pills, the star picker - it is worn behind their name, so the colour
     decides what the lettering has to be. This used to be white everywhere,
     which quietly ruled out half a colour wheel: white on yellow is unreadable,
     so yellow could not be offered, and the palette was ten muted mid-tones
     that were hard to tell apart on a small chip.
     Working the lettering out per colour is what lets the palette be bright. */

  var DEFAULT_COLOR = "#0055ff";
  var DARK_INK = "#1b1a17";

  function srgbPart(c) {
    c = c / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  /* Relative luminance, per WCAG. Not the same as "how light does it look" -
     green counts for far more than blue, which is why pure blue takes white
     lettering and pure yellow takes black. */
  function luminance(hex) {
    var n = parseInt(String(hex).slice(1), 16);
    if (isNaN(n)) return 0;
    return 0.2126 * srgbPart((n >> 16) & 255) +
           0.7152 * srgbPart((n >> 8) & 255) +
           0.0722 * srgbPart(n & 255);
  }

  function contrastRatio(a, b) {
    var la = luminance(a), lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  /* White unless white would be hard work, then near-black.
     3.6:1 rather than the 4.5 a body of text wants: these are short, mostly a
     single name, on a filled pill at a size the eye is not scanning. Going to
     4.5 pushes reds and magentas onto black lettering, which reads as a
     highlighter pen. Nothing in the palette is below 3.6 on the ink it gets. */
  function inkOn(color) {
    return contrastRatio(color, "#ffffff") >= 3.6 ? "#fff" : DARK_INK;
  }

  /* Put a person's colour on something, with lettering that can be read on it.
     Always use this rather than setting background on its own. */
  function paint(node, color) {
    var c = color || DEFAULT_COLOR;
    node.style.background = c;
    node.style.color = inkOn(c);
    return node;
  }

  /* The star picker has two things on it that the lettering colour doesn't
     cover, because neither is lettering: the fill of an earned star, and the
     wash under a pressed one.

     The gold is worth keeping where it can be seen - it is what says "star"
     before the shape has been read - but it is a fixed colour against a
     background that is now anything from pure yellow to deep indigo, and it
     clears 3:1 on only twenty-two of the thirty-six. On the rest the star
     falls back to the picker's own lettering colour, where the outline/solid
     distinction carries it instead. */
  var STAR_GOLD = "#ffd452";

  function starTones(node, color) {
    var c = color || DEFAULT_COLOR;
    var ink = inkOn(c);
    node.style.setProperty("--star-on",
      contrastRatio(STAR_GOLD, c) >= 3 ? STAR_GOLD : ink);
    // A wash away from the lettering, so it shows on either kind of picker.
    node.style.setProperty("--star-wash",
      ink === "#fff" ? "rgba(255,255,255,.22)" : "rgba(0,0,0,.16)");
    return node;
  }

  /* A day holds a list of "sittings" - separate meals eaten that day by
     different groups. Most days have one; some have two. */
  function weekData(key) {
    var week = state.weeks[key];
    var out = {};
    DAYS.forEach(function (d) {
      var cell = (week && week[d]) || {};
      out[d] = { cookId: cell.cookId || null, sittings: (cell.sittings || []).slice() };
    });
    return out;
  }

  function dayCook(key, day) {
    var week = state.weeks[key];
    if (!week || !week[day]) return null;
    return week[day].cookId || null;
  }

  function sittingsFor(key, day) {
    var week = state.weeks[key];
    if (!week || !week[day]) return [];
    return week[day].sittings || [];
  }

  /* Anyone in the house not down for any meal that day. The guest slot is never
     in this: it isn't anybody until a meal says how many of them there are. */
  function notEating(sittings) {
    var fed = {};
    sittings.forEach(function (s) {
      (s.eaters || []).forEach(function (id) { fed[id] = true; });
    });
    return household().filter(function (p) { return !fed[p.id]; });
  }

  // -------------------------------------------------------------- guests

  /* "Guest(s)" is a person in the household list with a number attached, rather
     than a number hidden on the meal: it toggles on and off with everybody
     else, takes a colour and a chip like everybody else, and the one thing it
     does differently is stand for more than one mouth.

     The count belongs to the sitting - six for dinner on Saturday says nothing
     about Tuesday - and the server is what decides it, so these read rather
     than calculate. */
  function guestPerson() {
    for (var i = 0; i < state.people.length; i++) {
      if (state.people[i].guest) return state.people[i];
    }
    return null;
  }

  function household() {
    return state.people.filter(function (p) { return !p.guest; });
  }

  /* People in the order the household is kept in, whatever order they arrived
     in. Everything that draws a list of names goes through here or through
     state.people directly, so the same faces come in the same order on every
     card - which is what makes a row of chips something you recognise rather
     than something you read.

     The one that didn't was the week card: a sitting's `eaters` is the order
     people were tapped, so Tuesday could say "Sam, Alex" and Wednesday "Alex,
     Sam" for the same two people at the same table. */
  function inHouseholdOrder(people) {
    var rank = {};
    state.people.forEach(function (p, i) { rank[p.id] = i; });
    return people.slice().sort(function (a, b) {
      return (rank[a.id] === undefined ? 1e6 : rank[a.id]) -
             (rank[b.id] === undefined ? 1e6 : rank[b.id]);
    });
  }

  function guestsOn(sitting) {
    var guest = guestPerson();
    if (!guest || (sitting.eaters || []).indexOf(guest.id) === -1) return 0;
    return Math.max(1, sitting.guests || 0);
  }

  /* How many the meal has to feed: everyone marked, with the guest slot
     counting for as many as it says. Mirrors head_count() in server.py - the
     quantities on screen have to match the ones the shopping list was built
     from, or the two disagree in front of someone holding a trolley. */
  function headCount(sitting) {
    var guest = guestPerson();
    var named = (sitting.eaters || []).filter(function (id) {
      return (!guest || id !== guest.id) && personById(id);
    });
    return named.length + guestsOn(sitting);
  }

  function guestLabel(n) { return n + (n === 1 ? " guest" : " guests"); }

  /* How many the whole day feeds, for the line beside the cook. Mirrors
     day_head_count() in server.py, and for the same reason headCount() mirrors
     head_count(): the kitchen display gets this number from the server and this
     page works it out for itself, so the two have to agree or the wall and the
     phone say different things about the same dinner.

     Distinct people, not the sum of the meals - somebody marked for both of a
     day's two sittings is still one person to feed. The guest slot counts once,
     at the largest number any single meal puts on it. */
  function dayHeadCount(sittings) {
    var guest = guestPerson();
    var named = {}, guests = 0, n = 0;
    (sittings || []).forEach(function (sitting) {
      (sitting.eaters || []).forEach(function (id) {
        if (guest && id === guest.id) return;
        if (personById(id)) named[id] = true;
      });
      guests = Math.max(guests, guestsOn(sitting));
    });
    for (var id in named) { if (named.hasOwnProperty(id)) n++; }
    return n + guests;
  }

  function peopleLabel(n) { return n + (n === 1 ? " person" : " people"); }

  function reloadWeek(key) {
    return api("GET", "/api/week/" + key).then(function (res) {
      state.weeks[key] = res.days;
    });
  }

  // ---------------------------------------------------------------- macros

  function round(n) { return Math.round(n * 10) / 10; }

  /* A compact "540 kcal · P 38g · C 45g · F 21g" strip. */
  function macroStrip(macros, scale) {
    var factor = scale || 1;
    var wrap = el("div", "macro-strip");
    var kcal = el("span", "kcal", Math.round(macros.calories * factor) + " kcal");
    wrap.appendChild(kcal);
    [["P", "protein"], ["C", "carbs"], ["F", "fat"]].forEach(function (pair) {
      var span = el("span");
      span.appendChild(el("span", null, pair[0] + " "));
      span.appendChild(el("b", null, round(macros[pair[1]] * factor) + "g"));
      wrap.appendChild(span);
    });
    /* Confidence is deliberately not shown here - it cluttered the cards.
       It still lives in the meal's note, visible when editing. */
    return wrap;
  }

  /* Four numbers, and nothing about where they came from. There was a caption
     under these boxes saying whether a figure had been estimated or typed; with
     only one way in it had nothing left to tell anyone, and the meals that
     predate that are no different now from any other. */
  function macrosFromForm() {
    var raw = {
      calories: $("m-calories").value,
      protein: $("m-protein").value,
      carbs: $("m-carbs").value,
      fat: $("m-fat").value
    };
    if (raw.calories === "" || raw.calories === null) return null;
    return {
      calories: Number(raw.calories),
      protein: Number(raw.protein || 0),
      carbs: Number(raw.carbs || 0),
      fat: Number(raw.fat || 0)
    };
  }

  function macrosIntoForm(macros) {
    $("m-calories").value = macros && macros.calories != null ? macros.calories : "";
    $("m-protein").value = macros && macros.protein != null ? macros.protein : "";
    $("m-carbs").value = macros && macros.carbs != null ? macros.carbs : "";
    $("m-fat").value = macros && macros.fat != null ? macros.fat : "";
  }

  // ---------------------------------------------------------------- images

  function imagePreview(src) {
    var pv = $("image-preview");
    if (!pv) return;
    if (src) {
      pv.setAttribute("src", src);
      pv.hidden = false;
    } else {
      pv.removeAttribute("src");
      pv.hidden = true;
    }
  }

  function imageIntoForm(meal) {
    var url = (meal && meal.image) || "";
    // A photo stored by the app isn't a typed URL; leave the field blank and
    // just show the preview. Leaving it blank keeps the photo on save.
    var typed = url.indexOf("/images/") === 0 ? "" : url;
    $("meal-image").value = typed;
    state.imageShown = typed;
    state.pendingImage = null;
    imagePreview(url);
  }

  // --------------------------------------------------------------- theming

  /* Stored per device in localStorage, so each phone, tablet and laptop keeps
     its own look. There are no accounts, so there is nothing to sync. */

  var THEME_MODES = [
    { id: "auto", label: "Auto" },
    { id: "light", label: "Light" },
    { id: "dark", label: "Dark" }
  ];
  /* The shades themselves live in style.css, under html[data-accent="..."]
     and .swatch[data-swatch="..."]. Adding one here without adding it there
     gets you a colourless swatch that does nothing. */
  var ACCENTS = [
    { id: "green", label: "Green" },
    { id: "olive", label: "Olive" },
    { id: "teal", label: "Teal" },
    { id: "blue", label: "Blue" },
    { id: "indigo", label: "Indigo" },
    { id: "plum", label: "Plum" },
    { id: "rose", label: "Rose" },
    { id: "rust", label: "Rust" },
    { id: "amber", label: "Amber" },
    { id: "cocoa", label: "Cocoa" },
    { id: "slate", label: "Slate" },
    { id: "charcoal", label: "Charcoal" }
  ];

  function store(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* storage off */ }
  }

  function stored(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
  }

  function prefersDark() {
    return !!(window.matchMedia &&
              window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  function applyTheme() {
    var mode = stored("mp-theme", "auto");
    var accent = stored("mp-accent", "green");
    var dark = mode === "dark" || (mode === "auto" && prefersDark());
    var html = document.documentElement;
    html.setAttribute("data-theme", dark ? "dark" : "light");
    html.setAttribute("data-accent", accent);
    var icon = $("theme-icon");
    if (icon) icon.textContent = dark ? "◑" : "◐";
    paintShell();
    return { mode: mode, accent: accent, dark: dark };
  }

  /* Everything outside the page itself that carries the accent: the status bar,
     the home-screen icon and the launch splash. The head of index.html does
     this once before first paint; this repeats it whenever the choice changes.

     The colours are read back out of the stylesheet rather than kept as a
     second copy of every accent here, so a new accent needs no change in this
     file. They travel to the server as plain hex on the query string, because
     the accent lives in localStorage and the phone's OS - which is what
     actually fetches the manifest and the icons - has no sight of it.

     What each one can do:

     - theme-color tints the Android status bar and the task-switcher card, and
       takes effect immediately. iOS ignores it in standalone mode and doesn't
       need it: the status bar there is transparent
       (apple-mobile-web-app-status-bar-style is black-translucent) and the
       accent-coloured top bar already shows through.
     - The manifest sets the launch splash (background_color, following light
       and dark) and the installed icon. A phone reads it at install time, so a
       change here only reaches an already-installed app when the OS re-checks:
       Android does within a day or so, iOS not at all until it is re-added.
     - apple-touch-icon is what iOS copies when "Add to Home Screen" is tapped,
       so it has to be right *before* that happens, not after. */
  function paintShell() {
    var s = getComputedStyle(document.documentElement);
    var accent = s.getPropertyValue("--accent").trim().replace("#", "");
    var ink = s.getPropertyValue("--accent-ink").trim().replace("#", "");
    var page = s.getPropertyValue("--bg").trim().replace("#", "");
    if (accent.length !== 6) return;

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", "#" + accent);

    var tint = "c=" + accent + "&f=" + ink;
    var manifest = $("manifest-link");
    if (manifest) manifest.href = "/manifest.webmanifest?" + tint + "&b=" + page;

    var apple = $("apple-icon-link");
    if (apple) apple.href = "/icon-192.png?" + tint;

    var favicon = $("favicon-link");
    if (favicon) favicon.href = "/icon-64.png?" + tint;

    /* The mark in the top bar is the same drawing. It starts with no src - see
       index.html - so this is what puts it on screen, not just what keeps it
       in step. */
    var mark = $("brand-mark");
    if (mark) mark.src = "/icon-64.png?" + tint;
  }

  function renderThemePanel() {
    var current = applyTheme();

    var modes = $("theme-modes");
    clear(modes);
    THEME_MODES.forEach(function (m) {
      var btn = el("button", "theme-opt" + (m.id === current.mode ? " on" : ""), m.label);
      btn.type = "button";
      btn.setAttribute("aria-pressed", m.id === current.mode ? "true" : "false");
      btn.onclick = function () {
        store("mp-theme", m.id);
        renderThemePanel();
      };
      modes.appendChild(btn);
    });

    var accents = $("theme-accents");
    clear(accents);
    ACCENTS.forEach(function (a) {
      var btn = el("button", "swatch" + (a.id === current.accent ? " on" : ""));
      btn.type = "button";
      btn.title = a.label;
      btn.setAttribute("aria-label", a.label);
      btn.setAttribute("aria-pressed", a.id === current.accent ? "true" : "false");
      // Show each swatch in its own colour by borrowing the theme rules.
      btn.setAttribute("data-swatch", a.id);
      btn.onclick = function () {
        store("mp-accent", a.id);
        renderThemePanel();
      };
      accents.appendChild(btn);
    });
  }

  /* Out here rather than inside wireTheme, because navigating away has to be
     able to shut the panel too - a tap on a tab closes it on its way past, but
     a swipe never produces a click for the document listener below to catch. */
  function openThemePanel(show) {
    var btn = $("theme-btn");
    var panel = $("theme-panel");
    if (!btn || !panel) return;
    panel.hidden = !show;
    btn.setAttribute("aria-expanded", show ? "true" : "false");
  }

  function wireTheme() {
    var btn = $("theme-btn");
    var panel = $("theme-panel");
    if (!btn || !panel) return;

    var open = openThemePanel;

    btn.onclick = function (e) {
      e.stopPropagation();
      open(panel.hidden);
    };
    panel.onclick = function (e) { e.stopPropagation(); };
    document.addEventListener("click", function () { open(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") open(false);
    });

    // Follow the system setting live while on "auto".
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function () {
        if (stored("mp-theme", "auto") === "auto") renderThemePanel();
      };
      if (mq.addEventListener) mq.addEventListener("change", onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }

    renderThemePanel();
  }

  // --------------------------------------------------------- recipe links

  /* Whoever is cooking needs to get to the method quickly, so this is a
     proper tappable button rather than a small inline link. */
  function linksOf(meal) {
    if (meal.links && meal.links.length) return meal.links;
    if (meal.link) return [{ label: "Open recipe", url: meal.link }];
    return [];
  }

  function oneLink(entry) {
    var a = el("a", "recipe-btn");
    a.href = entry.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.appendChild(el("span", null, entry.label || "Open recipe"));
    var host = "";
    try {
      host = entry.url.split("/")[2].replace(/^www\./, "");
    } catch (e) { host = ""; }
    if (host) a.appendChild(el("span", "recipe-host", host));
    return a;
  }

  /* A meal can point at several pages - a recipe, or one pack per shop-bought
     component. The cook may need all of them. */
  function recipeLink(meal) {
    var list = linksOf(meal);
    if (list.length === 1) return oneLink(list[0]);
    var wrap = el("div", "recipe-links");
    list.forEach(function (entry) { wrap.appendChild(oneLink(entry)); });
    return wrap;
  }

  function hasLink(meal) { return linksOf(meal).length > 0; }

  // ---- the link editor on the meal form ----

  function addLinkRow(entry) {
    var row = el("div", "link-row");

    var label = el("input", "link-label");
    label.type = "text";
    label.maxLength = 40;
    label.placeholder = "Label, e.g. The pie";
    label.value = (entry && entry.label) || "";

    var url = el("input", "link-url");
    url.type = "url";
    url.maxLength = 500;
    url.placeholder = "https://...";
    url.value = (entry && entry.url) || "";

    var remove = el("button", "icon-btn danger", "Remove");
    remove.type = "button";
    remove.onclick = function () {
      row.parentNode.removeChild(row);
      if (!$("link-rows").children.length) addLinkRow(null);
    };

    row.appendChild(label);
    row.appendChild(url);
    row.appendChild(remove);
    $("link-rows").appendChild(row);
    return row;
  }

  // ---- the ingredients editor ----

  var UNIT_CHOICES = ["each", "g", "kg", "ml", "l", "tbsp", "tsp", "tin",
                      "pack", "clove", "handful", "pinch", "sprig", "bunch", "slice"];

  function addIngRow(ing) {
    var row = el("div", "ing-row");

    var qty = el("input", "ing-qty");
    qty.type = "number";
    qty.min = "0";
    qty.step = "any";
    qty.placeholder = "1";
    qty.value = ing && ing.qty != null ? ing.qty : "";

    var unit = el("select", "ing-unit");
    UNIT_CHOICES.forEach(function (u) { unit.appendChild(new Option(u, u)); });
    unit.value = (ing && ing.unit) || "each";

    var item = el("input", "ing-item");
    item.type = "text";
    item.maxLength = 80;
    item.placeholder = "onion";
    item.value = (ing && ing.item) || "";

    var note = el("input", "ing-note");
    note.type = "text";
    note.maxLength = 80;
    note.placeholder = "finely chopped (optional)";
    note.value = (ing && ing.note) || "";

    var staple = el("button", "toggle ing-staple", "cupboard");
    staple.type = "button";
    var on = !!(ing && ing.staple);
    staple.setAttribute("aria-pressed", on ? "true" : "false");
    staple.title = "Cupboard staples are listed separately on the shopping list";
    staple.onclick = function () {
      var now = staple.getAttribute("aria-pressed") === "true";
      staple.setAttribute("aria-pressed", now ? "false" : "true");
    };

    var remove = el("button", "icon-btn danger", "Remove");
    remove.type = "button";
    remove.onclick = function () { row.parentNode.removeChild(row); };

    [qty, unit, item, note, staple, remove].forEach(function (n) { row.appendChild(n); });
    $("ing-rows").appendChild(row);
    return row;
  }

  function ingredientsIntoForm(list, serves) {
    clear($("ing-rows"));
    $("meal-serves").value = serves || "";
    (list || []).forEach(addIngRow);
    if (!list || !list.length) addIngRow(null);
    updateIngHint();
  }

  function ingredientsFromForm() {
    var out = [];
    Array.prototype.forEach.call($("ing-rows").children, function (row) {
      var item = row.querySelector(".ing-item").value.trim();
      if (!item) return;
      out.push({
        item: item,
        qty: Number(row.querySelector(".ing-qty").value || 0),
        unit: row.querySelector(".ing-unit").value,
        note: row.querySelector(".ing-note").value.trim(),
        staple: row.querySelector(".ing-staple").getAttribute("aria-pressed") === "true"
      });
    });
    return out;
  }

  function updateIngHint() {
    var count = ingredientsFromForm().length;
    var serves = Number($("meal-serves").value || 0);
    var hint = $("ing-hint");
    if (!count) {
      hint.textContent = "Without ingredients this meal can't go on the shopping list.";
    } else if (!serves) {
      hint.textContent = "Say how many the recipe serves, or it can't be scaled.";
    } else {
      hint.textContent = count + (count === 1 ? " ingredient" : " ingredients") +
        " for " + serves + " people. Ready for the shopping list.";
    }
  }

  function linksIntoForm(links) {
    clear($("link-rows"));
    if (!links || !links.length) {
      addLinkRow(null);
      return;
    }
    links.forEach(addLinkRow);
  }

  function linksFromForm() {
    var out = [];
    Array.prototype.forEach.call($("link-rows").children, function (row) {
      var url = row.querySelector(".link-url").value.trim();
      var label = row.querySelector(".link-label").value.trim();
      if (url) out.push({ label: label || "Open recipe", url: url });
    });
    return out;
  }

  var toastTimer;
  function toast(message) {
    var box = $("toast");
    box.textContent = message;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.hidden = true; }, 2200);
  }

  // ------------------------------------------------------------------ api

  var OFFLINE_WRITE = "You're offline, so the plan can't be changed from here. " +
                      "This copy is read-only until you're back on the home network.";

  function api(method, path, body) {
    /* Refuse writes up front rather than letting them fail halfway. Nothing is
       queued: two people editing the same week from different places would
       overwrite each other with no way to tell. */
    if (method !== "GET" && state.offline) {
      return Promise.reject(new Error(OFFLINE_WRITE));
    }
    return fetch(path, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new Error(data.error || "Something went wrong");
        return data;
      });
    });
  }

  /* Like api("GET", ...), but keeps the service worker's markers - api() throws
     the response away once it has parsed the body, and with it any sign that
     what came back was a saved copy rather than the live answer. */
  function getCacheable(path) {
    return fetch(path, { headers: { "Accept": "application/json" } })
      .then(function (res) {
        var cached = res.headers.get("X-Offline-Cache") === "1";
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var err = new Error(data.error || "Something went wrong");
            err.fromCache = cached;
            throw err;
          }
          return {
            data: data,
            cached: cached,
            cachedAt: res.headers.get("X-Cached-At") || ""
          };
        });
      });
  }

  /* ---- offline state -----------------------------------------------------
     "Offline" here means "can't reach the meal planner", not "no signal" -
     navigator.onLine is true on any wifi, including one nowhere near the Pi.
     The service worker is the one that knows, and says so with a header on the
     responses it serves from its own cache. */

  function setOffline(flag, cachedAt) {
    var changed = state.offline !== flag;
    state.offline = flag;
    state.cachedAt = flag ? (cachedAt || state.cachedAt) : null;
    document.documentElement.setAttribute("data-offline", flag ? "1" : "0");

    var bar = $("offline-bar");
    if (bar) {
      bar.hidden = !flag;
      if (flag) {
        var when = state.cachedAt ? niceAge(state.cachedAt) : "";
        $("offline-text").textContent =
          "Offline — showing the plan as it was" + (when ? " " + when : "") +
          ". You can look, but not change anything.";
      }
    }
    /* Only re-render if there is something to render: setOffline runs during
       the very first fetch, before any week data has arrived. */
    if (changed && state.ready) render();
  }

  function niceAge(iso) {
    var then = new Date(iso);
    if (isNaN(then.getTime())) return "";
    var mins = Math.round((Date.now() - then.getTime()) / 60000);
    if (mins < 2) return "a moment ago";
    if (mins < 60) return mins + " minutes ago";
    var hours = Math.round(mins / 60);
    if (hours < 24) return hours === 1 ? "an hour ago" : hours + " hours ago";
    var days = Math.round(hours / 24);
    return days === 1 ? "yesterday" : days + " days ago";
  }

  /* Fetched directly rather than through api() so the offline header survives:
     api() throws the response away once it has parsed the body. */
  var refreshing = null;

  function refresh() {
    if (refreshing) return refreshing;
    refreshing = fetch("/api/data", { headers: { "Accept": "application/json" } })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) throw new Error(data.error || "Something went wrong");
          setOffline(res.headers.get("X-Offline-Cache") === "1",
                     res.headers.get("X-Cached-At"));
          return data;
        });
      })
      .then(function (data) {
        state.people = data.people || [];
        state.meals = data.meals || [];
        state.weeks = data.weeks || {};
        /* Absent from an add-on older than the colour picker, which is exactly
           when the picker should not be offered - the PUT would be refused. */
        state.palette = data.palette || [];
        /* data.today and data.thisWeek are deliberately ignored - see
           localToday(). render() below covers any day change. */
        syncToday(true);
        if (!state.viewWeek) state.viewWeek = state.thisWeek;
        if (!state.planWeek) state.planWeek = state.thisWeek;
        if (!state.shopWeek) state.shopWeek = state.thisWeek;
        state.ready = true;
        render();
      })
      .then(function () { refreshing = null; },
            function (err) { refreshing = null; setOffline(true); throw err; });
    return refreshing;
  }

  function fail(err) { toast(err.message || "Something went wrong"); }

  /* The weekbars stick to the bottom edge of the top bar. That edge moves: the
     tabs wrap on a narrow phone, and the safe-area inset differs per device and
     per orientation. So publish the measured height rather than guessing it. */
  function trackTopbarHeight() {
    var bar = document.querySelector(".topbar");
    if (!bar) return;
    var apply = function () {
      document.documentElement.style.setProperty(
        "--topbar-h", bar.getBoundingClientRect().height + "px");
    };
    apply();
    if (window.ResizeObserver) new ResizeObserver(apply).observe(bar);
    else window.addEventListener("resize", apply);
  }

  /* With the "This week" heading gone from the bar, this is what tells you
     whether you are looking at the current week.

     `stillWorks` is for the week view's button, where going flat is only about
     the cue. There it still has a job on the current week - scrolling back to
     today's card after you have wandered off down the week - and a button that
     looks like the answer to "take me back" should not be the one control on
     the page that ignores you. The planner and the shopping list have nothing
     to scroll to, so theirs are disabled outright as before. */
  function markTodayBtn(id, key, stillWorks) {
    var btn = $(id);
    if (!btn) return;
    var here = (key === state.thisWeek);
    if (stillWorks) {
      btn.disabled = false;
      btn.classList.toggle("flat", here);
    } else {
      btn.disabled = here;
    }
  }

  // ------------------------------------------------------------- routing

  /* `dir` is -1 or 1 when the view was reached by swiping, and says which way,
     so the arriving page can slide in from the side the finger came from. Taps
     and links leave it out and get no animation - a tab you aimed at should
     just be there. */
  /* A view name from a URL hash, or "" if it names nothing this app has. */
  function viewFromHash(raw) {
    var name = OLD_VIEWS[raw] || raw;
    return VIEWS.indexOf(name) === -1 ? "" : name;
  }

  function setView(name, dir) {
    state.view = name;
    VIEWS.forEach(function (v) {
      $("view-" + v).hidden = v !== name;
    });
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
      var on = tab.dataset.view === name;
      tab.classList.toggle("active", on);
      /* As a bottom bar this reads as site navigation, so say which one you
         are on rather than leaving it to the colour. */
      if (on) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });
    if (location.hash.slice(1) !== name) location.hash = name;
    openThemePanel(false);
    window.scrollTo(0, 0);
    render();

    /* Asked for on arrival, not on every render: render() runs on a timer and
       on every save, and none of those is a reason to go and ask Home Assistant
       about the television again. */
    if (name === "settings") {
      loadCast(); loadDisplay(); loadBell(); loadBackupInfo();
    }

    /* After the scroll to the top, so the sticky week bar is sitting in normal
       flow: animating a transform on an ancestor of a stuck element is what
       makes it jump. */
    if (dir) {
      var section = $("view-" + name);
      section.classList.remove("slide-next", "slide-prev");
      void section.offsetWidth;        // let the animation be applied again
      section.classList.add(dir > 0 ? "slide-next" : "slide-prev");
    }

    /* Pull the latest before showing a tab, in case someone else in the house
       has added a meal or changed the plan since this page was opened.
       Not on the very first call though: boot has just fetched, and a second
       identical round-trip is the last thing a cold page load needs. */
    if (state.ready && state.booted) refresh().catch(function () {});
  }

  /* Opening the app should show this week, at today - and on a phone the app is
     rarely closed, only put down, so the launch URL alone doesn't get you
     there. A phone that has been in a pocket since yesterday is a cold open in
     every way that matters to the person taking it out again, so a long enough
     absence is treated as one.

     Short absences are not. Nipping out to a timer and coming back to find the
     tab has changed underneath you is the sort of thing that makes an app feel
     like it has a mind of its own. */
  var RESUME_MS = 30 * 60 * 1000;

  /* Nor is anything half-typed worth losing to it: the add panel being open is
     a meal being written or edited, and a focused field is someone in the
     middle of a thought. */
  function midEdit() {
    var panel = $("add-panel");
    if (panel && panel.classList.contains("open")) return true;
    var node = document.activeElement;
    return !!node && /^(INPUT|TEXTAREA|SELECT)$/.test(node.tagName);
  }

  /* Returns whether it moved the view, which also means a refresh is already
     on its way and the caller needn't start a second one. */
  function backFromAway() {
    if (!state.hiddenAt || Date.now() - state.hiddenAt < RESUME_MS) return false;
    if (midEdit()) return false;
    state.viewWeek = state.thisWeek;
    focusOnToday();
    if (state.view !== "week") { setView("week"); return state.booted; }
    renderWeek();
    return false;
  }

  // ------------------------------------------------------------- swiping

  /* Sideways between tabs, on the phone layout where the tabs are a bottom bar
     and the row of them already reads as a row of pages.

     The gesture is deliberately fussy, because a page that changes tab when you
     meant to scroll feels broken in a way that is hard to put a finger on:

     - one finger only, so a pinch is never mistaken for a swipe
     - it has to travel a good deal further across than down, or a thumb
       scrolling in a slight arc would keep landing on the next tab
     - it must not start on a text field or on anything that scrolls sideways
       of its own accord - those wanted the drag for themselves
     - it must not start hard against the left edge, which is where iOS puts
       its own back gesture, or both would fire

     Nothing follows the finger while the drag is in progress. Switching tab
     rebuilds the whole view, and there is no cheap way to drag a page that
     does not exist yet; the arriving view slides in afterwards instead, which
     is enough to show which way you went. */

  var SWIPE_MIN = 60;          // px across before it counts as a swipe at all
  var SWIPE_RATIO = 1.8;       // and it must be this much more across than down
  var SWIPE_EDGE = 24;         // px of left edge left to the browser
  var SWIPE_TIME = 700;        // ms; slower than this is a drag, not a swipe

  var swipe = null;            // the gesture in progress
  var swipedAt = 0;            // when the last one landed - see the click trap

  function swipeBlocked(node) {
    for (; node && node !== document.body; node = node.parentNode) {
      if (node.nodeType !== 1) continue;
      var tag = node.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      if (node.classList.contains("tabs")) return true;
      /* Only genuine sideways scrollers. Plenty of elements here are wider
         than their box and clipped with overflow:hidden - a title with an
         ellipsis, say - and those are not going anywhere. */
      var ox = getComputedStyle(node).overflowX;
      if ((ox === "auto" || ox === "scroll") &&
          node.scrollWidth > node.clientWidth + 2) return true;
    }
    return false;
  }

  /* How far, how far off course, how long, and where from - and does that add
     up to a tab change? Kept apart from the event plumbing so the thresholds
     can be read (and checked) without a phone in your hand. */
  function swipeTarget(dx, dy, ms, from) {
    if (ms > SWIPE_TIME) return null;
    if (Math.abs(dx) < SWIPE_MIN) return null;
    if (Math.abs(dx) < Math.abs(dy) * SWIPE_RATIO) return null;

    var at = VIEWS.indexOf(from);
    if (at === -1) return null;
    /* Dragging left pulls the next tab in from the right, the way a stack of
       cards would move. Stops at both ends rather than wrapping round: the tab
       bar is a straight line, and going off one end to reappear at the other
       has no meaning on it. */
    var dir = dx < 0 ? 1 : -1;
    var next = VIEWS[at + dir];
    return next ? { view: next, dir: dir } : null;
  }

  function wireSwipe() {
    var phone = window.matchMedia("(max-width: 700px)");

    document.addEventListener("touchstart", function (e) {
      swipe = null;
      if (!phone.matches || e.touches.length !== 1) return;
      var t = e.touches[0];
      if (t.clientX < SWIPE_EDGE) return;
      if (swipeBlocked(e.target)) return;
      swipe = { x: t.clientX, y: t.clientY, at: Date.now() };
    }, { passive: true });

    /* A second finger arriving mid-gesture means it was never a swipe. */
    document.addEventListener("touchmove", function (e) {
      if (e.touches.length !== 1) swipe = null;
    }, { passive: true });

    document.addEventListener("touchend", function (e) {
      var start = swipe;
      swipe = null;
      if (!start || e.changedTouches.length !== 1) return;

      var t = e.changedTouches[0];
      var hit = swipeTarget(t.clientX - start.x, t.clientY - start.y,
                            Date.now() - start.at, state.view);
      if (!hit) return;

      swipedAt = Date.now();
      setView(hit.view, hit.dir);
    }, { passive: true });

    /* A finger that travelled far enough to change tab usually cancels its own
       click, but "usually" is not good enough when the thing underneath might
       be a meal card that flips over. Swallow one click, briefly - by time
       rather than by a flag cleared on a timer, because how long a browser
       waits before sending the click after touchend is its own business. The
       window covers the old 300ms tap delay and little more, so a deliberate
       tap straight after a swipe still lands. */
    document.addEventListener("click", function (e) {
      if (!swipedAt || Date.now() - swipedAt > 400) return;
      swipedAt = 0;
      e.stopPropagation();
      e.preventDefault();
    }, true);
  }

  // --------------------------------------------------------- week view

  function renderWeek() {
    // The picker is anchored to a chip this is about to throw away.
    closeStars();
    var key = state.viewWeek;
    $("w-title").textContent = weekLabel(key);
    $("w-range").textContent = weekRange(key);
    markTodayBtn("w-today", key, true);

    var grid = $("w-grid");
    clear(grid);
    var days = weekData(key);

    DAYS.forEach(function (day, i) {
      var dateKey = addDays(key, i);
      var cell = days[day];
      var card = el("div", "day-card" + (dateKey === state.today ? " is-today" : ""));

      var head = el("div", "day-head");
      var nameWrap = el("div");
      nameWrap.appendChild(el("span", "day-name", DAY_NAMES[day]));
      if (dateKey === state.today) nameWrap.appendChild(el("span", "today-flag", "Today"));
      head.appendChild(nameWrap);
      head.appendChild(el("span", "day-date", prettyDate(dateKey)));
      card.appendChild(head);

      var sittings = cell.sittings;
      var realOnes = sittings.filter(function (s) { return s.mealId || s.eaters.length; });

      if (realOnes.length === 0) {
        card.classList.add("no-plan");
        card.appendChild(el("div", "meal-title empty", "Nothing planned"));
      } else {
        realOnes.forEach(function (sitting, n) {
          card.appendChild(renderSitting(sitting, n > 0,
                                         { key: key, day: day, on: dateKey }));
        });

        // One cook for the evening, however many meals there are, and how many
        // they are cooking for. The count is worth its place because the chips
        // above can't be counted for it: one of them may read "+ 3 guests".
        //
        // Nothing is said when nobody is marked yet - a card that reads
        // "Cooking: not decided, for 0 people" is a worse answer than the same
        // card without the second half.
        var cook = cell.cookId ? personById(cell.cookId) : null;
        var heads = dayHeadCount(realOnes);
        var cookLine = el("div", "cook-line day-cook");
        cookLine.appendChild(el("span", "label", "Cooking: "));
        cookLine.appendChild(el("span", null, cook ? cook.name : "not decided"));
        if (heads) {
          cookLine.appendChild(el("span", "head-count", ", for " + peopleLabel(heads)));
        }
        card.appendChild(cookLine);
      }

      var missing = notEating(sittings);
      if (realOnes.length && missing.length && missing.length < household().length) {
        var out = el("div", "not-eating");
        out.appendChild(el("span", "label", "Not eating: "));
        out.appendChild(el("span", null, missing.map(function (p) { return p.name; }).join(", ")));
        card.appendChild(out);
      }

      grid.appendChild(card);
    });

    // Re-applied on every render inside the focus window rather than consumed
    // by the first one: this rebuild may be what moved the card.
    if (Date.now() < state.focusUntil) scrollToToday();
  }

  /* The week is seven cards in one column on a phone, so by Friday the day you
     actually want is off the bottom of the screen. Opening the app should
     answer "what are we eating tonight" without a scroll first.

     This is deliberately not one scroll. A single measurement taken the instant
     the cards are built is a guess about a page that has not finished settling:
     the offline banner appears and disappears above everything, a photo that
     turns out to be a dead link collapses the card it was in, and a phone can
     apply its own restored scroll position after the load event. Any of those
     moves the card after it has been placed, and the version of this that
     measured once put today's meal behind the week bar.

     So the intent is held for a couple of seconds and re-applied. Each pass is
     idempotent and cheap - a card already in the right place costs two
     measurements and no scroll. It stops the moment the person touches the
     screen, because being dragged back after you have started reading is worse
     than never being taken there. */
  var FOCUS_MS = 2000;
  var FOCUS_STEP_MS = 120;
  var focusTimer = null;

  function focusOnToday() {
    state.focusUntil = Date.now() + FOCUS_MS;
    /* Aim once straight away as well as on the timer. Callers that have just
       rebuilt the grid have today's card sitting there ready, and waiting a
       tick for the first pass shows them the top of the week first and then
       jumps. Callers that haven't find no card and this does nothing. */
    scrollToToday();
    if (focusTimer) return;
    focusTimer = setInterval(function () {
      if (Date.now() > state.focusUntil) {
        clearInterval(focusTimer);
        focusTimer = null;
        return;
      }
      scrollToToday();
    }, FOCUS_STEP_MS);
  }

  function stopFocusingToday() { state.focusUntil = 0; }

  /* The planner's version of the same idea, and a much smaller one. The week
     view needs a re-aiming loop because its cards carry photos that can change
     height after they are placed; a plan row is text and a couple of controls,
     so it is where it is going to be by the time this runs. */
  function scrollToPlanToday() {
    var row = $("p-grid").querySelector(".plan-row.is-today");
    if (!row) return;
    window.scrollBy(0, row.getBoundingClientRect().top - (barsBottom("plan") + 8));
  }

  /* Changing week lands you at the top of the week you asked for.

     The three week views have always held a Monday key rather than a day, so
     "next week" was already a whole-week move. What carried over was the scroll
     position: leave on Friday, arrive on next Friday, with Monday to Thursday
     above the fold and unread. Nobody navigates a week ahead to look at the end
     of it first.

     This week is the exception, on purpose. Coming back to it - by pressing
     Today, or by paging back from a week ahead - is almost always someone
     asking what is happening now, and the top of this week is days already
     eaten. So this one week lands on today, and the rest land on Monday. */
  function goToWeek(field, key, redraw, focus) {
    state[field] = key;
    stopFocusingToday();
    redraw();
    if (key === state.thisWeek && focus) focus();
    else window.scrollTo(0, 0);
  }

  /* Where the page's own furniture ends.

     Measured from the week bar rather than added up from the parts. The bar is
     sticky, so once the page has scrolled at all, where it actually is on
     screen is the one number here that cannot be wrong: it already has the top
     bar's height in it, along with whatever inset the phone keeps for its
     status bar and any banner above them. Adding up heights means modelling all
     of that correctly, and the model is what got this wrong before. */
  function barsBottom(view) {
    var weekbar = document.querySelector("#view-" + (view || "week") + " .weekbar");
    return weekbar ? Math.max(0, weekbar.getBoundingClientRect().bottom) : 0;
  }

  function scrollToToday() {
    var card = $("w-grid").querySelector(".day-card.is-today");
    if (!card) return;                 // some other week is on screen
    var move = card.getBoundingClientRect().top - (barsBottom() + 8);
    if (Math.abs(move) < 2) return;    // as good as it is going to get

    /* One place to aim for, and it is aimed at from wherever the card happens
       to be - above the bars or too far below them.

       There is deliberately no "it's on screen already, leave it" rule here.
       That version could not tell "today is where it should be" from "today is
       eighty pixels too low because the offline banner was still up when this
       was worked out", and so never corrected the second one. Nothing is needed
       in its place: on a Monday, and on a screen wide enough to show the whole
       week, the page has nowhere to scroll to and the browser ignores this. */
    window.scrollBy(0, move);
  }

  /* Tidy a scaled quantity for display. Mirrors the server's pretty_qty so the
     week view and the kitchen display always read the same. */
  function fmtQty(qty, unit) {
    if (unit === "g" || unit === "ml") return Math.round(qty) + unit;
    var n = Math.round(qty * 100) / 100;          // trim long decimals
    if (unit === "each" || unit === "") return String(n);
    var plural = unit;
    if (n !== 1 && ["tin", "pack", "clove", "handful", "pinch",
                    "sprig", "bunch", "slice"].indexOf(unit) !== -1) {
      plural = unit + "s";
    }
    return n + " " + plural;
  }

  /* Ingredients for one meal, scaled from the recipe's serving figure to the
     number actually eating it (factor = eaters / serves). Not rounded up like
     the shopping list - this is what goes in the pan, so 0.75 stays 0.75. */
  function ingredientLines(meal, eaters) {
    var ings = (meal && meal.ingredients) || [];
    var serves = meal && meal.serves;
    if (!ings.length || !serves || eaters <= 0) return [];
    var factor = eaters / serves;
    return ings.map(function (ing) {
      var unit = ing.unit || "";
      var qty = (Number(ing.qty) || 0) * factor;
      if (unit === "g" || unit === "ml") qty = Math.round(qty);
      return {
        qty: fmtQty(qty, unit),
        item: ing.item || "",
        note: ing.note || "",
        staple: !!ing.staple
      };
    });
  }

  /* The row of coloured name chips at the foot of a meal card.

     Everybody eating gets their own chip, always. There used to be an
     "Everyone" shorthand for a whole-house meal, and it read well - but a chip
     is now the thing you tap to say what you thought of the dinner, and one
     chip standing for four people has nothing to tap for three of them.

     `rate`, when given, is {key, day, sitting, on} and turns each household
     chip into a button that opens the star picker. Guests don't rate: the slot
     stands for a variable number of visitors, so a single star count against
     it would be nobody's opinion in particular. */
  function eatersRow(eating, guests, rate) {
    var eaters = el("div", "eaters");
    var guest = guestPerson();
    var named = eating.filter(function (p) { return !p.guest; });

    if (named.length === 0 && !guests) {
      eaters.appendChild(el("span", "chip none", "No one marked"));
      return eaters;
    }
    named.forEach(function (p) {
      eaters.appendChild(rate ? rateableChip(p, rate) : plainChip(p, p.name));
    });
    if (guests) {
      eaters.appendChild(plainChip(guest, "+ " + guestLabel(guests)));
    }
    return eaters;
  }

  function plainChip(person, label) {
    var chip = el("span", "chip", label);
    return paint(chip, person && person.color);
  }

  /* A name chip you can tap to rate. It is a name chip and nothing else to
     look at: no star badge, and nothing to tell it apart from a chip on a day
     too far off to rate. The row's job is to say who is eating, and a week of
     chips wearing rating hardware turns that row into a form. What you thought
     of the meal is in the picker, which is where you go to change it anyway. */
  function rateableChip(person, rate) {
    var stars = ratingOf(rate.sitting, person.id);
    var chip = el("button", "chip chip-rate", person.name);
    chip.type = "button";
    paint(chip, person.color);
    chip.title = stars
      ? person.name + " gave this " + stars + (stars === 1 ? " star" : " stars")
      : "Tap to rate for " + person.name;
    chip.setAttribute("aria-label", chip.title);
    chip.onclick = function (e) {
      e.stopPropagation();
      openStars(chip, person, rate);
    };
    return chip;
  }

  function ratingOf(sitting, personId) {
    var r = sitting && sitting.ratings;
    return (r && r[personId]) || 0;
  }

  // ----------------------------------------------------- the star picker

  /* Five stars stacked under the name that was tapped, one nearest and five
     furthest: the further your thumb travels, the better the meal was. That is
     the whole gesture, and it is the reason this is a column rather than the
     usual row of stars - a row asks you to hit the right star among five on a
     phone, where a column asks you how far to reach.

     It hangs off <body> at a fixed position rather than inside the card. The
     card is a 3D flip with clipped faces, and a popover inside it would be cut
     off at the edge or, worse, rotate away with the face it sits on. */
  var starsOpen = null;

  function closeStars() {
    if (!starsOpen) return;
    if (starsOpen.node.parentNode) starsOpen.node.parentNode.removeChild(starsOpen.node);
    if (starsOpen.chip) starsOpen.chip.classList.remove("picking");
    starsOpen = null;
    document.removeEventListener("keydown", starsKey, true);
  }

  function starsKey(e) {
    if (e.key === "Escape") { closeStars(); e.stopPropagation(); }
  }

  /* Anything that isn't a choice closes it: a tap elsewhere, a scroll, a
     rotation. The popover is placed from a measurement of where the chip was,
     so a page that moves underneath it would leave it pointing at nothing -
     better gone than misplaced. */
  function wireStars() {
    document.addEventListener("click", function () { closeStars(); });
    window.addEventListener("resize", closeStars);
    window.addEventListener("scroll", closeStars, true);
  }

  function openStars(chip, person, rate) {
    var reopening = starsOpen && starsOpen.chip === chip;
    closeStars();
    if (reopening) return;

    var current = ratingOf(rate.sitting, person.id);
    var pop = el("div", "star-pop");
    /* The picker wears the colour of the chip it came out of. On a card with
       four names on it, that is the whole answer to "did I tap the right one" -
       and it is a better answer than a name written at the top of the list,
       which is another line to read before you can do the thing you opened it
       to do. */
    /* paint(), not just a background: the stars and the numbers inside are
       drawn in currentColor, so they follow the lettering this picks.
       starTones() covers the two things on here that aren't lettering. */
    starTones(paint(pop, person.color), person.color);
    // The colour is the cue on screen; a screen reader gets the name here
    // instead, since there is no longer a heading to read out.
    pop.setAttribute("role", "group");
    pop.setAttribute("aria-label", "Rate for " + person.name);

    var col = el("div", "star-col");
    for (var n = 1; n <= 5; n++) {
      col.appendChild(starButton(n, current, person, rate));
    }
    pop.appendChild(col);

    /* Only offered once there is something to take back. A "clear" on an
       unrated meal is a button that does nothing, sitting under a thumb that
       is about to press something else. */
    if (current) {
      var clear = el("button", "star-clear", "Clear");
      clear.type = "button";
      clear.onclick = function () { sendRating(person, rate, null); };
      pop.appendChild(clear);
    }

    pop.addEventListener("click", function (e) { e.stopPropagation(); });
    document.body.appendChild(pop);
    chip.classList.add("picking");
    starsOpen = { node: pop, chip: chip, key: rate.key, day: rate.day,
                  sid: rate.sitting.id, pid: person.id };
    placeStars(pop, chip);
    document.addEventListener("keydown", starsKey, true);
  }

  function starButton(n, current, person, rate) {
    var b = el("button", "star-btn" + (n <= current ? " on" : ""));
    b.type = "button";
    // Number first: it is the thing you are aiming at, and reading left to
    // right it says "3 stars" rather than "star, three".
    b.appendChild(el("span", "star-n", String(n)));
    b.appendChild(starShape());
    b.setAttribute("aria-label", n + (n === 1 ? " star" : " stars") +
                   " for " + person.name);
    b.onclick = function () {
      // Pressing the star already showing means "actually, no" - the same tap
      // that set it takes it off, so nobody has to find a Clear button.
      sendRating(person, rate, n === current ? null : n);
    };
    return b;
  }

  /* Drawn rather than typed. ★ is whatever the device's font makes of it -
     thin and spiky on some, a flat black lozenge on others - and it can't be
     given rounded points. This one is a plain five-pointer with a fat inner
     radius, stroked in its own fill colour with round joins, which rounds the
     points off and thickens it into something friendlier. */
  var STAR_PATH = "M12 4 L14.65 8.36 L19.61 9.53 L16.28 13.39 L16.7 18.47 " +
                  "L12 16.5 L7.3 18.47 L7.72 13.39 L4.39 9.53 L9.35 8.36 Z";

  function starShape() {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "star-svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    var path = document.createElementNS(ns, "path");
    path.setAttribute("d", STAR_PATH);
    svg.appendChild(path);
    return svg;
  }

  /* Below the chip by preference, above it when the card is near the bottom of
     the screen - but one star is always the one nearest the name, whichever way
     it opens, or the gesture would mean the opposite thing on the last day of
     the week. */
  function placeStars(pop, chip) {
    var at = chip.getBoundingClientRect();
    var size = pop.getBoundingClientRect();
    var gap = 6;
    var below = window.innerHeight - at.bottom;
    var up = below < size.height + gap && at.top > size.height + gap;

    pop.classList.toggle("upward", up);
    pop.style.top = (up ? at.top - size.height - gap : at.bottom + gap) + "px";

    var left = at.left + at.width / 2 - size.width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - size.width - 8));
    pop.style.left = left + "px";
    pop.style.visibility = "visible";
  }

  function sendRating(person, rate, stars) {
    var sitting = rate.sitting;
    closeStars();
    api("PUT", "/api/week/" + rate.key + "/" + rate.day +
               "/sittings/" + sitting.id + "/rating",
        { personId: person.id, stars: stars })
      .then(function (updated) {
        // Patch the copy the week view is drawn from, then redraw just this
        // week: a full reload would rebuild every card and lose the reader's
        // place on a page they were part way down.
        var list = sittingsFor(rate.key, rate.day);
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === sitting.id) { list[i] = updated; break; }
        }
        // No "Saved" flag: the chip comes back wearing the stars, which says
        // it more plainly and in the place you were already looking.
        if (state.view === "week") renderWeek();
        if (state.view === "meals") renderMeals();
      })
      .catch(fail);
  }

  /* The ingredient list that lives on the back of a meal card. Shared by the
     week view, where quantities are scaled to the number eating, and the meal
     library, where they are shown at the recipe's own serves count. */
  function ingredientsFace(lines, heading) {
    var back = el("div");
    back.appendChild(el("div", "ing-title", heading));
    var list = el("ul", "ing-list");
    lines.forEach(function (L) {
      var li = el("li", "ing-item" + (L.staple ? " staple" : ""));
      li.appendChild(el("span", "ing-qty", L.qty));
      li.appendChild(el("span", "ing-name",
        L.item + (L.note ? " (" + L.note + ")" : "")));
      list.appendChild(li);
    });
    back.appendChild(list);
    return back;
  }

  /* Assembles a two-sided card. `trigger` is the part of the front that turns
     it over and carries the hint badge; `alsoFlip` are extra elements that
     turn it too but can't hold a badge, such as a bare <img>. */
  function makeFlip(front, back, trigger, alsoFlip) {
    trigger.classList.add("flip-trigger");
    trigger.appendChild(el("div", "flip-hint front-hint", "Ingredients ↻"));
    back.appendChild(el("div", "flip-hint back-hint", "Tap to flip back"));

    var flip = el("div", "flip");
    var inner = el("div", "flip-inner");
    front.className = (front.className + " flip-face flip-front").trim();
    back.className = (back.className + " flip-face flip-back").trim();
    inner.appendChild(front);
    inner.appendChild(back);
    flip.appendChild(inner);

    /* Both faces share one grid cell, so left alone the card is always as tall
       as the taller of the two - twenty ingredients meant a tall, mostly empty
       card on the week view. Size the container to whichever face is showing
       and let CSS animate between the two. The faces themselves are pinned to
       the top of the cell in the stylesheet, so they keep their natural height
       and can still be measured after this runs.

       A ResizeObserver rather than a single measurement: hero photos load
       lazily, so the front grows after the card is built, and the ingredient
       list rewraps whenever the column width changes. */
    var resize = function () {
      var face = flip.classList.contains("flipped") ? back : front;
      var h = face.getBoundingClientRect().height;
      if (h) inner.style.height = h + "px";
    };
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(resize);
      ro.observe(front);
      ro.observe(back);
    } else {
      window.addEventListener("resize", resize);
      setTimeout(resize, 0);
    }

    function turn(on) {
      return function (e) {
        // A tap on a link or a button does its own job, not the flip.
        if (e.target.closest && e.target.closest("a, button")) return;
        flip.classList.toggle("flipped", on);
        resize();
      };
    }
    trigger.addEventListener("click", turn(true));
    (alsoFlip || []).forEach(function (node) {
      node.classList.add("flip-trigger");
      node.addEventListener("click", turn(true));
    });
    back.addEventListener("click", turn(false));

    return flip;
  }

  /* One meal within a day on the week view. The picture flips over on a tap to
     show the ingredient quantities for the number eating, and a tap on that
     list flips it back.

     `on` is the date the sitting falls on, and is what decides whether the name
     chips can be rated: today and earlier, yes; later in the week, no. Nobody
     can say what Thursday was like on Tuesday. */
  function renderSitting(sitting, isExtra, ctx) {
    var block = el("div", "sitting" + (isExtra ? " extra" : ""));
    var meal = sitting.mealId ? mealById(sitting.mealId) : null;
    var eating = inHouseholdOrder(sitting.eaters.map(personById).filter(Boolean));
    var heads = headCount(sitting);
    var lines = meal ? ingredientLines(meal, heads) : [];

    // Front face: exactly what the card showed before.
    var front = el("div");
    var trigger = null;   // the element a tap flips from (picture or title)

    if (meal) {
      if (meal.image) {
        var hero = el("div", "sitting-hero");
        var photo = el("img");
        photo.alt = "";
        photo.loading = "lazy";
        photo.setAttribute("src", meal.image);
        // A dead image link degrades to the plain title, not a broken icon.
        photo.onerror = function () {
          if (hero.parentNode) {
            hero.parentNode.replaceChild(el("div", "meal-title", meal.name), hero);
          }
        };
        hero.appendChild(photo);
        hero.appendChild(el("div", "hero-name", meal.name));
        front.appendChild(hero);
        trigger = hero;
      } else {
        var title = el("div", "meal-title", meal.name);
        front.appendChild(title);
        trigger = title;
      }
      (meal.tags || []).forEach(function (t) { front.appendChild(el("span", "tag", t)); });
      if (hasLink(meal)) front.appendChild(recipeLink(meal));
    } else {
      front.appendChild(el("div", "meal-title empty", "Meal not chosen"));
    }

    /* Per-serving macros only. There used to be a "N kcal cooked in total for
       six people" line under this; nobody eats the pan, so the number answered
       a question no one was asking. What one portion costs you is the figure
       that means something, and it is the one above. */
    if (meal && meal.macros) {
      front.appendChild(macroStrip(meal.macros, 1));
    } else if (meal) {
      front.appendChild(el("div", "macro-none", "No nutrition info"));
    }

    if (sitting.note) front.appendChild(el("div", "day-note", sitting.note));
    var rate = (ctx && ctx.on <= state.today && !state.offline)
      ? { key: ctx.key, day: ctx.day, sitting: sitting, on: ctx.on }
      : null;
    front.appendChild(eatersRow(eating, guestsOn(sitting), rate));

    // With no ingredients (or nobody eating) there's nothing to flip to, so the
    // card stays a plain front, just as it always was.
    if (!lines.length || !trigger) {
      while (front.firstChild) block.appendChild(front.firstChild);
      return block;
    }

    // Back face: the ingredient list, scaled to the number eating - which is
    // the head count, not the number of names, once guests are among them.
    var who = heads + " " + (heads === 1 ? "person" : "people");
    var back = ingredientsFace(lines, meal.name + " ingredients for " + who);

    block.appendChild(makeFlip(front, back, trigger));
    return block;
  }

  // ----------------------------------------------------------- planner

  function flagSaved() {
    var flag = $("p-saved");
    flag.hidden = false;
    clearTimeout(flag._t);
    flag._t = setTimeout(function () { flag.hidden = true; }, 1200);
  }

  function saveSitting(key, day, sid, patch) {
    return api("PUT", "/api/week/" + key + "/" + day + "/sittings/" + sid, patch)
      .then(function (updated) {
        var list = sittingsFor(key, day);
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === sid) { list[i] = updated; break; }
        }
        flagSaved();
        return updated;
      })
      .catch(fail);
  }

  /* Assigning someone to one meal takes them off the other meals that day,
     so the server's copy is authoritative after an eaters change. */
  function saveEaters(key, day, sid, eaters) {
    return api("PUT", "/api/week/" + key + "/" + day + "/sittings/" + sid, { eaters: eaters })
      .then(function () { return reloadWeek(key); })
      .then(function () { flagSaved(); refreshPlanDay(key, day); })
      .catch(fail);
  }

  /* How many the guest slot stands for at this meal. Only the one day is
     redrawn: nobody else's row changes, and a full reload under a thumb that is
     still on the + button loses the next press. */
  function saveGuests(key, day, sid, guests) {
    return api("PUT", "/api/week/" + key + "/" + day + "/sittings/" + sid, { guests: guests })
      .then(function (updated) {
        var sittings = sittingsFor(key, day);
        for (var i = 0; i < sittings.length; i++) {
          if (sittings[i].id === sid) sittings[i] = updated;
        }
        if (state.weeks[key] && state.weeks[key][day]) {
          state.weeks[key][day].sittings = sittings;
        }
        flagSaved();
        refreshPlanDay(key, day);
      })
      .catch(fail);
  }

  /* Straight from the meal library onto a date. Creates the meal's block on
     that day and hands over to the planner for the rest - who's cooking, who's
     eating - because that is where those controls already live and there is no
     good reason to build a second, smaller copy of them.

     One request, with the meal already on it: a POST to make the block and
     then a PUT to set the meal would strand an empty block on that day if the
     second one failed. */
  function quickAdd(meal, dateKey) {
    var key = mondayOf(dateKey);
    var day = dayOf(dateKey);
    return api("POST", "/api/week/" + key + "/" + day + "/sittings", { mealId: meal.id })
      .then(function (sitting) {
        if (!state.weeks[key]) state.weeks[key] = weekData(key);
        if (!state.weeks[key][day]) state.weeks[key][day] = { cookId: null, sittings: [] };
        state.weeks[key][day].sittings.push(sitting);
        state.planWeek = key;
        state.planFocus = { day: day, at: Date.now(), scrolled: false };
        setView("plan");
        toast(meal.name + " added to " + DAY_NAMES[day] + " " + prettyDate(dateKey));
      })
      .catch(fail);
  }

  /* Take the planner to the day just added to, and mark it long enough to be
     seen. Re-applied on every render rather than consumed by the first,
     because setView triggers a refresh whose reply rebuilds the whole grid a
     moment later and would otherwise wipe the highlight mid-flash. Scrolling
     happens once, though - being dragged back after you have started reading
     is worse than not being taken there at all. */
  var PLAN_FOCUS_MS = 2600;

  function applyPlanFocus() {
    var focus = state.planFocus;
    if (!focus) return;
    if (Date.now() - focus.at > PLAN_FOCUS_MS) { state.planFocus = null; return; }

    var row = $("p-grid").querySelector('.plan-row[data-day="' + focus.day + '"]');
    if (!row) return;
    row.classList.add("just-added");
    if (!focus.scrolled) {
      focus.scrolled = true;
      /* Centred, not at the top: the topbar is sticky and would otherwise sit
         over the row we just made a point of showing. */
      if (row.scrollIntoView) row.scrollIntoView({ block: "center" });
    }
  }

  function renderPlan() {
    var key = state.planWeek;
    $("p-title").textContent = "Plan: " + weekLabel(key).toLowerCase();
    $("p-range").textContent = weekRange(key);
    markTodayBtn("p-today", key);

    var grid = $("p-grid");
    clear(grid);

    if (state.meals.length === 0) {
      var warn = el("div", "empty-state");
      warn.appendChild(el("p", null, "Your meal library is empty."));
      var link = el("button", "btn small", "Add some meals");
      link.onclick = function () { setView("meals"); };
      warn.appendChild(link);
      grid.appendChild(warn);
      return;
    }

    DAYS.forEach(function (day, i) {
      grid.appendChild(buildPlanRow(key, day, i));
    });
    applyPlanFocus();
  }

  /* One day's editable row. Built separately so a change to one day can
     replace just that row - a full re-render collapses the page and throws
     the browser's scroll position back to the top. */
  function buildPlanRow(key, day, i) {
    var days = weekData(key);
    {
      var dateKey = addDays(key, i);
      var sittings = days[day].sittings;
      var row = el("div", "plan-row" + (dateKey === state.today ? " is-today" : ""));
      row.setAttribute("data-day", day);

      var dayLabel = el("div", "plan-day", DAY_NAMES[day]);
      dayLabel.appendChild(el("span", null, prettyDate(dateKey)));
      row.appendChild(dayLabel);

      var stack = el("div", "plan-stack");

      sittings.forEach(function (sitting, n) {
        stack.appendChild(planSitting(key, day, sitting, n, sittings.length));
      });

      // One cook for the whole evening, sitting below the meals it covers.
      if (sittings.length) {
        var cookLine = el("div", "plan-line day-cook-line");
        cookLine.appendChild(el("label", null, sittings.length > 1 ? "Cook (all meals)" : "Cook"));
        var cookSel = el("select");
        cookSel.appendChild(new Option("- not decided -", ""));
        // Guests don't cook. If one does, they're family for the evening and
        // whoever invited them can take the credit.
        household().forEach(function (p) { cookSel.appendChild(new Option(p.name, p.id)); });
        cookSel.value = days[day].cookId || "";
        cookSel.onchange = function () {
          var value = cookSel.value || null;
          api("PUT", "/api/week/" + key + "/" + day, { cookId: value })
            .then(function (updated) {
              if (!state.weeks[key]) state.weeks[key] = weekData(key);
              state.weeks[key][day].cookId = updated.cookId;
              flagSaved();
            })
            .catch(fail);
        };
        cookLine.appendChild(cookSel);
        stack.appendChild(cookLine);
      }

      var missing = notEating(sittings);
      if (sittings.length && missing.length) {
        stack.appendChild(el("div", "not-eating small",
          "Not eating: " + missing.map(function (p) { return p.name; }).join(", ")));
      }

      var addBtn = el("button", "btn ghost small add-meal",
        sittings.length ? "+ Another meal this day" : "+ Add a meal");
      addBtn.type = "button";
      addBtn.onclick = function () {
        addBtn.disabled = true;
        api("POST", "/api/week/" + key + "/" + day + "/sittings")
          .then(function (sitting) {
            if (!state.weeks[key]) state.weeks[key] = weekData(key);
            if (!state.weeks[key][day]) state.weeks[key][day] = { sittings: [] };
            state.weeks[key][day].sittings.push(sitting);
            refreshPlanDay(key, day);
          })
          .catch(function (err) { addBtn.disabled = false; fail(err); });
      };
      stack.appendChild(addBtn);

      row.appendChild(stack);
      return row;
    }
  }

  /* Swap in a rebuilt row for one day, leaving the rest of the page - and
     the scroll position, and any half-typed notes on other days - alone. */
  function refreshPlanDay(key, day) {
    if (state.view !== "plan" || state.planWeek !== key) return;
    var grid = $("p-grid");
    var old = grid.querySelector('.plan-row[data-day="' + day + '"]');
    if (!old) { renderPlan(); return; }
    grid.replaceChild(buildPlanRow(key, day, DAYS.indexOf(day)), old);
  }

  /* One editable meal block within a day on the planner. */
  function planSitting(key, day, sitting, index, total) {
    var box = el("div", "sitting-edit" + (index > 0 ? " extra" : ""));

    if (total > 1) {
      var head = el("div", "sitting-head");
      head.appendChild(el("span", "sitting-num", "Meal " + (index + 1)));
      box.appendChild(head);
    }

    var fields = el("div", "plan-fields");

    // meal
    var mealLine = el("div", "plan-line");
    mealLine.appendChild(el("label", null, "Meal"));
    var mealSel = el("select");
    mealSel.appendChild(new Option("- nothing chosen -", ""));
    state.meals.forEach(function (m) { mealSel.appendChild(new Option(m.name, m.id)); });
    mealSel.value = sitting.mealId || "";
    mealSel.onchange = function () {
      saveSitting(key, day, sitting.id, { mealId: mealSel.value || null })
        .then(function () { refreshPlanDay(key, day); });
    };
    mealLine.appendChild(mealSel);

    var chosen = sitting.mealId ? mealById(sitting.mealId) : null;
    if (chosen && hasLink(chosen)) mealLine.appendChild(recipeLink(chosen));
    fields.appendChild(mealLine);

    // who's eating this one
    var eatLine = el("div", "plan-line");
    eatLine.appendChild(el("label", null, "Eating"));
    var toggles = el("div", "eater-toggles");
    if (household().length === 0) {
      toggles.appendChild(el("span", "muted small", "Add people on the Settings tab first."));
    }

    /* Who's already down for a different meal today? Guests are not tracked
       here: two friends at the early sitting and four relatives at the late one
       are not the same people twice, so the slot is never "taken". */
    var elsewhere = {};
    sittingsFor(key, day).forEach(function (other) {
      if (other.id === sitting.id) return;
      (other.eaters || []).forEach(function (id) { elsewhere[id] = true; });
    });
    var guest = guestPerson();
    if (guest) delete elsewhere[guest.id];

    state.people.forEach(function (p) {
      var on = sitting.eaters.indexOf(p.id) !== -1;
      var btn = el("button", "toggle" + (!on && elsewhere[p.id] ? " taken" : ""), p.name);
      btn.type = "button";
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) paint(btn, p.color);
      if (!on && elsewhere[p.id]) btn.title = p.name + " is down for another meal this day";
      btn.onclick = function () {
        var next = sitting.eaters.slice();
        var idx = next.indexOf(p.id);
        if (idx === -1) next.push(p.id); else next.splice(idx, 1);
        saveEaters(key, day, sitting.id, next);
      };
      toggles.appendChild(btn);

      /* The number sits with the toggle it belongs to, and only while it is on.
         A stepper rather than a free text box: this is a kitchen decision made
         with one thumb, and it is never 47. */
      if (p.guest && on) {
        var count = guestsOn(sitting);
        var stepper = el("span", "guest-count");
        var less = el("button", "guest-step", "−");
        less.type = "button";
        less.disabled = count <= 1;
        less.setAttribute("aria-label", "One guest fewer");
        var shown = el("span", "guest-n", String(count));
        var more = el("button", "guest-step", "+");
        more.type = "button";
        more.disabled = count >= 30;
        more.setAttribute("aria-label", "One guest more");
        less.onclick = function () { saveGuests(key, day, sitting.id, count - 1); };
        more.onclick = function () { saveGuests(key, day, sitting.id, count + 1); };
        stepper.appendChild(less);
        stepper.appendChild(shown);
        stepper.appendChild(more);
        toggles.appendChild(stepper);
      }
    });

    if (state.people.length > 1) {
      /* "Everyone free" is about the household. It doesn't lay places for
         visitors nobody has mentioned. */
      var free = household().filter(function (p) {
        return sitting.eaters.indexOf(p.id) !== -1 || !elsewhere[p.id];
      });
      var allFree = free.length > 0 && free.every(function (p) {
        return sitting.eaters.indexOf(p.id) !== -1;
      });
      var bulk = el("button", "icon-btn everyone-btn", allFree ? "None" : "Everyone free");
      bulk.type = "button";
      bulk.onclick = function () {
        var next = allFree ? [] : free.map(function (p) { return p.id; });
        // Filling the table doesn't send the visitors home; clearing it does.
        if (!allFree && guest && sitting.eaters.indexOf(guest.id) !== -1) {
          next.push(guest.id);
        }
        saveEaters(key, day, sitting.id, next);
      };
      toggles.appendChild(bulk);
    }
    eatLine.appendChild(toggles);
    fields.appendChild(eatLine);

    // note
    var noteLine = el("div", "plan-line");
    noteLine.appendChild(el("label", null, "Note"));
    var note = el("input");
    note.type = "text";
    note.maxLength = 300;
    note.placeholder = "e.g. eating at 6";
    note.value = sitting.note || "";
    var noteTimer;
    note.oninput = function () {
      clearTimeout(noteTimer);
      noteTimer = setTimeout(function () {
        saveSitting(key, day, sitting.id, { note: note.value });
      }, 600);
    };
    note.onblur = function () {
      clearTimeout(noteTimer);
      saveSitting(key, day, sitting.id, { note: note.value });
    };
    noteLine.appendChild(note);
    fields.appendChild(noteLine);

    box.appendChild(fields);

    var remove = el("button", "icon-btn danger remove-sitting", "Remove this meal");
    remove.type = "button";
    remove.onclick = function () {
      api("DELETE", "/api/week/" + key + "/" + day + "/sittings/" + sitting.id)
        .then(function () {
          state.weeks[key][day].sittings =
            sittingsFor(key, day).filter(function (s) { return s.id !== sitting.id; });
          refreshPlanDay(key, day);
        })
        .catch(fail);
    };
    box.appendChild(remove);

    return box;
  }

  // ---------------------------------------------------------- shopping

  function renderShopping() {
    var key = state.shopWeek || state.thisWeek;
    $("s-title").textContent = "Shopping: " + weekLabel(key).toLowerCase();
    $("s-range").textContent = weekRange(key);
    markTodayBtn("s-today", key);

    /* Offline, the 20-second poll keeps running - that is how the app notices
       it has got home again - and every tick re-renders the current view.
       Rebuilding the list under someone's thumb halfway round the shop would
       throw away their place on it, and there is no new answer to be had
       anyway. So once it is up, leave it up. */
    if (state.offline && state.shopList && state.shopRendered === key) {
      updateShareBtn();
      return;
    }

    var missingBox = $("s-missing");
    var body = $("s-body");
    clear(missingBox);
    clear(body);
    $("s-note").textContent = "";
    /* Dropped on every render: a stale list from the previous week must not
       be shareable while the new one is still in flight. */
    state.shopList = null;
    state.shopRendered = null;
    updateShareBtn();
    /* Not emptied: the extras belong to no week, so they stay on screen while
       the new week's food is still in flight. Re-rendered only because the
       card was just cleared along with everything else. */
    renderExtras();
    extrasError("");

    /* No offline short-circuit here any more. The list can't be worked out on
       the phone - it comes from the plan plus what's in the cupboard, which
       only the server knows - but the service worker keeps the last answer it
       saw for each week, so ask and see what comes back. */
    getCacheable("/api/shopping?week=" + key).catch(function (err) {
      /* An old server that predates this page answers 404. Explain the fix
         rather than showing "Unknown endpoint". */
      if (/unknown endpoint/i.test(err.message || "")) {
        var msg = el("div", "notice-banner shop-missing");
        msg.appendChild(el("strong", null, "The meal planner server needs a restart. "));
        msg.appendChild(el("span", null,
          "It's still running an older version from before the shopping list " +
          "existed. On the computer that runs it, close the black window and " +
          "double-click Start Meal Planner again, then refresh this page."));
        body.appendChild(msg);
        throw { handled: true };
      }
      /* Offline and this week was never opened at home, so there is nothing
         saved to fall back on. The service worker's message says as much. */
      if (err && err.fromCache) {
        var none = el("div", "notice-banner shop-missing");
        none.appendChild(el("strong", null, "Not saved for offline yet. "));
        none.appendChild(el("span", null, err.message));
        body.appendChild(none);
        throw { handled: true };
      }
      /* No service worker at all - plain http, or a browser that refused to
         register one. Nothing is saved and nothing can be. */
      if (state.offline) {
        var off = el("div", "notice-banner shop-missing");
        off.appendChild(el("strong", null, "Not available offline. "));
        off.appendChild(el("span", null,
          "The shopping list is worked out by the meal planner at home, and " +
          "this device has no saved copy of it."));
        body.appendChild(off);
        throw { handled: true };
      }
      throw err;
    }).then(function (res) {
      var list = res.data;
      if (state.shopWeek !== key && state.thisWeek !== key) return;
      clear(missingBox);
      clear(body);
      state.shopList = list;
      state.shopRendered = key;
      /* Lifted out of the week's answer and kept on its own, because it isn't
         the week's: the same standing list is on screen whichever Monday you
         are looking at, and stepping between weeks must not blank it. */
      state.extras = list.extras || [];
      state.knownExtras = list.knownExtras || [];
      updateShareBtn();
      renderExtras();

      /* Say how old it is. The plan may have moved on since, and unlike the
         week view there is no way to tell from the contents. */
      if (res.cached) {
        var age = res.cachedAt ? niceAge(res.cachedAt) : "";
        var stale = el("div", "notice-banner shop-missing");
        stale.appendChild(el("strong", null, "Saved copy. "));
        stale.appendChild(el("span", null,
          "The list as it was" + (age ? " " + age : "") +
          ". Anything changed in the plan since then isn't on it."));
        missingBox.appendChild(stale);
      }

      // Anything planned that can't contribute goes at the top, where it
      // can't be missed - the list below is incomplete without it.
      if (list.missing.length) {
        var warn = el("div", "notice-banner shop-missing");
        warn.appendChild(el("strong", null,
          list.missing.length === 1
            ? "One meal isn't on this list. "
            : list.missing.length + " meals aren't on this list. "));
        warn.appendChild(el("span", null, "Buy for these separately:"));
        var ul = el("ul", "missing-list");
        list.missing.forEach(function (m) {
          var li = el("li");
          li.appendChild(el("b", null, m.meal));
          li.appendChild(document.createTextNode(
            " - " + m.day + ", " + m.eaters + (m.eaters === 1 ? " person" : " people") +
            " (" + m.why + ")"));
          var fix = el("button", "icon-btn", "Add ingredients");
          fix.type = "button";
          fix.onclick = function () {
            var meal = mealById(m.mealId);
            setView("meals");
            if (meal) startEditMeal(meal);
          };
          li.appendChild(fix);
          ul.appendChild(li);
        });
        warn.appendChild(ul);
        missingBox.appendChild(warn);
      }

      if (!list.items.length && !list.staples.length) {
        /* Extras are not "nothing to buy" - somebody has written baking paper
           down and it is sitting right above this. */
        body.appendChild(el("div", "empty-state",
          list.mealsPlanned
            ? "No ingredients to buy - none of this week's meals have any listed."
            : "Nothing planned for this week yet."));
        return;
      }

      body.appendChild(shoppingSection("To buy", list.items, false));
      if (list.staples.length) {
        body.appendChild(shoppingSection("Check the cupboard", list.staples, true));
      }

      $("s-note").textContent =
        "Quantities cover " + list.mealsCounted +
        (list.mealsCounted === 1 ? " meal" : " meals") +
        ", scaled by how many are eating each one and rounded up.";
    }).catch(function (err) {
      if (!err || !err.handled) fail(err);
    });
  }

  // ------------------------------------------------- extras on the list

  /* Things no recipe will ever mention: baking paper, foil, a birthday candle.
     One standing list, the same one whichever week is on screen. It used to be
     kept per week on the theory that a roll of baking paper bought on Saturday
     shouldn't still be there a fortnight later - but the week rolling over was
     throwing away everything that hadn't been bought yet, which is precisely
     the stuff you most needed reminding about.

     Two ways off the list, because there are two ways things get into this
     house. Bought in a shop, it is gone the moment you say so. Ordered for
     delivery, it drops into an ordered group and waits there - struck through,
     out of the way, but still on the page - until the van comes or doesn't.
     Nothing is on a timer: an order that never arrived is the one thing on
     this page that should be shouting, not quietly deleting itself.

     They arrive with the shopping list itself, so this draws from
     state.shopList rather than fetching anything of its own. */
  function extrasList() {
    return state.extras || [];
  }

  /* Which rows are ticked, and which group the ticking is happening in.

     Selection is scoped to one group on purpose. The actions differ either
     side - a thing you haven't ordered can't arrive - and a bar offering four
     buttons, two of which do nothing to half of what you've ticked, is worse
     than making you do it in two goes. Ticking in one group clears the other. */
  var extraSel = { scope: "need", ids: {} };

  function selectedExtras() {
    return Object.keys(extraSel.ids).filter(function (id) {
      return extraSel.ids[id];
    });
  }

  function clearExtraSel() { extraSel = { scope: "need", ids: {} }; }

  /* "3", "500g", "2 tins". Nothing at all for a single one of something,
     because "1 baking paper" is not how anybody writes a shopping list. */
  function extraQty(extra) {
    var qty = extra.qty || 1;
    var unit = extra.unit || "each";
    if (unit === "g" || unit === "ml") return qty + unit;
    if (unit === "kg" || unit === "l") return qty + unit;
    if (unit === "each") return qty === 1 ? "" : "×" + qty;
    var plural = qty !== 1 && ["tin", "pack", "clove", "handful", "pinch",
      "sprig", "bunch", "slice"].indexOf(unit) >= 0 ? unit + "s" : unit;
    return qty + " " + plural;
  }

  /* How long something has been on order, in the only units that matter when
     you're deciding whether to chase it. */
  function orderedAgo(iso) {
    if (!iso) return "";
    var then = toDate(iso);
    if (isNaN(then.getTime())) return "";
    var now = new Date();
    var days = Math.round((Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())
      - then.getTime()) / 86400000);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    return days + " days ago";
  }

  /* Everything ever typed into the box, offered back as you type. Ordered by
     the server - most used, then most recent - and the browser matches on it,
     so "bak" finds baking paper months after the last roll was bought.

     Bare names, no quantities: the number belongs to this week's shop, not to
     the thing. Things already on the list are left out - they are two inches
     above the box, and suggesting one is only ever an invitation to add it
     twice. */
  function renderExtraSuggestions() {
    var box = $("extras-known");
    if (!box) return;
    clear(box);
    var already = {};
    extrasList().forEach(function (e) { already[e.item.toLowerCase()] = true; });
    (state.knownExtras || []).forEach(function (name) {
      if (already[name.toLowerCase()]) return;
      var option = document.createElement("option");
      option.value = name;
      box.appendChild(option);
    });
  }

  /* One row. The tick box is the whole interaction - it is how you act on one
     thing and how you act on twelve, so there is no separate select mode to
     find and nothing to long-press. */
  function extraRow(extra, ordered) {
    var row = el("li", "extras-row" + (ordered ? " is-ordered" : ""));

    var box = document.createElement("input");
    box.type = "checkbox";
    box.className = "extras-tick";
    box.checked = !!extraSel.ids[extra.id];
    box.disabled = !!state.offline;
    box.setAttribute("aria-label", extra.item);
    box.onchange = function () {
      var scope = ordered ? "ordered" : "need";
      if (extraSel.scope !== scope) extraSel = { scope: scope, ids: {} };
      extraSel.ids[extra.id] = box.checked;
      renderExtras();
    };
    row.appendChild(box);

    var name = el("span", "extras-name", extra.item);
    row.appendChild(name);

    var qty = extraQty(extra);
    if (ordered) {
      if (qty) row.appendChild(el("span", "extras-qty muted", qty));
      row.appendChild(el("span", "extras-age muted small",
        orderedAgo(extra.orderedAt)));
      return row;
    }

    /* The quantity is parsed off what you typed, so it has to be correctable
       without retyping the line. Two buttons and the number between them. */
    var stepper = el("span", "extras-stepper");
    var down = el("button", "step-btn", "−");
    down.type = "button";
    down.disabled = !!state.offline;
    down.setAttribute("aria-label", "One fewer " + extra.item);
    down.onclick = function () { stepExtra(extra, -1); };
    var up = el("button", "step-btn", "+");
    up.type = "button";
    up.disabled = !!state.offline;
    up.setAttribute("aria-label", "One more " + extra.item);
    up.onclick = function () { stepExtra(extra, 1); };
    stepper.appendChild(down);
    stepper.appendChild(el("span", "extras-qty", qty || "1"));
    stepper.appendChild(up);
    row.appendChild(stepper);
    return row;
  }

  /* The heading over a group, with a tick box that takes the lot.

     It selects rather than acting. A button that marked a whole order arrived
     was the obvious thing and the wrong one: the usual delivery is everything
     bar the one item they'd run out of, and a button leaves you unpicking that
     one afterwards. Select all, untick the one that didn't come, and the bar
     is already offering the two things you might do with the rest. */
  function groupHead(label, items, ordered) {
    var head = el("li", "extras-batch");
    var ids = items.map(function (e) { return e.id; });
    var mine = ids.filter(function (id) {
      return extraSel.scope === (ordered ? "ordered" : "need") && extraSel.ids[id];
    });

    var box = document.createElement("input");
    box.type = "checkbox";
    box.className = "extras-tick";
    box.checked = mine.length === ids.length;
    // Some but not all: the box says so rather than lying in either direction.
    box.indeterminate = mine.length > 0 && mine.length < ids.length;
    box.disabled = !!state.offline;
    box.setAttribute("aria-label", "Select all - " + label);
    box.onchange = function () {
      var scope = ordered ? "ordered" : "need";
      if (extraSel.scope !== scope) extraSel = { scope: scope, ids: {} };
      ids.forEach(function (id) { extraSel.ids[id] = box.checked; });
      renderExtras();
    };
    head.appendChild(box);
    head.appendChild(el("span", "extras-batch-label",
      label + " · " + items.length + (items.length === 1 ? " item" : " items")));
    return head;
  }

  function renderExtras() {
    var list = $("extras-list");
    clear(list);
    renderExtraSuggestions();
    var extras = extrasList();
    var need = extras.filter(function (e) { return e.state !== "ordered"; });
    var ordered = extras.filter(function (e) { return e.state === "ordered"; });

    if (!extras.length) {
      list.appendChild(el("li", "extras-empty muted small",
        "Nothing else on the list."));
    }
    // No point offering to select all of one thing.
    if (need.length > 1) list.appendChild(groupHead("Still needed", need, false));
    need.forEach(function (extra) { list.appendChild(extraRow(extra, false)); });

    /* Grouped by the day they were ordered, because that is what an order is:
       one trip to one website, arriving in one box on one day. Each group takes
       its own select-all; they share a scope, so two orders arriving together
       can be ticked off in one go. */
    var batches = [];
    var byDay = {};
    ordered.forEach(function (extra) {
      var day = extra.orderedAt || "";
      if (!byDay[day]) { byDay[day] = []; batches.push(day); }
      byDay[day].push(extra);
    });

    batches.forEach(function (day) {
      var items = byDay[day];
      list.appendChild(groupHead(day ? "Ordered " + prettyDate(day) : "Ordered",
        items, true));
      items.forEach(function (extra) { list.appendChild(extraRow(extra, true)); });
    });

    renderExtraBar();

    /* The whole card goes quiet offline: writes are refused up front, and a
       form that can't be submitted is worse than one that isn't there. */
    var offline = !!state.offline;
    $("extras-item").disabled = offline;
    $("extras-form").querySelector("button").disabled = offline;
  }

  /* The bar only exists while something is ticked. It carries the pair of
     actions that make sense for the group being ticked in, and nothing else. */
  function renderExtraBar() {
    var bar = $("extras-bar");
    if (!bar) return;
    clear(bar);
    var ids = selectedExtras();
    bar.hidden = !ids.length;
    if (!ids.length) return;

    /* The count rides on the primary button rather than sitting beside it. At
       phone width the three buttons already need the whole row, so a separate
       "2 selected" had nowhere to go and spilled underneath them - and on a bar
       stuck to the bottom of the screen, a second row costs list you can see. */
    function action(label, cls, fn) {
      var button = el("button", "btn " + cls, label);
      button.type = "button";
      button.onclick = function () {
        Array.prototype.forEach.call(bar.querySelectorAll("button"),
          function (b) { b.disabled = true; });
        fn(ids);
      };
      bar.appendChild(button);
    }

    /* Only on the action that does the thing. Putting it on both reads like two
       different numbers, and neither would fit. */
    var count = " (" + ids.length + ")";

    if (extraSel.scope === "ordered") {
      action("Arrived" + count, "", doneExtras);
      /* Substitutions and things that were out of stock. Straight back onto
         the list, because you still need them - which is the whole reason for
         keeping ordered things visible rather than deleting them on trust. */
      action("Didn't arrive", "ghost", function (list) {
        setExtraState(list, "need");
      });
    } else {
      action("Got it" + count, "", doneExtras);
      action("Ordered", "ghost", function (list) {
        setExtraState(list, "ordered");
      });
    }

    var cancel = el("button", "btn ghost small", "Cancel");
    cancel.type = "button";
    cancel.onclick = function () { clearExtraSel(); renderExtras(); };
    bar.appendChild(cancel);
  }

  function extrasError(message) {
    var box = $("extras-error");
    box.textContent = message || "";
    box.hidden = !message;
  }

  /* Every one of these takes the whole list back from the server rather than
     patching what's on screen. It is a short list and one round trip either
     way, and with two phones in this kitchen the file is the only thing that
     knows what the list actually says. */
  function applyExtras(extras) {
    state.extras = extras || [];
    clearExtraSel();
    extrasError("");
    renderExtras();
  }

  function addExtra(text) {
    return api("POST", "/api/extras", { item: text })
      .then(function (added) {
        /* Replaced rather than appended: typing something already on the list
           adds to the one that's there, and the answer is that same row with a
           bigger number on it. */
        var kept = extrasList().filter(function (e) { return e.id !== added.id; });
        state.extras = kept.concat([added]);
        /* Remembered here as well as on the server, so it is suggested for
           the rest of this sitting without re-fetching the list. */
        var known = state.knownExtras || [];
        var seen = known.some(function (name) {
          return name.toLowerCase() === added.item.toLowerCase();
        });
        state.knownExtras = seen ? known : [added.item].concat(known);
        extrasError("");
        renderExtras();
      })
      .catch(function (err) { extrasError(err.message); });
  }

  function doneExtras(ids) {
    return api("POST", "/api/extras/done", { ids: ids })
      .then(function (res) { applyExtras(res.extras); })
      .catch(function (err) { extrasError(err.message); renderExtras(); });
  }

  function setExtraState(ids, next) {
    return api("POST", "/api/extras/state", { ids: ids, state: next })
      .then(function (res) { applyExtras(res.extras); })
      .catch(function (err) { extrasError(err.message); renderExtras(); });
  }

  /* Whole ones for countable things, sensible jumps for weights: nobody wants
     to press + four hundred times to get from 100g to 500g. */
  function stepExtra(extra, direction) {
    var unit = extra.unit || "each";
    var step = 1;
    if (unit === "g" || unit === "ml") step = (extra.qty || 1) >= 200 ? 50 : 10;
    if (unit === "tsp" || unit === "tbsp") step = 0.5;
    var qty = Math.round(((extra.qty || 1) + step * direction) * 100) / 100;
    return api("POST", "/api/extras/qty", { id: extra.id, qty: qty })
      .then(function (res) { applyExtras(res.extras); })
      .catch(function (err) { extrasError(err.message); renderExtras(); });
  }

  /* ---- taking the list to the shop ----

     There is no way to write into Google Keep from a web page. Its API is
     Workspace-only, gated behind an admin enabling domain-wide delegation, and
     personal gmail accounts can't use it at all. A downloaded file doesn't
     import into Keep either.

     What does work is the share sheet: navigator.share hands plain text to
     Android's ACTION_SEND, where Keep is registered as a text target. It
     arrives as a text note, which Keep turns into a checklist on request.
     So: share at home on the wifi, then Keep is readable in the shop with the
     server long out of reach. */

  /* Flat, one item per line and nothing else, because Keep's "Show checkboxes"
     makes every line tickable - a "TO BUY" heading would become an item to
     buy. Cupboard staples aren't labelled; they just come last, which is the
     only grouping a flat list can carry. */
  function shoppingText(list) {
    var lines = [];
    function add(it) { lines.push((it.text ? it.text + " " : "") + it.item); }
    /* First, as they are on the page: nothing else on the list will remind you
       that the baking paper ran out. Anything already ordered is left off -
       this is the list for the shop you are walking into, and a delivery
       that's on its way is not something to put in a trolley. */
    extrasList().forEach(function (e) {
      if (e.state === "ordered") return;
      var qty = extraQty(e);
      lines.push(qty ? e.item + " (" + qty + ")" : e.item);
    });
    (list.items || []).forEach(add);
    (list.staples || []).forEach(add);
    /* No ingredients on file, so nothing above covers these. The line has to
       explain itself - there is no heading to do it. */
    (list.missing || []).forEach(function (m) {
      lines.push("Also buy for: " + m.meal + " (" + m.day + ", " +
        m.eaters + (m.eaters === 1 ? " person" : " people") + ")");
    });
    return lines.join("\n");
  }

  function shareShoppingList() {
    var list = state.shopList;
    if (!list) return;
    var body = shoppingText(list);
    if (!body) { toast("Nothing on the list to share"); return; }
    /* The week goes in the title, which Chrome passes as the intent's
       EXTRA_SUBJECT for Keep to use as the note's heading - that keeps it off
       the checklist. The fallbacks have no title to put it in, so they put it
       on the first line instead. */
    var heading = "Shopping - " + weekRange(state.shopWeek || state.thisWeek);

    if (navigator.share) {
      navigator.share({ title: heading, text: body }).catch(function (err) {
        // Dismissing the sheet is an AbortError, and isn't worth a word.
        if (!err || err.name !== "AbortError") copyShoppingList(heading, body);
      });
      return;
    }
    copyShoppingList(heading, body);
  }

  /* Desktop has no share sheet. The clipboard is the next best thing, and a
     downloaded file is the last resort when that is blocked too. */
  function copyShoppingList(heading, body) {
    var text = heading + "\n" + body;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast("Copied - paste it into Keep");
      }).catch(function () { downloadShoppingList(heading, text); });
      return;
    }
    downloadShoppingList(heading, text);
  }

  function downloadShoppingList(heading, text) {
    var url;
    try {
      url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      var a = el("a");
      a.href = url;
      a.download = heading.replace(/[^a-z0-9]+/gi, "-").toLowerCase() + ".txt";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      toast("Shopping list downloaded");
    } catch (e) {
      toast("Couldn't share the list on this device");
    }
    if (url) setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }

  /* The button is only worth offering once there is something to send. */
  function updateShareBtn() {
    var btn = $("s-share");
    var note = $("s-share-note");
    if (!btn) return;
    var has = !!(state.shopList && shoppingText(state.shopList));
    btn.disabled = !has;
    btn.textContent = navigator.share ? "Share list" : "Copy list";
    if (note) {
      note.textContent = !has ? ""
        : navigator.share ? "Send it to Google Keep to read in the shop."
                          : "Copies the list so you can paste it into Keep.";
    }
  }

  function shoppingSection(title, items, muted) {
    var wrap = el("section", "shop-section" + (muted ? " cupboard" : ""));
    var head = el("h2");
    head.appendChild(document.createTextNode(title));
    head.appendChild(el("span", "count", " (" + items.length + ")"));
    wrap.appendChild(head);

    var ul = el("ul", "shop-list");
    items.forEach(function (it) {
      var li = el("li");
      li.appendChild(el("span", "shop-qty", it.text));
      li.appendChild(el("span", "shop-item", it.item));
      if (it.meals.length > 1) {
        li.appendChild(el("span", "shop-from", it.meals.length + " meals"));
      }
      // The exact figure sits in the tooltip rather than cluttering the line.
      if (it.rounded) {
        li.title = "Exactly " + it.exact + " " + it.unit + ", rounded up";
      }
      if (it.meals.length) {
        li.title = (li.title ? li.title + " - " : "") + "for " + it.meals.join(", ");
      }
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    return wrap;
  }

  // ------------------------------------------------------------- meals

  /* What the house has made of each meal, gathered from every week still on
     file. Worked out here rather than stored on the meal, because a rating
     belongs to the night it was eaten: the same recipe rated twice is two
     opinions, and a week deleted takes its opinions with it.

     Everything is keyed by meal id and rebuilt on each render. It is a few
     hundred numbers in the largest household this app is for; caching it would
     only be somewhere else for the figures to go stale. */
  function ratingStats(who) {
    var by = {};
    // `who` is the set of people whose opinion is being asked for. Empty means
    // the whole house - see whoseTaste().
    var only = null;
    if (who && who.length) {
      only = {};
      who.forEach(function (pid) { only[pid] = true; });
    }
    function slot(id) {
      if (!by[id]) by[id] = { all: [], people: {} };
      return by[id];
    }
    Object.keys(state.weeks || {}).forEach(function (key) {
      var week = state.weeks[key] || {};
      DAYS.forEach(function (day) {
        var cell = week[day] || {};
        (cell.sittings || []).forEach(function (s) {
          if (!s.mealId || !s.ratings) return;
          Object.keys(s.ratings).forEach(function (pid) {
            var stars = s.ratings[pid];
            if (!stars || !personById(pid)) return;
            if (only && !only[pid]) return;
            var entry = slot(s.mealId);
            entry.all.push(stars);
            (entry.people[pid] = entry.people[pid] || []).push(stars);
          });
        });
      });
    });

    Object.keys(by).forEach(function (id) {
      var entry = by[id];
      entry.count = entry.all.length;
      entry.mean = mean(entry.all);
      /* "Divisive" is the spread between people, not between nights. Someone
         who rates the same meal 3 then 5 is having an off week; two people who
         rate it 1 and 5 disagree about the meal, which is the thing worth
         surfacing. So each person is reduced to their own average first, and
         the spread is taken across those. */
      var perPerson = Object.keys(entry.people).map(function (pid) {
        return mean(entry.people[pid]);
      });
      entry.spread = perPerson.length > 1
        ? Math.max.apply(null, perPerson) - Math.min.apply(null, perPerson)
        : 0;
      entry.raters = perPerson.length;
    });
    return by;
  }

  function mean(list) {
    if (!list.length) return 0;
    var total = 0;
    for (var i = 0; i < list.length; i++) total += list[i];
    return total / list.length;
  }

  function personMean(stats, mealId, pid) {
    var entry = stats[mealId];
    var list = entry && entry.people[pid];
    return list && list.length ? mean(list) : null;
  }

  /* The sorts, each a comparison over the stats above.

     `rank` returns the number a meal is sorted by, or null when it has no
     answer to the question - a meal nobody has rated is not the worst meal in
     the house, it is an unknown, and unknowns go to the bottom in every
     direction rather than winning "lowest rated" by default. */
  var MEAL_SORTS = {
    az: { label: "A–Z", pill: "A–Z" },
    best: {
      label: "Highest rated", pill: "Highest",
      rank: function (m, st) { return st[m.id] ? st[m.id].mean : null; },
      dir: -1
    },
    worst: {
      label: "Lowest rated", pill: "Lowest",
      rank: function (m, st) { return st[m.id] ? st[m.id].mean : null; },
      dir: 1
    },
    divisive: {
      label: "Most divisive", pill: "Divisive",
      rank: function (m, st) {
        var e = st[m.id];
        return e && e.raters > 1 ? e.spread : null;
      },
      dir: -1
    },
    unrated: {
      label: "Not yet rated", pill: "Unrated",
      rank: function (m, st) { return st[m.id] ? null : 0; },
      dir: 1,
      only: true      // a filter, not an order: rated meals drop out entirely
    }
  };

  var SORT_ORDER = ["az", "best", "worst", "divisive", "unrated"];

  function mealSort() {
    return MEAL_SORTS.hasOwnProperty(state.mealSort) ? state.mealSort : "az";
  }

  /* Whose ratings the library is being asked about. Empty means everybody,
     which is both the starting state and where deselecting the last name lands
     - a library ordered by nobody's opinion would be an empty screen with no
     way to tell what you had done. Anyone who has since left the household
     drops out here rather than being cleaned up on delete: the selection is a
     per-device preference, not part of the plan. */
  function whoseTaste() {
    return (state.ratedBy || []).filter(personById);
  }

  function sortMeals(meals, stats) {
    var how = MEAL_SORTS[mealSort()];
    // A–Z is the default and the only order that ignores the ratings entirely.
    if (!how.rank) {
      return meals.slice().sort(function (a, b) {
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
      });
    }

    var ranked = meals.map(function (m, i) {
      return { meal: m, at: i, rank: how.rank(m, stats) };
    });
    if (how.only) ranked = ranked.filter(function (r) { return r.rank !== null; });

    ranked.sort(function (a, b) {
      // Nothing to rank on goes last whichever way round the sort is.
      if (a.rank === null && b.rank === null) return a.at - b.at;
      if (a.rank === null) return 1;
      if (b.rank === null) return -1;
      if (a.rank !== b.rank) return (a.rank - b.rank) * how.dir;
      return a.at - b.at;     // a tie keeps the library's own order
    });
    return ranked.map(function (r) { return r.meal; });
  }

  /* Filled stars up to the average, with the one it lands in the middle of
     faded rather than drawn as a half-star glyph: ⯨ and its neighbours are
     missing from enough system fonts to come out as a box, and a row of boxes
     on a meal card is worse than a rounder number. The figure is printed next
     to it for anyone who wants the rest. */
  function starRow(value) {
    var row = el("span", "stars");
    for (var n = 1; n <= 5; n++) {
      var full = value >= n - 0.25;
      var part = !full && value >= n - 0.75;
      row.appendChild(el("span",
        "star" + (full ? " on" : (part ? " on half" : "")),
        full || part ? "★" : "☆"));
    }
    return row;
  }

  /* The rating block on a meal card: the average, then who thought what.

     The average is over whoever is selected, not the whole house, so the
     figure on the card agrees with the order the card is sitting in - a meal
     at the top of "highest rated by Pete, Jules and Han" showing 2.8 because
     three other people can't stand it is a card arguing with its own list. The
     people who aren't being asked keep their pill, greyed: what they thought
     is still worth knowing, it just isn't what the list is about. */
  function ratingBlock(meal, stats, asked) {
    var entry = stats[meal.id];
    var subset = asked.length > 0;
    if (!entry || !entry.count) {
      return el("div", "macro-none",
        subset ? "Not rated by " + nameList(asked) : "Not rated yet");
    }
    var wrap = el("div", "rating-block");
    var top = el("div", "rating-mean");
    top.appendChild(starRow(entry.mean));
    top.appendChild(el("span", "rating-figure", round(entry.mean).toFixed(1)));
    top.appendChild(el("span", "rating-count",
      subset ? "· from " + nameList(asked)
             : "· " + entry.count + (entry.count === 1 ? " rating" : " ratings")));
    if (entry.raters > 1 && entry.spread >= 2) {
      top.appendChild(el("span", "rating-split", "· split"));
    }
    wrap.appendChild(top);

    /* Every rating on file, whoever gave it - so the greyed pills need their
       own pass over the data rather than the filtered stats above. */
    var everyone = stats.$all || stats;
    var who = el("div", "rating-people");
    household().forEach(function (p) {
      var avg = personMean(everyone, meal.id, p.id);
      if (avg === null) return;
      var asked_ = !subset || asked.indexOf(p.id) !== -1;
      var pill = el("span", "rating-pill" + (asked_ ? "" : " aside"));
      if (asked_) paint(pill, p.color);
      pill.appendChild(el("span", null, p.name));
      pill.appendChild(el("span", "rating-pill-n", "★" + round(avg).toFixed(1)));
      pill.title = p.name + " averages " + round(avg).toFixed(1) +
        " over " + everyone[meal.id].people[p.id].length + " of these";
      who.appendChild(pill);
    });
    if (who.childNodes.length) wrap.appendChild(who);
    return wrap;
  }

  function nameList(ids) {
    var names = ids.map(function (id) {
      var p = personById(id);
      return p ? p.name : null;
    }).filter(Boolean);
    if (names.length <= 2) return names.join(" and ");
    return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
  }

  // ------------------------------------------- ordering the meal library

  /* One button that reads back what the list is doing - "Highest · Pete,
     Jules +1" - and opens two rows of chips underneath it. A dropdown was the
     obvious control and the wrong one: it can only hold one choice, so asking
     for the meals three of six people like meant six entries in a list that
     grew with the household and still couldn't combine two of them. */
  function sortSummary() {
    var how = MEAL_SORTS[mealSort()];
    var asked = whoseTaste();
    if (!asked.length || !how.rank) return how.pill;
    var names = asked.map(function (id) { return personById(id).name; });
    var shown = names.slice(0, 2).join(", ");
    if (names.length > 2) shown += " +" + (names.length - 2);
    return how.pill + " · " + shown;
  }

  function renderSortControl() {
    var btn = $("meal-sort-btn");
    if (!btn) return;
    clear(btn);
    btn.appendChild(el("span", "sort-btn-icon", "⇅"));
    btn.appendChild(el("span", null, sortSummary()));
    btn.classList.toggle("set", mealSort() !== "az" || whoseTaste().length > 0);
    btn.setAttribute("aria-expanded", state.sortOpen ? "true" : "false");
    $("meal-sort-panel").hidden = !state.sortOpen;
    if (!state.sortOpen) return;

    var asked = whoseTaste();
    var people = $("sort-people");
    clear(people);
    household().forEach(function (p) {
      var on = asked.indexOf(p.id) !== -1;
      var chip = el("button", "sort-chip person" + (on ? " on" : ""), p.name);
      chip.type = "button";
      chip.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) {
        paint(chip, p.color);
        chip.style.borderColor = p.color || DEFAULT_COLOR;
      } else {
        /* Outlined, but the name stays in the page's own ink. It used to be
           written in the person's colour, which only worked while the palette
           was ten mid-tones - a yellow name on a white card is not a name, and
           on the dark theme the deep ones disappear the same way. The border
           carries the colour, and it carries it against a card either theme
           keeps a contrast against. */
        chip.style.borderColor = p.color || DEFAULT_COLOR;
      }
      chip.onclick = function () {
        var next = asked.filter(function (id) { return id !== p.id; });
        if (!on) next.push(p.id);
        // All six selected is the same question as none: the whole house.
        setTaste(next.length === household().length ? [] : next);
      };
      people.appendChild(chip);
    });
    var all = el("span", "sort-note",
      asked.length ? "" : "Everyone - tap a name to narrow it down");
    people.appendChild(all);

    var orders = $("sort-orders");
    clear(orders);
    SORT_ORDER.forEach(function (id) {
      var on = mealSort() === id;
      var pill = el("button", "sort-chip" + (on ? " on" : ""), MEAL_SORTS[id].pill);
      pill.type = "button";
      pill.setAttribute("aria-pressed", on ? "true" : "false");
      pill.title = MEAL_SORTS[id].label;
      pill.onclick = function () {
        state.mealSort = id;
        store("mealSort", id);
        renderMeals();
      };
      orders.appendChild(pill);
    });
  }

  function setTaste(ids) {
    state.ratedBy = ids;
    store("ratedBy", ids.join(","));
    renderMeals();
  }

  function renderMeals() {
    $("meal-count").textContent = state.meals.length ? "(" + state.meals.length + ")" : "";
    var list = $("meal-list");
    clear(list);
    renderSortControl();

    /* Two passes over the same ratings: `stats` is what the list is ordered
       and averaged by, `$all` is everybody, which the cards need for the greyed
       pills of the people not being asked. */
    var asked = whoseTaste();
    var stats = ratingStats(asked);
    if (asked.length) stats.$all = ratingStats([]);

    var filter = state.mealFilter.toLowerCase();
    var shown = state.meals.filter(function (m) {
      if (!filter) return true;
      return (m.name + " " + (m.tags || []).join(" ") + " " + (m.notes || ""))
        .toLowerCase().indexOf(filter) !== -1;
    });
    shown = sortMeals(shown, stats);

    if (shown.length === 0) {
      list.appendChild(el("div", "empty-state",
        !state.meals.length ? "No meals saved yet. Add one above."
          : mealSort() !== "unrated" ? "No meals match that search."
          : asked.length ? nameList(asked) + " have rated everything that matches."
          : "Everything that matches has been rated."));
      return;
    }

    shown.forEach(function (m) {
      var card = el("div", "meal-card");
      /* Built into a detached front face first: if the meal has ingredients
         it becomes the front of a flip card, and if not it is emptied straight
         into the card, exactly as before. */
      var front = el("div");
      var photo = null;
      if (m.image) {
        var thumb = el("img", "meal-thumb");
        thumb.src = m.image;
        thumb.alt = "";
        thumb.loading = "lazy";
        thumb.onerror = function () { thumb.parentNode && thumb.parentNode.removeChild(thumb); };
        front.appendChild(thumb);
        photo = thumb;
      }
      /* The title carries the flip, not the photo: an <img> can't hold the
         hint badge, and a broken image link removes itself. The photo still
         turns the card over when it is there. */
      var heading = el("h3", null, m.name);
      front.appendChild(heading);
      (m.tags || []).forEach(function (t) { front.appendChild(el("span", "tag", t)); });
      var ready = m.ingredients && m.ingredients.length && m.serves;
      var badge = el("span", "shop-badge" + (ready ? " ready" : ""),
        ready ? "Shopping ready" : "No ingredients");
      badge.title = ready
        ? m.ingredients.length + " ingredients, serves " + m.serves
        : (!m.ingredients || !m.ingredients.length
            ? "Add ingredients so this meal can go on the shopping list"
            : "Set how many this recipe serves");
      front.appendChild(badge);

      if (m.macros) {
        front.appendChild(macroStrip(m.macros, 1));
      } else {
        front.appendChild(el("div", "macro-none", "No nutrition info yet"));
      }
      front.appendChild(ratingBlock(m, stats, asked));
      if (m.notes) front.appendChild(el("p", null, m.notes));
      if (hasLink(m)) front.appendChild(recipeLink(m));
      var actions = el("div", "actions");

      /* Browsing the library is where you decide you fancy something, so the
         date can be picked here rather than going to the planner, finding the
         day and hunting the meal back out of a dropdown. The row below stays
         out of the way until asked for - every card carrying an open date
         field would drown the list it belongs to. */
      var addTo = el("button", "icon-btn", "Add to date");
      addTo.type = "button";
      addTo.setAttribute("aria-expanded", "false");

      var pick = el("div", "quick-add");
      pick.hidden = true;
      var when = el("input");
      when.type = "date";
      when.value = state.today;
      /* A year either side. Not a restriction anyone will meet on purpose - it
         is there so a slipped keystroke lands on a date you can see is wrong
         rather than silently planning a meal for the year 0202. */
      when.min = addDays(state.today, -365);
      when.max = addDays(state.today, 365);
      when.setAttribute("aria-label", "Date to add " + m.name + " to");
      when.onchange = function () {
        if (!when.value) return;
        pick.hidden = true;
        addTo.setAttribute("aria-expanded", "false");
        quickAdd(m, when.value);
      };
      pick.appendChild(el("span", "quick-add-label", "Add to"));
      pick.appendChild(when);

      addTo.onclick = function () {
        var show = pick.hidden;
        pick.hidden = !show;
        addTo.setAttribute("aria-expanded", show ? "true" : "false");
        if (!show) return;
        when.value = state.today;
        /* Open the calendar rather than leaving a field to be tapped a second
           time. Not everywhere has showPicker, and it throws unless it can see
           the tap that led here, so focus is the fallback. */
        try {
          if (when.showPicker) when.showPicker();
          else when.focus();
        } catch (e) { when.focus(); }
      };

      var edit = el("button", "icon-btn", "Edit");
      edit.onclick = function () { startEditMeal(m); };
      var del = el("button", "icon-btn danger", "Delete");
      del.onclick = function () {
        if (!confirm('Delete "' + m.name + '" from the library?')) return;
        api("DELETE", "/api/meals/" + m.id)
          .then(refresh).then(function () { toast("Meal deleted"); }).catch(fail);
      };
      actions.appendChild(addTo);
      actions.appendChild(edit);
      actions.appendChild(del);
      front.appendChild(actions);
      front.appendChild(pick);

      /* "Shopping ready" is exactly the condition for having something to show
         on the back: ingredients, and a serves count to scale them by. */
      var lines = ready ? ingredientLines(m, m.serves) : [];
      if (lines.length) {
        var back = ingredientsFace(lines,
          m.name + " ingredients, serves " + m.serves);
        card.appendChild(makeFlip(front, back, heading, photo ? [photo] : []));
      } else {
        while (front.firstChild) card.appendChild(front.firstChild);
      }
      list.appendChild(card);
    });
  }

  /* Shrink the photo in the browser before uploading: phone cameras produce
     4-12MB files, and a thumbnail on a meal card needs none of that. */
  function shrinkImage(file, maxSide) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () { reject(new Error("That photo couldn't be read.")); };
      reader.onload = function () {
        var img = new Image();
        img.onerror = function () { reject(new Error("That file isn't an image.")); };
        img.onload = function () {
          var scale = Math.min(1, maxSide / Math.max(img.width, img.height));
          var canvas = document.createElement("canvas");
          canvas.width = Math.round(img.width * scale);
          canvas.height = Math.round(img.height * scale);
          canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
          try {
            resolve(canvas.toDataURL("image/jpeg", 0.82));
          } catch (e) {
            reject(new Error("That photo couldn't be processed."));
          }
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  /* The add-a-meal form is put away by default so the page opens on the search
     box and the library - most visits are for inspiration, not for adding. The
     + button by the heading is what brings it out, and turns into a × while it
     is open, which is the same button saying the same thing both ways round. */
  function openAddPanel() {
    $("add-panel").hidden = false;
    $("add-panel").classList.add("open");
    $("add-panel-toggle").classList.add("on");
    $("add-panel-toggle").setAttribute("aria-expanded", "true");
    $("add-panel-toggle").title = "Close";
  }
  function closeAddPanel() {
    $("add-panel").hidden = true;
    $("add-panel").classList.remove("open");
    $("add-panel-toggle").classList.remove("on");
    $("add-panel-toggle").setAttribute("aria-expanded", "false");
    $("add-panel-toggle").title = "Add a meal";
  }

  function startEditMeal(meal) {
    state.editingMealId = meal.id;
    openAddPanel();
    $("meal-form-title").hidden = false;   // shows the "Edit meal" cue
    $("meal-submit").textContent = "Save changes";
    $("meal-cancel").hidden = false;
    $("meal-name").value = meal.name;
    $("meal-tags").value = (meal.tags || []).join(", ");
    linksIntoForm(linksOf(meal));
    ingredientsIntoForm(meal.ingredients, meal.serves);
    imageIntoForm(meal);
    $("meal-notes").value = meal.notes || "";
    macrosIntoForm(meal.macros);
    $("meal-name").focus();
    window.scrollTo(0, 0);
  }

  function resetMealForm() {
    state.editingMealId = null;
    $("meal-form").reset();
    $("meal-form-title").hidden = true;    // the "Edit meal" cue only shows mid-edit
    $("meal-submit").textContent = "Add meal";
    // Cancel stays visible in the Add-a-meal state too, where it clears the
    // fields ready to start again (in edit mode it cancels the edit).
    $("meal-cancel").hidden = false;
    $("meal-error").hidden = true;
    linksIntoForm([]);
    ingredientsIntoForm([], null);
    imageIntoForm(null);
    macrosIntoForm(null);
  }

  // ------------------------------------------------------------ people

  // ----------------------------------------------------- kitchen display

  /* The Cast picker. The list of displays comes from Home Assistant, which the
     add-on asks on our behalf - the browser can't see Cast devices, and this
     app has no business holding a Home Assistant token.

     Fetched when the Settings tab is opened rather than with /api/data: it is
     a page most people see once, to choose a screen, and never again. */
  function loadCast(refreshDevices) {
    return api("GET", "/api/cast" + (refreshDevices ? "?refresh=1" : ""))
      .then(function (info) {
        state.cast = info;
        renderCast();
        return info;
      })
      .catch(function () {
        /* Offline, or an older add-on that has no such endpoint. Either way
           there is nothing useful to show and nothing worth saying. */
        state.cast = null;
        renderCast();
      });
  }

  function castTargets() {
    return (state.cast && state.cast.targets) || [];
  }

  /* Checkboxes rather than a dropdown, because the week can go on more than one
     screen: the kitchen and a bedroom are a perfectly ordinary pair. */
  function castRow(device, chosen) {
    var row = el("label", "display-check cast-row" + (device.gone ? " is-gone" : ""));
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = chosen.indexOf(device.entityId) !== -1;
    box.disabled = !!(state.cast && state.cast.pinned) || state.offline;
    box.onchange = function () {
      var next = castTargets().filter(function (id) { return id !== device.entityId; });
      if (box.checked) next.push(device.entityId);
      saveCast(next);
    };
    row.appendChild(box);

    var text = el("span", null);
    text.appendChild(el("span", "cast-name", device.name));
    var hint = castHint(device);
    if (hint) text.appendChild(el("span", "cast-hint", hint));
    /* The entity id under the name. Two Cast devices can perfectly well be
       called the same thing, and after one has been taken out of the Google
       Home and put back, two of them usually are - Home Assistant registers the
       new one alongside the old, and the name is the half that can't tell them
       apart. */
    if (device.entityId && device.entityId !== device.name) {
      text.appendChild(el("span", "cast-id", device.entityId));
    }
    row.appendChild(text);
    return row;
  }

  function castHint(device) {
    /* "Removed" and "not answering" are worth separating, because only one of
       them is going to get better on its own. */
    if (device.gone) return "removed from Home Assistant";
    if (device.missing) return "not answering";
    if (!device.video) return device.model ? device.model + " — no screen" : "no screen";
    if (device.state === "unavailable") return "off";
    if (device.showing) return "showing " + device.showing;
    return "";
  }

  function renderCast() {
    var card = $("cast-card");
    var info = state.cast;
    /* The bell's speaker list comes out of this same answer, and the two
       requests land in whichever order the network decides. Redrawn from here
       so a device list that arrives after the bell's settings doesn't leave
       that card saying "Looking…" for good. */
    renderBell();
    card.hidden = !(info && info.available);
    if (card.hidden) return;

    var chosen = castTargets();
    var all = (info.devices || []).slice();
    var gone = info.gone || [];

    /* A display that is chosen but not in the list - switched off at the wall,
       or Home Assistant restarting - is still shown as chosen. Dropping it
       would make un-ticking it the only way to fix something that isn't
       broken.

       The add-on does this itself now, and does it better: it keeps the name
       and model the device last had, so the row reads like the one it replaces
       rather than like a bare entity id. This is the same thing done badly, for
       an older add-on that doesn't. */
    chosen.forEach(function (id) {
      var known = all.some(function (d) { return d.entityId === id; });
      if (!known) {
        all.push({ entityId: id, name: id, video: true, missing: true,
                   gone: gone.indexOf(id) !== -1 });
      }
    });

    var showAll = !!$("cast-show-all").checked;
    var screens = all.filter(function (d) { return d.video; });
    var rest = all.filter(function (d) { return !d.video; });
    /* Anything already chosen stays on screen whatever the filter says - being
       unable to see what you have turned on is worse than a longer list. */
    var listed = showAll ? all : screens.concat(rest.filter(function (d) {
      return chosen.indexOf(d.entityId) !== -1;
    }));

    var list = $("cast-list");
    clear(list);
    if (!listed.length) {
      list.appendChild(el("p", "muted small", info.checked
        ? (rest.length
            ? "No Cast screens — only speakers, which can't show a web page."
            : "Home Assistant can't see any Cast devices.")
        : "Looking…"));
    }
    listed.forEach(function (device) { list.appendChild(castRow(device, chosen)); });

    var hidden = rest.length - (listed.length - screens.length);
    var toggle = $("cast-show-all").parentNode;
    toggle.hidden = rest.length === 0;
    toggle.lastChild.textContent = showAll
      ? "Showing everything Home Assistant can cast to"
      : "Also show " + hidden + " speaker" + (hidden === 1 ? "" : "s")
        + " and other devices without a screen";

    /* The casting hours are part of the shared display settings rather than of
       the Cast choice, so they only appear once those have loaded. They sit in
       this card anyway: they are about the screen being taken over, which is
       what someone is looking at this card to decide. */
    var look = state.display;
    $("cast-hours").hidden = !look;
    if (look) {
      $("cast-window").checked = !!look.castWindow;
      $("cast-window").disabled = state.offline;
      $("cast-window-when").hidden = !look.castWindow;
      $("cast-from").value = look.castFrom || "07:00";
      $("cast-to").value = look.castTo || "23:00";
    }

    /* Chosen displays Home Assistant doesn't have any more. Counted out of the
       "showing on N screens" line as well as called out below it: a house with
       one working Hub and one that was taken off the shelf last month has one
       screen, whatever the tick boxes say. */
    var lost = gone.filter(function (id) { return chosen.indexOf(id) !== -1; });
    var live = chosen.length - lost.length;

    var note = "";
    if (info.pinned) {
      note = "Set in the add-on's Configuration panel. Clear cast_device there "
           + "to choose them here instead.";
    } else if (live) {
      note = "Showing " + (info.url || "the kitchen display") + " on "
           + live + (live === 1 ? " screen." : " screens.");
      /* `open` is missing from an older add-on's answer, which had no hours and
         so was always open. */
      if (look && look.castWindow) {
        note += info.open === false
          ? " Nothing until " + look.castFrom + "."
          : " Until " + look.castTo + ", then the screen goes back to normal.";
      }
    }
    if (info.guessed) {
      /* The add-on couldn't get a list out of the Cast integration and swept
         every media player instead. Worth saying, because that list calls a
         Sonos a screen and someone is about to wonder why. */
      note += (note ? " " : "")
           + "Home Assistant's Cast integration didn't answer, so this is every "
           + "media player it has. Try Look for displays in a minute.";
    }
    $("cast-state").textContent = note;

    /* Kept out of cast-error: this is not a fault that will clear, and the only
       thing that ends it is letting them go, so it comes with the button that
       does. */
    var forget = $("cast-forget");
    $("cast-gone").textContent = lost.length
      ? (lost.length === 1 ? "One chosen display is" : lost.length + " chosen displays are")
        + " no longer in Home Assistant. A display taken out of the Google Home "
        + "and put back usually comes back under a new name — tick the new one, "
        + "then forget these."
      : "";
    $("cast-gone").hidden = !lost.length;
    forget.hidden = !lost.length || !!info.pinned;
    forget.disabled = state.offline;

    var error = $("cast-error");
    error.textContent = info.error || "";
    error.hidden = !info.error;
  }

  /* Drop every chosen display Home Assistant no longer has, leaving the rest of
     the choice alone. */
  function forgetGone() {
    var lost = (state.cast && state.cast.gone) || [];
    if (!lost.length) return;
    saveCast(castTargets().filter(function (id) { return lost.indexOf(id) === -1; }));
  }

  function saveCast(next) {
    var previous = state.cast;
    if (state.cast) state.cast = withPatch(state.cast, { targets: next });
    renderCast();                         // tick the box now, ask afterwards
    return api("POST", "/api/cast", { devices: next }).then(function (info) {
      state.cast = info;
      renderCast();
      toast(next.length
        ? "Casting the week to " + next.length + (next.length === 1 ? " screen" : " screens")
        : "Kitchen display off");
    }).catch(function (err) {
      state.cast = previous;
      renderCast();
      var box = $("cast-error");
      box.textContent = err.message;
      box.hidden = false;
    });
  }

  // ------------------------------------------------- kitchen display looks

  /* Which parts of the display can be turned off, in the order they read down
     the screen. The ids match the fields display.py validates - a name added
     here and not there is a checkbox that does nothing. */
  var DISPLAY_PARTS = [
    { id: "showCook", label: "Who's cooking" },
    { id: "showHeads", label: "How many they're cooking for" },
    { id: "showClock", label: "The clock" },
    { id: "showDate", label: "The date" },
    { id: "showPhotos", label: "Meal photos" },
    /* Not "the week": the strip is today and the five days after it, and it
       stopped being a calendar week long before it stopped being seven days
       long. The stored name is still showWeek, because renaming a settings
       field renames it in everybody's display.json for no gain. */
    { id: "showWeek", label: "Meals coming up" },
    { id: "showEmpty", label: "“Nothing planned”" },
    { id: "showShopping", label: "The shopping button" }
  ];

  function withPatch(base, patch) {
    var out = {}, key;
    for (key in (base || {})) if (base.hasOwnProperty(key)) out[key] = base[key];
    for (key in patch) if (patch.hasOwnProperty(key)) out[key] = patch[key];
    return out;
  }

  function loadDisplay() {
    return api("GET", "/api/display").then(function (settings) {
      state.display = settings;
      renderDisplay();
    }).catch(function () {
      state.display = null;
      renderDisplay();
    });
  }

  /* Every control sends the one field it changed and gets the whole lot back,
     so two phones on this page at once can't undo each other's work by posting
     a stale copy of everything. */
  function saveDisplay(patch) {
    var previous = state.display;
    state.display = withPatch(state.display, patch);   // draw it now
    renderDisplay();
    return api("POST", "/api/display", patch).then(function (settings) {
      state.display = settings;
      renderDisplay();
    }).catch(function (err) {
      state.display = previous;
      renderDisplay();
      var box = $("display-error");
      box.textContent = err.message;
      box.hidden = false;
    });
  }

  /* Dragging a slider fires a change per step. Sent on a short delay so a drag
     from 100 to 140 is one request at the end rather than nine on the way. */
  var displayTimer = null;
  function saveDisplaySoon(patch) {
    state.display = withPatch(state.display, patch);
    renderDisplay();
    if (displayTimer) clearTimeout(displayTimer);
    displayTimer = setTimeout(function () { saveDisplay(patch); }, 400);
  }

  function renderDisplay() {
    var card = $("display-card");
    var settings = state.display;
    card.hidden = !settings;
    /* The casting hours are stored with these but drawn in the Cast card, so
       the two are redrawn together and a change to one can't leave the other
       showing the settings as they were a moment ago. */
    renderCast();
    if (!settings) return;

    var accents = $("display-accents");
    clear(accents);
    ACCENTS.forEach(function (a) {
      var btn = el("button", "swatch" + (a.id === settings.accent ? " on" : ""));
      btn.type = "button";
      btn.dataset.swatch = a.id;
      btn.title = a.label;
      btn.setAttribute("aria-label", a.label);
      btn.setAttribute("aria-pressed", a.id === settings.accent ? "true" : "false");
      btn.onclick = function () { saveDisplay({ accent: a.id }); };
      accents.appendChild(btn);
    });

    var themes = $("display-themes");
    clear(themes);
    [{ id: "dark", label: "Dark" }, { id: "light", label: "Light" }].forEach(function (t) {
      var btn = el("button", "theme-opt" + (t.id === settings.theme ? " on" : ""), t.label);
      btn.type = "button";
      btn.setAttribute("aria-pressed", t.id === settings.theme ? "true" : "false");
      btn.onclick = function () { saveDisplay({ theme: t.id }); };
      themes.appendChild(btn);
    });

    $("display-scale").value = settings.scale;
    $("display-scale-out").textContent = settings.scale + "%";

    var toggles = $("display-toggles");
    clear(toggles);
    DISPLAY_PARTS.forEach(function (part) {
      var row = el("label", "display-check");
      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = !!settings[part.id];
      box.onchange = function () {
        var patch = {};
        patch[part.id] = box.checked;
        saveDisplay(patch);
      };
      row.appendChild(box);
      row.appendChild(el("span", null, part.label));
      toggles.appendChild(row);
    });

    var rollover = settings.rollover || "00:00";
    $("display-rollover").value = rollover;
    $("display-rollover-note").textContent = rollover === "00:00"
      ? "Midnight: the display follows the calendar, as it always has."
      : "From " + rollover + " the display shows tomorrow, labelled Tomorrow - "
        + "the big card, who's cooking and the meals coming up all move "
        + "on together. Only the display; the app still calls today today.";

    $("display-dim").checked = !!settings.dim;
    $("display-dim-when").hidden = !settings.dim;
    $("display-dim-from").value = settings.dimFrom;
    $("display-dim-to").value = settings.dimTo;
    $("display-dim-level").value = settings.dimLevel;
    $("display-dim-out").textContent = settings.dimLevel + "%";
  }

  function renderPeople() {
    var list = $("person-list");
    /* The picker is placed from a measurement of a disc in this list, and the
       rebuild below throws that disc away. Anything left pointing at it would
       be pointing at nothing. */
    closePalette();
    clear(list);
    if (state.people.length === 0) {
      list.appendChild(el("div", "empty-state", "No one added yet."));
      return;
    }
    /* The guest slot is pinned to the end and has no handle. It reads last on
       a week card - "Alex, Sam and 2 guests" - so a household order that could
       put it anywhere else would only be an order Settings and the week
       disagreed about. The server pins it too; this is the same rule drawn. */
    var movable = household();

    state.people.forEach(function (p, at) {
      var row = el("div", "person-row" + (p.guest ? " is-guest" : ""));
      row.dataset.id = p.id;
      /* A spacer on the guest's row rather than nothing, so the discs and
         names below it stay in the same column as the ones above. */
      row.appendChild(!p.guest && movable.length > 1
        ? dragHandle(p, at, movable.length)
        : el("span", "drag-spacer"));
      row.appendChild(colorDot(p));
      row.appendChild(el("span", "name", p.name));

      /* The guest slot is a fixture of the app rather than a member of the
         household: it cannot be renamed, removed or dragged, so it carries none
         of the buttons that would do those things. What it is is explained by
         where it turns up - a "+ 2 guests" chip beside the names on a meal -
         rather than by a caption under it here.

         It keeps its colour disc, because that chip has to be told apart from
         the names beside it like any other. */
      if (!p.guest) {
        var rename = el("button", "icon-btn", "Rename");
        rename.onclick = function () {
          var name = prompt("New name for " + p.name + ":", p.name);
          if (!name || !name.trim()) return;
          api("PUT", "/api/people/" + p.id, { name: name.trim() }).then(refresh).catch(fail);
        };
        var del = el("button", "icon-btn danger", "Remove");
        del.onclick = function () {
          if (!confirm("Remove " + p.name + " from the household? They will be taken off all planned meals.")) return;
          api("DELETE", "/api/people/" + p.id)
            .then(refresh).then(function () { toast("Removed"); }).catch(fail);
        };
        row.appendChild(rename);
        row.appendChild(del);
      }
      list.appendChild(row);
    });

    /* Dragging replaces this list, so the handle that was being held no longer
       exists. Put the focus back on the new one, or a keyboard moving somebody
       down three places would have to find them again after every press. */
    if (state.grabbed) {
      var back = list.querySelector('.person-row[data-id="' + state.grabbed +
                                    '"] .drag-handle');
      if (back) back.focus();
      state.grabbed = null;
    }
  }

  // ------------------------------------------- reordering the household
  //
  /* The grip is the standard way to say "this row can be moved", and it says it
     without a caption. It is also the whole hit area: the row itself stays
     inert, so a thumb resting on a name while scrolling Settings does not pick
     anybody up.

     The handle is a real button as well as a drag target. Arrow keys on it move
     the person one place, which is what makes this reachable from a keyboard
     and from a screen reader - dragging on its own would leave both with
     nothing at all. It is the same one-place move either way, through the same
     endpoint. */

  var drag = null;

  function gripShape() {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "grip");
    svg.setAttribute("viewBox", "0 0 10 16");
    svg.setAttribute("aria-hidden", "true");
    [[3, 3], [7, 3], [3, 8], [7, 8], [3, 13], [7, 13]].forEach(function (at) {
      var dot = document.createElementNS(ns, "circle");
      dot.setAttribute("cx", at[0]);
      dot.setAttribute("cy", at[1]);
      dot.setAttribute("r", "1.35");
      dot.setAttribute("fill", "currentColor");
      svg.appendChild(dot);
    });
    return svg;
  }

  function dragHandle(person, at, count) {
    var handle = el("button", "icon-btn drag-handle");
    handle.type = "button";
    handle.appendChild(gripShape());
    handle.setAttribute("aria-label",
      person.name + ", " + (at + 1) + " of " + count +
      ". Drag to reorder, or use the arrow keys.");
    handle.title = "Drag " + person.name + " to reorder";
    handle.onpointerdown = function (e) { startDrag(e, handle, person); };
    handle.onkeydown = function (e) {
      var delta = e.key === "ArrowUp" ? -1 : e.key === "ArrowDown" ? 1 : 0;
      if (!delta) return;
      e.preventDefault();
      movePerson(person, delta);
    };
    return handle;
  }

  function startDrag(e, handle, person) {
    if (state.offline || drag) return;
    if (e.button !== undefined && e.button !== 0) return;   // right-click

    var row = handle.parentNode;
    var list = row.parentNode;
    var rect = row.getBoundingClientRect();

    // Stops the browser reading the gesture as a scroll and taking it away
    // half way through. touch-action:none on the handle is the other half.
    e.preventDefault();
    if (handle.setPointerCapture) handle.setPointerCapture(e.pointerId);

    /* A gap the size of the row, left where the row will land. It is what the
       drop reads to work out the new order, so there is no separate model of
       "where things are" to get out of step with the screen. */
    var gap = el("div", "person-gap");
    gap.style.height = rect.height + "px";
    list.insertBefore(gap, row);

    row.classList.add("dragging");
    row.style.position = "fixed";
    row.style.left = rect.left + "px";
    row.style.top = rect.top + "px";
    row.style.width = rect.width + "px";

    drag = { handle: handle, row: row, list: list, gap: gap,
             hold: e.clientY - rect.top, moved: false, person: person };

    handle.onpointermove = onDrag;
    handle.onpointerup = dropDrag;
    handle.onpointercancel = abandonDrag;
    document.addEventListener("keydown", dragKey, true);
  }

  function onDrag(e) {
    if (!drag) return;
    drag.moved = true;
    drag.row.style.top = (e.clientY - drag.hold) + "px";
    placeGap(e.clientY);
    edgeScroll(e.clientY);
  }

  /* The gap goes wherever the pointer is, by midpoints: above a row while the
     pointer is in its top half, below it after that. */
  function placeGap(y) {
    var rows = Array.prototype.filter.call(drag.list.children, function (n) {
      return n !== drag.row && n.classList &&
             n.classList.contains("person-row");
    });
    var before = null;
    for (var i = 0; i < rows.length; i++) {
      var at = rows[i].getBoundingClientRect();
      if (y < at.top + at.height / 2) { before = rows[i]; break; }
    }
    // The guest slot keeps the end of the list whatever the pointer says.
    var guest = drag.list.querySelector(".person-row.is-guest");
    if (!before && guest) before = guest;
    if (before !== drag.gap.nextSibling) drag.list.insertBefore(drag.gap, before);
  }

  /* Dragging to a row that is off the top or bottom of the screen. The list
     lives on a page with several other cards on it, so on a phone the far end
     of a big household can easily be past the edge. */
  function edgeScroll(y) {
    var margin = 72, step = 0;
    if (y < margin) step = -Math.ceil((margin - y) / 5);
    else if (y > window.innerHeight - margin) {
      step = Math.ceil((y - (window.innerHeight - margin)) / 5);
    }
    if (step) window.scrollBy(0, step);
  }

  function dragKey(e) {
    if (e.key === "Escape" || e.key === "Esc") {
      e.stopPropagation();
      abandonDrag();
    }
  }

  function releaseDrag() {
    var held = drag;
    drag = null;
    document.removeEventListener("keydown", dragKey, true);
    held.handle.onpointermove = null;
    held.handle.onpointerup = null;
    held.handle.onpointercancel = null;
    held.row.classList.remove("dragging");
    held.row.removeAttribute("style");
    return held;
  }

  function dropDrag() {
    if (!drag) return;
    var held = releaseDrag();
    if (!held.moved) {
      // A tap on the grip rather than a drag. Nothing to save.
      if (held.gap.parentNode) held.gap.parentNode.removeChild(held.gap);
      return;
    }
    held.list.insertBefore(held.row, held.gap);
    held.gap.parentNode.removeChild(held.gap);

    var ids = Array.prototype.map.call(
      held.list.querySelectorAll(".person-row"),
      function (n) { return n.dataset.id; });
    state.grabbed = held.person.id;
    commitOrder(ids);
  }

  /* Escape, or the phone deciding the gesture belongs to something else. The
     list is redrawn from state rather than unpicked by hand, so whatever half
     of the move had happened on screen goes with it. */
  function abandonDrag() {
    if (!drag) return;
    var held = releaseDrag();
    if (held.gap.parentNode) held.gap.parentNode.removeChild(held.gap);
    state.grabbed = held.person.id;
    renderPeople();
  }

  function movePerson(person, delta) {
    var ids = state.people.map(function (p) { return p.id; });
    var at = ids.indexOf(person.id);
    var to = at + delta;
    // Not past the guest slot, and not off either end.
    var guest = guestPerson();
    var last = guest && ids[ids.length - 1] === guest.id
      ? ids.length - 2 : ids.length - 1;
    if (at < 0 || to < 0 || to > last) return;
    ids.splice(to, 0, ids.splice(at, 1)[0]);
    state.grabbed = person.id;
    commitOrder(ids);
  }

  /* The whole order goes to the server, not "move this one". The browser has
     the list already, and a whole list can't half-apply or land somewhere
     unintended because another phone reordered it a second ago - the server
     checks it still describes the same household and refuses it if not. */
  function commitOrder(ids) {
    return api("POST", "/api/people/order", { ids: ids })
      .then(refresh)
      .catch(function (err) { refresh().catch(function () {}); fail(err); });
  }

  // ------------------------------------------------ picking a person's colour
  //
  /* The disc beside a name is the colour that name is wearing everywhere else
     in the app, so it is also the obvious place to change it. Tapping it opens
     a grid of the palette; taking a colour somebody else has is not offered.

     Refusing the clash rather than warning about it is the point of the whole
     feature. Two people in the same colour makes every name chip on the week
     view ambiguous, and the app has no way to tell you which one you are
     looking at - so the picker simply has nothing there to press. */

  var paletteOpen = null;

  function wirePalette() {
    document.addEventListener("click", function () { closePalette(); });
    window.addEventListener("resize", closePalette);
    window.addEventListener("scroll", closePalette, true);
  }

  function closePalette() {
    if (!paletteOpen) return;
    if (paletteOpen.node.parentNode) {
      paletteOpen.node.parentNode.removeChild(paletteOpen.node);
    }
    paletteOpen.dot.classList.remove("picking");
    paletteOpen = null;
    document.removeEventListener("keydown", paletteKey, true);
  }

  function paletteKey(e) {
    if (e.key === "Escape" || e.key === "Esc") {
      e.stopPropagation();
      var dot = paletteOpen && paletteOpen.dot;
      closePalette();
      if (dot) dot.focus();
    }
  }

  /* A button when there is something to choose from, a plain disc when there
     isn't: offline, or an add-on from before the palette was sent with the
     data. A control that can only fail is worse than no control. */
  function colorDot(person) {
    var choosable = (state.palette || []).length > 0 && !state.offline;
    if (!choosable) {
      var flat = el("span", "person-dot");
      flat.style.background = person.color || DEFAULT_COLOR;
      return flat;
    }

    var dot = el("button", "person-dot dot-btn");
    dot.type = "button";
    dot.style.background = person.color || DEFAULT_COLOR;
    dot.setAttribute("aria-label", "Change " + person.name + "'s colour");
    dot.title = dot.getAttribute("aria-label");
    dot.onclick = function (e) {
      e.stopPropagation();
      openPalette(dot, person);
    };
    return dot;
  }

  function openPalette(dot, person) {
    var reopening = paletteOpen && paletteOpen.dot === dot;
    closePalette();
    if (reopening) return;

    // Who has what, so a taken swatch can say whose it is rather than just
    // refusing to be pressed.
    var owner = {};
    state.people.forEach(function (other) {
      if (other.id !== person.id && other.color) owner[other.color] = other.name;
    });

    var pop = el("div", "color-pop");
    pop.setAttribute("role", "group");
    pop.setAttribute("aria-label", "Colour for " + person.name);

    var grid = el("div", "color-grid");
    state.palette.forEach(function (color) {
      var taken = owner[color];
      var mine = color === person.color;
      var cell = el("button", "swatch-cell" +
        (mine ? " is-current" : "") + (taken ? " taken" : ""));
      cell.type = "button";
      cell.style.background = color;
      /* The tick on the current colour has to be legible on it, and half this
         palette is too bright for a white one. */
      cell.style.color = inkOn(color);
      if (taken) {
        cell.disabled = true;
        cell.setAttribute("aria-label", taken + "'s colour");
        cell.title = "Already " + taken + "'s colour";
      } else {
        cell.setAttribute("aria-label", mine
          ? person.name + "'s colour now" : "Use this colour");
        if (mine) cell.setAttribute("aria-pressed", "true");
        cell.onclick = function () { setPersonColor(person, color); };
      }
      grid.appendChild(cell);
    });
    pop.appendChild(grid);

    pop.addEventListener("click", function (e) { e.stopPropagation(); });
    document.body.appendChild(pop);
    dot.classList.add("picking");
    paletteOpen = { node: pop, dot: dot };
    placePalette(pop, dot);
    document.addEventListener("keydown", paletteKey, true);
  }

  /* Centred on the disc and clamped to the screen, above it if there is no room
     below. The grid is six swatches wide, which is wider than most of the rows
     it opens from, so the clamp is doing real work on a phone. */
  function placePalette(pop, dot) {
    var at = dot.getBoundingClientRect();
    var size = pop.getBoundingClientRect();
    var gap = 6;
    var up = window.innerHeight - at.bottom < size.height + gap &&
             at.top > size.height + gap;

    pop.style.top = (up ? at.top - size.height - gap : at.bottom + gap) + "px";
    var left = at.left + at.width / 2 - size.width / 2;
    pop.style.left =
      Math.max(8, Math.min(left, window.innerWidth - size.width - 8)) + "px";
    pop.style.visibility = "visible";
  }

  function setPersonColor(person, color) {
    if (color === person.color) { closePalette(); return; }
    closePalette();
    api("PUT", "/api/people/" + person.id, { color: color })
      .then(refresh)
      .then(function () { toast(person.name + "'s colour changed"); })
      /* A 409 lands here: another phone took the colour between this one
         drawing the grid and the tap. refresh() puts the true state back, so
         reopening the picker shows it greyed out. */
      .catch(function (err) { refresh().catch(function () {}); fail(err); });
  }

  // ---------------------------------------------------- dinner bell
  //
  /* The panel for the bell. The speakers come from the same list the Cast
     picker uses - Home Assistant knows about all of them and this app has no
     business holding a token of its own - but the choice is separate, because
     the screen the week goes on and the speakers dinner is called through are
     different things in most houses.

     Unlike the Cast picker, this one never filters. A speaker with no screen is
     precisely what most people want here, so the "also show speakers" toggle
     that card needs would be backwards. */

  function loadBell() {
    return api("GET", "/api/bell").then(function (info) {
      state.bell = info;
      renderBell();
      return info;
    }).catch(function () {
      /* Offline, or an add-on from before the bell existed. Either way the
         card has nothing to say and hides itself. */
      state.bell = null;
      renderBell();
    });
  }

  /* What the card is currently saying, held in state rather than written
     straight to the page.

     It has to be state because the outcome of pressing a button and the
     redraw that follows it are two different things: writing "nothing rang"
     into the element and then calling renderBell() - which is what every
     handler here does - put the card's own idea of itself straight back over
     the top, and the message vanished in the same tick it appeared. */
  function bellSay(message, isError) {
    state.bellNote = message ? { text: message, error: !!isError } : null;
    paintBellNote();
  }

  function paintBellNote() {
    /* With nothing to say of our own, fall back to whatever the server last
       reported - a speaker that failed on the previous ring is still worth
       mentioning when the tab is opened again. */
    var note = state.bellNote;
    if (!note && state.bell && state.bell.error) {
      note = { text: state.bell.error, error: true };
    }
    $("bell-state").textContent = note && !note.error ? note.text : "";
    var box = $("bell-error");
    box.textContent = note && note.error ? note.text : "";
    box.hidden = !(note && note.error);
  }

  function saveBell(patch) {
    var previous = state.bell;
    state.bell = withPatch(state.bell, patch);      // tick the box now
    renderBell();
    return api("POST", "/api/bell", patch).then(function (info) {
      state.bell = info;
      renderBell();
    }).catch(function (err) {
      state.bell = previous;
      renderBell();
      bellSay(err.message || "That didn't save.", true);
    });
  }

  function bellTargets() {
    return (state.bell && state.bell.devices) || [];
  }

  /* Every media player Home Assistant has, screens and speakers alike, plus
     anything already chosen that isn't in the list any more - the same
     courtesy the Cast picker extends, and for the same reason: un-ticking
     something you can no longer see is not a fix anybody can find. */
  function bellDevices() {
    var all = ((state.cast && state.cast.devices) || []).slice();
    bellTargets().forEach(function (id) {
      if (!all.some(function (d) { return d.entityId === id; })) {
        all.push({ entityId: id, name: id, missing: true });
      }
    });
    return all;
  }

  /* A speaker's friendly name for a message somebody has to read. Falls back
     to the entity id, which is at least unambiguous. */
  function bellName(entityId) {
    var found = bellDevices().filter(function (d) { return d.entityId === entityId; });
    return (found[0] && found[0].name) || entityId;
  }

  function bellRow(device, chosen) {
    var row = el("label", "display-check cast-row");
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = chosen.indexOf(device.entityId) !== -1;
    box.disabled = state.offline || state.bellBusy;
    box.onchange = function () {
      var next = bellTargets().filter(function (id) { return id !== device.entityId; });
      if (box.checked) next.push(device.entityId);
      saveBell({ devices: next });
    };
    row.appendChild(box);

    var text = el("span", null);
    text.appendChild(el("span", "cast-name", device.name));
    /* A different hint from the Cast picker's. "No screen" is a reason not to
       tick something there and a recommendation here, so the only things worth
       flagging are the ones that might not ring. */
    var hint = device.missing ? "not in Home Assistant"
             : device.state === "unavailable" ? "off" : "";
    if (hint) text.appendChild(el("span", "cast-hint", hint));
    if (device.entityId && device.entityId !== device.name) {
      text.appendChild(el("span", "cast-id", device.entityId));
    }
    row.appendChild(text);
    return row;
  }

  function renderBell() {
    var card = $("bell-card");
    var info = state.bell;
    card.hidden = !(info && info.available);
    if (card.hidden) return;

    var on = !!info.enabled;
    $("bell-enabled").checked = on;
    $("bell-enabled").disabled = state.offline || state.bellBusy;
    $("bell-body").hidden = !on;
    $("bell-button").checked = !!info.showButton;
    $("bell-button").disabled = state.offline || state.bellBusy;

    $("bell-chime-name").textContent = info.builtIn
      ? "The built-in bell."
      : "Your own sound (" + info.chimeName + ").";
    $("bell-reset").hidden = !!info.builtIn;
    ["bell-choose", "bell-reset", "bell-preview", "bell-all", "bell-none"]
      .forEach(function (id) { $(id).disabled = state.offline || state.bellBusy; });

    var chosen = bellTargets();
    var all = bellDevices();
    var list = $("bell-devices");
    clear(list);
    if (!all.length) {
      list.appendChild(el("p", "muted small",
        state.cast ? "Home Assistant can't see any speakers."
                   : "Looking…"));
    }
    all.forEach(function (device) { list.appendChild(bellRow(device, chosen)); });

    /* Select all is only ever an addition, and Clear only a removal, so
       neither can be pressed to no effect without saying so. */
    $("bell-all").hidden = !all.length || chosen.length === all.length;
    $("bell-none").hidden = !chosen.length;
    $("bell-devices-note").textContent = chosen.length
      ? ""
      : "Nothing chosen, so the bell has nowhere to ring.";

    $("bell-ring").disabled = state.offline || state.bellBusy || !chosen.length;
    paintBellNote();
  }

  function bellBusy(busy, message) {
    state.bellBusy = busy;
    if (message) bellSay(message);
    renderBell();
  }

  function ringBell() {
    bellBusy(true, "Ringing…");
    api("POST", "/api/bell/ring", {}).then(function (result) {
      state.bellBusy = false;
      var rang = (result.rang || []).length;
      var failed = result.failed || [];
      var message;
      if (rang && !failed.length) {
        message = "Rang on " + plural(rang, "speaker") + ".";
      } else if (rang) {
        message = "Rang on " + rang + " of " + (rang + failed.length)
                + ". " + bellName(failed[0].entityId) + ": " + failed[0].error;
      } else {
        message = "Nothing rang. " + (failed.length
          ? bellName(failed[0].entityId) + ": " + failed[0].error
          : "Home Assistant didn't say why.");
      }
      bellSay(message, !rang);
      renderBell();
    }).catch(function (err) {
      state.bellBusy = false;
      bellSay(err.message || "The bell didn't ring.", true);
      renderBell();
    });
  }

  /* Uploaded as raw bytes with the name on the query string, the same shape the
     restore upload uses: there is no form parser on the server and a single
     file has never needed one. */
  function uploadChime(file) {
    if (!file) return;
    bellBusy(true, "Sending " + file.name + "…");
    upload("/api/bell/chime?name=" + encodeURIComponent(file.name), file,
           null, file.type || "application/octet-stream")
      .then(function (info) {
        state.bell = info;
        state.bellBusy = false;
        bellSay("Sound saved. Press Listen to hear it.");
        renderBell();
      }).catch(function (err) {
        state.bellBusy = false;
        bellSay(err.message || "That sound couldn't be saved.", true);
        renderBell();
      });
  }

  /* Plays on this device, not on the speakers - the question "is this the right
     sound" is worth being able to answer without ringing the house. The
     timestamp in the chime's name means there is never a stale one cached. */
  function previewChime() {
    var info = state.bell;
    if (!info) return;
    var audio = $("bell-audio");
    audio.src = info.chime;
    var played = audio.play();
    if (played && played.catch) {
      played.catch(function () {
        bellSay("This device wouldn't play the sound. It will still ring on "
                + "the speakers.", true);
      });
    }
  }

  // --------------------------------------------------------- backup
  //
  /* One file in, one file out. The point of this screen is that reinstalling
     the app stops being a thing to be nervous about: download, uninstall,
     install from the repository, restore.

     Nothing here goes through api(): the download is a zip rather than JSON,
     and the upload wants a progress bar, which fetch() can't give for a request
     body. Both use the browser's own machinery instead. */

  function fileSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + " bytes";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function backupSay(message, isError) {
    var note = $("backup-note");
    var error = $("backup-error");
    note.hidden = true;
    error.hidden = true;
    if (!message) return;
    var target = isError ? error : note;
    target.textContent = message;
    target.hidden = false;
  }

  function backupBusy(on, label, fraction) {
    /* Recorded on state, not just on the buttons: render() runs on a timer and
       on every save, and a long upload would otherwise have its own buttons
       re-enabled underneath it by a refresh that knew nothing about it. */
    state.backupBusy = on;
    var wrap = $("backup-progress");
    wrap.hidden = !on;
    $("backup-download").disabled = on;
    $("backup-restore").disabled = on || state.offline;
    if (!on) return;
    $("backup-progress-note").textContent = label || "";
    /* An indeterminate bar when there is no fraction to show - reading a zip is
       quick and unmeasurable, and a bar stuck at 0% looks like a hang. */
    $("backup-bar-fill").style.width =
      fraction === undefined || fraction === null ? "100%" : Math.round(fraction * 100) + "%";
    $("backup-progress").classList.toggle("is-waiting",
      fraction === undefined || fraction === null);
  }

  function loadBackupInfo() {
    return api("GET", "/api/backup/info").then(function (info) {
      state.backup = info;
      renderBackup();
      return info;
    }).catch(function () {
      /* Offline, or a version from before this existed. The card stays, because
         the buttons are what explain it; they just say why they can't run. */
      state.backup = null;
      renderBackup();
    });
  }

  /* What a backup holds, in words, for the card and for the confirmation before
     a restore. One function for both, because the two are read minutes apart by
     somebody deciding whether the file in their downloads folder is the right
     one, and they had better count the same things.

     Ratings are named explicitly. They have always been in the zip - they live
     on the sittings inside data.json, which is copied whole - but a summary
     that listed meals, people and photos read like a summary of everything
     that was in there, and the household's opinion of every dinner it has ever
     eaten is the one thing here that cannot be typed back in.

     Anything at zero is left out rather than shown as "0 ratings": a new
     household has none of several of these, and a list of noughts is a worse
     answer than a short sentence. */
  function backupParts(counts) {
    var c = counts || {};
    var parts = [
      plural(c.meals || 0, "meal"),
      plural(c.people || 0, "person", "people")
    ];
    if (c.weeks) parts.push(plural(c.weeks, "week") + " planned");
    if (c.ratings) parts.push(plural(c.ratings, "rating"));
    if (c.images) parts.push(plural(c.images, "photo"));
    return parts;
  }

  function plural(n, one, many) {
    return n + " " + (n === 1 ? one : (many || one + "s"));
  }

  function renderBackup() {
    var info = state.backup;
    var summary = $("backup-summary");
    if (state.offline) {
      summary.textContent = "Backups are made by the app itself, so this " +
        "needs you to be on the home network.";
    } else if (!info) {
      summary.textContent = "";
    } else {
      summary.textContent = "Version " + (info.version || "?") + " — " +
                            backupParts(info.contents).join(", ") + ".";
    }
    $("backup-download").disabled = state.offline || state.backupBusy;
    $("backup-restore").disabled = state.offline || state.backupBusy;

    var wrap = $("backup-undo-wrap");
    var list = $("backup-undo-list");
    var undo = (info && info.undo) || [];
    wrap.hidden = undo.length === 0;
    clear(list);
    undo.forEach(function (snap) {
      var row = el("div", "backup-undo-row");
      row.appendChild(el("span", "name",
        "Saved " + prettyStamp(snap.at) + " (" + fileSize(snap.bytes) + ")"));
      var get = el("button", "icon-btn", "Download");
      get.onclick = function () {
        window.location.href = "/api/backup?undo=" + encodeURIComponent(snap.name);
      };
      row.appendChild(get);
      list.appendChild(row);
    });
  }

  function prettyStamp(iso) {
    /* The server sends a local ISO stamp. Date can parse it; if some browser
       can't, showing the raw string beats showing "Invalid Date". */
    var when = new Date(iso);
    if (isNaN(when.getTime())) return iso;
    return when.toLocaleString(undefined,
      { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function downloadBackup() {
    backupSay("");
    backupBusy(true, "Gathering everything up…");
    /* Fetched rather than navigated to, so a failure comes back as a message on
       this card instead of a browser error page - and so the button can go back
       to normal when it lands. */
    fetch("/api/backup").then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.error || "The app couldn't build the backup.");
        });
      }
      return res.blob();
    }).then(function (blob) {
      var name = (state.backup && state.backup.suggestedName) ||
                 "meal-planner-backup.zip";
      var url = URL.createObjectURL(blob);
      var link = el("a");
      link.href = url;
      link.download = name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      /* Revoked on a delay rather than immediately: Safari has not always
         finished with the blob by the time click() returns. */
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
      backupBusy(false);
      backupSay("Saved " + name + " (" + fileSize(blob.size) + "). Keep it " +
                "somewhere that isn't the Pi.");
    }).catch(function (err) {
      backupBusy(false);
      backupSay(err.message || "The backup didn't download.", true);
    });
  }

  /* Restore is two round trips on purpose. The first asks the app what is in
     the file without writing anything, so the confirmation can name what is
     about to replace the current data - agreeing to "142 meals from 3 August"
     is a different act from agreeing to "are you sure". */
  function restoreBackup(file) {
    if (!file) return;
    backupSay("");
    backupBusy(true, "Reading " + file.name + "…");

    upload("/api/restore/check", file).then(function (found) {
      backupBusy(false);
      var a = found.actual || {};
      var lines = [
        "Restore from " + file.name + "?",
        "",
        "It holds " + backupParts(a).join(", ") +
          (a.certs ? ", and the https certificate" : "") + ".",
        "Made " + prettyStamp(found.createdAt) +
          " by version " + (found.version || "?") + ".",
        "",
        "Everything in the planner now will be replaced. A copy of it is saved " +
        "first, and you can download that copy from this screen afterwards."
      ];
      if (!confirm(lines.join("\n"))) return null;
      backupBusy(true, "Putting it back…", 0);
      return upload("/api/restore", file, function (fraction) {
        backupBusy(true, "Putting it back…", fraction);
      });
    }).then(function (result) {
      backupBusy(false);
      if (!result) return;                       // cancelled at the confirm
      var message = "Restored " + backupParts(result.contents).join(", ") + ".";
      if (result.restartNeeded) {
        /* certs/ was loaded into an SSL context when the process started, so
           https keeps using the old certificate until the app restarts. Worth
           saying plainly: the symptom otherwise is phones quietly failing the
           handshake with no clue why. */
        message += " The https certificate came back too — restart the app " +
                   "in Home Assistant so it starts using it.";
      }
      backupSay(message);
      toast("Restored");
      return refresh().then(loadBackupInfo).then(function () {
        loadDisplay();
        loadCast();
      });
    }).catch(function (err) {
      backupBusy(false);
      backupSay(err.message || "The restore didn't finish.", true);
    });
  }

  /* XMLHttpRequest rather than fetch, for one reason: upload progress. A
     household's photos make a zip of tens of megabytes and house wifi is not
     always quick, so a bar that moves is the difference between waiting and
     wondering. The body is the file itself - no multipart wrapper, because the
     server has no form parser and does not need one for a single file.

     `type` is what to declare the body as, and defaults to the zip this was
     written for. The server doesn't read it - the restore sniffs the zip and
     the chime sniffs the audio, because a content type off a phone's file
     picker is a guess - but sending application/zip for an mp3 would be a lie
     told to every proxy in between for no reason. */
  function upload(path, file, onProgress, type) {
    return new Promise(function (resolve, reject) {
      var req = new XMLHttpRequest();
      req.open("POST", path, true);
      req.setRequestHeader("Content-Type", type || "application/zip");
      if (onProgress && req.upload) {
        req.upload.onprogress = function (e) {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
      }
      req.onload = function () {
        var body = {};
        try { body = JSON.parse(req.responseText); } catch (e) {}
        if (req.status >= 200 && req.status < 300) resolve(body);
        else reject(new Error(body.error || "The app refused that file."));
      };
      req.onerror = function () {
        reject(new Error("The app couldn't be reached. Are you on the " +
                         "home network?"));
      };
      req.onabort = function () { reject(new Error("Cancelled.")); };
      req.send(file);
    });
  }

  // ------------------------------------------------------------ render

  function render() {
    if (state.view === "week") renderWeek();
    else if (state.view === "plan") renderPlan();
    else if (state.view === "shopping") renderShopping();
    else if (state.view === "meals") renderMeals();
    else if (state.view === "settings") {
      renderPeople(); renderBell(); renderBackup();
    }
  }

  // ------------------------------------------------------------- wiring

  function wire() {
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
      tab.onclick = function () { setView(tab.dataset.view); };
    });

    /* All six go through goToWeek, which decides where in the new week to put
       you - Monday, or today if the new week is this one. */
    function weekNav(field, ids, redraw, focus) {
      $(ids[0]).onclick = function () {
        goToWeek(field, addDays(state[field], -7), redraw, focus);
      };
      $(ids[1]).onclick = function () {
        goToWeek(field, addDays(state[field], 7), redraw, focus);
      };
      $(ids[2]).onclick = function () {
        goToWeek(field, state.thisWeek, redraw, focus);   // "Today", not merely
      };                                                  // "this week"
    }

    weekNav("viewWeek", ["w-prev", "w-next", "w-today"], renderWeek, focusOnToday);
    weekNav("planWeek", ["p-prev", "p-next", "p-today"], renderPlan, scrollToPlanToday);
    /* No focus for shopping: it is one list for the whole week rather than
       seven days, so it has no "today" to land on. Top of the list every time,
       which is where you start reading it anyway. */
    weekNav("shopWeek", ["s-prev", "s-next", "s-today"], renderShopping, null);
    $("extras-form").onsubmit = function (e) {
      e.preventDefault();
      var field = $("extras-item");
      var text = field.value.trim();
      if (!text) return;
      /* Cleared straight away rather than on the way back: the next thing on
         the list is usually already half-typed in someone's head. */
      field.value = "";
      addExtra(text).then(function () { field.focus(); });
    };

    $("s-print").onclick = function () { window.print(); };
    $("s-share").onclick = shareShoppingList;
    updateShareBtn();

    $("p-clear").onclick = function () {
      if (!confirm("Clear the whole plan for " + weekRange(state.planWeek) + "?")) return;
      api("POST", "/api/week/" + state.planWeek + "/clear")
        .then(refresh).then(function () { toast("Week cleared"); }).catch(fail);
    };

    $("p-copy-last").onclick = function () {
      var src = addDays(state.planWeek, -7);
      if (!confirm("Copy the plan from " + weekRange(src) + " into this week? Anything already planned will be replaced.")) return;
      api("POST", "/api/week/copy", { from: src, to: state.planWeek })
        .then(refresh).then(function () { toast("Copied"); }).catch(fail);
    };

    $("meal-form").onsubmit = function (e) {
      e.preventDefault();
      var payload = {
        name: $("meal-name").value.trim(),
        tags: $("meal-tags").value.split(",").map(function (t) { return t.trim(); }).filter(Boolean),
        links: linksFromForm(),
        ingredients: ingredientsFromForm(),
        serves: Number($("meal-serves").value) || null,
        notes: $("meal-notes").value.trim(),
        macros: macrosFromForm()
      };
      if (!payload.name) return;
      if (state.pendingImage) {
        payload.imageData = state.pendingImage;
      } else {
        var typedUrl = $("meal-image").value.trim();
        // Only mention the image when it changed, so an untouched field
        // doesn't wipe a stored photo.
        if (typedUrl !== state.imageShown) payload.image = typedUrl;
      }
      var editing = state.editingMealId;
      var req = editing
        ? api("PUT", "/api/meals/" + editing, payload)
        : api("POST", "/api/meals", payload);
      req.then(function () {
        resetMealForm();
        /* An edit is finished, so the form gets out of the way of the meal it
           just changed. A new meal often isn't the only one being typed - it
           is what the old Bulk Add tab was really for - so the empty form
           stays up, ready for the next one. */
        if (editing) closeAddPanel();
        return refresh();
      }).then(function () {
        toast(editing ? "Meal updated" : "Meal added");
      }).catch(function (err) {
        var box = $("meal-error");
        box.textContent = err.message;
        box.hidden = false;
      });
    };

    /* Cancel empties the form and puts it away. Since the panel is now opened
       deliberately with the +, "I've finished with this" is one thing, not
       two. */
    $("meal-cancel").onclick = function () { resetMealForm(); closeAddPanel(); };

    $("add-panel-toggle").onclick = function () {
      if ($("add-panel").hidden) { openAddPanel(); } else { closeAddPanel(); }
    };

    $("add-link").onclick = function () { addLinkRow(null); };

    $("meal-image").oninput = function () {
      state.pendingImage = null;
      imagePreview(this.value.trim());
    };

    /* Upload a picture from this device: resized here, then the server stores
       it in the images folder. */
    $("upload-image-btn").onclick = function () { $("image-file").click(); };
    $("image-file").onchange = function () {
      var file = this.files && this.files[0];
      this.value = "";              // picking the same file twice still fires
      if (!file) return;
      shrinkImage(file, 1024).then(function (dataUrl) {
        state.pendingImage = dataUrl;
        $("meal-image").value = "";
        imagePreview(dataUrl);
        toast("Picture ready - it'll be saved with the meal");
      }).catch(function (err) {
        toast(err.message || "That picture couldn't be read");
      });
    };
    $("add-ing").onclick = function () { addIngRow(null); updateIngHint(); };
    $("meal-serves").oninput = updateIngHint;
    $("ing-rows").addEventListener("input", updateIngHint);

    $("meal-search").oninput = function () {
      state.mealFilter = this.value;
      renderMeals();
    };

    $("meal-sort-btn").onclick = function () {
      state.sortOpen = !state.sortOpen;
      renderSortControl();
    };

    /* Which order and whose taste are a per-device preference, like the theme:
       the phone in Pete's pocket asking for what Pete likes shouldn't change
       what the kitchen tablet shows. Restored here rather than in the state
       literal because the household has to be loaded before a stored id means
       anything. */
    state.mealSort = stored("mealSort", "az");
    state.ratedBy = stored("ratedBy", "").split(",").filter(Boolean);

    $("cast-show-all").onchange = renderCast;

    $("display-scale").oninput = function () {
      saveDisplaySoon({ scale: Number($("display-scale").value) });
    };
    $("cast-window").onchange = function () {
      saveDisplay({ castWindow: $("cast-window").checked });
    };
    $("cast-from").onchange = function () {
      saveDisplay({ castFrom: $("cast-from").value });
    };
    $("cast-to").onchange = function () {
      saveDisplay({ castTo: $("cast-to").value });
    };
    $("display-rollover").onchange = function () {
      saveDisplay({ rollover: $("display-rollover").value });
    };
    $("display-dim").onchange = function () {
      saveDisplay({ dim: $("display-dim").checked });
    };
    $("display-dim-from").onchange = function () {
      saveDisplay({ dimFrom: $("display-dim-from").value });
    };
    $("display-dim-to").onchange = function () {
      saveDisplay({ dimTo: $("display-dim-to").value });
    };
    $("display-dim-level").oninput = function () {
      saveDisplaySoon({ dimLevel: Number($("display-dim-level").value) });
    };

    $("cast-forget").onclick = forgetGone;

    $("cast-refresh").onclick = function () {
      var btn = $("cast-refresh");
      btn.disabled = true;
      /* A real round trip to Home Assistant, so it is worth saying something -
         a button that looks identical either way is a button you press twice. */
      loadCast(true).then(function () {
        btn.disabled = false;
        toast(state.cast && state.cast.devices.length
          ? state.cast.devices.length + " Cast device"
            + (state.cast.devices.length === 1 ? "" : "s") + " found"
          : "No Cast devices found");
      });
    };

    // ---- dinner bell ----
    $("bell-enabled").onchange = function () {
      saveBell({ enabled: $("bell-enabled").checked });
    };
    $("bell-button").onchange = function () {
      saveBell({ showButton: $("bell-button").checked });
    };
    $("bell-all").onclick = function () {
      saveBell({ devices: bellDevices().map(function (d) { return d.entityId; }) });
    };
    $("bell-none").onclick = function () { saveBell({ devices: [] }); };
    $("bell-ring").onclick = ringBell;
    $("bell-preview").onclick = previewChime;

    $("bell-choose").onclick = function () { $("bell-chime-file").click(); };
    $("bell-chime-file").onchange = function () {
      var file = $("bell-chime-file").files[0];
      $("bell-chime-file").value = "";      // so the same file can be re-picked
      uploadChime(file);
    };
    $("bell-reset").onclick = function () {
      if (!confirm("Go back to the built-in bell? Your own sound is deleted.")) return;
      bellBusy(true, "Putting the built-in bell back…");
      api("DELETE", "/api/bell/chime").then(function (info) {
        state.bell = info;
        state.bellBusy = false;
        bellSay("Back to the built-in bell.");
        renderBell();
      }).catch(function (err) {
        state.bellBusy = false;
        bellSay(err.message || "That didn't work.", true);
        renderBell();
      });
    };

    $("backup-download").onclick = downloadBackup;

    /* The visible button drives the hidden file input, and the input is reset
       after each pick so choosing the same file twice still fires a change. */
    $("backup-restore").onclick = function () { $("backup-file").click(); };
    $("backup-file").onchange = function () {
      var file = $("backup-file").files[0];
      $("backup-file").value = "";
      restoreBackup(file);
    };

    $("person-form").onsubmit = function (e) {
      e.preventDefault();
      var name = $("person-name").value.trim();
      if (!name) return;
      api("POST", "/api/people", { name: name }).then(function () {
        $("person-form").reset();
        $("person-error").hidden = true;
        return refresh();
      }).then(function () { toast("Added"); }).catch(function (err) {
        var box = $("person-error");
        box.textContent = err.message;
        box.hidden = false;
      });
    };

    window.onhashchange = function () {
      var name = viewFromHash(location.hash.slice(1));
      if (name && name !== state.view) setView(name);
    };

    /* Keep the week view fresh when it is left up on a kitchen screen,
       but don't fight with anyone who is mid-edit on another tab.
       When offline, keep trying from any tab: that is how the app notices it
       has come back onto the home network. */
    setInterval(function () {
      if (document.hidden) return;
      syncToday();
      if (state.view === "week" || state.offline) refresh().catch(function () {});
    }, 20000);

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { state.hiddenAt = Date.now(); return; }
      /* The main way the day catches up: a phone that was asleep for three
         days gets here the moment its owner looks at the app again. */
      syncToday();
      var jumped = backFromAway();
      state.hiddenAt = 0;
      if (!jumped && (state.view === "week" || state.offline)) {
        refresh().catch(function () {});
      }
    });

    /* A hand on the screen ends any attempt to position it. Deliberately not
       the scroll event: our own scrolling raises that too, and telling the two
       apart is guesswork. These three are unambiguous - nothing but a person
       produces them. */
    ["touchstart", "wheel", "keydown"].forEach(function (name) {
      window.addEventListener(name, stopFocusingToday, { passive: true });
    });

    window.addEventListener("pagehide", function () { state.hiddenAt = Date.now(); });

    /* Restored from the back/forward cache, where no timer has been running. */
    window.addEventListener("pageshow", function (e) {
      if (!e.persisted) return;
      syncToday();
      backFromAway();
      state.hiddenAt = 0;
    });

    /* Coarse signals - the phone rejoining wifi doesn't prove the Pi is
       reachable, but it is a good moment to find out. */
    window.addEventListener("online", function () { refresh().catch(function () {}); });
    window.addEventListener("offline", function () { setOffline(true); });
  }

  // ------------------------------------------------------- service worker

  function wireServiceWorker() {
    if (!("serviceWorker" in navigator)) return;

    /* Service workers - and so offline reading - are only permitted in a secure
       context: https, or localhost. Over plain http on a LAN address the
       browser refuses to register and says nothing. Better to admit it here
       than to leave someone wondering why the week is blank on the train. */
    if (!window.isSecureContext) {
      var note = document.querySelector("#view-week .footnote");
      if (note) {
        note.appendChild(document.createElement("br"));
        note.appendChild(el("span", "muted small",
          "To read this week's meals when you're away from home, "));
        var link = el("a", null, "set this device up for offline use");
        link.href = "/setup";
        note.appendChild(link);
        note.appendChild(el("span", "muted small", " — it takes a minute, once."));
      }
      return;
    }

    /* Registered after load so it never competes with the first paint. */
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").then(function (reg) {
        /* A new version is waiting because another tab is still on the old
           one. Take over straight away - this app has no unsaved-state risk
           worth holding a release back for. */
        reg.addEventListener("updatefound", function () {
          var sw = reg.installing;
          if (!sw) return;
          sw.addEventListener("statechange", function () {
            if (sw.state === "installed" && navigator.serviceWorker.controller) {
              sw.postMessage("skip-waiting");
            }
          });
        });
      }).catch(function () {
        /* No offline copy, everything else still works. Browsers also refuse
           to register over plain http on anything but localhost, so this is
           expected if the app is ever reached by hostname over the internet. */
      });
    });
  }

  // -------------------------------------------------------------- start

  /* This app decides where the page should be looking - today's card - so the
     browser must not also have an opinion. Left on "auto" it re-applies the
     scroll position from the last visit, and it does so after the load event,
     which is to say after we have already put the week where we want it. */
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  /* Before the first fetch, so the week view has a valid week to draw even if
     the server is unreachable and there is nothing cached. */
  syncToday(true);
  scheduleMidnight();

  wire();
  wireTheme();
  wireSwipe();
  wireStars();
  wirePalette();
  wireServiceWorker();
  trackTopbarHeight();
  /* The hash is honoured so the manifest's shortcuts and any link into a tab
     still land where they point; a plain launch has no hash beyond the "week"
     the manifest's start_url carries, so it opens on the week either way. */
  var initial = viewFromHash(location.hash.slice(1)) || "week";
  state.view = initial;
  refresh().then(function () {
    /* Asked for here rather than before the fetch, because refresh() renders
       once of its own accord and setView goes to the top of the page before it
       renders again - so a scroll asked for any earlier is undone a moment
       later. */
    focusOnToday();
    setView(initial);
    state.booted = true;
  }).catch(function () {
    state.booted = true;
    document.getElementById("main").prepend(
      el("div", "empty-state",
        "Could not reach the meal planner, and there's no saved copy on this " +
        "device yet. Open this page once while you're at home and it will be " +
        "readable offline afterwards.")
    );
  });
})();
