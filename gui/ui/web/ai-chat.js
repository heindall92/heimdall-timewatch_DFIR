/**
 * Chat IA animado — equivalente vanilla de AnimatedAIChat (framer-motion / React).
 */
(function (global) {
  const MIN_H = 60;
  const MAX_H = 200;

  let root = null;
  let handlers = {};
  let state = {
    value: '',
    attachments: [],
    isBusy: false,
    showPalette: false,
    activeSuggestion: -1,
    inputFocused: false,
    reply: '',
  };

  function placeholderText() {
    return t('ai.analyzePh');
  }

  function isGeneratingText(text) {
    return text === t('ai.generating') || text === t('ai.thinking');
  }

  function hasReply() {
    return !!(state.reply && state.reply !== placeholderText() && !isGeneratingText(state.reply));
  }

  function hasContext() {
    return hasReply() || !!state.value.trim() || state.attachments.length > 0;
  }

  function clearContext() {
    if (state.isBusy) return;
    state.reply = '';
    state.value = '';
    state.attachments = [];
    state.showPalette = false;
    state.activeSuggestion = -1;
    const textarea = root?.querySelector('#ai-chat-textarea');
    if (textarea) {
      textarea.value = '';
      adjustHeight(textarea, true);
      textarea.focus();
    }
    syncUi();
  }

  async function runNewAnalysis() {
    if (state.isBusy) return;
    await runAnalyze();
  }

  function beginReply(pendingText) {
    state.reply = pendingText;
    syncUi();
  }

  function finishReply(text) {
    state.reply = text;
    state.isBusy = false;
    syncUi();
    root?.querySelector('#ai-result-card')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function t(key, vars) {
    if (handlers.translate) return handlers.translate(key, vars);
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function icon(name) {
    return global.HeimdallIcons?.html(name, 'ai-chat__ico') ?? '';
  }

  function commands() {
    return [
      { icon: 'scan', labelKey: 'ai.cmd.analyze', descKey: 'ai.cmd.analyzeDesc', prefix: '/analyze', action: 'analyze' },
      { icon: 'shield', labelKey: 'ai.cmd.heuristics', descKey: 'ai.cmd.heuristicsDesc', prefix: '/heuristics', prompt: t('ai.cmd.heuristicsPrompt') },
      { icon: 'score', labelKey: 'ai.cmd.critical', descKey: 'ai.cmd.criticalDesc', prefix: '/critical', prompt: t('ai.cmd.criticalPrompt') },
      { icon: 'calendar', labelKey: 'ai.cmd.timeline', descKey: 'ai.cmd.timelineDesc', prefix: '/timeline', prompt: t('ai.cmd.timelinePrompt') },
      { icon: 'sparkles', labelKey: 'ai.cmd.improve', descKey: 'ai.cmd.improveDesc', prefix: '/improve', prompt: t('ai.cmd.improvePrompt') },
    ];
  }

  function adjustHeight(textarea, reset) {
    if (!textarea) return;
    if (reset) {
      textarea.style.height = `${MIN_H}px`;
      return;
    }
    textarea.style.height = `${MIN_H}px`;
    const next = Math.max(MIN_H, Math.min(textarea.scrollHeight, MAX_H));
    textarea.style.height = `${next}px`;
  }

  function shellHtml() {
    return `
      <div class="ai-view">
        <div class="ai-view__blobs" aria-hidden="true">
          <span class="ai-view__blob ai-view__blob--a"></span>
          <span class="ai-view__blob ai-view__blob--b"></span>
          <span class="ai-view__blob ai-view__blob--c"></span>
        </div>
        <div class="ai-view__cursor-glow" id="ai-cursor-glow" hidden aria-hidden="true"></div>

        <div class="ai-view__inner">
          <header class="ai-view__head">
            <h1 class="ai-view__title" data-i18n="ai.heroTitle">${t('ai.heroTitle')}</h1>
            <p class="ai-view__lead" data-i18n="ai.heroLead">${t('ai.heroLead')}</p>
            <div class="ai-view__divider"></div>
          </header>

          <div class="ai-analyze-card glass-inset">
            <div class="ai-analyze-card__head">
              <div>
                <h2 data-i18n="ai.title">${t('ai.title')}</h2>
                <p class="ai-analyze-card__sub" data-i18n="ai.sub">${t('ai.sub')}</p>
              </div>
              <button type="button" class="btn-primary ai-analyze-card__btn" id="ai-btn-analyze">
                <span class="ai-chat__ico-wrap" data-icon="scan"></span>
                <span data-i18n="ai.analyze">${t('ai.analyze')}</span>
              </button>
            </div>
            <p class="ai-disclaimer" data-i18n="ai.disclaimer">${t('ai.disclaimer')}</p>
          </div>

          <div class="ai-composer glass-inset" id="ai-composer">
            <div class="ai-composer__body">
              <textarea
                id="ai-chat-textarea"
                class="ai-composer__input"
                rows="1"
                placeholder="${t('ai.chatPh')}"
                aria-label="${t('ai.chat')}"
              ></textarea>
            </div>

            <div class="ai-attachments" id="ai-attachments" hidden></div>

            <div class="ai-composer__foot">
              <div class="ai-composer__tools">
                <button type="button" class="ai-tool-btn" id="ai-btn-attach" title="${t('ai.attach')}">
                  <span data-icon="paperclip"></span>
                </button>
                <button type="button" class="ai-tool-btn" id="ai-btn-commands" data-command-button title="${t('ai.commands')}">
                  <span data-icon="command"></span>
                </button>
              </div>
              <button type="button" class="ai-send-btn" id="ai-btn-send" disabled>
                <span class="ai-send-btn__ico" data-icon="send"></span>
                <span data-i18n="ai.send">${t('ai.send')}</span>
              </button>
            </div>
          </div>

          <div class="ai-quick-chips" id="ai-quick-chips"></div>

          <div class="ai-result-card glass-inset" id="ai-result-card">
            <div class="ai-result-card__head">
              <h3 class="ai-result-card__title" data-i18n="ai.reply">${t('ai.reply')}</h3>
              <div class="ai-result-actions">
                <button type="button" class="btn-export ai-result-action" id="ai-btn-clear" hidden>
                  <span data-icon="close"></span>
                  <span data-i18n="ai.clearContext">${t('ai.clearContext')}</span>
                </button>
                <button type="button" class="btn-primary ai-result-action ai-result-action--primary" id="ai-btn-new-analysis">
                  <span data-icon="scan"></span>
                  <span data-i18n="ai.newAnalysis">${t('ai.newAnalysis')}</span>
                </button>
                <div class="ai-export-bar" id="ai-result-export" hidden>
                  <button type="button" class="btn-export ai-export-btn" data-export-kind="md">
                    <span data-icon="file"></span><span data-i18n="ai.exportMd">${t('ai.exportMd')}</span>
                  </button>
                  <button type="button" class="btn-export ai-export-btn" data-export-kind="html">
                    <span data-icon="export"></span><span data-i18n="ai.exportHtml">${t('ai.exportHtml')}</span>
                  </button>
                </div>
              </div>
            </div>
            <div class="ai-output glass-inset" id="ai-result-output">${state.reply || placeholderText()}</div>
          </div>
        </div>

        <div class="ai-palette-layer" id="ai-palette-layer" hidden role="listbox" aria-label="${t('ai.commands')}"></div>

        <div class="ai-thinking-toast" id="ai-thinking-toast" hidden role="status" aria-live="polite">
          <span class="ai-thinking-toast__badge">AI</span>
          <span class="ai-thinking-toast__text" data-i18n="ai.thinking">${t('ai.thinking')}</span>
          <span class="ai-typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </div>
      </div>
    `;
  }

  function visibleCommands() {
    const query = state.value.startsWith('/') && !state.value.includes(' ') ? state.value : '';
    return commands().filter((cmd) => !query || cmd.prefix.startsWith(query));
  }

  function renderPalette() {
    const layer = root?.querySelector('#ai-palette-layer');
    const view = root?.querySelector('.ai-view');
    if (!layer) return;

    if (!state.showPalette) {
      layer.hidden = true;
      layer.innerHTML = '';
      view?.classList.remove('ai-view--palette-open');
      return;
    }

    const visible = visibleCommands();
    if (state.activeSuggestion >= visible.length) state.activeSuggestion = visible.length - 1;
    if (state.activeSuggestion < 0 && visible.length) state.activeSuggestion = 0;

    view?.classList.add('ai-view--palette-open');
    layer.hidden = false;
    layer.innerHTML = `
      <div class="ai-palette">
        ${visible
          .map((cmd, index) => {
            const allIndex = commands().indexOf(cmd);
            const active = index === state.activeSuggestion ? ' is-active' : '';
            return `
              <button type="button" class="ai-palette__item${active}" data-cmd-index="${allIndex}" role="option">
                <span class="ai-palette__ico" data-icon="${cmd.icon}"></span>
                <span class="ai-palette__label">${t(cmd.labelKey)}</span>
                <span class="ai-palette__prefix">${cmd.prefix}</span>
              </button>
            `;
          })
          .join('')}
      </div>`;
    global.HeimdallIcons?.inject(layer);
    positionPalette();
  }

  function positionPalette() {
    const layer = root?.querySelector('#ai-palette-layer');
    const btn = root?.querySelector('#ai-btn-commands');
    if (!layer || !btn || layer.hidden) return;
    const rect = btn.getBoundingClientRect();
    const maxW = Math.min(360, window.innerWidth - 24);
    layer.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - maxW - 12))}px`;
    layer.style.top = `${rect.bottom + 8}px`;
    layer.style.width = `${maxW}px`;
  }

  function renderAttachments() {
    const wrap = root?.querySelector('#ai-attachments');
    if (!wrap) return;
    if (!state.attachments.length) {
      wrap.hidden = true;
      wrap.innerHTML = '';
      return;
    }
    wrap.hidden = false;
    wrap.innerHTML = state.attachments
      .map(
        (name, i) => `
        <span class="ai-attachment-chip">
          <span>${name}</span>
          <button type="button" class="ai-attachment-chip__x" data-remove-attach="${i}" aria-label="${t('ai.removeAttach')}">
            <span data-icon="close"></span>
          </button>
        </span>
      `,
      )
      .join('');
    global.HeimdallIcons?.inject(wrap);
  }

  function renderQuickChips() {
    const wrap = root?.querySelector('#ai-quick-chips');
    if (!wrap) return;
    wrap.innerHTML = commands()
      .map(
        (cmd, index) => `
        <button type="button" class="ai-quick-chip" data-cmd-index="${index}">
          <span data-icon="${cmd.icon}"></span>
          <span>${t(cmd.labelKey)}</span>
        </button>
      `,
      )
      .join('');
    global.HeimdallIcons?.inject(wrap);
  }

  function syncUi() {
    if (!root) return;
    const textarea = root.querySelector('#ai-chat-textarea');
    const sendBtn = root.querySelector('#ai-btn-send');
    const commandsBtn = root.querySelector('#ai-btn-commands');
    const resultOut = root.querySelector('#ai-result-output');
    const resultExport = root.querySelector('#ai-result-export');
    const clearBtn = root.querySelector('#ai-btn-clear');
    const newAnalysisBtn = root.querySelector('#ai-btn-new-analysis');
    const toast = root.querySelector('#ai-thinking-toast');
    const glow = root.querySelector('#ai-cursor-glow');
    const analyzeBtn = root.querySelector('#ai-btn-analyze');

    if (textarea && textarea.value !== state.value) textarea.value = state.value;
    if (sendBtn) {
      sendBtn.disabled = state.isBusy || !state.value.trim();
      sendBtn.classList.toggle('is-ready', !!state.value.trim() && !state.isBusy);
      sendBtn.querySelector('[data-icon]')?.setAttribute('data-icon', state.isBusy ? 'loader' : 'send');
      global.HeimdallIcons?.inject(sendBtn);
      if (state.isBusy) sendBtn.querySelector('.ai-send-btn__ico')?.classList.add('is-spinning');
      else sendBtn.querySelector('.ai-send-btn__ico')?.classList.remove('is-spinning');
    }
    if (commandsBtn) commandsBtn.classList.toggle('is-active', state.showPalette);
    if (resultOut) resultOut.textContent = state.reply || placeholderText();
    if (resultExport) resultExport.hidden = !hasReply();
    if (clearBtn) clearBtn.hidden = !hasContext();
    if (newAnalysisBtn) newAnalysisBtn.disabled = state.isBusy;
    if (clearBtn) clearBtn.disabled = state.isBusy;
    if (toast) toast.hidden = !state.isBusy;
    if (glow) glow.hidden = !state.inputFocused;
    if (analyzeBtn) analyzeBtn.disabled = state.isBusy;
    renderPalette();
    renderAttachments();
    global.HeimdallIcons?.inject(root);
  }

  function updatePaletteFromValue() {
    if (state.value.startsWith('/') && !state.value.includes(' ')) {
      state.showPalette = true;
      const visible = visibleCommands();
      const idx = visible.findIndex((cmd) => cmd.prefix.startsWith(state.value));
      state.activeSuggestion = idx >= 0 ? idx : (visible.length ? 0 : -1);
    } else if (!state.showPalette) {
      state.activeSuggestion = -1;
    }
  }

  function selectCommand(index) {
    const cmds = commands();
    const cmd = cmds[index];
    if (!cmd) return;
    state.value = `${cmd.prefix} `;
    state.showPalette = false;
    state.activeSuggestion = -1;
    const textarea = root?.querySelector('#ai-chat-textarea');
    if (textarea) {
      textarea.value = state.value;
      adjustHeight(textarea);
      textarea.focus();
    }
    syncUi();
  }

  async function runAnalyze() {
    if (!handlers.analyzeScan || state.isBusy) return;
    state.isBusy = true;
    beginReply(t('ai.generating'));
    try {
      finishReply(await handlers.analyzeScan());
    } catch (err) {
      finishReply(err?.message || String(err));
    }
  }

  async function runChat(message) {
    if (!handlers.sendChat || state.isBusy) return;
    state.isBusy = true;
    beginReply(t('ai.thinking'));
    try {
      finishReply(await handlers.sendChat(message));
    } catch (err) {
      finishReply(err?.message || String(err));
    }
  }

  function resolveOutgoingMessage(raw) {
    const trimmed = raw.trim();
    const cmds = commands();
    for (const cmd of cmds) {
      if (trimmed === cmd.prefix || trimmed.startsWith(`${cmd.prefix} `)) {
        if (cmd.action === 'analyze') return { type: 'analyze' };
        const tail = trimmed.slice(cmd.prefix.length).trim();
        return { type: 'chat', message: tail || cmd.prompt || trimmed };
      }
    }
    let message = trimmed;
    if (state.attachments.length) {
      message = `${message}\n\n[${t('ai.attachContext')}: ${state.attachments.join(', ')}]`;
    }
    return { type: 'chat', message };
  }

  async function runSend() {
    if (!handlers.sendChat || state.isBusy || !state.value.trim()) return;
    const outgoing = resolveOutgoingMessage(state.value);
    state.value = '';
    const textarea = root?.querySelector('#ai-chat-textarea');
    adjustHeight(textarea, true);
    syncUi();

    if (outgoing.type === 'analyze') {
      await runAnalyze();
      return;
    }

    state.attachments = [];
    await runChat(outgoing.message);
  }

  function bindEvents() {
    const textarea = root.querySelector('#ai-chat-textarea');
    const glow = root.querySelector('#ai-cursor-glow');

    root.querySelector('#ai-btn-analyze')?.addEventListener('click', runNewAnalysis);
    root.querySelector('#ai-btn-new-analysis')?.addEventListener('click', runNewAnalysis);
    root.querySelector('#ai-btn-clear')?.addEventListener('click', clearContext);
    root.querySelector('#ai-btn-send')?.addEventListener('click', runSend);

    root.querySelector('#ai-btn-attach')?.addEventListener('click', () => {
      const label = t('ai.scanContext');
      if (!state.attachments.includes(label)) {
        state.attachments.push(label);
        syncUi();
      }
    });

    root.querySelector('#ai-btn-commands')?.addEventListener('click', (e) => {
      e.stopPropagation();
      state.showPalette = !state.showPalette;
      if (state.showPalette) state.activeSuggestion = 0;
      syncUi();
    });

    root.querySelectorAll('.ai-export-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const kind = btn.dataset.exportKind || 'html';
        if (!hasReply() || !handlers.exportSummary) return;
        btn.disabled = true;
        try {
          await handlers.exportSummary(state.reply, kind);
        } finally {
          btn.disabled = false;
        }
      });
    });

    textarea?.addEventListener('input', () => {
      state.value = textarea.value;
      updatePaletteFromValue();
      adjustHeight(textarea);
      syncUi();
    });

    textarea?.addEventListener('focus', () => {
      state.inputFocused = true;
      syncUi();
    });

    textarea?.addEventListener('blur', () => {
      state.inputFocused = false;
      syncUi();
    });

    textarea?.addEventListener('keydown', (e) => {
      const visible = visibleCommands();
      if (state.showPalette && visible.length) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          state.activeSuggestion = state.activeSuggestion < visible.length - 1 ? state.activeSuggestion + 1 : 0;
          syncUi();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          state.activeSuggestion = state.activeSuggestion > 0 ? state.activeSuggestion - 1 : visible.length - 1;
          syncUi();
        } else if (e.key === 'Tab' || e.key === 'Enter') {
          if (state.activeSuggestion >= 0) {
            e.preventDefault();
            const picked = visible[state.activeSuggestion];
            const idx = commands().indexOf(picked);
            if (idx >= 0) selectCommand(idx);
          }
        } else if (e.key === 'Escape') {
          e.preventDefault();
          state.showPalette = false;
          syncUi();
        }
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runSend();
      }
    });

    root.addEventListener('click', (e) => {
      const cmdBtn = e.target.closest('[data-cmd-index]');
      if (cmdBtn) {
        selectCommand(Number(cmdBtn.dataset.cmdIndex));
        return;
      }
      const removeBtn = e.target.closest('[data-remove-attach]');
      if (removeBtn) {
        const idx = Number(removeBtn.dataset.removeAttach);
        state.attachments.splice(idx, 1);
        syncUi();
        return;
      }
      if (
        state.showPalette &&
        !e.target.closest('#ai-palette-layer') &&
        !e.target.closest('[data-command-button]')
      ) {
        state.showPalette = false;
        syncUi();
      }
    });

    document.addEventListener('mousedown', (e) => {
      if (
        state.showPalette &&
        !e.target.closest('#ai-palette-layer') &&
        !e.target.closest('[data-command-button]')
      ) {
        state.showPalette = false;
        syncUi();
      }
    });

    document.addEventListener('mousemove', (e) => {
      if (!state.inputFocused || !glow) return;
      glow.style.transform = `translate(${e.clientX - 320}px, ${e.clientY - 320}px)`;
    });

    window.addEventListener('resize', () => {
      adjustHeight(textarea);
      positionPalette();
    });
    window.addEventListener('scroll', positionPalette, true);
  }

  function mount(containerId, opts = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;
    handlers = opts;
    root = el;
    root.innerHTML = shellHtml();
    global.HeimdallIcons?.inject(root);
    renderQuickChips();
    bindEvents();
    syncUi();
  }

  function refreshI18n() {
    if (!root) return;
    root.querySelectorAll('[data-i18n]').forEach((node) => {
      const key = node.getAttribute('data-i18n');
      if (key) node.textContent = t(key);
    });
    const textarea = root.querySelector('#ai-chat-textarea');
    if (textarea) textarea.placeholder = t('ai.chatPh');
    renderQuickChips();
    syncUi();
  }

  global.HeimdallAiChat = { mount, refreshI18n, runAnalyze };
})(window);
