/* The kitchen display's shopping panel: the column at the end of the week
   strip and its count, what an ordered row is and isn't allowed to do, what
   the stepper posts, what a tile posts and where the answer lands, and the two
   things a cast display must not do to somebody's hands - reload under them,
   or redraw under them.

   Runs static/kitchen.js for real against static/kitchen.html, with XHR faked.
   Nothing inside the display is mocked, so a change that breaks the wiring
   between a tile and /api/extras fails here rather than in a kitchen.

   Note the layout fakes at the top. jsdom has no layout: offsetTop and
   clientHeight are zero for everything, so the pagers would measure a screen
   with no room on it and fall back to their defaults. The prototype patches
   below give the two boxes real numbers, which is what makes "the added thing
   is on the page you are looking at" testable at all. */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const DIR = path.join(__dirname, '..', '..', 'static');
const html = fs.readFileSync(path.join(DIR, 'kitchen.html'), 'utf8');
const js = fs.readFileSync(path.join(DIR, 'kitchen.js'), 'utf8');

let failures = 0;
function ok(label, cond, detail) {
  if (cond) { console.log('  ok   ' + label); return; }
  failures++;
  console.log('  FAIL ' + label + (detail ? '  -> ' + detail : ''));
}

const today = new Date().toISOString().slice(0, 10);

function extra(id, item, qty, unit, state) {
  return { id, item, qty, unit, state, orderedAt: state === 'ordered' ? today : '' };
}

/* Three needed and one ordered, which is the shape that matters: the ordered
   one has to sort last, dim, and lose its stepper. */
const EXTRAS = [
  extra('x1', 'Milk', 2, 'each', 'need'),
  extra('x2', 'Mince', 500, 'g', 'need'),
  extra('x3', 'Bin Bags', 1, 'each', 'need'),
  extra('x4', 'Foil', 1, 'each', 'ordered'),
];

const KNOWN = ['Milk', 'Mince', 'Bin Bags', 'Foil', 'Kitchen Roll', 'Washing Up Liquid'];

function feed(over) {
  return Object.assign({
    today, date: today, rolling: true, week: today, from: today,
    display: {
      accent: 'green', theme: 'dark', scale: 100, showCook: true,
      showHeads: true, showClock: true, showDate: true, showWeek: true,
      showPhotos: true, showEmpty: true, showShopping: true,
      dim: false, dimFrom: '22:00', dimTo: '06:30', dimLevel: 45,
    },
    bell: { ready: false, showButton: false },
    extras: JSON.parse(JSON.stringify(EXTRAS)),
    knownExtras: KNOWN.slice(),
    household: [],
    days: [{
      date: today, day: 'mon', name: 'Monday', isToday: true, cook: 'Ann',
      headCount: 2, meals: [], notEating: [],
    }],
    todayMeals: [], todayCook: 'Ann', todayNotEating: [],
  }, over || {});
}

// ---------------------------------------------------------------- harness

const posts = [];          // every write the display made, in order
let nextPostReply = null;  // what the next POST answers with
let failNextPost = false;
let overrideDisplay = null; // swap the display settings on the next poll
const windows = [];        // every display booted, so they can all be stopped

function boot(over) {
  /* Neither window.location nor the reload on it can be replaced in jsdom, so
     the six-hourly self-heal can't be stubbed. What jsdom does instead is
     report the attempt as a "Not implemented: navigation" error on the virtual
     console, which is the only observable this has - so it is counted there
     and hung on the window as __reloads. Anything else arriving on that
     channel is a real error and is let through, or a broken display would run
     these tests in silence. */
  const console_ = new VirtualConsole();
  let reloads = 0;
  console_.on('jsdomError', (err) => {
    if (/navigation/i.test(err.message || '')) { reloads++; return; }
    console.error(err.message);
  });

  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'http://hub/kitchen',
    virtualConsole: console_,
  });
  const win = dom.window;
  Object.defineProperty(win, '__reloads', { get() { return reloads; } });

  /* Layout, since jsdom has none. Rows are 80px in a 400px box (5 a page) and
     tiles are 100px across in a 300px box, 2 rows deep (6 a page). Written as
     prototype getters because the display measures probe elements it creates
     and throws away, so there is nothing to attach a fake to by hand. */
  Object.defineProperties(win.HTMLElement.prototype, {
    offsetTop: {
      get() {
        const box = this.parentNode;
        if (!box || !box.classList) return 0;
        const kids = Array.prototype.slice.call(box.children);
        const i = kids.indexOf(this);
        if (box.classList.contains('shop-rows')) return i * 80;
        if (box.classList.contains('pick-grid')) return Math.floor(i / 3) * 100;
        return 0;
      },
    },
    offsetHeight: { get() { return 80; } },
    offsetWidth: { get() { return 100; } },
    clientHeight: {
      get() {
        if (!this.classList) return 0;
        /* A hidden box has no height, and modelling that is the point of this
           fake rather than a detail of it: measuring a face before it is on
           the screen is exactly the mistake that is easy to make here, and a
           fake that answered 400 either way would let it through. */
        for (let n = this; n && n.hasAttribute; n = n.parentNode) {
          if (n.hasAttribute('hidden')) return 0;
        }
        if (this.classList.contains('shop-rows')) return 400;   // 5 rows
        if (this.classList.contains('pick-grid')) return 300;   // 3 rows of 100
        return 0;
      },
    },
    clientWidth: { get() { return 300; } },
  });

  // Fake XHR. GET answers with the feed; POST records and replies.
  win.XMLHttpRequest = function () {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
    this.open = function (method, url) { this._m = method; this._u = url; };
    this.setRequestHeader = function () {};
    this.send = function (body) {
      const self = this;
      const done = function () {
        self.readyState = 4;
        if (self.onreadystatechange) self.onreadystatechange();
      };
      if (this._m === 'GET') {
        this.status = 200;
        const payload = feed(over);
        if (overrideDisplay) payload.display = overrideDisplay;
        this.responseText = JSON.stringify(payload);
        done();
        return;
      }
      posts.push({ url: this._u, body: JSON.parse(body || '{}') });
      if (failNextPost) { failNextPost = false; this.status = 500; done(); return; }
      this.status = 200;
      this.responseText = JSON.stringify(nextPostReply || { ok: true });
      done();
    };
  };

  /* The display's own timers, kept rather than run. Waiting a real minute for
     a poll is not a test, and the two things worth checking here are exactly
     what those callbacks do when a panel is open - so they are captured on the
     way past and called by hand. */
  win.__timers = [];
  const realInterval = win.setInterval;
  win.setInterval = function (fn, ms) {
    win.__timers.push({ fn, ms });
    return realInterval(function () {}, 1e9);
  };

  /* The idle close is a setTimeout rather than an interval, and it is restarted
     on every touch - so what is kept is the whole sequence of registrations
     and which of them were cancelled. The last live one is the one that would
     actually fire. */
  win.__waits = [];
  const realTimeout = win.setTimeout;
  const realClear = win.clearTimeout;
  win.setTimeout = function (fn, ms) {
    const handle = realTimeout(function () {}, 1e9);
    win.__waits.push({ fn, ms, handle, cancelled: false });
    return handle;
  };
  win.clearTimeout = function (handle) {
    win.__waits.forEach((w) => { if (w.handle === handle) w.cancelled = true; });
    return realClear(handle);
  };

  win.eval(js);
  windows.push(win);
  return win;
}

/* The poll is the one on a 60s interval; the reload check is the 10-minute
   one. Found by their period rather than their position, so reordering the
   bottom of kitchen.js doesn't silently point these at the clock. */
function timerOf(win, ms) {
  const hit = win.__timers.filter((t) => t.ms === ms);
  if (hit.length !== 1) throw new Error('expected one ' + ms + 'ms timer, got ' + hit.length);
  return hit[0].fn;
}

// The idle close that is currently armed, if any. 90s is the shopping panel's
// and nothing else on this display uses it.
function liveWait(win, ms) {
  const live = win.__waits.filter((w) => w.ms === ms && !w.cancelled);
  return live.length ? live[live.length - 1] : null;
}

function $(win, id) { return win.document.getElementById(id); }
function rows(win) {
  return Array.prototype.slice.call($(win, 'shop-rows').children);
}
function tiles(win) {
  return Array.prototype.slice.call($(win, 'pick-grid').children)
    .filter((n) => n.className.indexOf('pick-tile') === 0);
}
function text(node, sel) { return node.querySelector(sel).textContent; }

// ------------------------------------------------------------- the button

console.log('the shopping column');
{
  const win = boot();
  ok('shows when the server offers it', !$(win, 'shop-btn').hidden);
  ok('counts what is still needed, not the ordered one',
    $(win, 'shop-count').textContent === '3',
    'got ' + $(win, 'shop-count').textContent);
}
{
  // A server too old to send extras at all, which is the upgrade path.
  const win = boot({ extras: undefined, knownExtras: undefined });
  ok('stays hidden on a feed with no extras on it', $(win, 'shop-btn').hidden);
}
{
  const d = feed().display; d.showShopping = false;
  const win = boot({ display: d });
  ok('stays hidden when the setting is off', $(win, 'shop-btn').hidden);
}
{
  const win = boot({ extras: [extra('x4', 'Foil', 1, 'each', 'ordered')] });
  ok('badge hidden when nothing is needed', $(win, 'shop-count').hidden);
  ok('button still offered, so the ordered line is reachable',
    !$(win, 'shop-btn').hidden);
}
{
  /* It is the eighth column of the bottom row now, not something floating over
     the corner of it. renderWeek() empties #week on every poll, so the thing
     that matters is that the button is NOT in there - it is a sibling in the
     wrapper - or the first poll would throw it away. */
  const win = boot();
  const btn = $(win, 'shop-btn');
  ok('lives beside the week strip, not inside it',
    btn.parentNode.className === 'weekbar');
  ok('and the strip is its sibling',
    btn.parentNode.querySelector('#week') !== null);

  const poll = timerOf(win, 60000);
  poll();
  poll();
  ok('so rebuilding the week twice leaves it alone',
    $(win, 'shop-btn') !== null && !$(win, 'shop-btn').hidden);
  // One day column, because the feed above carries one day. The point is what
  // is not in there rather than how many are.
  ok('and the strip holds day columns and nothing else',
    $(win, 'week').querySelector('#shop-btn') === null
    && $(win, 'week').children.length === 1,
    $(win, 'week').children.length + ' children of #week');
}
{
  /* Turning the week strip off must not take the shopping with it - the
     stylesheet turns the column back into a pill on the same row, but only if
     the button is still there to style. This is the assertion that stops a
     later tidy-up from hiding the two together. */
  const off = feed().display; off.showWeek = false;
  const win = boot({ display: off });
  ok('the screen knows the week is off',
    $(win, 'screen').className.indexOf('no-week') >= 0,
    $(win, 'screen').className);
  ok('but the shopping is still reachable', !$(win, 'shop-btn').hidden);
  $(win, 'shop-btn').click();
  ok('and still opens', !$(win, 'shop').hidden);
}

// --------------------------------------------------------------- the list

console.log('the list');
{
  const win = boot();
  $(win, 'shop-btn').click();
  ok('opens over the whole screen', !$(win, 'shop').hidden);
  ok('opens on the list, not the grid', !$(win, 'shop-list').hidden
    && $(win, 'shop-pick').hidden);

  const r = rows(win);
  ok('four rows on one page', r.length === 4, 'got ' + r.length);
  ok('needed first, ordered last',
    text(r[0], '.shop-name') === 'Milk' && text(r[3], '.shop-name') === 'Foil');
  ok('ordered row is marked', r[3].className.indexOf('is-ordered') >= 0);
  ok('needed rows are not', r[0].className.indexOf('is-ordered') < 0);

  ok('a countable quantity shows its number', text(r[0], '.shop-qty') === '2');
  ok('a single countable still shows "1"', text(r[2], '.shop-qty') === '1');
  ok('a weight keeps its unit', text(r[1], '.shop-qty') === '500g');

  // The steppers exist on every row - the ordered one hides them in CSS
  // rather than dropping them - but only the needed ones do anything.
  const orderedSteps = r[3].querySelectorAll('.shop-step');
  posts.length = 0;
  orderedSteps[0].click();
  orderedSteps[1].click();
  ok('an ordered row posts nothing', posts.length === 0,
    'posted ' + JSON.stringify(posts));
}

// ------------------------------------------------------------ the stepper

console.log('the stepper');
{
  const win = boot();
  $(win, 'shop-btn').click();
  posts.length = 0;

  const after = JSON.parse(JSON.stringify(EXTRAS));
  after[0].qty = 3;
  nextPostReply = { ok: true, extras: after };

  rows(win)[0].querySelectorAll('.shop-step')[1].click();   // + on Milk
  ok('posts to the quantity endpoint', posts[0].url === '/api/extras/qty');
  ok('sends the id and the new number',
    posts[0].body.id === 'x1' && posts[0].body.qty === 3,
    JSON.stringify(posts[0].body));
  ok('redraws from the list that came back',
    text(rows(win)[0], '.shop-qty') === '3');
}
{
  const win = boot();
  $(win, 'shop-btn').click();
  posts.length = 0;
  nextPostReply = { ok: true, extras: JSON.parse(JSON.stringify(EXTRAS)) };

  rows(win)[1].querySelectorAll('.shop-step')[0].click();   // - on 500g Mince
  ok('a weight steps by 50, not by 1', posts[0].body.qty === 450,
    'got ' + posts[0].body.qty);
}
{
  const win = boot();
  $(win, 'shop-btn').click();
  posts.length = 0;
  failNextPost = true;

  const step = rows(win)[0].querySelectorAll('.shop-step')[1];
  step.click();
  ok('a refused change leaves the button pressable again', !step.disabled);
  ok('and does not invent a new number',
    text(rows(win)[0], '.shop-qty') === '2');
}

// ---------------------------------------------------------------- the grid

console.log('the grid of names');
{
  const win = boot();
  $(win, 'shop-btn').click();
  $(win, 'shop-add').click();
  ok('swaps to the grid', $(win, 'shop-list').hidden && !$(win, 'shop-pick').hidden);
  ok('six tiles fit a page of three across', tiles(win).length === 6,
    'got ' + tiles(win).length);
  ok('most-used first, as the server sent them',
    tiles(win)[0].textContent === 'Milk');

  posts.length = 0;
  nextPostReply = extra('x5', 'Kitchen Roll', 1, 'each', 'need');
  tiles(win)[4].click();

  ok('posts the bare name', posts[0].url === '/api/extras'
    && posts[0].body.item === 'Kitchen Roll', JSON.stringify(posts[0]));
  ok('comes straight back to the list', !$(win, 'shop-list').hidden);
  ok('the new line is there', rows(win).some(
    (n) => text(n, '.shop-name') === 'Kitchen Roll'));
  ok('and it sorted above the ordered one',
    text(rows(win)[4], '.shop-name') === 'Foil');
  ok('the corner count went up', $(win, 'shop-count').textContent === '4');
}
{
  // Adding something already on the list answers with that same line, one
  // more of it - it must replace the row, not become a second one.
  const win = boot();
  $(win, 'shop-btn').click();
  $(win, 'shop-add').click();
  nextPostReply = extra('x1', 'Milk', 3, 'each', 'need');
  tiles(win)[0].click();

  const milk = rows(win).filter((n) => text(n, '.shop-name') === 'Milk');
  ok('one Milk row, not two', milk.length === 1, 'got ' + milk.length);
  ok('and it counts three', text(milk[0], '.shop-qty') === '3');
}
{
  const win = boot({ knownExtras: [] });
  $(win, 'shop-btn').click();
  $(win, 'shop-add').click();
  ok('nothing remembered says so rather than showing a blank grid',
    $(win, 'pick-grid').textContent.indexOf('Nothing remembered') >= 0);
}

// ------------------------------------------------------------- the paging

console.log('paging');
{
  // Nine needed things at five to a page.
  const many = [];
  for (let i = 0; i < 9; i++) many.push(extra('n' + i, 'Thing ' + i, 1, 'each', 'need'));
  const win = boot({ extras: many });
  $(win, 'shop-btn').click();

  ok('five rows on the first page', rows(win).length === 5, 'got ' + rows(win).length);
  ok('says which page', $(win, 'shop-page').textContent === '1 / 2');
  ok('offers more', !$(win, 'shop-more').hidden);

  $(win, 'shop-more').click();
  ok('second page has the rest', rows(win).length === 4);
  ok('and says so', $(win, 'shop-page').textContent === '2 / 2');

  $(win, 'shop-more').click();
  ok('wraps back to the first', $(win, 'shop-page').textContent === '1 / 2');
}
{
  // Added while looking at page one, landing on page two: the display has to
  // follow it, or the tap looks like it did nothing.
  const many = [];
  for (let i = 0; i < 5; i++) many.push(extra('n' + i, 'Thing ' + i, 1, 'each', 'need'));
  const win = boot({ extras: many });
  $(win, 'shop-btn').click();
  ok('one page to start with', $(win, 'shop-page').hidden);

  $(win, 'shop-add').click();
  nextPostReply = extra('n9', 'Kitchen Roll', 1, 'each', 'need');
  tiles(win)[4].click();

  ok('follows the new line onto the second page',
    $(win, 'shop-page').textContent === '2 / 2',
    'got ' + $(win, 'shop-page').textContent);
  ok('and the new line is what is on it',
    text(rows(win)[0], '.shop-name') === 'Kitchen Roll');
}

// ------------------------------------------- not moving under somebody

console.log('a poll landing while the panel is open');
{
  const win = boot();
  const poll = timerOf(win, 60000);

  $(win, 'shop-btn').click();
  $(win, 'shop-add').click();             // stood on the grid, mid-add
  const before = tiles(win).map((n) => n.textContent).join(',');

  // A phone adds something, and the minute ticks over.
  EXTRAS.unshift(extra('x0', 'Butter', 1, 'each', 'need'));
  poll();

  ok('the panel stayed open', !$(win, 'shop').hidden);
  ok('and stayed on the grid rather than snapping to the list',
    !$(win, 'shop-pick').hidden);
  ok('the tiles under the finger did not move',
    tiles(win).map((n) => n.textContent).join(',') === before);

  /* The count behind the panel is deliberately left stale - the panel is over
     the top of it, and catching it up would mean taking the list the tiles are
     built from out from under them. What matters is that closing collects the
     newest feed rather than leaving the display on the one it opened with. */
  $(win, 'shop-close').click();
  ok('closing catches the count up', $(win, 'shop-count').textContent === '4',
    'got ' + $(win, 'shop-count').textContent);
  $(win, 'shop-btn').click();
  ok('and the new line is on the list', rows(win).some(
    (n) => text(n, '.shop-name') === 'Butter'));
  EXTRAS.shift();
}

console.log('the setting being switched off mid-touch');
{
  const win = boot();
  const poll = timerOf(win, 60000);
  $(win, 'shop-btn').click();
  ok('open to start with', !$(win, 'shop').hidden);

  const off = feed().display; off.showShopping = false;
  overrideDisplay = off;
  poll();
  ok('closes rather than stranding a panel with no way back',
    $(win, 'shop').hidden);
  ok('and the button goes with it', $(win, 'shop-btn').hidden);
  overrideDisplay = null;
}

console.log('measuring a face that is on the screen');
{
  /* Both faces start hidden, so a page size worked out before the swap is the
     fallback wearing a measurement's clothes. Six needed things: the grid
     fits six a page, the list fits five, and getting either from the fallback
     rather than the box would show the wrong number of them. */
  const many = [];
  for (let i = 0; i < 6; i++) many.push(extra('n' + i, 'Thing ' + i, 1, 'each', 'need'));
  // Twelve names, so the two answers differ: measured is nine to a page (three
  // across by three down), and the fallback is six. With only six to show,
  // both would put six on the screen and the assertion would prove nothing.
  const lots = [];
  for (let i = 0; i < 12; i++) lots.push('Name ' + i);
  const win = boot({ extras: many, knownExtras: lots });

  $(win, 'shop-btn').click();
  ok('the list measured its own box, not a hidden one',
    rows(win).length === 5 && $(win, 'shop-page').textContent === '1 / 2',
    rows(win).length + ' rows, page ' + $(win, 'shop-page').textContent);

  $(win, 'shop-add').click();
  ok('and so did the grid, once it was the face on screen',
    tiles(win).length === 9, 'got ' + tiles(win).length + ', fallback would be 6');

  // Closed while standing on the grid: re-opening has to land on the list and
  // measure it again rather than trusting what the grid left behind.
  $(win, 'shop-close').click();
  $(win, 'shop-btn').click();
  ok('re-opening lands on the list', !$(win, 'shop-list').hidden);
  ok('and measures it again', rows(win).length === 5,
    'got ' + rows(win).length);
}

console.log('a panel nobody walked away from');
{
  const win = boot();
  ok('nothing armed before it is opened', !liveWait(win, 90000));

  $(win, 'shop-btn').click();
  const first = liveWait(win, 90000);
  ok('opening arms the idle close', !!first);

  // Every touch has to put it back to the start, or somebody reading a long
  // list gets closed on mid-sentence.
  $(win, 'shop-add').click();
  const second = liveWait(win, 90000);
  ok('a touch re-arms it', !!second && second !== first);
  ok('and cancels the one before', first.cancelled);

  second.fn();
  ok('left alone, it goes back to the meals', $(win, 'shop').hidden);
  ok('and disarms itself on the way out', !liveWait(win, 90000));
}
{
  // Stepping a quantity is a touch too - the row buttons are the easiest place
  // to get this wrong, because they post rather than just redrawing.
  const win = boot();
  $(win, 'shop-btn').click();
  const before = liveWait(win, 90000);
  nextPostReply = { ok: true, extras: JSON.parse(JSON.stringify(EXTRAS)) };
  rows(win)[0].querySelectorAll('.shop-step')[1].click();
  ok('the stepper re-arms it', liveWait(win, 90000) !== before);
}

console.log('the six-hourly reload');
{
  const win = boot();
  const check = timerOf(win, 600000);

  /* Old enough to be due one. `startedAt` is a closure variable inside the
     display, so the clock is moved rather than the variable - kitchen.js
     resolves Date off the window at call time, which is what makes that
     possible at all. */
  const RealDate = win.Date;
  const shifted = new RealDate().getTime() + 7 * 3600000;
  win.Date = function () { return new RealDate(shifted); };
  win.Date.now = function () { return shifted; };

  $(win, 'shop-btn').click();
  check();
  ok('does not reload the page under an open panel', win.__reloads === 0,
    'reloaded ' + win.__reloads + ' times');

  $(win, 'shop-close').click();
  check();
  ok('but still self-heals once it is closed', win.__reloads === 1,
    'reloaded ' + win.__reloads + ' times');
  win.Date = RealDate;
}

/* The display sets three intervals on itself - the poll, the clock and the
   six-hourly reload check - and every one of them holds jsdom's event loop
   open. A dozen booted displays means node never exits on its own, so the run
   is ended rather than waited on. */
windows.forEach((w) => w.close());

console.log('');
if (failures) {
  console.log(failures + ' failed');
  process.exit(1);
}
console.log('all passed');
process.exit(0);
