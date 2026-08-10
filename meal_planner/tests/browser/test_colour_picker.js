/* Drives the real app.js in a DOM against a fake /api/data, to check the parts
   of the colour picker and the week navigation that only exist in the browser. */
const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const DIR = path.join(ROOT, 'static');
const SRV = path.join(ROOT, 'server.py');

const PALETTE = fs.readFileSync(SRV, 'utf8')
  .match(/^COLORS = \[([\s\S]*?)\]/m)[1].match(/#[0-9a-f]{6}/g);

const people = [
  { id:'p_a', name:'Ann',  color:'#ff0000' },
  { id:'p_b', name:'Bob',  color:'#0000ff' },
  { id:'p_g', name:'Guest', color:'#ffff00', guest:true },
];
const thisMonday = (() => { const d=new Date(); d.setDate(d.getDate()-((d.getDay()+6)%7));
  return d.toISOString().slice(0,10); })();

const DATA = { people, meals:[], weeks:{}, palette:PALETTE,
               today:new Date().toISOString().slice(0,10), thisWeek:thisMonday };

const dom = new JSDOM(fs.readFileSync(DIR+'/index.html','utf8'), {
  runScripts:'outside-only', pretendToBeVisual:true, url:'http://localhost/'
});
const { window } = dom;
window.fetch = (url) => Promise.resolve({
  ok:true, status:200, headers:{ get:()=>null }, json:()=>Promise.resolve(DATA)
});
window.scrollBy = window.scrollTo = function(){ window.__scrolled = [...arguments]; };
window.matchMedia = window.matchMedia || (q => ({ matches:false, media:q,
  addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){} }));
window.navigator.serviceWorker = undefined;

const fails = [];
const ok = (label, cond) => { if (!cond) fails.push(label); };

window.eval(fs.readFileSync(DIR+'/app.js','utf8'));

setTimeout(() => {
  const doc = window.document;

  // Settings view, so renderPeople runs.
  doc.querySelector('.tab[data-view="settings"]').dispatchEvent(
    new window.MouseEvent('click', { bubbles:true }));

  const dots = doc.querySelectorAll('#person-list .dot-btn');
  ok('every person gets a tappable disc (got '+dots.length+')', dots.length === 3);
  ok('the disc wears the person\'s colour',
     dots[0] && dots[0].style.background.replace(/\s/g,'') === 'rgb(255,0,0)');

  // Open Ann's picker.
  dots[0].dispatchEvent(new window.MouseEvent('click', { bubbles:true }));
  const pop = doc.querySelector('.color-pop');
  ok('the picker opens', !!pop);
  const cells = pop ? pop.querySelectorAll('.swatch-cell') : [];
  ok('with all 36 colours (got '+cells.length+')', cells.length === 36);

  const disabled = [...cells].filter(c => c.disabled);
  const disabledColors = disabled.map(c => c.style.background.replace(/\s/g,''));
  ok('two colours are taken by others (got '+disabled.length+')', disabled.length === 2);
  ok('Bob\'s blue is one of them', disabledColors.includes('rgb(0,0,255)'));
  ok('the guest\'s yellow is the other', disabledColors.includes('rgb(255,255,0)'));
  ok('Ann\'s own colour is not disabled',
     !disabledColors.includes('rgb(255,0,0)'));

  const current = pop && pop.querySelector('.swatch-cell.is-current');
  ok('her current colour is marked',
     current && current.style.background.replace(/\s/g,'') === 'rgb(255,0,0)');
  ok('and it is still pressable', current && !current.disabled);

  // Ink: yellow must take dark lettering, blue white.
  const inkOf = hex => [...cells].find(
    c => c.style.background.replace(/\s/g,'') === hex).style.color.replace(/\s/g,'');
  ok('yellow gets dark lettering (got '+inkOf('rgb(255,255,0)')+')',
     inkOf('rgb(255,255,0)') === 'rgb(27,26,23)');
  ok('pure blue gets white lettering (got '+inkOf('rgb(0,0,255)')+')',
     inkOf('rgb(0,0,255)') === 'rgb(255,255,255)');

  // A click anywhere else closes it.
  doc.body.dispatchEvent(new window.MouseEvent('click', { bubbles:true }));
  ok('tapping away closes the picker', !doc.querySelector('.color-pop'));

  // Week navigation: forward a week should land at the top.
  doc.querySelector('.tab[data-view="week"]').dispatchEvent(
    new window.MouseEvent('click', { bubbles:true }));
  window.__scrolled = null;
  doc.getElementById('w-next').dispatchEvent(new window.MouseEvent('click', { bubbles:true }));
  ok('next week scrolls to the top (got '+JSON.stringify(window.__scrolled)+')',
     window.__scrolled && window.__scrolled[0] === 0 && window.__scrolled[1] === 0);
  ok('and the week bar has moved on',
     doc.getElementById('w-range').textContent.length > 0);

  window.__scrolled = null;
  doc.getElementById('w-prev').dispatchEvent(new window.MouseEvent('click', { bubbles:true }));
  ok('back to this week does not slam to the top',
     !(window.__scrolled && window.__scrolled[0] === 0 && window.__scrolled[1] === 0));

  if (fails.length) {
    console.log('FAILED (' + fails.length + ')');
    fails.forEach(f => console.log('  - ' + f));
    process.exit(1);
  }
  console.log('ui: all good');
  process.exit(0);
}, 300);
