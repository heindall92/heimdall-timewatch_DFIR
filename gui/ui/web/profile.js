/* Perfil de usuario — estilo Norvik */
(function (global) {
  function t(key, vars) {
    return global.HeimdallI18n?.t(key, vars) ?? key;
  }

  function $(id) { return document.getElementById(id); }

  function parseJson(raw) {
    try { return JSON.parse(raw); } catch { return { ok: false }; }
  }

  function callBridge(method, ...args) {
    const bridge = global.bridge;
    if (!bridge || typeof bridge[method] !== 'function') {
      return Promise.reject(new Error('Bridge no disponible'));
    }
    return Promise.resolve(bridge[method](...args));
  }

  function initials(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'DF';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function avatarSrc(url) {
    if (!url) return '';
    if (url.startsWith('data:')) return url;
    return `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`;
  }

  function renderAvatarEl(el, url, ini) {
    if (!el) return;
    if (url) {
      el.innerHTML = `<img src="${avatarSrc(url)}" alt="" />`;
      el.classList.add('has-photo');
    } else {
      el.textContent = ini;
      el.classList.remove('has-photo');
    }
  }

  function setProfileAvatarPreview(url, ini) {
    const preview = $('profile-avatar-preview');
    const initialsEl = $('profile-avatar-initials');
    const picker = $('profile-avatar-picker');
    const removeBtn = $('profile-avatar-remove');
    if (initialsEl) initialsEl.textContent = ini;
    if (url && preview) {
      preview.src = avatarSrc(url);
      preview.hidden = false;
      picker?.classList.add('has-photo');
      removeBtn?.removeAttribute('hidden');
    } else {
      if (preview) { preview.hidden = true; preview.removeAttribute('src'); }
      picker?.classList.remove('has-photo');
      removeBtn?.setAttribute('hidden', '');
    }
  }

  function applyUserProfile(s) {
    const name = s.user_name || t('profile.defaultName');
    const role = s.user_role || t('profile.defaultRole');
    const ini = initials(name);
    const avatarUrl = s.user_avatar_url || '';
    const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };
    setText('user-chip-name', name);
    setText('user-chip-role', role);
    setText('user-menu-title', name);
    setText('user-menu-sub', role);
    setText('brand-user-name', name);
    renderAvatarEl($('user-avatar'), avatarUrl, ini);
    renderAvatarEl($('user-menu-avatar'), avatarUrl, ini);
  }

  function fillProfileForm(s) {
    const setVal = (id, val) => { const el = $(id); if (el) el.value = val || ''; };
    setVal('profile-user-name', s.user_name);
    setVal('profile-user-role', s.user_role);
    setVal('profile-bio', s.user_bio);
    setVal('profile-org', s.org_name);
    setVal('profile-department', s.user_department);
    setVal('profile-email', s.user_email);
    setVal('profile-phone', s.user_phone);
    setVal('profile-location', s.user_location);
    setVal('profile-linkedin', s.user_linkedin);
    setVal('profile-github', s.user_github);
    setVal('profile-twitter', s.user_twitter);
    setVal('profile-website', s.user_website);
    setProfileAvatarPreview(s.user_avatar_url, initials(s.user_name));
    global.HeimdallIcons?.inject($('user-profile-modal'));
  }

  async function fetchSettings() {
    const data = parseJson(await callBridge('get_settings'));
    return data.ok ? (data.settings || {}) : {};
  }

  function openUserProfile() {
    global.closeUserPopup?.();
    const modal = $('user-profile-modal');
    if (!modal) return;
    fetchSettings().then((s) => {
      fillProfileForm(s);
      modal.hidden = false;
      $('profile-user-name')?.focus();
    }).catch(() => { modal.hidden = false; });
  }

  function closeUserProfile() {
    const modal = $('user-profile-modal');
    if (modal) modal.hidden = true;
  }

  function collectProfilePayload() {
    return {
      user_name: $('profile-user-name')?.value.trim() || '',
      user_role: $('profile-user-role')?.value.trim() || '',
      user_bio: $('profile-bio')?.value.trim() || '',
      org_name: $('profile-org')?.value.trim() || '',
      user_department: $('profile-department')?.value.trim() || '',
      user_email: $('profile-email')?.value.trim() || '',
      user_phone: $('profile-phone')?.value.trim() || '',
      user_location: $('profile-location')?.value.trim() || '',
      user_linkedin: $('profile-linkedin')?.value.trim() || '',
      user_github: $('profile-github')?.value.trim() || '',
      user_twitter: $('profile-twitter')?.value.trim() || '',
      user_website: $('profile-website')?.value.trim() || '',
    };
  }

  async function saveUserProfile() {
    const payload = collectProfilePayload();
    if (!payload.user_name) {
      global.toast?.(t('profile.nameRequired'));
      $('profile-user-name')?.focus();
      return;
    }
    if (!payload.user_role) {
      global.toast?.(t('profile.roleRequired'));
      $('profile-user-role')?.focus();
      return;
    }
    const data = parseJson(await callBridge('save_app_settings', JSON.stringify(payload)));
    if (data.ok) {
      const settings = await fetchSettings();
      applyUserProfile(settings);
      closeUserProfile();
      global.toast?.(t('profile.saved'));
    } else {
      global.toast?.(data.error || 'Error', true);
    }
  }

  async function uploadProfileAvatar(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      global.toast?.(t('profile.photoFormat'));
      return;
    }
    if (file.size > 3 * 1024 * 1024) {
      global.toast?.(t('profile.photoSize'));
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const result = parseJson(await callBridge('save_user_avatar', reader.result));
        if (!result.ok) throw new Error(result.error || 'No se pudo guardar la foto');
        const ini = initials($('profile-user-name')?.value);
        setProfileAvatarPreview(result.url, ini);
        const settings = await fetchSettings();
        applyUserProfile(settings);
        global.toast?.(t('profile.photoUpdated'));
      } catch (err) {
        global.toast?.(err.message || 'Error al subir', true);
      }
    };
    reader.readAsDataURL(file);
  }

  async function removeProfileAvatar() {
    const result = parseJson(await callBridge('remove_user_avatar'));
    if (!result.ok) {
      global.toast?.(result.error || 'Error', true);
      return;
    }
    const ini = initials($('profile-user-name')?.value);
    setProfileAvatarPreview('', ini);
    const settings = await fetchSettings();
    applyUserProfile(settings);
    global.toast?.(t('profile.photoRemoved'));
  }

  function bind() {
    $('profile-close')?.addEventListener('click', closeUserProfile);
    $('profile-cancel')?.addEventListener('click', closeUserProfile);
    $('profile-save')?.addEventListener('click', saveUserProfile);
    $('user-profile-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'user-profile-modal') closeUserProfile();
    });

    const avatarInput = $('profile-avatar-input');
    const triggerPick = () => avatarInput?.click();
    $('profile-avatar-upload')?.addEventListener('click', triggerPick);
    $('profile-avatar-picker')?.addEventListener('click', triggerPick);
    avatarInput?.addEventListener('change', () => {
      const file = avatarInput.files?.[0];
      if (file) uploadProfileAvatar(file);
      avatarInput.value = '';
    });
    $('profile-avatar-remove')?.addEventListener('click', (e) => {
      e.stopPropagation();
      removeProfileAvatar();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeUserProfile();
    });

    const socialMap = {
      linkedin: 'profile-linkedin',
      github: 'profile-github',
      twitter: 'profile-twitter',
      website: 'profile-website',
    };
    document.querySelectorAll('.social-link-btn[data-social]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const fieldId = socialMap[btn.dataset.social];
        const url = $(fieldId)?.value.trim();
        if (url) {
          window.open(url, '_blank', 'noopener,noreferrer');
          return;
        }
        $(fieldId)?.focus();
        global.toast?.(t('profile.socialEmpty'));
      });
    });
  }

  global.HeimdallProfile = {
    bind,
    applyUserProfile,
    openUserProfile,
    closeUserProfile,
  };
})(window);
