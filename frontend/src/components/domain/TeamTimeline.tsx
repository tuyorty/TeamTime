import { useEffect, useRef, useState, type ReactNode } from "react";

import type { Axis } from "@/lib/axis";
import { cn } from "@/lib/cn";
import { clock } from "@/lib/format";

/** Один маркер на всю команду, выровненный по фактической колонке полос расписания. */
export function TeamTimeline({ children, axis, now, className }: {
  children: ReactNode;
  axis: Axis;
  now?: number | null;
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [track, setTrack] = useState<{ left: number; width: number } | null>(null);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const measure = () => {
      const strip = element.querySelector<HTMLElement>("[data-timeline-track]");
      if (!strip) { setTrack(null); return; }
      const parent = element.getBoundingClientRect();
      const bounds = strip.getBoundingClientRect();
      setTrack({ left: bounds.left - parent.left, width: bounds.width });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    const strip = element.querySelector<HTMLElement>("[data-timeline-track]");
    if (strip) observer.observe(strip);
    return () => observer.disconnect();
  }, [children]);
  const position = now == null ? null : (now - axis.start) / (axis.end - axis.start);
  return <div ref={host} className={cn("relative", className)}>
    {children}
    {track && position !== null && position >= 0 && position <= 1 ? <div
      className="team-now-line"
      data-testid="team-now-line"
      role="img"
      aria-label={`Текущее время: ${clock(now)}`}
      style={{ left: track.left + track.width * position }}
    /> : null}
  </div>;
}
