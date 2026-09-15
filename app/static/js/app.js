/* ============================================================
   صرافی — فرانت‌اند (SPA)
   ============================================================ */
"use strict";

/* ---------------- تقویم جلالی ---------------- */
const J = {
  div(a,b){ return Math.trunc(a/b); },
  mod(a,b){ return a - Math.trunc(a/b)*b; },
  g2d(gy,gm,gd){
    let d = J.div((gy + J.div(gm-8,6) + 100100)*1461, 4)
          + J.div(153*J.mod(gm+9,12)+2, 5) + gd - 34840408;
    d = d - J.div(J.div(gy+100100+J.div(gm-8,6),100)*3,4) + 752;
    return d;
  },
  d2g(jdn){
    let j = 4*jdn + 139361631;
    j = j + J.div(J.div(4*jdn+183187720,146097)*3,4)*4 - 3908;
    let i = J.div(J.mod(j,1461),4)*5 + 308;
    let gd = J.div(J.mod(i,153),5) + 1;
    let gm = J.mod(J.div(i,153),12) + 1;
    let gy = J.div(j,1461) - 100100 + J.div(8-gm,6);
    return [gy,gm,gd];
  },
  jalCal(jy){
    const breaks=[-61,9,38,199,426,686,756,818,1111,1181,1210,1635,2060,2097,2192,2262,2324,2394,2456,3178];
    const bl=breaks.length, gy=jy+621;
    let leapJ=-14, jp=breaks[0], jump=0;
    if(jy<jp || jy>=breaks[bl-1]) return {leap:0, gy, march:20};
    for(let i=1;i<bl;i++){
      const jm=breaks[i]; jump=jm-jp;
      if(jy<jm) break;
      leapJ = leapJ + J.div(jump,33)*8 + J.div(J.mod(jump,33),4);
      jp = jm;
    }
    let n = jy-jp;
    leapJ = leapJ + J.div(n,33)*8 + J.div(J.mod(n,33)+3,4);
    if(J.mod(jump,33)===4 && jump-n===4) leapJ++;
    const leapG = J.div(gy,4) - J.div((J.div(gy,100)+1)*3,4) - 150;
    const march = 20 + leapJ - leapG;
    if(jump-n<6) n = n - jump + J.div(jump+4,33)*33;
    let leap = J.mod(J.mod(n+1,33)-1,4);
    if(leap===-1) leap = 4;
    return {leap, gy, march};
  },
  d2j(jdn){
    const g = J.d2g(jdn);
    let jy = g[0]-621;
    const r = J.jalCal(jy);
    const jdn1f = J.g2d(g[0],3,r.march);
    let k = jdn - jdn1f;
    if(k>=0){
      if(k<=185) return [jy, 1+J.div(k,31), J.mod(k,31)+1];
      k -= 186;
    } else {
      jy -= 1; k += 179;
      if(r.leap===1) k += 1;
    }
    const jm = 7 + J.div(k,30);
    const jd = J.mod(k,30)+1;
    return [jy,jm,jd];
  },
  toJalali(gy,gm,gd){ return J.d2j(J.g2d(gy,gm,gd)); },
  j2d(jy,jm,jd){
    const r = J.jalCal(jy);
    return J.g2d(r.gy, 3, r.march) + (jm-1)*31 - J.div(jm,7)*(jm-7) + jd - 1;
  },
  toGregorian(jy,jm,jd){ return J.d2g(J.j2d(jy,jm,jd)); }
};

/* ---------------- حالت سراسری ---------------- */
const state = {
  token: null,
  user: { full_name: 'مدیر سیستم', role: 'admin' },
  currencies: [], parties: [], cashboxes: [],
  section: 'dashboard',
  accountId: null,
  prevToken: null,
  me: null,
};

/* ---------------- ابزار ---------------- */
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function fileToDataURL(file){
  return new Promise((resolve, reject)=>{
    const r = new FileReader();
    r.onload = ()=> resolve(r.result);
    r.onerror = ()=> reject(new Error('خواندن فایل ناموفق بود'));
    r.readAsDataURL(file);
  });
}
let acctFormRemoveLogo = false;
function fmt(minor, dec, ratio){
  const v = (minor||0) / (ratio||1);
  return v.toLocaleString('en-US', {minimumFractionDigits: dec||0, maximumFractionDigits: dec||0});
}

/* ---------------- ماسک اعداد سه‌رقمی + حروف فارسی (v0.9) ---------------- */
const EN_DIG = {'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9'};
function numToEn(s){
  return String(s==null?'':s).replace(/[۰-۹]/g, d=>EN_DIG[d]).replace(/[٫]/g,'.').replace(/[٬،]/g,',');
}
function _numClean(v){ return String(v==null?'':v).replace(/[,\s٬،]/g,'').replace(/[^0-9.\-]/g,''); }
function _digitsBefore(s, pos){
  let c = 0;
  for(let i=0;i<pos&&i<s.length;i++){ if(/[0-9]/.test(s[i])) c++; }
  return c;
}
function _posAfterDigits(s, n){
  let c = 0;
  for(let i=0;i<s.length;i++){ if(/[0-9]/.test(s[i])){ c++; if(c===n) return i+1; } }
  return s.length;
}
function applyNumMask(el, opts){
  opts = opts || {};
  const dec = opts.decimals != null ? opts.decimals : 0;
  const allowNeg = !!opts.allowNegative;
  let raw = numToEn(el.value);
  let neg = '';
  if(allowNeg && /^[+-]/.test(raw)){ neg = raw[0]==='-'?'-':''; }
  raw = _numClean(raw.replace(/^[+-]/,''));
  let parts = raw.split('.');
  let int = (parts[0]||'').replace(/[^0-9]/g,'');
  let frac = parts.slice(1).join('').replace(/[^0-9]/g,'');
  if(dec > 0){ frac = frac.slice(0, dec); } else { frac = ''; }
  int = int.replace(/^0+(?=\d)/,'');
  if(int === '') int = '0';
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const hasFrac = frac.length > 0 || (dec > 0 && raw.indexOf('.') >= 0);
  const disp = (neg?'-':'') + grouped + (hasFrac ? '.'+frac : '');
  el.dataset.raw = (neg?'-':'') + int + (hasFrac ? '.'+frac : '');
  if(el.value !== disp) el.value = disp;
}
function numMask(el, opts){
  if(!el || el.__numMasked) return el;
  el.__numMasked = true;
  el.__numOpts = opts || {};
  el.addEventListener('input', ()=>{
    const pos = el.selectionStart;
    const db = _digitsBefore(el.value, pos);
    applyNumMask(el, el.__numOpts);
    const np = _posAfterDigits(el.value, db);
    try{ el.setSelectionRange(np, np); }catch(_){}
  });
  el.addEventListener('blur', ()=>{ applyNumMask(el, el.__numOpts); });
  applyNumMask(el, el.__numOpts);
  return el;
}
function setNum(el, v){
  if(!el) return;
  el.value = (v==null||v==='') ? '' : String(v);
  applyNumMask(el, el.__numOpts || {});
}
function numVal(el){
  if(!el) return 0;
  if(el.dataset.raw != null && el.dataset.raw !== '') return parseFloat(el.dataset.raw) || 0;
  return parseFloat(_numClean(numToEn(el.value||'0'))) || 0;
}

/* حروف فارسی اعداد */
const FA_ONES = ['','یک','دو','سه','چهار','پنج','شش','هفت','هشت','نه'];
const FA_TEENS = ['ده','یازده','دوازده','سیزده','چهارده','پانزده','شانزده','هفده','هجده','نوزده'];
const FA_TENS = ['','','بیست','سی','چهل','پنجاه','شصت','هفتاد','هشتاد','نود'];
const FA_HUNDREDS = ['','یکصد','دویست','سیصد','چهارصد','پانصد','ششصد','هفتصد','هشتصد','نهصد'];
const FA_SCALES = ['','هزار','میلیون','میلیارد','تریلیون'];
function faTriple(n){
  const h = Math.floor(n/100), t = Math.floor((n%100)/10), o = n%10;
  let s = '';
  if(h) s += FA_HUNDREDS[h];
  if(t === 1){ if(s) s += ' و '; return s + FA_TEENS[o]; }
  if(t){ if(s) s += ' و '; s += FA_TENS[t]; }
  if(o){ if(s) s += ' و '; s += FA_ONES[o]; }
  return s;
}
function numToFaWords(x){
  x = Math.floor(Math.abs(Number(x) || 0));
  if(x === 0) return 'صفر';
  const groups = [];
  let n = x;
  while(n > 0){ groups.push(n % 1000); n = Math.floor(n / 1000); }
  const parts = [];
  for(let i=groups.length-1;i>=0;i--){
    if(groups[i] === 0) continue;
    const t = faTriple(groups[i]);
    parts.push(t + (FA_SCALES[i] ? ' '+FA_SCALES[i] : ''));
  }
  return parts.join(' و ');
}
function tomanStr(rial){
  const t = (rial||0) / 10;
  return (t % 1 === 0) ? fmt(t,0,1) : fmt(t,1,1);
}
function renderNumHint(el, opts){
  const hintEl = document.getElementById(opts.hintId);
  if(!hintEl) return;
  const v = numVal(el);
  if(!v){ hintEl.textContent = ''; return; }
  if(opts.kind === 'amount'){
    const c = opts.cur || (opts.currencyEl ? currencyById(+document.getElementById(opts.currencyEl).value) : null);
    if(!c){ hintEl.textContent = ''; return; }
    const sign = v < 0 ? 'منفی ' : '';
    const a = Math.abs(v);
    const intPart = Math.floor(a);
    const frac = Math.round((a - intPart) * c.unit_ratio);
    let words = numToFaWords(intPart) + ' ' + c.name;
    if(c.decimals > 0 && frac > 0){
      words += ' و ' + numToFaWords(frac) + ' ' + (c.minor_name || 'واحد خُرد');
    }
    hintEl.textContent = sign + words;
  } else { // kind: 'rial' یا 'rate' → معادل تومان
    hintEl.textContent = '= ' + tomanStr(v) + ' تومان';
  }
}
function bindNumField(id, opts){
  const el = document.getElementById(id);
  if(!el) return null;
  opts = opts || {};
  numMask(el, {decimals: opts.decimals || 0, allowNegative: !!opts.allowNegative});
  if(opts.hint){
    opts.hintId = opts.hintId || (id + '-numhint');
    const host = el.closest('div') || el.parentNode;
    host.insertAdjacentHTML('afterend', `<div class="num-hint" id="${opts.hintId}"></div>`);
    el.addEventListener('input', ()=>renderNumHint(el, opts));
    if(opts.currencyEl){
      const cs = document.getElementById(opts.currencyEl);
      if(cs){
        const sync = ()=>{
          if(opts.syncDecimals){
            const c = currencyById(+cs.value);
            if(c){ el.__numOpts.decimals = c.decimals || 0; applyNumMask(el, el.__numOpts); }
          }
          renderNumHint(el, opts);
        };
        cs.addEventListener('change', sync);
      }
    }
    renderNumHint(el, opts);
  }
  return el;
}
function faDateFromIso(iso){
  if(!iso) return '';
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if(!m) return iso;
  const j = J.toJalali(+m[1], +m[2], +m[3]);
  return j[0]+'/'+String(j[1]).padStart(2,'0')+'/'+String(j[2]).padStart(2,'0');
}
function dateTimeFa(iso){
  if(!iso) return '';
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if(!m) return faDateFromIso(iso);
  const j = J.toJalali(+m[1],+m[2],+m[3]);
  return `${j[0]}/${String(j[1]).padStart(2,'0')}/${String(j[2]).padStart(2,'0')} ${m[4]}:${m[5]}`;
}
const faDigits = s => String(s).replace(/[0-9]/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);

/* تبدیل «۱۴۰۵/۰۶/۱۸» شمسی به ISO میلادی «YYYY-MM-DD» (برای ارسال به سرور) */
function faDateToIso(fa){
  if(!fa) return '';
  const s = String(fa).trim().replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d));
  if(!s) return '';
  const m = s.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if(!m) return s; // احتمالاً خودش ISO است
  const g = J.toGregorian(+m[1], +m[2], +m[3]);
  return g[0] + '-' + String(g[1]).padStart(2,'0') + '-' + String(g[2]).padStart(2,'0');
}
/* تاریخ شمسی امروز و ابتدای ماه جاری (به فرمت دیت‌پیکر ۱۴۰۵/۰۶/۱۸) */
function faToday(){ return faDateFromIso(new Date().toISOString().slice(0,10)); }
function faMonthStart(){
  const iso = new Date().toISOString().slice(0,10);
  return faDateFromIso(iso.slice(0,8) + '01');
}
/* راه‌اندازی دیت‌پیکر شمسی (jalaliDatepicker) روی فیلدهای دارای data-jdp */
function initDatePicker(){
  try{
    window.jalaliDatepicker.startWatch({
      container: 'body',
      selector: 'input[data-jdp]',
      autoShow: true,
      autoHide: true,
      hideAfterChange: true,
      showTodayBtn: true,
      showEmptyBtn: false,
      showCloseBtn: true,
      persianDigits: false,
      separatorChars: { date: '/', between: ' ', time: ':' },
      days: ['ش','ی','د','س','چ','پ','ج'],
      months: ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'],
      zIndex: 5000,
    });
  }catch(e){}
}

async function api(path, opts={}){
  const headers = {'Content-Type':'application/json'};
  if(state.token) headers['X-Token'] = state.token;
  const acct = opts.account != null ? opts.account : state.accountId;
  if(acct) headers['X-Account-Id'] = acct;
  const res = await fetch(path, {method: opts.method||'GET', headers, body: opts.body ? JSON.stringify(opts.body) : undefined});
  const data = await res.json().catch(()=>({}));
  if(!res.ok || data.error){
    const e = new Error(data.error || 'خطا در ارتباط با سرور');
    e.status = res.status;
    e.data = data;
    throw e;
  }
  return data;
}

function toast(msg, type='ok'){
  const wrap = document.getElementById('toastWrap');
  const t = document.createElement('div');
  t.className = 'toast '+type;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transition='opacity .4s'; setTimeout(()=>t.remove(),400); }, 3400);
}

function openModal(html, wide=false){
  const bd = document.getElementById('modalBackdrop');
  const box = document.getElementById('modalBox');
  box.className = 'modal'+(wide?' wide':'');
  box.innerHTML = html;
  bd.classList.add('open');
  return box;
}
function closeModal(){ document.getElementById('modalBackdrop').classList.remove('open'); }
document.getElementById('modalBackdrop').addEventListener('click', e => { if(e.target.id==='modalBackdrop') closeModal(); });

/* ---------------- آیکون‌ها و منو ---------------- */
const ICONS = {
  dashboard:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
  buy:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>',
  sell:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>',
  cashbox:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h4"/></svg>',
  parties:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5M17 8.5a3 3 0 1 0 0-5M17.5 14.5c2.5.3 4 1.8 4.6 4.5"/></svg>',
  debts:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4"/></svg>',
  loans:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 10a8 8 0 0 1 16 0M4 10v6M20 10v6M4 10h16"/></svg>',
  invoices:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2h12v20l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6"/></svg>',
  banknotes:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/></svg>',
  expenses:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l6-6 4 4 7-7M14 7h7v7"/></svg>',
  reports:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
  charts:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10h-10z"/><path d="M15 9a6 6 0 0 0-6-6v6z"/></svg>',
  transactions:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h12M8 12h12M8 18h12M3 6h.01M3 12h.01M3 18h.01"/></svg>',
  accounts:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  settings:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.7a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.7a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></svg>',
};

const SECTIONS = [
  {id:'dashboard',  label:'داشبورد', icon:'dashboard'},
  {id:'buy',        label:'خرید ارز', icon:'buy'},
  {id:'sell',       label:'فروش ارز', icon:'sell'},
  {id:'cashboxes',  label:'صندوق‌ها', icon:'cashbox', mod:'multi_cashbox'},
  {id:'parties',    label:'مشتریان و شرکت‌ها', icon:'parties', mod:'customers'},
  {id:'debts',      label:'بدهی و طلب', icon:'debts', mod:'debts'},
  {id:'loans',      label:'قرض‌ها', icon:'loans', mod:'loans'},
  {id:'invoices',   label:'فاکتورها', icon:'invoices', mod:'invoices'},
  {id:'banknotes',  label:'اسکناس‌ها', icon:'banknotes', mod:'banknotes'},
  {id:'expenses',   label:'درآمد و هزینه', icon:'expenses', mod:'expenses'},
  {id:'reports',    label:'گزارش‌ها', icon:'reports', mod:'reports'},
  {id:'charts',     label:'نمودارها', icon:'charts', mod:'charts'},
  {id:'accounts',   label:'مشترکین', icon:'accounts', superOnly:true},
  {id:'transactions', label:'تراکنش‌ها', icon:'transactions'},
  {id:'settings',   label:'تنظیمات', icon:'settings'},
];

/* فهرست منو با اعمال فلگ ماژول‌های کاربر */
function visibleSections(){
  const mods = (state.me && state.me.modules) || {};
  const isSuper = state.user.role === 'super_admin';
  return SECTIONS.filter(s => {
    if(s.superOnly && !isSuper) return false;
    if(s.mod && isSuper) return true;                 // سوپرادمین همه‌جا می‌بیند
    if(s.mod && mods[s.mod] === false) return false;  // ماژول خاموش → پنهان
    return true;
  });
}

const PARTY_TYPES = {customer:'مشتری', company:'شرکت', supplier:'تأمین‌کننده', partner:'همکار', employee:'کارمند'};
const JTYPE_FA = {buy:'خرید ارز', sell:'فروش ارز', loan_receive:'دریافت قرض', loan_give:'قرض دادن',
  loan_repay:'بازپرداخت قرض', expense:'هزینه', income:'درآمد', transfer:'انتقال صندوق',
  cash_adjust:'اصلاح صندوق', payment:'پرداخت / تسویه'};
const STATUS_FA = {draft:'پیش‌نویس', confirmed:'تأیید شده', settled:'تسویه شده', unsettled:'تسویه نشده', voided:'لغو شده', posted:'ثبت شده'};
const RATE_TYPE_FA = {market:'بازار', buy:'خرید', sell:'فروش', sana:'سنا'};
const NOTE_STATUS = {in_vault:'موجود در صندوق', sold:'فروخته شده', withdrawn:'برداشت شده', voided:'باطل'};
const LOAN_DIR = {receive:'دریافت قرض', give:'قرض دادن'};
const ROLE_FA = {super_admin:'سوپرادمین', admin:'مدیر', cashier:'صندوق‌دار', accountant:'حسابدار', operator:'اپراتور'};

function currencyById(id){ return state.currencies.find(c=>c.id==id); }
function currencyByCode(code){ return state.currencies.find(c=>c.code==code); }

/* ---------------- تم ---------------- */
function _osPrefersLight(){
  return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
}
function _applyResolved(light){
  if(light) document.documentElement.setAttribute('data-theme','light');
  else document.documentElement.removeAttribute('data-theme');
  const btn = document.getElementById('themeBtn');
  if(btn) btn.textContent = light ? '🌙' : '☀️';
}
function applyTheme(theme){
  theme = theme || 'dark';
  localStorage.setItem('sarrafi_theme', theme);
  if(theme === 'auto'){
    _applyResolved(_osPrefersLight());
    if(window.matchMedia){
      const mq = window.matchMedia('(prefers-color-scheme: light)');
      const on = e => { if(localStorage.getItem('sarrafi_theme')==='auto') _applyResolved(e.matches); };
      if(mq.addEventListener) mq.addEventListener('change', on);
      else if(mq.addListener) mq.addListener(on);
    }
  } else {
    _applyResolved(theme === 'light');
  }
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme')==='light' ? 'light':'dark';
  applyTheme(cur==='light'?'dark':'light');
}

/* ---------------- راه‌اندازی ---------------- */
async function boot(){
  applyTheme(localStorage.getItem('sarrafi_theme')||'dark');
  initDatePicker();
  const url = new URL(window.location.href);
  const t = url.searchParams.get('token');
  if(t){ state.token = t; localStorage.setItem('sarrafi_token', t); }
  else state.token = localStorage.getItem('sarrafi_token') || null;
  document.getElementById('todayChip').textContent = 'امروز: ' + faDateFromIso(new Date().toISOString());
  try{
    const me = await api('/api/me');
    state.me = me;
    state.user = me.user;
    refreshUserChip();
    refreshBrand();
    if(me.impersonated_by){
      document.getElementById('impersonationBanner').style.display = 'flex';
      document.getElementById('impersonationText').textContent =
        'در حال استفاده به‌عنوان: ' + (me.user.full_name||'') + ' (نمایندگی)';
    }
  }catch(e){}
  try{
    const [cur, par, cb] = await Promise.all([
      api('/api/currencies'), api('/api/parties'), api('/api/cashboxes')]);
    state.currencies = cur.items;
    state.parties = par.items;
    state.cashboxes = cb.items;
  }catch(e){}
  buildNav();
  // نرخ آنلاین خودکار (اگر فعال بود)
  maybeAutoFetchRates();
  await navigate('dashboard');
  if(state.token && !lsGet('sarrafi_welcomed')){ lsSet('sarrafi_welcomed','1'); setTimeout(openWelcome, 700); }
  initShortcuts();
  initTopbarExtras();
  handleHash();
}

function buildNav(){
  const nav = document.getElementById('nav');
  const secs = visibleSections();
  nav.innerHTML = secs.map(s =>
    `<a data-sec="${s.id}" class="${s.id==='dashboard'?'active':''}">${ICONS[s.icon]}<span>${s.label}</span></a>`
  ).join('');
  nav.querySelectorAll('a').forEach(a => a.addEventListener('click', ()=> navigate(a.dataset.sec)));
}

function refreshUserChip(){
  const u = state.user;
  document.getElementById('userName').textContent = u.full_name || 'مدیر سیستم';
  document.getElementById('userAvatar').textContent = (u.full_name||'م')[0];
  document.getElementById('userRole').textContent = ROLE_FA[u.role] || u.role;
  const loggedIn = !!state.token;
  document.getElementById('logoutBtn').style.display = loggedIn ? '' : 'none';
}

function refreshBrand(){
  const img = document.getElementById('brandLogo');
  const name = document.getElementById('brandName');
  let logo = null, accName = null;
  if(state.me && state.me.account && state.me.account.logo){
    logo = state.me.account.logo; accName = state.me.account.name;
  } else if(state.user && state.user.role === 'super_admin' && state.accountId && state.me && state.me.accounts){
    const a = state.me.accounts.find(x=>x.id===state.accountId);
    if(a){ logo = a.logo; accName = a.name; }
  }
  if(img){
    img.src = logo ? '/'+logo : '/static/img/logo.svg';
    img.onerror = ()=>{ img.src = '/static/img/logo.svg'; };
  }
  if(name && accName) name.textContent = accName;
}

async function maybeAutoFetchRates(){
  try{
    const st = await api('/api/rates/status');
    if(st.auto_refresh === '1'){
      // اگر بیش از ۳۰ دقیقه از آخرین دریافت گذشته
      const last = st.last_fetch ? new Date(st.last_fetch).getTime() : 0;
      if(Date.now() - last > 30*60*1000){
        try{ await api('/api/rates/fetch', {method:'POST', body:{provider: st.source}}); }catch(e){}
      }
    }
  }catch(e){}
}

/* ---------------- ناوبری ---------------- */
async function navigate(section){
  const sec = visibleSections().find(s=>s.id===section);
  const mods = (state.me && state.me.modules) || {};
  if(!sec || (sec.mod && mods[sec.mod] === false && state.user.role !== 'super_admin')){
    toast('این بخش برای شما غیرفعال است','warn');
    return;
  }
  state.section = section;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.sec===section));
  const title = sec?.label || '';
  document.getElementById('pageTitle').textContent = title;
  document.getElementById('sidebar').classList.remove('open');
  const c = document.getElementById('content');
  c.innerHTML = '<div class="loader">در حال بارگذاری…</div>';
  // تازه‌سازی داده‌ی کمبوها (طرف حساب/صندوق) تا حذف‌ها بلافاصله اعمال شوند
  try{
    const [par, cbx] = await Promise.all([api('/api/parties'), api('/api/cashboxes')]);
    state.parties = par.items; state.cashboxes = cbx.items;
  }catch(e){}
  try{
    switch(section){
      case 'dashboard':    c.innerHTML = await renderDashboard(); break;
      case 'buy':          c.innerHTML = renderTrade('buy'); bindTrade('buy'); break;
      case 'sell':         c.innerHTML = renderTrade('sell'); bindTrade('sell'); break;
      case 'cashboxes':    c.innerHTML = await renderCashboxes(); break;
      case 'parties':      c.innerHTML = await renderParties(); break;
      case 'debts':        c.innerHTML = await renderDebts(); break;
      case 'loans':        c.innerHTML = await renderLoans(); break;
      case 'invoices':     c.innerHTML = await renderInvoices(); break;
      case 'banknotes':    c.innerHTML = await renderBanknotes(); break;
      case 'expenses':     c.innerHTML = await renderExpenses('expense'); break;
      case 'reports':      c.innerHTML = await renderReports(); loadCashboxReport(); loadMonthlyReport(); loadProfitReport(); break;
      case 'charts':       c.innerHTML = await renderCharts(); loadCharts(); break;
      case 'accounts':     c.innerHTML = await renderAccounts(); break;
      case 'transactions': c.innerHTML = await renderTransactions(); break;
      case 'settings':
        c.innerHTML = await renderSettings();
        if(state.user.role==='admin' || state.user.role==='super_admin'){
          loadModulesBox();
          loadPermsBox();
        }
        break;
    }
    if(section!=='dashboard') refreshInstant();
  }catch(e){
    c.innerHTML = `<div class="alert err">خطا: ${esc(e.message)}</div>`;
  }
}

async function refreshInstant(){
  try{
    const d = await api('/api/dashboard');
    if(d.super) return;
    const parts = [];
    const irr = d.totals['IRR'];
    if(irr != null) parts.push(`💰 <b>${fmt(irr,0,1)}</b> ریال`);
    for(const code of ['USD','EUR','AED','TRY','GBP']){
      if(d.totals[code] != null){
        const cur = d.currencies.find(c=>c.code===code);
        parts.push(`<b>${fmt(d.totals[code], cur.decimals, cur.unit_ratio)}</b> ${code}`);
      }
    }
    document.getElementById('instantBalances').innerHTML = parts.join('<br>');
  }catch(e){}
}

/* ============================================================
   داشبورد
   ============================================================ */
async function renderDashboard(){
  const d = await api('/api/dashboard');
  if(d.super) return renderSuperDashboard(d);
  let fc = null; try{ fc = await api('/api/forecast?days=30'); }catch(e){}
  document.getElementById('todayChip').textContent = 'امروز: ' + (d.today_fa || '');
  const cur = c => d.currencies.find(x=>x.code===c);
  const rial = d.totals['IRR'] ?? 0;
  const stats = d.stats;

  const fxCards = ['USD','EUR','AED','TRY','GBP','IQD'].filter(c=>cur(c)).map(code => {
    const c = cur(code);
    const total = d.totals[code] ?? 0;
    return `<div class="stat"><span class="label">${esc(c.name)} (${code})</span>
      <span class="value">${fmt(total, c.decimals, c.unit_ratio)}</span></div>`;
  }).join('');

  const partyList = (arr) => arr.length ? arr.map(p => {
    const bs = Object.entries(p.balances).map(([code,b])=>{
      const c = cur(code); if(!c) return '';
      const v = b.amount;
      const sign = v<0 ? '−' : '+';
      return `<span class="chip">${esc(code)}: <b class="num">${sign}${fmt(Math.abs(v), b.decimals, b.unit_ratio)}</b></span>`;
    }).join(' ');
    return `<tr class="clickable" onclick="openParty(${p.id})">
      <td>${esc(p.full_name)}</td><td>${bs}</td>
      <td class="num">${fmt(Math.abs(p.net_rial),0,1)}</td></tr>`;
  }).join('') : '<tr><td colspan="3" class="empty">موردی نیست</td></tr>';

  const recent = d.recent.map(r => `
    <tr class="clickable" onclick="openJournal(${r.id})">
      <td>${dateTimeFa(r.created_at)}</td>
      <td>${esc(JTYPE_FA[r.jtype]||r.jtype)}</td>
      <td>${esc(r.title||'')}</td>
      <td>${esc(r.summary||'')}</td>
      <td>${r.status==='voided'?'<span class="badge red">لغو شده</span>':'<span class="badge green">ثبت شده</span>'}</td>
    </tr>`).join('');

  return `
  <div class="card mb" style="padding:14px 18px">
    <div class="flex">
      <button class="btn primary" onclick="navigate('buy')">💱 خرید ارز</button>
      <button class="btn" onclick="navigate('sell')">💱 فروش ارز</button>
      <button class="btn" onclick="navigate('parties')">👥 طرف حساب جدید</button>
      <button class="btn" onclick="navigate('banknotes')">💵 ثبت اسکناس</button>
      <button class="btn" onclick="openLoanModal('receive')">🤝 دریافت قرض</button>
      <button class="btn" onclick="navigate('expenses')">💰 درآمد / هزینه</button>
    </div>
  </div>
  <div class="card mb guide-card">
    <div class="flex between"><b>🎓 تازه وارد هستید؟</b></div>
    <p class="small muted mt">با راهنمای تعاملی، قدم‌به‌قدم و مستقیم روی صفحه، کار با سیستم را یاد بگیرید.</p>
    <div class="guide-btns">
      <button class="btn sm primary" onclick="startGuide('sell')">💱 آموزش فروش</button>
      <button class="btn sm" onclick="startGuide('buy')">💱 آموزش خرید</button>
      <button class="btn sm" onclick="startGuide('party')">👥 ثبت مشتری</button>
      <button class="btn sm" onclick="startGuide('cashbox')">🏦 ساخت صندوق</button>
      <button class="btn sm" onclick="startGuide('banknote')">💵 ثبت اسکناس</button>
      <button class="btn sm ghost" onclick="openHelp()">🎓 همه‌ی آموزش‌ها</button>
    </div>
  </div>
  <div class="grid cols-4 mb">
    <div class="stat"><span class="label">صندوق ریالی</span><span class="value">${fmt(rial,0,1)} <span class="cur">ریال</span></span></div>
    <div class="stat tone-green"><span class="label">خرید امروز</span><span class="value">${fmt(stats.buy_total,0,1)} <span class="cur">ریال</span></span><span class="sub">${stats.buy_count} فاکتور</span></div>
    <div class="stat tone-accent"><span class="label">فروش امروز</span><span class="value">${fmt(stats.sell_total,0,1)} <span class="cur">ریال</span></span><span class="sub">${stats.sell_count} فاکتور</span></div>
    <div class="stat tone-amber"><span class="label">سود تقریبی امروز</span><span class="value">${fmt(stats.profit,0,1)} <span class="cur">ریال</span></span></div>
  </div>
  ${(d.alerts||[]).length ? `<div class="alert warn mb">
    <b>⚠ هشدار کف موجودی:</b> ${d.alerts.map(a=>`${esc(a.name)} (${esc(a.code)}) موجودی ${fmt(a.balance, a.decimals, a.unit_ratio)} کمتر از حداقل ${fmt(a.minimum, a.decimals, a.unit_ratio)} است`).join(' — ')}
  </div>` : ''}
  ${(d.reminders||[]).length ? `<div class="alert ${d.reminders.some(r=>r.overdue)?'err':'warn'} mb">
    <b>⏰ یادآور سررسید قرض:</b> ${d.reminders.map(r=>{
      const when = r.overdue ? `${Math.abs(r.days_left)} روز گذشته` : (r.days_left===0?'امروز':`${r.days_left} روز مانده`);
      return `${esc(r.party)} — ${fmt(r.remaining, r.decimals, r.unit_ratio)} ${esc(r.code)} (${when})`;
    }).join(' — ')}
  </div>` : ''}
  ${fc ? `<div class="card mb"><h3>📈 پیش‌بینی نقدینگی (۳۰ روز آینده)</h3>
    <div class="grid cols-2">
      <div>
        <div class="forecast-row"><span>💵 وصولی‌های مورد انتظار</span><b class="num fc-pos">${fmt(fc.incoming_rial,0,1)} ریال</b></div>
        <div class="forecast-row"><span>💸 پرداخت‌های مورد انتظار</span><b class="num fc-neg">${fmt(fc.outgoing_rial,0,1)} ریال</b></div>
        <div class="forecast-row"><span>⚖️ خالص جریان نقد</span><b class="num ${fc.net_rial>=0?'fc-pos':'fc-neg'}">${fc.net_rial>=0?'+':''}${fmt(fc.net_rial,0,1)} ریال</b></div>
      </div>
      <div>
        <div class="forecast-row"><span>💰 موجودی ریالی فعلی</span><b class="num">${fmt(fc.rial_balance,0,1)} ریال</b></div>
        <div class="forecast-row"><span>🎯 موجودی پیش‌بینی‌شده</span><b class="num ${fc.projected_rial>=0?'fc-pos':'fc-neg'}">${fmt(fc.projected_rial,0,1)} ریال</b></div>
      </div>
    </div>
  </div>` : ''}
  <div class="card mb"><h3>موجودی صندوق‌های ارزی</h3>
    <div class="grid cols-4">${fxCards}</div>
  </div>
  <div class="grid cols-2 mb">
    <div class="card"><h3>📥 بدهکاران (به ما بدهکارند)</h3>
      <div class="table-wrap"><table><thead><tr><th>نام</th><th>مانده ارزها</th><th>معادل ریال</th></tr></thead><tbody>${partyList(d.debtors)}</tbody></table></div>
    </div>
    <div class="card"><h3>📤 بستانکاران (ما به آن‌ها بدهکاریم)</h3>
      <div class="table-wrap"><table><thead><tr><th>نام</th><th>مانده ارزها</th><th>معادل ریال</th></tr></thead><tbody>${partyList(d.creditors)}</tbody></table></div>
    </div>
  </div>
  <div class="grid cols-2 mb">
    <div class="card"><h3>صندوق‌ها</h3>
      ${d.cashboxes.map(cb => {
        const rows = Object.entries(cb.balances)
          .filter(([code])=> !cb.currency_code || code===cb.currency_code)
          .map(([code, bal]) => {
          const c = cur(code); if(!c) return '';
          return `<div class="kv"><span>${c.name} (${code})</span><b class="num" style="direction:ltr">${fmt(bal, c.decimals, c.unit_ratio)}</b></div>`;
        }).join('');
        return `<div class="mb"><b>${esc(cb.name)}</b>${rows}</div>`;
      }).join('')}
    </div>
    <div class="card"><h3>آخرین عملیات</h3>
      <div class="table-wrap"><table><thead><tr><th>زمان</th><th>نوع</th><th>شرح</th><th>خلاصه</th><th>وضعیت</th></tr></thead><tbody>${recent}</tbody></table></div>
    </div>
  </div>`;
}

function renderSuperDashboard(d){
  const rows = d.accounts.map(a=>`
    <tr>
      <td><b>${esc(a.name)}</b></td>
      <td><span class="badge ${a.plan==='pro'?'purple':'gray'}">${a.plan==='pro'?'حرفه‌ای':'رایگان'}</span></td>
      <td>${a.status==='active'?'<span class="badge green">فعال</span>':'<span class="badge red">معلق</span>'}</td>
      <td class="num">${faDigits(a.users)}</td>
      <td class="num">${faDigits(a.invoices)}</td>
      <td class="num">${faDateFromIso(a.created_at)}</td>
      <td>
        <button class="btn xs" onclick="viewAccount(${a.id})">👁 مشاهده</button>
        <button class="btn xs warn" onclick="impersonateUser(${a.id})">🔑 ورود</button>
      </td>
    </tr>`).join('');
  return `
  <div class="flex between mb">
    <h3 style="font-size:15px">مشترکین سیستم (${faDigits(d.total_accounts)} حساب)</h3>
    <button class="btn primary" onclick="openAccountForm()">+ حساب جدید</button>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>نام حساب</th><th>پلن</th><th>وضعیت</th><th>کاربران</th><th>فاکتورها</th><th>تاریخ ایجاد</th><th>عملیات</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="7" class="empty">حسابی نیست</td></tr>'}</tbody></table>
  </div></div>
  <div class="small muted mt">🔑 «ورود» = ورود مستقیم به حساب مشترک بدون نیاز به نام کاربری و رمز (نمایندگی). 👁 «مشاهده» = مرور داده‌ی حساب.</div>`;
}

async function viewAccount(id){
  state.accountId = id;
  await reloadAccountData();
  refreshBrand();
  document.getElementById('impersonationBanner').style.display = 'flex';
  document.getElementById('impersonationText').textContent = 'در حال مشاهده‌ی داده‌ی حساب #' + id;
  document.getElementById('endViewBtn').onclick = endViewAccount;
  await navigate('dashboard');
  refreshInstant();
}
async function endViewAccount(){
  state.accountId = null;
  await reloadAccountData();
  refreshBrand();
  document.getElementById('impersonationBanner').style.display = 'none';
  navigate('dashboard');
}

/* تازه‌سازی لیست صندوق‌ها و طرف حساب‌ها برای حساب جاری (سوپرادمین هنگام جابجایی بین حساب‌ها) */
async function reloadAccountData(){
  try{
    const [par, cb] = await Promise.all([
      api('/api/parties'), api('/api/cashboxes')]);
    state.parties = par.items;
    state.cashboxes = cb.items;
  }catch(e){}
}

async function openAccountForm(id){
  const accs = state.me && state.me.accounts ? state.me.accounts : [];
  const a = id ? accs.find(x=>x.id==id) : {};
  acctFormRemoveLogo = false;
  openModal(`
    <h2>${id?'ویرایش':'افزودن'} حساب (مشترک) <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div class="full"><label>نام حساب *</label><input id="af-name" value="${esc(a.name||'')}"></div>
      <div><label>پلن</label><select id="af-plan"><option value="free" ${a.plan==='free'?'selected':''}>رایگان</option><option value="pro" ${a.plan==='pro'?'selected':''}>حرفه‌ای</option></select></div>
      <div><label>وضعیت</label><select id="af-status"><option value="active" ${a.status!=='suspended'?'selected':''}>فعال</option><option value="suspended" ${a.status==='suspended'?'selected':''}>معلق</option></select></div>
      <div><label>تلفن</label><input id="af-phone" value="${esc(a.phone||'')}"></div>
      <div class="full"><label>لوگوی حساب (نمایش در سایدبار برای کاربران این حساب)</label>
        <div class="flex" style="gap:10px;align-items:center">
          ${a.logo?`<img src="/${esc(a.logo)}" alt="لوگو" class="acct-logo-lg">`:''}
          <input type="file" id="af-logo" accept="image/png,image/jpeg,image/webp">
          ${a.logo?`<button class="btn xs warn" id="af-logo-rm">🗑 حذف لوگو</button>`:''}
        </div>
      </div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="af-save">ذخیره</button></div>`);
  const rmBtn = document.getElementById('af-logo-rm');
  if(rmBtn) rmBtn.onclick = (e)=>{ e.preventDefault(); acctFormRemoveLogo = true; document.getElementById('af-logo').value=''; rmBtn.style.display='none'; };
  document.getElementById('af-save').onclick = async ()=>{
    const btn = document.getElementById('af-save');
    const oldText = btn.textContent;
    btn.disabled = true; btn.textContent = '⏳ در حال ذخیره…';
    try{
      const saved = await api('/api/account/save',{method:'POST', body:{
        id: id||null, name:document.getElementById('af-name').value,
        plan:document.getElementById('af-plan').value, status:document.getElementById('af-status').value,
        phone:document.getElementById('af-phone').value}});
      const aid = saved.id;
      const logoFile = document.getElementById('af-logo').files[0];
      if(logoFile){
        const data = await fileToDataURL(logoFile);
        await api('/api/account/logo',{method:'POST', body:{account_id: aid, data}});
      } else if(acctFormRemoveLogo){
        await api('/api/account/logo',{method:'POST', body:{account_id: aid, data:''}});
      }
      toast('ذخیره شد ✔'); closeModal(); navigate('accounts');
    }catch(e){ toast(e.message,'err'); }
    finally{ btn.disabled = false; btn.textContent = oldText; }
  };
}

/* ---------------- ورود به‌جای کاربر ---------------- */
async function impersonateUser(userIdOrAccountId, isAccount){
  let uid = userIdOrAccountId;
  if(isAccount){
    const accs = await api('/api/accounts');
    const a = accs.items.find(x=>x.id===userIdOrAccountId);
    if(!a || !a.owner_id) return toast('این حساب مالکی ندارد','err');
    uid = a.owner_id;
  }
  if(!confirm('ورود به این حساب بدون نام کاربری و رمز؟ (عملیات شما در لاگ ثبت می‌شود)')) return;
  try{
    const r = await api('/api/impersonate', {method:'POST', body:{user_id: uid}});
    state.prevToken = state.token;
    state.token = r.token;
    state.user = r.user;
    state.accountId = null;
    refreshUserChip();
    document.getElementById('impersonationBanner').style.display = 'flex';
    document.getElementById('impersonationText').textContent = 'در حال استفاده به‌عنوان: ' + r.user.full_name;
    document.getElementById('endViewBtn').onclick = endImpersonation;
    toast('وارد حساب شدید ✔');
    location.reload();
  }catch(e){ toast(e.message,'err'); }
}
async function endImpersonation(){
  if(state.prevToken){
    await api('/api/logout', {method:'POST', body:{}}).catch(()=>{});
    state.token = state.prevToken;
    state.prevToken = null;
    state.accountId = null;
    location.reload();
  }
}

/* ============================================================
   خرید / فروش (با افزودن طرف حساب از همان‌جا)
   ============================================================ */
function renderTrade(kind){
  const isBuy = kind==='buy';
  const parties = state.parties.filter(p=>p.is_active);
  const fx = state.currencies.filter(c=>c.code!=='IRR' && c.is_active);
  const mods = (state.me && state.me.modules) || {};
  return `
  <div class="grid cols-2">
    <div class="card">
      <h3>${isBuy?'📥 ثبت خرید ارز':'📤 ثبت فروش ارز'}</h3>
      <div class="form-grid">
        <div class="full"><label>طرف حساب (${isBuy?'فروشنده':'خریدار'})</label>
          <div class="flex">
            <select id="tr-party" style="flex:1"><option value="">انتخاب کنید…</option>
            ${parties.map(p=>`<option value="${p.id}">${esc(p.full_name)} (${PARTY_TYPES[p.type]||p.type})</option>`).join('')}</select>
            <button class="btn" onclick="openPartyForm(null, {onSaved: bindNewParty})">＋ جدید</button>
          </div></div>
        <div><label>نوع ارز</label>
          <select id="tr-currency">${fx.map(c=>`<option value="${c.id}">${esc(c.name)} (${c.code})</option>`).join('')}</select></div>
        <div><label>مقدار (${isBuy?'خرید':'فروش'})</label>
          <input type="text" inputmode="decimal" id="tr-amount" class="input-num" placeholder="0.00"></div>
        <div><label>نرخ (ریال به ازای ۱ واحد)</label>
          <div class="flex"><input type="text" inputmode="numeric" id="tr-rate" class="input-num" placeholder="0" style="flex:1">
          <button class="btn xs" onclick="refreshLiveRate()" title="نرخ لحظه‌ای">↻ نرخ لحظه‌ای</button></div>
          <div class="rate-hint" id="tr-rate-hint"></div></div>
        <div><label>روش تسویه</label>
          <select id="tr-method">
            <option value="cash">نقدی</option><option value="card">کارت به کارت</option>
            <option value="transfer">حواله</option><option value="mix">ترکیبی</option>
            <option value="later">پرداخت بعداً (نسیه)</option>
          </select></div>
        <div class="full"><label>نوع نرخ</label>
          <div class="rate-type-tabs" id="tr-rt-tabs">
            <span class="rt on" data-rt="market">بازار</span>
            <span class="rt" data-rt="buy">خرید</span>
            <span class="rt" data-rt="sell">فروش</span>
            <span class="rt" data-rt="sana">سنا</span>
          </div></div>
        <div><label>صندوق</label>
          <select id="tr-cashbox">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
        ${mods.fee_tax !== false ? `<div><label>کارمزد (ریال)</label><input type="text" inputmode="numeric" id="tr-fee" class="input-num" placeholder="۰"></div>
        <div><label>مالیات (ریال)</label><input type="text" inputmode="numeric" id="tr-tax" class="input-num" placeholder="۰"></div>` : ''}
        <div class="full"><div class="alert warn" id="tr-credit-warn" style="display:none"></div></div>
        <div class="full"><label>توضیحات</label><textarea id="tr-desc" placeholder="اختیاری…"></textarea></div>
        <div class="full">
          <div class="alert ok" id="tr-preview">مبلغ کل ریالی: —</div>
          <div class="btn-row">
            <button class="btn primary" id="tr-submit">${isBuy?'ثبت خرید':'ثبت فروش'}</button>
            <button class="btn" id="tr-draft">ذخیره پیش‌نویس</button>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <h3>راهنما</h3>
      <div class="kv"><span>اثر روی صندوق ارزی</span><b class="num">${isBuy?'+ مقدار':'− مقدار'}</b></div>
      <div class="kv"><span>اثر روی صندوق ریالی</span><b class="num">${isBuy?'− مبلغ ریالی':'+ مبلغ ریالی'}</b></div>
      <div class="kv"><span>اگر نسیه باشد</span><span class="small muted">${isBuy?'شما به طرف حساب بدهکار می‌شوید':'طرف حساب به شما بدهکار می‌شود'}</span></div>
      <div class="mt small muted">با دکمه‌ی «＋ جدید» می‌توانید مشتری/شرکت جدید را همین‌جا ثبت کنید و بلافاصله انتخاب شود.</div>
    </div>
  </div>`;
}

async function bindNewParty(id){
  // بعد از ثبت طرف حساب جدید در فرم خرید/فروش — لیست را تازه می‌کنیم و انتخاب می‌کنیم
  try{ const d = await api('/api/parties'); state.parties = d.items; }catch(e){}
  const sel = document.getElementById('tr-party');
  if(sel){
    const cur = (state.parties||[]).find(p=>p.id==id);
    if(cur){
      sel.innerHTML += `<option value="${cur.id}">${esc(cur.full_name)} (${PARTY_TYPES[cur.type]||cur.type})</option>`;
      sel.value = String(id);
    } else {
      sel.value = String(id);
    }
  }
  toast('طرف حساب اضافه شد ✔');
}

async function refreshLiveRate(){
  const sel = document.getElementById('tr-currency');
  if(!sel) return;
  try{
    const r = await api('/api/rates');
    const row = r.items.find(x=>x.currency_id===+sel.value);
    if(row){
      const rateEl = document.getElementById('tr-rate');
      setNum(rateEl, row.rate);
      document.getElementById('tr-rate-hint').textContent = 'نرخ ثبت‌شده برای امروز';
      rateEl.dispatchEvent(new Event('input'));
    } else toast('نرخی برای این ارز ثبت نشده','warn');
  }catch(e){ toast(e.message,'err'); }
}

function bindTrade(kind){
  const isBuy = kind==='buy';
  const amt = document.getElementById('tr-amount');
  const rate = document.getElementById('tr-rate');
  const curSel = document.getElementById('tr-currency');
  const preview = document.getElementById('tr-preview');
  let rateType = 'market';

  // ماسک اعداد + زیرنویس توضیحی (تومان / حروف فارسی)
  bindNumField('tr-amount', {decimals:2, syncDecimals:true, hint:true, kind:'amount', currencyEl:'tr-currency'});
  bindNumField('tr-rate', {decimals:0, hint:true, kind:'rate'});
  ['tr-fee','tr-tax'].forEach(id=> bindNumField(id, {decimals:0, hint:true, kind:'rial'}));

  // نوع نرخ (چندنرخی: بازار/خرید/فروش/سنا)
  const tabs = document.getElementById('tr-rt-tabs');
  if(tabs){
    tabs.querySelectorAll('.rt').forEach(t=> t.addEventListener('click', ()=>{
      tabs.querySelectorAll('.rt').forEach(x=>x.classList.remove('on'));
      t.classList.add('on');
      rateType = t.dataset.rt;
      prefillRate();
    }));
  }

  async function prefillRate(){
    try{
      const r = await api('/api/rates');
      const cid = +curSel.value;
      const rows = (r.by_type && r.by_type[rateType]) ? r.by_type[rateType] : r.items;
      const row = rows.find(x=>x.currency_id===cid);
      if(row) setNum(rate, row.rate);
      update();
    }catch(e){}
  }
  function feeTaxVals(){
    const feeEl = document.getElementById('tr-fee');
    const taxEl = document.getElementById('tr-tax');
    return {
      fee: feeEl ? Math.round(numVal(feeEl)) : 0,
      tax: taxEl ? Math.round(numVal(taxEl)) : 0,
    };
  }
  function update(){
    const c = currencyById(+curSel.value);
    const a = numVal(amt);
    const r = numVal(rate);
    const {fee, tax} = feeTaxVals();
    const rial = Math.round(a*r);
    if(!isNaN(rial) && a>0 && r>0){
      const extra = fee||tax ? ` + کارمزد ${fmt(fee,0,1)} + مالیات ${fmt(tax,0,1)}` : '';
      preview.textContent = `مبلغ کل ریالی: ${fmt(rial+fee+tax,0,1)} ریال${extra}`;
    } else preview.textContent = 'مبلغ کل ریالی: —';
  }
  curSel.addEventListener('change', prefillRate);
  amt.addEventListener('input', update);
  rate.addEventListener('input', update);
  ['tr-fee','tr-tax'].forEach(id=>{ const el=document.getElementById(id); if(el) el.addEventListener('input', update); });
  prefillRate();

  // سقف اعتبار مشتری (فروش نسیه)
  async function checkCredit(){
    const warn = document.getElementById('tr-credit-warn');
    if(!warn) return;
    const method = document.getElementById('tr-method').value;
    const pid = +document.getElementById('tr-party').value;
    if(isBuy || method!=='later' || !pid){ warn.style.display='none'; return; }
    try{
      const d = await api('/api/party?id='+pid);
      const lim = d.party.credit_limit;
      if(lim==null || lim==='' || !lim){ warn.style.display='none'; return; }
      warn.style.display='';
      warn.innerHTML = `سقف اعتبار این مشتری <b>${fmt(lim,0,1)} ریال</b> است — در فروش نسیه، عبور از آن هشدار داده می‌شود.`;
    }catch(e){ warn.style.display='none'; }
  }
  document.getElementById('tr-method').addEventListener('change', checkCredit);
  document.getElementById('tr-party').addEventListener('change', checkCredit);

  async function submit(confirm){
    const c = currencyById(+curSel.value);
    const a = numVal(amt);
    const r = Math.round(numVal(rate));
    const party = +document.getElementById('tr-party').value;
    if(!party) return toast('طرف حساب را انتخاب کنید (یا «＋ جدید» بزنید)','err');
    if(!a || a<=0) return toast('مقدار نامعتبر است','err');
    if(!r || r<=0) return toast('نرخ نامعتبر است','err');
    const amountMinor = Math.round(a * c.unit_ratio);
    const {fee: feeRial, tax: taxRial} = feeTaxVals();
    const body = {
      party_id: party, currency_id: c.id, amount: amountMinor, rate: r,
      method: document.getElementById('tr-method').value,
      cashbox: +document.getElementById('tr-cashbox').value,
      description: document.getElementById('tr-desc').value,
      rate_type: rateType,
      fee_minor: Math.round(feeRial * c.unit_ratio / r),
      tax_minor: Math.round(taxRial * c.unit_ratio / r),
      confirm
    };
    try{
      const res = await api(isBuy?'/api/buy':'/api/sell', {method:'POST', body});
      toast(`فاکتور ${res.invoice_no} ${confirm?'ثبت':'ذخیره'} شد ✔`);
      if(res.credit && res.credit.would_exceed){
        toast(`⚠ هشدار: از سقف اعتبار مشتری عبور کرد (استفاده: ${fmt(res.credit.used_after,0,1)} از ${fmt(res.credit.credit_limit,0,1)} ریال)`,'err');
      }
      document.getElementById('tr-amount').value='';
      document.getElementById('tr-desc').value='';
      const feeEl = document.getElementById('tr-fee'); if(feeEl) feeEl.value='';
      const taxEl = document.getElementById('tr-tax'); if(taxEl) taxEl.value='';
      update();
      refreshInstant();
      // پیشنهاد ثبت اسکناس برای همین طرف حساب، بعد از تأیید فاکتور
      if(confirm && res.invoice_id){
        const pname = (state.parties.find(p=>p.id===party)||{}).full_name || '';
        detOpen({
          title: isBuy ? 'ثبت اسکناس‌های خریداری‌شده' : 'ثبت اسکناس‌های فروخته‌شده',
          currency_id: c.id, invoice_id: res.invoice_id, journal_id: res.journal_id,
          party_id: party, party_name: pname,
          status: isBuy ? 'in_vault' : 'sold', movement_type: isBuy ? 'purchase' : 'sale',
          onDone: ()=>{ navigate('banknotes'); },
        });
      }
    }catch(e){ toast(e.message,'err'); }
  }
  document.getElementById('tr-submit').onclick = ()=> submit(true);
  document.getElementById('tr-draft').onclick = ()=> submit(false);
}

/* ============================================================
   صندوق‌ها
   ============================================================ */
async function renderCashboxes(){
  const d = await api('/api/cashboxes');
  state.cashboxes = d.items;
  const canManage = (state.me?.perms||[]).includes('cashbox_manage') || state.user.role==='super_admin' || state.user.role==='admin';

  const roots = d.items.filter(c=>!c.parent_id);
  const children = cid => d.items.filter(c=>c.parent_id===cid);

  function balRows(cb, ind){
    const rows = Object.entries(cb.balances)
      .filter(([code])=> !cb.currency_code || code===cb.currency_code)
      .map(([code, bal])=>{
      const c = currencyByCode(code); if(!c) return '';
      return `<tr><td>${esc(c.name)} (${code})</td><td class="num">${fmt(bal, c.decimals, c.unit_ratio)}</td></tr>`;
    }).join('');
    return `<div class="table-wrap"><table><thead><tr><th>ارز</th><th>موجودی</th></tr></thead><tbody>${rows||'<tr><td colspan="2" class="empty">موجودی ندارد</td></tr>'}</tbody></table></div>`;
  }

  function card(cb){
    const kids = children(cb.id);
    const kidRows = kids.map(k=>`
      <div class="cb-child">
        <div class="flex between">
          <b>↳ ${esc(k.name)}</b>
          ${canManage?`<span class="flex"><button class="btn xs" onclick="openCashboxForm(${k.id})">✎</button>${delBtn('cashbox', k.id)}</span>`:''}
        </div>
        ${k.currency_code?`<span class="badge gray">${esc(k.currency_code)}</span>`:''}
        <div class="mt">${balRows(k)}</div>
      </div>`).join('');
    return `<div class="card">
      <div class="flex between">
        <h3>${cb.kind==='bank'?'🏦':'💼'} ${esc(cb.name)} <span class="hint">${esc(cb.code||'')}</span></h3>
        ${canManage?`<div class="flex">
          <button class="btn xs" onclick="openCashboxForm(null, ${cb.id})">＋ زیرشاخه</button>
          <button class="btn xs" onclick="openCashboxForm(${cb.id})">✎ ویرایش</button>
          ${delBtn('cashbox', cb.id)}
        </div>`:''}
      </div>
      ${cb.currency_code?`<span class="badge gray">${esc(cb.currency_code)}</span>`:''}
      ${cb.description?`<div class="small muted">${esc(cb.description)}</div>`:''}
      ${balRows(cb)}
      <div class="btn-row mt">
        <button class="btn sm" onclick="openTransfer()">⇄ انتقال بین صندوق</button>
        <button class="btn sm warn" onclick="openAdjust()">⚙ اصلاح موجودی</button>
      </div>
      ${kidRows?`<div class="cb-children mt">${kidRows}</div>`:''}
    </div>`;
  }

  return `
  <div class="flex between mb">
    <p class="small muted">صندوق‌های خودتان را بسازید، نام‌گذاری کنید و برای صندوق‌های بانکی زیرشاخه‌ی ارزی تعریف کنید.</p>
    ${canManage?`<button class="btn primary" id="cashbox-new-btn" onclick="openCashboxForm()">+ صندوق جدید</button>`:''}
  </div>
  <div class="grid cols-2">${roots.map(card).join('')}</div>
  ${!canManage?`<div class="alert warn mt">شما مجوز مدیریت صندوق ندارید؛ برای ساخت/تغییر نام با مدیر حساب تماس بگیرید.</div>`:''}`;
}

function openCashboxForm(id, parentId){
  const cb = id ? state.cashboxes.find(c=>c.id===id) : {};
  const roots = state.cashboxes.filter(c=>!c.parent_id && c.id!==id);
  const selParent = cb.parent_id || parentId || '';
  const fx = state.currencies.filter(c=>c.is_active);
  openModal(`
    <h2>${id?'ویرایش صندوق':'صندوق جدید'} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div class="full"><label>نام صندوق *</label><input id="cb-name" value="${esc(cb.name||'')}" placeholder="مثلاً صندوق اصلی / بانک ملی"></div>
      <div><label>نوع</label><select id="cb-kind">
        <option value="physical" ${cb.kind!=='bank'?'selected':''}>نقدی (فیزیکی)</option>
        <option value="bank" ${cb.kind==='bank'?'selected':''}>بانکی</option>
      </select></div>
      <div><label>کد کوتاه (اختیاری)</label><input id="cb-code" value="${esc(cb.code||'')}" placeholder="MAIN"></div>
      <div><label>صندوق والد (برای زیرشاخه)</label><select id="cb-parent">
        <option value="">— بدون والد (صندوق اصلی) —</option>
        ${roots.map(c=>`<option value="${c.id}" ${selParent===c.id?'selected':''}>${esc(c.name)}</option>`).join('')}
      </select></div>
      <div><label>ارز اختصاصی (خالی = چندارزی)</label><select id="cb-currency">
        <option value="">— همه ارزها —</option>
        ${fx.map(c=>`<option value="${c.id}" ${cb.currency_id===c.id?'selected':''}>${esc(c.name)} (${c.code})</option>`).join('')}
      </select></div>
      <div class="full"><label>توضیحات</label><input id="cb-desc" value="${esc(cb.description||'')}"></div>
      <div class="full"><div class="small muted">زیرشاخه‌ها فقط زیر صندوق اصلی تعریف می‌شوند؛ والدِ بانکی می‌تواند فرزندهایی مثل «بانک ملی ریالی» یا «بانک ملت دلار» داشته باشد.</div></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="cb-save">ذخیره</button></div>`);
  document.getElementById('cb-save').onclick = async ()=>{
    try{
      await api('/api/cashbox/save',{method:'POST', body:{
        id: id||null,
        name: document.getElementById('cb-name').value,
        kind: document.getElementById('cb-kind').value,
        code: document.getElementById('cb-code').value,
        parent_id: +document.getElementById('cb-parent').value || null,
        currency_id: +document.getElementById('cb-currency').value || null,
        description: document.getElementById('cb-desc').value,
        is_active: cb.is_active!==0?1:1}});
      toast('صندوق ذخیره شد ✔');
      closeModal();
      const d = await api('/api/cashboxes'); state.cashboxes = d.items;
      navigate('cashboxes');
    }catch(e){ toast(e.message,'err'); }
  };
}

function openTransfer(){
  const fx = state.currencies.filter(c=>c.is_active);
  openModal(`
    <h2>انتقال بین صندوق <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>از صندوق</label><select id="tf-from">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>به صندوق</label><select id="tf-to">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>ارز</label><select id="tf-currency">${fx.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>مقدار</label><input type="text" inputmode="decimal" id="tf-amount" class="input-num"></div>
      <div><label>نرخ (ریال/واحد)</label><input type="text" inputmode="numeric" id="tf-rate" class="input-num" value="0"></div>
      <div class="full"><label>توضیحات</label><input id="tf-desc"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="tf-go">انتقال</button></div>`);
  bindNumField('tf-amount', {decimals:2, syncDecimals:true, hint:true, kind:'amount', currencyEl:'tf-currency'});
  bindNumField('tf-rate', {decimals:0, hint:true, kind:'rate'});
  document.getElementById('tf-go').onclick = async ()=>{
    const c = currencyById(+document.getElementById('tf-currency').value);
    const a = numVal(document.getElementById('tf-amount'));
    try{
      await api('/api/transfer',{method:'POST', body:{
        from:+document.getElementById('tf-from').value, to:+document.getElementById('tf-to').value,
        currency_id:c.id, amount:Math.round(a*c.unit_ratio), rate:Math.round(numVal(document.getElementById('tf-rate'))),
        description:document.getElementById('tf-desc').value}});
      toast('انتقال ثبت شد ✔'); closeModal(); navigate('cashboxes');
    }catch(e){ toast(e.message,'err'); }
  };
}

function openAdjust(){
  const fx = state.currencies.filter(c=>c.is_active);
  openModal(`
    <h2>اصلاح موجودی صندوق <button class="close" onclick="closeModal()">×</button></h2>
    <div class="alert warn">اصلاح صندوق فقط برای مغایرت‌گیری/شمارش اولیه است و در لاگ ثبت می‌شود.</div>
    <div class="form-grid">
      <div><label>صندوق</label><select id="ad-cashbox">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>ارز</label><select id="ad-currency">${fx.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>مقدار (منفی = کسر)</label><input type="text" inputmode="decimal" id="ad-amount" class="input-num"></div>
      <div><label>نرخ</label><input type="text" inputmode="numeric" id="ad-rate" class="input-num" value="0"></div>
      <div class="full"><label>دلیل</label><input id="ad-reason" placeholder="مثلاً: مغایرت‌گیری پایان روز"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="ad-go">ثبت اصلاح</button></div>`);
  bindNumField('ad-amount', {decimals:2, syncDecimals:true, allowNegative:true, hint:true, kind:'amount', currencyEl:'ad-currency'});
  bindNumField('ad-rate', {decimals:0, hint:true, kind:'rate'});
  document.getElementById('ad-go').onclick = async ()=>{
    const c = currencyById(+document.getElementById('ad-currency').value);
    const a = numVal(document.getElementById('ad-amount'));
    try{
      await api('/api/adjust',{method:'POST', body:{
        cashbox:+document.getElementById('ad-cashbox').value, currency_id:c.id,
        amount:Math.round(a*c.unit_ratio), rate:Math.round(numVal(document.getElementById('ad-rate'))),
        reason:document.getElementById('ad-reason').value}});
      toast('اصلاح ثبت شد ✔'); closeModal(); navigate('cashboxes');
    }catch(e){ toast(e.message,'err'); }
  };
}

/* ============================================================
   طرف حساب‌ها
   ============================================================ */
function partyRow(p){
  const credit = (p.credit_limit != null && p.credit_limit !== '')
    ? `<span class="small muted">${fmt(p.credit_limit,0,1)}</span>` : '<span class="small muted">—</span>';
  return `<tr class="clickable" onclick="openParty(${p.id})">
      <td><b>${esc(p.full_name)}</b></td>
      <td><span class="badge ${p.type==='company'?'purple':p.type==='supplier'?'amber':p.type==='partner'?'blue':'green'}">${PARTY_TYPES[p.type]||p.type}</span></td>
      <td class="num">${esc(p.mobile||p.phone||'—')}</td>
      <td class="num">${credit}</td>
      <td class="num">${faDigits(p.invoice_count||0)}</td>
      <td>${p.is_active?'<span class="badge green">فعال</span>':'<span class="badge gray">غیرفعال</span>'}</td>
      <td>${delBtn('party', p.id)}</td>
    </tr>`;
}
async function renderParties(){
  const d = await api('/api/parties');
  state.parties = d.items;
  const rows = d.items.map(partyRow).join('');
  return `
  <div class="flex between mb">
    <div class="search-box"><input id="party-q" placeholder="جستجوی نام / موبایل…" oninput="filterParties()"></div>
    <div class="flex">
      <button class="btn" onclick="exportXlsx('parties')">📥 اکسل</button>
      <button class="btn primary" id="party-new-btn" onclick="openPartyForm()">+ طرف حساب جدید</button>
    </div>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>نام</th><th>نوع</th><th>موبایل</th><th>سقف اعتبار (ریال)</th><th>تعداد فاکتور</th><th>وضعیت</th><th></th></tr></thead>
    <tbody id="party-tbody">${rows||'<tr><td colspan="7" class="empty">طرف حسابی ثبت نشده</td></tr>'}</tbody></table>
  </div></div>`;
}

function filterParties(){
  const q = (document.getElementById('party-q').value||'').trim();
  const rows = state.parties.filter(p=> !q || (p.full_name||'').includes(q) || (p.mobile||'').includes(q) || (p.phone||'').includes(q));
  document.getElementById('party-tbody').innerHTML = rows.map(partyRow).join('') || '<tr><td colspan="7" class="empty">موردی یافت نشد</td></tr>';
}

function openPartyForm(id, opts){
  opts = opts || {};
  const p = id ? state.parties.find(x=>x.id==id) : {};
  openModal(`
    <h2>${id?'ویرایش':'افزودن'} طرف حساب <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>نام کامل *</label><input id="pf-name" value="${esc(p.full_name||'')}"></div>
      <div><label>نوع</label><select id="pf-type">
        ${Object.entries(PARTY_TYPES).map(([k,v])=>`<option value="${k}" ${p.type===k?'selected':''}>${v}</option>`).join('')}</select></div>
      <div><label>موبایل</label><input id="pf-mobile" value="${esc(p.mobile||'')}"></div>
      <div><label>تلفن</label><input id="pf-phone" value="${esc(p.phone||'')}"></div>
      <div><label>کد ملی / شناسه ملی</label><input id="pf-nid" value="${esc(p.national_id||'')}"></div>
      <div><label>سقف اعتبار (ریال، برای فروش نسیه)</label><input id="pf-credit" inputmode="numeric" class="input-num" value="${esc(p.credit_limit??'')}" placeholder="اختیاری"></div>
      <div><label>وضعیت</label><select id="pf-active"><option value="1" ${p.is_active!==0?'selected':''}>فعال</option><option value="0" ${p.is_active===0?'selected':''}>غیرفعال</option></select></div>
      <div class="full"><label>آدرس</label><input id="pf-addr" value="${esc(p.address||'')}"></div>
      <div class="full"><label>توضیحات</label><textarea id="pf-notes">${esc(p.notes||'')}</textarea></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="pf-save">ذخیره</button></div>`);
  bindNumField('pf-credit', {decimals:0, hint:true, kind:'rial'});
  document.getElementById('pf-save').onclick = async ()=>{
    try{
      const r = await api('/api/party/save',{method:'POST', body:{
        id: id||null, type:document.getElementById('pf-type').value,
        full_name:document.getElementById('pf-name').value,
        mobile:document.getElementById('pf-mobile').value,
        phone:document.getElementById('pf-phone').value,
        national_id:document.getElementById('pf-nid').value,
        credit_limit: Math.round(numVal(document.getElementById('pf-credit')))||null,
        address:document.getElementById('pf-addr').value,
        notes:document.getElementById('pf-notes').value,
        is_active:+document.getElementById('pf-active').value}});
      toast('ذخیره شد ✔'); closeModal();
      if(opts.onSaved){ opts.onSaved(r.id); return; }
      navigate('parties');
    }catch(e){ toast(e.message,'err'); }
  };
}

async function openParty(id){
  const d = await api('/api/party?id='+id);
  const p = d.party;
  const c = document.getElementById('content');
  const balRows = d.balances.map(b=>{
    const sign = b.amount<0 ? 'بدهکار به ما' : 'ما به او بدهکاریم';
    const cls = b.amount<0 ? 'red':'green';
    return `<tr><td>${esc(b.code)}</td>
      <td class="num">${fmt(Math.abs(b.amount), b.decimals, b.unit_ratio)}</td>
      <td><span class="badge ${cls}">${sign}</span></td>
      <td class="num">${fmt(Math.abs(b.rial),0,1)} ریال</td></tr>`;
  }).join('') || '<tr><td colspan="4" class="empty">تراکنشی نیست</td></tr>';

  const invRows = d.invoices.map(i=>`
    <tr class="clickable" onclick="openInvoice(${i.id})">
      <td>${esc(i.invoice_no)}</td><td>${dateTimeFa(i.confirmed_at||i.created_at)}</td>
      <td>${i.invoice_type==='buy'?'خرید':'فروش'}</td>
      <td class="num">${fmt(i.amount, i.decimals, i.unit_ratio)} ${esc(i.code)}</td>
      <td class="num">${fmt(i.rate,0,1)}</td>
      <td><span class="badge ${i.status==='voided'?'red':(i.status==='settled'||i.status==='confirmed'?'green':'amber')}">${STATUS_FA[i.status]||i.status}</span></td>
    </tr>`).join('') || '<tr><td colspan="6" class="empty">فاکتوری نیست</td></tr>';

  const loanRows = d.loans.map(l=>`
    <tr><td>${LOAN_DIR[l.direction]||l.direction}</td>
    <td class="num">${fmt(l.amount, l.decimals, l.unit_ratio)} ${esc(l.code)}</td>
    <td><span class="badge ${l.status==='settled'?'green':l.status==='voided'?'red':'amber'}">${l.status==='settled'?'تسویه':l.status==='voided'?'لغو':'باز'}</span></td></tr>`).join('') || '<tr><td colspan="3" class="empty">قرضی نیست</td></tr>';

  const noteRows = d.banknotes.map(b=>`
    <tr><td class="serial">${esc(b.serial)}</td>
    <td class="num">${fmt(b.denomination, b.decimals, b.unit_ratio)} ${esc(b.code)}</td>
    <td><span class="badge ${b.status==='in_vault'?'green':'gray'}">${NOTE_STATUS[b.status]||b.status}</span></td></tr>`).join('') || '<tr><td colspan="3" class="empty">اسکناسی ثبت نشده</td></tr>';

  c.innerHTML = `
  <div class="flex between mb">
    <button class="btn ghost" onclick="navigate('parties')">→ بازگشت به لیست</button>
    <div class="flex">
      <button class="btn sm" onclick="openPartyForm(${p.id})">✎ ویرایش</button>
      ${delBtn('party', p.id, 'parties')}
    </div>
  </div>
  <div class="grid cols-2 mb">
    <div class="card"><h3>اطلاعات ${PARTY_TYPES[p.type]||p.type}</h3>
      <div class="kv"><span>نام</span><b>${esc(p.full_name)}</b></div>
      <div class="kv"><span>موبایل</span><b class="num">${esc(p.mobile||'—')}</b></div>
      <div class="kv"><span>تلفن</span><b class="num">${esc(p.phone||'—')}</b></div>
      <div class="kv"><span>کد ملی / شناسه</span><b class="num">${esc(p.national_id||'—')}</b></div>
      <div class="kv"><span>سقف اعتبار</span><b class="num">${p.credit_limit!=null?fmt(p.credit_limit,0,1)+' ریال':'—'}</b></div>
      <div class="kv"><span>آدرس</span><span class="small">${esc(p.address||'—')}</span></div>
      <div class="kv"><span>تاریخ ثبت</span><span>${dateTimeFa(p.created_at)}</span></div>
    </div>
    <div class="card"><h3>مانده حساب</h3>
      <div class="table-wrap"><table><thead><tr><th>ارز</th><th>مانده</th><th>وضعیت</th><th>معادل ریالی</th></tr></thead><tbody>${balRows}</tbody></table></div>
    </div>
  </div>
  <div class="grid cols-2 mb">
    <div class="card"><h3>فاکتورها</h3><div class="table-wrap"><table><thead><tr><th>شماره</th><th>تاریخ</th><th>نوع</th><th>مقدار</th><th>نرخ</th><th>وضعیت</th></tr></thead><tbody>${invRows}</tbody></table></div></div>
    <div class="card"><h3>قرض‌ها</h3><div class="table-wrap"><table><thead><tr><th>نوع</th><th>مبلغ</th><th>وضعیت</th></tr></thead><tbody>${loanRows}</tbody></table></div>
      <h3 class="mt">اسکناس‌های مرتبط</h3><div class="table-wrap"><table><thead><tr><th>سریال</th><th>ارزش</th><th>وضعیت</th></tr></thead><tbody>${noteRows}</tbody></table></div>
    </div>
  </div>`;
  window.scrollTo(0,0);
}

/* ============================================================
   بدهی و طلب / قرض / فاکتور / اسکناس / درآمد و هزینه
   ============================================================ */
async function renderDebts(){
  const d = await api('/api/debts');
  const rows = d.items.map(it => {
    const cells = it.rows.map(r => {
      const cls = r.bal<0?'red':'green';
      const label = r.bal<0?'بدهکار':'بستانکار';
      return `<span class="chip">${esc(r.code)}: <b class="num">${fmt(Math.abs(r.bal), r.decimals, r.unit_ratio)}</b> <span class="badge ${cls}" style="padding:0 6px">${label}</span></span>`;
    }).join(' ');
    return `<tr>
      <td><b style="cursor:pointer" onclick="openParty(${it.party_id})">${esc(it.full_name)}</b></td>
      <td>${PARTY_TYPES[it.type]||it.type}</td><td>${cells}</td>
      <td><button class="btn xs" onclick="openPayment(${it.party_id})">تسویه</button></td></tr>`;
  }).join('');
  return `<div class="card"><div class="table-wrap">
    <table><thead><tr><th>طرف حساب</th><th>نوع</th><th>مانده حساب (به تفکیک ارز)</th><th></th></tr></thead>
    <tbody>${rows||'<tr><td colspan="4" class="empty">تراکنشی ثبت نشده</td></tr>'}</tbody></table>
  </div>
  <div class="small muted mt">🔵 <b>بدهکار</b> = طرف حساب به شما بدهکار است &nbsp;|&nbsp; 🟢 <b>بستانکار</b> = شما به او بدهکار هستید</div>
  </div>`;
}

async function renderLoans(){
  const d = await api('/api/loans');
  const todayIso = new Date().toISOString().slice(0,10);
  const rows = d.items.map(l=>{
    const remaining = l.amount - l.repaid;
    let dueCell = '—';
    if(l.due_date){
      const overdue = l.due_date < todayIso && remaining > 0;
      dueCell = `<span class="badge ${overdue?'red':'gray'}">${faDateFromIso(l.due_date)}${overdue?' ⚠':''}</span>`;
    }
    return `<tr>
      <td>${esc(l.full_name)}</td>
      <td><span class="badge ${l.direction==='receive'?'blue':'amber'}">${LOAN_DIR[l.direction]}</span></td>
      <td class="num">${fmt(l.amount, l.decimals, l.unit_ratio)} ${esc(l.code)}</td>
      <td class="num">${fmt(l.repaid, l.decimals, l.unit_ratio)}</td>
      <td class="num">${fmt(Math.max(0,remaining), l.decimals, l.unit_ratio)}</td>
      <td>${dueCell}</td>
      <td>${remaining<=0?'<span class="badge green">تسویه شده</span>':'<span class="badge amber">باز</span>'}</td>
      <td>${remaining>0?`<button class="btn xs" onclick="openRepay(${l.id},{decimals:${l.decimals},unit_ratio:${l.unit_ratio},code:'${l.code}'})">بازپرداخت</button>`:''} ${delBtn('loan', l.id)}</td>
    </tr>`;
  }).join('');
  return `
  <div class="btn-row mb">
    <button class="btn primary" onclick="openLoanModal('receive')">دریافت قرض</button>
    <button class="btn warn" onclick="openLoanModal('give')">قرض دادن</button>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>طرف حساب</th><th>نوع</th><th>مبلغ اصل</th><th>بازپرداخت‌شده</th><th>مانده</th><th>سررسید</th><th>وضعیت</th><th></th></tr></thead>
    <tbody>${rows||'<tr><td colspan="8" class="empty">قرضی ثبت نشده</td></tr>'}</tbody></table>
  </div></div>`;
}

function openLoanModal(dir){
  const fx = state.currencies.filter(c=>c.is_active);
  openModal(`
    <h2>${dir==='receive'?'دریافت قرض':'قرض دادن'} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div class="full"><label>طرف حساب</label><select id="ln-party">${state.parties.filter(p=>p.is_active).map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join('')}</select></div>
      <div><label>ارز</label><select id="ln-currency">${fx.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>مقدار</label><input type="text" inputmode="decimal" id="ln-amount" class="input-num"></div>
      <div><label>نرخ (ریال/واحد)</label><input type="text" inputmode="numeric" id="ln-rate" class="input-num" value="0"></div>
      <div><label>سررسید (اختیاری)</label><input id="ln-due" data-jdp placeholder="۱۴۰۵/۰۶/۱۸"></div>
      <div class="full"><label>توضیحات</label><input id="ln-desc"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="ln-go">ثبت</button></div>`);
  initDatePicker();
  bindNumField('ln-amount', {decimals:2, syncDecimals:true, hint:true, kind:'amount', currencyEl:'ln-currency'});
  bindNumField('ln-rate', {decimals:0, hint:true, kind:'rate'});
  document.getElementById('ln-go').onclick = async ()=>{
    const c = currencyById(+document.getElementById('ln-currency').value);
    const a = numVal(document.getElementById('ln-amount'));
    try{
      const due = faDateToIso(document.getElementById('ln-due').value);
      await api(dir==='receive'?'/api/loan/receive':'/api/loan/give',{method:'POST', body:{
        party_id:+document.getElementById('ln-party').value, currency_id:c.id,
        amount:Math.round(a*c.unit_ratio), rate:Math.round(numVal(document.getElementById('ln-rate'))),
        due_date: due || null,
        description:document.getElementById('ln-desc').value}});
      toast('قرض ثبت شد ✔'); closeModal(); navigate('loans');
    }catch(e){ toast(e.message,'err'); }
  };
}

function openRepay(loanId, cur){
  cur = cur || {};
  openModal(`
    <h2>بازپرداخت قرض <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>مقدار بازپرداخت</label><input type="text" inputmode="decimal" id="rp-amount" class="input-num"></div>
      <div><label>نرخ (ریال/واحد)</label><input type="text" inputmode="numeric" id="rp-rate" class="input-num" value="0"></div>
      <div class="full"><label>توضیحات</label><input id="rp-desc"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="rp-go">ثبت بازپرداخت</button></div>`);
  const rpCur = {id: cur.id, code: cur.code, name: cur.code, decimals: cur.decimals||0,
                 unit_ratio: cur.unit_ratio||1, minor_name: ''};
  bindNumField('rp-amount', {decimals: rpCur.decimals, hint:true, kind:'amount', cur: rpCur});
  bindNumField('rp-rate', {decimals:0, hint:true, kind:'rate'});
  document.getElementById('rp-go').onclick = async ()=>{
    try{
      await api('/api/loan/repay',{method:'POST', body:{
        loan_id:loanId, amount:Math.round(numVal(document.getElementById('rp-amount')) * rpCur.unit_ratio),
        rate:Math.round(numVal(document.getElementById('rp-rate'))), description:document.getElementById('rp-desc').value}});
      toast('بازپرداخت ثبت شد ✔'); closeModal(); navigate('loans');
    }catch(e){ toast(e.message,'err'); }
  };
}

function openPayment(partyId){
  const p = state.parties.find(x=>x.id==partyId) || {};
  const fx = state.currencies.filter(c=>c.is_active);
  openModal(`
    <h2>تسویه حساب — ${esc(p.full_name||'')} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>نوع</label><select id="pay-dir">
        <option value="receive">دریافت از طرف حساب (او به ما می‌دهد)</option>
        <option value="pay">پرداخت به طرف حساب (ما به او می‌دهیم)</option></select></div>
      <div><label>ارز</label><select id="pay-currency">${fx.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>مقدار</label><input type="text" inputmode="decimal" id="pay-amount" class="input-num"></div>
      <div><label>نرخ (ریال/واحد)</label><input type="text" inputmode="numeric" id="pay-rate" class="input-num" value="0"></div>
      <div><label>صندوق</label><select id="pay-cashbox">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>روش</label><select id="pay-method"><option value="cash">نقدی</option><option value="card">کارت به کارت</option><option value="transfer">حواله</option><option value="other">سایر</option></select></div>
      <div class="full"><label>توضیحات</label><input id="pay-desc"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="pay-go">ثبت</button></div>`);
  bindNumField('pay-amount', {decimals:2, syncDecimals:true, hint:true, kind:'amount', currencyEl:'pay-currency'});
  bindNumField('pay-rate', {decimals:0, hint:true, kind:'rate'});
  document.getElementById('pay-currency').addEventListener('change', async e=>{
    try{ const r = await api('/api/rates'); const row = r.items.find(x=>x.currency_id===+e.target.value); if(row) setNum(document.getElementById('pay-rate'), row.rate); }catch(_){}
  });
  document.getElementById('pay-go').onclick = async ()=>{
    const c = currencyById(+document.getElementById('pay-currency').value);
    const a = numVal(document.getElementById('pay-amount'));
    try{
      await api('/api/payment',{method:'POST', body:{
        party_id:partyId, direction:document.getElementById('pay-dir').value,
        currency_id:c.id, amount:Math.round(a*c.unit_ratio),
        rate:Math.round(numVal(document.getElementById('pay-rate'))),
        cashbox:+document.getElementById('pay-cashbox').value,
        method:document.getElementById('pay-method').value,
        description:document.getElementById('pay-desc').value}});
      toast('تسویه ثبت شد ✔'); closeModal(); navigate('debts');
    }catch(e){ toast(e.message,'err'); }
  };
}

let invPage = 1;
function invRow(i){
  const rt = (i.rate_type && i.rate_type!=='market') ? `<span class="badge gray">${RATE_TYPE_FA[i.rate_type]||i.rate_type}</span>` : '';
  const feeTax = (i.fee_minor||i.tax_minor) ? `<div class="small muted">⚙ کارمزد/مالیات</div>` : '';
  return `<tr class="clickable" onclick="openInvoice(${i.id})">
      <td class="serial">${esc(i.invoice_no)}</td>
      <td>${dateTimeFa(i.confirmed_at||i.created_at)}</td>
      <td><span class="badge ${i.invoice_type==='buy'?'green':'blue'}">${i.invoice_type==='buy'?'خرید':'فروش'}</span></td>
      <td><b>${esc(i.party_name)}</b></td>
      <td class="num">${fmt(i.amount, i.decimals, i.unit_ratio)} ${esc(i.currency_code)}</td>
      <td class="num">${fmt(i.rate,0,1)} ${rt}</td>
      <td class="num">${fmt(i.total_rial,0,1)}${feeTax}</td>
      <td><span class="badge ${i.status==='voided'?'red':(i.status==='settled'||i.status==='confirmed'?'green':i.status==='unsettled'?'amber':'gray')}">${STATUS_FA[i.status]||i.status}</span></td>
      <td>${delBtn('invoice', i.id)}</td>
    </tr>`;
}
async function renderInvoices(){
  invPage = 1;
  const d = await api('/api/invoices?limit=100&page=1');
  const rows = d.items.map(invRow).join('');
  const more = d.total > d.items.length ? `<div class="mt"><button class="btn" onclick="loadMoreInvoices()">نمایش بیشتر (${fmt(d.total - d.items.length,0,1)} مورد باقی)</button></div>` : '';
  return `<div class="flex between mb">
    <button class="btn" onclick="exportXlsx('invoices')">📥 خروجی اکسل (xlsx)</button>
    <span class="small muted">${fmt(d.total,0,1)} فاکتور</span>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>شماره</th><th>تاریخ</th><th>نوع</th><th>طرف حساب</th><th>مقدار</th><th>نرخ</th><th>مبلغ ریالی</th><th>وضعیت</th><th></th></tr></thead>
    <tbody id="inv-tbody">${rows||'<tr><td colspan="9" class="empty">فاکتوری نیست</td></tr>'}</tbody></table></div>${more}</div>`;
}
async function loadMoreInvoices(){
  invPage++;
  const d = await api(`/api/invoices?limit=100&page=${invPage}`);
  document.getElementById('inv-tbody').insertAdjacentHTML('beforeend', d.items.map(invRow).join(''));
  if (invPage * 100 >= d.total){ document.querySelector('#content .mt button')?.remove(); }
}

async function openInvoice(id){
  const d = await api('/api/invoice?id='+id);
  const inv = d.invoice;
  const legs = d.legs.map(l=>`
    <tr>
      <td>${l.direction==='debit'?'<span class="badge green">+ ورود</span>':'<span class="badge red">− خروج</span>'}</td>
      <td>${l.account_type==='cashbox'?('صندوق: '+(l.cashbox_name||'')):l.account_type==='party'?('طرف حساب: '+(l.party_name||'')):'حساب داخلی'}</td>
      <td class="num">${fmt(l.amount, l.decimals, l.unit_ratio)} ${esc(l.code)}</td>
      <td class="num">${fmt(l.rate,0,1)}</td>
    </tr>`).join('');
  const feeRow = inv.fee_minor ? `<div><div class="kv"><span>کارمزد</span><b class="num">${fmt(inv.fee_minor, inv.decimals, inv.unit_ratio)} ${esc(inv.code)}</b></div></div>` : '';
  const taxRow = inv.tax_minor ? `<div><div class="kv"><span>مالیات</span><b class="num">${fmt(inv.tax_minor, inv.decimals, inv.unit_ratio)} ${esc(inv.code)}</b></div></div>` : '';
  const photos = (d.photos||[]).map(ph=>`<img src="/${esc(ph.file_path)}" class="thumb" alt="اسکناس">`).join('');
  const banknotes = (d.banknotes||[]).map(b=>`
    <div class="flex between" style="padding:6px 0;border-bottom:1px dashed var(--border)">
      <span>💵 <b class="serial">${esc(b.serial)}</b> — ${fmt(b.denomination, b.decimals, b.unit_ratio)} ${esc(b.code)}</span>
      <button class="btn xs warn" onclick="detachBanknoteFromInvoice(${b.id}, ${inv.id})">جداسازی ✕</button>
    </div>`).join('');
  const attachBtn = inv.status !== 'voided' ? `<button class="btn" onclick="openBanknotePicker({currency_id:${inv.currency_id}, invoice_id:${inv.id}, journal_id:${inv.journal_id||0}, party_id:${inv.party_id}, status:'${inv.invoice_type==='buy'?'in_vault':'sold'}', movement_type:'${inv.invoice_type==='buy'?'purchase':'sale'}', onDone:()=>openInvoice(${inv.id})})">🔗 پیوند اسکناس ثبت‌شده</button>` : '';
  openModal(`
    <div class="invoice-print">
      <div class="receipt-brand"><span>💱 صرافی</span><span class="serial">${esc(inv.invoice_no)}</span></div>
      <div class="flex between">
        <h2>${inv.invoice_type==='buy'?'فاکتور خرید ارز':'فاکتور فروش ارز'}</h2>
        <span class="badge ${inv.status==='voided'?'red':'green'}">${STATUS_FA[inv.status]||inv.status}</span>
      </div>
      <div class="grid cols-2" style="margin:14px 0">
        <div><div class="kv"><span>تاریخ</span><b>${dateTimeFa(inv.confirmed_at||inv.created_at)}</b></div></div>
        <div><div class="kv"><span>طرف حساب</span><b>${esc(inv.party_name)}</b></div></div>
        <div><div class="kv"><span>نوع ارز</span><b>${esc(inv.code)}</b></div></div>
        <div><div class="kv"><span>مقدار</span><b class="num">${fmt(inv.amount, inv.decimals, inv.unit_ratio)}</b></div></div>
        <div><div class="kv"><span>نرخ (${RATE_TYPE_FA[inv.rate_type]||inv.rate_type||'بازار'})</span><b class="num">${fmt(inv.rate,0,1)} ریال</b></div></div>
        ${feeRow}${taxRow}
        <div class="full"><div class="kv"><span>مبلغ کل ریالی</span><b class="num">${fmt(inv.total_rial,0,1)} ریال</b></div></div>
        <div class="full"><div class="kv"><span>توضیحات</span><span>${esc(inv.description||'—')}</span></div></div>
      </div>
      <table><thead><tr><th>نوع</th><th>حساب</th><th>مبلغ</th><th>نرخ</th></tr></thead><tbody>${legs}</tbody></table>
      ${photos?`<div class="mt"><b style="font-size:13px">عکس‌های اسکناس:</b><div class="flex" style="gap:8px;margin-top:8px">${photos}</div></div>`:''}
      <div class="mt"><b style="font-size:13px">اسکناس‌های پیوندخورده (${banknotes?faDigits(d.banknotes.length):'۰'}):</b>${banknotes||'<div class="small muted">اسکناسی پیوند نخورده است.</div>'}</div>
    </div>
    <div class="btn-row mt no-print">
      <button class="btn primary" onclick="window.print()">🖨 چاپ فاکتور</button>
      <button class="btn" onclick="openDetectBanknotes({currency_id:${inv.currency_id}, invoice_id:${inv.id}, journal_id:${inv.journal_id||0}, status:'${inv.invoice_type==='buy'?'in_vault':'sold'}'})">📷 ثبت اسکناس از عکس</button>
      ${attachBtn}
      ${delBtn('invoice', inv.id, 'invoices')}
      <button class="btn ghost" onclick="closeModal()">بستن</button>
    </div>`, true);
}

async function detachBanknoteFromInvoice(bnId, invId){
  if(!confirm('این اسکناس از فاکتور جدا شود و دوباره «در دسترس» گردد؟')) return;
  try{
    await api('/api/banknote/detach', {method:'POST', body:{id: bnId}});
    toast('اسکناس جدا شد ✔');
    openInvoice(invId);
  }catch(e){ toast(e.message,'err'); }
}

let bnPage = 1;
function bnRow(b){
  return `<tr class="clickable" onclick="openBanknote(${b.id})">
      <td class="serial">${esc(b.serial)}</td>
      <td class="num">${fmt(b.denomination, b.decimals, b.unit_ratio)} ${esc(b.code)}</td>
      <td><span class="badge ${b.status==='in_vault'?'green':b.status==='sold'?'red':'gray'}">${NOTE_STATUS[b.status]||b.status}</span></td>
      <td>${esc(b.cashbox_name||'—')}</td>
      <td class="small muted">${esc(b.parties||'')}</td>
      <td>${delBtn('banknote', b.id)}</td>
    </tr>`;
}
function bnParams(){
  const q = document.getElementById('bn-q')?.value.trim()||'';
  const st = document.getElementById('bn-status')?.value||'';
  const cu = document.getElementById('bn-currency')?.value||'';
  const p = new URLSearchParams();
  if(q) p.set('q', q);
  if(st) p.set('status', st);
  if(cu) p.set('currency', cu);
  return p;
}
async function renderBanknotes(){
  bnPage = 1;
  const d = await api('/api/banknotes?limit=100&page=1');
  const rows = d.items.map(bnRow).join('');
  const more = d.total > d.items.length ? `<div class="mt"><button class="btn" onclick="loadMoreBanknotes()">نمایش بیشتر (${fmt(d.total - d.items.length,0,1)} مورد باقی)</button></div>` : '';
  return `
  <div class="flex between mb">
    <div class="search-box">
      <input id="bn-q" placeholder="جستجوی سریال / طرف حساب…" oninput="searchBanknotes()">
      <select id="bn-status" onchange="searchBanknotes()">
        <option value="">همه وضعیت‌ها</option>
        <option value="in_vault">موجود در صندوق</option>
        <option value="sold">فروخته شده</option>
        <option value="withdrawn">برداشت شده</option>
      </select>
      <select id="bn-currency" onchange="searchBanknotes()">
        <option value="">همه ارزها</option>
        ${state.currencies.map(c=>`<option value="${c.id}">${esc(c.code)}</option>`).join('')}
      </select>
    </div>
    <div class="flex">
      <button class="btn" onclick="openDetectBanknotes({})">📷 تشخیص از عکس</button>
      <button class="btn" onclick="exportXlsx('banknotes')">📥 اکسل</button>
      <button class="btn" onclick="openBanknoteBulk()">🗂 ثبت گروهی</button>
      <button class="btn primary" id="bn-new-btn" onclick="openBanknoteForm()">+ ثبت اسکناس</button>
    </div>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>سریال</th><th>ارزش</th><th>وضعیت</th><th>محل فعلی</th><th>مرتبط با</th><th></th></tr></thead>
    <tbody id="bn-tbody">${rows||'<tr><td colspan="6" class="empty">اسکناسی ثبت نشده</td></tr>'}</tbody></table>
  </div>${more}</div>`;
}

async function searchBanknotes(){
  bnPage = 1;
  const params = bnParams();
  params.set('limit', '100'); params.set('page', '1');
  const d = await api('/api/banknotes?'+params.toString());
  document.getElementById('bn-tbody').innerHTML = d.items.map(bnRow).join('') || '<tr><td colspan="6" class="empty">موردی یافت نشد</td></tr>';
  const moreBtn = document.querySelector('#content .card .mt button');
  if(d.total > d.items.length){
    if(!moreBtn){
      document.querySelector('#content .card').insertAdjacentHTML('beforeend', `<div class="mt"><button class="btn" onclick="loadMoreBanknotes()">نمایش بیشتر</button></div>`);
    }
  } else if(moreBtn){ moreBtn.parentElement.remove(); }
}
async function loadMoreBanknotes(){
  bnPage++;
  const params = bnParams();
  params.set('limit', '100'); params.set('page', String(bnPage));
  const d = await api('/api/banknotes?'+params.toString());
  document.getElementById('bn-tbody').insertAdjacentHTML('beforeend', d.items.map(bnRow).join(''));
  if(bnPage * 100 >= d.total){
    const moreBtn = document.querySelector('#content .card .mt button');
    if(moreBtn) moreBtn.parentElement.remove();
  }
}

const FACE_VALUES = {
  USD:[1,2,5,10,20,50,100], EUR:[5,10,20,50,100,200,500],
  AED:[5,10,20,50,100,200,500,1000], TRY:[5,10,20,50,100,200],
  GBP:[5,10,20,50], IQD:[250,500,1000,5000,10000,25000],
};

function openBanknoteForm(preset){
  preset = preset || {};
  const cbs = state.cashboxes;
  openModal(`
    <h2>ثبت اسکناس <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>ارز</label><select id="bnf-currency" onchange="bnfUpdateFaces()">
        ${state.currencies.filter(c=>c.code!=='IRR').map(c=>`<option value="${c.id}">${esc(c.name)} (${c.code})</option>`).join('')}</select></div>
      <div><label>ارزش اسکناس</label><select id="bnf-face"></select></div>
      <div class="full"><label>شماره سریال *</label><input id="bnf-serial" placeholder="مثلاً AB12345678" style="font-family:Consolas,monospace;direction:ltr"></div>
      <div><label>وضعیت</label><select id="bnf-status">
        <option value="in_vault">موجود در صندوق</option>
        <option value="sold">فروخته شده</option>
        <option value="withdrawn">برداشت شده</option></select></div>
      <div><label>صندوق</label><select id="bnf-cashbox">${cbs.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div class="full"><label>مرتبط با طرف حساب (اختیاری)</label><select id="bnf-party">
        <option value="">— بدون پیوند —</option>
        ${state.parties.filter(p=>p.is_active).map(p=>`<option value="${p.id}">${esc(p.full_name)} (${PARTY_TYPES[p.type]||p.type})</option>`).join('')}
      </select></div>
      <div class="full"><label>یادداشت</label><input id="bnf-note" placeholder="مثلاً خرید از علی محمدی"></div>
      <div class="full">
        <label>عکس اسکناس (اختیاری — چند عکس مجاز)</label>
        <div class="flex" style="flex-wrap:wrap">
          <button class="btn sm" onclick="capturePhoto()">📷 دوربین</button>
          <input type="file" id="bnf-file" accept="image/*" multiple style="max-width:260px">
          <button class="btn sm" id="bnf-ocr" style="display:none">📝 تشخیص خودکار سریال (OCR)</button>
          <span class="small muted" id="bnf-count"></span>
        </div>
        <img id="bnf-preview" style="display:none;width:80px;height:52px;object-fit:cover;border-radius:8px;margin-top:6px">
      </div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="bnf-save">ثبت</button></div>`);
  bnfUpdateFaces();
  if(preset.currency_id){
    const csel = document.getElementById('bnf-currency');
    if([...csel.options].some(o=>o.value==String(preset.currency_id))){ csel.value = String(preset.currency_id); bnfUpdateFaces(); }
  }
  if(preset.party_id){ const p=document.getElementById('bnf-party'); if(p && [...p.options].some(o=>o.value==String(preset.party_id))) p.value=String(preset.party_id); }
  if(preset.status){ const s=document.getElementById('bnf-status'); if(s) s.value=preset.status; }
  const bnfPhotos = [];
  function bnfAddPhoto(data){
    bnfPhotos.push(data);
    document.getElementById('bnf-preview').src = data;
    document.getElementById('bnf-preview').style.display='block';
    document.getElementById('bnf-ocr').style.display='';
    document.getElementById('bnf-count').textContent = faDigits(bnfPhotos.length) + ' عکس';
  }
  window.__bnfAdd = bnfAddPhoto;
  document.getElementById('bnf-file').addEventListener('change', e=>{
    const files = [...e.target.files]; if(!files.length) return;
    files.forEach(f=>{
      const r = new FileReader();
      r.onload = ev => bnfAddPhoto(ev.target.result);
      r.readAsDataURL(f);
    });
  });
  window.__bnfPhoto = ()=> bnfPhotos[0] || null;
  document.getElementById('bnf-ocr').addEventListener('click', async function(){
    const data = bnfPhotos[0] || null;
    if(!data) return toast('اول عکس بگیرید یا آپلود کنید','warn');
    const btn = this;
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ در حال تشخیص سریال…';
    try{
      const res = await api('/api/ocr', {method:'POST', body:{data}});
      if(res.suggestions && res.suggestions.length){
        document.getElementById('bnf-serial').value = res.suggestions[0];
        toast('سریال پیشنهادی: '+res.suggestions[0]+' — لطفاً بررسی و تأیید کنید','ok');
      } else toast(res.message || 'سریالی تشخیص داده نشد — دستی وارد کنید','warn');
    }catch(e){ toast('OCR در دسترس نیست: '+e.message,'err'); }
    finally{ btn.disabled = false; btn.textContent = oldText; }
  });
  async function uploadPhotos(bnId){
    for(const ph of bnfPhotos){
      await api('/api/banknote/photo',{method:'POST', body:{banknote_id:bnId, data:ph}});
    }
  }
  document.getElementById('bnf-save').onclick = async ()=>{
    const cid = +document.getElementById('bnf-currency').value;
    const c = currencyById(cid);
    const face = +document.getElementById('bnf-face').value;
    const serial = document.getElementById('bnf-serial').value.trim();
    if(!serial) return toast('سریال را وارد کنید','err');
    const status = document.getElementById('bnf-status').value;
    const party_id = +document.getElementById('bnf-party').value || null;
    const movement_type = status === 'sold' ? 'sale' : 'purchase';
    const bodyBase = {
      currency_id:cid, denomination:Math.round(face*c.unit_ratio), serial,
      status, party_id, movement_type,
      cashbox_id:+document.getElementById('bnf-cashbox').value,
      note:document.getElementById('bnf-note').value};
    try{
      const res = await api('/api/banknote/save',{method:'POST', body:bodyBase});
      if(res.duplicate){
        toast('⚠ این سریال قبلاً ثبت شده است!','warn');
        if(confirm('این سریال قبلاً در سیستم ثبت شده است. آیا همچنان ثبت شود؟')){
          const r2 = await api('/api/banknote/save',{method:'POST', body:{...bodyBase, force:true}});
          await uploadPhotos(r2.id);
        } else { return; }
      } else {
        await uploadPhotos(res.id);
      }
      toast('اسکناس ثبت شد ✔'); closeModal();
      if(preset.onDone) preset.onDone(); else navigate('banknotes');
    }catch(e){ toast(e.message,'err'); }
  };
}

function bnfUpdateFaces(){
  const cid = +document.getElementById('bnf-currency').value;
  const c = currencyById(cid);
  const faces = FACE_VALUES[c.code] || [1,5,10,20,50,100];
  document.getElementById('bnf-face').innerHTML = faces.map(f=>`<option value="${f}">${f} ${c.code}</option>`).join('');
}

async function capturePhoto(){
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    toast('دوربین در این محیط در دسترس نیست — از گزینه آپلود فایل استفاده کنید','warn');
    return;
  }
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});
    openModal(`<h2>عکس‌برداری از اسکناس <button class="close" onclick="stopCam()">×</button></h2>
      <video id="cam" autoplay playsinline style="width:100%;border-radius:10px"></video>
      <div class="btn-row mt"><button class="btn primary" id="cam-shot">📸 ثبت عکس</button></div>`);
    const v = document.getElementById('cam');
    v.srcObject = stream;
    window.__camStream = stream;
    document.getElementById('cam-shot').onclick = ()=>{
      const canvas = document.createElement('canvas');
      canvas.width = v.videoWidth; canvas.height = v.videoHeight;
      canvas.getContext('2d').drawImage(v,0,0);
      const data = canvas.toDataURL('image/jpeg', .85);
      window.__photoData = data;
      stream.getTracks().forEach(t=>t.stop());
      closeModal();
      if(window.__bnfAdd){
        window.__bnfAdd(data);
      } else {
        document.getElementById('bnf-preview').src = data;
        document.getElementById('bnf-preview').style.display='block';
        document.getElementById('bnf-ocr').style.display='';
        window.__bnfPhoto = ()=>data;
      }
      toast('عکس گرفته شد ✔');
    };
  }catch(e){ toast('دسترسی به دوربین ممکن نشد: '+e.message,'err'); }
}
function stopCam(){ if(window.__camStream){ window.__camStream.getTracks().forEach(t=>t.stop()); } closeModal(); }

/* ثبت گروهی اسکناس‌ها — هر سریال در یک سطر */
function openBanknoteBulk(preset){
  preset = preset || {};
  const cbs = state.cashboxes;
  const fx = state.currencies.filter(c=>c.code!=='IRR');
  openModal(`
    <h2>ثبت گروهی اسکناس <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>ارز</label><select id="bnk-currency" onchange="bnkUpdateFaces()">
        ${fx.map(c=>`<option value="${c.id}">${esc(c.name)} (${c.code})</option>`).join('')}</select></div>
      <div><label>ارزش اسکناس</label><select id="bnk-face"></select></div>
      <div><label>وضعیت</label><select id="bnk-status">
        <option value="in_vault">موجود در صندوق</option>
        <option value="sold">فروخته شده</option>
        <option value="withdrawn">برداشت شده</option></select></div>
      <div><label>صندوق</label><select id="bnk-cashbox">${cbs.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div class="full"><label>مرتبط با طرف حساب (اختیاری)</label><select id="bnk-party">
        <option value="">— بدون پیوند —</option>
        ${state.parties.filter(p=>p.is_active).map(p=>`<option value="${p.id}">${esc(p.full_name)} (${PARTY_TYPES[p.type]||p.type})</option>`).join('')}
      </select></div>
      <div class="full"><label>یادداشت مشترک</label><input id="bnk-note" placeholder="مثلاً خرید از علی محمدی"></div>
      <div class="full"><label>عکس مشترک (اختیاری — به همه‌ی اسکناس‌ها الصاق می‌شود)</label>
        <input type="file" id="bnk-file" accept="image/*" style="max-width:300px"></div>
      <div class="full"><label>شماره سریال‌ها * (هر سریال در یک سطر)</label>
        <textarea id="bnk-serials" rows="7" placeholder="AB12345678&#10;CD98765432&#10;EF55667788" style="font-family:Consolas,monospace;direction:ltr"></textarea></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="bnk-save">ثبت گروهی</button></div>`);
  bnkUpdateFaces();
  if(preset.currency_id){
    const csel = document.getElementById('bnk-currency');
    if([...csel.options].some(o=>o.value==String(preset.currency_id))){ csel.value = String(preset.currency_id); bnkUpdateFaces(); }
  }
  if(preset.party_id){ const p=document.getElementById('bnk-party'); if(p && [...p.options].some(o=>o.value==String(preset.party_id))) p.value=String(preset.party_id); }
  if(preset.status){ const s=document.getElementById('bnk-status'); if(s) s.value=preset.status; }
  let bnkPhoto = null;
  document.getElementById('bnk-file').addEventListener('change', e=>{
    const f = e.target.files[0]; if(!f) return;
    const r = new FileReader();
    r.onload = ev => bnkPhoto = ev.target.result;
    r.readAsDataURL(f);
  });
  document.getElementById('bnk-save').onclick = async ()=>{
    const serials = document.getElementById('bnk-serials').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    if(!serials.length) return toast('حداقل یک سریال وارد کنید','err');
    const bcur = currencyById(+document.getElementById('bnk-currency').value);
    const bface = +document.getElementById('bnk-face').value;
    const bstatus = document.getElementById('bnk-status').value;
    try{
      const r = await api('/api/banknote/bulk',{method:'POST', body:{
        currency_id:bcur.id,
        denomination:Math.round(bface * bcur.unit_ratio),
        serials,
        status:bstatus,
        cashbox_id:+document.getElementById('bnk-cashbox').value,
        note:document.getElementById('bnk-note').value,
        party_id:+document.getElementById('bnk-party').value || null,
        movement_type: bstatus === 'sold' ? 'sale' : 'purchase'}});
      if(bnkPhoto && r.ids && r.ids.length){
        for(const bnid of r.ids){
          await api('/api/banknote/photo',{method:'POST', body:{banknote_id:bnid, data:bnkPhoto}});
        }
      }
      let msg = `${r.inserted} اسکناس ثبت شد ✔`;
      if(r.duplicates.length) msg += ` — ${r.duplicates.length} تکراری (${r.duplicates.slice(0,5).join('، ')}${r.duplicates.length>5?'…':''})`;
      if(r.skipped.length) msg += ` — ${r.skipped.length} تکراری داخل همین فهرست`;
      toast(msg, r.duplicates.length||r.skipped.length ? 'warn':'ok');
      closeModal();
      if(preset.onDone) preset.onDone(); else navigate('banknotes');
    }catch(e){ toast(e.message,'err'); }
  };
}
function bnkUpdateFaces(){
  const cid = +document.getElementById('bnk-currency').value;
  const c = currencyById(cid);
  const faces = FACE_VALUES[c.code] || [1,5,10,20,50,100];
  document.getElementById('bnk-face').innerHTML = faces.map(f=>`<option value="${f}">${f} ${c.code}</option>`).join('');
}

async function openBanknote(id){
  const d = await api('/api/banknote?id='+id);
  const b = d.banknote;
  const tl = d.movements.map(m=>`
    <li><div class="t-date">${dateTimeFa(m.created_at)}</div>
    <div class="t-text">${esc({purchase:'خرید از',sale:'فروش به',transfer:'انتقال',initial:'ورود اولیه'}[m.movement_type]||m.movement_type)} ${m.party_name?esc(m.party_name):''} ${m.from_name?'از '+esc(m.from_name):''}${m.to_name?' به '+esc(m.to_name):''} ${m.note?'— '+esc(m.note):''}</div></li>`).join('');
  const imgs = d.images.map(im=>`<img src="/${esc(im.file_path)}" class="photo-thumb" onclick="window.open('/${esc(im.file_path)}')">`).join('');
  openModal(`
    <h2>اسکناس ${esc(b.serial)} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="bnote-card mb">
      <div class="kv"><span>سریال</span><b class="serial">${esc(b.serial)}</b></div>
      <div class="kv"><span>ارزش</span><b class="num">${fmt(b.denomination, b.decimals, b.unit_ratio)} ${esc(b.code)}</b></div>
      <div class="kv"><span>وضعیت</span><span class="badge ${b.status==='in_vault'?'green':'red'}">${NOTE_STATUS[b.status]||b.status}</span></div>
      <div class="kv"><span>محل فعلی</span><b>${esc(b.cashbox_name||'—')}</b></div>
      <div class="kv"><span>تاریخ ثبت</span><span>${dateTimeFa(b.created_at)}</span></div>
      <div class="kv"><span>یادداشت</span><span>${esc(b.note||'—')}</span></div>
    </div>
    ${imgs?`<div class="mb"><label>تصاویر</label><div class="flex">${imgs}</div></div>`:''}
    <label>تاریخچه مالکیت</label>
    <ul class="timeline">${tl||'<li><div class="t-text muted">تاریخچه‌ای ثبت نشده</div></li>'}</ul>
    <div class="btn-row mt">
      <button class="btn sm" onclick="addPhoto(${b.id})">📷 افزودن عکس</button>
      ${delBtn('banknote', b.id, 'banknotes')}
      <button class="btn ghost" onclick="closeModal()">بستن</button>
    </div>`);
}

function addPhoto(bnId){
  openModal(`<h2>افزودن عکس به اسکناس <button class="close" onclick="closeModal()">×</button></h2>
    <div class="flex">
      <button class="btn sm" onclick="capturePhoto()">📷 دوربین</button>
      <input type="file" id="ap-file" accept="image/*">
    </div>
    <div class="btn-row mt"><button class="btn primary" id="ap-save">ذخیره</button></div>`);
  let data = null;
  document.getElementById('ap-file').addEventListener('change', e=>{
    const f = e.target.files[0]; if(!f) return;
    const r = new FileReader();
    r.onload = ev => data = ev.target.result;
    r.readAsDataURL(f);
  });
  document.getElementById('ap-save').onclick = async ()=>{
    if(!data && window.__photoData) data = window.__photoData;
    if(!data) return toast('تصویری انتخاب نشده','err');
    await api('/api/banknote/photo',{method:'POST', body:{banknote_id:bnId, data}});
    toast('عکس ذخیره شد ✔'); closeModal(); openBanknote(bnId);
  };
}

/* ============================================================
   درآمد و هزینه
   ============================================================ */
async function renderExpenses(kind){
  currentExpKind = kind;
  const d = await api('/api/expenses?kind='+kind);
  const rows = d.items.map(e=>`
    <tr>
      <td>${dateTimeFa(e.created_at)}</td>
      <td><b>${esc(e.title)}</b></td>
      <td>${esc(e.category||'—')}</td>
      <td class="num">${fmt(e.amount, e.decimals, e.unit_ratio)} ${esc(e.code)}</td>
      <td class="num">${fmt(e.rial_value,0,1)} ریال</td>
      <td>${delBtn(kind, e.id, kind)}</td>
    </tr>`).join('');
  return `
  <div class="flex between mb">
    <div class="seg">
      <button class="${kind==='expense'?'active':''}" onclick="navigateExp('expense')">هزینه‌ها</button>
      <button class="${kind==='income'?'active':''}" onclick="navigateExp('income')">درآمدها</button>
    </div>
    <button class="btn primary" onclick="openExpForm('${kind}')">+ ${kind==='expense'?'ثبت هزینه':'ثبت درآمد'}</button>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>تاریخ</th><th>عنوان</th><th>دسته</th><th>مبلغ</th><th>معادل ریالی</th><th></th></tr></thead>
    <tbody>${rows||'<tr><td colspan="6" class="empty">موردی نیست</td></tr>'}</tbody></table></div></div>`;
}
function navigateExp(kind){ currentExpKind = kind; document.getElementById('content').innerHTML='<div class="loader"></div>'; renderExpenses(kind).then(h=>document.getElementById('content').innerHTML=h); }

function openExpForm(kind){
  const fx = state.currencies.filter(c=>c.is_active);
  const isExp = kind==='expense';
  openModal(`
    <h2>${isExp?'ثبت هزینه':'ثبت درآمد'} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div class="full"><label>عنوان *</label><input id="ex-title" placeholder="${isExp?'مثلاً اجاره دفتر':'مثلاً کارمزد حواله'}"></div>
      <div><label>ارز</label><select id="ex-currency">${fx.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div><label>مبلغ</label><input type="text" inputmode="decimal" id="ex-amount" class="input-num"></div>
      <div><label>نرخ (ریال/واحد)</label><input type="text" inputmode="numeric" id="ex-rate" class="input-num" value="0"></div>
      <div><label>صندوق</label><select id="ex-cashbox">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div class="full"><label>توضیحات</label><input id="ex-desc"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="ex-save">ثبت</button></div>`);
  bindNumField('ex-amount', {decimals:2, syncDecimals:true, hint:true, kind:'amount', currencyEl:'ex-currency'});
  bindNumField('ex-rate', {decimals:0, hint:true, kind:'rate'});
  document.getElementById('ex-currency').addEventListener('change', async e=>{
    try{ const r = await api('/api/rates'); const row = r.items.find(x=>x.currency_id===+e.target.value); if(row) setNum(document.getElementById('ex-rate'), row.rate); }catch(_){}
  });
  document.getElementById('ex-save').onclick = async ()=>{
    const c = currencyById(+document.getElementById('ex-currency').value);
    const a = numVal(document.getElementById('ex-amount'));
    try{
      await api(isExp?'/api/expense':'/api/income',{method:'POST', body:{
        title:document.getElementById('ex-title').value, currency_id:c.id,
        amount:Math.round(a*c.unit_ratio), rate:Math.round(numVal(document.getElementById('ex-rate'))),
        cashbox:+document.getElementById('ex-cashbox').value,
        description:document.getElementById('ex-desc').value}});
      toast('ثبت شد ✔'); closeModal(); navigateExp(kind);
    }catch(e){ toast(e.message,'err'); }
  };
}

/* ============================================================
   گزارش‌ها
   ============================================================ */
async function renderReports(){
  const cbs = await api('/api/cashboxes');
  return `
  <div class="card mb">
    <h3>📊 گزارش صندوق روزانه</h3>
    <div class="flex mb">
      <select id="rp-cashbox">${cbs.items.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select>
      <input data-jdp class="date-inp" id="rp-day" value="${faToday()}" placeholder="۱۴۰۵/۰۶/۱۸">
      <button class="btn primary" onclick="loadCashboxReport()">نمایش</button>
    </div>
    <div id="rp-cashbox-out"><div class="empty">در حال بارگذاری…</div></div>
  </div>
  <div class="card mb">
    <h3>📅 گزارش ماهانه</h3>
    <div class="flex mb">
      <input data-jdp class="date-inp" id="mo-from" value="${faMonthStart()}" placeholder="۱۴۰۵/۰۶/۰۱">
      <input data-jdp class="date-inp" id="mo-to" value="${faToday()}" placeholder="۱۴۰۵/۰۶/۱۸">
      <button class="btn primary" onclick="loadMonthlyReport()">نمایش</button>
    </div>
    <div id="rp-monthly-out"><div class="empty">در حال بارگذاری…</div></div>
  </div>
  <div class="grid cols-2 mb">
    <div class="card">
      <h3>💰 سود و زیان دوره‌ای</h3>
      <div class="flex mb">
        <input data-jdp class="date-inp" id="pl-from" value="${faMonthStart()}" placeholder="۱۴۰۵/۰۶/۰۱">
        <input data-jdp class="date-inp" id="pl-to" value="${faToday()}" placeholder="۱۴۰۵/۰۶/۱۸">
        <button class="btn primary" onclick="loadProfitReport()">محاسبه</button>
      </div>
      <div id="rp-profit-out"><div class="empty">در حال بارگذاری…</div></div>
    </div>
    <div class="card">
      <h3>👤 گزارش طرف حساب</h3>
      <div class="flex mb">
        <select id="rp-party">${state.parties.filter(p=>p.is_active).map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join('')}</select>
        <button class="btn primary" onclick="openParty(+document.getElementById('rp-party').value)">نمایش پروفایل</button>
      </div>
      <div class="small muted">پروفایل کامل شامل فاکتورها، مانده حساب، قرض‌ها و اسکناس‌ها در بخش «مشتریان» قابل مشاهده است.</div>
    </div>
  </div>
  <div class="card mb">
    <h3>⬇ خروجی داده</h3>
    <div class="flex">
      <button class="btn" onclick="downloadPdf()">🖨 گزارش PDF</button>
      <a class="btn" href="/api/export/csv?type=transactions">تراکنش‌ها (CSV)</a>
      <a class="btn" href="/api/export/csv?type=invoices">فاکتورها (CSV)</a>
      <a class="btn" href="/api/export/csv?type=banknotes">اسکناس‌ها (CSV)</a>
      <a class="btn" href="/api/export/csv?type=parties">طرف حساب‌ها (CSV)</a>
      <a class="btn" href="/api/export/all" target="_blank">بکاپ کامل (JSON)</a>
    </div>
    <div class="small muted mt">CSV با BOM ذخیره می‌شود تا در اکسل، فارسی درست نمایش داده شود. PDF بر اساس بازه‌ی «سود و زیان» ساخته می‌شود.</div>
  </div>`;
}

async function downloadPdf(){
  const frm = faDateToIso(document.getElementById('pl-from').value) || '';
  const to = faDateToIso(document.getElementById('pl-to').value) || '';
  if(!frm || !to) return toast('ابتدا بازه‌ی سود و زیان را تعیین کنید','warn');
  toast('در حال ساخت PDF…');
  try{
    const headers = {};
    if(state.token) headers['X-Token'] = state.token;
    if(state.accountId != null) headers['X-Account-Id'] = state.accountId;
    const res = await fetch(`/api/report/pdf?from=${frm}&to=${to}`, {headers});
    if(!res.ok){
      const j = await res.json().catch(()=>({}));
      throw new Error(j.error || 'خطا در ساخت PDF');
    }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `sarrafi-report-${frm}-${to}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    toast('گزارش PDF دانلود شد ✔');
  }catch(e){ toast(e.message,'err'); }
}

async function loadCashboxReport(){
  const cb = document.getElementById('rp-cashbox').value;
  const day = faDateToIso(document.getElementById('rp-day').value);
  if(!day) return toast('تاریخ معتبر نیست','err');
  const d = await api(`/api/report/cashbox?cashbox=${cb}&day=${day}`);
  const rows = d.items.map(it=>{
    const c = currencyByCode(it.currency) || {decimals:0, unit_ratio:1};
    return `
    <tr>
      <td><b>${esc(it.currency)}</b></td>
      <td class="num">${fmt(it.opening, c.decimals, c.unit_ratio)}</td>
      <td class="num" style="color:var(--green)">${fmt(it.inflow, c.decimals, c.unit_ratio)}</td>
      <td class="num" style="color:var(--red)">${fmt(it.outflow, c.decimals, c.unit_ratio)}</td>
      <td class="num"><b>${fmt(it.closing, c.decimals, c.unit_ratio)}</b></td>
    </tr>`;
  }).join('');
  document.getElementById('rp-cashbox-out').innerHTML = `
    <div class="small muted mb">تاریخ گزارش: ${faDateFromIso(d.day)}</div>
    <div id="rp-cashbox-chart" class="mb"></div>
    <div class="table-wrap"><table><thead><tr><th>ارز</th><th>مانده اول روز</th><th>ورودی</th><th>خروجی</th><th>مانده پایان روز</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  // نمودار میله‌ای ورودی/خروجی/مانده پایان به تفکیک ارز
  Charts.bar(document.getElementById('rp-cashbox-chart'),
    d.items.map(it=>it.currency),
    [{name:'ورودی', values:d.items.map(it=>it.inflow), color:'#34d399'},
     {name:'خروجی', values:d.items.map(it=>it.outflow), color:'#f87171'},
     {name:'مانده پایان', values:d.items.map(it=>it.closing), color:'#38bdf8'}],
    {height: 240});
}

async function loadMonthlyReport(){
  const frm = faDateToIso(document.getElementById('mo-from').value);
  const to = faDateToIso(document.getElementById('mo-to').value);
  if(!frm || !to) return toast('بازه را کامل انتخاب کنید','err');
  const d = await api(`/api/report/monthly?from=${frm}&to=${to}`);
  const rows = d.items.map(it=>`
    <tr>
      <td><b>${esc(it.month)}</b></td><td>${esc(it.month_name)}</td>
      <td class="num">${fmt(it.buy,0,1)}</td>
      <td class="num">${fmt(it.sell,0,1)}</td>
      <td class="num">${fmt(it.income,0,1)}</td>
      <td class="num">${fmt(it.expense,0,1)}</td>
      <td class="num" style="color:${it.net>=0?'var(--green)':'var(--red)'}"><b>${fmt(it.net,0,1)}</b></td>
    </tr>`).join('');
  document.getElementById('rp-monthly-out').innerHTML = `
    <div class="small muted mb">بازه: ${d.from_fa} تا ${d.to_fa}</div>
    <div id="rp-monthly-chart" class="mb"></div>
    <div class="table-wrap"><table><thead><tr><th>ماه</th><th>نام ماه</th><th>خرید</th><th>فروش</th><th>درآمد</th><th>هزینه</th><th>سود/زیان</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="7" class="empty">داده‌ای نیست</td></tr>'}</tbody></table></div>`;
  // نمودار مقایسه‌ای ماهانه
  Charts.bar(document.getElementById('rp-monthly-chart'),
    d.items.map(it=>it.month_name),
    [{name:'درآمد', values:d.items.map(it=>it.income), color:'#34d399'},
     {name:'هزینه', values:d.items.map(it=>it.expense), color:'#f87171'},
     {name:'سود/زیان', values:d.items.map(it=>it.net), color:'#38bdf8'}],
    {height: 240});
}

async function loadProfitReport(){
  const frm = faDateToIso(document.getElementById('pl-from').value);
  const to = faDateToIso(document.getElementById('pl-to').value);
  if(!frm || !to) return toast('بازه را کامل انتخاب کنید','err');
  const d = await api(`/api/report/profit?from=${frm}&to=${to}`);
  const pl = d.pl;
  const pc = d.per_currency.map(c=>`
    <tr><td>${esc(c.name)} (${esc(c.code)})</td>
    <td class="num">${fmt(c.sold, 2, 100)}</td>
    <td class="num" style="color:${c.profit>=0?'var(--green)':'var(--red)'}">${fmt(c.profit,0,1)}</td></tr>`).join('');
  document.getElementById('rp-profit-out').innerHTML = `
    <div class="small muted mb">بازه: ${d.from_fa} تا ${d.to_fa}</div>
    <div class="grid cols-2 mb">
      <div id="rp-profit-chart"></div>
      <div id="rp-profit-pie"></div>
    </div>
    <div class="kv"><span>فروش</span><b class="num">${fmt(pl.sell,0,1)} ریال</b></div>
    <div class="kv"><span>خرید</span><b class="num">${fmt(pl.buy,0,1)} ریال</b></div>
    <div class="kv"><span>سایر درآمدها</span><b class="num">${fmt(pl.income,0,1)} ریال</b></div>
    <div class="kv"><span>هزینه‌ها</span><b class="num">${fmt(pl.expense,0,1)} ریال</b></div>
    <div class="kv"><span>سود/زیان خالص</span><b class="num" style="color:${pl.net>=0?'var(--green)':'var(--red)'}">${fmt(pl.net,0,1)} ریال</b></div>
    <h3 class="mt">سود محقق به تفکیک ارز (FIFO)</h3>
    <div class="table-wrap"><table><thead><tr><th>ارز</th><th>مقدار فروخته‌شده</th><th>سود محقق (ریال)</th></tr></thead><tbody>${pc}</tbody></table></div>`;
  // نمودار مقایسه‌ای درآمد/هزینه/سود دوره
  const totalIncome = (pl.sell||0) + (pl.income||0);
  const totalCost = (pl.buy||0) + (pl.expense||0);
  Charts.bar(document.getElementById('rp-profit-chart'),
    ['این دوره'],
    [{name:'درآمد کل', values:[totalIncome], color:'#34d399'},
     {name:'هزینه کل', values:[totalCost], color:'#f87171'},
     {name:'سود خالص', values:[pl.net||0], color:'#38bdf8'}],
    {height: 220});
  // دایره‌ای سهم سود محقق هر ارز
  const pieData = d.per_currency.filter(c=>c.profit!==0).map(c=>({label:`${c.code}`, value:c.profit}));
  if(pieData.length){
    Charts.pie(document.getElementById('rp-profit-pie'), pieData, {donut:true, height: 220});
  } else {
    document.getElementById('rp-profit-pie').innerHTML = '<div class="empty">سود محققی در این بازه نیست</div>';
  }
}

/* ============================================================
   نمودارها
   ============================================================ */
async function renderCharts(){
  const frm = faDateFromIso(new Date(Date.now()-30*86400000).toISOString().slice(0,10));
  const today = faToday();
  const isSuper = state.user && state.user.role === 'super_admin';
  const accs = (state.me && state.me.accounts) || [];
  const needAccount = isSuper && !state.accountId;
  const acctSel = needAccount ? `<select id="ch-account" onchange="loadCharts()">
      ${accs.map((a,i)=>`<option value="${a.id}" ${i===0?'selected':''}>${esc(a.name)}</option>`).join('')}
    </select>` : '';
  return `
  <div class="card mb">
    <div class="flex mb">
      ${acctSel}
      <input data-jdp class="date-inp" id="ch-from" value="${frm}" placeholder="۱۴۰۵/۰۵/۱۰">
      <input data-jdp class="date-inp" id="ch-to" value="${today}" placeholder="۱۴۰۵/۰۶/۱۸">
      <button class="btn primary" onclick="loadCharts()">نمایش</button>
      <span class="chip">تحلیل خودکار — بدون کدنویسی</span>
    </div>
    ${needAccount && !accs.length ? '<div class="alert warn">هنوز حسابی (مشترکی) ثبت نشده است.</div>' : ''}
    <div id="ch-out"><div class="loader">در حال بارگذاری…</div></div>
  </div>`;
}

async function loadCharts(){
  const frm = faDateToIso(document.getElementById('ch-from').value);
  const to = faDateToIso(document.getElementById('ch-to').value);
  if(!frm || !to) return toast('بازه را کامل انتخاب کنید','err');
  const sel = document.getElementById('ch-account');
  const opts = {};
  if(sel && !state.accountId) opts.account = +sel.value;
  const d = await api(`/api/report/charts?from=${frm}&to=${to}`, opts);
  const out = document.getElementById('ch-out');

  const compData = d.cashbox_composition.map(c=>({label:`${c.name} (${c.code})`, value:c.rial}));
  const expData = d.expense_by_category.map(c=>({label:c.category, value:c.total}));

  const m = d.monthly;
  const hasData = compData.length || expData.length || m.length || d.buy_sell_daily.length || d.top_parties.length;
  if(!hasData){
    out.innerHTML = `<div class="empty">در این بازه و برای حساب انتخاب‌شده داده‌ای نیست — بازه یا حساب دیگری را امتحان کنید.</div>`;
    return;
  }
  const barHtml = `<div class="card mb"><h3>📊 مقایسه ماهانه — درآمد / هزینه / سود</h3><div id="ch-monthly"></div></div>`;
  const lineHtml = `<div class="card mb"><h3>📈 روند روزانه خرید و فروش</h3><div id="ch-daily"></div></div>`;
  const pie1 = `<div class="card mb"><h3>🥧 ترکیب صندوق (معادل ریالی)</h3><div id="ch-comp"></div></div>`;
  const pie2 = `<div class="card mb"><h3>🍩 هزینه‌ها به تفکیک دسته</h3><div id="ch-exp"></div></div>`;
  const hbarHtml = `<div class="card mb"><h3>🏆 طرف حساب‌های برتر (حجم معامله)</h3><div id="ch-parties"></div></div>`;
  const rateHtml = (d.rate_trend && d.rate_trend.length) ? `<div class="card mb"><h3>📉 روند نرخ ارز</h3><div class="grid cols-2">${d.rate_trend.map((t,i)=>`<div id="ch-rate-${i}"></div>`).join('')}</div></div>` : '';
  const yc = d.year_compare;
  const ycHtml = yc ? `<div class="card mb"><h3>🗓 مقایسه با سال قبل <span class="small muted">(${yc.prev_from_fa} تا ${yc.prev_to_fa})</span></h3><div id="ch-year"></div></div>` : '';

  out.innerHTML = `${ycHtml}<div class="grid cols-2">${pie1}${pie2}</div>${barHtml}${rateHtml}${lineHtml}${hbarHtml}`;

  Charts.pie(document.getElementById('ch-comp'), compData, {donut:false});
  Charts.pie(document.getElementById('ch-exp'), expData, {donut:true});
  Charts.bar(document.getElementById('ch-monthly'),
    m.map(x=>x.month_name),
    [{name:'درآمد', values:m.map(x=>x.income), color:'#34d399'},
     {name:'هزینه', values:m.map(x=>x.expense), color:'#f87171'},
     {name:'سود خالص', values:m.map(x=>x.net), color:'#38bdf8'}]);
  Charts.line(document.getElementById('ch-daily'),
    d.buy_sell_daily.map(x=>faDateFromIso(x.d)),
    [{name:'خرید', values:d.buy_sell_daily.map(x=>x.buy), color:'#34d399'},
     {name:'فروش', values:d.buy_sell_daily.map(x=>x.sell), color:'#38bdf8'}]);
  Charts.hbar(document.getElementById('ch-parties'),
    d.top_parties.map(x=>({label:x.full_name, value:x.volume})));
  if(d.rate_trend){
    d.rate_trend.forEach((t,i)=>{
      const el = document.getElementById('ch-rate-'+i);
      if(!el) return;
      Charts.line(el, t.points.map(p=>faDateFromIso(String(p.rate_date).slice(0,10))),
        [{name:`${t.name} (${t.code})`, values:t.points.map(p=>p.rate), color:Charts.PALETTE[i%Charts.PALETTE.length]}],
        {height:200});
    });
  }
  if(yc){
    Charts.bar(document.getElementById('ch-year'),
      ['خرید','فروش','درآمد','هزینه','سود خالص'],
      [{name:'دوره جاری', values:[yc.current.buy, yc.current.sell, yc.current.income, yc.current.expense, yc.current.net], color:'#38bdf8'},
       {name:'سال قبل', values:[yc.previous.buy, yc.previous.sell, yc.previous.income, yc.previous.expense, yc.previous.net], color:'#94a3b8'}]);
  }
}

/* ============================================================
   مشترکین (سوپرادمین)
   ============================================================ */
async function renderAccounts(){
  const d = await api('/api/accounts');
  const rows = d.items.map(a=>`
    <tr>
      <td><div class="flex" style="align-items:center;gap:8px">${a.logo?`<img src="/${esc(a.logo)}" alt="لوگو" class="acct-logo">`:''}<b>${esc(a.name)}</b></div></td>
      <td><span class="badge ${a.plan==='pro'?'purple':'gray'}">${a.plan==='pro'?'حرفه‌ای':'رایگان'}</span></td>
      <td>${a.status==='active'?'<span class="badge green">فعال</span>':'<span class="badge red">معلق</span>'}</td>
      <td class="num">${faDigits(a.users)}</td>
      <td class="num">${faDigits(a.parties)}</td>
      <td class="num">${faDigits(a.invoices)}</td>
      <td>${esc(a.owner_name||'—')}</td>
      <td>
        <button class="btn xs" onclick="viewAccount(${a.id})">👁 مشاهده</button>
        <button class="btn xs warn" onclick="impersonateUser(${a.id}, true)">🔑 ورود</button>
        <button class="btn xs" onclick="openAccountForm(${a.id})">✎</button>
        ${delBtn('account', a.id)}
      </td>
    </tr>`).join('');
  return `
  <div class="flex between mb">
    <div></div>
    <button class="btn primary" onclick="openAccountForm()">+ حساب جدید</button>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>نام حساب</th><th>پلن</th><th>وضعیت</th><th>کاربران</th><th>طرف حساب</th><th>فاکتورها</th><th>مالک</th><th>عملیات</th></tr></thead>
    <tbody>${rows}</tbody></table>
  </div></div>
  <div class="small muted mt">🔑 «ورود» = ورود مستقیم به حساب مشترک بدون نام کاربری و رمز. 👁 «مشاهده» = مرور داده‌ی حساب از دید سوپرادمین.</div>`;
}

/* ============================================================
   تراکنش‌ها
   ============================================================ */
let txPage = 1;
function txRow(t){
  return `<tr class="clickable" onclick="openJournal(${t.journal_id})">
      <td>${dateTimeFa(t.created_at)}</td>
      <td><span class="badge blue">${JTYPE_FA[t.jtype]||t.jtype}</span></td>
      <td>${t.direction==='debit'?'<span class="badge green">+ ورود</span>':'<span class="badge red">− خروج</span>'}</td>
      <td>${t.cashbox_name?('صندوق '+esc(t.cashbox_name)):t.party_name?esc(t.party_name):'—'}</td>
      <td class="num">${fmt(t.amount, t.decimals, t.unit_ratio)} ${esc(t.code)}</td>
      <td class="num">${t.rial_value?fmt(t.rial_value,0,1)+' ریال':''}</td>
    </tr>`;
}
async function renderTransactions(){
  txPage = 1;
  const d = await api('/api/transactions?limit=100&page=1');
  const rows = d.items.map(txRow).join('');
  const more = d.total > d.items.length ? `<div class="mt"><button class="btn" onclick="loadMoreTransactions()">نمایش بیشتر (${fmt(d.total - d.items.length,0,1)} مورد باقی)</button></div>` : '';
  return `<div class="flex between mb">
    <button class="btn" onclick="exportXlsx('transactions')">📥 خروجی اکسل (xlsx)</button>
    <span class="small muted">${fmt(d.total,0,1)} تراکنش</span>
  </div>
  <div class="card"><div class="table-wrap">
    <table><thead><tr><th>زمان</th><th>نوع</th><th>جهت</th><th>حساب</th><th>مبلغ</th><th>معادل ریالی</th></tr></thead>
    <tbody id="tx-tbody">${rows||'<tr><td colspan="6" class="empty">تراکنشی نیست</td></tr>'}</tbody></table></div>${more}</div>`;
}
async function loadMoreTransactions(){
  txPage++;
  const d = await api(`/api/transactions?limit=100&page=${txPage}`);
  document.getElementById('tx-tbody').insertAdjacentHTML('beforeend', d.items.map(txRow).join(''));
  if (txPage * 100 >= d.total){ document.querySelector('#content .mt button')?.remove(); }
}

async function openJournal(id){
  const d = await api('/api/journal?id='+id);
  const j = d.journal;
  const legs = d.legs.map(l=>`
    <tr>
      <td>${l.direction==='debit'?'<span class="badge green">+ ورود</span>':'<span class="badge red">− خروج</span>'}</td>
      <td>${l.account_type==='cashbox'?('صندوق: '+(l.cashbox_name||'')):l.account_type==='party'?('طرف حساب: '+(l.party_name||'')):'حساب داخلی'}</td>
      <td class="num">${fmt(l.amount, l.decimals, l.unit_ratio)} ${esc(l.code)}</td>
      <td class="num">${fmt(l.rial_value,0,1)} ریال</td>
    </tr>`).join('');
  const canVoid = ['super_admin','admin','accountant'].includes(state.user.role) && j.status!=='voided';
  openModal(`
    <h2>سند #${j.id} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="kv"><span>نوع</span><b>${JTYPE_FA[j.jtype]||j.jtype}</b></div>
    <div class="kv"><span>عنوان</span><span>${esc(j.title||'—')}</span></div>
    <div class="kv"><span>زمان</span><span>${dateTimeFa(j.created_at)}</span></div>
    <div class="kv"><span>وضعیت</span>${j.status==='voided'?'<span class="badge red">لغو شده</span>':'<span class="badge green">ثبت شده</span>'}</div>
    ${j.status==='voided'?`<div class="kv"><span>دلیل لغو</span><span>${esc(j.void_reason||'—')}</span></div>`:''}
    <div class="table-wrap mt"><table><thead><tr><th>جهت</th><th>حساب</th><th>مبلغ</th><th>معادل ریالی</th></tr></thead><tbody>${legs}</tbody></table></div>
    ${canVoid?`
    <div class="mt">
      <div class="alert warn">لغو سند برگشت‌ناپذیر است و در تاریخچه باقی می‌ماند.</div>
      <input id="void-reason" placeholder="دلیل لغو…" style="margin-bottom:8px">
      <button class="btn danger" onclick="voidJournal(${j.id})">لغو سند</button>
    </div>`:''}
    <div class="btn-row mt"><button class="btn ghost" onclick="closeModal()">بستن</button></div>`);
}

async function voidJournal(id){
  const reason = document.getElementById('void-reason').value;
  if(!reason) return toast('دلیل لغو را بنویسید','err');
  try{
    await api('/api/void',{method:'POST', body:{journal_id:id, reason}});
    toast('سند لغو شد'); closeModal(); navigate('transactions');
  }catch(e){ toast(e.message,'err'); }
}

/* ============================================================
   حذف نرم (v0.8) — دکمه حذف + پنجره تأیید + سطل بازیافت
   ============================================================ */
let currentExpKind = 'expense';

function canDelete(){
  const u = state.user || {};
  if(u.role === 'super_admin' || u.role === 'admin') return true;
  const perms = (state.me && state.me.perms) || [];
  return perms.includes('all') || perms.includes('delete');
}

function delBtn(type, id, after){
  if(!canDelete()) return '';
  const a = after ? `, '${after}'` : '';
  return `<button class="btn xs danger" title="حذف" onclick="event.stopPropagation();confirmDelete('${type}', ${id}${a})">🗑</button>`;
}

async function confirmDelete(type, id, after){
  if(!canDelete()) return toast('مجوز حذف ندارید','err');
  let info;
  try{ info = await api('/api/delete/info?type='+type+'&id='+id); }
  catch(e){ return toast(e.message,'err'); }
  const warnings = (info.warnings||[]).map(w=>`<div class="alert warn" style="margin:6px 0">⚠ ${esc(w)}</div>`).join('');
  openModal(`
    <h2>🗑 حذف ${esc(info.label)} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="alert warn">
      <div style="font-size:15px">آیا از حذف <b>«${esc(info.name)}»</b> مطمئن هستید؟</div>
      <div class="small muted mt">نوع رکورد: ${esc(info.label)} — ${info.reversible?'قابل بازیابی از سطل بازیافت':'اثر مالی دارد'}</div>
    </div>
    ${warnings}
    <div class="btn-row mt">
      <button class="btn danger" id="del-confirm">🗑 بله، حذف کن</button>
      <button class="btn ghost" onclick="closeModal()">انصراف</button>
    </div>`);
  document.getElementById('del-confirm').onclick = async ()=>{
    try{
      await api('/api/delete',{method:'POST', body:{type:type, id:id}});
      toast('حذف شد ✔');
      closeModal();
      reloadAfterDelete(after);
    }catch(e){ toast(e.message,'err'); }
  };
}

function reloadAfterDelete(after){
  if(after === 'expense' || after === 'income'){ navigateExp(after); return; }
  navigate(after || state.section);
}

async function openRecycleBin(){
  let d;
  try{ d = await api('/api/deleted'); }catch(e){ return toast(e.message,'err'); }
  const items = d.items || [];
  const rows = items.map(it=>`
    <tr>
      <td><span class="badge gray">${esc(it.label)}</span></td>
      <td><b>${esc(it.name)}</b></td>
      <td class="num">${dateTimeFa(it.deleted_at)}</td>
      <td><button class="btn xs" onclick="restoreDeleted('${it.type}', ${it.id})">↩ بازیابی</button></td>
    </tr>`).join('');
  openModal(`
    <h2>♻️ سطل بازیافت <button class="close" onclick="closeModal()">×</button></h2>
    <p class="small muted mb">رکوردهای حذف‌شده اینجا هستند؛ با «بازیابی» دوباره در فهرست‌ها ظاهر می‌شوند (اثر مالیِ لغو‌شده برنمی‌گردد).</p>
    <div class="table-wrap"><table><thead><tr><th>نوع</th><th>نام</th><th>زمان حذف</th><th></th></tr></thead>
    <tbody>${rows||'<tr><td colspan="4" class="empty">مورد حذف‌شده‌ای نیست</td></tr>'}</tbody></table></div>
    <div class="btn-row mt"><button class="btn ghost" onclick="closeModal()">بستن</button></div>`, true);
}

async function restoreDeleted(type, id){
  try{
    await api('/api/restore',{method:'POST', body:{type:type, id:id}});
    toast('بازیابی شد ✔');
    reloadAfterDelete(state.section === 'expenses' ? currentExpKind : state.section);
    openRecycleBin();
  }catch(e){ toast(e.message,'err'); }
}


/* ============================================================
   تنظیمات
   ============================================================ */
async function saveAccountLogo(){
  const f = document.getElementById('acct-logo-file').files[0];
  if(!f) return toast('یک فایل تصویر انتخاب کنید','warn');
  try{
    const data = await fileToDataURL(f);
    await api('/api/account/logo', {method:'POST', body:{data}});
    toast('لوگو بارگذاری شد ✔');
    state.me = await api('/api/me'); refreshBrand();
    navigate('settings');
  }catch(e){ toast(e.message,'err'); }
}
async function removeAccountLogo(){
  if(!confirm('لوگوی حساب حذف شود؟')) return;
  try{
    await api('/api/account/logo', {method:'POST', body:{data:''}});
    toast('لوگو حذف شد');
    state.me = await api('/api/me'); refreshBrand();
    navigate('settings');
  }catch(e){ toast(e.message,'err'); }
}

async function renderSettings(){
  const isSuper = state.user.role === 'super_admin';
  const isAdmin = ['super_admin','admin'].includes(state.user.role);
  let users = [], health = null, ratesStatus = null, backups = {items:[]};
  try{ users = (await api('/api/users')).items || []; state.usersCache = users; }catch(e){}
  try{ health = await api('/api/health'); }catch(e){}
  try{ ratesStatus = await api('/api/rates/status'); }catch(e){}
  try{ backups = await api('/api/backup/list'); }catch(e){ backups = {items:[]}; }

  const usersRows = users.map(u=>`
    <tr><td><b>${esc(u.full_name)}</b></td><td class="num">${esc(u.username)}</td>
    <td><span class="badge blue">${ROLE_FA[u.role]||u.role}</span></td>
    <td>${u.is_active?'<span class="badge green">فعال</span>':'<span class="badge gray">غیرفعال</span>'}</td>
    <td>${isAdmin?`<button class="btn xs" onclick="openUserForm(${u.id})">✎</button>
      <button class="btn xs warn" onclick="impersonateUser(${u.id})">🔑</button>
      ${u.id!==state.user.id?delBtn('user', u.id):''}`:''}</td></tr>`).join('');

  const rates = await api('/api/rates');
  const rateRows = rates.items.filter(r=>r.code!=='IRR').map(r=>`
    <tr><td>${esc(r.name)} (${esc(r.code)})</td>
    <td><input type="text" inputmode="numeric" class="input-num" id="rate-${r.currency_id}" value="${r.rate}" style="max-width:200px"></td>
    <td><button class="btn xs" onclick="saveRate(${r.currency_id})">ذخیره</button></td></tr>`).join('');

  const bkRows = (backups.items||[]).slice(0,10).map(b=>`
    <tr><td class="num">${esc(b.name)}</td>
    <td class="num">${fmt(b.size,0,1)} بایت</td>
    <td><a class="btn xs" href="/api/backup/download?file=${esc(b.name)}" target="_blank">دانلود</a></td></tr>`).join('');

  const provOpts = Object.entries(ratesStatus.providers||{})
    .map(([k,v])=>`<option value="${k}" ${ratesStatus.source===k?'selected':''}>${esc(v)}</option>`).join('');

  const audit = await api('/api/audit');
  const auditRows = audit.items.slice(0,40).map(a=>`
    <tr><td>${dateTimeFa(a.created_at)}</td><td>${esc(a.full_name||'—')}</td>
    <td><span class="badge gray">${esc(a.action)}</span></td>
    <td>${esc(a.entity||'')} ${a.entity_id||''}</td>
    <td class="small muted">${esc((a.detail||'').slice(0,80))}</td></tr>`).join('');

  const theme = localStorage.getItem('sarrafi_theme') || 'dark';
  const googleOk = health && health.google;

  let allCur = [], settings = {settings:{}}, plans = [], billing = [];
  if(isSuper){ try{ allCur = (await api('/api/currencies/all')).items || []; }catch(e){} }
  if(isAdmin){ try{ settings = await api('/api/settings'); }catch(e){} }
  if(isAdmin){ try{ plans = (await api('/api/plans')).items || []; }catch(e){} try{ billing = (await api('/api/billing')).items || []; }catch(e){} }
  const acctPlan = (state.me && state.me.account && state.me.account.plan) || 'free';
  const curRows = allCur.map(c=>`
    <tr><td><b>${esc(c.name)}</b> <span class="small muted">${esc(c.name_en||'')}</span></td>
    <td class="num">${esc(c.code)}</td>
    <td class="num">${esc(c.symbol)}</td>
    <td class="num">${c.decimals}</td>
    <td class="num">${c.unit_ratio}</td>
    <td>${c.is_active?'<span class="badge green">فعال</span>':'<span class="badge gray">غیرفعال</span>'}</td>
    <td><button class="btn xs" onclick="openCurrencyForm(${c.id})">✎</button> ${delBtn('currency', c.id)}</td></tr>`).join('');
  const minRows = state.currencies.filter(c=>c.code!=='IRR').map(c=>{
    const v = settings.settings['min_stock_'+c.code] || '';
    return `<tr><td><b>${esc(c.name)}</b> (${esc(c.code)})</td>
      <td><input type="text" inputmode="numeric" class="input-num" id="min-${c.code}" value="${v}" placeholder="—" style="max-width:160px"></td></tr>`;
  }).join('');

  return `
  ${isSuper?`<div class="card mb"><h3>💰 مدیریت ارزها</h3>
    <button class="btn primary mb" onclick="openCurrencyForm()">+ ارز جدید</button>
    <div class="table-wrap"><table><thead><tr><th>نام</th><th>کد</th><th>نماد</th><th>اعشار</th><th>ضریب</th><th>وضعیت</th><th></th></tr></thead><tbody>${curRows}</tbody></table></div>
    <div class="small muted mt">تغییر ارزها بلافاصله در کل سیستم اعمال می‌شود (فقط سوپرادمین).</div>
  </div>`:''}

  ${isAdmin?`<div class="card mb"><h3>🚨 هشدار کف موجودی</h3>
    <p class="small muted mb">برای هر ارز حداقل موجودی تعیین کنید؛ وقتی موجودی صندوق‌ها کمتر از آن شود، در داشبورد هشدار داده می‌شود.</p>
    <div class="table-wrap"><table><thead><tr><th>ارز</th><th>حداقل موجودی (واحد ارز)</th></tr></thead><tbody>${minRows}</tbody></table></div>
    <div class="btn-row mt"><button class="btn primary" onclick="saveLowStock()">ذخیره</button></div>
  </div>`:''}

  ${isSuper?`<div class="card mb"><h3>🌐 پیکربندی ورود گوگل</h3>
    <div class="alert ${googleOk?'ok':'warn'}">${googleOk?'گوگل پیکربندی شده است ✔':'گوگل هنوز پیکربندی نشده — Client ID و Secret را وارد کنید.'}</div>
    <div class="form-grid">
      <div><label>Google Client ID</label><input id="gcid" placeholder="xxxx.apps.googleusercontent.com"></div>
      <div><label>Google Client Secret</label><input id="gcs" type="password"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" onclick="saveGoogle()">ذخیره</button></div>
    <div class="small muted mt">Redirect URI: <code>/api/auth/google/callback</code> — آن را در Google Cloud Console ثبت کنید.</div>
  </div>`:''}

  ${isAdmin?`<div class="card mb"><h3>💳 اشتراک و صورتحساب</h3>
    <div class="small muted mb">پلن فعلی: <b>${esc((plans.find(p=>p.code===acctPlan)||{}).name || acctPlan)}</b></div>
    <div class="plan-grid mb">
      ${plans.map(p=>`<div class="plan-card ${acctPlan===p.code?'current':''}">
        ${acctPlan===p.code?'<span class="plan-tag badge green">فعال</span>':''}
        <div class="plan-name">${esc(p.name)}</div>
        <div class="plan-price">${fmt(p.price_rial,0,1)} ریال</div>
        <div class="plan-feat">${esc(p.features)}</div>
        ${acctPlan===p.code?'':`<button class="btn ${p.code==='pro'?'primary':'warn'} mt" onclick="checkoutPlan('${p.code}')">انتخاب</button>`}
      </div>`).join('')}
    </div>
    ${billing.length?`<div class="table-wrap"><table><thead><tr><th>پلن</th><th>مبلغ</th><th>وضعیت</th><th>زمان</th></tr></thead><tbody>
      ${billing.slice(0,10).map(b=>`<tr><td>${esc(b.plan_code)}</td><td class="num">${fmt(b.amount_rial,0,1)}</td>
        <td><span class="badge ${b.status==='paid'?'green':b.status==='pending'?'amber':'gray'}">${b.status==='paid'?'پرداخت شده':b.status==='pending'?'در انتظار':'ناموفق'}</span></td>
        <td>${dateTimeFa(b.paid_at||b.created_at)}</td></tr>`).join('')}
    </tbody></table></div>`:''}
  </div>`:''}

  ${isSuper?`<div class="card mb"><h3>📧 پیکربندی ایمیل (SMTP)</h3>
    <p class="small muted mb">برای ارسال واقعی کد بازیابی رمز از طریق ایمیل. اگر پیکربندی نشود، کد بازیابی فقط روی صفحه نمایش داده می‌شود.</p>
    <div class="form-grid">
      <div><label>Host</label><input id="smtp-host" placeholder="smtp.gmail.com" value="${esc(settings.settings.smtp_host||'')}"></div>
      <div><label>Port</label><input id="smtp-port" inputmode="numeric" value="${esc(settings.settings.smtp_port||'587')}"></div>
      <div><label>Username</label><input id="smtp-user" value="${esc(settings.settings.smtp_user||'')}"></div>
      <div><label>Password</label><input id="smtp-pass" type="password" value="${esc(settings.settings.smtp_pass||'')}"></div>
      <div><label>From (ایمیل فرستنده)</label><input id="smtp-from" value="${esc(settings.settings.smtp_from||'')}"></div>
      <div><label>TLS</label><select id="smtp-tls"><option value="1" ${settings.settings.smtp_tls!=='0'?'selected':''}>فعال</option><option value="0" ${settings.settings.smtp_tls==='0'?'selected':''}>غیرفعال</option></select></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" onclick="saveSmtp()">ذخیره</button></div>
  </div>`:''}

  ${isAdmin?`<div class="card mb"><h3>🧩 امکانات و ماژول‌ها</h3>
    <p class="small muted mb">هر قابلیت را برای ${isSuper?'حساب‌ها و کاربران':'کارمندان این حساب'} روشن یا خاموش کنید. بخش خاموش از منو حذف و در سرور هم مسدود می‌شود.</p>
    <div id="modules-box"><div class="loader">در حال بارگذاری…</div></div>
    <div class="small muted mt">💡 از دکمه‌ی «⚙» کنار هر کاربر هم می‌توانید امکانات همان کاربر را جداگانه تنظیم کنید.</div>
  </div>`:''}

  ${isAdmin?`<div class="card mb"><h3>🛡 سطح دسترسی نقش‌ها</h3>
    <p class="small muted mb">برای هر نقش مشخص کنید چه عملیاتی مجاز است؛ تغییرات بلافاصله روی کاربرانِ همان حساب اعمال می‌شود. (سوپرادمین همیشه دسترسی کامل دارد و قابل تغییر نیست.)</p>
    <div id="perms-box"><div class="loader">در حال بارگذاری…</div></div>
  </div>`:''}

  ${canDelete()?`<div class="card mb"><h3>♻️ سطل بازیافت</h3>
    <p class="small muted mb">هر رکورد حذف‌شده (طرف حساب، صندوق، فاکتور، اسکناس، هزینه، قرض و…) اینجا قابل بازیابی است.</p>
    <button class="btn" onclick="openRecycleBin()">♻️ مشاهده و بازیابی</button>
  </div>`:''}

  ${isAdmin && !isSuper ? `<div class="card mb"><h3>🏷 لوگوی حساب (برند)</h3>
    <p class="small muted mb">این لوگو در سایدبار برای همه‌ی کاربران حساب شما نمایش داده می‌شود. (سوپرادمین می‌تواند از فهرست مشترکین لوگوی هر حساب را بگذارد.)</p>
    <div class="flex" style="gap:10px;align-items:center;flex-wrap:wrap">
      ${(state.me.account && state.me.account.logo) ? `<img src="/${esc(state.me.account.logo)}" class="acct-logo-lg" alt="لوگو">` : ''}
      <input type="file" id="acct-logo-file" accept="image/png,image/jpeg,image/webp">
      <button class="btn primary" onclick="saveAccountLogo()">بارگذاری</button>
      ${(state.me.account && state.me.account.logo) ? `<button class="btn warn" onclick="removeAccountLogo()">حذف لوگو</button>` : ''}
    </div>
  </div>` : ''}

  <div class="card mb"><h3>💱 نرخ ارز آنلاین</h3>
    <div class="flex mb">
      <select id="rs-provider" style="max-width:280px">${provOpts}</select>
      <label class="flex" style="gap:6px;margin:0"><input type="checkbox" id="rs-auto" style="width:auto" ${ratesStatus.auto_refresh==='1'?'checked':''}> به‌روزرسانی خودکار (هر ۳۰ دقیقه)</label>
      <button class="btn sm" onclick="saveRateSettings()">ذخیره تنظیمات</button>
    </div>
    ${isAdmin?`<div class="flex mb" style="gap:8px;align-items:center;flex-wrap:wrap">
      <label class="small muted" style="margin:0">کلید API نوسان:</label>
      <input id="rs-navasan-key" type="password" autocomplete="off" style="max-width:280px"
        placeholder="${ratesStatus.navasan_key_set?'••• تنظیم شده — خالی = بدون تغییر':'از ربات @navasan_contact_bot بگیرید'}">
      <button class="btn sm" onclick="testNavasanKey()">تست اتصال</button>
      ${ratesStatus.navasan_key_set?`<button class="btn sm warn" onclick="clearNavasanKey()">حذف کلید</button>`:''}
      <span class="small muted">${ratesStatus.navasan_key_set?'کلید تنظیم شده ✔':'کلید تنظیم نشده — نرخ خودکار از منبع پشتیبان (er-api) گرفته می‌شود'}</span>
    </div>
    <div class="small muted mb">پیش‌فرض: «نوسان». اگر نوسان در دسترس نباشد (کلید/سهمیه)، خودکار به er-api و سپس سنا بازمی‌گردد. پلن رایگان نوسان ۱۲۰ درخواست در ماه دارد.</div>`:''}
    <div class="btn-row mb">
      <button class="btn primary" onclick="fetchRatesOnline()">🌐 دریافت نرخ از اینترنت (لحظه‌ای)</button>
    </div>
    ${ratesStatus.last_fetch?`<div class="small muted mb">آخرین دریافت: ${esc(ratesStatus.last_fetch)} (منبع: ${esc(ratesStatus.last_source||'—')})</div>`:''}
    <div class="table-wrap"><table><thead><tr><th>ارز</th><th>نرخ (ریال/واحد)</th><th></th></tr></thead><tbody>${rateRows}</tbody></table></div>
  </div>

  ${isAdmin?`<div class="grid cols-2 mb">
    <div class="card"><h3>👥 کاربران ${isSuper?'(انتخاب از حساب‌ها)':'و کارمندان'}</h3>
      <button class="btn primary mb" onclick="openUserForm()">+ کاربر جدید</button>
      <div class="table-wrap"><table><thead><tr><th>نام</th><th>نام کاربری</th><th>نقش</th><th>وضعیت</th><th></th></tr></thead><tbody>${usersRows}</tbody></table></div>
      <div class="small muted mt">🔑 = ورود به‌جای کاربر (بدون رمز). مدیر می‌تواند وارد حساب کارمندانش شود؛ سوپرادمین وارد هر حسابی.</div>
    </div>
    <div class="card"><h3>💾 بکاپ و بازیابی</h3>
      <button class="btn primary mb" onclick="makeBackup()">ایجاد بکاپ جدید</button>
      <div class="table-wrap"><table><thead><tr><th>فایل</th><th>حجم</th><th></th></tr></thead><tbody>${bkRows||'<tr><td colspan="3" class="empty">بکاپی موجود نیست</td></tr>'}</tbody></table></div>
      <hr style="border-color:var(--border);margin:12px 0">
      <label class="small muted">عبارت عبور بکاپ رمزنگاری‌شده (خالی = بدون رمزنگاری)</label>
      <div class="flex mt">
        <input type="password" id="bk-passphrase" placeholder="اختیاری" style="max-width:220px">
        <button class="btn sm" onclick="saveBackupPassphrase()">ذخیره</button>
      </div>
      <hr style="border-color:var(--border);margin:12px 0">
      <label class="small muted">بازیابی از فایل JSON (خروجی «بکاپ کامل»)</label>
      <div class="flex mt">
        <input type="file" id="restore-file" accept=".json,application/json" style="max-width:280px">
        <button class="btn warn" onclick="restoreBackup()">بازیابی</button>
      </div>
    </div>
  </div>`:''}

  <div class="grid cols-2 mb">
    ${isAdmin?`<div class="card"><h3>🛡 احراز دومرحله‌ای (2FA)</h3>
      ${state.user.totp_enabled
        ? `<div class="alert ok">فعال است ✔ — برای ورود، افزون بر رمز، کد برنامه Authenticator لازم است.</div>
           <div class="btn-row"><button class="btn warn" onclick="disable2fa()">غیرفعال‌کردن</button></div>`
        : `<div class="alert warn">غیرفعال — توصیه می‌شود برای حساب مدیر/سوپرادمین فعال شود.</div>
           <div class="btn-row"><button class="btn primary" onclick="enable2fa()">فعال‌سازی</button></div>`}
    </div>`:''}
    <div class="card"><h3>🔐 تغییر رمز عبور</h3>
      <div class="form-grid">
        <div><label>رمز فعلی</label><input id="pw-old" type="password"></div>
        <div><label>رمز جدید</label><input id="pw-new" type="password"></div>
        <div><label>تکرار رمز جدید</label><input id="pw-new2" type="password"></div>
      </div>
      <div class="btn-row mt"><button class="btn primary" onclick="changePassword()">ذخیره</button></div>
    </div>
    <div class="card"><h3>🎨 ظاهر (تم)</h3>
      <div class="flex">
        <button class="btn ${theme==='auto'?'primary':''}" onclick="applyTheme('auto')">🖥 خودکار (هماهنگ با سیستم)</button>
        <button class="btn ${theme==='dark'?'primary':''}" onclick="applyTheme('dark')">🌙 تم تیره</button>
        <button class="btn ${theme==='light'?'primary':''}" onclick="applyTheme('light')">☀️ تم روشن</button>
      </div>
    </div>
    <div class="card"><h3>📜 لاگ کاربران</h3>
      <div class="table-wrap"><table><thead><tr><th>زمان</th><th>کاربر</th><th>عملیات</th><th>جزئیات</th></tr></thead><tbody>${auditRows}</tbody></table></div>
    </div>
  </div>
  ${health?`<div class="card mb"><h3>🩺 سلامت سیستم</h3>
    <div class="grid cols-4">
      <div class="stat"><span class="label">موتور دیتابیس</span><span class="value" style="font-size:15px">${health.db.engine}</span></div>
      <div class="stat"><span class="label">نسخه</span><span class="value" style="font-size:15px">${esc(health.version)}</span></div>
      <div class="stat"><span class="label">OCR</span><span class="value" style="font-size:15px">${health.ocr?'<span style="color:var(--green)">فعال</span>':'<span style="color:var(--muted)">غیرفعال</span>'}</span></div>
      <div class="stat"><span class="label">ورود گوگل</span><span class="value" style="font-size:15px">${health.google?'<span style="color:var(--green)">فعال</span>':'<span style="color:var(--muted)">غیرفعال</span>'}</span></div>
    </div>
  </div>`:''}`;
}

async function saveGoogle(){
  try{
    await api('/api/google/save',{method:'POST', body:{
      google_client_id:document.getElementById('gcid').value,
      google_client_secret:document.getElementById('gcs').value}});
    toast('تنظیمات گوگل ذخیره شد ✔');
  }catch(e){ toast(e.message,'err'); }
}

async function saveRateSettings(){
  try{
    const body = {
      rate_source:document.getElementById('rs-provider').value,
      rate_auto_refresh:document.getElementById('rs-auto').checked?'1':'0'};
    const keyEl = document.getElementById('rs-navasan-key');
    if(keyEl && keyEl.value.trim()) body.rate_navasan_key = keyEl.value.trim();
    await api('/api/settings/save',{method:'POST', body});
    toast('تنظیمات نرخ ذخیره شد ✔');
    navigate('settings');
  }catch(e){ toast(e.message,'err'); }
}

async function testNavasanKey(){
  const keyEl = document.getElementById('rs-navasan-key');
  const key = keyEl ? keyEl.value.trim() : '';
  if(!key) return toast('اول کلید را وارد کنید','warn');
  toast('در حال تست اتصال به نوسان…');
  try{
    const r = await api('/api/rates/test',{method:'POST', body:{provider:'navasan', key}});
    toast('اتصال به نوسان برقرار شد ✔ — '+faDigits(r.count)+' نرخ دریافت شد','ok');
  }catch(e){ toast('تست ناموفق: '+e.message,'err'); }
}

async function clearNavasanKey(){
  if(!confirm('کلید API نوسان حذف شود؟ پس از حذف، نرخ خودکار از منبع پشتیبان گرفته می‌شود.')) return;
  try{
    await api('/api/settings/save',{method:'POST', body:{rate_navasan_key:''}});
    toast('کلید حذف شد'); navigate('settings');
  }catch(e){ toast(e.message,'err'); }
}

async function fetchRatesOnline(){
  toast('در حال دریافت نرخ از اینترنت…');
  try{
    const provider = document.getElementById('rs-provider').value;
    const r = await api('/api/rates/fetch',{method:'POST', body:{provider}});
    const names = (r.updated||[]).map(u=>`${u.code}: ${fmt(u.rate,0,1)}`).join('، ');
    let msg = 'نرخ‌ها به‌روز شد ✔ ('+esc(r.source_name)+')';
    if(r.fallback) msg += ' — منبع اصلی در دسترس نبود، از منبع پشتیبان دریافت شد';
    if(names) msg += ' — '+esc(names);
    toast(msg);
    navigate('settings');
  }catch(e){ toast('دریافت نرخ ناموفق: '+e.message,'err'); }
}

async function saveRate(cid){
  const v = document.getElementById('rate-'+cid).value;
  try{ await api('/api/rate',{method:'POST', body:{currency_id:cid, rate:+v}}); toast('نرخ ذخیره شد ✔'); }catch(e){ toast(e.message,'err'); }
}

async function enable2fa(){
  try{
    const r = await api('/api/2fa/start',{method:'POST', body:{}});
    openModal(`
      <h2>فعال‌سازی احراز دومرحله‌ای <button class="close" onclick="closeModal()">×</button></h2>
      <p class="small">۱) این کلید را در برنامه Authenticator (Google Authenticator، Authy و…) وارد کنید یا کد QR را اسکن کنید:</p>
      <div class="kv"><span>کلید</span><b id="tfa-secret" style="direction:ltr;letter-spacing:1px">${r.secret}</b></div>
      <div class="small muted mb">${esc(r.url)}</div>
      <p class="small">۲) کد ۶ رقمی نمایش‌داده‌شده در برنامه را وارد کنید:</p>
      <div class="form-grid"><div><label>کد تأیید</label><input id="tfa-code" inputmode="numeric" style="direction:ltr" placeholder="123456"></div></div>
      <div class="btn-row mt"><button class="btn primary" id="tfa-go">تأیید و فعال‌سازی</button></div>`);
    document.getElementById('tfa-go').onclick = async ()=>{
      try{
        const c = await api('/api/2fa/confirm',{method:'POST', body:{
          secret: r.secret, code: document.getElementById('tfa-code').value}});
        toast(c.message||'2FA فعال شد ✔'); closeModal();
        renderSettings().then(h=>document.getElementById('content').innerHTML=h);
      }catch(e){ toast(e.message,'err'); }
    };
  }catch(e){ toast(e.message,'err'); }
}

async function disable2fa(){
  openModal(`
    <h2>غیرفعال‌سازی 2FA <button class="close" onclick="closeModal()">×</button></h2>
    <p class="small">برای تأیید، کد فعلی برنامه یا رمز عبور را وارد کنید:</p>
    <div class="form-grid">
      <div><label>کد تأیید (یا رمز عبور)</label><input id="tfa-off" style="direction:ltr"></div>
    </div>
    <div class="btn-row mt"><button class="btn warn" id="tfa-off-go">غیرفعال‌کردن</button></div>`);
  document.getElementById('tfa-off-go').onclick = async ()=>{
    const v = document.getElementById('tfa-off').value;
    try{
      const body = v.length===6 && /^\d+$/.test(v) ? {code:v} : {password:v};
      const r = await api('/api/2fa/disable',{method:'POST', body});
      toast(r.message||'2FA غیرفعال شد ✔'); closeModal();
      renderSettings().then(h=>document.getElementById('content').innerHTML=h);
    }catch(e){ toast(e.message,'err'); }
  };
}

async function changePassword(){
  const old = document.getElementById('pw-old').value;
  const nw = document.getElementById('pw-new').value;
  const nw2 = document.getElementById('pw-new2').value;
  if(nw !== nw2) return toast('تکرار رمز جدید مطابقت ندارد','err');
  if(nw.length < 4) return toast('رمز جدید حداقل ۴ نویسه باشد','err');
  try{
    const r = await api('/api/password/change',{method:'POST', body:{old_password:old, new_password:nw}});
    toast(r.message||'رمز تغییر کرد ✔');
    document.getElementById('pw-old').value='';
    document.getElementById('pw-new').value='';
    document.getElementById('pw-new2').value='';
  }catch(e){ toast(e.message,'err'); }
}

async function saveLowStock(){
  const thresholds = {};
  state.currencies.filter(c=>c.code!=='IRR').forEach(c=>{
    const el = document.getElementById('min-'+c.code);
    if(el) thresholds[c.code] = el.value.trim();
  });
  try{
    await api('/api/lowstock/save',{method:'POST', body:{thresholds}});
    toast('کف موجودی ذخیره شد ✔');
  }catch(e){ toast(e.message,'err'); }
}

let __allCurrenciesCache = null;
async function openCurrencyForm(id){
  let c = null;
  if(id){
    if(!__allCurrenciesCache){ try{ __allCurrenciesCache = (await api('/api/currencies/all')).items; }catch(e){ __allCurrenciesCache=[]; } }
    c = __allCurrenciesCache.find(x=>x.id===id) || null;
  }
  const def = c || {name:'', name_en:'', code:'', symbol:'', decimals:2, unit_ratio:1, sort_order:99, is_active:1, default_rate:0};
  openModal(`
    <h2>${c?'ویرایش ارز':'ارز جدید'} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>نام فارسی *</label><input id="cur-name" value="${esc(def.name)}"></div>
      <div><label>نام انگلیسی</label><input id="cur-name-en" value="${esc(def.name_en)}" style="direction:ltr"></div>
      <div><label>کد ISO *</label><input id="cur-code" value="${esc(def.code)}" placeholder="USD" style="direction:ltr;text-transform:uppercase"></div>
      <div><label>نماد</label><input id="cur-symbol" value="${esc(def.symbol)}"></div>
      <div><label>اعشار</label><input id="cur-decimals" type="number" min="0" max="6" value="${def.decimals}"></div>
      <div><label>ضریب واحد (ریال‌برابر)</label><input id="cur-ratio" type="number" min="1" step="any" value="${def.unit_ratio}"></div>
      <div><label>نرخ پیش‌فرض</label><input id="cur-rate" type="number" step="any" value="${def.default_rate||0}"></div>
      <div><label>ترتیب</label><input id="cur-sort" type="number" value="${def.sort_order}"></div>
      <div><label>وضعیت</label><select id="cur-active">
        <option value="1" ${def.is_active?'selected':''}>فعال</option>
        <option value="0" ${!def.is_active?'selected':''}>غیرفعال</option></select></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="cur-save">ذخیره</button></div>`);
  document.getElementById('cur-save').onclick = async ()=>{
    try{
      await api('/api/currency/save',{method:'POST', body:{
        id:c?c.id:null,
        name:document.getElementById('cur-name').value,
        name_en:document.getElementById('cur-name-en').value,
        code:document.getElementById('cur-code').value.toUpperCase(),
        symbol:document.getElementById('cur-symbol').value,
        decimals:+document.getElementById('cur-decimals').value,
        unit_ratio:+document.getElementById('cur-ratio').value,
        default_rate:+document.getElementById('cur-rate').value,
        sort_order:+document.getElementById('cur-sort').value,
        is_active:+document.getElementById('cur-active').value}});
      __allCurrenciesCache = null;
      closeModal(); toast('ارز ذخیره شد ✔');
      renderSettings().then(h=>document.getElementById('content').innerHTML=h);
    }catch(e){ toast(e.message,'err'); }
  };
}
async function makeBackup(){
  try{ const r = await api('/api/backup',{method:'POST', body:{}}); toast('بکاپ ایجاد شد: '+r.file); renderSettings().then(h=>document.getElementById('content').innerHTML=h); }
  catch(e){ toast(e.message,'err'); }
}

function openUserForm(id){
  const u = id ? (state.usersCache||[]).find(x=>x.id==id) : {};
  const isSuper = state.user.role === 'super_admin';
  openModal(`
    <h2>${id?'ویرایش':'افزودن'} کاربر <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>نام کامل *</label><input id="uf-name" value="${esc(u.full_name||'')}"></div>
      <div><label>نام کاربری *</label><input id="uf-username" value="${esc(u.username||'')}"></div>
      <div><label>رمز عبور ${id?'(خالی = بدون تغییر)':''}</label><input id="uf-pass" type="password"></div>
      <div><label>نقش</label><select id="uf-role">
        ${(isSuper?['super_admin','admin','cashier','accountant','operator']:['admin','cashier','accountant','operator']).map(r=>`<option value="${r}" ${u.role===r?'selected':''}>${ROLE_FA[r]}</option>`).join('')}
      </select></div>
      ${isSuper?`<div><label>حساب (مشترک)</label><select id="uf-account">
        ${(state.me.accounts||[]).map(a=>`<option value="${a.id}" ${u.account_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}
      </select></div>`:''}
      <div><label>وضعیت</label><select id="uf-active"><option value="1" ${u.is_active!==0?'selected':''}>فعال</option><option value="0" ${u.is_active===0?'selected':''}>غیرفعال</option></select></div>
    </div>
    <div class="btn-row mt">
      <button class="btn primary" id="uf-save">ذخیره</button>
      ${id?`<button class="btn" onclick="openUserModules(${id})">⚙ امکانات این کاربر</button>`:''}
    </div>`);
  document.getElementById('uf-save').onclick = async ()=>{
    try{
      const body = {
        id: id||null, full_name:document.getElementById('uf-name').value,
        username:document.getElementById('uf-username').value,
        password:document.getElementById('uf-pass').value,
        role:document.getElementById('uf-role').value,
        is_active:+document.getElementById('uf-active').value};
      if(isSuper) body.account_id = +document.getElementById('uf-account').value;
      await api('/api/user/save',{method:'POST', body});
      toast('ذخیره شد ✔'); closeModal(); navigate('settings');
    }catch(e){ toast(e.message,'err'); }
  };
}

async function restoreBackup(){
  const f = document.getElementById('restore-file').files[0];
  if(!f) return toast('فایل JSON را انتخاب کنید','err');
  const txt = await f.text();
  let data; try{ data = JSON.parse(txt); }catch(e){ return toast('فایل JSON نامعتبر است','err'); }
  if(!confirm('بازیابی داده‌ها، اطلاعات فعلی را بازنویسی می‌کند. ادامه می‌دهید؟')) return;
  try{
    await api('/api/import',{method:'POST', body:{data}});
    toast('بازیابی انجام شد ✔'); navigate('settings');
  }catch(e){ toast(e.message,'err'); }
}

/* ============================================================
   ورود / ثبت‌نام / گوگل
   ============================================================ */
function openLogin(){
  openModal(`
    <h2>ورود به سیستم <button class="close" onclick="closeModal()">×</button></h2>
    <div class="alert ok">حساب‌های دمو: <b>admin / admin123</b> (مدیر) — <b>ali / 1234</b> (صندوق‌دار) — <b>sara / 1234</b> (حسابدار) — <b>root / root123</b> (سوپرادمین)</div>
    <div class="form-grid">
      <div><label>نام کاربری</label><input id="lg-user" value="admin"></div>
      <div><label>رمز عبور</label><input id="lg-pass" type="password" value="admin123"></div>
    </div>
    <div id="lg-2fa" style="display:none" class="mt">
      <div class="form-grid"><div><label>کد تأیید دومرحله‌ای (برنامه Authenticator)</label>
        <input id="lg-code" inputmode="numeric" style="direction:ltr" placeholder="123456"></div></div>
    </div>
    <div class="btn-row mt">
      <button class="btn primary" id="lg-go">ورود</button>
      <button class="btn" id="lg-google">ورود با گوگل</button>
      <button class="btn ghost" onclick="openSignup()">ثبت‌نام حساب جدید</button>
    </div>
    <div class="mt small"><a href="#" onclick="openForgotPassword(event)" class="muted">رمز عبور را فراموش کرده‌ام</a></div>`);
  document.getElementById('lg-go').onclick = async ()=>{
    try{
      const body = {username:document.getElementById('lg-user').value, password:document.getElementById('lg-pass').value};
      const code = document.getElementById('lg-code');
      if(code && code.value) body.code = code.value;
      const r = await api('/api/login',{method:'POST', body});
      state.token = r.token; state.user = r.user; localStorage.setItem('sarrafi_token', r.token);
      refreshUserChip();
      toast('خوش آمدید، '+r.user.full_name+' ✔'); closeModal();
      location.reload();
    }catch(e){
      if(e.data && e.data.need_2fa){
        const wrap = document.getElementById('lg-2fa');
        if(wrap) wrap.style.display='';
        toast('کد تأیید دومرحله‌ای لازم است','warn');
      } else {
        toast(e.message,'err');
      }
    }
  };
  document.getElementById('lg-google').onclick = async ()=>{
    try{
      const r = await api('/api/auth/google/url');
      if(!r.configured){ toast('ورود با گوگل پیکربندی نشده است (سوپرادمین: تنظیمات → پیکربندی گوگل)','warn'); return; }
      window.location.href = r.url;
    }catch(e){ toast(e.message,'err'); }
  };
}

function openForgotPassword(e){
  if(e) e.preventDefault();
  openModal(`
    <h2>بازیابی رمز عبور <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>نام کاربری</label><input id="fp-user" value="admin"></div>
    </div>
    <div class="btn-row mt"><button class="btn" id="fp-send">دریافت کد بازیابی</button></div>
    <div id="fp-code-area" style="display:none" class="mt">
      <div class="alert ok" id="fp-hint"></div>
      <div class="form-grid">
        <div><label>کد بازیابی</label><input id="fp-code" inputmode="numeric" style="direction:ltr"></div>
        <div><label>رمز عبور جدید</label><input id="fp-new" type="password"></div>
      </div>
      <div class="btn-row mt"><button class="btn primary" id="fp-go">تغییر رمز</button></div>
    </div>`);
  document.getElementById('fp-send').onclick = async ()=>{
    try{
      const r = await api('/api/password/forgot',{method:'POST', body:{username:document.getElementById('fp-user').value}});
      if(r.code){
        document.getElementById('fp-hint').textContent = 'کد یک‌بارمصرف شما: '+r.code+' (اعتبار '+r.ttl_minutes+' دقیقه)';
        document.getElementById('fp-code').value = r.code;
        document.getElementById('fp-code-area').style.display='';
      } else {
        toast(r.hint||'کد ساخته نشد','warn');
      }
    }catch(e){ toast(e.message,'err'); }
  };
  document.getElementById('fp-go').onclick = async ()=>{
    try{
      const r = await api('/api/password/reset',{method:'POST', body:{
        username:document.getElementById('fp-user').value,
        code:document.getElementById('fp-code').value,
        new_password:document.getElementById('fp-new').value}});
      toast(r.message||'رمز تغییر کرد ✔'); closeModal(); openLogin();
    }catch(e){ toast(e.message,'err'); }
  };
}

function openSignup(){
  openModal(`
    <h2>ثبت‌نام (حساب جدید) <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div class="full"><label>نام صرافی / مجموعه *</label><input id="su-name"></div>
      <div><label>نام کاربری *</label><input id="su-username"></div>
      <div><label>رمز عبور * (حداقل ۴ کاراکتر)</label><input id="su-pass" type="password"></div>
      <div><label>تلفن</label><input id="su-phone"></div>
    </div>
    <div class="btn-row mt"><button class="btn primary" id="su-go">ایجاد حساب</button></div>`);
  document.getElementById('su-go').onclick = async ()=>{
    try{
      const r = await api('/api/signup',{method:'POST', body:{
        name:document.getElementById('su-name').value,
        username:document.getElementById('su-username').value,
        password:document.getElementById('su-pass').value,
        phone:document.getElementById('su-phone').value}});
      state.token = r.token; state.user = r.user; localStorage.setItem('sarrafi_token', r.token);
      toast('حساب شما ساخته شد ✔'); closeModal(); location.reload();
    }catch(e){ toast(e.message,'err'); }
  };
}

async function logout(){
  try{ await api('/api/logout', {method:'POST', body:{}}); }catch(e){}
  state.token = null;
  localStorage.removeItem('sarrafi_token');
  location.reload();
}

/* ---------------- رویدادهای سراسری ---------------- */
window.openParty = openParty;
window.openPartyForm = openPartyForm;
window.openInvoice = openInvoice;
window.openJournal = openJournal;
window.openBanknote = openBanknote;
window.openBanknoteForm = openBanknoteForm;
window.openBanknoteBulk = openBanknoteBulk;
window.bnkUpdateFaces = bnkUpdateFaces;
window.bnfUpdateFaces = bnfUpdateFaces;
window.openTransfer = openTransfer;
window.openAdjust = openAdjust;
window.openLoanModal = openLoanModal;
window.openRepay = openRepay;
window.openPayment = openPayment;
window.openExpForm = openExpForm;
window.openLogin = openLogin;
window.openSignup = openSignup;
window.openForgotPassword = openForgotPassword;
window.navigate = navigate;
window.navigateExp = navigateExp;
window.loadCashboxReport = loadCashboxReport;
window.loadProfitReport = loadProfitReport;
window.loadMonthlyReport = loadMonthlyReport;
window.loadCharts = loadCharts;
window.downloadPdf = downloadPdf;
window.loadMoreTransactions = loadMoreTransactions;
window.loadMoreInvoices = loadMoreInvoices;
window.restoreBackup = restoreBackup;
window.saveRate = saveRate;
window.makeBackup = makeBackup;
window.voidJournal = voidJournal;
window.capturePhoto = capturePhoto;
window.addPhoto = addPhoto;
window.stopCam = stopCam;
window.searchBanknotes = searchBanknotes;
window.filterParties = filterParties;
window.logout = logout;
window.openUserForm = openUserForm;
window.openAccountForm = openAccountForm;
window.viewAccount = viewAccount;
window.impersonateUser = impersonateUser;
window.endImpersonation = endImpersonation;
window.endViewAccount = endViewAccount;
window.applyTheme = applyTheme;
window.toggleTheme = toggleTheme;
window.fetchRatesOnline = fetchRatesOnline;
window.saveRateSettings = saveRateSettings;
window.testNavasanKey = testNavasanKey;
window.clearNavasanKey = clearNavasanKey;
window.saveGoogle = saveGoogle;
window.saveLowStock = saveLowStock;
window.openCurrencyForm = openCurrencyForm;
window.changePassword = changePassword;
window.enable2fa = enable2fa;
window.disable2fa = disable2fa;
window.refreshLiveRate = refreshLiveRate;

document.getElementById('loginBtn').addEventListener('click', openLogin);
document.getElementById('logoutBtn').addEventListener('click', logout);
document.getElementById('menuBtn').addEventListener('click', ()=> document.getElementById('sidebar').classList.toggle('open'));
document.getElementById('themeBtn').addEventListener('click', toggleTheme);
document.getElementById('endViewBtn').addEventListener('click', endViewAccount);

boot();

/* ============================================================
   v0.6 — جستجوی سراسری، اعلان‌ها، تشخیص اسکناس، اشتراک، میان‌برها
   ============================================================ */

// ---------- خروجی اکسل (xlsx) ----------
async function exportXlsx(type){
  try{
    const headers = {'X-Token': state.token||''};
    if(state.accountId) headers['X-Account-Id'] = state.accountId;
    const res = await fetch('/api/export/xlsx?type='+encodeURIComponent(type), {headers});
    if(!res.ok){
      const j = await res.json().catch(()=>({}));
      throw new Error(j.error || 'خطا در ساخت خروجی اکسل (openpyxl لازم است)');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'sarrafi-'+type+'.xlsx';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast('فایل اکسل دانلود شد ✔');
  }catch(e){ toast(e.message,'err'); }
}

// ---------- اعلان‌ها ----------
let notifCache = [];
async function loadNotifications(){
  try{
    const d = await api('/api/dashboard');
    if(d.super) return;
    const items = [];
    (d.reminders||[]).forEach(r=>{
      items.push({
        type: r.overdue ? 'overdue' : 'warn',
        title: 'سررسید قرض — '+r.party,
        body: (r.direction==='receive'?'دریافتی':'داده‌شده')+' '+fmt(r.remaining, r.decimals, r.unit_ratio)+' '+r.code+' — '+(r.overdue ? Math.abs(r.days_left)+' روز گذشته' : (r.days_left===0?'امروز':r.days_left+' روز مانده')),
        link: '#/loans',
      });
    });
    (d.alerts||[]).forEach(a=>{
      items.push({
        type: 'warn',
        title: 'کف موجودی — '+a.name+' ('+a.code+')',
        body: 'موجودی '+fmt(a.balance, a.decimals, a.unit_ratio)+' کمتر از حداقل '+fmt(a.minimum, a.decimals, a.unit_ratio)+' است',
        link: '#/settings',
      });
    });
    (d.credit_alerts||[]).forEach(c=>{
      items.push({
        type: 'overdue',
        title: 'عبور از سقف اعتبار — '+c.party,
        body: 'استفاده '+fmt(c.used_rial,0,1)+' از سقف '+fmt(c.credit_limit,0,1)+' ریال',
        link: '#/parties',
      });
    });
    notifCache = items;
    const badge = document.getElementById('bellBadge');
    if(badge){
      if(items.length){ badge.style.display=''; badge.textContent = faDigits(items.length); }
      else badge.style.display='none';
    }
  }catch(e){}
}
function renderNotifPanel(){
  const panel = document.getElementById('notifPanel');
  if(!panel) return;
  if(!notifCache.length){
    panel.innerHTML = '<div class="np-head"><span>🔔 اعلان‌ها</span></div><div class="np-item"><span class="small muted">اعلانی نیست — همه‌چیز مرتب است ✔</span></div>';
  } else {
    panel.innerHTML = '<div class="np-head"><span>🔔 اعلان‌ها</span><span class="small muted">'+faDigits(notifCache.length)+' مورد</span></div>' +
      notifCache.map(n=>'<div class="notif-item '+n.type+'" onclick="location.hash=\''+(n.link||'#/').replace('#/','')+'\'; document.getElementById(\'notifPanel\').style.display=\'none\';">'+
        '<div class="np-title">'+esc(n.title)+'</div><div class="np-body">'+esc(n.body)+'</div></div>').join('');
  }
  panel.style.display = 'block';
}
function toggleNotifPanel(){
  const panel = document.getElementById('notifPanel');
  if(!panel) return;
  if(panel.style.display==='block'){ panel.style.display='none'; return; }
  renderNotifPanel();
}

// ---------- جستجوی سراسری ----------
let searchTimer = null;
const SEARCH_TYPE_FA = {party:'مشتری', invoice:'فاکتور', journal:'سند', banknote:'اسکناس', loan:'قرض'};
async function doGlobalSearch(){
  const input = document.getElementById('globalSearch');
  const box = document.getElementById('searchResults');
  const q = (input.value||'').trim();
  if(!q){ box.style.display='none'; box.innerHTML=''; return; }
  try{
    const r = await api('/api/search?q='+encodeURIComponent(q));
    const items = r.items||[];
    box.innerHTML = items.length
      ? items.map(it=>'<div class="sr-item" onclick="location.hash=\''+(it.link||'#/').replace('#/','')+'\'; document.getElementById(\'searchResults\').style.display=\'none\'; document.getElementById(\'globalSearch\').value=\'\';">'+
          '<div class="sr-title">'+esc(it.title)+'</div><div class="sr-sub">'+esc(it.subtitle)+' — '+(SEARCH_TYPE_FA[it.type]||it.type)+'</div></div>').join('')
      : '<div class="sr-empty">موردی یافت نشد</div>';
    box.style.display='block';
  }catch(e){ box.innerHTML = '<div class="sr-empty">خطا: '+esc(e.message)+'</div>'; box.style.display='block'; }
}

// ---------- مسیریابی هش (deep-link) ----------
function handleHash(){
  const h = (location.hash||'').replace(/^#\/?/, '');
  if(!h) return;
  const parts = h.split('/');
  const seg = parts[0];
  try{
    if(seg==='billing' && parts[1]==='pay' && parts[2]){
      openModal(`
        <h2>پرداخت اشتراک <button class="close" onclick="closeModal()">×</button></h2>
        <div class="kv"><span>کد پیگیری</span><b class="serial" style="direction:ltr">${esc(parts[2])}</b></div>
        <div class="btn-row mt">
          <button class="btn primary" onclick="confirmPlanPay('${esc(parts[2])}')">تأیید پرداخت</button>
          <button class="btn ghost" onclick="closeModal()">انصراف</button>
        </div>`);
    }
    else if(seg==='invoice' && parts[1]) openInvoice(+parts[1]);
    else if(seg==='party' && parts[1]) openParty(+parts[1]);
    else if(seg==='journal' && parts[1]) openJournal(+parts[1]);
    else if(visibleSections().some(s=>s.id===seg)) navigate(seg);
  }catch(e){ toast(e.message,'err'); }
}
window.addEventListener('hashchange', handleHash);

// ---------- میان‌برهای صفحه‌کلید ----------
function initShortcuts(){
  document.addEventListener('keydown', e=>{
    const t = e.target;
    const typing = t && (t.tagName==='INPUT' || t.tagName==='TEXTAREA' || t.tagName==='SELECT' || t.isContentEditable);
    // Ctrl+K / «/» → فوکوس جستجوی سراسری
    if((e.ctrlKey && (e.key==='k' || e.key==='K')) || (e.key==='/' && !typing)){
      e.preventDefault();
      const g = document.getElementById('globalSearch');
      if(g) g.focus();
      return;
    }
    // Shift+? → راهنمای میانبرها
    if(e.key==='?' && e.shiftKey){
      e.preventDefault();
      openModal(`
        <h2>⌨ میان‌برهای صفحه‌کلید <button class="close" onclick="closeModal()">×</button></h2>
        <div class="table-wrap"><table>
          <thead><tr><th>کلید</th><th>عمل</th></tr></thead><tbody>
          <tr><td><kbd>F2</kbd></td><td>فروش ارز</td></tr>
          <tr><td><kbd>F3</kbd></td><td>خرید ارز</td></tr>
          <tr><td><kbd>F4</kbd></td><td>فاکتورها</td></tr>
          <tr><td><kbd>F5</kbd></td><td>داشبورد</td></tr>
          <tr><td><kbd>Ctrl</kbd>+<kbd>K</kbd> یا <kbd>/</kbd></td><td>جستجوی سراسری</td></tr>
          <tr><td><kbd>Shift</kbd>+<kbd>?</kbd></td><td>این راهنما</td></tr>
          <tr><td><kbd>Esc</kbd></td><td>بستن پنجره‌ها</td></tr>
          </tbody></table></div>`);
      return;
    }
    if(e.key==='Escape'){
      const box = document.getElementById('searchResults'); if(box) box.style.display='none';
      const panel = document.getElementById('notifPanel'); if(panel) panel.style.display='none';
      if(guide && guide.active) guideStop();
      return;
    }
    if(typing || e.ctrlKey || e.metaKey) return;
    // F-کلیدها
    const fmap = {F2:'sell', F3:'buy', F4:'invoices', F5:'dashboard'};
    if(fmap[e.key]){ e.preventDefault(); navigate(fmap[e.key]); return; }
    if(e.altKey){
      const map = {b:'buy', s:'sell', d:'dashboard', p:'parties', i:'invoices', n:'banknotes', l:'loans', r:'reports', t:'transactions', c:'charts', e:'expenses'};
      const sec = map[e.key.toLowerCase()];
      if(sec){ e.preventDefault(); navigate(sec); }
    }
  });
}
function initTopbarExtras(){
  const gs = document.getElementById('globalSearch');
  if(gs){
    gs.addEventListener('input', ()=>{ clearTimeout(searchTimer); searchTimer = setTimeout(doGlobalSearch, 250); });
    gs.addEventListener('focus', ()=>{ if((gs.value||'').trim()) doGlobalSearch(); });
  }
  const nb = document.getElementById('notifBtn');
  if(nb) nb.addEventListener('click', toggleNotifPanel);
  const hb = document.getElementById('helpBtn');
  if(hb) hb.addEventListener('click', openHelp);
  document.addEventListener('click', e=>{
    const box = document.getElementById('searchResults');
    if(box && !e.target.closest('#globalSearchWrap')) box.style.display='none';
    const panel = document.getElementById('notifPanel');
    if(panel && !e.target.closest('#notifBtn') && !e.target.closest('#notifPanel')) panel.style.display='none';
  });
  loadNotifications();
  // به‌روزرسانی دوره‌ای اعلان‌ها (هر ۵ دقیقه)
  setInterval(loadNotifications, 5 * 60 * 1000);
}

/* ============================================================
   راهنمای تعاملی (Interactive Onboarding)
   ============================================================ */
function lsGet(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } }
function lsSet(k,v){ try{ localStorage.setItem(k,v); }catch(e){} }

const GUIDES = {
  sell: {
    title: 'آموزش فروش ارز', icon: '💱',
    desc: 'قدم‌به‌قدم یاد می‌گیرید چطور یک فروش ارز را ثبت کنید.',
    steps: [
      { t: 'برای شروع، روی گزینه‌ی «فروش ارز» در منو کلیک کنید.', sel: '#nav a[data-sec="sell"]', action: 'click', nav: 'sell' },
      { t: 'خریدار (طرف حساب) را از این لیست انتخاب کنید. اگر طرف حساب جدید است، دکمه‌ی «＋ جدید» را بزنید و ثبتش کنید.', sel: '#tr-party' },
      { t: 'نوع ارزی که می‌فروشید را انتخاب کنید (مثلاً دلار).', sel: '#tr-currency' },
      { t: 'مقدار ارز را وارد کنید (مثلاً ۱۰۰).', sel: '#tr-amount' },
      { t: 'نرخ فروش را وارد کنید. برای گرفتن نرخ امروز می‌توانید روی «↻ نرخ لحظه‌ای» کلیک کنید.', sel: '#tr-rate' },
      { t: 'صندوقی که ارز از آن خارج می‌شود را انتخاب کنید.', sel: '#tr-cashbox' },
      { t: 'روش تسویه (نقدی، کارت به کارت، حواله یا نسیه) را مشخص کنید.', sel: '#tr-method' },
      { t: 'در پایان دکمه‌ی «ثبت فروش» را بزنید. بعد از ثبت، اگر اسکناس فروخته‌اید، سیستم پیشنهاد می‌دهد اسکناس را برای همین مشتری ثبت کنید. 🎉', sel: '#tr-submit', last: true },
    ],
  },
  buy: {
    title: 'آموزش خرید ارز', icon: '💱',
    desc: 'قدم‌به‌قدم یاد می‌گیرید چطور یک خرید ارز را ثبت کنید.',
    steps: [
      { t: 'روی گزینه‌ی «خرید ارز» در منو کلیک کنید.', sel: '#nav a[data-sec="buy"]', action: 'click', nav: 'buy' },
      { t: 'فروشنده (طرف حساب) را انتخاب کنید.', sel: '#tr-party' },
      { t: 'نوع ارز را انتخاب کنید.', sel: '#tr-currency' },
      { t: 'مقدار ارزی که می‌خرید را وارد کنید.', sel: '#tr-amount' },
      { t: 'نرخ خرید را وارد کنید (یا نرخ لحظه‌ای بگیرید).', sel: '#tr-rate' },
      { t: 'صندوقی که ارز وارد آن می‌شود را انتخاب کنید.', sel: '#tr-cashbox' },
      { t: 'روش تسویه را مشخص کنید.', sel: '#tr-method' },
      { t: 'دکمه‌ی «ثبت خرید» را بزنید. تمام شد! 🎉', sel: '#tr-submit', last: true },
    ],
  },
  party: {
    title: 'آموزش ثبت مشتری / طرف حساب', icon: '👥',
    desc: 'یاد بگیرید چطور مشتری یا شرکت جدید ثبت کنید.',
    steps: [
      { t: 'به بخش «مشتریان و شرکت‌ها» بروید.', sel: '#nav a[data-sec="parties"]', action: 'click', nav: 'parties' },
      { t: 'روی دکمه‌ی «+ طرف حساب جدید» کلیک کنید.', sel: '#party-new-btn', action: 'click' },
      { t: 'نام کامل را وارد کنید و نوع (مشتری/شرکت/...) را انتخاب کنید.', sel: '#pf-name' },
      { t: 'موبایل و کد ملی را پر کنید (اختیاری اما برای پیگیری مفید است).', sel: '#pf-mobile' },
      { t: 'در پایان دکمه‌ی «ذخیره» را بزنید. مشتری ثبت شد! ✅', sel: '#pf-save', last: true },
    ],
  },
  cashbox: {
    title: 'آموزش ساخت صندوق و زیرشاخه', icon: '🏦',
    desc: 'یاد بگیرید صندوق نقدی/بانکی بسازید و برای هر ارز زیرشاخه تعریف کنید.',
    steps: [
      { t: 'به بخش «صندوق‌ها» بروید.', sel: '#nav a[data-sec="cashboxes"]', action: 'click', nav: 'cashboxes' },
      { t: 'برای ساخت صندوق اصلی روی «+ صندوق جدید» کلیک کنید؛ برای ساخت زیرشاخه‌ی ارزی، روی «＋ زیرشاخه» روی همان صندوق بزنید.', sel: '#cashbox-new-btn' },
      { t: 'نام صندوق را بنویسید (مثلاً «صندوق دلار») و نوع را انتخاب کنید.', sel: '#cb-name' },
      { t: 'اگر زیرشاخه می‌سازید: «صندوق والد» از قبل روی صندوق مادر تنظیم شده؛ فقط «ارز اختصاصی» را انتخاب کنید تا فقط همان ارز نمایش داده شود.', sel: '#cb-parent' },
      { t: 'دکمه‌ی «ذخیره» را بزنید. ✅', sel: '#cb-save', last: true },
    ],
  },
  banknote: {
    title: 'آموزش ثبت اسکناس', icon: '💵',
    desc: 'یاد بگیرید اسکناس را با سریال ثبت و رهگیری کنید.',
    steps: [
      { t: 'به بخش «اسکناس‌ها» بروید.', sel: '#nav a[data-sec="banknotes"]', action: 'click', nav: 'banknotes' },
      { t: 'برای ثبت یک اسکناس روی «+ ثبت اسکناس» کلیک کنید؛ برای چند اسکناس از یک عکس، «📷 تشخیص از عکس» را بزنید.', sel: '#bn-new-btn' },
      { t: 'ارز و ارزش اسکناس را انتخاب کنید و شماره سریال را وارد کنید.', sel: '#bnf-serial' },
      { t: 'دکمه‌ی «ثبت» را بزنید. اسکناس با تاریخچه‌ی مالکیت ثبت می‌شود. ✅', sel: '#bnf-save', last: true },
    ],
  },
};

let guide = { active: false, key: null, idx: 0 };

function ensureGuideDom(){
  if(document.getElementById('guideTip')) return;
  const tip = document.createElement('div');
  tip.id = 'guideTip';
  tip.className = 'guide-tip';
  tip.innerHTML = `
    <div class="guide-head"><b id="guideTitle"></b><span class="guide-count" id="guideCount"></span></div>
    <div class="guide-text" id="guideText"></div>
    <div class="guide-nav">
      <button class="btn xs" id="guidePrev">→ قبلی</button>
      <button class="btn xs primary" id="guideNext">بعدی</button>
      <button class="btn xs ghost" id="guideSkip">رد کردن</button>
    </div>`;
  document.body.appendChild(tip);
  document.getElementById('guidePrev').addEventListener('click', guidePrev);
  document.getElementById('guideNext').addEventListener('click', guideNext);
  document.getElementById('guideSkip').addEventListener('click', guideStop);
}

function startGuide(key){
  const g = GUIDES[key];
  if(!g) return;
  ensureGuideDom();
  guide = { active: true, key: key, idx: 0 };
  document.getElementById('guideTitle').textContent = g.icon + ' ' + g.title;
  document.getElementById('guideTip').style.display = 'block';
  showGuideStep();
}

function guideStep(){ return GUIDES[guide.key].steps[guide.idx]; }

function showGuideStep(){
  const g = GUIDES[guide.key];
  const s = guideStep();
  document.getElementById('guideCount').textContent = (guide.idx + 1) + ' از ' + g.steps.length;
  document.getElementById('guideText').textContent = s.t;
  document.getElementById('guidePrev').style.display = guide.idx > 0 ? '' : 'none';
  document.getElementById('guideNext').textContent = s.last ? 'پایان 🎉' : 'بعدی';
  clearGuideHighlight();
  tryGuideHighlight(0);
}

function tryGuideHighlight(attempt){
  const s = guideStep();
  const el = s.sel ? document.querySelector(s.sel) : null;
  if(el){
    el.classList.add('guide-target');
    try{ el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }catch(e){}
    if(s.action === 'click') el.addEventListener('click', guideAutoNext, { once: true });
    positionGuideTip(el);
    return;
  }
  positionGuideTip(null);
  if(attempt < 30){
    setTimeout(()=>{ if(guide.active && guideStep().sel === s.sel) tryGuideHighlight(attempt + 1); }, 100);
  }
}

function positionGuideTip(el){
  const tip = document.getElementById('guideTip');
  const tw = Math.min(330, window.innerWidth - 16);
  tip.style.width = tw + 'px';
  if(el){
    const r = el.getBoundingClientRect();
    let left = r.left + r.width/2 - tw/2;
    left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
    let top = r.bottom + 12;
    if(top + 120 > window.innerHeight){ top = Math.max(8, r.top - 130); }
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  } else {
    tip.style.left = ((window.innerWidth - tw) / 2) + 'px';
    tip.style.top = '20vh';
  }
}

function guideAutoNext(){
  const s = guideStep();
  if(s.nav){
    const t0 = Date.now();
    const iv = setInterval(()=>{
      if(state.section === s.nav || Date.now() - t0 > 4000){
        clearInterval(iv);
        if(guide.active) advanceGuide();
      }
    }, 80);
  } else {
    setTimeout(()=>{ if(guide.active) advanceGuide(); }, 400);
  }
}

function guideNext(){
  const s = guideStep();
  if(s.nav && state.section !== s.nav){
    clearGuideHighlight();
    navigate(s.nav);
    setTimeout(()=>{ if(guide.active) advanceGuide(); }, 500);
    return;
  }
  advanceGuide();
}

function advanceGuide(){
  const g = GUIDES[guide.key];
  if(guide.idx >= g.steps.length - 1){ guideStop(); return; }
  guide.idx++;
  showGuideStep();
}

function guidePrev(){ if(guide.idx > 0){ guide.idx--; showGuideStep(); } }

function guideStop(){
  guide.active = false;
  clearGuideHighlight();
  const tip = document.getElementById('guideTip');
  if(tip) tip.style.display = 'none';
  if(guide.key) lsSet('sarrafi_guide_seen_' + guide.key, '1');
}

function clearGuideHighlight(){
  document.querySelectorAll('.guide-target').forEach(e => e.classList.remove('guide-target'));
}

function openHelp(){
  const cards = Object.entries(GUIDES).map(([k,g])=>`
    <div class="guide-card mb">
      <div><b>${g.icon} ${esc(g.title)}</b></div>
      <div class="small muted">${esc(g.desc)}</div>
      <div class="guide-btns"><button class="btn sm primary" onclick="closeModal();startGuide('${k}')">▶ شروع آموزش</button></div>
    </div>`).join('');
  openModal(`
    <h2>🎓 راهنمای تعاملی <button class="close" onclick="closeModal()">×</button></h2>
    <p class="small muted mb">با این آموزش‌های کوتاه، قدم‌به‌قدم و روی خودِ صفحه کار با سیستم را یاد می‌گیرید؛ روی هر بخش که گفتیم کلیک کنید تا جلو برود.</p>
    ${cards}
    <div class="small muted mt">💡 میان‌برها: <kbd>F2</kbd> فروش، <kbd>F3</kbd> خرید، <kbd>F4</kbd> فاکتورها، <kbd>F5</kbd> داشبورد، <kbd>Shift</kbd>+<kbd>?</kbd> لیست کامل.</div>`);
}

function openWelcome(){
  if(guide.active) return;
  openModal(`
    <h2>خوش آمدید 👋 <button class="close" onclick="closeModal()">×</button></h2>
    <p class="mb">برای شروع کار با صرافی، با یک آموزش تعاملیِ کوتاه، فروش ارز را قدم‌به‌قدم یاد بگیرید. راهنما مستقیم روی صفحه به شما می‌گوید کجا کلیک کنید.</p>
    <div class="btn-row">
      <button class="btn primary" onclick="closeModal();startGuide('sell')">💱 آموزش فروش ارز</button>
      <button class="btn" onclick="closeModal();openHelp()">🎓 همه‌ی آموزش‌ها</button>
    </div>
    <div class="small muted mt">هر وقت خواستید از دکمه‌ی «؟ راهنما» بالای صفحه به آموزش‌ها برگردید.</div>`);
}

// ---------- صورتحساب اشتراک (SaaS) ----------
async function checkoutPlan(code){
  try{
    const r = await api('/api/billing/checkout', {method:'POST', body:{plan_code: code}});
    openModal(`
      <h2>پرداخت اشتراک ${esc(r.plan.name)} <button class="close" onclick="closeModal()">×</button></h2>
      <div class="alert ok">مبلغ قابل پرداخت: <b>${fmt(r.plan.price_rial,0,1)} ریال</b></div>
      <div class="kv"><span>کد پیگیری</span><b class="serial" style="direction:ltr">${esc(r.ref_code)}</b></div>
      <p class="small muted mt">این یک درگاه شبیه‌سازی‌شده است. در نسخه‌ی تولید به درگاه پرداخت واقعی متصل می‌شود.</p>
      <div class="btn-row mt">
        <button class="btn primary" onclick="confirmPlanPay('${esc(r.ref_code)}')">شبیه‌سازی پرداخت موفق</button>
        <button class="btn ghost" onclick="closeModal()">انصراف</button>
      </div>`);
  }catch(e){ toast(e.message,'err'); }
}
async function confirmPlanPay(ref){
  try{
    const r = await api('/api/billing/confirm', {method:'POST', body:{ref_code: ref}});
    toast('پرداخت موفق — پلن شما فعال شد: '+r.plan+' ✔');
    closeModal();
    location.reload();
  }catch(e){ toast(e.message,'err'); }
}

// ---------- پیکربندی SMTP ----------
async function saveSmtp(){
  try{
    await api('/api/smtp/save', {method:'POST', body:{
      smtp_host: document.getElementById('smtp-host').value,
      smtp_port: document.getElementById('smtp-port').value,
      smtp_user: document.getElementById('smtp-user').value,
      smtp_pass: document.getElementById('smtp-pass').value,
      smtp_from: document.getElementById('smtp-from').value,
      smtp_tls: document.getElementById('smtp-tls').value,
    }});
    toast('تنظیمات ایمیل ذخیره شد ✔');
  }catch(e){ toast(e.message,'err'); }
}

// ---------- عبارت عبور بکاپ ----------
async function saveBackupPassphrase(){
  try{
    const pp = document.getElementById('bk-passphrase').value;
    const r = await api('/api/backup/passphrase', {method:'POST', body:{passphrase: pp}});
    toast(r.encrypted ? 'بکاپ‌ها از این پس رمزنگاری می‌شوند ✔' : 'رمزنگاری بکاپ غیرفعال شد');
    document.getElementById('bk-passphrase').value = '';
  }catch(e){ toast(e.message,'err'); }
}

// ---------- تشخیص تصویری اسکناس (چند اسکناس از یک عکس) ----------
const det = { items: [], selected: -1, img: null, nw: 0, nh: 0, opts: {}, countOnly: 0 };

function confChip(c){
  if(c==null || c===undefined) return '<span class="conf-chip conf-low">بدون داده</span>';
  if(c>=0.8) return '<span class="conf-chip conf-high">✔ '+faDigits((c*100).toFixed(0))+'٪</span>';
  if(c>=0.5) return '<span class="conf-chip conf-mid">◐ '+faDigits((c*100).toFixed(0))+'٪</span>';
  return '<span class="conf-chip conf-low">✘ '+faDigits((c*100).toFixed(0))+'٪</span>';
}

function detOpen(opts){
  opts = opts || {};
  const direction = opts.status === 'sold' ? 'فروخته‌شده به' : 'خریداری‌شده از';
  openModal(`
    <h2>💵 ${esc(opts.title||'ثبت اسکناس')} <button class="close" onclick="closeModal()">×</button></h2>
    <div class="alert ok">طرف حساب: <b>${esc(opts.party_name||'—')}</b> — این اسکناس‌ها به‌عنوان «${esc(direction)} ${esc(opts.party_name||'')}» ثبت و به همین طرف حساب پیوند می‌خورند.</div>
    <p class="small muted mt">روش ثبت را انتخاب کنید:</p>
    <div class="btn-row mt">
      <button class="btn primary" id="det-btn-photo">📷 از عکس (تشخیص خودکار)</button>
      <button class="btn" id="det-btn-pick">🗂 انتخاب از ثبت‌شده‌ها</button>
      <button class="btn" id="det-btn-bulk">🗂 گروهی دستی</button>
      <button class="btn" id="det-btn-single">💵 تکی</button>
      <button class="btn ghost" id="det-btn-skip">فعلاً نه</button>
    </div>`);
  const base = {
    currency_id: opts.currency_id, invoice_id: opts.invoice_id, journal_id: opts.journal_id,
    party_id: opts.party_id, party_name: opts.party_name,
    status: opts.status, movement_type: opts.movement_type,
  };
  document.getElementById('det-btn-photo').onclick = ()=>{
    closeModal();
    openDetectBanknotes({...base, onDone: opts.onDone});
  };
  document.getElementById('det-btn-pick').onclick = ()=>{
    closeModal();
    openBanknotePicker({...base, cashbox_id: opts.cashbox_id, onDone: opts.onDone});
  };
  document.getElementById('det-btn-bulk').onclick = ()=>{
    closeModal();
    openBanknoteBulk({...base, onDone: opts.onDone});
  };
  document.getElementById('det-btn-single').onclick = ()=>{
    closeModal();
    openBanknoteForm({...base, onDone: opts.onDone});
  };
  document.getElementById('det-btn-skip').onclick = ()=>{
    closeModal();
    if(opts.onDone) opts.onDone();
  };
}

/* ---------------- انتخاب از اسکناس‌های ثبت‌شده (الصاق به فاکتور) ---------------- */
const bnPicker = { sel: new Set(), opts: {}, items: [] };
function openBanknotePicker(opts){
  opts = opts || {};
  bnPicker.opts = opts;
  bnPicker.sel = new Set();
  bnPicker.items = [];
  const fx = state.currencies.filter(c=>c.code!=='IRR' && c.is_active);
  openModal(`
    <h2>🗂 انتخاب از اسکناس‌های ثبت‌شده <button class="close" onclick="closeModal()">×</button></h2>
    <div class="alert ok">فقط اسکناس‌های «در دسترس» (موجود در صندوق و الصاق‌نشده) نمایش داده می‌شوند؛ اسکناس‌های استفاده‌شده در این فهرست نیستند.</div>
    <div class="flex mb" style="gap:8px;flex-wrap:wrap">
      <select id="pk-currency" onchange="bnPickerLoad()">
        <option value="">همه ارزها</option>
        ${fx.map(c=>`<option value="${c.id}" ${opts.currency_id==c.id?'selected':''}>${esc(c.name)} (${c.code})</option>`).join('')}
      </select>
      <input id="pk-q" placeholder="جستجوی سریال…" oninput="bnPickerLoad()" style="flex:1;min-width:140px">
      <button class="btn xs" onclick="bnPickerLoad()" title="به‌روزرسانی">↻</button>
    </div>
    <div class="table-wrap" style="max-height:340px;overflow:auto">
      <table><thead><tr><th></th><th>سریال</th><th>ارزش</th><th>صندوق</th><th>عکس</th></tr></thead>
      <tbody id="pk-body"><tr><td colspan="5" class="empty">در حال بارگذاری…</td></tr></tbody></table>
    </div>
    <div class="btn-row mt">
      <button class="btn primary" onclick="bnPickerAttach()">الصاق انتخاب‌شده‌ها</button>
      <button class="btn ghost" onclick="closeModal()">انصراف</button>
    </div>`);
  bnPickerLoad();
}

async function bnPickerLoad(){
  const body = document.getElementById('pk-body');
  if(!body) return;
  const cur = document.getElementById('pk-currency').value;
  const q = (document.getElementById('pk-q')?.value || '').trim();
  const p = new URLSearchParams();
  if(cur) p.set('currency_id', cur);
  if(q) p.set('q', q);
  p.set('limit', '200');
  try{
    const d = await api('/api/banknotes/available?' + p.toString());
    bnPicker.items = d.items || [];
    body.innerHTML = bnPicker.items.length ? bnPicker.items.map(b=>`
      <tr class="${bnPicker.sel.has(b.id)?'pick-sel':''}">
        <td><input type="checkbox" ${bnPicker.sel.has(b.id)?'checked':''} onchange="bnPickerToggle(${b.id}, this.checked)"></td>
        <td class="serial">${esc(b.serial)}</td>
        <td class="num">${fmt(b.denomination, b.decimals, b.unit_ratio)} ${esc(b.code)}</td>
        <td>${esc(b.cashbox_name||'—')}</td>
        <td>${b.img_count>0?`<span class="badge gray">${faDigits(b.img_count)} عکس</span>`:'—'}</td>
      </tr>`).join('') : '<tr><td colspan="5" class="empty">اسکناس در دسترسی نیست — اول اسکناس ثبت کنید.</td></tr>';
  }catch(e){
    body.innerHTML = `<tr><td colspan="5" class="empty">${esc(e.message)}</td></tr>`;
  }
}
function bnPickerToggle(id, on){ if(on) bnPicker.sel.add(id); else bnPicker.sel.delete(id); }
async function bnPickerAttach(){
  if(!bnPicker.sel.size) return toast('هیچ اسکناسی انتخاب نشده','warn');
  const o = bnPicker.opts;
  try{
    const r = await api('/api/banknote/attach', {method:'POST', body:{
      ids: [...bnPicker.sel],
      invoice_id: o.invoice_id || null,
      journal_id: o.journal_id || null,
      party_id: o.party_id || null,
      movement_type: o.movement_type || (o.status === 'sold' ? 'sale' : 'purchase'),
      cashbox_id: o.cashbox_id || null,
    }});
    let msg = `${faDigits(r.attached.length)} اسکناس الصاق شد ✔`;
    if(r.rejected.length) msg += ` — ${faDigits(r.rejected.length)} رد شد`;
    if(r.skipped.length) msg += ` — ${faDigits(r.skipped.length)} تکراری نادیده گرفته شد`;
    if(r.warnings.length) msg += ' — ⚠ اختلاف صندوق با فاکتور';
    toast(msg, r.attached.length ? 'ok' : 'warn');
    closeModal();
    if(o.onDone) o.onDone();
    else if(state.section === 'banknotes') navigate('banknotes');
  }catch(e){ toast(e.message,'err'); }
}

function openDetectBanknotes(opts){
  det.opts = opts || {};
  det.items = []; det.selected = -1; det.img = null; det.countOnly = 0; det.drawMode = false;
  const fx = state.currencies.filter(c=>c.code!=='IRR' && c.is_active);
  openModal(`
    <h2>📷 تشخیص اسکناس از عکس <button class="close" onclick="closeModal()">×</button></h2>
    <div class="form-grid">
      <div><label>ارز</label><select id="det-currency" onchange="detFacesUpdate()">
        ${fx.map(c=>`<option value="${c.id}" ${det.opts.currency_id==c.id?'selected':''}>${esc(c.name)} (${c.code})</option>`).join('')}</select></div>
      <div><label>ارزش اسکناس</label><select id="det-face"></select></div>
      <div><label>وضعیت ثبت</label><select id="det-status">
        <option value="in_vault" ${det.opts.status==='in_vault'?'selected':''}>موجود در صندوق</option>
        <option value="sold" ${det.opts.status==='sold'?'selected':''}>فروخته شده</option>
      </select></div>
      <div><label>صندوق</label><select id="det-cashbox">${state.cashboxes.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
      <div class="full">
        <label>عکس (چند اسکناس در یک قاب)</label>
        <input type="file" id="det-file" accept="image/*" onchange="detPickFile(this)">
        <div class="det-stage mt" id="det-stage">
          <div class="small muted" style="padding:30px;text-align:center">عکسی انتخاب نشده — روی دکمه‌ی انتخاب فایل بزنید</div>
        </div>
      </div>
      <div class="full" id="det-count-row" style="display:none">
        <label>ثبت شمارشی (بدون سریال): تعداد</label>
        <div class="flex"><input type="text" inputmode="numeric" id="det-count" class="input-num" placeholder="مثلاً ۵" style="max-width:160px">
        <button class="btn sm" onclick="detAddCountOnly()">افزودن شمارشی</button></div>
      </div>
      <div class="full mt" id="det-tools" style="display:none">
        <button class="btn sm" id="det-btn-draw" onclick="detToggleDraw()">✏️ کادر دستی (افزودن اسکناس)</button>
        <div class="small muted mt">تشخیص خودکار روی عکس کادر می‌کشد و می‌توانید گوشه‌ها را بکشید یا هر مورد را حذف کنید؛ اگر بخشی از عکس غیر از اسکناس بود (یا تشخیص جا ماند)، با «کادر دستی» روی عکس بکشید.</div>
      </div>
    </div>
    <div class="mt" id="det-items"></div>
    <div class="btn-row mt no-print">
      <button class="btn primary" onclick="detRegister()">ثبت اسکناس‌ها</button>
      <button class="btn ghost" onclick="closeModal()">بستن</button>
    </div>`, true);
  detFacesUpdate();
  bindNumField('det-count', {decimals:0});
}

function detFacesUpdate(){
  const cid = +document.getElementById('det-currency').value;
  const c = currencyById(cid);
  const faces = (c && FACE_VALUES[c.code]) || [1,2,5,10,20,50,100];
  document.getElementById('det-face').innerHTML = faces.map(f=>`<option value="${f}">${faDigits(f)}</option>`).join('');
}

async function detPickFile(input){
  const f = input.files[0]; if(!f) return;
  const r = new FileReader();
  r.onload = async ev => {
    det.img = ev.target.result;
    const im = new Image();
    im.onload = async ()=>{ det.nw = im.naturalWidth; det.nh = im.naturalHeight; await detRun(); };
    im.src = det.img;
  };
  r.readAsDataURL(f);
}

async function detRun(){
  const stage = document.getElementById('det-stage');
  stage.innerHTML = '<div class="loader">در حال تشخیص اسکناس‌ها…</div>';
  const showStage = (msg, type) => {
    stage.innerHTML = `<img src="${det.img}" id="det-img"><svg id="det-svg"></svg>`;
    detDrawRects();
    detRenderItems();
    detAttachDraw();
    document.getElementById('det-count-row').style.display = '';
    document.getElementById('det-tools').style.display = '';
    if(msg) toast(msg, type || 'warn');
  };
  try{
    const res = await api('/api/detect', {method:'POST', body:{
      image: det.img, currency_id: +document.getElementById('det-currency').value}});
    if(res.available === false){
      det.items = [];
      showStage((res.message||'تشخیص تصویری در دسترس نیست') + ' — می‌توانید «کادر دستی» بکشید یا ثبت شمارشی کنید');
      return;
    }
    det.items = (res.items||[]).map(it=>({...it, serial: it.serial||'', note: ''}));
    det.selected = -1;
    stage.innerHTML = `<img src="${det.img}" id="det-img"><svg id="det-svg"></svg>`;
    detDrawRects();
    detRenderItems();
    detAttachDraw();
    document.getElementById('det-count-row').style.display = '';
    document.getElementById('det-tools').style.display = '';
    if(det.items.length) toast(faDigits(det.items.length)+' اسکناس تشخیص داده شد — سریال‌ها را بررسی/اصلاح و ثبت کنید');
    else toast('اسکناسی تشخیص داده نشد — می‌توانید «کادر دستی» بکشید یا ثبت شمارشی کنید','warn');
  }catch(e){
    det.items = [];
    showStage('تشخیص خودکار ناموفق: '+e.message+' — از «کادر دستی» استفاده کنید','err');
  }
}

function detSvgPoint(e){
  const svg = document.getElementById('det-svg');
  const r = svg.getBoundingClientRect();
  return { x: (e.clientX - r.left) / r.width * det.nw, y: (e.clientY - r.top) / r.height * det.nh };
}
function detToggleDraw(){
  const svg = document.getElementById('det-svg');
  if(!svg || !det.img) return toast('اول یک عکس انتخاب کنید','warn');
  det.drawMode = !det.drawMode;
  const btn = document.getElementById('det-btn-draw');
  if(det.drawMode){
    svg.style.cursor = 'crosshair';
    if(btn) btn.classList.add('primary');
    toast('روی عکس بکشید تا کادر اسکناس را مشخص کنید','ok');
  } else {
    svg.style.cursor = '';
    if(btn) btn.classList.remove('primary');
  }
}
function detAttachDraw(){
  const svg = document.getElementById('det-svg');
  if(!svg || svg.__drawAttached) return;
  svg.__drawAttached = true;
  let start = null, draft = null;
  svg.addEventListener('pointerdown', e=>{
    if(!det.drawMode || !det.img) return;
    if(e.target && e.target.closest && e.target.closest('circle.corner')) return;
    start = detSvgPoint(e);
    draft = document.createElementNS('http://www.w3.org/2000/svg','rect');
    draft.setAttribute('class','rect sel');
    svg.appendChild(draft);
    e.preventDefault();
  });
  svg.addEventListener('pointermove', e=>{
    if(!det.drawMode || !start || !draft) return;
    const p = detSvgPoint(e);
    const x = Math.min(start.x,p.x), y = Math.min(start.y,p.y);
    const w = Math.abs(p.x-start.x), h = Math.abs(p.y-start.y);
    draft.setAttribute('x',x); draft.setAttribute('y',y);
    draft.setAttribute('width',w); draft.setAttribute('height',h);
  });
  svg.addEventListener('pointerup', e=>{
    if(!det.drawMode || !start) return;
    const p = detSvgPoint(e);
    const x0=Math.min(start.x,p.x), y0=Math.min(start.y,p.y);
    const x1=Math.max(start.x,p.x), y1=Math.max(start.y,p.y);
    if(draft){ try{ svg.removeChild(draft); }catch(_){} }
    draft = null; start = null;
    if((x1-x0) < 8 || (y1-y0) < 8) return;
    det.items.push({serial:'', value:null, quad:[[x0,y0],[x1,y0],[x1,y1],[x0,y1]], note:'', busy:true});
    det.selected = det.items.length - 1;
    det.drawMode = false;
    svg.style.cursor = '';
    const btn = document.getElementById('det-btn-draw');
    if(btn) btn.classList.remove('primary');
    detDrawRects(); detRenderItems();
    detRecrop(det.selected);
  });
}

function detQuad(it){
  if(it.quad && it.quad.length===4) return it.quad;
  return [[it.x,it.y],[it.x+it.w,it.y],[it.x+it.w,it.y+it.h],[it.x,it.y+it.h]];
}
function detQuadToPoints(it){
  return detQuad(it).map(p=>p[0]+','+p[1]).join(' ');
}

function detDrawRects(){
  const svg = document.getElementById('det-svg');
  const img = document.getElementById('det-img');
  if(!svg || !img) return;
  svg.setAttribute('viewBox', '0 0 '+det.nw+' '+det.nh);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.innerHTML = det.items.map((it, i)=>
    `<polygon class="rect ${i===det.selected?'sel':''} ${it.busy?'busy':''}" data-i="${i}" points="${detQuadToPoints(it)}" onclick="detSelect(${i})"></polygon>`
  ).join('');
  if(det.selected>=0){
    const q = detQuad(det.items[det.selected]);
    q.forEach((p,k)=>{
      svg.insertAdjacentHTML('beforeend', `<circle class="corner" cx="${p[0]}" cy="${p[1]}" r="${Math.max(6, det.nw*0.008)}" data-k="${k}" data-i="${det.selected}"></circle>`);
    });
  }
  detEnableCornerDrag();
}

function detEnableCornerDrag(){
  const svg = document.getElementById('det-svg');
  if(!svg) return;
  svg.querySelectorAll('circle.corner').forEach(c=>{
    c.addEventListener('pointerdown', e=>{
      e.stopPropagation();
      const i = +c.dataset.i, k = +c.dataset.k;
      const move = ev=>{
        const rect = svg.getBoundingClientRect();
        const x = (ev.clientX - rect.left) / rect.width * det.nw;
        const y = (ev.clientY - rect.top) / rect.height * det.nh;
        const q = detQuad(det.items[i]);
        q[k] = [Math.max(0,Math.min(det.nw,Math.round(x))), Math.max(0,Math.min(det.nh,Math.round(y)))];
        det.items[i].quad = q;
        detDrawRects();
      };
      const up = ()=>{ window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); detRecrop(i); };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
  });
}

async function detRecrop(i){
  const it = det.items[i];
  const q = detQuad(it);
  const xs = q.map(p=>p[0]), ys = q.map(p=>p[1]);
  const x0 = Math.max(0, Math.floor(Math.min(...xs)));
  const y0 = Math.max(0, Math.floor(Math.min(...ys)));
  const x1 = Math.min(det.nw, Math.ceil(Math.max(...xs)));
  const y1 = Math.min(det.nh, Math.ceil(Math.max(...ys)));
  const w = x1-x0, h = y1-y0;
  if(w<4 || h<4) return;
  try{
    const img = new Image();
    img.onload = async ()=>{
      const cv = document.createElement('canvas');
      cv.width = w; cv.height = h;
      cv.getContext('2d').drawImage(img, x0, y0, w, h, 0, 0, w, h);
      it.crop = cv.toDataURL('image/jpeg', 0.92);
      detRenderItems();
      try{
        const ocr = await api('/api/ocr', {method:'POST', body:{data: it.crop}});
        if(ocr.suggestions && ocr.suggestions.length){
          it.serial = ocr.suggestions[0];
          detRenderItems();
          toast('سریال پیشنهادی جدید: '+ocr.suggestions[0]+' — بررسی و تأیید کنید');
        }
      }catch(_){}
      finally{ it.busy = false; detRenderItems(); detDrawRects(); }
    };
    img.src = det.img;
  }catch(_){}
}

function detRenderItems(){
  const box = document.getElementById('det-items');
  if(!box) return;
  if(!det.items.length){
    box.innerHTML = '<div class="small muted">هنوز اسکناسی تشخیص داده نشده است.</div>';
    return;
  }
  box.innerHTML = det.items.map((it,i)=>`
    <div class="detect-item ${i===det.selected?'sel':''}" onclick="detSelect(${i})">
      <div class="flex" style="align-items:center;gap:10px">
        ${it.crop?`<img class="thumb" src="${it.crop}" alt="برش">`:''}
        <div style="flex:1">
          <div class="flex" style="gap:8px;flex-wrap:wrap;align-items:center">
            <label class="small muted">سریال</label>
            ${it.busy
              ? '<span class="small muted">⏳ در حال تشخیص سریال از برش…</span>'
              : `<input value="${esc(it.serial)}" style="font-family:Consolas,monospace;direction:ltr;flex:1;min-width:150px"
              oninput="detItemChange(${i},'serial',this.value)">`}
            ${confChip(it.serial_confidence)}
            ${it.value?`<span class="conf-chip conf-mid">ارزش: ${faDigits(it.value)}</span>`:''}
            <button class="btn xs warn" onclick="event.stopPropagation();detRemoveItem(${i})">✕</button>
          </div>
          <div class="small muted mt">${esc(it.note||'')} ${det.selected===i?'· گوشه‌های قاب روی تصویر را بکشید تا برش دقیق شود':''}</div>
        </div>
      </div>
    </div>`).join('');
}

function detSelect(i){ det.selected = i; detDrawRects(); detRenderItems(); }
function detItemChange(i, field, val){ if(det.items[i]) det.items[i][field] = val; }
function detRemoveItem(i){
  det.items.splice(i,1);
  if(det.selected===i) det.selected=-1; else if(det.selected>i) det.selected--;
  detDrawRects(); detRenderItems();
}
function detAddCountOnly(){
  const v = Math.round(numVal(document.getElementById('det-count')));
  if(!v || v<=0) return toast('تعداد شمارشی نامعتبر است','err');
  det.countOnly = v;
  toast(faDigits(v)+' اسکناس شمارشی (بدون سریال) ثبت خواهد شد');
  document.getElementById('det-count').value='';
}

async function detRegister(){
  const cid = +document.getElementById('det-currency').value;
  const c = currencyById(cid);
  const face = +document.getElementById('det-face').value;
  const countOnly = det.countOnly || 0;
  const meta = {device: String(navigator.userAgent||'').slice(0,200), captured_at: new Date().toISOString(), source: 'detect-ui'};
  const items = det.items.map(it=>({serial: it.serial, crop: it.crop, serial_confidence: it.serial_confidence, note: it.note, meta}));
  if(!countOnly && !items.length) return toast('هیچ اسکناسی برای ثبت نیست','err');
  if(!countOnly && !items.some(it=>it.serial.trim())) return toast('حداقل یک سریال معتبر وارد کنید (یا از ثبت شمارشی استفاده کنید)','err');
  try{
    const r = await api('/api/detect/register', {method:'POST', body:{
      currency_id: cid, denomination: Math.round(face * c.unit_ratio),
      count_only: countOnly,
      items: countOnly ? [] : items,
      status: document.getElementById('det-status').value,
      cashbox_id: +document.getElementById('det-cashbox').value,
      party_id: det.opts.party_id || null,
      invoice_id: det.opts.invoice_id || null,
      journal_id: det.opts.journal_id || null,
      source_image: det.img,
      note: '',
    }});
    let msg = faDigits(r.inserted||0)+' اسکناس ثبت شد';
    if(countOnly) msg += ' (شمارشی)';
    if(r.duplicates && r.duplicates.length) msg += ' — '+faDigits(r.duplicates.length)+' تکراری نادیده گرفته شد';
    const recon = r.reconciliation;
    let matched = true;
    if(recon){
      matched = recon.matched;
      msg += ' — تطبیق با فاکتور: '+fmt(recon.registered_minor, c.decimals, c.unit_ratio)+' از '+fmt(recon.expected_minor, c.decimals, c.unit_ratio)+' '+c.code+
        (recon.matched ? ' (تطبیق کامل ✔)' : ' (اختلاف '+fmt(Math.abs(recon.diff_minor), c.decimals, c.unit_ratio)+')');
    }
    toast(msg, matched ? 'ok':'warn');
    closeModal();
    if(det.opts.onDone) det.opts.onDone();
    else if(state.section==='banknotes') navigate('banknotes');
    else refreshInstant();
  }catch(e){ toast(e.message,'err'); }
}

/* ---------- خروجی توابع v0.6 به سطح window ---------- */
window.exportXlsx = exportXlsx;
window.checkoutPlan = checkoutPlan;
window.confirmPlanPay = confirmPlanPay;
window.saveSmtp = saveSmtp;
window.saveBackupPassphrase = saveBackupPassphrase;
window.openDetectBanknotes = openDetectBanknotes;
window.detPickFile = detPickFile;
window.detFacesUpdate = detFacesUpdate;
window.detDrawRects = detDrawRects;
window.detSelect = detSelect;
window.detItemChange = detItemChange;
window.detRemoveItem = detRemoveItem;
window.detAddCountOnly = detAddCountOnly;
window.detRegister = detRegister;
window.openBanknotePicker = openBanknotePicker;
window.bnPickerLoad = bnPickerLoad;
window.bnPickerToggle = bnPickerToggle;
window.bnPickerAttach = bnPickerAttach;
window.detachBanknoteFromInvoice = detachBanknoteFromInvoice;
window.loadNotifications = loadNotifications;
window.toggleNotifPanel = toggleNotifPanel;

/* ============================================================
   v0.7 — مدیریت ماژول‌ها (امکانات) و سطح دسترسی نقش‌ها
   ============================================================ */
let modState = null;
let permsState = null;

function switchRow(id, m, on){
  return `<div class="mod-row flex between">
    <div style="flex:1"><b>${m.icon||''} ${esc(m.name)}</b>
      <div class="small muted">${esc(m.desc)}</div></div>
    <label class="switch"><input type="checkbox" id="${id}" ${on?'checked':''}><span class="slider"></span></label>
  </div>`;
}

async function loadModulesBox(){
  const box = document.getElementById('modules-box');
  if(!box) return;
  try{ modState = await api('/api/modules'); }catch(e){ box.innerHTML = `<div class="alert err">${esc(e.message)}</div>`; return; }
  const d = modState;
  const cat = d.catalog || [];
  box.innerHTML = `
    ${d.is_super?`<div class="form-grid mb"><div><label>حساب مشترک</label>
      <select id="mod-acct" onchange="modLoadAccount()">${(d.accounts||[]).map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('')}</select></div></div>`:''}
    <div class="small muted mb"><b>تنظیم حساب (برای همه‌ی کاربران این حساب)</b></div>
    <div class="mod-list" id="mod-acc-list">${cat.map(m=>switchRow('acc_'+m.key, m, d.account_flags[m.key] ?? m.default)).join('')}</div>
    <div class="btn-row mt"><button class="btn primary" onclick="saveModules()">ذخیره تنظیمات حساب</button></div>
    <hr style="border-color:var(--border);margin:16px 0">
    <div class="form-grid mb"><div><label>تنظیم استثنا برای یک کاربر خاص</label>
      <select id="mod-user" onchange="modLoadUser()">
        <option value="">— انتخاب کاربر —</option>
        ${(d.users||[]).map(u=>`<option value="${u.id}">${esc(u.full_name||u.username)} (${esc(u.username)})</option>`).join('')}
      </select></div></div>
    <div class="mod-list" id="mod-user-list"><div class="small muted">کاربری انتخاب نشده — با انتخاب کاربر، سوییچ‌های استثنای او نمایش داده می‌شود.</div></div>
    <div class="btn-row mt"><button class="btn" id="mod-user-save" style="display:none" onclick="saveUserModules()">ذخیره استثناهای کاربر</button></div>
  `;
  document.getElementById('mod-acct').value = String(d.account_id);
}

async function modLoadAccount(){
  const acct = document.getElementById('mod-acct').value;
  try{
    const d = await api('/api/modules?account_id='+acct);
    modState.account_flags = d.account_flags;
    modState.account_id = d.account_id;
    const cat = d.catalog||[];
    document.getElementById('mod-acc-list').innerHTML = cat.map(m=>switchRow('acc_'+m.key, m, d.account_flags[m.key] ?? m.default)).join('');
  }catch(e){ toast(e.message,'err'); }
}

async function modLoadUser(){
  const uid = document.getElementById('mod-user').value;
  const list = document.getElementById('mod-user-list');
  const btn = document.getElementById('mod-user-save');
  if(!uid){ list.innerHTML = '<div class="small muted">کاربری انتخاب نشده.</div>'; btn.style.display='none'; return; }
  try{
    const d = await api('/api/modules?user_id='+uid);
    const cat = d.catalog||[];
    const eff = d.account_flags;                 // پایه = فلگ حساب
    const ovr = d.user_overrides;                // استثناهای کاربر
    list.innerHTML = cat.map(m=>{
      const val = (m.key in ovr) ? ovr[m.key] : (eff[m.key] ?? m.default);
      return `<div class="mod-row flex between">
        <div style="flex:1"><b>${m.icon||''} ${esc(m.name)}</b>
          <div class="small muted">${esc(m.desc)}</div></div>
        <select id="usr_${m.key}" class="sm">
          <option value="1" ${val?'selected':''}>روشن</option>
          <option value="0" ${!val?'selected':''}>خاموش</option>
        </select>
      </div>`;
    }).join('');
    btn.style.display='';
  }catch(e){ toast(e.message,'err'); }
}

async function saveModules(){
  const cat = (modState && modState.catalog) || [];
  const flags = {};
  cat.forEach(m=>{ const el=document.getElementById('acc_'+m.key); if(el) flags[m.key]=el.checked; });
  try{
    await api('/api/modules/save',{method:'POST', body:{flags, account_id: +(document.getElementById('mod-acct')?.value||0)}});
    toast('تنظیمات امکانات حساب ذخیره شد ✔');
    state.me = await api('/api/me');   // به‌روزرسانی فلگ‌های کاربر جاری
    state.user = state.me.user;
    buildNav();
  }catch(e){ toast(e.message,'err'); }
}

async function saveUserModules(){
  const uid = +document.getElementById('mod-user').value;
  if(!uid) return;
  const cat = (modState && modState.catalog) || [];
  const flags = {};
  cat.forEach(m=>{ const el=document.getElementById('usr_'+m.key); if(el) flags[m.key]= el.value==='1'; });
  try{
    await api('/api/modules/save',{method:'POST', body:{flags, user_id: uid}});
    toast('استثناهای کاربر ذخیره شد ✔');
    state.me = await api('/api/me');
    state.user = state.me.user;
    buildNav();
  }catch(e){ toast(e.message,'err'); }
}

async function loadPermsBox(){
  const box = document.getElementById('perms-box');
  if(!box) return;
  try{ permsState = await api('/api/permissions'); }catch(e){ box.innerHTML = `<div class="alert err">${esc(e.message)}</div>`; return; }
  const d = permsState;
  const roleFa = d.role_fa || {};
  const rows = d.roles.map(role=>{
    const cells = d.perms.map(p=>{
      const on = d.matrix[role] && d.matrix[role][p.key];
      return `<td class="num"><label class="switch"><input type="checkbox" data-role="${role}" data-perm="${p.key}" ${on?'checked':''}><span class="slider"></span></label></td>`;
    }).join('');
    return `<tr><th>${esc(roleFa[role]||role)}</th>${cells}</tr>`;
  }).join('');
  box.innerHTML = `
    <div class="table-wrap"><table>
      <thead><tr><th>نقش</th>${d.perms.map(p=>`<th class="num">${esc(p.name)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <div class="btn-row mt"><button class="btn primary" onclick="savePermissions()">ذخیره سطح دسترسی</button></div>
  `;
}

async function savePermissions(){
  const box = document.getElementById('perms-box');
  const matrix = {};
  box.querySelectorAll('input[data-role]').forEach(el=>{
    matrix[el.dataset.role] = matrix[el.dataset.role] || {};
    matrix[el.dataset.role][el.dataset.perm] = el.checked;
  });
  try{
    await api('/api/permissions/save',{method:'POST', body:{matrix}});
    toast('سطح دسترسی نقش‌ها ذخیره شد ✔');
  }catch(e){ toast(e.message,'err'); }
}

window.openCashboxForm = openCashboxForm;
window.detOpen = detOpen;
window.saveModules = saveModules;
window.saveUserModules = saveUserModules;
window.modLoadAccount = modLoadAccount;
window.modLoadUser = modLoadUser;
window.loadModulesBox = loadModulesBox;
window.loadPermsBox = loadPermsBox;
window.savePermissions = savePermissions;

/* ---------- تنظیم امکانات یک کاربر (از فرم کاربر) ---------- */
async function openUserModules(id){
  try{
    const d = await api('/api/modules?user_id='+id);
    const cat = d.catalog||[];
    const eff = d.account_flags;
    const ovr = d.user_overrides;
    openModal(`
      <h2>⚙ امکانات کاربر <button class="close" onclick="closeModal()">×</button></h2>
      <p class="small muted mb">استثناهای این کاربر؛ خالی‌ها از تنظیمات حساب پیروی می‌کنند.</p>
      <div class="mod-list">
        ${cat.map(m=>{
          const val = (m.key in ovr) ? ovr[m.key] : (eff[m.key] ?? m.default);
          return `<div class="mod-row flex between">
            <div style="flex:1"><b>${m.icon||''} ${esc(m.name)}</b>
              <div class="small muted">${esc(m.desc)}</div></div>
            <select id="um_${m.key}" class="sm">
              <option value="1" ${val?'selected':''}>روشن</option>
              <option value="0" ${!val?'selected':''}>خاموش</option>
            </select>
          </div>`;
        }).join('')}
      </div>
      <div class="btn-row mt"><button class="btn primary" id="um-save">ذخیره</button></div>`);
    document.getElementById('um-save').onclick = async ()=>{
      const flags = {};
      cat.forEach(m=>{ const el=document.getElementById('um_'+m.key); if(el) flags[m.key]= el.value==='1'; });
      try{
        await api('/api/modules/save',{method:'POST', body:{flags, user_id: id}});
        toast('امکانات کاربر ذخیره شد ✔'); closeModal();
      }catch(e){ toast(e.message,'err'); }
    };
  }catch(e){ toast(e.message,'err'); }
}
window.openUserModules = openUserModules;
