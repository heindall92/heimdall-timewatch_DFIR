/* Heimdall Timewatch — dashboard forense */

let bridge = null;
let pendingTasks = new Map();
let findings = [];
let planted = [];
let lastMeta = {};
let lastStats = {};
let selectedIndex = -1;
let scanRunning = false;
let currentView = 'dashboard';
let displayMode = 'graph'; // graph | table
let inspectorTab = 'node';
let sidebarFilter = 'all';

/* ── Timeline animation ── */
let timelineFrames = [];
let timelineFrame = 0;
let timelinePlaying = false;
let timelineLoop = false;
let timelineTimer = null;
let timelineMode = 'idle'; // idle | scan | findings
let timelineScrubbing = false;
let graphRelayoutTimer = null;

function relayoutGraphs() {
  if (graphRelayoutTimer) clearTimeout(graphRelayoutTimer);
  graphRelayoutTimer = setTimeout(() => {
    graphRelayoutTimer = null;
    renderGraph();
    if (currentView === 'lab') renderLabGraph();
    updateGlowChart();
  }, 48);
}

function relayoutGraphsNow() {
  if (graphRelayoutTimer) clearTimeout(graphRelayoutTimer);
  graphRelayoutTimer = null;
  renderGraph();
  if (currentView === 'lab') renderLabGraph();
  updateGlowChart();
}

function initGraphResizeWatch() {
  document.querySelectorAll('.graph-area').forEach((area) => {
    const ro = new ResizeObserver(() => relayoutGraphs());
    ro.observe(area);
  });
  document.querySelector('.sidebar')?.addEventListener('transitionend', (e) => {
    if (e.propertyName === 'width') relayoutGraphsNow();
  });
}

function $(id) { return document.getElementById(id); }

function t(key, vars) {
  return window.HeimdallI18n?.t(key, vars) ?? key;
}

function applyTheme(theme) {
  const next = theme === 'light' ? 'light' : 'dark';
  document.body.setAttribute('data-theme', next);
  const toggle = $('theme-toggle');
  if (toggle) {
    toggle.checked = next === 'dark';
    window.HeimdallElasticSwitch?.syncAria(toggle);
  }
  const setTheme = $('set-theme');
  if (setTheme) setTheme.value = next;
  const label = document.querySelector('.theme-label');
  if (label) label.textContent = t(next === 'dark' ? 'theme.dark' : 'theme.light');
}

function applyLocale(locale) {
  if (!window.HeimdallI18n) return locale;
  HeimdallI18n.setLocale(locale);
  document.querySelectorAll('.lang-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.lang === HeimdallI18n.getLocale());
  });
  const setLoc = $('set-locale');
  if (setLoc) setLoc.value = HeimdallI18n.getLocale();
  refreshCtaLabels();
  updateOllamaStatus();
  if (lastMeta && Object.keys(lastMeta).length) {
    updateStats(lastStats, lastMeta);
  }
}

function refreshCtaLabels() {
  const ctaLabel = $('cta-label');
  const ctaSub = $('cta-sub');
  const btnScan = $('btn-scan');
  if (currentView === 'lab') {
    if (ctaLabel) ctaLabel.textContent = t('cta.lab');
    if (ctaSub) ctaSub.textContent = t('cta.labSub');
    if (btnScan) btnScan.title = t('cta.lab');
  } else if (currentView === 'dashboard') {
    if (ctaLabel) ctaLabel.textContent = t('cta.scan');
    if (ctaSub) ctaSub.textContent = t('cta.scanSub');
    if (btnScan) btnScan.title = t('cta.scan');
  }
}

async function persistUiPrefs() {
  if (!bridge) return;
  try {
    await callBridge('save_app_settings', JSON.stringify({
      theme: document.body.getAttribute('data-theme') || 'dark',
      locale: HeimdallI18n?.getLocale() || 'es',
    }));
  } catch { /* offline / early init */ }
}

function setScanControlsDisabled(disabled) {
  const ids = ['btn-scan', 'btn-lab', 'btn-new-scan', 'btn-new-lab', 'btn-lab-rescan', 'ntfs-run-scan'];
  ids.forEach((id) => {
    const node = $(id);
    if (!node) return;
    if (disabled) node.setAttribute('disabled', 'disabled');
    else node.removeAttribute('disabled');
  });
}

function resetScanUi() {
  $('timeline-bar')?.classList.remove('is-scanning');
  if (timelineMode === 'scan') {
    timelineMode = timelineFrames.length ? 'findings' : 'idle';
  }
  setTimelineControlsEnabled(timelineFrames.length > 0);
  $('scan-progress').hidden = true;
}

function updateScanActionVisibility() {
  const onDash = currentView === 'dashboard';
  const onLab = currentView === 'lab';
  $('btn-new-scan')?.toggleAttribute('hidden', !onDash);
  $('btn-new-lab')?.toggleAttribute('hidden', !onDash);
  $('btn-lab-rescan')?.toggleAttribute('hidden', !onLab);
}

function updateGlowChart() {
  if (window.HeimdallGlowChart && $('glow-chart')) {
    HeimdallGlowChart.render('glow-chart', findings);
  }
}

function toast(msg, isErr = false) {
  const el = $('toast');
  el.textContent = msg;
  el.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 3200);
}
window.toast = toast;

function parseJson(raw) {
  try { return JSON.parse(raw); } catch { return { ok: false, error: 'JSON inválido' }; }
}

function callBridge(method, ...args) {
  return new Promise((resolve, reject) => {
    if (!bridge || typeof bridge[method] !== 'function') {
      reject(new Error('Bridge no disponible'));
      return;
    }
    Promise.resolve(bridge[method](...args)).then(resolve).catch(reject);
  });
}

function waitTask(initialRaw, timeoutMs = 600000) {
  const initial = typeof initialRaw === 'string' ? parseJson(initialRaw) : initialRaw;
  if (!initial.pending) return Promise.resolve(initial);
  const id = initial.request_id;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingTasks.delete(id);
      reject(new Error('Tiempo de espera agotado'));
    }, timeoutMs);
    pendingTasks.set(id, {
      resolve: (d) => { clearTimeout(timer); resolve(d); },
      reject: (e) => { clearTimeout(timer); reject(e); },
    });
  });
}

function onTaskFinished(raw) {
  const payload = parseJson(raw);
  const entry = pendingTasks.get(payload.request_id);
  if (!entry) return;
  pendingTasks.delete(payload.request_id);
  if (payload.result?.ok === false && payload.result.error) {
    entry.reject(new Error(payload.result.error));
  } else {
    entry.resolve(payload.result || payload);
  }
}

function onScanProgress(raw) {
  const data = parseJson(raw);
  const bar = $('scan-progress');
  const status = $('scan-status');
  bar.hidden = false;
  bar.querySelector('span').style.width = '100%';
  const phaseKey = data.phase === 'usn' ? 'scan.phase.usn' : data.phase === 'mft' ? 'scan.phase.mft' : 'scan.phase.proc';
  const label = t(phaseKey);
  const count = Number(data.count).toLocaleString();
  status.textContent = t('scan.progress', { phase: label, count });

  timelineMode = 'scan';
  $('timeline-bar')?.classList.add('is-scanning');
  pauseTimeline();
  const pct = Math.min(98, 8 + (Math.log10(Math.max(data.count, 1)) * 18));
  setTimelineProgress(pct / 100, t('scan.progressShort', { phase: label, count }));
}

function setTimelineProgress(ratio, label) {
  const pct = `${Math.max(0, Math.min(100, ratio * 100))}%`;
  $('timeline-fill').style.width = pct;
  $('timeline-thumb').style.left = pct;
  if (label) $('timeline-ts').textContent = label;
}

function rebuildTimeline() {
  timelineFrames = findings
    .map((_, i) => i)
    .sort((a, b) => (findings[a].record_number || 0) - (findings[b].record_number || 0));
  timelineFrame = 0;
  timelineMode = timelineFrames.length ? 'findings' : 'idle';
  $('timeline-bar')?.classList.remove('is-scanning');
  pauseTimeline();
  renderTimelineTicks();
  updateTimelineUI();
  setTimelineControlsEnabled(timelineFrames.length > 0);
  if (timelineFrames.length) {
    goToTimelineFrame(0, { syncFinding: true, silent: true });
  } else {
    setTimelineProgress(0, t('timeline.none') + ' · — UTC');
    $('timeline-counter').textContent = '0 / 0';
  }
}

function renderTimelineTicks() {
  const ticks = $('timeline-ticks');
  if (!ticks) return;
  ticks.innerHTML = '';
  const n = timelineFrames.length;
  if (n <= 1) return;
  timelineFrames.forEach((findingIdx, frameIdx) => {
    const f = findings[findingIdx];
    const tick = document.createElement('span');
    tick.className = 'timeline-tick';
    if (f?.suspicion_level === 'CRÍTICO') tick.classList.add('is-critical');
    if (frameIdx === timelineFrame) tick.classList.add('is-active');
    tick.style.left = `${(frameIdx / (n - 1)) * 100}%`;
    ticks.appendChild(tick);
  });
}

function setTimelineControlsEnabled(enabled) {
  ['timeline-play', 'timeline-prev', 'timeline-next', 'timeline-reset', 'timeline-speed'].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = !enabled;
  });
  const loop = $('timeline-loop');
  if (loop) loop.disabled = !enabled;
}

function getTimelineIntervalMs() {
  return Number($('timeline-speed')?.value) || 1200;
}

function updateTimelineUI() {
  const n = timelineFrames.length;
  const playBtn = $('timeline-play');
  const bar = $('timeline-bar');

  if (timelineMode === 'scan') return;

  if (n === 0) {
    setTimelineProgress(0);
    $('timeline-counter').textContent = '0 / 0';
    if (playBtn) playBtn.textContent = '▶';
    bar?.classList.remove('is-playing');
    return;
  }

  const ratio = n <= 1 ? 0 : timelineFrame / (n - 1);
  setTimelineProgress(ratio);

  const f = findings[timelineFrames[timelineFrame]];
  const name = f?.filename || (f ? `MFT #${f.record_number}` : '—');
  const mftHex = f ? `0x${f.record_number.toString(16).padStart(4, '0').toUpperCase()}` : '—';
  $('timeline-counter').textContent = `${timelineFrame + 1} / ${n}`;
  $('timeline-ts').textContent = `${name} · ${mftHex} · score ${f?.score ?? 0}`;

  if (playBtn) playBtn.textContent = timelinePlaying ? '⏸' : '▶';
  bar?.classList.toggle('is-playing', timelinePlaying);
  renderTimelineTicks();
}

function goToTimelineFrame(frameIdx, opts = {}) {
  const n = timelineFrames.length;
  if (!n) return;
  timelineFrame = Math.max(0, Math.min(n - 1, frameIdx));
  updateTimelineUI();
  if (opts.syncFinding !== false) {
    const findingIdx = timelineFrames[timelineFrame];
    showDetail(findingIdx, { skipTimeline: true });
  }
}

function stepTimeline(delta) {
  if (!timelineFrames.length) return;
  pauseTimeline();
  goToTimelineFrame(timelineFrame + delta);
}

function resetTimeline() {
  if (!timelineFrames.length) return;
  pauseTimeline();
  goToTimelineFrame(0);
}

function toggleTimeline() {
  if (!timelineFrames.length || timelineMode === 'scan') return;
  if (timelinePlaying) pauseTimeline();
  else playTimeline();
}

function playTimeline() {
  if (!timelineFrames.length || timelineMode === 'scan') return;
  timelinePlaying = true;
  updateTimelineUI();
  scheduleTimelineStep();
}

function pauseTimeline() {
  timelinePlaying = false;
  if (timelineTimer) {
    clearTimeout(timelineTimer);
    timelineTimer = null;
  }
  updateTimelineUI();
}

function scheduleTimelineStep() {
  if (!timelinePlaying) return;
  timelineTimer = setTimeout(() => {
    if (!timelinePlaying) return;
    const n = timelineFrames.length;
    if (timelineFrame >= n - 1) {
      if (timelineLoop && $('timeline-loop')?.checked) {
        goToTimelineFrame(0);
      } else {
        pauseTimeline();
        return;
      }
    } else {
      goToTimelineFrame(timelineFrame + 1);
    }
    scheduleTimelineStep();
  }, getTimelineIntervalMs());
}

function syncTimelineToFinding(findingIdx) {
  if (timelineMode === 'scan' || !timelineFrames.length) return;
  const frame = timelineFrames.indexOf(findingIdx);
  if (frame >= 0 && frame !== timelineFrame) {
    pauseTimeline();
    timelineFrame = frame;
    updateTimelineUI();
  }
}

function positionFromTimelineEvent(event) {
  const track = $('timeline-track');
  if (!track) return 0;
  const rect = track.getBoundingClientRect();
  const x = (event.clientX ?? 0) - rect.left;
  return Math.max(0, Math.min(1, x / rect.width));
}

function scrubTimeline(ratio) {
  if (!timelineFrames.length) return;
  const n = timelineFrames.length;
  const frame = n <= 1 ? 0 : Math.round(ratio * (n - 1));
  goToTimelineFrame(frame);
}

function bindTimelineEvents() {
  const track = $('timeline-track');
  const thumb = $('timeline-thumb');
  if (!track || !thumb) return;

  track.addEventListener('click', (e) => {
    if (timelineMode === 'scan' || !timelineFrames.length) return;
    if (e.target === thumb) return;
    pauseTimeline();
    scrubTimeline(positionFromTimelineEvent(e));
  });

  const startScrub = (e) => {
    if (timelineMode === 'scan' || !timelineFrames.length) return;
    e.preventDefault();
    timelineScrubbing = true;
    $('timeline-bar')?.classList.add('is-scrubbing');
    pauseTimeline();
    scrubTimeline(positionFromTimelineEvent(e));
  };

  const moveScrub = (e) => {
    if (!timelineScrubbing) return;
    scrubTimeline(positionFromTimelineEvent(e));
  };

  const endScrub = () => {
    if (!timelineScrubbing) return;
    timelineScrubbing = false;
    $('timeline-bar')?.classList.remove('is-scrubbing');
  };

  thumb.addEventListener('mousedown', startScrub);
  track.addEventListener('mousedown', (e) => {
    if (e.target !== thumb) startScrub(e);
  });
  document.addEventListener('mousemove', moveScrub);
  document.addEventListener('mouseup', endScrub);

  $('timeline-play')?.addEventListener('click', toggleTimeline);
  $('timeline-prev')?.addEventListener('click', () => stepTimeline(-1));
  $('timeline-next')?.addEventListener('click', () => stepTimeline(1));
  $('timeline-reset')?.addEventListener('click', resetTimeline);
  $('timeline-speed')?.addEventListener('change', () => {
    if (timelinePlaying) {
      pauseTimeline();
      playTimeline();
    }
  });
  $('timeline-loop')?.addEventListener('change', (e) => {
    timelineLoop = e.target.checked;
  });

  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea, select')) return;
    if (currentView === 'ai' || currentView === 'settings') return;
    if (e.code === 'Space') {
      e.preventDefault();
      toggleTimeline();
    } else if (e.code === 'ArrowLeft') {
      e.preventDefault();
      stepTimeline(-1);
    } else if (e.code === 'ArrowRight') {
      e.preventDefault();
      stepTimeline(1);
    } else if (e.code === 'Home') {
      e.preventDefault();
      resetTimeline();
    }
  });
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function levelBadge(level) {
  return `<span class="badge badge-${level}">${level}</span>`;
}

function levelClass(level) {
  if (level === 'CRÍTICO') return 'crit';
  if (level === 'ALTO') return 'high';
  return '';
}

function getBaseFilteredFindings() {
  const q = ($('filter-text')?.value || '').toLowerCase();
  return findings.filter((f) => {
    if (sidebarFilter === 'CRÍTICO' || sidebarFilter === 'ALTO') {
      if (f.suspicion_level !== sidebarFilter) return false;
    }
    const name = (f.filename || '').toLowerCase();
    return !q || name.includes(q) || String(f.record_number).includes(q);
  });
}

function getFilteredFindings() {
  const base = getBaseFilteredFindings();
  return window.HeimdallAdvancedFilters?.applyToFindings(base) ?? base;
}

function applyGlobalSearch(query) {
  const q = (query ?? '').trim();
  const filter = $('filter-text');
  if (filter) filter.value = q;
  HeimdallExpandingSearch?.sync?.(q);
  if (q && currentView !== 'dashboard' && currentView !== 'lab') {
    switchView('dashboard');
  } else {
    renderGraph();
    if (currentView === 'lab') renderLabGraph();
  }
}

function switchView(name) {
  currentView = name;
  document.querySelectorAll('.nav-item[data-view]').forEach((t) => {
    t.classList.toggle('active', t.dataset.view === name);
  });
  document.querySelectorAll('.view').forEach((v) => {
    v.classList.toggle('active', v.id === `view-${name}`);
  });

  const shell = $('shell');
  const inspector = $('inspector');
  const timeline = $('timeline-bar');
  const sidebarDash = $('sidebar-dashboard');
  const sidebarLab = $('sidebar-lab');
  const sidebarCta = document.querySelector('.sidebar-cta');
  const ctaLabel = $('cta-label');
  const ctaFab = $('btn-scan');
  const btnLab = $('btn-lab');

  const fullViews = name === 'ai' || name === 'settings' || name === 'explorer';

  if (fullViews) {
    shell.classList.add('full-height');
    inspector.classList.add('hidden');
    timeline.classList.add('hidden');
    sidebarDash.hidden = true;
    sidebarLab.hidden = true;
    if (sidebarCta) sidebarCta.hidden = true;
  } else {
    shell.classList.remove('full-height');
    inspector.classList.remove('hidden');
    timeline.classList.remove('hidden');
    sidebarDash.hidden = name !== 'dashboard';
    sidebarLab.hidden = name !== 'lab';
    if (sidebarCta) sidebarCta.hidden = false;
  }

  if (name === 'lab') {
    refreshCtaLabels();
    if (ctaFab) ctaFab.onclick = () => runScan(true);
  } else if (name === 'dashboard') {
    refreshCtaLabels();
    if (ctaFab) ctaFab.onclick = () => runScan(false);
  }

  if (name === 'lab') renderLabGraph();
  else if (name === 'explorer') {
    syncMftPathDisplay();
    HeimdallNtfsExplorer?.render(findings, lastMeta);
  } else renderGraph();
  updateScanActionVisibility();
}

function syncMftPathDisplay() {
  const main = $('mft-path');
  const ntfs = $('ntfs-mft-path');
  if (!main || !ntfs) return;
  const path = main.value.trim() || lastMeta?.mft_file || '';
  if (path && !main.value.trim()) main.value = path;
  ntfs.value = main.value.trim() || path;
}

window.switchView = switchView;

function setDisplayMode(mode) {
  displayMode = mode;
  $('graph-area').hidden = mode === 'table';
  $('table-wrap').hidden = mode !== 'table';
  $('btn-view-graph')?.classList.toggle('active', mode === 'graph');
  $('btn-view-table')?.classList.toggle('active', mode === 'table');
}

/* ── Graph layout ── */
function layoutNodes(count, width, height) {
  return HeimdallForensicsGraph?.layoutNodes(count, width, height) || [];
}

function renderGraphNodes(containerId, emptyId, items, onSelect) {
  HeimdallForensicsGraph?.renderGraphNodes(containerId, emptyId, items, {
    findings,
    selectedIndex,
    onSelect,
    resolveIndex: (f) => findings.indexOf(f),
  });
}

function renderGraph() {
  renderGraphNodes('graph-nodes', 'graph-empty', getFilteredFindings(), showDetail);
  renderFindingsTable();
}

function renderLabGraph() {
  const labItems = planted.length
    ? planted.map((p) => {
        const match = findings.find((f) => f.record_number === p.record_number);
        return match || {
          record_number: p.record_number,
          filename: p.label,
          suspicion_level: p.detected ? 'ALTO' : 'BAJO',
          score: p.detected ? 50 : 0,
          findings: p.detected ? [{ code: 'LAB', title: p.label }] : [],
          is_directory: false,
          in_use: true,
        };
      })
    : getFilteredFindings();

  renderGraphNodes('lab-graph-nodes', 'lab-graph-empty', labItems, (idx) => {
    const item = labItems[idx];
    const realIdx = findings.findIndex((f) => f.record_number === item.record_number);
    showDetail(realIdx >= 0 ? realIdx : idx);
  });
}

function renderFindingsTable() {
  const base = getBaseFilteredFindings();
  const items = getFilteredFindings();
  HeimdallFindingsTable?.render('findings-table-root', {
    items,
    allItems: base,
    selectedIndex,
    onSelect: showDetail,
    resolveIndex: (f) => findings.indexOf(f),
  });
}

function renderInspectorTab(f) {
  const body = $('inspector-body');
  if (!f) {
    body.innerHTML = '<p class="empty-state">Selecciona un nodo en el grafo o una fila en la tabla</p>';
    return;
  }

  if (inspectorTab === 'node') {
    body.innerHTML = `
      <div class="meta-block">
        <div class="meta-label">FILENAME</div>
        <div class="meta-value">${escapeHtml(f.filename || `registro #${f.record_number}`)}</div>
      </div>
      <div class="meta-block">
        <div class="meta-label">SUSPICION LEVEL</div>
        <div class="meta-value">${levelBadge(f.suspicion_level)} · score ${f.score}</div>
      </div>
      <div class="meta-block">
        <div class="meta-label">STATUS</div>
        <div class="meta-value">${f.is_directory ? 'DIR' : 'FILE'} · ${f.in_use ? 'IN USE' : 'DELETED'}</div>
      </div>
      <div class="divider"></div>
      <div class="section-title heuristics-title">⏱ HEURISTICS SUMMARY</div>
      ${(f.findings || []).slice(0, 3).map((item) => `
        <div class="finding-detail">
          <strong>${escapeHtml(item.code)}</strong> ${escapeHtml(item.title)}
          <div class="finding-detail-body">${escapeHtml(item.detail)}</div>
        </div>
      `).join('') || '<p class="empty-state">Sin heurísticas</p>'}
    `;
  } else if (inspectorTab === 'mft') {
    body.innerHTML = `
      <div class="meta-block">
        <div class="meta-label">MFT REFERENCE</div>
        <div class="meta-value accent">0x${f.record_number.toString(16).padStart(8, '0').toUpperCase()}</div>
      </div>
      <div class="meta-block">
        <div class="meta-label">RECORD NUMBER</div>
        <div class="meta-value">${f.record_number}</div>
      </div>
      <div class="meta-block">
        <div class="meta-label">ENTRY TYPE</div>
        <div class="meta-value">${f.is_directory ? 'Directory' : 'File'} · ${f.in_use ? 'Active' : 'Deleted'}</div>
      </div>
      <div class="divider"></div>
      <div class="section-title">⏱ TIMESTAMPS (from heuristics)</div>
      ${(f.findings || []).map((item, i) => `
        <div class="ts-row${i === 0 ? ' highlight' : ''}">
          <span class="ts-key">${escapeHtml(item.code)}</span>
          <span class="ts-val">${escapeHtml(item.detail.slice(0, 42))}${item.detail.length > 42 ? '…' : ''}</span>
        </div>
      `).join('') || '<p class="empty-state">Sin datos de timestamp en hallazgos</p>'}
    `;
  } else {
    const tags = (f.findings || []).map((item) => {
      const alert = item.confidence === 'ALTA' || f.suspicion_level === 'CRÍTICO';
      return `<span class="reason-tag${alert ? ' alert' : ''}">${escapeHtml(item.code)} · ${escapeHtml(item.title)} (${escapeHtml(item.confidence)})</span>`;
    }).join('');
    body.innerHTML = `
      <div class="section-title">⚑ REASON CODES</div>
      <div class="reason-tags">${tags || '<span class="reason-tag">CLEAN</span>'}</div>
      <div class="divider"></div>
      ${(f.findings || []).map((item) => `
        <div class="finding-detail">
          <strong>${escapeHtml(item.code)}</strong> — ${escapeHtml(item.confidence)}
          <div style="margin-top:4px">${escapeHtml(item.detail)}</div>
          <div class="fp">⚠ FP: ${escapeHtml(item.false_positive_note || '—')}</div>
        </div>
      `).join('')}
    `;
  }
}

function showDetail(idx, opts = {}) {
  selectedIndex = idx;
  const f = findings[idx];
  renderGraph();
  if (currentView === 'lab') renderLabGraph();
  renderInspectorTab(f);
  if (!opts.skipTimeline) syncTimelineToFinding(idx);
  else if (f && timelineMode !== 'scan') {
    const n = timelineFrames.length;
    if (n > 1) {
      const ratio = timelineFrame / (n - 1);
      setTimelineProgress(ratio);
    }
  }
}

function updateStats(stats, meta) {
  if (stats && Object.keys(stats).length) lastStats = stats;
  if (meta && Object.keys(meta).length) lastMeta = meta;
  $('stat-crit').textContent = lastStats.critical ?? 0;
  $('stat-high').textContent = lastStats.high ?? 0;
  $('stat-med').textContent = lastStats.medium ?? 0;
  $('stat-low').textContent = lastStats.low ?? 0;
  $('stat-flagged').textContent = lastStats.files_flagged ?? 0;
  const badge = $('badge-flagged');
  if (badge) badge.textContent = lastStats.files_flagged ?? 0;
  const mft = meta?.mft_file || '—';
  const fileName = mft.split(/[/\\]/).pop() || mft;
  const analyzed = lastStats.files_analyzed ?? 0;
  if (analyzed || fileName !== '—') {
    $('results-meta').textContent = t('results.meta', { file: fileName, n: analyzed });
  } else {
    $('results-meta').textContent = t('results.none');
  }

  $('lab-stat-crit').textContent = lastStats.critical ?? 0;
  $('lab-stat-flagged').textContent = lastStats.files_flagged ?? 0;
  updateGlowChart();
}

function updateLabStats(result) {
  $('lab-stat-detected').textContent = result.lab_hits ?? 0;
  $('lab-stat-planted').textContent = result.lab_total ?? 0;
  if (result.planted) {
    $('lab-banner').textContent = t('lab.hit', { hits: result.lab_hits ?? 0, total: result.lab_total ?? 0 });
    $('lab-status').textContent = t('lab.lastRun', { hits: result.lab_hits ?? 0, total: result.lab_total ?? 0 });
  }
}

function applyScanResult(result, isLab = false, opts = {}) {
  findings = result.findings || [];
  planted = result.planted || [];
  lastMeta = result.meta || {};
  window.findings = findings;
  window.lastMeta = lastMeta;
  updateStats(result.stats || {}, lastMeta);
  if (isLab) updateLabStats(result);
  renderGraph();
  if (isLab) {
    renderLabGraph();
    switchView(opts.stayView || 'lab');
    HeimdallNotifs?.push({
      kind: 'lab',
      tone: 'green',
      icon: 'lab',
      title: t('notif.labDone'),
      desc: t('notif.labDesc', { hits: result.lab_hits ?? 0, total: result.lab_total ?? 0 }),
      meta: `${result.lab_hits ?? 0}/${result.lab_total ?? 0}`,
      action: 'lab',
    });
  } else {
    switchView(opts.stayView || 'dashboard');
    HeimdallNotifs?.pushScanResult({ stats: result.stats || {}, meta: lastMeta });
  }
  syncMftPathDisplay();
  HeimdallNtfsExplorer?.render(findings, lastMeta);
  rebuildTimeline();
}

function scanConfig() {
  return {
    mft: $('mft-path').value.trim(),
    usn: $('usn-path').value.trim(),
    system_install: $('system-install').value || '',
    min_score: Number($('min-score').value) || 1,
    only_in_use: $('only-in-use').checked,
    include_directories: $('include-dirs').checked,
    enable_h3: $('enable-h3').checked,
  };
}

async function ensureMftPath() {
  const current = $('mft-path').value.trim();
  const check = parseJson(await callBridge('validate_path', current));
  if (check.ok) return check.path || current;

  toast(t('scan.pickMft'), true);
  const pick = parseJson(await callBridge('pick_file', 'mft'));
  if (!pick.ok || !pick.path) {
    throw new Error(t('scan.noMft'));
  }
  $('mft-path').value = pick.path;
  return pick.path;
}

async function runScan(lab = false, opts = {}) {
  if (scanRunning) {
    toast(t('scan.busy'), true);
    return;
  }
  scanRunning = true;
  setScanControlsDisabled(true);
  $('scan-progress').hidden = false;
  timelineMode = 'scan';
  $('timeline-bar')?.classList.add('is-scanning');
  pauseTimeline();
  setTimelineProgress(0, lab ? t('scan.labGen') : t('scan.analyzing'));
  setTimelineControlsEnabled(false);
  if (lab) {
    $('lab-status').textContent = t('scan.labGen');
  } else {
    $('scan-status').textContent = t('scan.analyzing');
  }

  try {
    if (!lab) await ensureMftPath();
    const raw = lab
      ? await callBridge('start_lab', JSON.stringify({
          clean_files: Number($('lab-clean-files')?.value) || 200,
        }))
      : await callBridge('start_scan', JSON.stringify(scanConfig()));
    const parsed = typeof raw === 'string' ? parseJson(raw) : raw;
    if (!parsed.pending && parsed.ok === false) {
      throw new Error(parsed.error || t('scan.error'));
    }
    const result = parsed.pending ? await waitTask(raw) : parsed;
    if (result?.ok === false) {
      throw new Error(result.error || t('scan.error'));
    }
    applyScanResult(result, lab, opts);
    toast(lab
      ? t('toast.labDone', { hits: result.lab_hits, total: result.lab_total })
      : t('toast.scanDone'));
    if (!lab) $('scan-status').textContent = t('scan.done', { n: findings.length });
  } catch (err) {
    toast(err.message || String(err), true);
    if (lab) $('lab-status').textContent = t('scan.errorLab');
    else $('scan-status').textContent = t('scan.error');
    resetScanUi();
  } finally {
    scanRunning = false;
    setScanControlsDisabled(false);
  }
}

async function loadSettings() {
  const data = parseJson(await callBridge('get_settings'));
  if (!data.ok) return;
  const s = data.settings || {};
  $('mft-path').value = s.last_mft || '';
  $('usn-path').value = s.last_usn || '';
  syncMftPathDisplay();
  $('system-install').value = s.system_install || '';
  $('min-score').value = s.min_score || '1';
  $('only-in-use').checked = s.only_in_use === 'true';
  $('include-dirs').checked = s.include_directories === 'true';
  $('enable-h3').checked = s.enable_h3 !== 'false';
  $('set-provider').value = s.ollama_provider || 'local';
  $('set-host').value = s.ollama_host || 'http://localhost:11434';
  applyTheme(s.theme || 'dark');
  applyLocale(s.locale || 'es');
  syncProviderFields();
  await refreshModels(s.ollama_model || s.ollama_cloud_model);
  HeimdallProfile?.applyUserProfile(s);
}

function syncProviderFields() {
  const cloud = $('set-provider').value === 'cloud';
  $('field-cloud-key').hidden = !cloud;
  $('field-host').hidden = cloud;
}

async function refreshModels(selected) {
  const data = parseJson(await callBridge('get_ollama_models'));
  const sel = $('set-model');
  sel.innerHTML = '';
  (data.models?.length ? data.models : ['llama3.2', 'gpt-oss:120b']).forEach((m) => {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    sel.appendChild(opt);
  });
  if (selected && [...sel.options].some((o) => o.value === selected)) sel.value = selected;
}

async function updateOllamaStatus() {
  const data = parseJson(await callBridge('get_ollama_status'));
  const dot = $('ollama-dot');
  const label = $('ollama-label');
  if (data.connected) {
    dot.className = 'status-dot on';
    label.textContent = t('ollama.on', {
      prov: t(data.provider === 'cloud' ? 'ollama.cloud' : 'ollama.local'),
      model: data.model || '?',
    });
  } else {
    dot.className = 'status-dot off';
    label.textContent = t('ollama.off');
  }
}

async function saveSettings() {
  const payload = {
    ollama_provider: $('set-provider').value,
    ollama_host: $('set-host').value.trim(),
    ollama_model: $('set-model').value,
    ollama_cloud_model: $('set-model').value,
    ollama_cloud_key: $('set-cloud-key').value.trim(),
    theme: document.body.getAttribute('data-theme') || 'dark',
    locale: HeimdallI18n?.getLocale() || 'es',
  };
  const data = parseJson(await callBridge('save_app_settings', JSON.stringify(payload)));
  if (data.ok) {
    toast(t('toast.saved'));
    $('settings-status').textContent = t('settings.savedOk');
    await updateOllamaStatus();
  } else {
    toast(data.error || 'Error al guardar', true);
  }
}

async function testOllama() {
  $('settings-status').textContent = t('settings.testing');
  const data = parseJson(await callBridge('test_ollama_connection'));
  $('settings-status').textContent = data.connected
    ? t('settings.connOk', { model: data.model })
    : (data.error || t('settings.noConn'));
  if (data.connected) toast(t('toast.ollamaOk'));
  else toast(data.error || 'Sin conexión', true);
  await refreshModels(data.model);
  await updateOllamaStatus();
}

async function exportReport(kind) {
  try {
    const data = parseJson(await callBridge('export_report', kind));
    if (data.cancelled) return;
    if (data.ok) toast(t('toast.exported', { path: data.path }));
    else toast(data.error || 'Error', true);
  } catch (err) {
    toast(String(err), true);
  }
}
window.exportReport = exportReport;
window.runScan = runScan;

async function aiAnalyzeScan() {
  const result = await waitTask(await callBridge('ai_analyze_scan'), 300000);
  return result.content || result.error || t('ai.noReply');
}

async function aiSendChat(msg) {
  const result = await waitTask(await callBridge('ai_chat', msg), 300000);
  return result.content || result.error || t('ai.noReply');
}

function mountAiChat() {
  window.HeimdallAiChat?.mount('ai-chat-root', {
    translate: t,
    analyzeScan: aiAnalyzeScan,
    sendChat: aiSendChat,
    exportSummary: exportAiSummary,
  });
}

async function exportAiSummary(content, kind) {
  try {
    const data = parseJson(await callBridge('export_ai_summary', content, kind));
    if (data.cancelled) return;
    if (data.ok) toast(t('toast.exported', { path: data.path }));
    else toast(data.error || 'Error', true);
  } catch (err) {
    toast(String(err), true);
  }
}

function applySidebarFilter(filter) {
  sidebarFilter = filter;
  document.querySelectorAll('.sidebar-link[data-filter]').forEach((l) => {
    l.classList.toggle('active', l.dataset.filter === filter);
  });
  document.querySelectorAll('.chip[data-filter]').forEach((c) => {
    c.classList.toggle('active', c.dataset.filter === filter);
  });
  renderGraph();
}

window.applySidebarFilter = applySidebarFilter;

function closeUserPopup() {
  const modal = $('user-menu-modal');
  const chip = $('user-chip');
  if (modal) modal.hidden = true;
  chip?.setAttribute('aria-expanded', 'false');
}
window.closeUserPopup = closeUserPopup;

function openUserPopup() {
  HeimdallNotifs?.closePanel?.();
  const modal = $('user-menu-modal');
  if (!modal) return;
  modal.hidden = false;
  HeimdallIcons?.inject(modal);
  $('user-chip')?.setAttribute('aria-expanded', 'true');
}

function toggleUserPopup() {
  const modal = $('user-menu-modal');
  if (!modal) return;
  if (!modal.hidden) closeUserPopup();
  else openUserPopup();
}

function openSupportModal() {
  const modal = $('support-modal');
  if (!modal) return;
  modal.hidden = false;
  HeimdallIcons?.inject(modal);
}

function closeSupportModal() {
  $('support-modal').hidden = true;
}

function initSupportModal() {
  $('btn-support')?.addEventListener('click', openSupportModal);
  $('support-close')?.addEventListener('click', closeSupportModal);
  $('support-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'support-modal') closeSupportModal();
  });
}

function initUserMenu() {
  $('user-chip')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleUserPopup();
  });
  $('user-chip')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleUserPopup();
    }
  });
  $('user-menu-close')?.addEventListener('click', closeUserPopup);
  $('user-menu-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'user-menu-modal') closeUserPopup();
  });
  document.querySelectorAll('#user-menu-modal [data-user-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.userAction;
      closeUserPopup();
      if (action === 'profile') HeimdallProfile?.openUserProfile();
      else if (action === 'settings') switchView('settings');
      else if (action === 'explorer') switchView('explorer');
      else if (action === 'help') openSupportModal();
      else if (action === 'quit') callBridge('quit_application');
    });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeUserPopup();
      closeSupportModal();
      HeimdallProfile?.closeUserProfile();
    }
  });
}

function bindEvents() {
  document.querySelectorAll('.nav-item[data-view]').forEach((tab) => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });

  document.querySelectorAll('.inspector-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      inspectorTab = tab.dataset.tab;
      document.querySelectorAll('.inspector-tab').forEach((t) => t.classList.toggle('active', t === tab));
      showDetail(selectedIndex);
    });
  });

  document.querySelectorAll('.sidebar-link[data-filter], .chip[data-filter]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      applySidebarFilter(el.dataset.filter);
    });
  });

  $('btn-sidebar-toggle')?.addEventListener('click', () => {
    const root = $('app-root');
    root?.classList.toggle('sidebar-collapsed');
    const collapsed = root?.classList.contains('sidebar-collapsed');
    const btn = $('btn-sidebar-toggle');
    if (btn) btn.title = t(collapsed ? 'sidebar.expand' : 'sidebar.collapse');
    relayoutGraphs();
    requestAnimationFrame(() => requestAnimationFrame(relayoutGraphs));
  });

  HeimdallNotifs?.init();
  initUserMenu();
  initSupportModal();
  HeimdallProfile?.bind();
  HeimdallNtfsExplorer?.bind();
  HeimdallIcons?.inject();
  HeimdallScanShowcase?.mount('graph-empty');
  HeimdallScanShowcase?.mount('lab-graph-empty', { lab: true });
  HeimdallGlowChart?.bind('glow-chart');
  HeimdallExpandingSearch?.mount('expanding-search-dock', {
    onSearch: applyGlobalSearch,
  });
  updateScanActionVisibility();

  $('theme-toggle')?.addEventListener('change', (e) => {
    applyTheme(e.target.checked ? 'dark' : 'light');
    persistUiPrefs();
  });

  document.querySelectorAll('.lang-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      applyLocale(btn.dataset.lang);
      persistUiPrefs();
    });
  });

  $('set-theme')?.addEventListener('change', (e) => {
    applyTheme(e.target.value);
    persistUiPrefs();
  });

  $('set-locale')?.addEventListener('change', (e) => {
    applyLocale(e.target.value);
    persistUiPrefs();
  });

  document.addEventListener('heimdall:locale', () => {
    refreshCtaLabels();
    rebuildTimeline();
    updateGlowChart();
    document.querySelector('.search-dock__input')?.setAttribute('placeholder', t('search.globalPh'));
    document.querySelector('.search-dock__fab')?.setAttribute('aria-label', t('search.globalPh'));
    document.querySelector('.search-dock__close')?.setAttribute('aria-label', t('search.close'));
    HeimdallIcons?.inject();
    HeimdallIcons?.inject($('graph-empty'));
    HeimdallIcons?.inject($('lab-graph-empty'));
    window.HeimdallAiChat?.refreshI18n();
    window.HeimdallAdvancedFilters?.refreshI18n();
  });

  $('btn-pick-mft').addEventListener('click', async () => {
    const d = parseJson(await callBridge('pick_file', 'mft'));
    if (d.path) {
      $('mft-path').value = d.path;
      syncMftPathDisplay();
    }
  });
  $('ntfs-pick-mft')?.addEventListener('click', async () => {
    const d = parseJson(await callBridge('pick_file', 'mft'));
    if (d.path) {
      $('mft-path').value = d.path;
      syncMftPathDisplay();
    }
  });
  $('ntfs-run-scan')?.addEventListener('click', () => runScan(false, { stayView: 'explorer' }));
  $('btn-pick-usn').addEventListener('click', async () => {
    const d = parseJson(await callBridge('pick_file', 'usn'));
    if (d.path) $('usn-path').value = d.path;
  });

  $('btn-scan').addEventListener('click', () => runScan(false));
  $('btn-lab')?.addEventListener('click', () => runScan(true));
  $('btn-new-scan')?.addEventListener('click', () => runScan(false));
  $('btn-new-lab')?.addEventListener('click', () => runScan(true));
  $('btn-lab-rescan')?.addEventListener('click', () => runScan(true));
  $('filter-text').addEventListener('input', () => {
    HeimdallExpandingSearch?.sync?.($('filter-text').value);
    renderGraph();
  });

  window.HeimdallAdvancedFilters?.mount('advanced-filters-root', {
    onChange: () => renderGraph(),
  });
  $('btn-view-graph').addEventListener('click', () => setDisplayMode('graph'));
  $('btn-view-table').addEventListener('click', () => setDisplayMode('table'));
  $('btn-export-json').addEventListener('click', () => exportReport('json'));
  $('btn-export-csv').addEventListener('click', () => exportReport('csv'));
  $('btn-export-html').addEventListener('click', () => exportReport('html'));
  $('link-export')?.addEventListener('click', (e) => { e.preventDefault(); exportReport('html'); });
  $('btn-save-settings').addEventListener('click', saveSettings);
  $('btn-test-ollama').addEventListener('click', testOllama);
  $('set-provider').addEventListener('change', syncProviderFields);
  mountAiChat();

  bindTimelineEvents();
  initGraphResizeWatch();

  window.addEventListener('resize', relayoutGraphs);

  setDisplayMode('graph');
}

function initBridge() {
  HeimdallI18n?.applyI18n();
  HeimdallIcons?.inject();
  window.HeimdallElasticSwitch?.bind();
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    window.bridge = bridge;
    bridge.taskFinished.connect(onTaskFinished);
    bridge.scanProgress.connect(onScanProgress);
    bindEvents();
    switchView('dashboard');
    updateGlowChart();
    loadSettings();
    updateOllamaStatus();
    callBridge('get_last_results').then((raw) => {
      const data = parseJson(raw);
      if (!data.empty && data.findings) {
        findings = data.findings;
        lastMeta = data.meta || {};
        planted = data.planted || [];
        window.findings = findings;
        window.lastMeta = lastMeta;
        updateStats(data.stats || {}, lastMeta);
        syncMftPathDisplay();
        updateGlowChart();
        rebuildTimeline();
        renderGraph();
        HeimdallNtfsExplorer?.render(findings, lastMeta);
      }
    }).catch(() => {});
  });
}

document.addEventListener('DOMContentLoaded', initBridge);
