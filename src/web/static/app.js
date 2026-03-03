/* Beacon Dashboard — vanilla JS */
'use strict';

// ── Theme toggle ────────────────────────────────────────────────────────────
const THEME_KEY = 'beacon-theme';

function getStoredTheme() {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}
function storeTheme(t) {
  try { localStorage.setItem(THEME_KEY, t); } catch { /* ignore */ }
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const icon = document.getElementById('themeIcon');
  if (icon) icon.textContent = theme === 'dark' ? '☽' : '☀';
}

function initTheme() {
  const stored = getStoredTheme();
  const preferred = stored || (
    window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  );
  applyTheme(preferred);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  storeTheme(next);
}

// ── Footer clock ────────────────────────────────────────────────────────────
function updateFooterTime() {
  const el = document.getElementById('footerTime');
  if (!el) return;
  const now = new Date();
  const h = String(now.getUTCHours()).padStart(2, '0');
  const m = String(now.getUTCMinutes()).padStart(2, '0');
  const s = String(now.getUTCSeconds()).padStart(2, '0');
  el.textContent = `${h}:${m}:${s} UTC`;
}

// ── Auto-refresh ─────────────────────────────────────────────────────────────
// On /dashboard and /briefing, quietly refresh the page every 5 minutes
// so the data stays current after a sync.
const AUTO_REFRESH_ROUTES = ['/dashboard', '/briefing'];
const AUTO_REFRESH_MS = 5 * 60 * 1000;

function maybeStartAutoRefresh() {
  const path = window.location.pathname;
  if (AUTO_REFRESH_ROUTES.includes(path)) {
    setTimeout(() => window.location.reload(), AUTO_REFRESH_MS);
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  const toggleBtn = document.getElementById('themeToggle');
  if (toggleBtn) toggleBtn.addEventListener('click', toggleTheme);

  updateFooterTime();
  setInterval(updateFooterTime, 1000);

  maybeStartAutoRefresh();
});
