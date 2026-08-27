export type ChatImageLightboxPoint = {
  x: number;
  y: number;
};

export type ChatImageLightboxSize = {
  width: number;
  height: number;
};

/** Fits an image into the available lightbox stage while preserving its aspect ratio. */
export function fitChatImageToStage(
  stage: ChatImageLightboxSize,
  image: ChatImageLightboxSize,
): ChatImageLightboxSize {
  if (stage.width <= 0 || stage.height <= 0 || image.width <= 0 || image.height <= 0) {
    return { width: 0, height: 0 };
  }
  const scale = Math.min(stage.width / image.width, stage.height / image.height);
  return {
    width: image.width * scale,
    height: image.height * scale,
  };
}

/** Clamps dragging so the fitted image cannot be moved irrecoverably outside the lightbox stage. */
export function clampChatImageOffset(
  offset: ChatImageLightboxPoint,
  stage: ChatImageLightboxSize,
  image: ChatImageLightboxSize,
  zoom: number,
): ChatImageLightboxPoint {
  if (stage.width <= 0 || stage.height <= 0 || image.width <= 0 || image.height <= 0 || zoom <= 0) {
    return { x: 0, y: 0 };
  }

  const scaledWidth = image.width * zoom;
  const scaledHeight = image.height * zoom;
  const maxOffsetX = Math.abs(stage.width - scaledWidth) / 2;
  const maxOffsetY = Math.abs(stage.height - scaledHeight) / 2;

  return {
    x: Math.min(maxOffsetX, Math.max(-maxOffsetX, offset.x)),
    y: Math.min(maxOffsetY, Math.max(-maxOffsetY, offset.y)),
  };
}
