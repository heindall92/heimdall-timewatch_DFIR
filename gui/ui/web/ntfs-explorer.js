/* NTFS Explorer — vista de tres paneles */
(function (global) {
  let selectedIdx = -1;

  function t(key, vars) {
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function mftEntry(f) {
    if (!f) return null;
    if (f.record_number != null) return f.record_number;
    if (f.mft_entry != null) return f.mft_entry;
    if (f.entry != null) return f.entry;
    return null;
  }

  function parentLabel(f) {
    if (f.parent_ref != null) {
      return `MFT #${f.parent_ref}`;
    }
    const p = f.parent_path || f.path?.replace(/[/\\][^/\\]+$/, '') || '—';
    return p.length > 28 ? '…' + p.slice(-26) : p;
  }

  function formatSize(f) {
    if (f.is_directory) return '—';
    const n = f.file_size ?? f.size ?? 0;
    if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
    if (n >= 1024) return `${Math.round(n / 1024)} KB`;
    return n > 0 ? `${n} B` : '—';
  }

  function splitPath(raw) {
    return String(raw || '').replace(/\\/g, '/').split('/').filter(Boolean);
  }

  function pathSegments(mftPath) {
    const parts = splitPath(mftPath);
    if (!parts.length) return [];
    const last = parts[parts.length - 1];
    const isFile = last.includes('.') || last.toLowerCase().includes('$mft');
    return isFile ? parts.slice(0, -1) : parts;
  }

  function mftFileName(mftPath) {
    const parts = splitPath(mftPath);
    if (!parts.length) return '$MFT';
    return parts[parts.length - 1] || '$MFT';
  }

  function volumeRootLabel(mftPath, meta) {
    const parts = pathSegments(mftPath);
    if (meta?.mode === 'laboratorio') {
      const labDir = parts.find((p) => p.startsWith('heimdall_lab_')) || parts[parts.length - 1] || 'Lab';
      return `${labDir} · NTFS sintético`;
    }
    const drive = parts[0] || '';
    if (/^[A-Za-z]:$/.test(drive)) return `${drive}\\ (NTFS)`;
    if (/^[A-Za-z]:/.test(drive)) return `${drive.charAt(0)}:\\ (NTFS)`;
    return `${parts[0] || 'Volume'} (NTFS)`;
  }

  function inferPathParts(f) {
    const raw = f.path || f.full_path || f.filepath || '';
    if (raw) return splitPath(raw).filter((p) => p && !p.includes('.'));
    const name = f.filename || '';
    if (/[/\\]/.test(name)) return splitPath(name).slice(0, -1);
    return [];
  }

  function folderSegments(mftPath) {
    let segs = pathSegments(mftPath);
    if (segs.length && /^[A-Za-z]:?$/.test(segs[0])) segs = segs.slice(1);
    return segs;
  }

  function fileExtKind(name) {
    const ext = String(name || '').split('.').pop()?.toLowerCase() || '';
    const map = {
      exe: 'exe', dll: 'dll', sys: 'sys', dat: 'dat', bin: 'bin',
      json: 'json', csv: 'csv', html: 'html', mft: 'mft',
    };
    return map[ext] || 'file';
  }

  function treeItem(name, depth, opts = {}) {
    const { root, warn, file, mono, mft } = opts;
    const cls = ['ntfs-tree-item'];
    if (root) cls.push('ntfs-tree-item--root');
    if (warn) cls.push('ntfs-tree-item--warn');
    if (file) {
      cls.push('ntfs-tree-item--file');
      cls.push(`ntfs-tree-item--ext-${fileExtKind(name)}`);
    } else if (!mft) {
      cls.push('ntfs-tree-item--folder');
    }
    if (mft) cls.push('ntfs-tree-item--mft');
    const icon = mft ? 'mft' : file ? 'file' : 'folder';
    const pad = 10 + depth * 14;
    return `
      <div class="${cls.join(' ')}" style="padding-left:${pad}px" title="${esc(name)}">
        <span class="ico sm ntfs-tree-ico" data-icon="${icon}"></span>
        <span class="${mono ? 'mono' : ''}">${esc(name)}</span>
      </div>`;
  }

  function buildTree(findings, mftPath, meta) {
    const path = mftPath || meta?.mft_file || '';
    const segments = folderSegments(path);
    const mftName = mftFileName(path);
    const rows = [];

    rows.push(treeItem(volumeRootLabel(path, meta), 0, { root: true }));

    segments.forEach((seg, i) => {
      rows.push(treeItem(seg, i + 1));
    });

    const mftDepth = segments.length + 1;
    rows.push(treeItem(
      `${mftName} (${findings.length} ${findings.length === 1 ? 'entry' : 'entries'})`,
      mftDepth,
      { mft: true, mono: true },
    ));

    const folderSet = new Map();
    findings.forEach((f) => {
      const parts = inferPathParts(f);
      const key = parts.length ? parts.join('/') : (f.parent_ref != null ? `MFT #${f.parent_ref}` : '');
      if (!key) return;
      if (!folderSet.has(key)) folderSet.set(key, []);
      folderSet.get(key).push(f);
    });

    if (folderSet.size) {
      [...folderSet.entries()].slice(0, 10).forEach(([folderKey, items]) => {
        const parts = folderKey.includes('/') ? folderKey.split('/') : [folderKey];
        parts.forEach((part, pi) => {
          rows.push(treeItem(part, mftDepth + 1 + pi));
        });
        const fileDepth = mftDepth + 1 + parts.length;
        items.slice(0, 8).forEach((f) => {
          const name = f.filename || f.path?.split(/[/\\]/).pop() || `rec_${mftEntry(f)}`;
          const crit = f.suspicion_level === 'CRÍTICO' || f.suspicion_level === 'CRITICAL';
          rows.push(treeItem(name, fileDepth, { file: true, warn: crit }));
        });
      });
    } else if (findings.length) {
      findings.slice(0, 12).forEach((f) => {
        const name = f.filename || `rec_${mftEntry(f)}`;
        const crit = f.suspicion_level === 'CRÍTICO' || f.suspicion_level === 'CRITICAL';
        rows.push(treeItem(name, mftDepth + 1, { file: true, warn: crit }));
      });
    }

    return rows.join('');
  }

  function fakeHex(entry, name) {
    const seed = (entry || 0) * 7919 + (name || '').length * 31;
    const lines = [];
    for (let row = 0; row < 8; row++) {
      const off = (entry || 0) * 1024 + row * 16;
      const hex = [];
      const asc = [];
      for (let col = 0; col < 16; col++) {
        const v = (seed + row * 16 + col * 7) & 0xff;
        hex.push(v.toString(16).padStart(2, '0'));
        asc.push(v >= 32 && v < 127 ? String.fromCharCode(v) : '.');
      }
      lines.push(`${off.toString(16).padStart(8, '0')}  ${hex.slice(0, 8).join(' ')}  ${hex.slice(8).join(' ')}  |${asc.join('')}|`);
    }
    return lines.join('\n');
  }

  function renderDetails(f) {
    const body = $('ntfs-details-body');
    if (!body || !f) {
      if (body) body.innerHTML = `<p class="empty-state">${t('ntfs.selectEntry')}</p>`;
      return;
    }
    const entry = mftEntry(f) ?? '—';
    const ns = f.filename_namespace || 'Win32';
    body.innerHTML = `
      <div class="ntfs-detail-section">
        <div class="ntfs-detail-head"><span class="attr-pill">HDR</span><strong data-i18n="ntfs.recordHeader">RECORD HEADER</strong></div>
        <div class="ntfs-kv"><span>Magic Number</span><code>FILE</code></div>
        <div class="ntfs-kv"><span>Flags</span><code>${f.in_use === false ? 'Deleted' : f.is_directory ? 'Directory' : 'Allocated File'}</code></div>
        <div class="ntfs-kv"><span>MFT Entry</span><code>${esc(entry)}</code></div>
        <div class="ntfs-kv"><span>Score</span><code>${esc(f.score ?? 0)} · ${esc(f.suspicion_level || '—')}</code></div>
      </div>
      <div class="ntfs-detail-section">
        <div class="ntfs-detail-head"><span class="attr-pill">0x10</span><strong>$STANDARD_INFO</strong></div>
        <div class="ntfs-kv"><span>Creation Time</span><code>${esc(f.si_created || '—')}</code></div>
        <div class="ntfs-kv"><span>Modified</span><code>${esc(f.si_modified || '—')}</code></div>
        <div class="ntfs-kv"><span>MFT Altered</span><code>${esc(f.si_mft_modified || '—')}</code></div>
        <div class="ntfs-kv"><span>Accessed</span><code>${esc(f.si_accessed || '—')}</code></div>
      </div>
      <div class="ntfs-detail-section">
        <div class="ntfs-detail-head"><span class="attr-pill">0x30</span><strong>$FILE_NAME</strong></div>
        <div class="ntfs-kv"><span>Name</span><code>${esc(f.filename || f.path?.split(/[/\\]/).pop() || '—')}</code></div>
        <div class="ntfs-kv"><span>Namespace</span><code>${esc(ns)}</code></div>
        <div class="ntfs-kv"><span>Parent</span><code>${esc(parentLabel(f))}</code></div>
        <div class="ntfs-kv"><span>FN Created</span><code>${esc(f.fn_created || '—')}</code></div>
        <div class="ntfs-kv"><span>FN Modified</span><code>${esc(f.fn_modified || '—')}</code></div>
      </div>
      <div class="ntfs-detail-section">
        <div class="ntfs-detail-head"><span class="attr-pill">H1–H6</span><strong>Findings</strong></div>
        ${(f.findings || []).length
          ? (f.findings || []).map((item) =>
              `<div class="ntfs-kv"><span>${esc(item.code)}</span><code>${esc(item.title)}</code></div>`
            ).join('')
          : `<div class="ntfs-kv"><span>—</span><code>${t('ntfs.noFindings')}</code></div>`}
      </div>`;
  }

  function selectRow(idx, findings) {
    selectedIdx = idx;
    const f = findings[idx];
    document.querySelectorAll('#ntfs-table-body tr[data-idx]').forEach((tr) => {
      tr.classList.toggle('selected', Number(tr.dataset.idx) === idx);
    });
    const entry = mftEntry(f) ?? 0;
    const name = f?.filename || f?.path?.split(/[/\\]/).pop() || '';
    $('ntfs-hex-meta').textContent = f
      ? `ENTRY ${entry} (MFT) · Offset: 0x${(entry * 1024).toString(16).padStart(8, '0')} · ${name}`
      : '—';
    $('ntfs-hex-body').textContent = f ? fakeHex(entry, name) : '';
    renderDetails(f);
  }

  function filteredFindings(findings) {
    const showDeleted = $('ntfs-f-deleted')?.checked !== false;
    const showHidden = $('ntfs-f-hidden')?.checked !== false;
    return findings.filter((f) => {
      if (!showDeleted && f.in_use === false) return false;
      const name = (f.filename || f.path || '').toLowerCase();
      if (!showHidden && name.startsWith('.')) return false;
      return true;
    });
  }

  function renderTable(findings) {
    const tbody = $('ntfs-table-body');
    if (!tbody) return;
    const list = filteredFindings(findings);
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('ntfs.empty')}</td></tr>`;
      selectedIdx = -1;
      renderDetails(null);
      $('ntfs-hex-body').textContent = '';
      $('ntfs-hex-meta').textContent = '—';
      return;
    }
    tbody.innerHTML = list.map((f, i) => {
      const entry = mftEntry(f) ?? i;
      const name = f.filename || f.path?.split(/[/\\]/).pop() || '—';
      const deleted = f.in_use === false;
      const crit = f.suspicion_level === 'CRÍTICO' || f.suspicion_level === 'CRITICAL';
      return `<tr data-idx="${i}" class="${deleted ? 'is-deleted' : ''}${crit ? ' is-crit' : ''}">
        <td class="mono">${esc(entry)}</td>
        <td>${esc(name)}</td>
        <td class="muted">${esc(parentLabel(f))}</td>
        <td class="mono">${esc(formatSize(f))}</td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('tr[data-idx]').forEach((tr) => {
      tr.addEventListener('click', () => selectRow(Number(tr.dataset.idx), list));
    });
    if (selectedIdx >= 0 && selectedIdx < list.length) selectRow(selectedIdx, list);
    else selectRow(0, list);
  }

  function render(findings, meta) {
    const mftPath = meta?.mft_file || $('mft-path')?.value || $('ntfs-mft-path')?.value;
    const tree = $('ntfs-tree');
    if (tree) {
      tree.innerHTML = buildTree(findings || [], mftPath, meta || global.lastMeta || {});
      global.HeimdallIcons?.inject(tree);
    }
    renderTable(findings || []);
  }

  function initSplitters() {
    const root = $('ntfs-explorer');
    if (!root || root.dataset.splittersBound === '1') return;
    root.dataset.splittersBound = '1';

    const TREE_KEY = 'heimdall.ntfs.treeW';
    const DETAILS_KEY = 'heimdall.ntfs.detailsW';
    const savedTree = parseInt(localStorage.getItem(TREE_KEY), 10);
    const savedDetails = parseInt(localStorage.getItem(DETAILS_KEY), 10);
    if (savedTree >= 160) root.style.setProperty('--ntfs-tree-w', `${savedTree}px`);
    if (savedDetails >= 220) root.style.setProperty('--ntfs-details-w', `${savedDetails}px`);

    const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

    root.querySelectorAll('.ntfs-splitter').forEach((splitter) => {
      const startDrag = (clientX) => {
        const mode = splitter.dataset.resize;
        const treeEl = root.querySelector('.ntfs-tree');
        const detailsEl = root.querySelector('.ntfs-details');
        const startTree = treeEl?.offsetWidth || 280;
        const startDetails = detailsEl?.offsetWidth || 300;
        const startX = clientX;

        document.body.classList.add('ntfs-resizing');

        const onMove = (ev) => {
          const dx = ev.clientX - startX;
          if (mode === 'tree') {
            const w = clamp(startTree + dx, 160, Math.min(520, window.innerWidth * 0.48));
            root.style.setProperty('--ntfs-tree-w', `${w}px`);
          } else if (mode === 'details') {
            const w = clamp(startDetails - dx, 220, Math.min(480, window.innerWidth * 0.42));
            root.style.setProperty('--ntfs-details-w', `${w}px`);
          }
        };

        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          document.body.classList.remove('ntfs-resizing');
          if (treeEl?.offsetWidth) localStorage.setItem(TREE_KEY, String(treeEl.offsetWidth));
          if (detailsEl?.offsetWidth) localStorage.setItem(DETAILS_KEY, String(detailsEl.offsetWidth));
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      };

      splitter.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        startDrag(e.clientX);
      });

      splitter.addEventListener('keydown', (e) => {
        const treeEl = root.querySelector('.ntfs-tree');
        const detailsEl = root.querySelector('.ntfs-details');
        const step = e.shiftKey ? 32 : 12;
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        const dir = e.key === 'ArrowRight' ? 1 : -1;
        if (splitter.dataset.resize === 'tree') {
          const w = clamp((treeEl?.offsetWidth || 280) + dir * step, 160, Math.min(520, window.innerWidth * 0.48));
          root.style.setProperty('--ntfs-tree-w', `${w}px`);
          localStorage.setItem(TREE_KEY, String(w));
        } else {
          const w = clamp((detailsEl?.offsetWidth || 300) - dir * step, 220, Math.min(480, window.innerWidth * 0.42));
          root.style.setProperty('--ntfs-details-w', `${w}px`);
          localStorage.setItem(DETAILS_KEY, String(w));
        }
      });
    });
  }

  function bind() {
    initSplitters();
    ['ntfs-f-hidden', 'ntfs-f-deleted', 'ntfs-f-ads'].forEach((id) => {
      $(id)?.addEventListener('change', () => {
        render(global.findings || [], global.lastMeta || {});
      });
    });
    $('ntfs-export-csv')?.addEventListener('click', () => {
      global.exportReport?.('csv');
    });
  }

  global.HeimdallNtfsExplorer = { render, bind, selectRow };
})(window);
