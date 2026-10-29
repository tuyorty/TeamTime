import { describe, expect, it } from "vitest";

import { avatarCropRect, clampAvatarCrop, DEFAULT_AVATAR_CROP } from "./avatar";

describe("кадр фотографии", () => {
  it("сохраняет квадрат по центру горизонтального снимка", () => {
    expect(avatarCropRect({ width: 1200, height: 800 }, DEFAULT_AVATAR_CROP)).toEqual({ x: 200, y: 0, side: 800 });
  });

  it("приближает и сдвигает кадр к краю вертикального снимка", () => {
    expect(avatarCropRect({ width: 800, height: 1200 }, { zoom: 2, x: 1, y: 0 })).toEqual({ x: 400, y: 0, side: 400 });
  });

  it("не допускает пустых полей и выхода масштаба за границы", () => {
    expect(clampAvatarCrop({ width: 1200, height: 800 }, { zoom: 0.2, x: -5, y: 20 })).toEqual({
      zoom: 1,
      x: 1 / 3,
      y: 0.5,
    });
    expect(avatarCropRect({ width: 800, height: 800 }, { zoom: 20, x: -1, y: 2 })).toEqual({ x: 0, y: 600, side: 200 });
  });
});
