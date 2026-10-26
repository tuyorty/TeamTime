#!/usr/bin/env node
// Проверка контраста пар «текст/фон» в обеих темах. Значения читаются из src/index.css,
// поэтому дизайн-токены и проверка не расходятся. Используется в CI: `npm run contrast`.
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");

function block(selector) {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`Нет блока ${selector}`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/gi)].map((m) => [m[1], m[2]]));
}

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// [текст, фон, минимум]. 4.5 — обычный текст, 3 — крупный текст, иконки и границы метрик.
const PAIRS = [
  ["ink", "bg", 7], ["ink", "surface", 7], ["ink", "surface-2", 7], ["ink", "surface-3", 4.5],
  ["ink-2", "surface", 4.5], ["ink-2", "bg", 4.5], ["ink-2", "surface-2", 4.5],
  ["ink-3", "surface", 4.5], ["ink-3", "bg", 4.5], ["ink-3", "surface-2", 4.5],
  ["accent-ink", "surface", 4.5], ["accent-ink", "accent-soft", 4.5], ["on-accent", "accent", 4.5],
  ["late-ink", "surface", 4.5], ["late-ink", "late-soft", 4.5],
  ["absence-ink", "surface", 4.5], ["absence-ink", "absence-soft", 4.5],
  ["deviation-ink", "surface", 4.5], ["deviation-ink", "deviation-soft", 4.5],
  ["accent", "surface", 3], ["late", "surface", 3], ["absence", "surface", 3], ["deviation", "surface", 3],
  ["ink-3", "surface", 3],
];

let failed = 0;
for (const [name, selector] of [["светлая", ":root"], ["тёмная", ".dark"]]) {
  const t = block(selector);
  console.log(`\nТема: ${name}`);
  for (const [fg, bg, min] of PAIRS) {
    if (!t[fg] || !t[bg]) throw new Error(`Нет токена ${fg} или ${bg} в ${selector}`);
    const r = ratio(t[fg], t[bg]);
    const ok = r >= min;
    if (!ok) failed++;
    console.log(`  ${ok ? "✓" : "✗"} ${fg.padEnd(14)} на ${bg.padEnd(14)} ${r.toFixed(2).padStart(5)} (нужно ${min})`);
  }
}
if (failed) {
  console.error(`\nНе прошли проверку: ${failed}`);
  process.exit(1);
}
console.log("\nВсе пары проходят.");
