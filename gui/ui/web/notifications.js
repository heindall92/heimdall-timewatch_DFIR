/* Heimdall — notificaciones glass + parallax (tema claro/oscuro) */
(function (global) {
  let items = [];
  let unread = 0;
  let panelOpen = false;

  function t(key, vars) {
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function $(id) { return document.getElementById(id); }

  function updateBadge() {
    const badge = $('notif-count');
    if (!badge) return;
    if (unread > 0) {
      badge.hidden = false;
      badge.textContent = unread > 99 ? '99+' : String(unread);
    } else {
      badge.hidden = true;
    }
  }

  function push(item) {
    items.unshift({
      id: `n-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      read: false,
      time: new Date(),
      ...item,
    });
    if (items.length > 40) items.length = 40;
    unread += 1;
    updateBadge();
    renderPanel();
  }

  function pushScanResult(result) {
    const stats = result.stats || {};
    const flagged = stats.files_flagged ?? 0;
    const crit = stats.critical ?? 0;
    const high = stats.high ?? 0;
    const analyzed = stats.files_analyzed ?? stats.files_flagged ?? 0;
    const file = (result.meta?.mft_file || '').split(/[/\\]/).pop() || 'MFT';

    push({
      kind: 'scan',
      tone: 'blue',
      icon: 'scan',
      title: t('notif.scanDone'),
      desc: t('notif.scanDesc', { file, n: flagged, analyzed }),
      meta: `${flagged}`,
      action: 'dashboard',
    });

    if (crit > 0) {
      push({
        kind: 'crit',
        tone: 'red',
        icon: 'shield',
        title: t('notif.critTitle'),
        desc: t('notif.critDesc', { n: crit }),
        meta: String(crit),
        action: 'dashboard',
        filter: 'CRÍTICO',
      });
    }
    if (high > 0) {
      push({
        kind: 'high',
        tone: 'amber',
        icon: 'filter',
        title: t('notif.highTitle'),
        desc: t('notif.highDesc', { n: high }),
        meta: String(high),
        action: 'dashboard',
        filter: 'ALTO',
      });
    }
  }

  function cardHtml(n, i) {
    const tone = n.tone || 'blue';
    return `
      <article class="notif-card notif-card--${tone}" data-notif-id="${n.id}" data-notif-i="${i}"
        data-action="${n.action || ''}" data-filter="${n.filter || ''}" style="--parallax:${i * 0.04}">
        <div class="notif-card__icon"><span class="ico" data-icon="${n.icon || 'shield'}"></span></div>
        <div class="notif-card__body">
          <h3 class="notif-card__title">${escapeHtml(n.title)}</h3>
          <p class="notif-card__desc">${escapeHtml(n.desc)}</p>
        </div>
        <span class="notif-card__meta">${escapeHtml(n.meta || '')}</span>
      </article>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderPanel() {
    const list = $('notif-list');
    if (!list) return;
    const visible = items.filter((n) => !n.read);
    if (!visible.length) {
      list.innerHTML = `<p class="notif-empty">${t('notif.empty')}</p>`;
      return;
    }
    list.innerHTML = visible.map((n, i) => cardHtml(n, i)).join('');
    global.HeimdallIcons?.inject(list);
    list.querySelectorAll('.notif-card').forEach((el) => {
      el.addEventListener('click', () => onCardClick(el));
    });
    bindParallax();
  }

  function onCardClick(el) {
    const id = el.dataset.notifId;
    const item = items.find((x) => x.id === id);
    const action = item?.action || el.dataset.action;
    const filter = item?.filter || el.dataset.filter;
    if (item) {
      const idx = items.indexOf(item);
      if (idx >= 0) items.splice(idx, 1);
    }
    unread = items.filter((x) => !x.read).length;
    updateBadge();
    renderPanel();
    closePanel();
    if (action && global.switchView) global.switchView(action);
    if (filter && global.applySidebarFilter) global.applySidebarFilter(filter);
  }

  function bindParallax() {
    const scroll = $('notif-list');
    if (!scroll) return;
    const onScroll = () => {
      const st = scroll.scrollTop;
      scroll.querySelectorAll('.notif-card').forEach((card) => {
        const i = Number(card.dataset.notifI) || 0;
        const offset = st * (0.015 + i * 0.008);
        card.style.transform = `translateY(${-offset * 0.35}px)`;
      });
    };
    scroll.removeEventListener('scroll', scroll._parallax);
    scroll._parallax = onScroll;
    scroll.addEventListener('scroll', onScroll, { passive: true });
  }

  function setPanelOpen(open) {
    panelOpen = open;
    const panel = $('notif-panel');
    const backdrop = $('notif-backdrop');
    const btn = $('btn-notifs');
    if (panel) panel.hidden = !open;
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (backdrop) {
      backdrop.hidden = !open;
      backdrop.classList.toggle('is-visible', open);
    }
    if (open) {
      renderPanel();
      requestAnimationFrame(bindParallax);
    }
  }

  function closePanel() { setPanelOpen(false); }
  function togglePanel() { setPanelOpen(!panelOpen); }

  function markAllRead() {
    items = [];
    unread = 0;
    updateBadge();
    renderPanel();
  }

  function init() {
    $('btn-notifs')?.addEventListener('click', (e) => {
      e.stopPropagation();
      togglePanel();
    });
    $('notif-mark-read')?.addEventListener('click', (e) => {
      e.stopPropagation();
      markAllRead();
    });
    $('notif-view-all')?.addEventListener('click', (e) => {
      e.stopPropagation();
      closePanel();
      global.switchView?.('dashboard');
    });
    $('notif-panel')?.addEventListener('click', (e) => e.stopPropagation());
    $('notif-backdrop')?.addEventListener('click', closePanel);
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#notif-wrap') && !e.target.closest('#notif-backdrop')) {
        closePanel();
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closePanel();
    });
    updateBadge();
  }

  global.HeimdallNotifs = { init, push, pushScanResult, closePanel, markAllRead };
})(window);
