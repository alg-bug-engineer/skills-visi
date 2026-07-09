(function () {
  const phaseLinks = [
    { label: '场景认知', phase: 1 },
    { label: '问题诊断', phase: 2 },
    { label: '控制策略', phase: 3 },
    { label: '方案生成', phase: 4 },
    { label: '评价反馈', phase: 5 },
  ];

  function params() {
    return new URLSearchParams(window.location.search);
  }

  function contextQuery(extra) {
    const input = params();
    const out = new URLSearchParams();
    ['id', 'type'].forEach((key) => {
      const value = input.get(key);
      if (value) out.set(key, value);
    });
    Object.entries(extra || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') out.set(key, value);
    });
    const s = out.toString();
    return s ? `?${s}` : '';
  }

  function preserveContextLinks(root) {
    const scope = root || document;
    scope.querySelectorAll('a[href*="agent-workbench.html"],a[href*="scene-cognition.html"],a[href*="problem-diagnosis.html"],a[href*="control-strategy.html"],a[href*="plan-generation.html"],a[href*="evaluation-feedback.html"],a[href*="human-in-loop.html"]').forEach((link) => {
      const href = link.getAttribute('href');
      if (!href || href.startsWith('http') || href.includes('id=') || href.includes('type=')) return;
      const [base, rawQuery] = href.split('?');
      const q = new URLSearchParams(rawQuery || '');
      const current = params();
      ['id', 'type'].forEach((key) => {
        if (!q.has(key) && current.get(key)) q.set(key, current.get(key));
      });
      const next = q.toString();
      link.setAttribute('href', next ? `${base}?${next}` : base);
    });
  }

  function decorateTopnav() {
    document.querySelectorAll('.topnav').forEach((nav) => {
      nav.classList.add('sc-shell-topnav');
    });
  }

  function toast(message, type) {
    let region = document.querySelector('.sc-toast-region');
    if (!region) {
      region = document.createElement('div');
      region.className = 'sc-toast-region';
      document.body.appendChild(region);
    }
    const el = document.createElement('div');
    el.className = `sc-toast ${type || 'info'}`;
    el.textContent = message;
    region.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    window.setTimeout(() => {
      el.classList.remove('show');
      window.setTimeout(() => el.remove(), 220);
    }, 2600);
  }

  function confirmRisk(options) {
    const opts = Object.assign({
      title: '确认高风险动作',
      message: '该动作会改变当前处置状态，请确认后继续。',
      confirmText: '确认',
      cancelText: '取消',
      requireReason: false,
      reasonPlaceholder: '请输入原因，便于后续复盘',
    }, options || {});

    return new Promise((resolve) => {
      let mask = document.querySelector('.sc-confirm-mask');
      if (!mask) {
        mask = document.createElement('div');
        mask.className = 'sc-confirm-mask';
        document.body.appendChild(mask);
      }
      mask.innerHTML = `
        <div class="sc-confirm" role="dialog" aria-modal="true">
          <div class="sc-confirm-head"></div>
          <div class="sc-confirm-body">
            <div class="sc-confirm-message"></div>
            ${opts.requireReason ? '<textarea class="sc-confirm-reason"></textarea>' : ''}
          </div>
          <div class="sc-confirm-actions">
            <button type="button" class="sc-btn" data-role="cancel"></button>
            <button type="button" class="sc-btn danger" data-role="confirm"></button>
          </div>
        </div>
      `;
      mask.querySelector('.sc-confirm-head').textContent = opts.title;
      mask.querySelector('.sc-confirm-message').textContent = opts.message;
      mask.querySelector('[data-role="cancel"]').textContent = opts.cancelText;
      mask.querySelector('[data-role="confirm"]').textContent = opts.confirmText;
      const reason = mask.querySelector('.sc-confirm-reason');
      if (reason) reason.placeholder = opts.reasonPlaceholder;

      function close(value) {
        mask.classList.remove('open');
        resolve(value);
      }

      mask.querySelector('[data-role="cancel"]').onclick = () => close({ ok: false, reason: '' });
      mask.querySelector('[data-role="confirm"]').onclick = () => {
        const reasonValue = reason ? reason.value.trim() : '';
        if (opts.requireReason && !reasonValue) {
          toast('请先填写原因', 'warn');
          reason.focus();
          return;
        }
        close({ ok: true, reason: reasonValue });
      };
      mask.onclick = (event) => {
        if (event.target === mask) close({ ok: false, reason: '' });
      };
      mask.classList.add('open');
      if (reason) reason.focus();
    });
  }

  function injectPhaseShortcuts(container, activePhase) {
    if (!container) return;
    const current = Number(activePhase || params().get('phase') || 1);
    container.innerHTML = phaseLinks.map((item) => {
      const cls = item.phase === current ? 'sc-action primary' : item.phase < current ? 'sc-action success' : 'sc-action';
      return `<a class="${cls}" href="/debug/agent-workbench.html${contextQuery({ phase: item.phase })}">${item.phase}. ${item.label}</a>`;
    }).join('');
  }

  function emptyState(title, desc) {
    return `<div class="sc-empty"><strong>${escapeHtml(title || '暂无数据')}</strong>${desc ? `<br>${escapeHtml(desc)}` : ''}</div>`;
  }

  function errorBox(message) {
    return `<div class="sc-error-box">${escapeHtml(message || '请求失败，请检查服务状态后重试。')}</div>`;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function boot() {
    document.body.classList.add('sc-ui');
    decorateTopnav();
    preserveContextLinks();
  }

  window.SignalControlUI = {
    params,
    contextQuery,
    preserveContextLinks,
    toast,
    confirmRisk,
    injectPhaseShortcuts,
    emptyState,
    errorBox,
    escapeHtml,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
}());
