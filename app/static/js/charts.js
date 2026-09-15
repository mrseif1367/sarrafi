/* ============================================================
   کتابخانه‌ی نمودار سبک (SVG خالص، بدون وابستگی خارجی)
   — دایره‌ای (pie/donut)، میله‌ای، خطی، مقایسه‌ای
   ============================================================ */
"use strict";

const Charts = (function () {
  const PALETTE = ['#38bdf8', '#818cf8', '#34d399', '#fbbf24', '#f472b6',
                   '#a78bfa', '#fb923c', '#2dd4bf', '#f87171', '#eab308',
                   '#4ade80', '#c084fc', '#60a5fa', '#facc15', '#5eead4'];

  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function num(n){ return Number(n||0).toLocaleString('en-US'); }

  function _svg(w, h, inner, defs){
    defs = defs || '';
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="xMidYMid meet"
      style="font-family:Vazirmatn,sans-serif;direction:ltr">${defs}${inner}</svg>`;
  }

  /* ---------------- دایره‌ای ---------------- */
  function pie(container, data, opts){
    opts = opts || {};
    const W = opts.width || 640, H = opts.height || 300;
    const donut = opts.donut ? 0.62 : 0;
    const cx = donut ? W/2 : W*0.34, cy = H/2;
    const R = Math.min(H/2 - 14, donut ? H*0.36 : W*0.24);
    const total = data.reduce((s,d)=>s+Math.abs(Number(d.value||0)), 0) || 1;
    let a0 = -Math.PI/2, body = '', legend = '';
    data.forEach((d, i) => {
      const v = Math.abs(Number(d.value||0));
      if (v <= 0) return;
      const frac = v/total, a1 = a0 + frac*2*Math.PI;
      const color = d.color || PALETTE[i % PALETTE.length];
      const large = (a1-a0) > Math.PI ? 1 : 0;
      const x0 = cx + R*Math.cos(a0), y0 = cy + R*Math.sin(a0);
      const x1 = cx + R*Math.cos(a1), y1 = cy + R*Math.sin(a1);
      const x2 = cx + R*donut*Math.cos(a1), y2 = cy + R*donut*Math.sin(a1);
      const x3 = cx + R*donut*Math.cos(a0), y3 = cy + R*donut*Math.sin(a0);
      const path = donut
        ? `M ${x0} ${y0} A ${R} ${R} 0 ${large} 1 ${x1} ${y1} L ${x2} ${y2} A ${R*donut} ${R*donut} 0 ${large} 0 ${x3} ${y3} Z`
        : `M ${cx} ${cy} L ${x0} ${y0} A ${R} ${R} 0 ${large} 1 ${x1} ${y1} Z`;
      body += `<path d="${path}" fill="${color}" stroke="#0f172a" stroke-width="1.5" opacity="0.92">
        <title>${esc(d.label)}: ${num(Math.round(v))}</title></path>`;
      const pct = (frac*100).toFixed(1);
      legend += `<div class="ch-leg"><span class="ch-dot" style="background:${color}"></span>
        <span>${esc(d.label)}</span><b>${num(Math.round(v))}</b><i>${pct}%</i></div>`;
      a0 = a1;
    });
    const labelHtml = donut
      ? `<text x="${cx}" y="${cy-6}" text-anchor="middle" fill="#e6edf7" font-size="22" font-weight="700">${num(Math.round(total))}</text>
         <text x="${cx}" y="${cy+16}" text-anchor="middle" fill="#8ea0bd" font-size="12">مجموع (ریال)</text>`
      : '';
    container.innerHTML = `<div class="ch-pie"><div class="ch-pie-svg">${_svg(W,H,body+labelHtml)}</div>
      <div class="ch-legend">${legend || '<div class="muted small">داده‌ای نیست</div>'}</div></div>`;
  }

  /* ---------------- میله‌ای (گروهی/مقایسه‌ای) ---------------- */
  function bar(container, labels, series, opts){
    opts = opts || {};
    const H = opts.height || 300, W = opts.width || 860;
    const padL = 70, padR = 16, padT = 20, padB = 46;
    const maxV = Math.max(1, ...series.flatMap(s=>s.values.map(v=>Math.abs(Number(v||0)))));
    const n = labels.length, groupW = (W-padL-padR)/Math.max(1,n);
    const barW = Math.min(46, groupW*0.7/series.length);
    const y0 = H-padB, plotH = H-padT-padB;
    const x = i => padL + groupW*i + groupW/2 - (series.length*barW)/2;
    const y = v => y0 - (Math.abs(Number(v||0))/maxV)*plotH;

    let grid = '', bars = '', seriesTags = '';
    for (let g=0; g<=4; g++){
      const gy = y0 - (plotH*g/4);
      grid += `<line x1="${padL}" y1="${gy}" x2="${W-padR}" y2="${gy}" stroke="#1e2c4a" stroke-dasharray="3 4"/>
        <text x="${padL-8}" y="${gy+4}" text-anchor="end" fill="#8ea0bd" font-size="10">${num(Math.round(maxV*g/4))}</text>`;
    }
    labels.forEach((lb, i) => {
      series.forEach((s, si) => {
        const v = Number(s.values[i]||0);
        const bx = x(i) + si*barW;
        const by = y(v), bh = y0-by;
        const color = s.color || PALETTE[si % PALETTE.length];
        bars += `<rect x="${bx}" y="${by}" width="${barW-3}" height="${Math.max(0,bh)}" rx="4"
          fill="${color}" opacity="0.9"><title>${esc(lb)} — ${esc(s.name)}: ${num(Math.round(v))}</title></rect>`;
      });
      grid += `<text x="${x(i)+series.length*barW/2}" y="${y0+18}" text-anchor="middle" fill="#8ea0bd" font-size="10">${esc(lb)}</text>`;
    });
    series.forEach((s, si) => {
      seriesTags += `<span class="ch-dot" style="background:${s.color||PALETTE[si%PALETTE.length]}"></span>${esc(s.name)}`;
    });
    container.innerHTML = `<div class="ch-legend ch-legend-top">${seriesTags}</div>
      ${_svg(W,H,grid+bars)}`;
  }

  /* ---------------- خطی / سطح ---------------- */
  function line(container, labels, series, opts){
    opts = opts || {};
    const H = opts.height || 300, W = opts.width || 860;
    const padL = 70, padR = 16, padT = 20, padB = 40;
    const maxV = Math.max(1, ...series.flatMap(s=>s.values.map(v=>Math.abs(Number(v||0)))));
    const n = labels.length;
    const x = i => n<=1 ? (padL+(W-padL-padR)/2) : padL + (W-padL-padR)*i/(n-1);
    const y0 = H-padB, plotH = H-padT-padB;
    const y = v => y0 - (Math.abs(Number(v||0))/maxV)*plotH;

    let grid = '';
    for (let g=0; g<=4; g++){
      const gy = y0 - plotH*g/4;
      grid += `<line x1="${padL}" y1="${gy}" x2="${W-padR}" y2="${gy}" stroke="#1e2c4a" stroke-dasharray="3 4"/>
        <text x="${padL-8}" y="${gy+4}" text-anchor="end" fill="#8ea0bd" font-size="10">${num(Math.round(maxV*g/4))}</text>`;
    }
    // برچسب محور x (حداکثر ۸ برچسب)
    const step = Math.max(1, Math.ceil(n/8));
    labels.forEach((lb, i) => {
      if (i % step !== 0 && i !== n-1) return;
      grid += `<text x="${x(i)}" y="${y0+18}" text-anchor="middle" fill="#8ea0bd" font-size="10">${esc(lb)}</text>`;
    });

    let paths = '', dots = '', area = '';
    series.forEach((s, si) => {
      const color = s.color || PALETTE[si % PALETTE.length];
      let d = '', a = '';
      s.values.forEach((v, i) => {
        const px = x(i), py = y(v);
        d += (i===0?`M ${px} ${py}`:` L ${px} ${py}`);
        a += (i===0?`M ${px} ${y0} L ${px} ${py}`:` L ${px} ${py}`);
        dots += `<circle cx="${px}" cy="${py}" r="3" fill="${color}"><title>${esc(labels[i])}: ${num(Math.round(v))}</title></circle>`;
      });
      if (s.values.length) a += ` L ${x(s.values.length-1)} ${y0} Z`;
      area += (opts.area !== false)
        ? `<path d="${a}" fill="${color}" opacity="0.12"></path>` : '';
      paths += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></path>`;
    });
    let tags = '';
    series.forEach((s, si) => {
      tags += `<span class="ch-dot" style="background:${s.color||PALETTE[si%PALETTE.length]}"></span>${esc(s.name)}`;
    });
    container.innerHTML = `<div class="ch-legend ch-legend-top">${tags}</div>
      ${_svg(W,H,grid+area+paths+dots)}`;
  }

  /* ---------------- میله‌ای افقی (رتبه‌بندی) ---------------- */
  function hbar(container, data, opts){
    opts = opts || {};
    const H = Math.max(140, data.length*46 + 20);
    const W = opts.width || 640, padL = 150, padR = 90;
    const maxV = Math.max(1, ...data.map(d=>Math.abs(Number(d.value||0))));
    let rows = '';
    data.forEach((d, i) => {
      const v = Math.abs(Number(d.value||0));
      const w = Math.max(2, (v/maxV)*(W-padL-padR));
      const color = d.color || PALETTE[i % PALETTE.length];
      rows += `<g>
        <text x="${padL-10}" y="${i*46+26}" text-anchor="end" fill="#aab8d0" font-size="12">${esc(d.label)}</text>
        <rect x="${padL}" y="${i*46+12}" width="${w}" height="22" rx="5" fill="${color}" opacity="0.9">
          <title>${esc(d.label)}: ${num(Math.round(v))}</title></rect>
        <text x="${padL+w+8}" y="${i*46+28}" fill="#e6edf7" font-size="12">${num(Math.round(v))}</text>
      </g>`;
    });
    container.innerHTML = _svg(W, H, rows);
  }

  return { pie, bar, line, hbar, PALETTE };
})();
