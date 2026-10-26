/** Цвета для Recharts из CSS-токенов (SVG-атрибутам нужны значения, а не классы). */
export const chart = {
  accent: "var(--accent)",
  late: "var(--late)",
  absence: "var(--absence)",
  deviation: "var(--deviation)",
  ink2: "var(--ink-2)",
  ink3: "var(--ink-3)",
  line: "var(--line)",
  surface: "var(--surface)",
  surface2: "var(--surface-2)",
};

export const axisProps = {
  stroke: "var(--line)",
  tick: { fill: "var(--ink-3)", fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;
