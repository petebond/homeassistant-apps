/* Chip ordering, the reorder arrows, and the star picker's tones. */
const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const DIR = path.join(ROOT, 'static');
const SRV = path.join(ROOT, 'server.py');
const PALETTE = fs.readFileSync(SRV,'utf8')
  .match(/^COLORS = \[([\s\S]*?)\]/m)[1].match(/#[0-9a-f]{6}/g);

const d = new Date(); d.setDate(d.getDate()-((d.getDay()+6)%7));
const monday = d.toISOString().slice(0,10);
const today = new Date().toISOString().slice(0,10);
const DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
const todayDay = DAYS[(new Date().getDay()+6)%7];

// Household order: Ann, Bob, Cal, then the guest.
const people = [
  { id:'p_a', name:'Ann', color:'#ff0000' },
  { id:'p_b', name:'Bob', color:'#ffff00' },   // takes dark ink
  { id:'p_c', name:'Cal', color:'#0000ff' },
  { id:'p_g', name:'Guest', color:'#00ff00', guest:true },
];
const week = {}; DAYS.forEach(k => week[k] = { cookId:null, sittings:[] });
// Tapped in reverse: Cal, Bob, Ann.
week[todayDay].sittings = [{ id:'s1', mealId:'m1',
  eaters:['p_c','p_b','p_a'], guests:0, note:'', ratings:{} }];

const DATA = { people, weeks:{ [monday]: week }, palette:PALETTE,
  meals:[{ id:'m1', name:'Fish pie', tags:['fast'], links:[], notes:'',
           ingredients:[], serves:4, macros:null, image:null }],
  today, thisWeek:monday };

const dom = new JSDOM(fs.readFileSync(DIR+'/index.html','utf8'),
  { runScripts:'outside-only', pretendToBeVisual:true, url:'http://localhost/' });
const { window } = dom;
const posted = [];
window.fetch = (url, opts) => {
  if (opts && opts.method && opts.method !== 'GET') posted.push([url, opts]);
  return Promise.resolve({ ok:true, status:200, headers:{get:()=>null},
                           json:()=>Promise.resolve(DATA) });
};
window.scrollBy = window.scrollTo = ()=>{};
window.matchMedia = window.matchMedia || (q=>({matches:false,media:q,
  addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}}));
window.navigator.serviceWorker = undefined;

const fails = [];
const ok = (l,c) => { if(!c) fails.push(l); };
const click = n => n.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));

window.eval(fs.readFileSync(DIR+'/app.js','utf8'));

setTimeout(() => {
  const doc = window.document;

  // ---- chips on the week card come out in household order, not tap order
  const chips = [...doc.querySelectorAll('#w-grid .sitting .chip')]
    .map(c => c.textContent);
  ok('chips are in household order, not tap order (got '+JSON.stringify(chips)+')',
     JSON.stringify(chips) === JSON.stringify(['Ann','Bob','Cal']));

  // ---- and each still carries readable lettering
  const inkOf = name => {
    const c = [...doc.querySelectorAll('#w-grid .chip')].find(x=>x.textContent===name);
    return c.style.color.replace(/\s/g,'');
  };
  ok('Bob on yellow gets dark lettering (got '+inkOf('Bob')+')',
     inkOf('Bob') === 'rgb(27,26,23)');
  ok('Cal on blue gets white lettering (got '+inkOf('Cal')+')',
     inkOf('Cal') === 'rgb(255,255,255)');

  // ---- the star picker's tones follow the person
  const bobChip = [...doc.querySelectorAll('#w-grid .chip-rate')]
    .find(c => c.textContent === 'Bob');
  ok('the chip is rateable today', !!bobChip);
  if (bobChip) {
    click(bobChip);
    const pop = doc.querySelector('.star-pop');
    ok('the star picker opens', !!pop);
    if (pop) {
      const on = pop.style.getPropertyValue('--star-on').trim();
      const wash = pop.style.getPropertyValue('--star-wash').trim();
      // Gold #ffd452 on yellow #ffff00 is 1.32:1, so it must fall back.
      ok('on yellow the earned star falls back to the ink (got '+on+')',
         on === '#1b1a17');
      ok('and the wash goes dark (got '+wash+')', wash === 'rgba(0,0,0,.16)');
      click(doc.body);
    }
  }
  const calChip = [...doc.querySelectorAll('#w-grid .chip-rate')]
    .find(c => c.textContent === 'Cal');
  if (calChip) {
    click(calChip);
    const pop = doc.querySelector('.star-pop');
    const on = pop && pop.style.getPropertyValue('--star-on').trim();
    ok('on deep blue the star keeps its gold (got '+on+')', on === '#ffd452');
    click(doc.body);
  }

  // The household list and its drag handle are covered in uitest3.js.
  if (fails.length) {
    console.log('FAILED ('+fails.length+')');
    fails.forEach(f => console.log('  - '+f));
    process.exit(1);
  }
  console.log('ui ordering + star tones: all good');
  process.exit(0);
}, 300);
