import { Move, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { useId, useRef } from "react";

import { Button } from "@/components/ui/button";
import { avatarCropRect, clampAvatarCrop, DEFAULT_AVATAR_CROP, type AvatarCrop, type AvatarSource } from "@/lib/avatar";

export function AvatarEditor({
  source,
  crop,
  onChange,
}: {
  source: AvatarSource;
  crop: AvatarCrop;
  onChange: (crop: AvatarCrop) => void;
}) {
  const hintId = useId();
  const sliderId = useId();
  const drag = useRef<{ id: number; x: number; y: number; crop: AvatarCrop; width: number } | null>(null);
  const valid = clampAvatarCrop(source, crop);
  const rect = avatarCropRect(source, valid);
  const update = (value: AvatarCrop) => onChange(clampAvatarCrop(source, value));
  const imageStyle = {
    width: `${(source.width / rect.side) * 100}%`,
    height: `${(source.height / rect.side) * 100}%`,
    left: `${(-rect.x / rect.side) * 100}%`,
    top: `${(-rect.y / rect.side) * 100}%`,
  };
  return (
    <section
      aria-label="Настройка фотографии"
      className="grid min-w-0 gap-3 rounded-lg border border-line bg-surface-2/40 p-3"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-[13px] font-semibold">
          <Move className="size-4 text-accent-ink" />
          Выберите кадр
        </h3>
        <div
          className="relative size-10 shrink-0 overflow-hidden rounded-full border border-line"
          aria-label="Предпросмотр аватара"
          role="img"
        >
          <img
            src={source.url}
            alt=""
            draggable={false}
            className="pointer-events-none absolute max-w-none"
            style={imageStyle}
          />
        </div>
      </div>
      <div
        role="group"
        aria-label="Область кадрирования"
        aria-describedby={hintId}
        tabIndex={0}
        className="relative mx-auto aspect-square w-full max-w-64 touch-none cursor-grab overflow-hidden rounded-md bg-bg outline-none select-none active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-accent"
        onPointerDown={(event) => {
          if (event.button !== 0 || !event.isPrimary) return;
          event.preventDefault();
          event.currentTarget.focus({ preventScroll: true });
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            id: event.pointerId,
            x: event.clientX,
            y: event.clientY,
            crop: valid,
            width: event.currentTarget.getBoundingClientRect().width,
          };
        }}
        onPointerMove={(event) => {
          const start = drag.current;
          if (!start || start.id !== event.pointerId) return;
          const side = Math.min(source.width, source.height) / start.crop.zoom;
          update({
            ...start.crop,
            x: start.crop.x - (((event.clientX - start.x) / start.width) * side) / source.width,
            y: start.crop.y - (((event.clientY - start.y) / start.width) * side) / source.height,
          });
        }}
        onPointerUp={(event) => {
          if (drag.current?.id !== event.pointerId) return;
          drag.current = null;
          event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onLostPointerCapture={() => {
          drag.current = null;
        }}
        onKeyDown={(event) => {
          const direction = { ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[event.key];
          if (!direction) return;
          event.preventDefault();
          const step = event.shiftKey ? 0.1 : 0.025;
          update({
            ...valid,
            x: valid.x + ((direction[0]! * rect.side) / source.width) * step,
            y: valid.y + ((direction[1]! * rect.side) / source.height) * step,
          });
        }}
      >
        <img
          src={source.url}
          alt="Фотография сотрудника"
          draggable={false}
          className="pointer-events-none absolute max-w-none"
          style={imageStyle}
        />
        <div className="pointer-events-none absolute inset-0 rounded-full border border-white/70 shadow-[0_0_0_100px_rgb(0_0_0/45%)]" />
      </div>
      <p id={hintId} className="text-[12px] leading-relaxed text-ink-3">
        Перетащите фото мышью или пальцем. Можно выделить рамку и двигать фото стрелками.
      </p>
      <div className="flex items-center justify-between text-[12px]">
        <label htmlFor={sliderId} className="font-medium">
          Масштаб фото
        </label>
        <span className="text-ink-3 tnum">{Math.round(valid.zoom * 100)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Уменьшить фото"
          disabled={valid.zoom <= 1}
          onClick={() => update({ ...valid, zoom: valid.zoom - 0.1 })}
        >
          <ZoomOut />
        </Button>
        <input
          id={sliderId}
          type="range"
          min={1}
          max={4}
          step={0.05}
          value={valid.zoom}
          className="h-5 min-w-0 flex-1 accent-accent"
          onChange={(event) => update({ ...valid, zoom: Number(event.target.value) })}
        />
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Увеличить фото"
          disabled={valid.zoom >= 4}
          onClick={() => update({ ...valid, zoom: valid.zoom + 0.1 })}
        >
          <ZoomIn />
        </Button>
      </div>
      <Button size="sm" variant="ghost" className="w-fit" onClick={() => onChange({ ...DEFAULT_AVATAR_CROP })}>
        <RotateCcw />
        Сбросить кадр
      </Button>
    </section>
  );
}
