/* The Settings tab's collapsed sections, correcting a line on the shopping
   list, and the drawer where remembered names get thrown out.

   Three things here are only true once app.js is running in a page.

   The settings cards are <details>, which means the browser owns the open and
   shut of them - so what is worth checking is that every card really is one,
   that none of them arrives open, and that the sections app.js hides when the
   planner isn't running under Home Assistant are still hidden as <details>
   rather than quietly appearing.

   The rename is a row that turns into a field and back. What it posts, what it
   posts when nothing was changed (nothing), and that Escape leaves no trace.

   And the history section fetches on open rather than on boot - which is the
   whole reason it is worth collapsing - so the test has to prove the request
   does not happen until the section is opened.

   Run: node tests/browser/test_settings_and_rename.js */

const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const DIR = path.join(ROOT, 'static');

const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
const monday = d.toISOString().slice(0, 10);
const today = new Date().toISOString().slice(0, 10);
const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

const week = {}; DAYS.forEach(k => week[k] = { cookId: null, sittings: [] });

const DATA = {
  people: [{ id: 'p_a', name: 'Ann', color: '#3d8361' }],
  weeks: { [monday]: week },
  palette: ['#3d8361'],
  meals: [],
  today, thisWeek: monday,
};

/* Two lines on the standing list, one of them spelled wrong. */
let extras = [
  { id: 'x1', item: 'Coke Xero', qty: 2, unit: 'each', state: 'need', orderedAt: '' },
  { id: 'x2', item: 'Foil', qty: 1, unit: 'each', state: 'need', orderedAt: '' },
];
let knownExtras = ['Coke Xero', 'Foil', 'Birthday Candles'];
let history = [
  { key: 'coke xero', item: 'Coke Xero', used: 1, at: '2026-08-01' },
  { key: 'foil', item: 'Foil', used: 12, at: '2026-08-10' },
  { key: 'birthday candle', item: 'Birthday Candles', used: 1, at: '2026-03-02' },
];

const SHOPPING = () => ({
  week: monday, weekEnd: monday, generated: today,
  items: [], staples: [], missing: [], mealsPlanned: 0, mealsCounted: 0,
  extras, knownExtras,
});

const dom = new JSDOM(fs.readFileSync(DIR + '/index.html', 'utf8'),
  { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost/' });
const { window } = dom;

const posted = [];
const fetched = [];

window.fetch = (url, opts) => {
  const method = (opts && opts.method) || 'GET';
  fetched.push([method, url]);
  if (method !== 'GET') posted.push([url, JSON.parse((opts && opts.body) || '{}')]);

  let body = DATA;
  if (url.indexOf('/api/shopping') === 0) body = SHOPPING();
  else if (url.indexOf('/api/extras/history') === 0) body = { history };
  else if (url.indexOf('/api/extras/rename') === 0) {
    /* What the server does: the word changes, everything else survives, and
       the misspelling stops being suggested. */
    const sent = JSON.parse(opts.body);
    const was = (extras.find(e => e.id === sent.id) || {}).item;
    extras = extras.map(e => e.id === sent.id ? Object.assign({}, e, { item: sent.item }) : e);
    // The server retires the old spelling and credits the new one, so the
    // suggestions that come back have the correction in place of the mistake.
    history = history.map(r => r.item === was
      ? { key: sent.item.toLowerCase(), item: sent.item, used: r.used, at: today }
      : r);
    knownExtras = history.map(r => r.item);
    body = { ok: true, extras, knownExtras };
  } else if (url.indexOf('/api/extras/forget') === 0) {
    const sent = JSON.parse(opts.body);
    history = history.filter(r => sent.keys.indexOf(r.key) < 0);
    knownExtras = history.map(r => r.item);
    body = { ok: true, history, knownExtras };
  } else if (url.indexOf('/api/cast') === 0) body = { available: false, devices: [] };
  else if (url.indexOf('/api/bell') === 0) body = { available: false };
  else if (url.indexOf('/api/display') === 0) body = null;
  else if (url.indexOf('/api/backup/info') === 0) {
    body = { contents: {}, version: '1.21.0', undo: [], suggestedName: 'b.zip' };
  }

  return Promise.resolve({
    ok: true, status: 200, headers: { get: () => null },
    json: () => Promise.resolve(body),
  });
};
window.scrollBy = window.scrollTo = () => {};
window.matchMedia = window.matchMedia || (q => ({ matches: false, media: q,
  addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
window.navigator.serviceWorker = undefined;

const fails = [];
const ok = (l, c) => { if (!c) fails.push(l); };
const doc = window.document;
const $ = id => doc.getElementById(id);
const click = n => n.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
const down = n => n.dispatchEvent(new window.MouseEvent('mousedown',
  { bubbles: true, cancelable: true }));
const key = (n, k) => n.dispatchEvent(new window.KeyboardEvent('keydown',
  { key: k, bubbles: true, cancelable: true }));

/* jsdom implements <details> as an element but does not run the browser's own
   "clicking the summary toggles it" behaviour, so open it the way the browser
   would and fire the event app.js listens for. */
function openDetails(id) {
  const box = $(id);
  box.open = true;
  box.dispatchEvent(new window.Event('toggle'));
  return box;
}

const CARDS = ['people-card', 'cast-card', 'display-card', 'bell-card',
               'history-card', 'backup-card'];

window.eval(fs.readFileSync(DIR + '/app.js', 'utf8'));

const tick = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  await tick(300);

  // ---------------------------------------------- every card is a shut drawer

  CARDS.forEach(id => {
    const card = $(id);
    ok(id + ' exists', !!card);
    if (!card) return;
    ok(id + ' is a <details>', card.tagName.toLowerCase() === 'details');
    /* The whole point. A settings tab that arrives with six sections open is
       the settings tab this replaced. */
    ok(id + ' starts shut', card.open === false);
    const head = card.querySelector(':scope > summary.settings-head');
    ok(id + ' has a heading row', !!head);
    if (head) {
      ok(id + ' heading carries an icon', !!head.querySelector('svg.settings-ico'));
      ok(id + ' heading names the section',
         !!head.querySelector('h2') && head.querySelector('h2').textContent.trim().length > 0);
    }
    /* Everything below the heading is in one wrapper, which is what the
       offline styling dims and what the padding hangs off. */
    ok(id + ' has a body', !!card.querySelector(':scope > .settings-body'));
  });

  // The two Home-Assistant-only sections are still hidden when there is no
  // Home Assistant. Becoming a <details> must not have made them visible.
  window.location.hash = 'settings';
  await tick(150);
  ok('the cast section stays hidden without Home Assistant', $('cast-card').hidden === true);
  ok('the bell section stays hidden without Home Assistant', $('bell-card').hidden === true);
  ok('the household section is never hidden', $('people-card').hidden === false);
  ok('the history section is never hidden', $('history-card').hidden === false);

  // ------------------------------------------- the names are not fetched yet

  /* The reason for collapsing this one: two hundred names with counts on them
     have no business riding along with a page whose first job is this week's
     dinners. */
  ok('the remembered names are not fetched until the section is opened',
     fetched.every(([, url]) => url.indexOf('/api/extras/history') < 0));

  openDetails('history-card');
  await tick(150);
  ok('opening the section fetches them',
     fetched.some(([, url]) => url.indexOf('/api/extras/history') === 0));

  let rows = [...doc.querySelectorAll('#history-list .history-row')];
  ok('a row per remembered name (got ' + rows.length + ')', rows.length === 3);
  ok('the name is shown',
     rows[0].querySelector('.history-name').textContent === 'Coke Xero');
  ok('with how often and how long ago',
     /×1/.test(rows[0].querySelector('.history-meta').textContent));
  ok('and the count is reported',
     /3 names remembered/.test($('history-note').textContent));

  // ---- the search box narrows it

  $('history-search').value = 'candle';
  $('history-search').dispatchEvent(new window.Event('input', { bubbles: true }));
  rows = [...doc.querySelectorAll('#history-list .history-row')];
  ok('search narrows to one (got ' + rows.length + ')', rows.length === 1);
  ok('and it is the right one',
     rows[0].querySelector('.history-name').textContent === 'Birthday Candles');
  ok('the note says how many are shown',
     /1 shown/.test($('history-note').textContent));

  // ---- the x removes it from the suggestions, by key

  posted.length = 0;
  click(rows[0].querySelector('.history-drop'));
  await tick(150);
  ok('the x posts a forget', posted.length === 1);
  ok('to the forget endpoint', posted[0] && posted[0][0] === '/api/extras/forget');
  /* By the stored key, not the displayed name: the key is what the file is
     keyed on, and the two are deliberately different. */
  ok('naming the key rather than the words',
     posted[0] && JSON.stringify(posted[0][1]) === JSON.stringify({ keys: ['birthday candle'] }));

  $('history-search').value = '';
  $('history-search').dispatchEvent(new window.Event('input', { bubbles: true }));
  rows = [...doc.querySelectorAll('#history-list .history-row')];
  ok('the row is gone afterwards (got ' + rows.length + ')', rows.length === 2);

  // The suggestions under the "Also needed" box follow immediately: the reason
  // anybody is on this screen is that a name keeps coming up.
  const suggested = () => [...doc.querySelectorAll('#extras-known option')]
    .map(o => o.value);
  ok('and it stops being suggested', suggested().indexOf('Birthday Candles') < 0);

  // ------------------------------------------------ correcting a line by tap

  window.location.hash = 'shopping';
  await tick(250);

  const nameBtn = () => [...doc.querySelectorAll('#extras-list .extras-name')]
    .find(b => b.textContent === 'Coke Xero' || b.textContent === 'Coke Zero');

  let btn = nameBtn();
  ok('the name on a row is a button', !!btn && btn.tagName.toLowerCase() === 'button');
  ok('and says what tapping it does', !!btn && /correct/i.test(btn.title));

  // ---- Escape backs out without posting anything

  posted.length = 0;
  click(btn);
  let field = doc.querySelector('#extras-list .extras-edit input');
  ok('tapping it opens a field', !!field);
  ok('with the current wording in it', field && field.value === 'Coke Xero');
  field.value = 'Something else';
  key(field, 'Escape');
  await tick(50);
  ok('Escape posts nothing', posted.length === 0);
  ok('and puts the row back', !doc.querySelector('#extras-list .extras-edit'));
  ok('with the wording untouched', !!nameBtn() && nameBtn().textContent === 'Coke Xero');

  // ---- unchanged text is not a rename either

  click(nameBtn());
  field = doc.querySelector('#extras-list .extras-edit input');
  key(field, 'Enter');
  await tick(50);
  ok('leaving it as it was posts nothing', posted.length === 0);
  ok('and closes the field', !doc.querySelector('#extras-list .extras-edit'));

  // ---- the correction itself

  click(nameBtn());
  field = doc.querySelector('#extras-list .extras-edit input');
  field.value = 'Coke Zero';
  key(field, 'Enter');
  await tick(150);
  ok('Enter posts the rename', posted.length === 1);
  ok('to the rename endpoint', posted[0] && posted[0][0] === '/api/extras/rename');
  ok('carrying the row it belongs to and the new wording',
     posted[0] && JSON.stringify(posted[0][1]) ===
       JSON.stringify({ id: 'x1', item: 'Coke Zero' }));
  ok('the row now reads the corrected way',
     !!nameBtn() && nameBtn().textContent === 'Coke Zero');
  ok('the field has closed', !doc.querySelector('#extras-list .extras-edit'));

  /* The half that is easy to forget: the box was still offering the
     misspelling, which is exactly how it got typed in the first place.

     The corrected spelling is deliberately not checked for here - it is on the
     list now, and renderExtraSuggestions() leaves anything on the list out of
     the datalist, because suggesting a line two inches above the box is only
     ever an invitation to add it twice. */
  ok('the misspelling stops being suggested', suggested().indexOf('Coke Xero') < 0);
  /* Nothing is left to suggest at this point: the two remaining remembered
     names are both on the list. That the datalist emptied rather than keeping
     the stale set is what says the answer was taken and re-drawn. */
  ok('the box was re-drawn from the answer (got ' +
     JSON.stringify(suggested()) + ')', suggested().length === 0);

  // ---- the Save button works from mousedown, not click
  //
  // A click fires after the field has lost focus, and on the phones that
  // scroll the keyboard away on blur the button has moved out from under the
  // thumb by then.

  posted.length = 0;
  click(nameBtn());
  field = doc.querySelector('#extras-list .extras-edit input');
  field.value = 'Diet Coke';
  const save = [...doc.querySelectorAll('#extras-list .extras-edit .btn')]
    .find(b => b.textContent === 'Save');
  ok('there is a Save button', !!save);
  down(save);
  await tick(150);
  ok('pressing it saves', posted.length === 1 &&
     posted[0][1].item === 'Diet Coke');

  // ---- ticking and editing do not happen at once

  posted.length = 0;
  const tickbox = doc.querySelector('#extras-list .extras-tick');
  tickbox.checked = true;
  tickbox.dispatchEvent(new window.Event('change', { bubbles: true }));
  ok('ticking a row raises the bar', $('extras-bar').hidden === false);
  click(doc.querySelector('#extras-list .extras-name'));
  ok('opening a field puts the bar away', $('extras-bar').hidden === true);

  if (fails.length) {
    console.log('FAILED (' + fails.length + ')');
    fails.forEach(f => console.log('  - ' + f));
    process.exit(1);
  }
  console.log('settings sections + rename: all good');
  process.exit(0);
})();
