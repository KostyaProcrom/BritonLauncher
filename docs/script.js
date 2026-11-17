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
//  PlayerDATA — аккаунты и роли (хранятся в localStorage)
// =========================================================
const PD_KEY = 'britonlauncher.playerdata';
const SESSION_KEY = 'britonlauncher.session';
const ADMINS = ['KostyaKosmos', 'BritonLauncher'];
// Подпись кода для лаунчера. Секрет виден в исходниках сайта — это защита от
// случайной подмены, а не настоящая серверная авторизация.
const LAUNCHER_SECRET = '577b977f8870b4a173026dc3ca5962300ad353f38cb0a4ba9464b41f4daba6b3';

function isAdminNick(nick) {
  const low = String(nick || '').toLowerCase();
  return ADMINS.some((a) => a.toLowerCase() === low);
}

function pdLoad() {
  try {
    const raw = localStorage.getItem(PD_KEY);
    const data = raw ? JSON.parse(raw) : null;
    if (data && data.players && typeof data.players === 'object') return data;
  } catch (e) {}
  return { players: {} };
}

function pdSave(data) {
  try {
    localStorage.setItem(PD_KEY, JSON.stringify(data));
    return true;
  } catch (e) {
    return false;
  }
}

function findPlayerKey(players, nick) {
  const low = String(nick || '').toLowerCase();
  return Object.keys(players).find((k) => k.toLowerCase() === low) || null;
}

function isMainAdmin(nick) {
  return String(nick || '').toLowerCase() === ADMINS[0].toLowerCase();
}

/* ---------- код для лаунчера ---------- */
function b64url(bytes) {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function makeLauncherCode() {
  const me = currentPlayer();
  if (!me) return;
  if (!crypto?.subtle) return;

  const status = document.getElementById('launcher-code-status');
  if (isBanned(me.player)) {
    if (status) status.textContent = 'Аккаунт забанен: ' + (me.player.banReason || 'без причины');
    return;
  }
  if (status) status.textContent = 'Генерация...';

  const payload = {
    n: me.nick,
    r: me.role,
    m: isMainAdmin(me.nick) ? 1 : 0,
    mu: isMuted(me.player) ? 1 : 0,
    t: Date.now(),
  };
  const payloadB64 = b64url(new TextEncoder().encode(JSON.stringify(payload)));
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(LAUNCHER_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payloadB64));
  const code = 'BLS1.' + payloadB64 + '.' + b64url(new Uint8Array(sig));

  document.getElementById('launcher-code').value = code;
  document.getElementById('launcher-code-result').classList.remove('hidden');
  if (status) status.textContent = 'Код действует 7 дней.';
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

function roleOf(nick, player) {
  if (isAdminNick(nick)) return 'admin';
  return player && player.role === 'admin' ? 'admin' : 'player';
}

function randomSalt() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function hashPassword(password, salt) {
  const enc = new TextEncoder().encode(salt + ':' + password);
  const buf = await crypto.subtle.digest('SHA-256', enc);
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function currentPlayer() {
  const nick = localStorage.getItem(SESSION_KEY);
  if (!nick) return null;
  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key) {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
  return { nick: key, role: roleOf(key, data.players[key]), player: data.players[key] };
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
  if (!crypto?.subtle) return setMsg('Браузер не поддерживает шифрование', 'error');

  const nick = (document.getElementById('reg-nick').value || '').trim();
  const pass = document.getElementById('reg-pass').value || '';
  const pass2 = document.getElementById('reg-pass2').value || '';

  if (!/^[A-Za-z0-9_]{3,16}$/.test(nick)) {
    return setMsg('Ник: 3–16 символов (латиница, цифры, _)', 'error');
  }
  if (pass.length < 4) return setMsg('Пароль должен быть минимум 4 символа', 'error');
  if (pass !== pass2) return setMsg('Пароли не совпадают', 'error');

  const data = pdLoad();
  if (findPlayerKey(data.players, nick)) return setMsg('Этот ник уже занят', 'error');

  const salt = randomSalt();
  const hash = await hashPassword(pass, salt);
  data.players[nick] = {
    salt,
    hash,
    role: isAdminNick(nick) ? 'admin' : 'player',
    created: new Date().toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }),
    lastLogin: '—',
    banned: false,
    muted: false,
  };
  if (!pdSave(data)) return setMsg('Не удалось сохранить данные (localStorage)', 'error');

  localStorage.setItem(SESSION_KEY, nick);
  adminLog('register', nick, '');
  document.getElementById('form-register').reset();
  setMsg('');
  refreshAccountUI();
}

async function doLogin(event) {
  event.preventDefault();
  if (!crypto?.subtle) return setMsg('Браузер не поддерживает шифрование', 'error');

  const nick = (document.getElementById('login-nick').value || '').trim();
  const pass = document.getElementById('login-pass').value || '';
  if (!nick || !pass) return setMsg('Введи ник и пароль', 'error');

  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key) return setMsg('Аккаунт не найден. Зарегистрируйся.', 'error');

  const player = data.players[key];
  const hash = await hashPassword(pass, player.salt || '');
  if (hash !== player.hash) return setMsg('Неверный пароль', 'error');
  if (isBanned(player)) {
    return setMsg('Аккаунт забанен: ' + (player.banReason || 'без причины'), 'error');
  }

  player.lastLogin = new Date().toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
  player.role = isAdminNick(key) ? 'admin' : player.role || 'player';
  pdSave(data);

  localStorage.setItem(SESSION_KEY, key);
  document.getElementById('form-login').reset();
  setMsg('');
  refreshAccountUI();
}

function doLogout() {
  localStorage.removeItem(SESSION_KEY);
  switchTab('login');
  refreshAccountUI();
}

/* ---------- отрисовка ---------- */
function refreshAccountUI() {
  const guest = document.getElementById('account-guest');
  const user = document.getElementById('account-user');
  const navBtn = document.getElementById('nav-account');
  if (!guest || !user) return;

  const me = currentPlayer();

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
    (isBanned(me.player) ? ' <span class="status-badge banned">ЗАБАНЕН</span>' : '') +
    (isMuted(me.player) ? ' <span class="status-badge muted">МУТ</span>' : '');

  document.getElementById('launcher-code-box').classList.toggle('hidden', isBanned(me.player));

  const adminPanel = document.getElementById('admin-panel');
  adminPanel.classList.toggle('hidden', me.role !== 'admin');

  let note = '';
  if (isBanned(me.player)) {
    note = 'Аккаунт забанен: ' + (me.player.banReason || 'без причины') + '. Вход в лаунчер и получение кода недоступны.';
  } else if (me.role === 'admin') {
    note = isMainAdmin(me.nick)
      ? 'Ты главный администратор: полный доступ к аккаунтам, банам и мутам.'
      : 'Ты администратор: можешь выдавать роли, банить, мутить и удалять аккаунты.';
    if (isMuted(me.player)) note += ' На тебе мут.';
  } else {
    note = isMuted(me.player) ? 'Ты вошёл как игрок. Действует мут.' : 'Ты вошёл как игрок.';
  }
  document.getElementById('user-note').textContent = note;

  if (me.role === 'admin') renderAdmin();
}

/* ---------- статусы, журнал и админ-действия ---------- */
function isBanned(player) {
  return !!(player && player.banned);
}

function isMuted(player) {
  return !!(player && player.muted);
}

function nowStr() {
  return new Date().toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
}

const LOG_LABELS = {
  register: 'зарегистрировался',
  ban: 'забанил',
  unban: 'разбанил',
  mute: 'замутил',
  unmute: 'размутил',
  promote: 'выдал админа',
  demote: 'снял админа',
  delete: 'удалил',
};

function adminLog(action, nick, extra) {
  const data = pdLoad();
  if (!Array.isArray(data.log)) data.log = [];
  const me = currentPlayer();
  data.log.unshift({
    at: nowStr(),
    by: me ? me.nick : '—',
    action,
    nick: nick || '',
    extra: extra || '',
  });
  data.log = data.log.slice(0, 60);
  pdSave(data);
}

function renderAdminLog(data) {
  const list = document.getElementById('admin-log-list');
  if (!list) return;
  const log = Array.isArray(data.log) ? data.log : [];
  if (!log.length) {
    list.innerHTML = '<li class="admin-log-empty">Пока пусто.</li>';
    return;
  }
  list.innerHTML = log
    .map((e) => {
      const label = LOG_LABELS[e.action] || e.action;
      const target = e.action === 'register' || !e.nick ? '' : ' <b>' + escapeHtml(e.nick) + '</b>';
      const extra = e.extra ? ' <span class="log-extra">(' + escapeHtml(e.extra) + ')</span>' : '';
      return `<li><span class="log-time">${escapeHtml(e.at)}</span> <b>${escapeHtml(e.by)}</b> ${label}${target}${extra}</li>`;
    })
    .join('');
}

function renderAdmin() {
  const data = pdLoad();
  const me = localStorage.getItem(SESSION_KEY) || '';
  const query = (document.getElementById('admin-search')?.value || '').trim().toLowerCase();
  const all = Object.keys(data.players);
  const keys = all
    .filter((nick) => !query || nick.toLowerCase().includes(query))
    .sort((a, b) => {
      const rank = (nick) => (isMainAdmin(nick) ? 0 : roleOf(nick, data.players[nick]) === 'admin' ? 1 : 2);
      const diff = rank(a) - rank(b);
      return diff !== 0 ? diff : a.localeCompare(b);
    });

  const tbody = document.getElementById('admin-players');
  if (!tbody) return;

  tbody.innerHTML = keys.length
    ? keys
        .map((nick) => {
          const player = data.players[nick] || {};
          const role = roleOf(nick, player);
          const banned = isBanned(player);
          const muted = isMuted(player);
          const isFixed = isAdminNick(nick);
          const isSelf = nick.toLowerCase() === me.toLowerCase();

          const status = banned
            ? `<span class="status-badge banned" title="${escapeHtml(player.banReason || '')}">ЗАБАНЕН</span>`
            : muted
              ? `<span class="status-badge muted" title="${escapeHtml(player.muteReason || '')}">МУТ</span>`
              : '<span class="status-badge active">АКТИВЕН</span>';

          let actions;
          if (isFixed) {
            actions = `<span class="auth-note">${isMainAdmin(nick) ? 'главный админ' : 'админ сайта'}</span>`;
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

  document.getElementById('admin-count').textContent = all.length;
  document.getElementById('admin-admins').textContent = all.filter((n) => roleOf(n, data.players[n]) === 'admin').length;
  document.getElementById('admin-bans').textContent = all.filter((n) => isBanned(data.players[n])).length;
  document.getElementById('admin-mutes').textContent = all.filter((n) => isMuted(data.players[n])).length;

  renderAdminLog(data);
}

function adminCanAct() {
  const me = currentPlayer();
  return me && me.role === 'admin' ? me : null;
}

function adminToggleBan(nick) {
  const me = adminCanAct();
  if (!me) return;
  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key || isAdminNick(key) || key.toLowerCase() === me.nick.toLowerCase()) return;
  const player = data.players[key];

  if (isBanned(player)) {
    player.banned = false;
    delete player.banReason;
    delete player.bannedAt;
    delete player.bannedBy;
    pdSave(data);
    adminLog('unban', key, '');
  } else {
    const reason = prompt(`Причина бана для «${key}» (необязательно):`, '');
    if (reason === null) return;
    player.banned = true;
    player.banReason = reason.trim() || 'без причины';
    player.bannedAt = nowStr();
    player.bannedBy = me.nick;
    pdSave(data);
    adminLog('ban', key, player.banReason);
    if (localStorage.getItem(SESSION_KEY) === key) localStorage.removeItem(SESSION_KEY);
  }
  refreshAccountUI();
}

function adminToggleMute(nick) {
  const me = adminCanAct();
  if (!me) return;
  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key || isAdminNick(key) || key.toLowerCase() === me.nick.toLowerCase()) return;
  const player = data.players[key];

  if (isMuted(player)) {
    player.muted = false;
    delete player.muteReason;
    delete player.mutedAt;
    delete player.mutedBy;
    pdSave(data);
    adminLog('unmute', key, '');
  } else {
    const reason = prompt(`Причина мута для «${key}» (необязательно):`, '');
    if (reason === null) return;
    player.muted = true;
    player.muteReason = reason.trim() || 'без причины';
    player.mutedAt = nowStr();
    player.mutedBy = me.nick;
    pdSave(data);
    adminLog('mute', key, player.muteReason);
  }
  refreshAccountUI();
}

function adminToggleRole(nick) {
  const me = adminCanAct();
  if (!me) return;
  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key || isAdminNick(key)) return;
  const makeAdmin = roleOf(key, data.players[key]) !== 'admin';
  data.players[key].role = makeAdmin ? 'admin' : 'player';
  pdSave(data);
  adminLog(makeAdmin ? 'promote' : 'demote', key, '');
  refreshAccountUI();
}

function adminDelete(nick) {
  const me = adminCanAct();
  if (!me) return;
  if (isAdminNick(nick)) return;
  if (!confirm(`Удалить аккаунт «${nick}»?`)) return;

  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key) return;
  delete data.players[key];
  pdSave(data);
  adminLog('delete', key, '');
  if (localStorage.getItem(SESSION_KEY) === key) localStorage.removeItem(SESSION_KEY);
  refreshAccountUI();
}

/* ---------- инициализация ---------- */
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAccount();
});

document.addEventListener('DOMContentLoaded', refreshAccountUI);
refreshAccountUI();
