/* The drag handle: a real pointer drag, the keyboard fallback, and the guest
   slot staying pinned to the end.

   Written with await rather than nested timeouts. Every action here kicks off a
   POST and a refresh, and guessing how long that takes is how the first version
   of this file ended up asserting against a list the app had already moved on
   from. `settle()` waits for the app, and each section re-reads the order from
   the DOM the app has just drawn rather than carrying one forward. */
const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const DIR = path.join(ROOT, 'static');
const SRV = path.join(ROOT, 'server.py');
const PALETTE = fs.readFileSync(SRV, 'utf8')
  .match(/^COLORS = \[([\s\S]*?)\]/m)[1].match(/#[0-9a-f]{6}/g);

const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
const monday = d.toISOString().slice(0, 10);
const DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
const week = {}; DAYS.forEach(k => week[k] = { cookId: null, sittings: [] });

const DATA = {
  people: [
    { id:'p_a', name:'Ann',   color:'#ff0000' },
    { id:'p_b', name:'Bob',   color:'#ffff00' },
    { id:'p_c', name:'Cal',   color:'#0000ff' },
    { id:'p_g', name:'Guest', color:'#00ff00', guest:true },
  ],
  meals: [], weeks: { [monday]: week }, palette: PALETTE,
  today: new Date().toISOString().slice(0, 10), thisWeek: monday,
};

const dom = new JSDOM(fs.readFileSync(DIR + '/index.html', 'utf8'),
  { runScripts:'outside-only', pretendToBeVisual:true, url:'http://localhost/' });
const { window } = dom;

// jsdom has neither PointerEvent nor layout, so both are supplied here.
window.PointerEvent = window.MouseEvent;
window.Element.prototype.setPointerCapture = function () {};
window.Element.prototype.releasePointerCapture = function () {};
const ROW_H = 50;
window.Element.prototype.getBoundingClientRect = function () {
  const list = this.closest && this.closest('#person-list');
  const movable = this.classList && (this.classList.contains('person-row') ||
                                     this.classList.contains('person-gap'));
  if (!list || !movable) return { top:0,bottom:0,height:0,left:0,right:0,width:0 };
  // The lifted row is position:fixed and out of flow, so the rows below it
  // close up. Model that, or the midpoints are the ones from before the drag.
  const sibs = [...list.children].filter(
    n => n === this || n.style.position !== 'fixed');
  const top = this.style.position === 'fixed'
    ? parseFloat(this.style.top) : sibs.indexOf(this) * ROW_H;
  return { top, bottom: top + ROW_H, height: ROW_H, left: 0, right: 300, width: 300 };
};

const posted = [];
window.fetch = (url, opts) => {
  if (opts && opts.method && opts.method !== 'GET') {
    posted.push([url, opts]);
    // Stateful, like the real server: otherwise every refresh puts the
    // household back as it started and the next assertion is meaningless.
    if (String(url).indexOf('/api/people/order') !== -1) {
      const ids = JSON.parse(opts.body).ids;
      const by = {}; DATA.people.forEach(p => by[p.id] = p);
      const guests = ids.filter(i => by[i].guest);
      DATA.people = ids.filter(i => !by[i].guest).concat(guests).map(i => by[i]);
    }
  }
  return Promise.resolve({ ok:true, status:200, headers:{ get:()=>null },
                           json:()=>Promise.resolve(DATA) });
};
window.scrollBy = window.scrollTo = () => {};
window.matchMedia = window.matchMedia || (q => ({ matches:false, media:q,
  addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){} }));
window.navigator.serviceWorker = undefined;

const fails = [];
const ok = (l, c) => { if (!c) fails.push(l); };
const settle = () => new Promise(r => setTimeout(r, 60));
const click = n => n.dispatchEvent(new window.MouseEvent('click', { bubbles:true }));
const key = (n, k) => n.dispatchEvent(
  new window.KeyboardEvent('keydown', { key:k, bubbles:true }));
const pointer = (n, type, y) => {
  const e = new window.MouseEvent(type, { bubbles:true, clientY:y, button:0 });
  e.pointerId = 1;
  n.dispatchEvent(e);
};

window.eval(fs.readFileSync(DIR + '/app.js', 'utf8'));

(async () => {
  await settle();
  const doc = window.document;
  const list = doc.getElementById('person-list');

  // Redraw from state, so each section starts from what the app believes.
  const openSettings = async () => {
    click(doc.querySelector('.tab[data-view="week"]'));
    click(doc.querySelector('.tab[data-view="settings"]'));
    await settle();
  };
  const rowIds = () => [...list.querySelectorAll('.person-row')].map(r => r.dataset.id);
  const inFlow = () => [...list.children]
    .filter(n => n.style.position !== 'fixed')
    .map(n => n.classList.contains('person-gap') ? 'GAP' : n.dataset.id);
  const handleFor = id => list.querySelector(
    '.person-row[data-id="' + id + '"] .drag-handle');
  const lastOrder = () => {
    const call = posted.filter(p => String(p[0]).indexOf('/api/people/order') !== -1).pop();
    return call ? JSON.parse(call[1].body).ids : null;
  };

  await openSettings();

  // ---- the handle replaces the arrows
  ok('no arrow buttons remain', doc.querySelectorAll('.move-btn').length === 0);
  ok('a handle on each real person (got ' + list.querySelectorAll('.drag-handle').length + ')',
     list.querySelectorAll('.drag-handle').length === 3);
  ok('the guest has no handle, but keeps the column',
     list.querySelectorAll('.person-row.is-guest .drag-spacer').length === 1);

  /* The guest slot is a fixture, not a member of the household: nothing on its
     row offers to rename, remove or move it, and there is no caption under it
     explaining what it is. It keeps its colour disc - the "+ 2 guests" chip
     sits among the names on a meal and has to be told apart from them. */
  const guestRow = list.querySelector('.person-row.is-guest');
  ok('the guest has no buttons but its colour disc',
     [...guestRow.querySelectorAll('button')]
       .every(b => b.classList.contains('dot-btn')));
  ok('and no caption under its name',
     !guestRow.querySelector('.person-note'));
  ok('everyone else still has Rename and Remove',
     [...list.querySelectorAll('.person-row:not(.is-guest)')]
       .every(r => r.querySelectorAll('.icon-btn:not(.drag-handle)').length === 2));
  ok('the grip is six dots',
     handleFor('p_a').querySelectorAll('.grip circle').length === 6);
  ok('and it says what it is and how else to use it',
     /Drag to reorder, or use the arrow keys/.test(
       handleFor('p_a').getAttribute('aria-label')));

  // ---- drag the first person down past the others
  let before = rowIds();
  let h = handleFor(before[0]);
  pointer(h, 'pointerdown', 10);
  ok('a gap opens where the row was', !!list.querySelector('.person-gap'));
  ok('the row is lifted out of the list',
     list.querySelector('.person-row[data-id="' + before[0] + '"]')
         .classList.contains('dragging'));

  pointer(h, 'pointermove', 130);
  ok('the gap follows the pointer (got ' + JSON.stringify(inFlow()) + ')',
     JSON.stringify(inFlow()) ===
     JSON.stringify([before[1], before[2], 'GAP', 'p_g']));

  posted.length = 0;
  pointer(h, 'pointerup', 130);
  ok('the gap is cleaned up', !list.querySelector('.person-gap'));
  await settle();

  ok('dropping posts the whole order', !!lastOrder());
  ok('with the person moved to the end of the real people (got ' +
     JSON.stringify(lastOrder()) + ')',
     JSON.stringify(lastOrder()) ===
     JSON.stringify([before[1], before[2], before[0], 'p_g']));

  // ---- the guest cannot be passed
  await openSettings();
  before = rowIds();
  h = handleFor(before[0]);
  pointer(h, 'pointerdown', 10);
  pointer(h, 'pointermove', 900);          // way past the guest
  ok('the gap never goes below the guest (got ' + JSON.stringify(inFlow()) + ')',
     inFlow().indexOf('GAP') < inFlow().indexOf('p_g'));
  pointer(h, 'pointerup', 900);
  await settle();

  // ---- a tap on the grip is not a drag
  await openSettings();
  posted.length = 0;
  h = handleFor(rowIds()[0]);
  pointer(h, 'pointerdown', 10);
  pointer(h, 'pointerup', 10);
  await settle();
  ok('a tap with no movement saves nothing', posted.length === 0);
  ok('and leaves no gap behind', !list.querySelector('.person-gap'));

  // ---- Escape puts it back
  await openSettings();
  before = rowIds();
  posted.length = 0;
  h = handleFor(before[0]);
  pointer(h, 'pointerdown', 10);
  pointer(h, 'pointermove', 130);
  key(doc, 'Escape');
  await settle();
  ok('Escape saves nothing', posted.length === 0);
  ok('and leaves no gap behind', !list.querySelector('.person-gap'));
  ok('and the order is as it was (got ' + JSON.stringify(rowIds()) + ')',
     JSON.stringify(rowIds()) === JSON.stringify(before));

  // ---- keyboard
  await openSettings();
  before = rowIds();
  const want = before.slice();
  want.splice(1, 0, want.splice(0, 1)[0]);
  posted.length = 0;
  key(handleFor(before[0]), 'ArrowDown');
  await settle();
  ok('arrow keys on the handle move the person', !!lastOrder());
  ok('one place down (' + JSON.stringify(before) + ' -> ' +
     JSON.stringify(lastOrder()) + ')',
     JSON.stringify(lastOrder()) === JSON.stringify(want));
  ok('and the guest stays last', lastOrder().slice(-1)[0] === 'p_g');

  await openSettings();
  posted.length = 0;
  key(handleFor(rowIds()[0]), 'ArrowUp');
  await settle();
  ok('the top person cannot go up', posted.length === 0);

  posted.length = 0;
  const ids = rowIds();
  key(handleFor(ids[ids.length - 2]), 'ArrowDown');
  await settle();
  ok('the last real person cannot pass the guest', posted.length === 0);

  if (fails.length) {
    console.log('FAILED (' + fails.length + ')');
    fails.forEach(f => console.log('  - ' + f));
    process.exit(1);
  }
  console.log('ui drag handle: all good');
  process.exit(0);
})();
