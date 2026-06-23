/**
 * ExpandingSearchDock — barra de búsqueda expandible (inspirado en 21st.dev / framer-motion).
 */
(function (global) {
  function t(key) {
    return global.HeimdallI18n?.t(key) ?? key;
  }

  function mount(containerId, opts = {}) {
    const root = document.getElementById(containerId);
    if (!root || root.dataset.searchMounted === '1') return;
    root.dataset.searchMounted = '1';

    const placeholder = opts.placeholder ?? t('search.globalPh');
    let expanded = false;

    root.className = 'search-dock';
    root.innerHTML = `
      <button type="button" class="search-dock__fab glass-inset" aria-label="${placeholder}" aria-expanded="false">
        <svg class="search-dock__ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4" stroke-linecap="round"/>
        </svg>
      </button>
      <form class="search-dock__panel" role="search">
        <div class="search-dock__inner glass-inset">
          <svg class="search-dock__ico search-dock__ico--sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4" stroke-linecap="round"/>
          </svg>
          <input type="search" class="search-dock__input" autocomplete="off" spellcheck="false" placeholder="${placeholder}" />
          <button type="button" class="search-dock__close" aria-label="${t('search.close')}">
            <svg class="search-dock__ico search-dock__ico--xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      </form>`;

    const fab = root.querySelector('.search-dock__fab');
    const form = root.querySelector('.search-dock__panel');
    const input = root.querySelector('.search-dock__input');
    const closeBtn = root.querySelector('.search-dock__close');

    function setExpanded(next) {
      expanded = next;
      root.classList.toggle('is-expanded', expanded);
      fab.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      if (expanded) {
        requestAnimationFrame(() => {
          input.focus();
          input.select();
        });
      }
    }

    function applyQuery(raw, { collapse = false } = {}) {
      const q = (raw ?? input.value ?? '').trim();
      input.value = q;
      opts.onSearch?.(q);
      if (collapse) setExpanded(false);
    }

    function collapse() {
      input.value = '';
      applyQuery('', { collapse: true });
    }

    fab.addEventListener('click', () => setExpanded(true));
    closeBtn.addEventListener('click', collapse);

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      applyQuery(input.value, { collapse: false });
    });

    input.addEventListener('input', () => {
      applyQuery(input.value, { collapse: false });
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        collapse();
      }
    });

    document.addEventListener('click', (e) => {
      if (!expanded) return;
      if (root.contains(e.target)) return;
      setExpanded(false);
    });

    global.HeimdallExpandingSearch = global.HeimdallExpandingSearch || {};
    global.HeimdallExpandingSearch.sync = (value) => {
      if (input && document.activeElement !== input) {
        input.value = value ?? '';
      }
    };
    global.HeimdallExpandingSearch.expand = () => setExpanded(true);
    global.HeimdallExpandingSearch.collapse = collapse;
  }

  global.HeimdallExpandingSearch = { mount };
})(window);
