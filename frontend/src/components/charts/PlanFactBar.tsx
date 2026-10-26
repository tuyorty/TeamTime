/**
 * Столбик «контур + заливка» для Recharts: внешнее значение — контуром, внутреннее — узкой заливкой
 * строго по центру. Та же грамматика, что у полосы дня (план контуром, факт заливкой).
 *
 * Два отдельных <Bar> с отрицательным barGap выравниваются по левому краю и разъезжаются,
 * когда столбиков много, поэтому оба значения рисуются одной фигурой. Бар строится по ключу
 * `outer` = max(контур, заливка), а высоты пересчитываются из его масштаба.
 */
export type PlanFactRow = { outer: number; missing?: boolean };

type ShapeProps = {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: Record<string, unknown>;
};

/** Прямоугольник со скруглёнными верхними углами; без нижней грани, если `open`. */
function topRounded(x: number, y: number, w: number, h: number, r: number, open = false) {
  const rr = Math.max(0, Math.min(r, w / 2, h));
  const path = `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h}`;
  return open ? path : `${path} Z`;
}

export function planFactShape({
  outlineKey,
  fillKey,
  outlineColor,
  fillColor,
  fillRatio = 0.5,
  radius = 3,
}: {
  outlineKey: string;
  fillKey: string;
  outlineColor: string;
  fillColor: string;
  /** Ширина заливки относительно контура. */
  fillRatio?: number;
  radius?: number;
}) {
  return function PlanFactShape({ x = 0, y = 0, width = 0, height = 0, payload }: ShapeProps) {
    const outer = Number(payload?.outer ?? 0);
    if (!outer || height <= 0 || width <= 0) return <g />;
    const k = height / outer;
    const base = y + height;
    const outlineH = Number(payload?.[outlineKey] ?? 0) * k;
    const fillH = Number(payload?.[fillKey] ?? 0) * k;
    const fillW = Math.max(2, Math.round(width * fillRatio));
    const fillX = x + (width - fillW) / 2;
    return (
      <g>
        {outlineH > 0 ? (
          <path
            d={topRounded(x + 0.5, base - outlineH + 0.5, width - 1, outlineH - 0.5, radius, true)}
            fill="none"
            stroke={outlineColor}
            strokeWidth={1}
            strokeDasharray={payload?.missing ? "3 2" : undefined}
          />
        ) : null}
        {fillH > 0 ? (
          <path d={topRounded(fillX, base - fillH, fillW, fillH, Math.min(radius, fillW / 2))} fill={fillColor} />
        ) : null}
      </g>
    );
  };
}
