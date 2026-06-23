/**
 * Filtros avanzados estilo Linear — vanilla (sin React/shadcn).
 */
(function (global) {
  const LEVELS = ['CRÍTICO', 'ALTO', 'MEDIO', 'BAJO'];
  const HEURISTICS = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6'];
  const SCORE_PRESETS = ['70', '50', '25', '10'];
  const STATES = ['in_use', 'deleted', 'directory'];

  const TYPE_ICONS = {
    level: 'score',
    heuristic: 'shield',
    score: 'score',
    state: 'file',
  };

  let root = null;
  let filters = [];
  let openPopover = null;
  let onChange = () => {};
  let bound = false;

  function t(key, vars) {
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function uid() {
    return `f-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
  }

  function normLevel(level) {
    const map = { CRITICAL: 'CRÍTICO', HIGH: 'ALTO', MEDIUM: 'MEDIO', LOW: 'BAJO' };
    return map[level] || level || 'BAJO';
  }

  function operatorsFor(type, values) {
    const multi = values.length > 1;
    if (type === 'level' || type === 'state') {
      return multi ? ['is_any_of', 'is_not'] : ['is', 'is_not'];
    }
    if (type === 'heuristic') {
      return multi
        ? ['include_any_of', 'exclude_all_of']
        : ['include', 'do_not_include'];
    }
    if (type === 'score') return ['gte', 'lte'];
    return ['is'];
  }

  function operatorLabel(op) {
    return t(`advFilter.op.${op}`);
  }

  function typeLabel(type) {
    return t(`advFilter.type.${type}`);
  }

  function valueLabel(type, value) {
    if (type === 'state') return t(`advFilter.state.${value}`);
    if (type === 'score') return t('advFilter.scoreGte', { n: value });
    return value;
  }

  function optionsFor(type) {
    switch (type) {
      case 'level': return LEVELS.map((v) => ({ value: v, label: v }));
      case 'heuristic': return HEURISTICS.map((v) => ({ value: v, label: v }));
      case 'score': return SCORE_PRESETS.map((v) => ({ value: v, label: t('advFilter.scoreGte', { n: v }) }));
      case 'state':
        return STATES.map((v) => ({ value: v, label: t(`advFilter.state.${v}`) }));
      default: return [];
    }
  }

  function defaultOperator(type) {
    return operatorsFor(type, [])[0];
  }

  function matchesFilter(f, filter) {
    if (!filter.value?.length) return true;
    switch (filter.type) {
      case 'level': {
        const lv = normLevel(f.suspicion_level);
        if (filter.operator === 'is') return filter.value.includes(lv);
        if (filter.operator === 'is_not') return !filter.value.includes(lv);
        if (filter.operator === 'is_any_of') return filter.value.includes(lv);
        return true;
      }
      case 'heuristic': {
        const codes = (f.findings || []).map((x) => x.code).filter(Boolean);
        const hit = (v) => codes.includes(v);
        if (filter.operator === 'include') return filter.value.some(hit);
        if (filter.operator === 'do_not_include') return !filter.value.some(hit);
        if (filter.operator === 'include_any_of') return filter.value.some(hit);
        if (filter.operator === 'exclude_all_of') return !filter.value.some(hit);
        return true;
      }
      case 'score': {
        const score = f.score ?? 0;
        const n = Number(filter.value[0] || 0);
        if (filter.operator === 'gte') return score >= n;
        if (filter.operator === 'lte') return score <= n;
        return true;
      }
      case 'state': {
        const tags = [];
        if (f.is_directory) tags.push('directory');
        else if (f.in_use) tags.push('in_use');
        else tags.push('deleted');
        if (filter.operator === 'is') return filter.value.some((v) => tags.includes(v));
        if (filter.operator === 'is_not') return !filter.value.some((v) => tags.includes(v));
        if (filter.operator === 'is_any_of') return filter.value.some((v) => tags.includes(v));
        return true;
      }
      default:
        return true;
    }
  }

  function applyToFindings(items) {
    const active = filters.filter((f) => f.value?.length);
    if (!active.length) return items;
    return items.filter((f) => active.every((filter) => matchesFilter(f, filter)));
  }

  function closePopover() {
    openPopover = null;
    render();
  }

  function filterChipHtml(filter) {
    const values = filter.value || [];
    const valueText = filter.type === 'score' && values.length
      ? (filter.operator === 'lte'
        ? t('advFilter.scoreLte', { n: values[0] })
        : t('advFilter.scoreGte', { n: values[0] }))
      : values.length === 1
        ? valueLabel(filter.type, values[0])
        : t('advFilter.selected', { n: values.length });

    const icons = filter.type !== 'score'
      ? values.slice(0, 3).map((v) => {
        if (filter.type === 'level') {
          return `<span class="adv-filter__lv adv-filter__lv--${v.toLowerCase().replace('í', 'i')}"></span>`;
        }
        if (filter.type === 'heuristic') {
          return `<span class="adv-filter__tag-dot"></span>`;
        }
        return '';
      }).join('')
      : '';

    return `
      <div class="adv-filter" data-filter-id="${filter.id}">
        <span class="adv-filter__type">
          <span class="adv-filter__type-ico" data-icon="${TYPE_ICONS[filter.type] || 'filter'}"></span>
          ${typeLabel(filter.type)}
        </span>
        <button type="button" class="adv-filter__op" data-action="op" data-id="${filter.id}">${operatorLabel(filter.operator)}</button>
        <button type="button" class="adv-filter__val" data-action="val" data-id="${filter.id}">
          ${icons ? `<span class="adv-filter__val-icons">${icons}</span>` : ''}
          <span>${valueText}</span>
        </button>
        <button type="button" class="adv-filter__remove" data-action="remove" data-id="${filter.id}" aria-label="${t('advFilter.remove')}">
          <span data-icon="close"></span>
        </button>
      </div>`;
  }

  function popoverHtml(kind, filterId) {
    const filter = filters.find((f) => f.id === filterId);
    if (!filter) return '';

    if (kind === 'add-type') {
      const groups = [
        ['level', 'heuristic', 'score', 'state'],
      ];
      return `
        <div class="adv-popover adv-popover--add" data-popover="add-type">
          <p class="adv-popover__title">${t('advFilter.addFilter')}</p>
          ${groups.map((group) => `
            <div class="adv-popover__group">
              ${group.map((type) => `
                <button type="button" class="adv-popover__item" data-action="pick-type" data-type="${type}">
                  <span data-icon="${TYPE_ICONS[type] || 'filter'}"></span>
                  <span>${typeLabel(type)}</span>
                </button>
              `).join('')}
            </div>
          `).join('')}
        </div>`;
    }

    if (kind === 'op') {
      const ops = operatorsFor(filter.type, filter.value);
      return `
        <div class="adv-popover" data-popover="op" data-id="${filter.id}">
          ${ops.map((op) => `
            <button type="button" class="adv-popover__item${filter.operator === op ? ' is-active' : ''}" data-action="set-op" data-id="${filter.id}" data-op="${op}">
              ${operatorLabel(op)}
              ${filter.operator === op ? '<span data-icon="check"></span>' : ''}
            </button>
          `).join('')}
        </div>`;
    }

    if (kind === 'val') {
      const opts = optionsFor(filter.type);
      const q = openPopover?.query || '';
      const selected = new Set(filter.value);
      const filtered = opts.filter((o) => !q || o.label.toLowerCase().includes(q.toLowerCase()));
      const isScore = filter.type === 'score';

      return `
        <div class="adv-popover adv-popover--val" data-popover="val" data-id="${filter.id}">
          <input type="search" class="adv-popover__search" placeholder="${typeLabel(filter.type)}" value="${q}" data-action="search-val" />
          <div class="adv-popover__scroll adv-popover__animated">
            ${selected.size ? `
              <div class="adv-popover__section">
                ${[...selected].map((v) => {
                  const opt = opts.find((o) => o.value === v);
                  return `
                    <button type="button" class="adv-popover__item is-checked" data-action="toggle-val" data-id="${filter.id}" data-value="${v}">
                      <span class="adv-popover__check is-on"></span>
                      <span>${opt?.label || v}</span>
                    </button>`;
                }).join('')}
              </div>
            ` : ''}
            ${filtered.filter((o) => !selected.has(o.value)).length ? `
              <div class="adv-popover__section">
                ${filtered.filter((o) => !selected.has(o.value)).map((o) => `
                  <button type="button" class="adv-popover__item" data-action="toggle-val" data-id="${filter.id}" data-value="${o.value}">
                    <span class="adv-popover__check"></span>
                    <span>${o.label}</span>
                  </button>
                `).join('')}
              </div>
            ` : `<p class="adv-popover__empty">${t('advFilter.noResults')}</p>`}
          </div>
        </div>`;
    }

    return '';
  }

  function render() {
    if (!root) return;
    root.innerHTML = `
      <div class="adv-filters">
        <div class="adv-filters__bar">
          ${filters.filter((f) => f.value?.length).map(filterChipHtml).join('')}
          <div class="adv-filters__add-wrap">
            <button type="button" class="adv-filters__add" data-action="add" aria-expanded="${openPopover?.kind === 'add-type' ? 'true' : 'false'}">
              <span data-icon="filter"></span>
              <span>${t('advFilter.add')}</span>
            </button>
            ${openPopover?.kind === 'add-type' ? popoverHtml('add-type') : ''}
          </div>
        </div>
        ${openPopover?.kind === 'op' || openPopover?.kind === 'val'
          ? `<div class="adv-filters__float">${popoverHtml(openPopover.kind, openPopover.filterId)}</div>`
          : ''}
      </div>
    `;

    global.HeimdallIcons?.inject(root);

    if (openPopover?.kind === 'val') {
      const input = root.querySelector('[data-action="search-val"]');
      input?.focus();
      observePopoverHeight(root.querySelector('.adv-popover__animated'));
    }
  }

  function observePopoverHeight(el) {
    if (!el || typeof ResizeObserver === 'undefined') return;
    el.style.height = 'auto';
    const h = el.scrollHeight;
    el.style.height = `${h}px`;
    const ro = new ResizeObserver(() => {
      el.style.height = `${el.scrollHeight}px`;
    });
    ro.observe(el);
    el._ro = ro;
  }

  function emitChange() {
    onChange(filters);
    render();
  }

  function addFilter(type) {
    const f = {
      id: uid(),
      type,
      operator: defaultOperator(type),
      value: type === 'score' ? [] : [],
    };
    filters.push(f);
    openPopover = { kind: 'val', filterId: f.id, query: '' };
    emitChange();
  }

  function bind() {
    if (bound || !root) return;
    bound = true;

    document.addEventListener('mousedown', (e) => {
      if (!root?.contains(e.target)) closePopover();
    });

    root.addEventListener('click', (e) => {
      const addBtn = e.target.closest('[data-action="add"]');
      if (addBtn) {
        openPopover = openPopover?.kind === 'add-type' ? null : { kind: 'add-type' };
        render();
        return;
      }

      const pickType = e.target.closest('[data-action="pick-type"]');
      if (pickType) {
        addFilter(pickType.dataset.type);
        return;
      }

      const opBtn = e.target.closest('[data-action="op"]');
      if (opBtn) {
        const rect = opBtn.getBoundingClientRect();
        openPopover = { kind: 'op', filterId: opBtn.dataset.id, anchor: rect };
        render();
        positionFloat(root, opBtn);
        return;
      }

      const valBtn = e.target.closest('[data-action="val"]');
      if (valBtn) {
        openPopover = { kind: 'val', filterId: valBtn.dataset.id, query: '' };
        render();
        positionFloat(root, valBtn);
        return;
      }

      const setOp = e.target.closest('[data-action="set-op"]');
      if (setOp) {
        const f = filters.find((x) => x.id === setOp.dataset.id);
        if (f) {
          f.operator = setOp.dataset.op;
          if (f.type === 'score') f.value = f.value.slice(0, 1);
        }
        closePopover();
        emitChange();
        return;
      }

      const toggleVal = e.target.closest('[data-action="toggle-val"]');
      if (toggleVal) {
        const f = filters.find((x) => x.id === toggleVal.dataset.id);
        const v = toggleVal.dataset.value;
        if (!f) return;
        if (f.type === 'score') {
          f.value = f.value.includes(v) ? [] : [v];
          closePopover();
        } else if (f.value.includes(v)) {
          f.value = f.value.filter((x) => x !== v);
        } else {
          f.value = [...f.value, v];
        }
        const allowed = operatorsFor(f.type, f.value);
        if (!allowed.includes(f.operator)) f.operator = allowed[0];
        emitChange();
        if (f.type !== 'score') {
          openPopover = { kind: 'val', filterId: f.id, query: openPopover?.query || '' };
          render();
          positionFloat(root, root.querySelector(`[data-action="val"][data-id="${f.id}"]`));
        }
        return;
      }

      const removeBtn = e.target.closest('[data-action="remove"]');
      if (removeBtn) {
        filters = filters.filter((x) => x.id !== removeBtn.dataset.id);
        closePopover();
        emitChange();
      }
    });

    root.addEventListener('input', (e) => {
      if (e.target.matches('[data-action="search-val"]')) {
        openPopover = { ...openPopover, query: e.target.value };
        render();
        const valBtn = root.querySelector(`[data-action="val"][data-id="${openPopover.filterId}"]`);
        positionFloat(root, valBtn);
        root.querySelector('[data-action="search-val"]')?.focus();
      }
    });
  }

  function positionFloat(container, anchorEl) {
    const float = container.querySelector('.adv-filters__float');
    if (!float || !anchorEl) return;
    const wrap = container.getBoundingClientRect();
    const rect = anchorEl.getBoundingClientRect();
    float.style.left = `${rect.left - wrap.left}px`;
    float.style.top = `${rect.bottom - wrap.top + 6}px`;
  }

  function mount(containerId, opts = {}) {
    root = document.getElementById(containerId);
    if (!root) return;
    onChange = opts.onChange || (() => {});
    if (opts.initial) filters = opts.initial;
    bind();
    render();
  }

  function getFilters() {
    return filters.slice();
  }

  function setFilters(next) {
    filters = next.slice();
    render();
  }

  function clearFilters() {
    filters = [];
    closePopover();
    emitChange();
  }

  function activeCount() {
    return filters.filter((f) => f.value?.length).length;
  }

  function refreshI18n() {
    render();
  }

  global.HeimdallAdvancedFilters = {
    mount,
    applyToFindings,
    getFilters,
    setFilters,
    clearFilters,
    activeCount,
    refreshI18n,
  };
})(window);
