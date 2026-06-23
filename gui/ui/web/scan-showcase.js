/**
 * Empty state animado — tags DFIR con efecto lupa (inspirado en MagnifiedBento / 21st.dev).
 */
(function (global) {
  const ROWS = [
    [
      { id: 'h1', label: 'H1 · $SI vs $FN' },
      { id: 'h2', label: 'H2 · Subsegundos' },
      { id: 'h3', label: 'H3 · RID / birth' },
      { id: 'mft', label: '$MFT parse' },
      { id: 'usn', label: 'USN Journal' },
    ],
    [
      { id: 'h4', label: 'H4 · created > mod' },
      { id: 'h5', label: 'H5 · Fuera de rango' },
      { id: 'h6', label: 'H6 · $FN truncado' },
      { id: 'si', label: '$STANDARD_INFO' },
      { id: 'fn', label: '$FILE_NAME' },
    ],
    [
      { id: 'lab', label: 'Modo laboratorio' },
      { id: 'ts', label: 'Timestomp T1070.006' },
      { id: 'corr', label: 'Corroboración' },
      { id: 'dfir', label: 'Línea temporal' },
      { id: 'hex', label: 'NTFS Explorer' },
    ],
  ];

  function t(key) {
    return global.HeimdallI18n?.t(key) ?? key;
  }

  function tagHtml(item, reveal) {
    const cls = reveal ? 'scan-tag scan-tag--reveal' : 'scan-tag';
    return `<span class="${cls}" data-tag="${item.id}">${item.label}</span>`;
  }

  function rowHtml(row, rowIndex, reveal) {
    const triple = [...row, ...row, ...row];
    const dir = rowIndex % 2 === 0 ? 'scan-marquee--left' : 'scan-marquee--right';
    return `
      <div class="scan-marquee ${dir}" style="--marquee-delay:${rowIndex * 0.4}s">
        ${triple.map((item) => tagHtml(item, reveal)).join('')}
      </div>`;
  }

  function mount(containerId, opts = {}) {
    const lab = Boolean(opts.lab);
    const el = document.getElementById(containerId);
    if (!el || el.dataset.showcaseMounted === '1') return;
    el.dataset.showcaseMounted = '1';

    el.innerHTML = `
      <div class="scan-showcase">
        <div class="scan-showcase__stage" id="scan-showcase-stage-${containerId}">
          <div class="scan-showcase__base">${ROWS.map((r, i) => rowHtml(r, i, false)).join('')}</div>
          <div class="scan-showcase__reveal" aria-hidden="true">${ROWS.map((r, i) => rowHtml(r, i, true)).join('')}</div>
          <div class="scan-showcase__lens" aria-hidden="true">
            <svg viewBox="0 0 512 512" aria-hidden="true"><path d="M332 332C260 404 142.4 404 69.6 332C-2.4 260-2.4 142.4 69.6 69.6C141.6-3.2 259.2-2.4 332 69.6C404.8 142.4 404.8 260 332 332ZM315.2 87.2C252 24 150.4 24 88 87.2C24.8 150.4 24.8 252 88 314.4C151.2 377.6 252.8 377.6 315.2 314.4C377.6 252 377.6 150.4 315.2 87.2Z" fill="#7A858C"/><path d="M484.1 428.8L373.8 318.5 318.4 373.9 428.7 484.2Z" fill="#333"/><path d="M471.7 441.2 361.3 330.9 330.8 361.5 441.1 471.8Z" fill="#575B5E"/></svg>
          </div>
          <div class="scan-showcase__fade scan-showcase__fade--l"></div>
          <div class="scan-showcase__fade scan-showcase__fade--r"></div>
        </div>
        <div class="scan-showcase__copy">
          <button type="button" class="scan-showcase__cta" data-showcase-action>
            <span class="scan-showcase__cta-icon" data-icon="${lab ? 'lab' : 'scan'}"></span>
            <span>
              <strong data-i18n="${lab ? 'cta.lab' : 'cta.scan'}">${lab ? 'Ejecutar laboratorio' : 'Escanear MFT'}</strong>
              <small data-i18n="${lab ? 'lab.emptySub' : 'scan.showcaseSub'}">${lab ? 'MFT sintético con casos plantados' : 'Compara $SI vs $FN · heurísticas H1–H6'}</small>
            </span>
          </button>
        </div>
      </div>`;

    global.HeimdallIcons?.inject(el);
    global.HeimdallI18n?.applyI18n?.(el);

    const stage = el.querySelector('.scan-showcase__stage');
    const lens = el.querySelector('.scan-showcase__lens');
    if (stage && lens) {
      stage.addEventListener('mousemove', (e) => {
        const rect = stage.getBoundingClientRect();
        const lensSize = lens.offsetWidth || 48;
        const half = lensSize / 2;
        const x = e.clientX - rect.left - half;
        const y = e.clientY - rect.top - half;
        lens.style.transform = `translate(${Math.max(4, Math.min(rect.width - lensSize - 4, x))}px, ${Math.max(4, Math.min(rect.height - lensSize - 4, y))}px)`;
        stage.style.setProperty('--lens-x', `${((e.clientX - rect.left) / rect.width) * 100}%`);
        stage.style.setProperty('--lens-y', `${((e.clientY - rect.top) / rect.height) * 100}%`);
      });
    }

    el.querySelector('[data-showcase-action]')?.addEventListener('click', () => {
      global.runScan?.(lab);
    });
  }

  global.HeimdallScanShowcase = { mount, ROWS };
})(window);
