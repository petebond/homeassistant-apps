/* The pen on a day card: it opens that one day for changing, in place, and
   the rest of the week stays as it reads.

   Run: node tests/browser/test_day_edit.js  (needs jsdom; see README.md) */
const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');
const DIR = path.join(__dirname, '..', '..', 'static');

const d = new Date(); d.setDate(d.getDate()-((d.getDay()+6)%7));
const monday = d.toISOString().slice(0,10);
const today = new Date().toISOString().slice(0,10);
const DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
const todayDay = DAYS[(new Date().getDay()+6)%7];
const otherDay = todayDay === 'mon' ? 'tue' : 'mon';

const people = [
  { id:'p_a', name:'Ann', color:'#ff0000' },
  { id:'p_b', name:'Bob', color:'#0000ff' },
];
const week = {}; DAYS.forEach(k => week[k] = { cookId:null, sittings:[] });
week[todayDay].sittings = [{ id:'s1', mealId:'m1', eaters:['p_a'], guests:0,
                             note:'', ratings:{} }];
const DATA = { people, weeks:{ [monday]: week }, palette:[],
  meals:[{ id:'m1', name:'Fish pie', tags:[], links:[], notes:'',
           ingredients:[], serves:4, macros:null, image:null }],
  today, thisWeek:monday };

function boot(hash) {
  const dom = new JSDOM(fs.readFileSync(DIR+'/index.html','utf8'),
    { runScripts:'outside-only', pretendToBeVisual:true,
      url:'http://localhost/' + (hash || '') });
  const { window } = dom;
  const sent = [];
  window.fetch = (url, opts) => {
    const method = (opts && opts.method) || 'GET';
    if (method !== 'GET') sent.push([method, url, opts.body && JSON.parse(opts.body)]);
    let body = DATA;
    if (method === 'PUT' && /\/sittings\/s1$/.test(url)) {
      body = Object.assign({}, week[todayDay].sittings[0], JSON.parse(opts.body));
    }
    return Promise.resolve({ ok:true, status:200, headers:{get:()=>null},
                             json:()=>Promise.resolve(body) });
  };
  window.scrollBy = window.scrollTo = ()=>{};
  window.confirm = () => true;
  window.matchMedia = window.matchMedia || (q=>({matches:false,media:q,
    addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}}));
  window.navigator.serviceWorker = undefined;
  window.eval(fs.readFileSync(DIR+'/app.js','utf8'));
  return { window, doc: window.document, sent };
}

const fails = [];
const ok = (l,c) => { if(!c) fails.push(l); };
const wait = ms => new Promise(r => setTimeout(r, ms));
const click = (w, n) => n.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));

(async () => {
  const { window, doc, sent } = boot();
  await wait(300);
  const card = day => doc.querySelector('#w-grid .day-card[data-day="'+day+'"]');

  // ---- no Plan tab, no Plan page
  ok('the Plan tab is gone', !doc.querySelector('.tab[data-view="plan"]'));
  ok('the Plan page is gone', !doc.getElementById('view-plan'));
  ok('the week has its whole-week jobs', !!doc.getElementById('w-copy-last') &&
     !!doc.getElementById('w-clear'));

  // ---- every day has a pen, and nothing is open to start with
  ok('seven pens', doc.querySelectorAll('#w-grid .day-card .day-edit').length === 7);
  ok('no day open at first', !doc.querySelector('#w-grid .day-card.editing'));

  // ---- tapping one opens that day only, in place
  click(window, card(todayDay).querySelector('.day-edit'));
  ok('today opens', card(todayDay).classList.contains('editing'));
  ok('in the same place on the page',
     [...doc.querySelectorAll('#w-grid .day-card')].indexOf(card(todayDay)) ===
     DAYS.indexOf(todayDay));
  ok('it has the meal picker set to Fish pie',
     card(todayDay).querySelector('select') &&
     card(todayDay).querySelector('select').value === 'm1');
  ok('and a Done button', !!card(todayDay).querySelector('.day-done'));
  ok('the other days still read as the week',
     doc.querySelectorAll('#w-grid .day-card.editing').length === 1 &&
     !card(otherDay).querySelector('select'));

  // ---- a change saves and the day stays open
  const bob = [...card(todayDay).querySelectorAll('.toggle')]
    .find(b => b.textContent === 'Bob');
  click(window, bob);
  await wait(100);
  ok('adding Bob is sent', sent.some(([m,u,b]) => m === 'PUT' &&
     /\/sittings\/s1$/.test(u) && b.eaters && b.eaters.indexOf('p_b') !== -1));
  ok('the day is still open after saving', card(todayDay).classList.contains('editing'));

  // ---- opening another day shuts the first
  click(window, card(otherDay).querySelector('.day-edit'));
  ok('the other day opens', card(otherDay).classList.contains('editing'));
  ok('and the first one shuts', !card(todayDay).classList.contains('editing'));
  ok('an empty day offers to add a meal',
     !!card(otherDay).querySelector('.add-meal'));

  // ---- Done shuts it
  click(window, card(otherDay).querySelector('.day-done'));
  ok('Done shuts the day', !doc.querySelector('#w-grid .day-card.editing'));

  // ---- Escape does too
  click(window, card(todayDay).querySelector('.day-edit'));
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key:'Escape', bubbles:true }));
  ok('Escape shuts the day', !doc.querySelector('#w-grid .day-card.editing'));

  // ---- paging to another week shuts it
  click(window, card(todayDay).querySelector('.day-edit'));
  click(window, doc.getElementById('w-next'));
  ok('next week has nothing open', !doc.querySelector('#w-grid .day-card.editing'));
  click(window, doc.getElementById('w-prev'));
  ok('and coming back has nothing open either',
     !doc.querySelector('#w-grid .day-card.editing'));

  // ---- an old #plan link lands on the week
  const old = boot('#plan');
  await wait(300);
  ok('#plan lands on the week', !old.doc.getElementById('view-week').hidden);

  if (fails.length) {
    console.log('FAILED ('+fails.length+')');
    fails.forEach(f => console.log('  - '+f));
    process.exit(1);
  }
  console.log('day edit in place: all good');
  process.exit(0);
})();
