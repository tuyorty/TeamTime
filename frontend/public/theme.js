// Тема ставится до первой отрисовки, чтобы не мигал светлый фон. Отдельный файл, а не
// встроенный скрипт: политика CSP разрешает только скрипты с самого сайта.
try {
  const t = localStorage.getItem("tt-theme");
  const dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
} catch {}
