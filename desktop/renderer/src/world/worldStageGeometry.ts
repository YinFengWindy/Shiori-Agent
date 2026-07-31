export const worldStageSize = Object.freeze({ width: 1920, height: 1080 });

/** Central region that must remain readable across window aspect ratios. */
export const worldStageSafeArea = Object.freeze({ x: 160, y: 90, width: 1600, height: 900 });

export type WorldStageViewport = {
  scale: number;
  offsetX: number;
  offsetY: number;
  renderedWidth: number;
  renderedHeight: number;
};

export type WorldStageRect = {
  x: number;
  y: number;
  width: number;
  height: number;
  scale: number;
};

/** Fits the logical stage inside a viewport while preserving its aspect ratio. */
export function fitWorldStage(viewportWidth: number, viewportHeight: number): WorldStageViewport {
  if (viewportWidth <= 0 || viewportHeight <= 0) {
    throw new Error("world stage viewport must be positive");
  }
  const scale = Math.min(viewportWidth / worldStageSize.width, viewportHeight / worldStageSize.height);
  const renderedWidth = worldStageSize.width * scale;
  const renderedHeight = worldStageSize.height * scale;
  return {
    scale,
    offsetX: (viewportWidth - renderedWidth) / 2,
    offsetY: (viewportHeight - renderedHeight) / 2,
    renderedWidth,
    renderedHeight,
  };
}

/** Covers a logical target with an image without distorting or exposing gaps. */
export function coverWorldStage(sourceWidth: number, sourceHeight: number): WorldStageRect {
  if (sourceWidth <= 0 || sourceHeight <= 0) {
    throw new Error("world stage source dimensions must be positive");
  }
  const scale = Math.max(worldStageSize.width / sourceWidth, worldStageSize.height / sourceHeight);
  const width = sourceWidth * scale;
  const height = sourceHeight * scale;
  return {
    x: (worldStageSize.width - width) / 2,
    y: (worldStageSize.height - height) / 2,
    width,
    height,
    scale,
  };
}

/** Resolves a normalized character slot onto the shared baseline in the safe area. */
export function placeWorldCharacter(normalizedX: number, sourceHeight: number) {
  if (sourceHeight <= 0) {
    throw new Error("character source height must be positive");
  }
  const clampedX = Math.min(1, Math.max(0, normalizedX));
  return {
    x: worldStageSafeArea.x + worldStageSafeArea.width * clampedX,
    y: worldStageSafeArea.y + worldStageSafeArea.height,
    scale: Math.min(1, worldStageSafeArea.height / sourceHeight),
  };
}
