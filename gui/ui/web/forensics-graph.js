/**
 * Grafo forense — nodos + aristas SVG animadas (inspirado en dashboards 21st.dev).
 */
(function (global) {
  function escapeHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function levelClass(level) {
    if (level === 'CRÍTICO' || level === 'CRITICAL') return 'crit';
    if (level === 'ALTO' || level === 'HIGH') return 'high';
    if (level === 'MEDIO' || level === 'MEDIUM') return 'med';
    return 'low';
  }

  function primaryReason(f) {
    const first = (f.findings || [])[0];
    return first ? first.code : '';
  }

  function nodeIcon(f) {
    if (f.suspicion_level === 'CRÍTICO' || f.suspicion_level === 'CRITICAL') return 'shield';
    const code = primaryReason(f);
    if (code === 'LAB' || code.startsWith('H2')) return 'lab';
    if (code.startsWith('H5')) return 'help';
    return 'scan';
  }

  function layoutNodes(count, width, height) {
    const positions = [];
    if (count <= 0) return positions;
    const cx = width / 2;
    const cy = height / 2;
    const rx = Math.min(width, height) * 0.34;
    const ry = Math.min(width, height) * 0.3;
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
      positions.push({
        x: cx + Math.cos(angle) * rx * (0.88 + (i % 3) * 0.06),
        y: cy + Math.sin(angle) * ry * (0.88 + (i % 2) * 0.08),
      });
    }
    return positions;
  }

  function curvedPath(ax, ay, bx, by, w, h, bendSign = 1) {
    const cx = w / 2;
    const cy = h / 2;
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    const mx = (ax + bx) / 2;
    const my = (ay + by) / 2;
    const toCenter = (cx - mx) * nx + (cy - my) * ny;
    const sign = (toCenter >= 0 ? 1 : -1) * bendSign;
    const bow = Math.min(len * 0.28, 56) * sign;
    const c1x = ax + dx * 0.28 + nx * bow;
    const c1y = ay + dy * 0.28 + ny * bow;
    const c2x = ax + dx * 0.72 + nx * bow;
    const c2y = ay + dy * 0.72 + ny * bow;
    return `M ${ax.toFixed(1)} ${ay.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)} `
      + `${c2x.toFixed(1)} ${c2y.toFixed(1)} ${bx.toFixed(1)} ${by.toFixed(1)}`;
  }

  function measureGraphArea(container) {
    const area = container?.parentElement;
    if (!area) return { w: 800, h: 500 };
    const rect = area.getBoundingClientRect();
    return {
      w: Math.max(1, Math.round(rect.width)),
      h: Math.max(1, Math.round(rect.height)),
    };
  }

  function buildEdgesSvg(positions, w, h) {
    if (positions.length < 2) return '';
    const paths = [];
    for (let i = 0; i < positions.length; i++) {
      const a = positions[i];
      const b = positions[(i + 1) % positions.length];
      const d = curvedPath(a.x, a.y, b.x, b.y, w, h, 1);
      paths.push(
        `<path class="graph-edge-line" d="${d}" pathLength="100" `
        + `style="animation-delay:${(i * 0.15).toFixed(2)}s"/>`
      );
      if (i % 2 === 0 && positions.length > 3) {
        const c = positions[(i + 2) % positions.length];
        const dSoft = curvedPath(a.x, a.y, c.x, c.y, w, h, -0.65);
        paths.push(
          `<path class="graph-edge-line graph-edge-line--soft" d="${dSoft}" pathLength="100" `
          + `style="animation-delay:${(i * 0.22).toFixed(2)}s"/>`
        );
      }
    }
    return `
      <svg class="graph-edges-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        ${paths.join('')}
      </svg>`;
  }

  function renderGraphNodes(containerId, emptyId, items, options) {
    const container = document.getElementById(containerId);
    const empty = document.getElementById(emptyId);
    if (!container) return;

    const {
      findings = [],
      selectedIndex = -1,
      onSelect = () => {},
      resolveIndex = (f) => findings.indexOf(f),
    } = options || {};

    container.innerHTML = '';
    if (!items.length) {
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    const { w, h } = measureGraphArea(container);
    const slice = items.slice(0, 12);
    const positions = layoutNodes(slice.length, w, h);

    container.insertAdjacentHTML('afterbegin', buildEdgesSvg(positions, w, h));

    slice.forEach((f, i) => {
      const realIdx = resolveIndex(f);
      const idx = realIdx >= 0 ? realIdx : i;
      const pos = positions[i];
      const name = f.filename || `rec_${f.record_number}`;
      const short = name.length > 20 ? `${name.slice(0, 18)}…` : name;
      const reason = primaryReason(f);
      const sel = idx === selectedIndex ? ' selected' : '';
      const lvl = levelClass(f.suspicion_level);
      const icon = nodeIcon(f);

      const node = document.createElement('div');
      node.className = `graph-node ${lvl}${sel}`;
      node.style.left = `${pos.x}px`;
      node.style.top = `${pos.y}px`;
      node.innerHTML = `
        <div class="node-circle">
          <span class="node-glyph" data-icon="${icon}"></span>
        </div>
        <span class="node-label">${escapeHtml(short)}</span>
        ${reason ? `<span class="node-reason">${escapeHtml(reason)}</span>` : ''}
      `;
      node.addEventListener('click', () => onSelect(idx));
      container.appendChild(node);
    });

    global.HeimdallIcons?.inject(container);
  }

  global.HeimdallForensicsGraph = { renderGraphNodes, layoutNodes };
})(window);
