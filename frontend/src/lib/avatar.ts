/** Уменьшаем фотографию перед сохранением, чтобы не хранить полноразмерный снимок в профиле. */
export async function prepareAvatar(file: File): Promise<string> {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    throw new Error("Выберите фотографию JPEG, PNG или WebP.");
  }
  if (file.size > 10 * 1024 * 1024) throw new Error("Фотография должна быть меньше 10 МБ.");
  const bitmap = await createImageBitmap(file).catch(() => {
    throw new Error("Не удалось прочитать фотографию. Выберите другой файл.");
  });
  try {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Не удалось обработать фотографию.");
    const side = Math.min(bitmap.width, bitmap.height);
    context.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, 256, 256);
    return canvas.toDataURL("image/jpeg", 0.85);
  } finally {
    bitmap.close();
  }
}
