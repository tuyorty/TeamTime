export type AvatarSource = { url: string; width: number; height: number };
export type AvatarCrop = { zoom: number; x: number; y: number };
export const DEFAULT_AVATAR_CROP: AvatarCrop = { zoom: 1, x: 0.5, y: 0.5 };

/** Ограничиваем центр так, чтобы рамка всегда была заполнена фотографией. */
export function clampAvatarCrop(source: Pick<AvatarSource, "width" | "height">, crop: AvatarCrop): AvatarCrop {
  const zoom = Math.max(1, Math.min(4, crop.zoom));
  const side = Math.min(source.width, source.height) / zoom;
  const marginX = side / source.width / 2;
  const marginY = side / source.height / 2;
  return {
    zoom,
    x: Math.max(marginX, Math.min(1 - marginX, crop.x)),
    y: Math.max(marginY, Math.min(1 - marginY, crop.y)),
  };
}

export function avatarCropRect(source: Pick<AvatarSource, "width" | "height">, crop: AvatarCrop) {
  const valid = clampAvatarCrop(source, crop);
  const side = Math.min(source.width, source.height) / valid.zoom;
  return { x: valid.x * source.width - side / 2, y: valid.y * source.height - side / 2, side };
}

/** Подготавливаем весь снимок для редактора, сохраняя возможность выбрать другую область. */
export async function loadAvatar(file: File): Promise<AvatarSource> {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    throw new Error("Выберите фотографию JPEG, PNG или WebP.");
  }
  if (file.size > 10 * 1024 * 1024) throw new Error("Фотография должна быть меньше 10 МБ.");
  const bitmap = await createImageBitmap(file).catch(() => {
    throw new Error("Не удалось прочитать фотографию. Выберите другой файл.");
  });
  try {
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Не удалось обработать фотографию.");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return { url: canvas.toDataURL("image/jpeg", 0.92), width: canvas.width, height: canvas.height };
  } finally {
    bitmap.close();
  }
}

export async function readAvatar(url: string): Promise<AvatarSource> {
  const image = new Image();
  image.src = url;
  await image.decode().catch(() => {
    throw new Error("Не удалось прочитать фотографию. Выберите другой файл.");
  });
  return { url, width: image.naturalWidth, height: image.naturalHeight };
}

/** Сохраняем только выбранный квадрат 256 × 256, исходный снимок на сервер не уходит. */
export async function prepareAvatar(source: AvatarSource, crop: AvatarCrop): Promise<string> {
  const image = new Image();
  image.src = source.url;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Не удалось обработать фотографию.");
  const rect = avatarCropRect(source, crop);
  context.fillStyle = "#fff";
  context.fillRect(0, 0, 256, 256);
  context.drawImage(image, rect.x, rect.y, rect.side, rect.side, 0, 0, 256, 256);
  return canvas.toDataURL("image/jpeg", 0.85);
}
