const THEMES = ["system", "light", "dark"];
function normalizeTheme(value) { return THEMES.includes(value) ? value : "system"; }
function nextTheme(value) { const current = normalizeTheme(value); return THEMES[(THEMES.indexOf(current) + 1) % THEMES.length]; }
function applyTheme(value, root = document.documentElement) { const theme = normalizeTheme(value); root.dataset.theme = theme; root.style.colorScheme = theme === "system" ? "light dark" : theme; return theme; }
if (typeof module !== "undefined") module.exports = { THEMES, normalizeTheme, nextTheme, applyTheme };
if (typeof window !== "undefined") window.marketIntelTheme = { THEMES, normalizeTheme, nextTheme, applyTheme };
