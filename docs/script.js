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
