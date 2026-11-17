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

function isAdminNick(nick) {
  const low = String(nick || '').toLowerCase();
  return ADMINS.some((a) => a.toLowerCase() === low);
}

function isMainAdmin(nick) {
  return String(nick || '').toLowerCase() === ADMINS[0].toLowerCase();
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
  };
  if (!pdSave(data)) return setMsg('Не удалось сохранить данные (localStorage)', 'error');

  localStorage.setItem(SESSION_KEY, nick);
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
    me.role === 'admin' ? '<span class="role-badge admin">ADMIN</span>' : '<span class="role-badge">PLAYER</span>';

  const adminPanel = document.getElementById('admin-panel');
  adminPanel.classList.toggle('hidden', me.role !== 'admin');
  document.getElementById('user-note').textContent =
    me.role === 'admin'
      ? (isMainAdmin(me.nick)
          ? 'Ты главный администратор: полный доступ к аккаунтам и ролям.'
          : 'Ты администратор: можешь выдавать роли и удалять аккаунты.')
      : 'Ты вошёл как игрок.';

  if (me.role === 'admin') renderAdmin();
}

function renderAdmin() {
  const data = pdLoad();
  const me = localStorage.getItem(SESSION_KEY) || '';
  const keys = Object.keys(data.players).sort((a, b) => {
    const rank = (nick) => (isMainAdmin(nick) ? 0 : roleOf(nick, data.players[nick]) === 'admin' ? 1 : 2);
    const diff = rank(a) - rank(b);
    return diff !== 0 ? diff : a.localeCompare(b);
  });

  const tbody = document.getElementById('admin-players');
  if (!tbody) return;

  tbody.innerHTML = keys
    .map((nick) => {
      const player = data.players[nick];
      const role = roleOf(nick, player);
      const isFixed = isAdminNick(nick);
      const actions = isFixed
        ? `<span class="auth-note">${isMainAdmin(nick) ? 'главный админ' : 'админ сайта'}</span>`
        : `<button class="mini-btn" onclick="adminToggleRole('${escapeHtml(nick)}')">${
            role === 'admin' ? 'Снять админа' : 'Сделать админом'
          }</button>` +
          `<button class="mini-btn danger" onclick="adminDelete('${escapeHtml(nick)}')">Удалить</button>`;

      return `<tr class="${nick === me ? 'is-me' : ''}">
        <td>${escapeHtml(nick)}</td>
        <td><span class="role-badge ${role === 'admin' ? 'admin' : ''}">${role.toUpperCase()}</span></td>
        <td>${escapeHtml(player.created || '—')}</td>
        <td>${escapeHtml(player.lastLogin || '—')}</td>
        <td class="admin-actions">${actions}</td>
      </tr>`;
    })
    .join('');

  document.getElementById('admin-count').textContent = keys.length;
}

function adminToggleRole(nick) {
  if (!currentPlayer() || currentPlayer().role !== 'admin') return;
  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key || isAdminNick(key)) return;
  data.players[key].role = roleOf(key, data.players[key]) === 'admin' ? 'player' : 'admin';
  pdSave(data);
  renderAdmin();
}

function adminDelete(nick) {
  const me = currentPlayer();
  if (!me || me.role !== 'admin') return;
  if (isAdminNick(nick)) return;
  if (!confirm(`Удалить аккаунт «${nick}»?`)) return;

  const data = pdLoad();
  const key = findPlayerKey(data.players, nick);
  if (!key) return;
  delete data.players[key];
  pdSave(data);
  if (localStorage.getItem(SESSION_KEY) === key) localStorage.removeItem(SESSION_KEY);
  refreshAccountUI();
}

/* ---------- инициализация ---------- */
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAccount();
});

document.addEventListener('DOMContentLoaded', refreshAccountUI);
refreshAccountUI();
