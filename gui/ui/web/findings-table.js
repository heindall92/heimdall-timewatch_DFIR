/**
 * Tabla interactiva de hallazgos — filas expandibles y animaciones (vanilla).
 */
(function (global) {
  const LEVELS = ['CRÍTICO', 'ALTO', 'MEDIO', 'BAJO'];
  const LEVEL_ALIASES = {
    CRITICAL: 'CRÍTICO',
    HIGH: 'ALTO',
    MEDIUM: 'MEDIO',
    LOW: 'BAJO',
  };

  let expandedIdx = null;
  let bound = false;

  function t(key, vars) {
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function normLevel(level) {
    return LEVEL_ALIASES[level] || level || 'BAJO';
  }

  function levelKey(level) {
    return normLevel(level).toLowerCase().replace('í', 'i');
  }

  function badgeHtml(level) {
    const lv = normLevel(level);
    return `<span class="findings-badge findings-badge--${levelKey(lv)}">${esc(lv)}</span>`;
  }

  function detailHtml(f) {
    const rows = (f.findings || []).map((item) => `
      <div class="findings-detail-block">
        <div class="findings-detail-block__head">
          <span class="findings-detail-code">${esc(item.code || '—')}</span>
          ${item.confidence ? `<span class="findings-detail-conf">${esc(item.confidence)}</span>` : ''}
        </div>
        <p class="findings-detail-title">${esc(item.title || '')}</p>
        ${item.detail ? `<pre class="findings-detail-text">${esc(item.detail)}</pre>` : ''}
        ${item.false_positive ? `<p class="findings-detail-fp">${esc(item.false_positive)}</p>` : ''}
      </div>`).join('');

    const tags = (f.findings || []).map((item) => item.code).filter(Boolean);

    return `
      <div class="findings-detail-inner">
        <div class="findings-detail-grid">
          <div>
            <p class="findings-detail-label">${t('table.mft')}</p>
            <p class="findings-detail-value mono">0x${f.record_number.toString(16).padStart(4, '0').toUpperCase()}</p>
          </div>
          <div>
            <p class="findings-detail-label">${t('table.score')}</p>
            <p class="findings-detail-value mono">${f.score ?? 0}</p>
          </div>
          <div>
            <p class="findings-detail-label">${t('table.status')}</p>
            <p class="findings-detail-value">${f.is_directory ? 'DIR' : 'FILE'} · ${f.in_use ? t('table.inUse') : t('table.deleted')}</p>
          </div>
        </div>
        ${rows || `<p class="findings-detail-empty">${t('table.noHeuristics')}</p>`}
        ${tags.length ? `
          <div class="findings-detail-tags">
            <p class="findings-detail-label">${t('table.heuristics')}</p>
            <div class="findings-tag-list">${tags.map((tag) => `<span class="findings-tag">${esc(tag)}</span>`).join('')}</div>
          </div>` : ''}
      </div>`;
  }

  function rowHtml(f, realIndex, selected, expanded, stagger) {
    const name = f.filename || `<sin nombre #${f.record_number}>`;
    const mft = `0x${f.record_number.toString(16).padStart(4, '0').toUpperCase()}`;
    const codes = (f.findings || []).slice(0, 2).map((x) => x.code).filter(Boolean).join(' · ');

    return `
      <article class="findings-row${selected ? ' is-selected' : ''}${expanded ? ' is-expanded' : ''}"
        data-idx="${realIndex}" style="--row-delay:${stagger}s">
        <button type="button" class="findings-row__head" aria-expanded="${expanded}">
          <span class="findings-row__chev" data-icon="chevronDown" aria-hidden="true"></span>
          ${badgeHtml(f.suspicion_level)}
          <span class="findings-row__score mono">${f.score ?? 0}</span>
          <span class="findings-row__name" title="${esc(name)}">${esc(name)}</span>
          ${codes ? `<span class="findings-row__codes mono">${esc(codes)}</span>` : ''}
          <span class="findings-row__mft mono">${mft}</span>
        </button>
        <div class="findings-row__detail" ${expanded ? '' : 'hidden'}>
          ${detailHtml(f)}
        </div>
      </article>`;
  }

  function shellHtml() {
    return `
      <div class="findings-table">
        <header class="findings-table__header">
          <div class="findings-table__meta">
            <span class="findings-table__count" id="findings-table-count"></span>
          </div>
        </header>
        <div class="findings-table__main">
          <div class="findings-table__list" id="findings-table-list" role="list"></div>
        </div>
      </div>`;
  }

  function bind(root) {
    if (bound) return;
    bound = true;

    root.addEventListener('click', (e) => {
      const head = e.target.closest('.findings-row__head');
      if (head) {
        const row = head.closest('.findings-row');
        const idx = Number(row?.dataset.idx);
        if (Number.isNaN(idx)) return;
        const state = global.__findingsTableState || {};
        expandedIdx = expandedIdx === idx ? null : idx;
        state.onSelect?.(idx);
        render(root, state);
      }
    });
  }

  function render(containerId, options) {
    const mount = typeof containerId === 'string' ? document.getElementById(containerId) : containerId;
    if (!mount) return;

    if (!mount.dataset.mounted) {
      mount.innerHTML = shellHtml();
      mount.dataset.mounted = '1';
      bind(mount);
    }

    const {
      items = [],
      allItems = items,
      selectedIndex = -1,
      onSelect = () => {},
    } = options || {};

    global.__findingsTableState = { items: allItems, selectedIndex, onSelect };

    const list = mount.querySelector('#findings-table-list');
    const countEl = mount.querySelector('#findings-table-count');

    if (countEl) {
      countEl.textContent = t('table.count', { shown: items.length, total: allItems.length });
    }

    if (!items.length) {
      list.innerHTML = `<p class="findings-table__empty">${allItems.length ? t('table.noMatch') : t('table.empty')}</p>`;
      global.HeimdallIcons?.inject(mount);
      return;
    }

    list.innerHTML = items.map((f, i) => {
      const realIndex = options.resolveIndex ? options.resolveIndex(f) : i;
      return rowHtml(
        f,
        realIndex,
        realIndex === selectedIndex,
        expandedIdx === realIndex,
        i * 0.03,
      );
    }).join('');

    global.HeimdallIcons?.inject(mount);
    global.HeimdallI18n?.applyI18n?.(mount);
  }

  global.HeimdallFindingsTable = { render };
})(window);
