// =========================================================
// BritonLauncher landing — script
// =========================================================

// 👉 ЗАМЕНИ на свой репозиторий: "ник/репозиторий"
const REPO = "KostyaProcrom/BritonLauncher";

const repoUrl = `https://github.com/${REPO}`;
const releasesUrl = `${repoUrl}/releases/latest`;

document.querySelectorAll('[data-repo-link]').forEach((el) => {
  const kind = el.getAttribute('data-repo-link');
  el.href = kind === 'releases' ? releasesUrl : repoUrl;
});

// Мобильное меню
const burger = document.getElementById('burger');
const nav = document.getElementById('nav');
if (burger && nav) {
  burger.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    burger.setAttribute('aria-expanded', String(open));
  });
  nav.querySelectorAll('a').forEach((a) =>
    a.addEventListener('click', () => {
      nav.classList.remove('open');
      burger.setAttribute('aria-expanded', 'false');
    })
  );
}

// Появление блоков при скролле
const revealTargets = document.querySelectorAll(
  '.card, .step, .shot-card, .faq, .section-head, .preview-text, .preview-shot, .cta-row'
);
revealTargets.forEach((el) => el.classList.add('reveal'));

if ('IntersectionObserver' in window) {
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  revealTargets.forEach((el) => io.observe(el));
} else {
  revealTargets.forEach((el) => el.classList.add('in'));
}

// Год в футере (если добавишь элемент)
const yearEl = document.getElementById('year');
if (yearEl) yearEl.textContent = new Date().getFullYear();

// =========================================================
//  BritonLauncher DB — аккаунты в Supabase
// =========================================================
const SUPA_URL = 'https://lmjizrowtxuwlovbirge.supabase.co';
const SUPA_KEY = 'sb_publishable_R4FofdxSpJhuzDvahy1gKw_Q1Dfmbob';
const TOKEN_KEY = 'britonlauncher.token';
const LEGACY_PD_KEY = 'britonlauncher.playerdata';
const LEGACY_SESSION_KEY = 'britonlauncher.session';
const ADMINS = ['KostyaKosmos', 'BritonLauncher'];

let CURRENT = null;
let ADMIN_DATA = null;
let adminSeq = 0;
let adminDebounce = null;

const LOG_LABELS = {
  register: 'зарегистрировался',
  launcher_login: 'вошёл в лаунчер',
  ban: 'забанил',
  unban: 'разбанил',
  mute: 'замутил',
  unmute: 'размутил',
  promote: 'выдал админа',
  demote: 'снял админа',
  delete: 'удалил',
};

function isAdminNick(nick) {
  const low = String(nick || '').toLowerCase();
  return ADMINS.some((a) => a.toLowerCase() === low);
}

function isMainAdmin(nick, profile) {
  if (profile && profile.main) return true;
  return String(nick || '').toLowerCase() === ADMINS[0].toLowerCase();
}

function isBanned(player) {
  return !!(player && player.banned);
}

function isMuted(player) {
  return !!(player && player.muted);
}

function currentPlayer() {
  return CURRENT;
}

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

/* ---------- запросы к Supabase ---------- */
async function sbRpc(fn, params) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 20000);
  try {
    const res = await fetch(`${SUPA_URL}/rest/v1/rpc/${fn}`, {
      method: 'POST',
      headers: {
        apikey: SUPA_KEY,
        Authorization: `Bearer ${SUPA_KEY}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(params || {}),
      signal: ctrl.signal,
    });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (e) {}
    if (!res.ok) {
      const msg = (data && (data.message || data.hint || data.error)) || `Ошибка базы (${res.status})`;
      throw new Error(msg);
    }
    return data || { ok: false, error: 'Пустой ответ базы' };
  } catch (e) {
    if (e && e.name === 'AbortError') throw new Error('База не отвечает — проверь интернет');
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- старые локальные аккаунты (только для переноса) ---------- */
function legacyLoad() {
  try {
    const raw = localStorage.getItem(LEGACY_PD_KEY);
    const data = raw ? JSON.parse(raw) : null;
    if (data && data.players && typeof data.players === 'object') return data;
  } catch (e) {}
  return { players: {} };
}

function legacyFind(players, nick) {
  const low = String(nick || '').toLowerCase();
  const key = Object.keys(players).find((k) => k.toLowerCase() === low);
  return key ? { nick: key, player: players[key] } : null;
}

async function hashPassword(password, salt) {
  const enc = new TextEncoder().encode(salt + ':' + password);
  const buf = await crypto.subtle.digest('SHA-256', enc);
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function legacyPasswordOk(player, pass) {
  if (!player || !player.salt || !player.hash || !crypto?.subtle) return false;
  const hash = await hashPassword(pass, player.salt);
  return hash === player.hash;
}

/* ---------- сессия ---------- */
function applyAuth(res) {
  if (!res || !res.ok) return false;
  localStorage.setItem(TOKEN_KEY, res.token);
  CURRENT = res.profile;
  ADMIN_DATA = null;
  return true;
}

async function initSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    CURRENT = null;
    refreshAccountUI();
    return;
  }
  try {
    const res = await sbRpc('bl_me', { p_token: token });
    if (res && res.ok) {
      CURRENT = res.profile;
    } else {
      localStorage.removeItem(TOKEN_KEY);
      CURRENT = null;
    }
  } catch (e) {
    CURRENT = null;
    setMsg('База временно недоступна: ' + e.message, 'error');
  }
  refreshAccountUI();
}

/* ---------- раздел аккаунта ---------- */
function openLogin() {
  switchTab('login');
  openAccount();
}

function openAccount() {
  const section = document.getElementById('account');
  if (!section) return;
  nav?.classList.remove('open');
  burger?.setAttribute('aria-expanded', 'false');
  refreshAccountUI();
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeAccount() {
  nav?.classList.remove('open');
}

function switchTab(tab) {
  document.querySelectorAll('.auth-tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  document.getElementById('form-login').classList.toggle('hidden', tab !== 'login');
  document.getElementById('form-register').classList.toggle('hidden', tab !== 'register');
  setMsg('');
}

function setMsg(text, kind) {
  const el = document.getElementById('auth-msg');
  if (!el) return;
  el.textContent = text || '';
  el.className = 'auth-msg' + (kind ? ' ' + kind : '');
}

/* ---------- регистрация / вход ---------- */
async function doRegister(event) {
  event.preventDefault();

  const nick = (document.getElementById('reg-nick').value || '').trim();
  const pass = document.getElementById('reg-pass').value || '';
  const pass2 = document.getElementById('reg-pass2').value || '';

  if (!/^[A-Za-z0-9_]{3,16}$/.test(nick)) {
    return setMsg('Ник: 3–16 символов (латиница, цифры, _)', 'error');
  }
  if (pass.length < 4) return setMsg('Пароль должен быть минимум 4 символа', 'error');
  if (pass !== pass2) return setMsg('Пароли не совпадают', 'error');

  setMsg('Создаю аккаунт...');
  let res;
  try {
    if (isAdminNick(nick)) {
      const code = prompt(`Ник «${nick}» зарезервирован.\nВведи код администратора:`, '');
      if (code === null) return setMsg('Регистрация отменена');
      if (!code.trim()) return setMsg('Нужен код администратора', 'error');
      res = await sbRpc('bl_claim_fixed_admin', {
        p_nick: nick,
        p_password: pass,
        p_code: code.trim(),
      });
    } else {
      res = await sbRpc('bl_register', { p_nick: nick, p_password: pass });
    }
  } catch (e) {
    return setMsg('Ошибка базы: ' + e.message, 'error');
  }

  if (!res || !res.ok) return setMsg((res && res.error) || 'Не удалось создать аккаунт', 'error');
  if (!applyAuth(res)) return setMsg('База не выдала сессию', 'error');

  document.getElementById('form-register').reset();
  setMsg('');
  refreshAccountUI();
}

async function doLogin(event) {
  event.preventDefault();

  const nick = (document.getElementById('login-nick').value || '').trim();
  const pass = document.getElementById('login-pass').value || '';
  if (!nick || !pass) return setMsg('Введи ник и пароль', 'error');

  setMsg('Проверяю...');
  let res;
  try {
    res = await sbRpc('bl_login', { p_nick: nick, p_password: pass });

    // Первый вход после перехода на базу: переносим аккаунт из localStorage.
    if (!res.ok && res.code === 'not_found') {
      const legacy = legacyFind(legacyLoad().players, nick);
      if (legacy && (await legacyPasswordOk(legacy.player, pass))) {
        if (isAdminNick(legacy.nick)) {
          return setMsg('Админский ник нужно зарегистрировать заново с кодом администратора', 'error');
        }
        res = await sbRpc('bl_register', { p_nick: legacy.nick, p_password: pass });
        if (!res.ok && res.code === 'taken') {
          res = await sbRpc('bl_login', { p_nick: legacy.nick, p_password: pass });
        }
        if (res.ok) setMsg('Аккаунт перенесён в базу');
      }
    }
  } catch (e) {
    return setMsg('База недоступна: ' + e.message, 'error');
  }

  if (!res || !res.ok) return setMsg((res && res.error) || 'Не удалось войти', 'error');
  if (!applyAuth(res)) return setMsg('База не выдала сессию', 'error');

  localStorage.removeItem(LEGACY_SESSION_KEY);
  document.getElementById('form-login').reset();
  setMsg('');
  refreshAccountUI();
}

async function doLogout() {
  const token = localStorage.getItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
  CURRENT = null;
  ADMIN_DATA = null;
  switchTab('login');
  refreshAccountUI();
  if (token) {
    try {
      await sbRpc('bl_logout', { p_token: token });
    } catch (e) {}
  }
}

/* ---------- код для лаунчера ---------- */
async function makeLauncherCode() {
  const me = currentPlayer();
  const status = document.getElementById('launcher-code-status');
  if (!me) return;

  if (isBanned(me)) {
    if (status) status.textContent = 'Аккаунт забанен: ' + (me.banReason || 'без причины');
    return;
  }

  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    if (status) status.textContent = 'Сессия истекла — войди заново';
    return;
  }

  if (status) status.textContent = 'Генерация...';
  try {
    const res = await sbRpc('bl_create_launcher_code', { p_token: token });
    if (!res.ok) {
      if (status) status.textContent = res.error || 'Не удалось получить код';
      return;
    }
    document.getElementById('launcher-code').value = res.code;
    document.getElementById('launcher-code-result').classList.remove('hidden');
    if (status) status.textContent = 'Код действует 7 дней. Одноразовый.';
  } catch (e) {
    if (status) status.textContent = 'Ошибка базы: ' + e.message;
  }
}

async function copyLauncherCode() {
  const el = document.getElementById('launcher-code');
  const status = document.getElementById('launcher-code-status');
  if (!el || !el.value) return;
  try {
    await navigator.clipboard.writeText(el.value);
    if (status) status.textContent = 'Скопировано ✓';
  } catch (e) {
    el.select();
    document.execCommand('copy');
    if (status) status.textContent = 'Скопировано ✓';
  }
}

/* ---------- отрисовка ---------- */
function refreshAccountUI() {
  const guest = document.getElementById('account-guest');
  const user = document.getElementById('account-user');
  const navBtn = document.getElementById('nav-account');
  if (!guest || !user) return;

  const me = CURRENT;

  if (!me) {
    guest.classList.remove('hidden');
    user.classList.add('hidden');
    if (navBtn) {
      navBtn.textContent = 'Вход';
      navBtn.classList.remove('is-user');
    }
    return;
  }

  guest.classList.add('hidden');
  user.classList.remove('hidden');
  if (navBtn) {
    navBtn.textContent = me.nick;
    navBtn.classList.add('is-user');
  }

  document.getElementById('profile-avatar').textContent = me.nick.charAt(0).toUpperCase();
  document.getElementById('profile-nick').textContent = me.nick;
  document.getElementById('profile-role').innerHTML =
    (me.role === 'admin' ? '<span class="role-badge admin">ADMIN</span>' : '<span class="role-badge">PLAYER</span>') +
    (isBanned(me) ? ' <span class="status-badge banned">ЗАБАНЕН</span>' : '') +
    (isMuted(me) ? ' <span class="status-badge muted">МУТ</span>' : '');

  document.getElementById('launcher-code-box').classList.toggle('hidden', isBanned(me));

  const adminPanel = document.getElementById('admin-panel');
  adminPanel.classList.toggle('hidden', me.role !== 'admin');

  let note = '';
  if (isBanned(me)) {
    note = 'Аккаунт забанен: ' + (me.banReason || 'без причины') + '. Вход в лаунчер и получение кода недоступны.';
  } else if (me.role === 'admin') {
    note = isMainAdmin(me.nick, me)
      ? 'Ты главный администратор: полный доступ к аккаунтам, банам и мутам.'
      : 'Ты администратор: можешь выдавать роли, банить, мутить и удалять аккаунты.';
    if (isMuted(me)) note += ' На тебе мут.';
  } else {
    note = isMuted(me) ? 'Ты вошёл как игрок. Действует мут.' : 'Ты вошёл как игрок.';
  }
  document.getElementById('user-note').textContent = note;

  if (me.role === 'admin') renderAdmin();
}

function renderAdminLog(log) {
  const list = document.getElementById('admin-log-list');
  if (!list) return;
  const rows = Array.isArray(log) ? log : [];
  if (!rows.length) {
    list.innerHTML = '<li class="admin-log-empty">Пока пусто.</li>';
    return;
  }
  list.innerHTML = rows
    .map((e) => {
      const label = LOG_LABELS[e.action] || e.action;
      const target = e.action === 'register' || !e.nick ? '' : ' <b>' + escapeHtml(e.nick) + '</b>';
      const extra = e.extra ? ' <span class="log-extra">(' + escapeHtml(e.extra) + ')</span>' : '';
      return `<li><span class="log-time">${escapeHtml(e.at || '')}</span> <b>${escapeHtml(e.by || '—')}</b> ${label}${target}${extra}</li>`;
    })
    .join('');
}

function renderAdminTable(players) {
  const tbody = document.getElementById('admin-players');
  if (!tbody) return;
  const me = CURRENT;
  const rows = Array.isArray(players) ? players : [];

  tbody.innerHTML = rows.length
    ? rows
        .map((player) => {
          const nick = player.nick;
          const role = player.role === 'admin' ? 'admin' : 'player';
          const banned = isBanned(player);
          const muted = isMuted(player);
          const isFixed = isAdminNick(nick);
          const isSelf = me && nick.toLowerCase() === me.nick.toLowerCase();

          const status = banned
            ? `<span class="status-badge banned" title="${escapeHtml(player.banReason || '')}">ЗАБАНЕН</span>`
            : muted
              ? `<span class="status-badge muted" title="${escapeHtml(player.muteReason || '')}">МУТ</span>`
              : '<span class="status-badge active">АКТИВЕН</span>';

          let actions;
          if (isFixed) {
            actions = `<span class="auth-note">${isMainAdmin(nick, player) ? 'главный админ' : 'админ сайта'}</span>`;
          } else if (isSelf) {
            actions = `<span class="auth-note">это ты</span>`;
          } else {
            actions =
              `<button class="mini-btn ${banned ? '' : 'danger'}" onclick="adminToggleBan('${escapeHtml(nick)}')">${
                banned ? 'Разбанить' : 'Забанить'
              }</button>` +
              `<button class="mini-btn" onclick="adminToggleMute('${escapeHtml(nick)}')">${
                muted ? 'Размутить' : 'Замутить'
              }</button>` +
              `<button class="mini-btn" onclick="adminToggleRole('${escapeHtml(nick)}')">${
                role === 'admin' ? 'Снять админа' : 'Сделать админом'
              }</button>` +
              `<button class="mini-btn danger" onclick="adminDelete('${escapeHtml(nick)}')">Удалить</button>`;
          }

          return `<tr class="${isSelf ? 'is-me' : ''}">
            <td>${escapeHtml(nick)}</td>
            <td><span class="role-badge ${role === 'admin' ? 'admin' : ''}">${role.toUpperCase()}</span></td>
            <td>${status}</td>
            <td>${escapeHtml(player.created || '—')}</td>
            <td>${escapeHtml(player.lastLogin || '—')}</td>
            <td class="admin-actions">${actions}</td>
          </tr>`;
        })
        .join('')
    : '<tr><td colspan="6" class="admin-empty">Ничего не найдено.</td></tr>';
}

async function renderAdmin() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token || !CURRENT || CURRENT.role !== 'admin') return;

  const seq = ++adminSeq;
  const query = (document.getElementById('admin-search')?.value || '').trim();

  try {
    const res = await sbRpc('bl_admin_data', { p_token: token, p_search: query });
    if (seq !== adminSeq) return;
    if (!res.ok) {
      const tbody = document.getElementById('admin-players');
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="admin-empty">${escapeHtml(res.error || 'Ошибка базы')}</td></tr>`;
      return;
    }
    ADMIN_DATA = res;
    renderAdminTable(res.players);
    const stats = res.stats || {};
    document.getElementById('admin-count').textContent = stats.total || 0;
    document.getElementById('admin-admins').textContent = stats.admins || 0;
    document.getElementById('admin-bans').textContent = stats.bans || 0;
    document.getElementById('admin-mutes').textContent = stats.mutes || 0;
    renderAdminLog(res.log);
  } catch (e) {
    if (seq !== adminSeq) return;
    const tbody = document.getElementById('admin-players');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="admin-empty">База недоступна: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function scheduleAdminRender() {
  clearTimeout(adminDebounce);
  adminDebounce = setTimeout(renderAdmin, 250);
}

function adminCanAct() {
  return CURRENT && CURRENT.role === 'admin' ? CURRENT : null;
}

function adminFind(nick) {
  const players = (ADMIN_DATA && ADMIN_DATA.players) || [];
  return players.find((p) => p.nick.toLowerCase() === String(nick || '').toLowerCase()) || null;
}

async function adminRun(action, nick, extra) {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return false;
  try {
    const res = await sbRpc('bl_admin_action', {
      p_token: token,
      p_action: action,
      p_target: nick,
      p_extra: extra || '',
    });
    if (!res.ok) {
      alert(res.error || 'Ошибка действия');
      return false;
    }
    await renderAdmin();
    return true;
  } catch (e) {
    alert('База недоступна: ' + e.message);
    return false;
  }
}

async function adminToggleBan(nick) {
  const me = adminCanAct();
  if (!me || isAdminNick(nick) || nick.toLowerCase() === me.nick.toLowerCase()) return;
  const row = adminFind(nick);
  if (row && row.banned) {
    await adminRun('unban', nick, '');
    return;
  }
  const reason = prompt(`Причина бана для «${nick}» (необязательно):`, '');
  if (reason === null) return;
  await adminRun('ban', nick, reason.trim());
}

async function adminToggleMute(nick) {
  const me = adminCanAct();
  if (!me || isAdminNick(nick) || nick.toLowerCase() === me.nick.toLowerCase()) return;
  const row = adminFind(nick);
  if (row && row.muted) {
    await adminRun('unmute', nick, '');
    return;
  }
  const reason = prompt(`Причина мута для «${nick}» (необязательно):`, '');
  if (reason === null) return;
  await adminRun('mute', nick, reason.trim());
}

async function adminToggleRole(nick) {
  const me = adminCanAct();
  if (!me || isAdminNick(nick)) return;
  const row = adminFind(nick);
  const makeAdmin = !(row && row.role === 'admin');
  await adminRun(makeAdmin ? 'promote' : 'demote', nick, '');
}

async function adminDelete(nick) {
  const me = adminCanAct();
  if (!me || isAdminNick(nick)) return;
  if (!confirm(`Удалить аккаунт «${nick}»?`)) return;
  await adminRun('delete', nick, '');
}

/* ---------- инициализация ---------- */
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAccount();
});

initSession();
