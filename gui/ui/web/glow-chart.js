/**
 * ProgressMetricCard adaptado — distribución de severidad (vanilla JS / 21st.dev).
 */
(function (global) {
  const SEVERITY_COLORS = {
    CRÍTICO: { stroke: '#ef4444', text: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
    ALTO: { stroke: '#f97316', text: '#f97316', bg: 'rgba(249,115,22,0.12)' },
    MEDIO: { stroke: '#eab308', text: '#ca8a04', bg: 'rgba(234,179,8,0.12)' },
    BAJO: { stroke: '#3b82f6', text: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
  };
  const ORDER = ['CRÍTICO', 'ALTO', 'MEDIO', 'BAJO'];
  const REGION_W = 62;
  const NEUTRAL_PCT = 0.5;
  let chartUid = 0;
  let state = { periodKey: 'chart.periodAll', view: 'curve' };
  let bound = false;

  function t(key, vars) {
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function periods() {
    return [
      { key: 'chart.periodAll', points: undefined },
      { key: 'chart.period50', points: 50 },
      { key: 'chart.period100', points: 100 },
    ];
  }

  function formatCompact(n) {
    const v = Math.abs(Number(n) || 0);
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 10_000) return `${Math.round(v / 1000)}k`;
    if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
    return String(Math.round(v));
  }

  function sliceWindow(points, n) {
    return n && n < points.length ? points.slice(-n) : points;
  }

  function buildSeries(findings) {
    if (!findings?.length) {
      return { series: { CRÍTICO: [], ALTO: [], MEDIO: [], BAJO: [], TOTAL: [] }, maxY: 1, totals: {} };
    }
    const ordered = [...findings].sort((a, b) => (a.record_number || 0) - (b.record_number || 0));
    const counts = { CRÍTICO: 0, ALTO: 0, MEDIO: 0, BAJO: 0, TOTAL: 0 };
    const series = { CRÍTICO: [], ALTO: [], MEDIO: [], BAJO: [], TOTAL: [] };
    ordered.forEach((f, i) => {
      const lvl = f.suspicion_level || 'BAJO';
      if (counts[lvl] !== undefined) counts[lvl] += 1;
      counts.TOTAL += 1;
      ORDER.forEach((k) => series[k].push({ x: i, y: counts[k], date: String(f.record_number ?? i) }));
      series.TOTAL.push({ x: i, y: counts.TOTAL, date: String(f.record_number ?? i) });
    });
    const maxY = Math.max(1, ...Object.values(counts));
    return { series, maxY, totals: { ...counts } };
  }

  function computeStats(data) {
    const vals = data.map((d) => d.y);
    const sum = vals.reduce((a, b) => a + b, 0);
    const first = vals[0] ?? 0;
    const last = vals[vals.length - 1] ?? 0;
    const prev = vals[vals.length - 2] ?? first;
    const net = last - first;
    return {
      sum,
      net,
      pct: first ? (net / first) * 100 : 0,
      step: last - prev,
      peak: vals.length ? Math.max(...vals) : 0,
      low: vals.length ? Math.min(...vals) : 0,
      avg: vals.length ? sum / vals.length : 0,
      last,
    };
  }

  function scaleFns(w, h, maxX, maxY, pad) {
    return {
      sx: (x) => pad + (x / Math.max(maxX, 1)) * (w - pad * 2),
      sy: (y) => h - pad - (y / maxY) * (h - pad * 2),
      baseline: h - pad,
    };
  }

  /** Catmull-Rom → Bézier cúbico (curvas suaves, estilo ProgressMetricCard). */
  function smoothCurvePath(pts, w, h, maxX, maxY, pad) {
    if (!pts.length) return '';
    const { sx, sy } = scaleFns(w, h, maxX, maxY, pad);
    const xy = pts.map((p) => ({ x: sx(p.x), y: sy(p.y) }));

    if (xy.length === 1) {
      return `M ${xy[0].x.toFixed(1)} ${xy[0].y.toFixed(1)}`;
    }
    if (xy.length === 2) {
      const mx = (xy[0].x + xy[1].x) / 2;
      const my = (xy[0].y + xy[1].y) / 2;
      return `M ${xy[0].x.toFixed(1)} ${xy[0].y.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} `
        + `${xy[1].x.toFixed(1)} ${xy[1].y.toFixed(1)}`;
    }

    const extended = [xy[0], ...xy, xy[xy.length - 1]];
    let d = `M ${xy[0].x.toFixed(1)} ${xy[0].y.toFixed(1)}`;
    for (let i = 0; i < xy.length - 1; i += 1) {
      const p0 = extended[i];
      const p1 = extended[i + 1];
      const p2 = extended[i + 2];
      const p3 = extended[i + 3];
      const c1x = p1.x + (p2.x - p0.x) / 6;
      const c1y = p1.y + (p2.y - p0.y) / 6;
      const c2x = p2.x - (p3.x - p1.x) / 6;
      const c2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} `
        + `${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
    return d;
  }

  function smoothAreaPath(pts, w, h, maxX, maxY, pad) {
    const line = smoothCurvePath(pts, w, h, maxX, maxY, pad);
    if (!line) return '';
    const { sx, baseline } = scaleFns(w, h, maxX, maxY, pad);
    const last = pts[pts.length - 1];
    const first = pts[0];
    return `${line} L ${sx(last.x).toFixed(1)} ${baseline.toFixed(1)} `
      + `L ${sx(first.x).toFixed(1)} ${baseline.toFixed(1)} Z`;
  }

  function pathFromPoints(pts, w, h, maxX, maxY, pad, closeArea) {
    if (!pts.length) return '';
    const line = smoothCurvePath(pts, w, h, maxX, maxY, pad);
    if (!closeArea) return line;
    return smoothAreaPath(pts, w, h, maxX, maxY, pad);
  }

  function barsSvg(pts, w, h, maxX, maxY, pad, color) {
    if (!pts.length) return '';
    const bw = Math.max(2, ((w - pad * 2) / Math.max(pts.length, 1)) * 0.55);
    const sx = (x) => pad + (x / Math.max(maxX, 1)) * (w - pad * 2);
    const sy = (y) => h - pad - (y / maxY) * (h - pad * 2);
    return pts.map((p) => {
      const x = sx(p.x) - bw / 2;
      const y = sy(p.y);
      const bh = h - pad - y;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0, bh).toFixed(1)}" fill="${color}" opacity="0.75" rx="2"/>`;
    }).join('');
  }

  function trendMeta(stats) {
    const flat = Math.abs(stats.pct) < NEUTRAL_PCT;
    const dir = flat ? 'flat' : stats.net >= 0 ? 'up' : 'down';
    const accent = dir === 'flat'
      ? { stroke: '#64748b', text: '#64748b' }
      : dir === 'up'
        ? SEVERITY_COLORS.CRÍTICO
        : SEVERITY_COLORS.BAJO;
    return { dir, accent, pct: `${Math.abs(stats.pct).toFixed(1)}%` };
  }

  function trendIcon(dir) {
    if (dir === 'flat') {
      return '<svg class="metric-trend-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
    }
    if (dir === 'down') {
      return '<svg class="metric-trend-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12l7 7 7-7"/></svg>';
    }
    return '<svg class="metric-trend-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
  }

  function renderChartSvg(chartSeries, view, w, h, maxX, maxY, uid) {
    const pad = 14;
    return chartSeries.map((s, si) => {
      const pts = s.data;
      if (!pts.length) return '';
      const fid = `mc-${uid}-${si}`;
      if (view === 'bar') {
        return barsSvg(pts, w, h, maxX, maxY, pad, s.color);
      }
      const d = pathFromPoints(pts, w, h, maxX, maxY, pad, false);
      const area = pathFromPoints(pts, w, h, maxX, maxY, pad, true);
      return `
        <defs>
          <linearGradient id="${fid}-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${s.color}" stop-opacity="0.28"/>
            <stop offset="100%" stop-color="${s.color}" stop-opacity="0"/>
          </linearGradient>
          <filter id="${fid}" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <path d="${area}" fill="url(#${fid}-area)" opacity="${si === 0 ? 1 : 0.35}"/>
        <path class="glow-line glow-line--dim" d="${d}" stroke="${s.color}" fill="none" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.18" filter="url(#${fid})"/>
        <path class="glow-line glow-line--anim" d="${d}" stroke="${s.color}" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" filter="url(#${fid})" style="animation-delay:${si * 0.12}s"/>
      `;
    }).join('');
  }

  function renderEmpty(el) {
    el.innerHTML = `
      <div class="metric-card metric-card--empty">
        <div class="metric-card__body metric-card__body--empty">
          <h3 class="metric-card__title">${t('chart.title')}</h3>
          <p class="metric-card__empty-title">${t('chart.noData')}</p>
          <p class="metric-card__empty-sub">${t('chart.noDataSub')}</p>
          <button type="button" class="btn-primary metric-card__cta" data-metric-action="scan">
            <span class="ico sm" data-icon="scan" aria-hidden="true"></span>
            <span>${t('cta.scan')}</span>
          </button>
        </div>
      </div>`;
    global.HeimdallIcons?.inject(el);
  }

  function render(containerId, findings) {
    const el = document.getElementById(containerId);
    if (!el) return;

    if (!findings?.length) {
      renderEmpty(el);
      return;
    }

    const uid = ++chartUid;
    const gridId = `metric-grid-${uid}`;
    const { series, maxY, totals } = buildSeries(findings);
    const periodOpt = periods().find((p) => p.key === state.periodKey) ?? periods()[0];

    const visibleSeries = ORDER.filter((k) => (totals[k] || 0) > 0).map((k) => ({
      name: k,
      data: sliceWindow(series[k], periodOpt.points),
      color: SEVERITY_COLORS[k].stroke,
    }));

    const primaryData = sliceWindow(series.TOTAL, periodOpt.points);
    const stats = computeStats(primaryData);
    const { dir, accent, pct } = trendMeta(stats);
    const sign = (n) => (n >= 0 ? '+' : '−') + formatCompact(Math.abs(n));
    const maxX = Math.max((primaryData.length || 1) - 1, 1);
    const w = el.clientWidth ? Math.floor(el.clientWidth * (REGION_W / 100)) : 400;
    const h = 148;

    const periodOptions = periods().map((p) =>
      `<option value="${p.key}"${p.key === state.periodKey ? ' selected' : ''}>${t(p.key)}</option>`
    ).join('');

    const legend = visibleSeries.length > 1
      ? `<div class="metric-card__legend">${visibleSeries.map((s) =>
        `<span class="metric-legend-item"><span class="metric-legend-dot" style="background:${s.color}"></span>${s.name}</span>`
      ).join('')}</div>`
      : '';

    const chartLayers = renderChartSvg(
      visibleSeries.length ? visibleSeries : [{ name: 'TOTAL', data: primaryData, color: accent.stroke }],
      state.view,
      w,
      h,
      maxX,
      maxY,
      uid,
    );

    el.innerHTML = `
      <div class="metric-card" data-metric-card>
        <div class="metric-card__chart-region" style="width:${REGION_W}%">
          <div class="metric-card__chart-gradient" style="background:linear-gradient(to left, ${accent.stroke}1f, transparent 75%)"></div>
          <div class="metric-card__chart-grid">
            <svg class="metric-card__grid-svg" aria-hidden="true">
              <defs>
                <pattern id="${gridId}" width="14" height="14" patternUnits="userSpaceOnUse">
                  <circle cx="1" cy="1" r="1" fill="currentColor"/>
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#${gridId})"/>
            </svg>
          </div>
          <svg class="metric-card__chart-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
            ${chartLayers}
          </svg>
        </div>

        <div class="metric-card__body">
          <div class="metric-card__head">
            <div class="metric-card__head-left">
              <h3 class="metric-card__title">${t('chart.title')}</h3>
              <div class="metric-view-toggle" role="group" aria-label="${t('chart.viewLabel')}">
                <button type="button" class="metric-view-btn${state.view === 'curve' ? ' active' : ''}" data-metric-view="curve">${t('chart.viewCurve')}</button>
                <button type="button" class="metric-view-btn${state.view === 'bar' ? ' active' : ''}" data-metric-view="bar">${t('chart.viewBar')}</button>
              </div>
            </div>
            <div class="metric-card__head-right">
              <span class="metric-trend" style="color:${accent.text}">
                ${trendIcon(dir)}
                ${pct}
              </span>
              <select class="metric-period-select" data-metric-period aria-label="${t('chart.periodLabel')}">
                ${periodOptions}
              </select>
            </div>
          </div>
          ${legend}
          <div class="metric-card__headline">${formatCompact(stats.last || findings.length)}</div>
          <p class="metric-card__sub">${t('chart.sub')}</p>
        </div>

        <div class="metric-card__footer">
          <div class="metric-card__delta">
            <span class="metric-delta-val" style="color:${accent.text}">${sign(stats.step)}</span>
            <span class="metric-delta-label">${t('chart.deltaLabel')}</span>
          </div>
          <div class="metric-card__stats">
            <span><strong>${formatCompact(stats.peak)}</strong> ${t('chart.peak')}</span>
            <span class="metric-stat-sep">·</span>
            <span><strong>${formatCompact(stats.low)}</strong> ${t('chart.low')}</span>
            <span class="metric-stat-sep">·</span>
            <span><strong>${formatCompact(Math.round(stats.avg))}</strong> ${t('chart.avg')}</span>
          </div>
          <button type="button" class="btn-export metric-card__rescan" data-metric-action="scan" title="${t('scan.new')}">
            <span class="ico sm" data-icon="scan" aria-hidden="true"></span>
            ${t('scan.new')}
          </button>
        </div>
      </div>`;
    global.HeimdallIcons?.inject(el);
  }

  function bind(containerId) {
    if (bound) return;
    const el = document.getElementById(containerId);
    if (!el) return;
    bound = true;

    el.addEventListener('click', (e) => {
      const action = e.target.closest('[data-metric-action]');
      if (action?.dataset.metricAction === 'scan') {
        global.runScan?.(false);
        return;
      }
      const viewBtn = e.target.closest('[data-metric-view]');
      if (viewBtn) {
        state.view = viewBtn.dataset.metricView === 'bar' ? 'bar' : 'curve';
        render(containerId, global.findings || []);
      }
    });

    el.addEventListener('change', (e) => {
      if (e.target.matches('[data-metric-period]')) {
        state.periodKey = e.target.value;
        render(containerId, global.findings || []);
      }
    });
  }

  global.HeimdallGlowChart = { render, buildSeries, bind };
})(window);
