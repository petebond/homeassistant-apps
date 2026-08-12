/* The strip along the bottom of the kitchen display: how many days it asks the
   server for, and the rule that decides how many lines a meal name gets.

   The line count is the reason this file exists. It is set by a selector that
   counts backwards from the end of a column - see .wday-meal:nth-last-child(3)
   in kitchen.css - and that is the kind of thing that is correct until someone
   adds an element to the column and quietly moves everything along one. jsdom
   has no CSS cascade to read a computed -webkit-line-clamp out of, but it does
   have a selector engine, so the check here is which elements the selector
   claims rather than what they end up looking like. That catches the mistake
   that would actually be made. */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const DIR = path.join(__dirname, '..', '..', 'static');
const html = fs.readFileSync(path.join(DIR, 'kitchen.html'), 'utf8');
const js = fs.readFileSync(path.join(DIR, 'kitchen.js'), 'utf8');
const css = fs.readFileSync(path.join(DIR, 'kitchen.css'), 'utf8');

let failures = 0;
function ok(label, cond, detail) {
  if (cond) { console.log('  ok   ' + label); return; }
  failures++;
  console.log('  FAIL ' + label + (detail ? '  -> ' + detail : ''));
}

/* The clamp selector, read out of the stylesheet rather than copied here. A
   test that carries its own copy of the thing under test passes for ever. */
const CLAMP = (function () {
  const m = css.match(/\n(\.wday-meal:nth-last-child\(\d\)[^{]*?)\s*\{\s*-webkit-line-clamp:\s*1;/);
  if (!m) throw new Error('could not find the one-line clamp rule in kitchen.css');
  return m[1].replace(/\s*\n\s*/g, ' ').trim();
}());

const today = new Date();
const iso = (d) => d.toISOString().slice(0, 10);
const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
                   'Friday', 'Saturday'];

let asked = null;                 // the URL the display last fetched

function meal(name) {
  return { meal: name, eaters: ['Ann'], headCount: 1, guests: 0, note: '',
           tags: [], image: null, serves: 2, ingredients: [] };
}

/* `counts` is how many meals each day gets, first day being today. */
function feed(counts) {
  const days = counts.map((n, i) => {
    const d = new Date(today); d.setDate(d.getDate() + i);
    return {
      date: iso(d), day: 'x', name: DAY_NAMES[d.getDay()], isToday: i === 0,
      cook: 'Ann', headCount: 1, notEating: [],
      meals: Array.from({ length: n },
        (_, k) => meal('Chicken and Chorizo Traybake ' + (k + 1))),
    };
  });
  return {
    today: iso(today), date: iso(today), rolling: true,
    week: iso(today), from: iso(today),
    display: {
      accent: 'green', theme: 'dark', scale: 100, showCook: true,
      showHeads: true, showClock: true, showDate: true, showWeek: true,
      showPhotos: true, showEmpty: true, showShopping: true,
      dim: false, dimFrom: '22:00', dimTo: '06:30', dimLevel: 45,
    },
    bell: { ready: false, showButton: false },
    extras: [], knownExtras: [], household: [],
    days, todayMeals: days[0].meals, todayCook: 'Ann', todayNotEating: [],
  };
}

const windows = [];
function boot(counts) {
  const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://hub/kitchen' });
  const win = dom.window;
  win.XMLHttpRequest = function () {
    this.open = function (m, u) { this._m = m; if (m === 'GET') asked = u; };
    this.setRequestHeader = function () {};
    this.send = function () {
      this.readyState = 4;
      this.status = 200;
      this.responseText = JSON.stringify(feed(counts));
      if (this.onreadystatechange) this.onreadystatechange();
    };
  };
  win.eval(js);
  windows.push(win);
  return win;
}

function columns(win) {
  return Array.prototype.slice.call(win.document.getElementById('week').children);
}

// ------------------------------------------------------ how far it looks

console.log('the look-ahead');
{
  const win = boot([1, 1, 1, 1, 1, 1]);
  ok('asks for six days, not seven', /[?&]days=6(&|$)/.test(asked || ''),
    asked);
  ok('starting from today', /[?&]from=today(&|$)/.test(asked || ''), asked);
  ok('and draws six columns', columns(win).length === 6,
    'got ' + columns(win).length);
  ok('the first is today', columns(win)[0].className.indexOf('is-today') >= 0);
  ok('and no other is', columns(win).filter(
    (c) => c.className.indexOf('is-today') >= 0).length === 1);
}

// ------------------------------------------------- how many lines a name gets

console.log('the line clamp');
{
  // One meal: two lines, so the clamp-to-one rule must claim nothing.
  const win = boot([1, 1, 1, 1, 1, 1]);
  const col = columns(win)[0];
  ok('a column with one meal has it clamped to two',
    col.querySelectorAll(CLAMP).length === 0,
    col.querySelectorAll(CLAMP).length + ' claimed for one line');
}
{
  const win = boot([2, 1, 1, 1, 1, 1]);
  const col = columns(win)[0];
  ok('two meals still get two lines each',
    col.querySelectorAll(CLAMP).length === 0,
    col.querySelectorAll(CLAMP).length + ' claimed for one line');
}
{
  const win = boot([3, 1, 1, 1, 1, 1]);
  const col = columns(win)[0];
  const claimed = col.querySelectorAll(CLAMP);
  ok('three meals drop to one line', claimed.length === 3,
    'claimed ' + claimed.length + ' of 3');
  ok('and it is the meals that were claimed, not the day name',
    Array.prototype.every.call(claimed,
      (n) => n.className.indexOf('wday-meal') === 0));
}
{
  /* renderWeek only ever draws three, however many the day has. If that cap
     ever moves, the selector - which is written for exactly three - has to
     move with it, and this is what says so. */
  const win = boot([5, 1, 1, 1, 1, 1]);
  const col = columns(win)[0];
  ok('a day with five meals still only draws three',
    col.querySelectorAll('.wday-meal').length === 3,
    'drew ' + col.querySelectorAll('.wday-meal').length);
  ok('and all three are on one line',
    col.querySelectorAll(CLAMP).length === 3);
}
{
  // An empty day puts a "-" in the column, which must not be mistaken for a
  // meal by a selector that counts positions.
  const win = boot([0, 1, 1, 1, 1, 1]);
  const col = columns(win)[0];
  ok('an empty day draws a dash and no meals',
    col.querySelectorAll('.wday-empty').length === 1
    && col.querySelectorAll('.wday-meal').length === 0);
  ok('and the clamp rule claims nothing in it',
    col.querySelectorAll(CLAMP).length === 0);
}

// ------------------------------------------- the ellipsis is actually asked for

console.log('the stylesheet says truncate, not just hide');
{
  const block = css.match(/\n\.wday-meal \{([\s\S]*?)\}/);
  ok('the strip clamps its meal names', !!block
    && /-webkit-line-clamp:\s*2/.test(block[1])
    && /-webkit-box-orient:\s*vertical/.test(block[1])
    && /display:\s*-webkit-box/.test(block[1]),
    'a clamp needs all three of display, box-orient and line-clamp');

  const card = css.match(/\n\.meal-name \{([\s\S]*?)\}/);
  ok('and so does the big card', !!card
    && /-webkit-line-clamp:\s*3/.test(card[1])
    && /display:\s*-webkit-box/.test(card[1]));
}

windows.forEach((w) => w.close());
console.log('');
if (failures) {
  console.log(failures + ' failed');
  process.exit(1);
}
console.log('all passed');
process.exit(0);
